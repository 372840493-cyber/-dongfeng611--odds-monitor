# -*- coding: utf-8 -*-
"""Shared scan logic: fetch per-company OU history, compute line movement."""

import concurrent.futures
import os
import re
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


def fmt_spf(o):
    if not o or len(o) < 3:
        return "-"
    vals = []
    for x in o:
        try:
            vals.append(f"{float(x):.2f}")
        except (TypeError, ValueError):
            vals.append("-")
    return "/".join(vals)


def spf_pick(o):
    """Return the most likely side ('主胜'/'平局'/'客胜') from normalized odds."""
    if not o or len(o) < 3:
        return None
    odds = []
    for x in o:
        try:
            odds.append(float(x))
        except (TypeError, ValueError):
            odds.append(None)
    if not all(odds):
        return None
    inv = [1.0 / x for x in odds]
    s = sum(inv)
    probs = [x / s for x in inv]
    idx = probs.index(max(probs))
    return ("主胜", "平局", "客胜")[idx]


def spf_tendency(pin_cur, crown_cur):
    """Compare Pinnacle vs Crown 1X2 direction."""
    p = spf_pick(pin_cur)
    c = spf_pick(crown_cur)
    if p is None and c is None:
        return ""
    if p is None:
        return f"仅皇冠:{c}"
    if c is None:
        return f"仅平博:{p}"
    if p == c:
        return f"{p}(两家一致)"
    return f"平博{p} vs 皇冠{c}"


def ou_signal(r, water_th=0.05):
    """Rule table (Pinnacle over/under): line move x over-water change.
    升盘/降盘 by line; 大/小 by |over-water change| >= water_th.
    """
    o_line, c_line = r.get("open_line"), r.get("cur_line")
    o_big, c_big = r.get("open_big"), r.get("cur_big")
    if o_line is None or c_line is None or o_big is None or c_big is None:
        return ""
    ld = c_line - o_line
    wd = c_big - o_big
    if abs(ld) < 1e-9:
        move = "平盘"
    elif ld > 0:
        move = "升盘"
    else:
        move = "降盘"
    if abs(wd) >= water_th:
        cat = "大" + ("降水" if wd < 0 else "升水")
    else:
        cat = "小" + ("降水" if wd < 0 else ("升水" if wd > 0 else "持平"))
    key = move + "+" + cat
    table = {
        "升盘+大降水": "🔥 强大 · 大球强势",
        "升盘+大升水": "⚠️ 升盘阻大",
        "降盘+小降水": "🔥 强小 · 小球强势",
        "降盘+小升水": "⚠️ 不一定真小",
        "降盘+大降水": "🟡 重点观察 · 可能降盘诱大",
        "升盘+小降水": "🟡 可能阻大/造小",
        "平盘+大降水": "🟡 平盘大球水位急降 · 偏大观察",
        "平盘+小降水": "平盘 · 水位略降",
        "平盘+大升水": "平盘 · 大球水位急升",
        "平盘+小升水": "平盘 · 水位略升",
        "升盘+小升水": "升盘 · 水位配合一般",
        "降盘+大升水": "降盘 · 大球水位急升(偏小观察)",
    }
    return table.get(key, f"{move}+{cat}")


def _side(open_line, cur_line):
    if open_line is None or cur_line is None:
        return ""
    d = cur_line - open_line
    if abs(d) < 1e-9:
        return ""
    return "大" if d > 0 else "小"


def combined_signal(r):
    """Combine Pinnacle OU rule signal + Crown comparison."""
    out = ou_signal(r) or "平博无盘口数据"
    bits = []
    pin_cur = r.get("cur_line")
    crown_cur = r.get("c2_cur_line")
    if pin_cur is not None and crown_cur is not None:
        if abs(crown_cur - pin_cur) < 1e-9:
            bits.append("皇冠与平博同盘")
        elif crown_cur > pin_cur:
            bits.append(f"皇冠高盘 {sc_line(crown_cur)}>{sc_line(pin_cur)}(偏大)")
        else:
            bits.append(f"皇冠低盘 {sc_line(crown_cur)}<{sc_line(pin_cur)}(偏小)")
    crown_side = _side(r.get("c2_open_line"), crown_cur)
    if crown_side:
        bits.append(f"皇冠自身{'升盘偏大' if crown_side == '大' else '降盘偏小'}")
    pin_side = _side(r.get("open_line"), pin_cur)
    if pin_side and crown_side:
        if pin_side == crown_side:
            bits.append("两家同向")
        else:
            bits.append("两家反向")
    if bits:
        out += " ｜ " + "，".join(bits)
    if r.get("ou_consensus"):
        out += " ｜ 全平台:" + r["ou_consensus"]
    return out


def sc_line(x):
    return fmt_line(x)


def _water_sub(open_big, open_small, cur_big, cur_small, cap):
    if open_big is None or cur_big is None:
        return 0
    wd = cur_big - open_big  # 大球水位变化: 负=降水(大球热)
    if wd <= -0.08:
        base = cap
    elif wd <= -0.05:
        base = int(cap * 0.9)
    elif wd <= -0.02:
        base = int(cap * 0.7)
    elif wd >= 0.08:
        base = int(cap * 0.2)
    elif wd >= 0.05:
        base = int(cap * 0.3)
    elif wd >= 0.02:
        base = int(cap * 0.45)
    else:
        base = int(cap * 0.6)
    if open_small is not None and cur_small is not None:
        sd = cur_small - open_small
        if (wd < 0 and sd > 0.02) or (wd > 0 and sd < -0.02):
            base = min(cap, base + 1)
    return base


def size_score(r):
    """大小球专用评分 (满分 35)."""
    sig = ou_signal(r)
    pin_side = _side(r.get("open_line"), r.get("cur_line"))
    crown_side = _side(r.get("c2_open_line"), r.get("c2_cur_line"))
    strong = ("强大" in sig) or ("强小" in sig)

    # 方向分 0-8
    dir_score = 0
    if pin_side:
        if crown_side == pin_side:
            dir_score = 8 if strong else 6
        elif not crown_side:
            dir_score = 5 if strong else 3
        else:
            dir_score = 3 if strong else 1

    # 水位结构分 0-15 (平博8 + 皇冠7)
    water_score = _water_sub(
        r.get("open_big"), r.get("open_small"),
        r.get("cur_big"), r.get("cur_small"), 8,
    ) + _water_sub(
        r.get("c2_open_big"), r.get("c2_open_small"),
        r.get("c2_cur_big"), r.get("c2_cur_small"), 7,
    )

    # 一致性分 0-12
    cons_score = 0
    o1, c1 = r.get("open_line"), r.get("cur_line")
    o2, c2 = r.get("c2_open_line"), r.get("c2_cur_line")
    if o1 is not None and o2 is not None:
        same_line = c1 is not None and c2 is not None and abs(c1 - c2) < 1e-9
        if pin_side and crown_side:
            if pin_side == crown_side:
                cons_score = 12 if same_line else 9
            else:
                cons_score = 0
        elif not pin_side and not crown_side:
            cons_score = 4
        else:
            cons_score = 4
    total = min(35, dir_score + water_score + cons_score)
    return {
        "dir": dir_score,
        "water": water_score,
        "cons": cons_score,
        "total": total,
    }


def size_score_text(r):
    s = size_score(r)
    t = s["total"]
    if t >= 30:
        level = "强"
    elif t >= 25:
        level = "中强"
    elif t >= 20:
        level = "普通"
    else:
        level = "低"
    return (
        f"{t}/35 {level} "
        f"(方向{s['dir']}/水位{s['water']}/一致{s['cons']})"
    )


def fmt_ah_line(x):
    if x is None:
        return "-"
    if abs(x) < 1e-9:
        return "平手"
    return f"{'让' if x > 0 else '受'}{abs(x):.2g}"


def fmt_ah_pair(r, tag):
    o = r.get(f"{tag}_open_line")
    c = r.get(f"{tag}_cur_line")
    if c is None:
        return "-"
    oh = r.get(f"{tag}_open_water_h")
    oa = r.get(f"{tag}_open_water_a")
    ch = r.get(f"{tag}_cur_water_h")
    ca = r.get(f"{tag}_cur_water_a")
    w = lambda a, b: f"{a:.2f}/{b:.2f}" if a is not None and b is not None else "-"
    return f"{fmt_ah_line(o)}[{w(oh, oa)}] → {fmt_ah_line(c)}[{w(ch, ca)}]"


def ah_model_text(r):
    """Layer-2 model: Asian handicap direction + probability + strength."""
    parts = []
    for tag, label in (("ah", "平博"), ("c2ah", "皇冠")):
        cur = r.get(f"{tag}_cur_line")
        if cur is None:
            continue
        opn = r.get(f"{tag}_open_line")
        wh = r.get(f"{tag}_cur_water_h")
        wa = r.get(f"{tag}_cur_water_a")
        side = "主" if cur >= 0 else "客"
        prob = None
        if wh and wa:
            inv_h, inv_a = 1.0 / wh, 1.0 / wa
            p_home = inv_h / (inv_h + inv_a)
            prob = p_home if cur >= 0 else 1.0 - p_home
        mv = "不变"
        if opn is not None:
            d = abs(cur) - abs(opn)
            if d > 1e-9:
                mv = "加深"
            elif d < -1e-9:
                mv = "回调"
        prob_txt = f"{prob * 100:.0f}%" if prob is not None else "?"
        parts.append(f"{label}:{side}{fmt_ah_line(cur)}{mv} 强度{prob_txt}")
    return " ｜ ".join(parts)


def layer2_text(r):
    parts = []
    ah = ah_model_text(r)
    if ah:
        parts.append("亚盘:" + ah)
    parts.append("大小:" + size_score_text(r))
    return " ｜ ".join(parts)


def betting_reference(r):
    """Layer-3 reference conclusion (no odds-value filter yet)."""
    buys = []
    s = size_score(r)
    pin_side = _side(r.get("open_line"), r.get("cur_line"))
    crown_side = _side(r.get("c2_open_line"), r.get("c2_cur_line"))
    sig = ou_signal(r)
    trap = ("⚠️" in sig) or ("🟡" in sig)
    strong = ("强大" in sig) or ("强小" in sig)
    if (
        s["total"] >= 25
        and pin_side
        and pin_side == crown_side
        and strong
        and not trap
    ):
        allow = {"大": "升盘+降水", "小": "降盘+升水"}.get(pin_side)
        pf = r.get("platform")
        if pf and allow and pf.get("top") == allow and pf.get("top_pct", 0) >= 40:
            line = r.get("cur_line")
            if line is not None:
                direction = "小球" if pin_side == "小" else "大球"
                buys.append(f"倾向[大小] {direction} {fmt_line(line)}")
    ah_cur = r.get("ah_cur_line")
    c2ah_cur = r.get("c2ah_cur_line")
    if ah_cur is not None and c2ah_cur is not None and ah_cur * c2ah_cur > 0:
        wh = r.get("ah_cur_water_h")
        wa = r.get("ah_cur_water_a")
        if wh and wa:
            inv_h, inv_a = 1.0 / wh, 1.0 / wa
            p_home = inv_h / (inv_h + inv_a)
            prob = p_home if ah_cur >= 0 else 1.0 - p_home
            if prob >= 0.55:
                if ah_cur >= 0:
                    buys.append(f"倾向[亚盘] 主队 {_ah_cn(ah_cur).lstrip('让')}")
                else:
                    buys.append(f"倾向[亚盘] 客队 受{_ah_cn(ah_cur).lstrip('受')}")
    if not buys:
        return "不建议下注"
    return " ｜ ".join(buys)


def _bet_num(x):
    return f"{float(x):.2f}".rstrip("0").rstrip(".")


def _split_line(line):
    """Split a quarter line into its two full/half legs, e.g. 0.75 -> [0.5, 1.0]."""
    h = line * 2
    if abs(h - round(h)) < 1e-9:
        return [line]
    import math

    lo = math.floor(h) / 2.0
    hi = math.ceil(h) / 2.0
    return sorted([lo, hi])


def _leg_result_gt(value, leg):
    if value > leg + 1e-9:
        return 1
    if value < leg - 1e-9:
        return -1
    return 0


def result_verdict(r):
    """After full time: settle each 倾向 in the betting cell against final score.
    Returns ('✔', ...) hit / ('✘', ...) miss / ('走盘', ...) or None if not settled.
    """
    if not score_status(r).startswith("完场"):
        return None
    score = (r.get("cur_score") or "").strip()
    if "-" not in score:
        return None
    try:
        hs, as_ = score.split("-", 1)
        home_g, away_g = int(hs.strip()), int(as_.strip())
    except (TypeError, ValueError):
        return None
    total = home_g + away_g
    margin = home_g - away_g
    text = r.get("bet_snapshot") or betting_reference(r)
    if not text or "倾向" not in text:
        return None
    wins = []
    for seg in text.split("｜"):
        seg = seg.strip()
        if not seg:
            continue
        if "倾向[大小]" in seg:
            m = re.search(r"(大球|小球)\s+([0-9.]+/[0-9.]+|[0-9.]+)", seg)
            if not m:
                continue
            side = m.group(1)
            line = t.parse_line(m.group(2))
            if line is None:
                continue
            for leg in _split_line(line):
                if side == "大球":
                    wins.append(_leg_result_gt(total, leg))
                else:
                    wins.append(-_leg_result_gt(total, leg))
        elif "倾向[亚盘]" in seg:
            m = re.search(r"(主队|客队)\s+(.+)", seg)
            if not m:
                continue
            side = m.group(1)
            term = m.group(2).strip()
            line = t.parse_ah_line(term)
            if line is None:
                continue
            for leg in _split_line(abs(line)) if line >= 0 else _split_line(-abs(line)):
                # buy side wins when actual margin beats the signed handicap leg
                wins.append(_leg_result_gt(margin, leg))
    if not wins:
        return None
    if any(w < 0 for w in wins):
        return "✘"
    if any(w > 0 for w in wins):
        return "✔"
    return "走盘"


def bet_cell(r):
    text = betting_reference(r)
    snap = r.get("bet_snapshot")
    if snap and "倾向" in snap:
        text = snap
    mark = result_verdict(r)
    if mark:
        return f"{text} {mark}"
    return text


def _ah_cn(x):
    table = {
        0.25: "平手/半球", 0.5: "半球", 0.75: "半球/一球", 1.0: "一球",
        1.25: "一球/球半", 1.5: "球半", 1.75: "球半/两球", 2.0: "两球",
        2.25: "两球/两球半", 2.5: "两球半", 2.75: "两球半/三球", 3.0: "三球",
    }
    v = abs(float(x))
    term = table.get(v, f"{v:.2g}")
    if x >= 0:
        return f"让{term}"
    return f"受{term}"


def score_status(r):
    from datetime import datetime, timedelta

    score = (r.get("cur_score") or "").strip()
    minute = (r.get("cur_minute") or "").strip()
    ko = r.get("kickoff")
    now = datetime.now()
    if score:
        if ko:
            try:
                ko_dt = datetime.strptime(ko, "%Y-%m-%d %H:%M")
                if now >= ko_dt + timedelta(minutes=135):
                    return f"完场 {score}"
            except ValueError:
                pass
        if minute and minute.isdigit():
            return f"{score} {minute}'"
        return f"进行中 {score}"
    if ko:
        try:
            if now >= datetime.strptime(ko, "%Y-%m-%d %H:%M") + timedelta(minutes=10):
                return "已开赛(比分更新中)"
        except ValueError:
            pass
    return "未开赛"


def fetch_ou_consensus(sid, timeout=25):
    """Fetch the full over/under page and summarize all companies' line moves."""
    try:
        html = t.fetch_text(t.OU_URL.format(sid=sid), timeout=timeout)
        d = t.parse_ou(html, sid)
    except Exception:
        return None
    valid = [
        r
        for r in d.get("rows", [])
        if r.get("open_line") is not None and r.get("cur_line") is not None
    ]
    if len(valid) < 3:
        return None
    from collections import Counter

    up = down = same = 0
    for r in valid:
        diff = r["cur_line"] - r["open_line"]
        if diff > 1e-9:
            up += 1
        elif diff < -1e-9:
            down += 1
        else:
            same += 1
    cur_lines = Counter(r["cur_line"] for r in valid)
    mode_line, mode_n = cur_lines.most_common(1)[0]
    n = len(valid)
    majority = max(up, down, same)
    agree = round(100.0 * majority / n)
    return (
        f"{fmt_line(mode_line)}为主档({mode_n}/{n}家) "
        f"升{up}/降{down}/平{same} 一致度{agree}%"
    )


def fetch_platform_ou(sid, timeout=25):
    """Classify every company into line x water combos (full page)."""
    try:
        html = t.fetch_text(t.OU_URL.format(sid=sid), timeout=timeout)
        d = t.parse_ou(html, sid)
    except Exception:
        return None
    counts = {
        "升盘+降水": 0, "升盘+升水": 0,
        "降盘+升水": 0, "降盘+降水": 0,
        "其它/不动": 0,
    }
    n = 0
    for r in d.get("rows", []):
        o_l, c_l = r.get("open_line"), r.get("cur_line")
        o_w, c_w = r.get("open_big"), r.get("cur_big")
        if o_l is None or c_l is None or o_w is None or c_w is None:
            continue
        n += 1
        ld = c_l - o_l
        wd = c_w - o_w
        if abs(ld) < 1e-9 or abs(wd) < 0.005:
            counts["其它/不动"] += 1
            continue
        line_k = "升盘" if ld > 0 else "降盘"
        water_k = "升水" if wd > 0 else "降水"
        key = line_k + "+" + water_k
        counts[key] = counts.get(key, 0) + 1
    if not n:
        return None
    top = max(counts, key=counts.get)
    return {
        "n": n,
        "counts": counts,
        "top": top,
        "top_pct": round(100.0 * counts[top] / n),
    }


def platform_text(pf):
    if not pf:
        return ""
    c = pf["counts"]
    return (
        f"全平台{pf['n']}家: 升盘降水{_wc(c,'升盘+降水')}/升盘升水{_wc(c,'升盘+升水')}"
        f"/降盘升水{_wc(c,'降盘+升水')}/降盘降水{_wc(c,'降盘+降水')} "
        f"主流={pf['top']}({pf['top_pct']}%)"
    )


def _wc(c, k):
    return c.get(k, 0)


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
    for tag, cidv in (("ah", cid), ("c2ah", cid2)):
        if not cidv:
            continue
        try:
            ad = t.fetch_company_ah_detail(match["sid"], cid=cidv, timeout=timeout)
        except Exception as e:
            row[f"{tag}_error"] = f"{type(e).__name__}: {e}"
            continue
        if ad and ad.get("cur_line") is not None:
            for k in (
                "open_water_h", "open_line", "open_water_a", "open_time",
                "cur_water_h", "cur_line", "cur_water_a", "cur_time",
            ):
                row[f"{tag}_{k}"] = ad[k]
            row[f"{tag}_diff"] = t.line_diff(ad["open_line"], ad["cur_line"])
        else:
            row[f"{tag}_error"] = "no-data"
    return row


def scan_matches(
    matches,
    cid=47,
    cid2=None,
    workers=8,
    timeout=18,
    limit=0,
    on_result=None,
    stop_check=None,
):
    todo = matches if not limit else matches[:limit]
    results = []
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers))
    futures = []
    try:
        for m in todo:
            if stop_check and stop_check():
                break
            futures.append(ex.submit(fetch_one, m, cid, cid2, timeout))
        for fut in concurrent.futures.as_completed(futures):
            if stop_check and stop_check():
                break
            try:
                r = fut.result()
            except Exception as e:
                r = {"sid": "?", "error": str(e)}
            results.append(r)
            if on_result:
                on_result(r)
    finally:
        for fut in futures:
            fut.cancel()
        ex.shutdown(wait=False)
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
