# -*- coding: utf-8 -*-
"""titan007 (球探网) public data helpers: schedule ids + over/under page parsing."""

import os
import re
import urllib.request

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://www.titan007.com/",
}

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")

SCHEDULE_URLS = [
    "https://m.titan007.com/txt/basid.js",
    "https://data.titan007.com/soccer_scheduleid.js?rp=20260905",
]

OU_URL = "https://vip.titan007.com/OverDown_n.aspx?id={sid}&l=0"
CHANGE_URL = (
    "https://vip.titan007.com/changeDetail/overunder.aspx"
    "?id={sid}&companyID={cid}&l=0"
)
HOME_URL = "https://www.titan007.com/"

LINE_RE = re.compile(r"([\d.]+(?:/[\d.]+)?)")


def _decode(raw):
    for enc in ("gb18030", "gbk", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def fetch_text(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return _decode(r.read())


def fetch_ids():
    """Return a list of today's football match ids from titan007 public js."""
    ids = []
    for url in SCHEDULE_URLS:
        try:
            text = fetch_text(url)
        except Exception:
            continue
        m = re.search(r'Ba_Soccer\s*=\s*"([0-9,]+)"', text)
        if not m:
            m = re.search(r'soccer_scheduleid\s*=\s*"([0-9,]+)"', text)
        if m:
            ids = [x for x in m.group(1).split(",") if x]
            if ids:
                break
    return ids


def split_title(title):
    """title -> (home, away, league)."""
    t = title.strip()
    t = t.split("-")[0].strip()  # drop site suffix
    m = re.match(r"^(.+?)\s*VS\s*(.+?)\s*[（(](.*?)[)）]\s*$", t, re.I | re.S)
    if m:
        return m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
    return "", "", t


def parse_ou(html, sid=None):
    """Parse OverDown_n.aspx page -> dict with header + company rows."""
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    title = m.group(1).strip() if m else ""
    home, away, league = split_title(title)
    rows = []
    # Each company block: a <tr> row containing checkbox/company/odds,
    # followed optionally by hidden companyID subrows. Parse only visible rows
    # that carry a company name cell plus 初/即时 odds cells.
    for rm in re.finditer(
        r"<tr[^>]*>(?:(?!</tr>).)*?<input[^>]*name=\"oddsShow\"[^>]*>.*?</tr>",
        html,
        re.S,
    ):
        seg = rm.group(0)
        tds = re.findall(r"<td[^>]*>(.*?)</td>", seg, re.S)
        if len(tds) < 9:
            continue
        name = re.sub(r"<[^>]+>", "", tds[1]).strip()
        if not name:
            continue
        cid_m = re.search(r"companyID=['\"]?(\d+)", tds[2])
        cid = int(cid_m.group(1)) if cid_m else None

        def cell(i):
            txt = re.sub(r"<[^>]+>", "", tds[i]).strip()
            try:
                return float(txt)
            except ValueError:
                return None

        def goals(i):
            gm = re.search(r"goals=\"([\d.]+)\"", tds[i])
            if gm:
                return float(gm.group(1))
            txt = re.sub(r"<[^>]+>", "", tds[i]).strip()
            return parse_line(txt)

        open_ = (cell(3), goals(4), cell(5))
        cur = (cell(6), goals(7), cell(8))
        rows.append(
            {
                "cid": cid,
                "name": name,
                "open_big": open_[0],
                "open_line": open_[1],
                "open_small": open_[2],
                "cur_big": cur[0],
                "cur_line": cur[1],
                "cur_small": cur[2],
            }
        )
    return {
        "sid": sid,
        "title": title,
        "home": home,
        "away": away,
        "league": league,
        "rows": rows,
    }


def parse_line(txt):
    """'2.5/3' -> 2.75 ; '3' -> 3.0 ; also handle Chinese AH text."""
    txt = (txt or "").replace(" ", "")
    if not txt:
        return None
    if txt.isdigit() or txt.replace(".", "", 1).isdigit():
        try:
            return float(txt)
        except ValueError:
            return None
    if "/" in txt:
        a, b = txt.split("/", 1)
        try:
            return (float(a) + float(b)) / 2.0
        except ValueError:
            return None
    return None


def line_diff(a, b):
    if a is None or b is None:
        return None
    return round(abs(a - b), 3)


def parse_home_matches(html):
    """Parse today's match rows from the desktop homepage html."""
    matches = []
    seen = set()
    block_pat = re.compile(
        r"(<div class=\"title matchinfo\"[^>]*>)(.*?)</div>\s*<ul",
        re.S,
    )
    for m in block_pat.finditer(html):
        tag = m.group(1)
        block = m.group(2)
        sid_m = re.search(r'data-scheduleid="\s*(\d+)\s*"', tag)
        if not sid_m:
            continue
        sid = sid_m.group(1)
        if sid in seen:
            continue
        state_m = re.search(r'data-state="\s*(\d+)\s*"', tag)
        state = state_m.group(1) if state_m else "0"
        if state not in ("0", ""):
            continue
        league_m = re.search(r'<span class="league"[^>]*>\s*([^<]+)</span>', block)
        time_m = re.search(r'<span class="L-time">\s*([^<]+)</span>', block)
        tit_m = re.search(
            r'<a href="[^"]*linkmatch/1/\d+\.html"[^>]*class="tit">(.*?)</a>',
            block,
            re.S,
        )
        if not tit_m:
            continue
        raw_anchor = tit_m.group(1)
        if not re.search(r">\s*VS\s*<|VS", raw_anchor, re.I):
            continue
        seen.add(sid)
        kickoff = ""
        dt_m = re.search(r'data-time="([^"]*)"', tag)
        if dt_m:
            parts = dt_m.group(1).split(",")
            if len(parts) >= 5:
                try:
                    y, mo, d, hh, mi = (int(parts[i]) for i in range(5))
                    mo += 1  # titan007 month field is 0-based
                    kickoff = f"{y:04d}-{mo:02d}-{d:02d} {hh:02d}:{mi:02d}"
                except (TypeError, ValueError):
                    kickoff = ""
        anchor = re.sub(r"<[^>]+>", "", raw_anchor)
        anchor = re.sub(r"\s+", " ", anchor).strip()
        home, away = "", ""
        parts = re.split(r"\s+VS\s+", anchor, maxsplit=1, flags=re.I)
        if len(parts) == 2:
            home, away = parts[0].strip(), parts[1].strip()
        matches.append(
            {
                "sid": sid,
                "league": league_m.group(1).strip() if league_m else "",
                "time": time_m.group(1).strip() if time_m else "",
                "kickoff": kickoff,
                "home": home,
                "away": away,
            }
        )
    return matches


def fetch_home_matches():
    """Fetch and parse today's match rows from the desktop homepage."""
    return parse_home_matches(fetch_text(HOME_URL, timeout=40))


def parse_company_detail(html):
    """Parse changeDetail/overunder page.
    Rows are newest -> oldest; we treat rows[-1] as opening and rows[0] as current.
    """
    rows = []
    for rm in re.finditer(r"<TR[^>]*>(.*?)</TR>", html, re.S | re.I):
        seg = rm.group(1)
        tds = re.findall(r"<TD[^>]*>(.*?)</TD>", seg, re.S | re.I)
        if len(tds) < 6:
            continue
        vals = []
        for td in tds[:6]:
            txt = re.sub(r"<[^>]+>", "", td).strip()
            vals.append(txt)
        big = _f(vals[2])
        line = parse_line(vals[3])
        small = _f(vals[4])
        if line is None and big is None:
            continue
        rows.append(
            {
                "big": big,
                "line": line,
                "small": small,
                "time": vals[5],
                "status": re.sub(r"<[^>]+>", "", tds[6]).strip()
                if len(tds) > 6
                else "",
            }
        )
    if not rows:
        return None
    cur = rows[0]
    opn = rows[-1]
    return {
        "open_big": opn["big"],
        "open_line": opn["line"],
        "open_small": opn["small"],
        "open_time": opn["time"],
        "cur_big": cur["big"],
        "cur_line": cur["line"],
        "cur_small": cur["small"],
        "cur_time": cur["time"],
        "n_changes": len(rows),
    }


def fetch_company_ou_detail(sid, cid=1, timeout=20):
    return parse_company_detail(fetch_text(CHANGE_URL.format(sid=sid, cid=cid), timeout=timeout))


def _f(txt):
    try:
        return float(txt)
    except (TypeError, ValueError):
        return None
