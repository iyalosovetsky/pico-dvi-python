#!/usr/bin/env python3
"""Over-the-air updates for the dashboard (device side: device/lib/ota.py).

Usage:
  tools/ota.py info               files on the device + free RAM / flash
  tools/ota.py push [--reset]     upload changed files from device/ (not secrets.py)
  tools/ota.py romfs              build romfs/ into an image, upload, reboot
  tools/ota.py put LOCAL REMOTE   upload one file (e.g. secrets.py /secrets.py)
  tools/ota.py reset

Host and token come from the local secrets.py (OTA_HOST, OTA_TOKEN); OTA_HOST
defaults to picodvi.local. Firmware (.uf2) still needs USB.
"""
import hashlib
import http.client
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEVICE = ROOT / "device"
PORT = 8080


def _secrets():
    ns = {}
    exec((ROOT / "secrets.py").read_text(), ns)
    if not ns.get("OTA_TOKEN"):
        sys.exit("OTA_TOKEN missing in secrets.py")
    return ns.get("OTA_HOST", "picodvi.local"), ns["OTA_TOKEN"]


HOST, TOKEN = _secrets()


def request(method, path, body=None, headers=None, timeout=60):
    c = http.client.HTTPConnection(HOST, PORT, timeout=timeout)
    h = {"X-Token": TOKEN}
    h.update(headers or {})
    if body is not None:
        h["Content-Length"] = str(len(body))
    c.request(method, path, body=body, headers=h)
    r = c.getresponse()
    data = r.read()
    c.close()
    try:
        res = json.loads(data)
    except ValueError:
        res = data.decode(errors="replace")
    if r.status != 200:
        sys.exit(f"{method} {path}: {r.status} {res}")
    return res


def local_files():
    """device/ tree -> {remote path: local Path}, secrets.py is never pushed."""
    out = {}
    for p in sorted(DEVICE.rglob("*.py")):
        rel = "/" + p.relative_to(DEVICE).as_posix()
        out[rel] = p
    return out


def put(local, remote):
    data = Path(local).read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    res = request("PUT", "/fs" + remote, data, {"X-SHA256": sha})
    print(f"  {remote}  {res['size']} B")


def cmd_info():
    info = request("GET", "/info")
    print(f"{info['machine']}\n{info['micropython']}")
    print(f"free RAM {info['free_ram']} B, free flash {info['free_fs']} B")
    for path, sha in sorted(info["files"].items()):
        print(f"  {path:28s} {sha[:12]}")


def cmd_push(reset):
    remote = request("GET", "/info")["files"]
    changed = []
    for rpath, lpath in local_files().items():
        if hashlib.sha256(lpath.read_bytes()).hexdigest() != remote.get(rpath):
            changed.append((lpath, rpath))
    if not changed:
        print("device is up to date")
    else:
        print(f"uploading {len(changed)} file(s):")
        for lpath, rpath in changed:
            put(lpath, rpath)
    if reset or (changed and "--no-reset" not in sys.argv):
        cmd_reset()


def cmd_romfs():
    from mpremote.romfs import make_romfs
    img = make_romfs(str(ROOT / "romfs"), mpy_cross=False)
    print(f"ROMFS image {len(img)} B, uploading...")
    res = request("PUT", "/romfs", img, timeout=180)
    print(f"  written {res['blocks']} blocks")
    cmd_reset()


def cmd_reset():
    request("POST", "/reset")
    print("device is rebooting")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    cmd = args[0] if args else "info"
    if cmd == "info":
        cmd_info()
    elif cmd == "push":
        cmd_push("--reset" in sys.argv)
    elif cmd == "romfs":
        cmd_romfs()
    elif cmd == "put" and len(args) == 3:
        put(args[1], args[2])
    elif cmd == "reset":
        cmd_reset()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
