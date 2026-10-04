# -*- coding: utf-8 -*-
import re
import sys

sys.path.insert(0, ".")
import titan_common as t

ou = {}
ms = t.fetch_home_matches()[:25]
for m in ms:
    try:
        html = t.fetch_text(t.OU_URL.format(sid=m["sid"]), timeout=20)
        d = t.parse_ou(html, m["sid"])
    except Exception:
        continue
    for r in d.get("rows", []):
        cid, name = r.get("cid"), (r.get("name") or "").strip()
        if cid is not None and name and cid not in ou:
            ou[cid] = name

h = t.fetch_text("https://1x2.titan007.com/companies.js", timeout=20)
o1 = {int(i): n for i, n in re.findall(r"\[(\d+),'([^']*)'", h)}

print("id | 大小球/亚盘(软件公司ID用这套) | 欧赔页面")
for i in range(1, 50):
    print(f"{i:>2} | {ou.get(i, '-'):<10} | {o1.get(i, '-')}")
print("OU_IDS", sorted(ou))
