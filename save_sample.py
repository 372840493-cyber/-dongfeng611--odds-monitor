# -*- coding: utf-8 -*-
"""Save one OverDown page to cache for parser development."""
import os
import re
import sys
import urllib.request

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Referer": "https://1x2.titan007.com/",
}

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")


def main():
    sid = sys.argv[1] if len(sys.argv) > 1 else "3075217"
    url = f"https://vip.titan007.com/OverDown_n.aspx?id={sid}&l=0"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    text = None
    for enc in ("gb18030", "gbk", "utf-8"):
        try:
            text = raw.decode(enc)
            used = enc
            break
        except UnicodeDecodeError:
            continue
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, f"OverDown_{sid}.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"SAVED {out} len={len(text)} enc={used}")
    m = re.search(r"<title>(.*?)</title>", text, re.S)
    print("TITLE:", m.group(1).strip() if m else "?")
    i = text.find("澳*")
    if i >= 0:
        print("RAW AROUND 澳*:")
        print(text[max(0, i - 800): i + 2600])
    else:
        j = text.find("公司")
        print(text[max(0, j - 200): j + 3000])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
