# -*- coding: utf-8 -*-
"""List SPF companies matching Pinnacle/Crown in the JS data file."""
import re
import sys
import urllib.request

sys.path.insert(0, ".")
import titan_common as t  # noqa: E402


def main():
    sid = sys.argv[1] if len(sys.argv) > 1 else "3019124"
    url = f"https://1x2d.titan007.com/{sid}.js?r=007134330874330588340"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://1x2.titan007.com/"},
    )
    text = t._decode(urllib.request.urlopen(req, timeout=25).read())
    a = text.find("var game=Array(")
    b = text.find(");", a)
    body = text[a + len("var game=Array("):b]
    entries = re.findall(r'"((?:[^"\\]|\\.)*)"', body, re.S)
    print("ENTRIES", len(entries))
    for e in entries:
        p = e.split("|")
        if len(p) < 22:
            continue
        hay = p[2] + " " + p[21]
        if re.search(r"Pin|Crown|皇|平", hay):
            print(p[0], "|", p[2], "|", p[21])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
