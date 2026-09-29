# -*- coding: utf-8 -*-
import sys
import time

sys.path.insert(0, ".")
from scan_gui import ScannerApp

a = ScannerApp()
orig_put = a.events.put


def put(ev):
    try:
        if ev and ev[0] in ("log", "daily_mail"):
            print("EVENT", ev[0], ev[1] if len(ev) > 1 else "")
    except Exception:
        pass
    orig_put(ev)


a.events.put = put
a._append_log = lambda msg: print("LOG", msg)
print("BUY_ROWS", len([r for r in a.all_rows if "倾向" in __import__("scanner_core").bet_cell(r)]))
a._send_digest_now()
time.sleep(12)
a.destroy()
print("DONE")
