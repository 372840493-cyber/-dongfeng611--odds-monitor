# -*- coding: utf-8 -*-
"""Command-line over/under line-movement scanner (titan007 public data).

Usage:
  python scan.py --once --limit 50
  python scan.py --threshold 0.25 --interval 30 --cid 1
"""

import argparse
import csv
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scanner_core as sc  # noqa: E402
import titan_common as t  # noqa: E402


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def main():
    ap = argparse.ArgumentParser(description="大小球变盘扫描器 (titan007 公开数据)")
    ap.add_argument("--threshold", type=float, default=0.25, help="盘差阈值 (默认 0.25)")
    ap.add_argument("--cid", type=int, default=47, help="公司ID (默认 47=平博)")
    ap.add_argument("--cid2", type=int, default=3, help="对照公司ID (默认 3=皇冠)")
    ap.add_argument("--interval", type=int, default=30, help="每轮间隔秒数 (默认 30)")
    ap.add_argument("--workers", type=int, default=4, help="并发数 (默认 4, 太高会被限流)")
    ap.add_argument("--limit", type=int, default=0, help="只扫前 N 场 (0=全部)")
    ap.add_argument("--once", action="store_true", help="只跑一轮")
    ap.add_argument("--csv", default="alerts.csv", help="报警 CSV 输出路径")
    args = ap.parse_args()

    alerted = set()
    skip = set()
    csv_path = args.csv
    first = True
    log(f"扫描器启动: 阈值≥{args.threshold} 公司ID={args.cid} 并发={args.workers}")
    while True:
        t0 = time.time()
        try:
            matches = t.fetch_home_matches()
        except Exception as e:
            log(f"获取比赛列表失败: {e}")
            if args.once:
                return 1
            time.sleep(args.interval)
            continue
        if not matches:
            log("比赛列表为空")
            if args.once:
                return 1
            time.sleep(args.interval)
            continue
        matches = [m for m in matches if m["sid"] not in skip]
        if args.limit:
            matches = matches[: args.limit]
        log(f"本轮 {len(matches)} 场比赛 (已跳过不开盘 {len(skip)})")
        results = sc.scan_matches(
            matches, cid=args.cid, cid2=args.cid2, workers=args.workers
        )
        ok = [r for r in results if not r.get("error")]
        err = len(results) - len(ok)
        for r in results:
            if r.get("error") == "no-data":
                skip.add(r["sid"])
        q = sc.qualify(results, args.threshold)
        log(f"解析成功 {len(ok)} 失败 {err} 达标 {len(q)}")

        need_header = first
        new_count = 0
        with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            if need_header:
                w.writerow(
                    [
                        "时间", "联赛", "开赛", "主队", "客队", "ID",
                        "主公司初盘", "主公司即时盘", "盘差", "初时间", "即时时间",
                        "皇冠即时盘",
                    ]
                )
            for r in q:
                sid = r["sid"]
                tag = "NEW" if sid not in alerted else "   "
                if sid not in alerted:
                    alerted.add(sid)
                    new_count += 1
                crown = ""
                if r.get("c2_cur_line") is not None:
                    crown = f" 皇冠即时 {sc.fmt_odds(r['c2_cur_line'], r.get('c2_cur_big'), r.get('c2_cur_small'))}"
                line = (
                    f"{tag} {r['league']} {r['time']} {r['home']} vs {r['away']} "
                    f"id={sid} 初 {sc.fmt_odds(r['open_line'], r['open_big'], r['open_small'])} "
                    f"→ 即 {sc.fmt_odds(r['cur_line'], r['cur_big'], r['cur_small'])} "
                    f"盘差 {r['diff']}{crown}"
                )
                log(line)
                w.writerow(
                    [
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        r["league"], r["time"], r["home"], r["away"], sid,
                        sc.fmt_odds(r["open_line"], r["open_big"], r["open_small"]),
                        sc.fmt_odds(r["cur_line"], r["cur_big"], r["cur_small"]),
                        r["diff"], r.get("open_time", ""), r.get("cur_time", ""),
                        sc.fmt_odds(r.get("c2_cur_line"), r.get("c2_cur_big"), r.get("c2_cur_small")),
                    ]
                )
        first = False
        log(f"新增达标 {new_count} 条")
        if args.once:
            return 0
        cost = time.time() - t0
        sleep = max(5, args.interval - cost)
        log(f"本轮耗时 {cost:.1f}s, {sleep:.0f}s 后下一轮\n")
        time.sleep(sleep)


if __name__ == "__main__":
    if sys.stdout is not None:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("已停止")
        sys.exit(0)
