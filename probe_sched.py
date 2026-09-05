# -*- coding: utf-8 -*-
"""Probe titan007 schedule/base-data JS files + match title format."""
import re
import sys
import urllib.request

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.titan007.com/",
}

URLS = [
    "https://live.titan007.com/vbsxml/Ballpub/BaSID.js?r=007",
    "https://m.titan007.com/txt/basid.js",
    "https://1x2.titan007.com/oddslist/3075217.htm",
    "https://zq.titan007.com/analysis/3075217cn.htm",
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
        if "basid" in url.lower() or "BaSID" in url:
            print(text[:1800])
            continue
        m = re.search(r"<title>(.*?)</title>", text, re.S)
        print("TITLE:", m.group(1).strip() if m else "?")
        body = re.sub(r"<script.*?</script>", " ", text, flags=re.S)
        body = re.sub(r"<[^>]+>", "|", body)
        body = re.sub(r"\|+", "|", body)
        body = re.sub(r"\s+", " ", body).strip()
        print("BODY:", body[:800])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
