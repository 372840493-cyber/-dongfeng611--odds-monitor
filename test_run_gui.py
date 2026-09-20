# -*- coding: utf-8 -*-
"""Drive ScannerApp through one real scan pass (no manual click needed)."""
import sys
import time

sys.path.insert(0, ".")
from scan_gui import ScannerApp  # noqa: E402


def main():
    app = ScannerApp()
    app.e_thr.delete(0, "end")
    app.e_thr.insert(0, "0.25")
    app.e_cid.delete(0, "end")
    app.e_cid.insert(0, "47")
    app.start()
    deadline = time.time() + 420
    seen = 0
    while time.time() < deadline:
        app.update()
        time.sleep(1)
        n = len(app.last_rows)
        if n != seen:
            seen = n
            print(f"t={int(time.time() % 1000)} last_rows={n} status={app.status.cget('text')}", flush=True)
        if n and "达标" in app.status.cget("text"):
            break
    app.update()
    print("FINAL_ROWS", len(app.last_rows), "STATUS", app.status.cget("text"), flush=True)
    for iid in list(app.tree.get_children())[:3]:
        vals = app.tree.item(iid, "values")
        print("ROW", vals, flush=True)
    app.running = False
    app.destroy()


if __name__ == "__main__":
    main()
