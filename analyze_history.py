# -*- coding: utf-8 -*-
import json
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, ".")
import scanner_core as sc

rows = json.load(open("track_history.json", encoding="utf-8"))
stat = Counter()
by_market = defaultdict(lambda: Counter())
by_pick = defaultdict(lambda: Counter())
losses = []
pending = 0
for r in rows:
    snap = r.get("bet_snapshot") or ""
    if "倾向" not in snap:
        continue
    v = sc.result_verdict(r)
    if v is None:
        pending += 1
        continue
    key = {"✔": "win", "✘": "loss", "走盘": "push"}[v]
    stat[key] += 1
    market = "亚盘" if "[亚盘]" in snap else ("大小" if "[大小]" in snap else "其他")
    by_market[market][key] += 1
    pick = "主队" if "主队" in snap else ("客队" if "客队" in snap else ("大球" if "大球" in snap else ("小球" if "小球" in snap else "?")))
    by_pick[pick][key] += 1
    if key == "loss":
        losses.append((r.get("kickoff", ""), r.get("league", ""), r.get("home", ""), r.get("away", ""), snap, r.get("cur_score", "")))
print("TOTAL", dict(stat), "pending", pending)
for m, c in by_market.items():
    print("MARKET", m, dict(c))
for m, c in by_pick.items():
    print("PICK", m, dict(c))
print("LOSSES")
for x in sorted(losses)[-25:]:
    print(" | ".join(str(i) for i in x))
