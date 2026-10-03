# -*- coding: utf-8 -*-
import re
import sys

sys.path.insert(0, ".")
import titan_common as t

h = t.fetch_text("https://1x2.titan007.com/companies.js", timeout=20)
m = {int(i): n for i, n in re.findall(r"\[(\d+),'([^']*)'", h)}
print("COUNT", len(m))
for k in (1, 2, 49):
    print(k, m.get(k))
print("---ALL---")
for k in sorted(m):
    print(k, m[k])
