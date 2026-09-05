# -*- coding: utf-8 -*-
"""Diagnose per-match OU fetch failures: sequential vs parallel."""
import sys
import time

sys.path.insert(0, ".")
import scanner_core as sc  # noqa: E402
import titan_common as t  # noqa: E402


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    mode = sys.argv[2] if len(sys.argv) > 2 else "seq"
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    matches = t.fetch_home_matches()[:n]
    if mode == "seq":
        results = []
        for m in matches:
            results.append(sc.fetch_one(m, cid=1, timeout=15))
            time.sleep(0.15)
    else:
        results = sc.scan_matches(matches, cid=1, workers=workers, timeout=15)
    ok = [r for r in results if not r.get("error")]
    fail = [r for r in results if r.get("error")]
    print(f"mode={mode} n={n} ok={len(ok)} fail={len(fail)}")
    for r in fail[:20]:
        print("FAIL", r["sid"], r.get("error"))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
