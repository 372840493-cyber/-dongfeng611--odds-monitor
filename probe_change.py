# -*- coding: utf-8 -*-
"""Inspect per-company over/under change-detail page size & structure."""
import re
import os
import sys
import urllib.request

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Referer": "https://vip.titan007.com/OverDown_n.aspx?id=3075217&l=0",
}


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()


def decode(raw):
    for enc in ("gb18030", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def main():
    outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
    os.makedirs(outdir, exist_ok=True)
    for cid in ("1", "8", "1055"):
        url = (
            "https://vip.titan007.com/changeDetail/overunder.aspx?"
            f"id=3075217&companyID={cid}&l=0"
        )
        try:
            text = decode(fetch(url))
        except Exception as e:
            print(f"CID {cid} ERR {type(e).__name__}: {e}")
            continue
        out = os.path.join(outdir, f"changeDetail_{cid}.html")
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
        m = re.search(r"<title>(.*?)</title>", text, re.S)
        print(f"\nCID {cid} len={len(text)} SAVED={out} TITLE={m.group(1).strip() if m else '?'}")
        i = text.find("<tr")
        j = text.find("</table>", i)
        if i >= 0 and j > i:
            print(text[i:min(j + 8, i + 2600)])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
