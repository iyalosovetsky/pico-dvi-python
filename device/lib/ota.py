# Over-the-air updates of the Python files and the ROMFS image (fonts, icons).
# Tiny HTTP server, every request needs header "X-Token: <secrets.OTA_TOKEN>".
#
#   GET    /info            -> {"files": {path: sha256}, "free": bytes, ...}
#   PUT    /fs/<path>       body = file; header X-SHA256 must match, written
#                            to <path>.new first, then renamed over <path>
#   DELETE /fs/<path>
#   PUT    /romfs           body = ROMFS image (mpremote romfs build format)
#   POST   /reset           reboot (also needed after /romfs)
#
# Host side: tools/ota.py. The MicroPython firmware itself is not updated here.
import asyncio
import gc
import hashlib
import json
import os

import binascii
import machine

import secrets

PORT = 8080
CHUNK = 1024
# True while the ROMFS (fonts/icons) is being rewritten: drawing must pause.
busy = False


def _sha(path):
    h = hashlib.sha256()
    buf = bytearray(CHUNK)
    with open(path, "rb") as f:
        while True:
            n = f.readinto(buf)
            if not n:
                break
            h.update(memoryview(buf)[:n])
    return binascii.hexlify(h.digest()).decode()


def _walk(d="/", out=None):
    out = {} if out is None else out
    for name, kind, *_ in os.ilistdir(d):
        p = (d.rstrip("/") + "/" + name)
        if p == "/rom":
            continue
        if kind == 0x4000:
            _walk(p, out)
        else:
            out[p] = _sha(p)
    return out


def _makedirs(path):
    parts = path.split("/")[1:-1]
    d = ""
    for part in parts:
        d += "/" + part
        try:
            os.mkdir(d)
        except OSError:
            pass


async def _respond(writer, status, body=b"", ctype="application/json"):
    if not isinstance(body, (bytes, bytearray)):
        body = json.dumps(body).encode()
    writer.write(b"HTTP/1.0 %s\r\nContent-Type: %s\r\nContent-Length: %d\r\nConnection: close\r\n\r\n"
                 % (status.encode(), ctype.encode(), len(body)))
    writer.write(body)
    await writer.drain()


async def _put_file(reader, path, length, expect):
    _makedirs(path)
    tmp = path + ".new"
    h = hashlib.sha256()
    left = length
    with open(tmp, "wb") as f:
        while left:
            data = await reader.read(min(CHUNK, left))
            if not data:
                raise OSError("short body")
            h.update(data)
            f.write(data)
            left -= len(data)
    got = binascii.hexlify(h.digest()).decode()
    if expect and got != expect:
        os.remove(tmp)
        return 400, {"error": "sha256 mismatch", "got": got}
    try:
        os.remove(path)
    except OSError:
        pass
    os.rename(tmp, path)
    return 200, {"path": path, "sha256": got, "size": length}


async def _put_romfs(reader, length):
    import vfs
    dev = vfs.rom_ioctl(2, 0)
    bs = dev.ioctl(5, 0)
    if length > dev.ioctl(4, 0) * bs:
        return 413, {"error": "image too big"}
    first = await reader.readexactly(min(length, bs))
    if not first.startswith(b"\xd2\xcd\x31"):  # ROMFS header
        return 400, {"error": "not a ROMFS image"}
    try:
        vfs.umount("/rom")
    except OSError:
        pass
    buf = bytearray(bs)
    st = [0, 0]  # next block, bytes buffered

    def flush():
        buf[st[1]:] = bytes(bs - st[1])
        dev.ioctl(6, st[0])  # erase
        dev.writeblocks(st[0], buf, 0)
        st[0] += 1
        st[1] = 0

    def feed(data):
        mv = memoryview(data)
        while len(mv):
            n = min(len(mv), bs - st[1])
            buf[st[1]:st[1] + n] = mv[:n]
            st[1] += n
            mv = mv[n:]
            if st[1] == bs:
                flush()

    feed(first)
    left = length - len(first)
    while left:
        data = await reader.read(min(CHUNK, left))
        if not data:
            raise OSError("short body")
        left -= len(data)
        feed(data)
    if st[1]:
        flush()
    return 200, {"romfs_bytes": length, "blocks": st[0], "note": "POST /reset to remount"}


async def _handle(reader, writer):
    try:
        line = (await reader.readline()).decode().split()
        if len(line) < 2:
            return
        method, path = line[0], line[1]
        headers = {}
        while True:
            h = await reader.readline()
            if h in (b"\r\n", b"\n", b""):
                break
            k, _, v = h.decode().partition(":")
            headers[k.strip().lower()] = v.strip()
        token = getattr(secrets, "OTA_TOKEN", None)
        if not token or headers.get("x-token") != token:
            await _respond(writer, "403 Forbidden", {"error": "bad token"})
            return
        length = int(headers.get("content-length", 0))
        gc.collect()
        if method == "GET" and path == "/info":
            import sys
            st = os.statvfs("/")
            await _respond(writer, "200 OK", {
                "machine": os.uname().machine, "micropython": sys.version,
                "free_ram": gc.mem_free(), "free_fs": st[0] * st[3], "files": _walk()})
        elif method == "PUT" and path.startswith("/fs/"):
            code, res = await _put_file(reader, path[3:], length, headers.get("x-sha256"))
            await _respond(writer, "%d %s" % (code, "OK" if code == 200 else "Error"), res)
        elif method == "DELETE" and path.startswith("/fs/"):
            os.remove(path[3:])
            await _respond(writer, "200 OK", {"deleted": path[3:]})
        elif method == "PUT" and path == "/romfs":
            global busy
            busy = True  # stays set: the device must be reset afterwards
            code, res = await _put_romfs(reader, length)
            await _respond(writer, "%d %s" % (code, "OK" if code == 200 else "Error"), res)
        elif method == "POST" and path == "/reset":
            await _respond(writer, "200 OK", {"reset": True})
            await writer.wait_closed() if hasattr(writer, "wait_closed") else None
            await asyncio.sleep_ms(300)
            machine.reset()
        else:
            await _respond(writer, "404 Not Found", {"error": "no route"})
    except Exception as e:
        try:
            await _respond(writer, "500 Error", {"error": repr(e)})
        except Exception:
            pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass
        gc.collect()


async def serve():
    if not getattr(secrets, "OTA_TOKEN", None):
        return  # OTA disabled
    await asyncio.start_server(_handle, "0.0.0.0", PORT)
    while True:
        await asyncio.sleep(3600)
