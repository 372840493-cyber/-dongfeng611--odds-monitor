# -*- coding: utf-8 -*-
"""titan007 (球探网) public data helpers: schedule ids + over/under page parsing."""

import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
from urllib.parse import quote

# Windows: 后台跑 netstat/tasklist/curl 时不要弹黑窗口
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

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
SPF_DATA_URL = "https://1x2d.titan007.com/{sid}.js?r=007"
AH_CHANGE_URL = (
    "https://vip.titan007.com/changeDetail/handicap.aspx"
    "?id={sid}&companyID={cid}&l=0"
)
LIVE_DATA_URL = "https://bf.titan007.com/vbsxml/bfdata.js?r=007"
HOME_URL = "https://www.titan007.com/"

# 官方即时比分状态码: -1 完场 / 0 未开赛 / 1 上半场 / 2 中场 / 3 下半场
LIVE_STATE_TEXT = {
    "-1": "完场",
    "0": "未开赛",
    "1": "上半场",
    "2": "中场",
    "3": "下半场",
    "4": "加时",
    "5": "点球",
}

_LIVE_CACHE = {"t": 0.0, "map": None}

AH_MAP = {
    "平手": 0.0, "平手/半球": 0.25, "半球": 0.5, "半球/一球": 0.75,
    "一球": 1.0, "一球/球半": 1.25, "球半": 1.5, "球半/两球": 1.75,
    "两球": 2.0, "两球/两球半": 2.25, "两球半": 2.5,
    "两球半/三球": 2.75, "三球": 3.0, "三球/三球半": 3.25,
    "三球半": 3.5, "三球半/四球": 3.75, "四球": 4.0,
    "受平手": 0.0, "受平手/半球": -0.25, "受半球": -0.5,
    "受半球/一球": -0.75, "受一球": -1.0, "受一球/球半": -1.25,
    "受球半": -1.5, "受球半/两球": -1.75, "受两球": -2.0,
    "受两球/两球半": -2.25, "受两球半": -2.5, "受两球半/三球": -2.75,
    "受三球": -3.0,
}

LINE_RE = re.compile(r"([\d.]+(?:/[\d.]+)?)")


def _decode(raw):
    for enc in ("gb18030", "gbk", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


_REQ_LOCK = threading.Lock()
_LAST_REQ = {"t": 0.0}
_MIN_GAP = 0.25

_PROXY_CFG = {
    "host": "127.0.0.1",
    "port": 7890,
    "enabled": True,
    "prefer": False,
    "user": "",
    "pass": "",
}


def set_proxy(host=None, port=None, enabled=True, prefer=False, user=None, password=None):
    if host:
        _PROXY_CFG["host"] = str(host).strip()
    try:
        if port:
            _PROXY_CFG["port"] = int(port)
    except (TypeError, ValueError):
        pass
    # 代理IP（带账号密码的那种）需要认证，留空表示不需要
    if user is not None:
        _PROXY_CFG["user"] = str(user).strip()
    if password is not None:
        _PROXY_CFG["pass"] = str(password)
    _PROXY_CFG["enabled"] = bool(enabled)
    _PROXY_CFG["prefer"] = bool(prefer)


def _proxy_http(host, port):
    """拼代理地址；有账号密码就带上（http://user:pass@host:port）。"""
    user = str(_PROXY_CFG.get("user") or "").strip()
    password = str(_PROXY_CFG.get("pass") or "")
    if user:
        return "http://%s:%s@%s:%d" % (
            quote(user, safe=""),
            quote(password, safe=""),
            host,
            int(port),
        )
    return "http://%s:%d" % (host, int(port))


def proxy_url():
    return _proxy_http(_PROXY_CFG["host"], _PROXY_CFG["port"])


def _is_remote_proxy():
    """是不是手动填的「代理IP」(不是本机加速器端口)。"""
    host = str(_PROXY_CFG.get("host") or "").strip().lower()
    return bool(host) and host not in ("127.0.0.1", "localhost")


def _throttle():
    with _REQ_LOCK:
        now = time.time()
        wait = _MIN_GAP - (now - _LAST_REQ["t"])
        if wait > 0:
            time.sleep(wait)
        _LAST_REQ["t"] = time.time()


def _proxy_alive():
    # 本机加速器端口 0.4 秒足够；远程「代理IP」要跨网络，给 3 秒，
    # 否则经常被误判成"不可用"而直接走直连（这些域名直连本来就是被挡的）。
    timeout = 3.0 if _is_remote_proxy() else 0.4
    try:
        s = socket.create_connection(
            (_PROXY_CFG["host"], int(_PROXY_CFG["port"])), timeout=timeout
        )
        s.close()
        return True
    except OSError:
        return False


_CURL = shutil.which("curl.exe") or shutil.which("curl")
try:
    from curl_cffi import requests as _cffi_requests
except Exception:
    _cffi_requests = None


def _cffi_fetch(url, timeout=25, proxy=None):
    kwargs = {
        "impersonate": "chrome",
        "timeout": int(timeout),
        "headers": {
            "Referer": "https://www.titan007.com/",
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    }
    if proxy:
        kwargs["proxies"] = {"http": proxy, "https": proxy}
    r = _cffi_requests.get(url, **kwargs)
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}")
    return _decode(r.content)


def _curl_fetch(url, timeout=25, proxy=None):
    args = [
        _CURL,
        "-sS",
        "--max-time",
        str(int(timeout)),
        "-A",
        UA["User-Agent"],
        "-H",
        "Accept-Language: zh-CN,zh;q=0.9",
        "-H",
        "Referer: https://www.titan007.com/",
        "-w",
        "\n__HTTP__%{http_code}",
    ]
    if proxy:
        args += ["-x", proxy]
    args.append(url)
    r = subprocess.run(
        args, capture_output=True, timeout=int(timeout) + 5,
        creationflags=_NO_WINDOW,
    )
    if r.returncode != 0:
        raise RuntimeError(f"curl exit {r.returncode}: {r.stderr[:120]!r}")
    out = r.stdout
    marker = b"\n__HTTP__"
    idx = out.rfind(marker)
    if idx < 0:
        raise RuntimeError("curl status parse failed")
    code = int((out[idx + len(marker):] or b"0").strip() or 0)
    body = out[:idx]
    if code >= 400:
        raise RuntimeError(f"HTTP {code}")
    return _decode(body)


_PROXY_FIRST_HOSTS = set()
_HOST_FAILS = {}
_DEAD_HOSTS = {}
_DEAD_COOLDOWN = 30.0


def _is_dead(host):
    ts = _DEAD_HOSTS.get(host)
    return bool(ts and time.time() < ts)


def _mark_host_fail(host):
    if not host:
        return
    n = _HOST_FAILS.get(host, 0) + 1
    _HOST_FAILS[host] = n
    # 网络/代理会抖(偶尔超时/被重置)，别两三次失败就把整个域名判死
    limit = 6 if _is_remote_proxy() else 5
    if n >= limit:
        _DEAD_HOSTS[host] = time.time() + _DEAD_COOLDOWN


def _clear_host_fail(host):
    if host:
        _HOST_FAILS.pop(host, None)
        _DEAD_HOSTS.pop(host, None)




def _run_quiet(args, timeout=10):
    try:
        return subprocess.run(
            args, capture_output=True, text=True, timeout=timeout,
            encoding="gb18030", errors="ignore", creationflags=_NO_WINDOW,
        )
    except Exception:
        return None
_ACCEL_KEYWORDS = (
    "ruisu", "gjjt", "clash", "verge", "v2ray", "xray", "sing", "netch",
    "tunnel", "proxy", "shadow", "ssr", "vpn",
)


def _netloc(url):
    try:
        from urllib.parse import urlparse

        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def _is_dns_error(e):
    msg = str(e).lower()
    return any(k in msg for k in ("getaddrinfo", "11004", "name or service", "nodename"))


def clear_dead_hosts():
    """清掉"通道不通"的短期标记(用户重新扫描/换代理后调用)。"""
    _DEAD_HOSTS.clear()
    _HOST_FAILS.clear()


def _is_conn_error(e):
    msg = str(e).lower()
    return any(
        k in msg
        for k in (
            "timed out", "timeout", "refused", "10060", "10061", "unreachable",
            "handshake", "eof", "connection", "reset", "ssl", "11004",
            "getaddrinfo", "failed to connect",
        )
    )


def _one_fetch(url, timeout=25, proxy=None):
    """一次抓取尝试: curl_cffi(Chrome指纹) -> curl.exe -> urllib。

    连不上(超时/被拒/握手失败)时直接放弃, 不再换工具重试同一条路,
    否则一次失败要等 3 倍超时, 整轮会拖到几十分钟。
    """
    errs = []
    if _cffi_requests is not None:
        try:
            return _cffi_fetch(url, timeout, proxy)
        except Exception as e:
            errs.append(e)
            if _is_conn_error(e):
                raise
    if _CURL:
        try:
            return _curl_fetch(url, timeout, proxy)
        except Exception as e:
            errs.append(e)
            if _is_conn_error(e):
                raise
    if proxy is None:
        try:
            return _urllib_fetch(url, timeout)
        except Exception as e:
            errs.append(e)
    raise errs[-1] if errs else RuntimeError("fetch failed")


def fetch_text(url, timeout=25):
    """抓取网页。直连失败的域名会自动改为优先走本机加速器代理。"""
    _throttle()
    host = _netloc(url)
    if _is_dead(host):
        raise RuntimeError(
            "通道暂时不通(%s): 直连被挡且加速器未连上" % host
        )
    proxy_ready = bool(_PROXY_CFG.get("enabled")) and _proxy_alive()
    if not proxy_ready:
        if host in _PROXY_FIRST_HOSTS:
            # 这个域名直连不通(本地被挡), 缩短超时, 别把整轮拖成几分钟
            timeout = min(timeout, 8)
        try:
            out = _one_fetch(url, timeout, None)
            _clear_host_fail(host)
            return out
        except Exception as e:
            if _is_conn_error(e):
                _PROXY_FIRST_HOSTS.add(host)
                _mark_host_fail(host)
            raise
    prefer = bool(_PROXY_CFG.get("prefer")) or host in _PROXY_FIRST_HOSTS
    if prefer and _is_remote_proxy():
        # 用的是代理IP：这些域名直连本来就被挡，失败就直接再试一次代理，
        # 省掉每次 20 秒的直连空等（代理IP偶尔会抖，重试一次基本能拿到）。
        order = [proxy_url(), proxy_url()]
    else:
        order = [proxy_url(), None] if prefer else [None, proxy_url()]
    last = None
    for index, proxy in enumerate(order):
        if index > 0 and _is_remote_proxy():
            time.sleep(0.6)
        try:
            out = _one_fetch(url, timeout, proxy)
            _clear_host_fail(host)
            return out
        except Exception as e:
            last = e
            if proxy is None and _is_conn_error(e):
                _PROXY_FIRST_HOSTS.add(host)
    if _is_conn_error(last):
        _mark_host_fail(host)
    raise last


def _accelerator_ports():
    """从本机加速器进程的监听端口里找可能的代理端口。"""
    ports = []
    try:
        out = (_run_quiet(["netstat", "-ano", "-p", "tcp"], 10) or None)
        out = out.stdout if out else ""
    except Exception:
        return ports
    names = {}
    try:
        tl = (_run_quiet(["tasklist", "/fo", "csv", "/nh"], 10) or None)
        tl = tl.stdout if tl else ""
        for line in tl.splitlines():
            parts = [x.strip().strip('"') for x in line.split('","')]
            if len(parts) >= 2:
                names[parts[1]] = parts[0].lower()
    except Exception:
        pass
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[3].upper() != "LISTENING":
            continue
        if not parts[1].startswith("127.0.0.1:"):
            continue
        try:
            port = int(parts[1].rsplit(":", 1)[1])
        except ValueError:
            continue
        pname = names.get(parts[4], "")
        if any(k in pname for k in _ACCEL_KEYWORDS):
            ports.append(port)
    return ports


def proxy_works(host="127.0.0.1", port=None, timeout=6):
    """试探某个端口能不能当代理访问球探(直连不通的那个域名)。"""
    try:
        port = int(port)
    except (TypeError, ValueError):
        return False
    if not port or not _CURL:
        return False
    args = [
        _CURL, "-s", "-o", os.devnull, "--max-time", str(timeout),
        "-w", "%{http_code}",
        "-x", _proxy_http(host, port),
        "-A", UA["User-Agent"],
        "https://vip.titan007.com/OverDown_n.aspx?id=1&l=0",
    ]
    try:
        r = _run_quiet(args, timeout + 6)
    except Exception:
        return False
    code = ((r.stdout if r else "") or "").strip()
    return code.isdigit() and int(code) > 0


def detect_proxy_port(host="127.0.0.1", timeout=6):
    """自动找当前加速器可用的代理端口(端口每次启动都可能变)。"""
    cands = []
    try:
        cfg_port = int(_PROXY_CFG.get("port") or 0)
    except (TypeError, ValueError):
        cfg_port = 0
    if cfg_port:
        cands.append(cfg_port)
    for p in _accelerator_ports():
        if p not in cands:
            cands.append(p)
    for p in (7890, 7891, 7897, 10809, 10808, 1080, 2080, 8889, 1087):
        if p not in cands:
            cands.append(p)
    for port in cands:
        if proxy_works(host, port, timeout):
            return port
    return None


def auto_proxy(save_path=None, host=None):
    """自动识别并启用可用代理; 找不到就直连。返回识别到的端口。"""
    host = host or _PROXY_CFG.get("host") or "127.0.0.1"
    clear_dead_hosts()
    # 手动填的「代理IP」(不是本机加速器)优先：能用就一直用它，别被自动探测覆盖掉。
    cfg_host = str(_PROXY_CFG.get("host") or "").strip()
    try:
        cfg_port = int(_PROXY_CFG.get("port") or 0)
    except (TypeError, ValueError):
        cfg_port = 0
    if (
        _PROXY_CFG.get("enabled")
        and cfg_host
        and cfg_host not in ("127.0.0.1", "localhost")
        and cfg_port
    ):
        # 手动填的代理IP(带账号密码)就直接信任它：不要每轮再探测一次，
        # 探测用的是 curl，票探对 TLS 指纹敏感会误判成"不可用"从而被清掉。
        set_proxy(cfg_host, cfg_port, True, True)
        return cfg_port
    port = detect_proxy_port(host)
    if port:
        set_proxy(host, port, True, False)
        if save_path:
            try:
                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "host": host,
                            "port": port,
                            "enabled": True,
                            "prefer": False,
                            "user": _PROXY_CFG.get("user", ""),
                            "pass": _PROXY_CFG.get("pass", ""),
                        },
                        f, ensure_ascii=False, indent=1,
                    )
            except Exception:
                pass
    else:
        try:
            keep = int(_PROXY_CFG.get("port") or 7890)
        except (TypeError, ValueError):
            keep = 7890
        set_proxy(host, keep, False, False)
    return port


def _urllib_fetch(url, timeout=25):
    req = urllib.request.Request(url, headers=UA)
    last_err = None
    proxies = {}  # 不用系统代理, 只用软件自己的代理设置
    custom = []
    if _PROXY_CFG["enabled"] and _proxy_alive():
        custom = [("custom", min(timeout, 10))]
    if proxies:
        attempts = [("default", timeout)] + custom + [("direct", timeout)]
    elif _PROXY_CFG["prefer"] and custom:
        attempts = custom + [("direct", min(timeout, 8))]
    else:
        attempts = [("direct", min(timeout, 8))] + custom
    for mode, tmo in attempts:
        try:
            _throttle()
            if mode == "default":
                resp = urllib.request.urlopen(req, timeout=timeout)
            elif mode == "direct":
                opener = urllib.request.build_opener(
                    urllib.request.ProxyHandler({})
                )
                resp = opener.open(req, timeout=tmo)
            else:
                opener = urllib.request.build_opener(
                    urllib.request.ProxyHandler(
                        {"http": proxy_url(), "https": proxy_url()}
                    )
                )
                resp = opener.open(req, timeout=tmo)
            with resp as r:
                return _decode(r.read())
        except Exception as e:
            last_err = e
            msg = str(e)
            if mode == "default" and not any(
                k in msg
                for k in ("refused", "timed out", "Timeout", "EOF", "10061")
            ):
                break
    raise last_err


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


AH_MAP.setdefault("平手", 0.0)
for _k, _v in list(AH_MAP.items()):
    if _k.startswith("受"):
        continue
    AH_MAP.setdefault("受" + _k, -_v)
    AH_MAP.setdefault("受让" + _k, -_v)


def parse_ah_line(txt):
    txt = (txt or "").replace(" ", "")
    if not txt:
        return None
    txt = txt.replace("受让", "受")
    if txt.startswith("让"):
        txt = txt[1:]
    if txt in AH_MAP:
        return AH_MAP[txt]
    m = re.match(r"^受(.+)$", txt)
    if m and m.group(1) in AH_MAP:
        v = AH_MAP[m.group(1)]
        return -v if v != 0 else 0.0
    return parse_line(txt)


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
                "minute": vals[0],
                "score": vals[1],
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
        "cur_minute": cur.get("minute", ""),
        "cur_score": cur.get("score", ""),
        "cur_time": cur["time"],
        "n_changes": len(rows),
    }


def fetch_company_ou_detail(sid, cid=1, timeout=20):
    return parse_company_detail(fetch_text(CHANGE_URL.format(sid=sid, cid=cid), timeout=timeout))


def fetch_spf_rows(sid, timeout=25):
    """Parse European odds (胜平负) rows from the per-match JS data file.
    Entry fields (pipe separated):
      0 cid | 2 English name | 3-5 open H/D/A | 10-12 current H/D/A | 21 short name
    """
    text = fetch_text(SPF_DATA_URL.format(sid=sid), timeout=timeout)
    a = text.find("var game=Array(")
    if a < 0:
        return []
    a += len("var game=Array(")
    b = text.find(");", a)
    body = text[a:b] if b > a else text[a:]
    rows = []
    for ent in re.findall(r'"((?:[^"\\]|\\.)*)"', body, re.S):
        p = ent.split("|")
        if len(p) < 22:
            continue

        def odds(i):
            try:
                return (float(p[i]), float(p[i + 1]), float(p[i + 2]))
            except (IndexError, TypeError, ValueError):
                return None

        rows.append(
            {
                "cid": p[0],
                "name": p[2],
                "short": p[21],
                "open": odds(3),
                "cur": odds(10),
            }
        )
    return rows


def parse_company_ah_detail(html):
    """Parse changeDetail/handicap page.
    Row: [分钟, 比分, 主水, 盘口, 客水, 变化时间, 状态], newest -> oldest.
    """
    rows = []
    for rm in re.finditer(r"<TR[^>]*>(.*?)</TR>", html, re.S | re.I):
        seg = rm.group(1)
        tds = re.findall(r"<TD[^>]*>(.*?)</TD>", seg, re.S | re.I)
        if len(tds) < 6:
            continue

        def clean(i):
            return re.sub(r"<[^>]+>", "", tds[i]).strip()

        wh = _f(clean(2))
        line = parse_ah_line(clean(3))
        wa = _f(clean(4))
        if line is None and wh is None:
            continue
        rows.append(
            {
                "water_h": wh,
                "line": line,
                "water_a": wa,
                "time": clean(5),
                "status": clean(6) if len(tds) > 6 else "",
            }
        )
    if not rows:
        return None
    opn, cur = rows[-1], rows[0]
    return {
        "open_water_h": opn["water_h"],
        "open_line": opn["line"],
        "open_water_a": opn["water_a"],
        "open_time": opn["time"],
        "cur_water_h": cur["water_h"],
        "cur_line": cur["line"],
        "cur_water_a": cur["water_a"],
        "cur_time": cur["time"],
        "n_changes": len(rows),
    }


def fetch_company_ah_detail(sid, cid=47, timeout=20):
    return parse_company_ah_detail(
        fetch_text(AH_CHANGE_URL.format(sid=sid, cid=cid), timeout=timeout)
    )


def parse_live_states(text):
    """Parse titan007 live feed (bfdata.js) into {sid: {...}}."""
    out = {}
    if not text:
        return out
    for m in re.finditer(r'A\[\d+\]="(.*?)"\.split', text, re.S):
        f = m.group(1).split("^")
        if len(f) < 18 or not f[0].isdigit():
            continue
        state = f[13].strip()
        hs, aws = f[14].strip(), f[15].strip()
        score = ""
        if hs.isdigit() and aws.isdigit() and state != "0":
            score = f"{hs}-{aws}"
        htd, atd = f[16].strip(), f[17].strip()
        half = ""
        if htd.isdigit() and atd.isdigit() and state != "0":
            half = f"{htd}-{atd}"
        out[f[0]] = {
            "state": state,
            "state_text": LIVE_STATE_TEXT.get(state, ""),
            "finished": state == "-1",
            "ko_time": f[11].strip(),
            "updated": f[12].strip(),
            "score": score,
            "half": half,
            "home_cn": f[5].strip(),
            "away_cn": f[8].strip(),
            "home_en": f[7].strip(),
            "away_en": f[10].strip(),
        }
    return out


def fetch_live_states(timeout=20, cache_secs=25):
    """All matches' live status/score from titan007 feed (cached briefly)."""
    now = time.time()
    if _LIVE_CACHE["map"] is not None and now - _LIVE_CACHE["t"] < cache_secs:
        return _LIVE_CACHE["map"]
    try:
        text = fetch_text(LIVE_DATA_URL, timeout=timeout)
    except Exception:
        return _LIVE_CACHE["map"] or {}
    states = parse_live_states(text)
    if states:
        _LIVE_CACHE["map"] = states
        _LIVE_CACHE["t"] = now
    return states or (_LIVE_CACHE["map"] or {})


def _f(txt):
    try:
        return float(txt)
    except (TypeError, ValueError):
        return None
