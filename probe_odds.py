# -*- coding: utf-8 -*-
"""Inspect one titan007 oddslist page + schedule js format."""
import re
import sys
import urllib.request

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://www.titan007.com/",
}

URLS = [
    "https://1x2.titan007.com/oddslist/3075217.htm",
    "https://data.titan007.com/soccer_scheduleid.js?rp=20260905",
    "https://vip.titan007.com/OverDown_n.aspx?id=3075217&l=0",
    "https://vip.titan007.com/AsianOdds_n.aspx?id=3075217&l=0",
]


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def decode(raw):
    for enc in ("utf-8", "gb18030", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def main():
    for url in URLS:
        print(f"\n===== {url} =====")
        try:
            text = decode(get(url))
        except Exception as e:
            print(f"ERR {type(e).__name__}: {e}")
            continue
        print(f"len={len(text)}")
        if "scheduleid" in url or "schedule" in url.lower():
            print(text[:1500])
            continue
        if "OverDown" in url or "AsianOdds" in url:
            clean = re.sub(r"<script.*?</script>", " ", text, flags=re.S)
            clean = re.sub(r"<[^>]+>", "|", clean)
            clean = re.sub(r"\|+", "|", clean)
            clean = re.sub(r"\s+", " ", clean)
            idx = clean.find("公司")
            if idx < 0:
                idx = clean.find("威廉")
            if idx < 0:
                idx = 0
            print("TEXT:", clean[idx: idx + 2600])
            continue
        seen = set()
        for m in re.finditer(
            r"href=\"([^\"]+)\"[^>]*>([^<]{0,20})", text, re.I
        ):
            href, label = m.group(1), m.group(2).strip()
            if re.search(r"odds|asian|over|under|fenxi|analysis|change|handicap|1x2|index", href, re.I):
                key = (href, label)
                if key not in seen:
                    seen.add(key)
        for href, label in sorted(seen)[:60]:
            print(f"LINK {href[:130]} | {label[:20]}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
