# -*- coding: utf-8 -*-
"""Check homepage data-time format for known matches."""
import re
import sys

sys.path.insert(0, ".")
import titan_common as t  # noqa: E402


def main():
    html = t.fetch_text(t.HOME_URL, timeout=40)
    ids = ["2993778", "3013679", "3003871", "3046975"]
    for sid in ids:
        m = re.search(
            r'<div class="title matchinfo"[^>]*?data-scheduleid="\s*'
            + sid
            + r'\s*"[^>]*?>(?:(?!</div>\s*<ul).)*?</div>\s*<ul',
            html,
            re.S,
        )
        if not m:
            print(sid, "NOT FOUND")
            continue
        head = m.group(0)
        dt = re.search(r'data-time="([^"]*)"', head)
        tm = re.search(r'<span class="L-time">\s*([^<]+)</span>', head)
        league = re.search(r'<span class="league"[^>]*>\s*([^<]+)</span>', head)
        tit = re.search(r'class="tit">(.*?)</a>', head, re.S)
        teams = re.sub(r"<[^>]+>", " ", tit.group(1)) if tit else ""
        teams = re.sub(r"\s+", " ", teams).strip()
        print(sid, "| league:", league.group(1).strip() if league else "?",
              "| show:", tm.group(1).strip() if tm else "?",
              "| data-time:", dt.group(1).strip() if dt else "?",
              "|", teams)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
