# -*- coding: utf-8 -*-
"""Fetch titan007 homepage and print contexts around match/odds links."""
import os
import re
import sys
import urllib.request

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "titan_home.html")
UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
}

PATTERNS = [
    r"[^<>\"']*(?:changeDetail|multiOverunder|overunderHalf|OverDown|AsianOdds|AsianHandicap|oddslist)[^<>\"']*",
    r"[^<>\"']*(?:analysis|fenxi|1x2|index)[^<>\"']*",
]


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    url = "https://www.titan007.com/"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r:
        raw = r.read()
    for enc in ("utf-8", "gb18030"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"SAVED {OUT} len={len(text)}")
    seen = set()
    for pat in PATTERNS:
        for m in re.finditer(pat, text, re.I):
            s = m.group(0).strip()
            if len(s) < 240 and s not in seen:
                seen.add(s)
    for s in sorted(seen)[:120]:
        print("CTX:", s.replace("\n", " ")[:230])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
