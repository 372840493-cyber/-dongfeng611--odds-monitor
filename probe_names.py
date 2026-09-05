# -*- coding: utf-8 -*-
"""Compare homepage names vs per-match page title names."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import titan_common as t  # noqa: E402


def main():
    ids = sys.argv[1:] or ["3001168", "3000054", "3075217"]
    home = {}
    for m in t.parse_home_matches(
        open(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "titan_home.html"),
            encoding="utf-8",
        ).read()
    ):
        home[m["sid"]] = m
    for sid in ids:
        try:
            html = t.fetch_text(f"https://1x2.titan007.com/oddslist/{sid}.htm", timeout=25)
            mt = re.search(r"<title>(.*?)</title>", html, re.S)
            title = mt.group(1).strip() if mt else "?"
        except Exception as e:
            title = f"ERR {e}"
        hm = home.get(sid)
        print(sid, "| HOME:", hm["home"] if hm else "?", "vs", hm["away"] if hm else "?")
        print(sid, "| PAGE:", title)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
