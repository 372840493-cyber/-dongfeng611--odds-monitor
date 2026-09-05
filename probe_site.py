# -*- coding: utf-8 -*-
"""Probe titan007 public pages to locate match list + over/under detail links."""
import re
import sys
import urllib.request

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
}

CANDIDATES = [
    "https://vip.titan007.com/",
    "https://www.titan007.com/",
    "https://live.titan007.com/",
    "http://vip.titan007.com/",
    "https://m.titan007.com/",
]

PATTERNS = [
    r'href="([^"]*(?:overunder|OverDown|asian|AsianOdds|oddslist|changeDetail|fenxi|analysis)[^"]*)"',
    r"src=\"([^\"]*(?:js|xml|json)[^\"]*)\"",
]


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            final = r.geturl()
            ctype = r.headers.get("Content-Type", "")
    except Exception as e:
        return None, None, None, f"ERR {type(e).__name__}: {e}"
    text = None
    for enc in ("utf-8", "gb18030", "gbk"):
        try:
            text = raw.decode(enc)
            used = enc
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = raw.decode("utf-8", errors="replace")
        used = "utf8-replace"
    return text, len(raw), final, f"{ctype} enc={used}"


def main():
    for url in CANDIDATES:
        text, size, final, meta = fetch(url)
        if text is None:
            print(f"\n== {url}\n{meta}")
            continue
        print(f"\n== {url}\nstatus ok size={size} meta={meta} final={final}")
        hits = set()
        for pat in PATTERNS:
            for m in re.finditer(pat, text, re.I):
                hits.add(m.group(1))
        for h in sorted(hits)[:40]:
            print("  LINK:", h[:180])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
