# -*- coding: utf-8 -*-
import sys

sys.path.insert(0, ".")
import scanner_core as sc
import titan_common as t

ms = t.fetch_home_matches()[:15]
home_buy = away_buy = none = sign_diff = 0
for m in ms:
    r = sc.fetch_one(m, cid=47, cid2=3, timeout=15)
    ah = r.get("ah_cur_line")
    c2 = r.get("c2ah_cur_line")
    text = sc.betting_reference(r)
    if "倾向[亚盘] 主队" in text:
        home_buy += 1
    elif "倾向[亚盘] 客队" in text:
        away_buy += 1
    else:
        none += 1
    if ah is not None and c2 is not None and ah * c2 < 0:
        sign_diff += 1
    print(m["sid"], m.get("league"), m.get("home"), "vs", m.get("away"),
          "| ah", ah, "c2ah", c2, "|", text)
print("SUMMARY home_buy", home_buy, "away_buy", away_buy, "none", none, "sign_diff", sign_diff)
