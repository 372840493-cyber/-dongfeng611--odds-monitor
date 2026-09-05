# -*- coding: utf-8 -*-
"""Shared scan logic: fetch per-company OU history, compute line movement."""

import concurrent.futures
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import titan_common as t  # noqa: E402


def fmt_line(x):
    if x is None:
        return "-"
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    q = round((x - int(x)) * 4)
    whole = int(x)
    if q == 1:
        return f"{whole}/{whole + 0.5:g}"
    if q == 2:
        return f"{whole + 0.5:g}"
    if q == 3:
        return f"{whole + 0.5:g}/{whole + 1:g}"
    return f"{x:g}"


def fmt_odds(line, big, small):
    if line is None:
        return "-"
    big_t = f"{big:.2f}" if big is not None else "-"
    small_t = f"{small:.2f}" if small is not None else "-"
    return f"{fmt_line(line)} [{big_t}/{small_t}]"


def fetch_one(match, cid=47, cid2=None, timeout=18):
    d = None
    last_err = None
    for attempt in range(2):
        try:
            d = t.fetch_company_ou_detail(match["sid"], cid=cid, timeout=timeout)
            break
        except Exception as e:
            last_err = e
            time.sleep(0.6 * (attempt + 1))
    if d is None:
        return {
            "sid": match["sid"],
            "error": f"{type(last_err).__name__}: {last_err}" if last_err else "fetch-fail",
        }
    if not d or d.get("open_line") is None or d.get("cur_line") is None:
        return {"sid": match["sid"], "error": "no-data"}
    row = dict(match)
    row.update(d)
    row["diff"] = t.line_diff(d["open_line"], d["cur_line"])
    if cid2:
        d2 = None
        last2 = None
        for attempt in range(2):
            try:
                d2 = t.fetch_company_ou_detail(match["sid"], cid=cid2, timeout=timeout)
                break
            except Exception as e:
                last2 = e
                time.sleep(0.6 * (attempt + 1))
        if d2 and d2.get("open_line") is not None and d2.get("cur_line") is not None:
            row["c2_open_line"] = d2["open_line"]
            row["c2_open_big"] = d2["open_big"]
            row["c2_open_small"] = d2["open_small"]
            row["c2_cur_line"] = d2["cur_line"]
            row["c2_cur_big"] = d2["cur_big"]
            row["c2_cur_small"] = d2["cur_small"]
            row["c2_diff"] = t.line_diff(d2["open_line"], d2["cur_line"])
        else:
            row["c2_error"] = "no-data" if d2 is not None else (
                f"{type(last2).__name__}: {last2}" if last2 else "fetch-fail"
            )
    return row


def scan_matches(matches, cid=47, cid2=None, workers=8, timeout=18, limit=0):
    todo = matches if not limit else matches[:limit]
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futures = [ex.submit(fetch_one, m, cid, cid2, timeout) for m in todo]
        for fut in concurrent.futures.as_completed(futures):
            try:
                results.append(fut.result())
            except Exception as e:
                results.append({"sid": "?", "error": str(e)})
    return results


def qualify(results, threshold):
    out = []
    for r in results:
        if r.get("error"):
            continue
        if r.get("diff") is not None and r["diff"] + 1e-9 >= threshold:
            out.append(r)
    out.sort(key=lambda r: float(r.get("diff") or 0), reverse=True)
    return out
