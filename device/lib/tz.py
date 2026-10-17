# Europe/Kyiv local time from a UTC epoch (EU DST rule, no tz database needed).
import time

WEEKDAYS = ("понеділок", "вівторок", "середа", "четвер", "п’ятниця", "субота", "неділя")
MONTHS = ("січня", "лютого", "березня", "квітня", "травня", "червня",
          "липня", "серпня", "вересня", "жовтня", "листопада", "грудня")


def _last_sunday_utc(year, month):
    # 01:00 UTC on the last Sunday of the month (EU switch moment)
    days = 31  # March and October both have 31 days
    t = time.mktime((year, month, days, 1, 0, 0, 0, 0, 0))
    wd = time.gmtime(t)[6]  # Monday = 0
    return t - ((wd + 1) % 7) * 86400


def utc_offset(utc):
    year = time.gmtime(utc)[0]
    dst = _last_sunday_utc(year, 3) <= utc < _last_sunday_utc(year, 10)
    return 3 * 3600 if dst else 2 * 3600


def localtime(utc=None):
    if utc is None:
        utc = time.time()
    return time.gmtime(utc + utc_offset(utc))


def date_text(t):
    """'субота, 17 жовтня' for a localtime() tuple."""
    return "%s, %d %s" % (WEEKDAYS[t[6]], t[2], MONTHS[t[1] - 1])
