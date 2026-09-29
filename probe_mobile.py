# -*- coding: utf-8 -*-
import re
import sys

sys.path.insert(0, ".")
import titan_common as t

h = t.fetch_text("https://m.titan007.com/", timeout=15)
print("LEN", len(h))
hrefs = sorted(set(re.findall(r'href="([^"]+)"', h)))
print("HREFS", len(hrefs))
for x in hrefs[:80]:
    print(" H", x)
srcs = sorted(set(re.findall(r'src="([^"]+)"', h)))
print("SRCS", len(srcs))
for x in srcs[:40]:
    print(" S", x)
