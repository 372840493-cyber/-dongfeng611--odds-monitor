# -*- coding: utf-8 -*-
import sys

sys.path.insert(0, ".")
import titan_common as t

mapping = {}
ms = t.fetch_home_matches()[:6]
for m in ms:
    try:
        html = t.fetch_text(t.OU_URL.format(sid=m["sid"]), timeout=20)
        d = t.parse_ou(html, m["sid"])
    except Exception as e:
        print("ERR", m["sid"], type(e).__name__)
        continue
    for r in d.get("rows", []):
        cid = r.get("cid")
        name = (r.get("name") or "").strip()
        if cid is not None and name and cid not in mapping:
            mapping[cid] = name
for cid in sorted(mapping):
    print(f"{cid:>4}  {mapping[cid]}")
print("TOTAL", len(mapping))
