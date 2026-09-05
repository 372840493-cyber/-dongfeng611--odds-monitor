# -*- coding: utf-8 -*-
"""Inspect titan007 European odds (胜平负) page structure."""
import os
import re
import sys

sys.path.insert(0, ".")
import titan_common as t  # noqa: E402


def main():
    sid = sys.argv[1] if len(sys.argv) > 1 else "3019124"
    url = f"https://1x2.titan007.com/oddslist/{sid}.htm"
    html = t.fetch_text(url, timeout=25)
    outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, f"oddslist_{sid}.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print("SAVED", out, "len", len(html))
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    print("TITLE", m.group(1).strip() if m else "?")
    i = html.find("平*")
    if i < 0:
        i = html.find("威*")
    if i < 0:
        i = html.find("澳*")
    print("SEG:", html[max(0, i - 1200): i + 2200].replace("\r", ""))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
