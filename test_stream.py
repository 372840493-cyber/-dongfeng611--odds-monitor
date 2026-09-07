# -*- coding: utf-8 -*-
"""Quick check: rows appear incrementally before the scan pass finishes."""
import sys
import time

sys.path.insert(0, ".")
import scan_gui  # noqa: E402
import titan_common as t  # noqa: E402
from scan_gui import ScannerApp  # noqa: E402


def fake_fetch_home():
    return [
        {
            "sid": str(i),
            "league": "测试",
            "time": f"19:{i:02d}",
            "kickoff": f"2026-09-05 19:{i:02d}",
            "home": f"主{i}",
            "away": f"客{i}",
        }
        for i in range(6, 10)
    ]


def fake_scan(matches, cid=47, cid2=None, workers=8, timeout=18, limit=0, on_result=None):
    out = []
    for m in matches:
        time.sleep(0.3)
        r = dict(m)
        r.update(
            {
                "open_line": 2.5,
                "cur_line": 3.0,
                "diff": 0.5,
                "c2_cur_line": 3.0,
                "spf_pin_open": (2.2, 3.4, 3.1),
                "spf_pin_cur": (2.0, 3.5, 3.5),
                "spf_crown_cur": (2.1, 3.4, 3.3),
            }
        )
        out.append(r)
        if on_result:
            on_result(r)
    return out


def main():
    t.fetch_home_matches = fake_fetch_home
    scan_gui.sc.scan_matches = fake_scan
    app = ScannerApp()
    app.start()
    t0 = time.time()
    first = None
    for _ in range(80):
        app.update()
        time.sleep(0.1)
        if app.last_rows and first is None:
            first = time.time() - t0
    app.update()
    print("FIRST_ROW_AT_SECONDS", round(first, 2) if first else None)
    print("ROWS_AFTER", len(app.last_rows))
    print("STATUS", app.status.cget("text"))
    app.running = False
    app.destroy()


if __name__ == "__main__":
    main()
