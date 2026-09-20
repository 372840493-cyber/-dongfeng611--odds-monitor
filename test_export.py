# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, ".")
import scan_gui
from scan_gui import ScannerApp

out = os.path.join(".cache", "export_check.csv")
a = ScannerApp()
a._ask_export_scope = lambda: "buy"
scan_gui.filedialog.asksaveasfilename = lambda **k: out
a.last_rows = [
    {
        "sid": "1",
        "league": "美冠联",
        "time": "07:00",
        "kickoff": "2026-09-15 07:00",
        "home": "印地十一",
        "away": "布鲁克林",
        "bet_snapshot": "倾向[亚盘] 主队 半球/一球",
    },
    {
        "sid": "2",
        "league": "英超",
        "time": "20:00",
        "kickoff": "2026-09-15 20:00",
        "home": "A",
        "away": "B",
    },
]
a.export_csv()
a.destroy()
print(open(out, encoding="utf-8-sig").read())
