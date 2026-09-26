# -*- coding: utf-8 -*-
import concurrent.futures
import sys

sys.path.insert(0, ".")
import titan_common as t

ms = t.fetch_home_matches()[:30]


def one(m):
    try:
        d = t.fetch_company_ah_detail(m["sid"], cid=47, timeout=15)
    except Exception as e:
        return m, None
    return m, d


neg = 0
zero = 0
pos = 0
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
    for m, d in ex.map(one, ms):
        if not d:
            print(m["sid"], "NO_DATA", m.get("league"), m.get("home"), m.get("away"))
            continue
        line = d.get("cur_line")
        wh = d.get("cur_water_h")
        wa = d.get("cur_water_a")
        if line is None:
            continue
        if line < 0:
            neg += 1
        elif abs(line) < 1e-9:
            zero += 1
        else:
            pos += 1
        print(m["sid"], line, wh, wa, m.get("league"), m.get("home"), "vs", m.get("away"))
print("SUMMARY pos", pos, "zero", zero, "neg", neg)
