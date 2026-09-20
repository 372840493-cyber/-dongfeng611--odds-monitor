# -*- coding: utf-8 -*-
"""Find authoritative final score for a finished match."""
import re
import sys

sys.path.insert(0, ".")
import titan_common as t  # noqa: E402


def main():
    sid = sys.argv[1] if len(sys.argv) > 1 else "2914689"
    urls = [
        f"https://zq.titan007.com/analysis/{sid}cn.htm",
        f"https://vip.titan007.com/AsianOdds_n.aspx?id={sid}&l=0",
        f"https://vip.titan007.com/OverDown_n.aspx?id={sid}&l=0",
    ]
    for url in urls:
        try:
            html = t.fetch_text(url, timeout=25)
        except Exception as e:
            print(url, "ERR", type(e).__name__, str(e)[:120])
            continue
        print("\n==", url, "len", len(html))
        hits = re.findall(r"(\d{1,2})\s*[-:]\s*(\d{1,2})", html)
        print("score-like count", len(hits), hits[:15])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
