# -*- coding: utf-8 -*-
"""Probe titan007 Asian-handicap change-detail pages (Pinnacle/Crown)."""
import os
import re
import sys
import urllib.request

sys.path.insert(0, ".")
import titan_common as t  # noqa: E402


def main():
    sid = sys.argv[1] if len(sys.argv) > 1 else "3019124"
    outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
    os.makedirs(outdir, exist_ok=True)
    full_url = f"https://vip.titan007.com/AsianOdds_n.aspx?id={sid}&l=0"
    try:
        req = urllib.request.Request(
            full_url,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://1x2.titan007.com/"},
        )
        full = t._decode(urllib.request.urlopen(req, timeout=30).read())
    except Exception as e:
        print(f"FULL ERR {type(e).__name__}: {e}")
        return
    out = os.path.join(outdir, f"AsianOdds_{sid}.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(full)
    print("FULL len", len(full))
    links = sorted(set(re.findall(r'href="([^"]*changeDetail[^"]*)"', full)))
    for link in links[:25]:
        print("LINK", link)
    for cid in ("47", "3"):
        url = (
            "https://vip.titan007.com/changeDetail/handicap.aspx?"
            f"id={sid}&companyID={cid}&l=0"
        )
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": f"https://vip.titan007.com/AsianOdds_n.aspx?id={sid}&l=0",
                },
            )
            text = t._decode(urllib.request.urlopen(req, timeout=25).read())
        except Exception as e:
            print(f"CID {cid} ERR {type(e).__name__}: {e}")
            continue
        out = os.path.join(outdir, f"ah_{cid}_{sid}.html")
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
        m = re.search(r"<title>(.*?)</title>", text, re.S)
        print(f"CID {cid} len={len(text)} TITLE={m.group(1).strip() if m else '?'}")
        i = text.find("<TR")
        j = text.find("</table>", i)
        print(text[i:min(j + 8, i + 1400)] if i >= 0 and j > i else text[:600])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
