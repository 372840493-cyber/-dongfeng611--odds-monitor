# -*- coding: utf-8 -*-
"""Quick parser sanity checks (uses cached pages)."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import titan_common as t  # noqa: E402

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")


def main():
    home = open(os.path.join(CACHE, "titan_home.html"), encoding="utf-8").read()
    print("HOME_LEN", len(home))
    print("HAS_L-sclass", home.count("L-sclass"))
    print("HAS_linkmatch", home.count("linkmatch/1/"))
    ms = t.parse_home_matches(home)
    print("HOME_MATCHES", len(ms))
    for m in ms[:5]:
        print(m)
    det = t.parse_company_detail(
        open(os.path.join(CACHE, "changeDetail_1.html"), encoding="utf-8").read()
    )
    print("DETAIL_OK", det is not None)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
