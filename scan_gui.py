# -*- coding: utf-8 -*-
"""东风‑61 洲际导弹 - 作者：程序猿虾米（本软件只提供数据参考，禁止非法赌博行为）"""

import csv
import concurrent.futures
import json
import os
import queue
import re
import smtplib
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from email.header import Header
from email.mime.text import MIMEText
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scanner_core as sc  # noqa: E402
import titan_common as t  # noqa: E402

try:
    import winsound
except ImportError:
    winsound = None


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def now():
    return datetime.now().strftime("%H:%M:%S")


class ScannerApp(tk.Tk):
    COLS = [
        ("league", "联赛", 64),
        ("time", "开赛", 46),
        ("live", "比分/状态", 130),
        ("home", "主队", 96),
        ("away", "客队", 96),
        ("open", "初盘", 92),
        ("cur", "即时盘", 92),
        ("diff", "盘差", 46),
        ("open_time", "初盘时间", 74),
        ("cur_time", "即时时间", 74),
        ("c2open", "皇冠初盘", 92),
        ("c2cur", "皇冠即时", 92),
        ("bet", "下注层", 260),
    ]

    COMPANY_NAMES = {
        1: "澳门", 3: "皇冠", 8: "bet365", 9: "威廉希尔", 12: "易胜博",
        14: "伟德", 17: "明陞", 22: "10BET", 24: "12bet", 31: "利记",
        35: "盈禾", 42: "18bet", 47: "平博", 50: "1xBet",
    }

    def __init__(self):
        super().__init__()
        self.title(
            "东风‑61 洲际导弹  -作者：程序猿虾"
            "（本软件只提供数据参考，禁止非法赌博行为，如有违法行为后果自负！）"
        )
        self.geometry("1250x920")
        self.running = False
        self.stop_ev = threading.Event()
        self.worker = None
        self.score_thread = None
        self._last_live = {}
        self._feed_seen = {}
        self._feed_live = set()
        self._live_done = set()
        self.live_meta = {}
        self.live_info = {}
        self._rechecked = set()
        self._score_verified = set()
        self._prematch_notified = set()
        self.ou_stats = []
        self.ou_recorded = set()
        self.events = queue.Queue()
        self.alerted = set()
        self.skip = set()
        self.last_rows = []
        self.all_rows = []
        self.live_sids = set()
        self.live_meta = {}
        self.tend_sounded = set()
        default_wav = os.path.join(app_dir(), "alert.wav")
        self.sound_wav = default_wav if os.path.exists(default_wav) else None
        self.sound_mode = "自定义WAV" if self.sound_wav else "双声高音(默认)"
        self.mail_cfg = {}
        self._load_mail_cfg()
        self.league_kw = []
        self._load_league_filter()
        self.all_leagues = self._load_all_leagues()
        self.proxy_cfg = self._load_proxy_cfg()
        t.set_proxy(
            self.proxy_cfg.get("host", "127.0.0.1"),
            self.proxy_cfg.get("port", 7890),
            self.proxy_cfg.get("enabled", True),
            self.proxy_cfg.get("prefer", True),
        )
        self.sort_key = "time"
        self.sort_desc = False
        self.notes = {}
        self._edit_active = False
        self._load_notes()
        self._build()
        self._load_history()
        self.ou_stats = self._load_ou_stats()
        self.ou_recorded = {str(x.get("sid")) for x in self.ou_stats}
        for _r in self.all_rows:
            self._record_ou_if_finished(_r)
        self.live_sids = {str(r.get("sid")) for r in self.all_rows}
        self.live_meta = {
            str(r.get("sid")): r.get("kickoff") for r in self.all_rows
        }
        self.live_info = {
            str(r.get("sid")): {
                "kickoff": r.get("kickoff"),
                "league": r.get("league", ""),
                "home": r.get("home", ""),
                "away": r.get("away", ""),
                "time": r.get("time", ""),
            }
            for r in self.all_rows
        }
        self.tend_sounded.update(
            str(r.get("sid"))
            for r in self.all_rows
            if r.get("bet_snapshot") and "倾向" in r["bet_snapshot"]
        )
        if self.all_rows:
            self._render(self.all_rows, set())
            self.status.config(text=f"已恢复 {len(self.all_rows)} 场跟踪记录")
        self.after(200, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.tree.bind("<Double-1>", self._on_double_click)

    def _build(self):
        tk.Label(
            self,
            text="东风‑61 洲际导弹",
            font=("Microsoft YaHei", 15, "bold"),
            fg="#c00000",
        ).pack(pady=(8, 0))
        tk.Label(
            self,
            text="本软件只提供数据参考，禁止非法赌博行为",
            font=("Microsoft YaHei", 10),
            fg="#8a4b08",
        ).pack(pady=(0, 4))
        cfg = ttk.Frame(self, padding=8)
        cfg.pack(fill="x")
        ttk.Label(cfg, text="盘差阈值:").pack(side="left")
        self.e_thr = ttk.Entry(cfg, width=6)
        self.e_thr.insert(0, "0.25")
        self.e_thr.pack(side="left", padx=(2, 10))
        ttk.Label(cfg, text="公司ID:").pack(side="left")
        self.e_cid = ttk.Entry(cfg, width=6)
        self.e_cid.insert(0, "47")
        self.e_cid.pack(side="left", padx=(2, 10))
        ttk.Label(cfg, text="轮询间隔(秒):").pack(side="left")
        self.e_int = ttk.Entry(cfg, width=7)
        self.e_int.insert(0, "60")
        self.e_int.pack(side="left", padx=(2, 10))
        ttk.Label(cfg, text="并发:").pack(side="left")
        self.e_workers = ttk.Entry(cfg, width=5)
        self.e_workers.insert(0, "2")
        self.e_workers.pack(side="left", padx=(2, 10))
        self.btn_start = ttk.Button(cfg, text="开始扫描", command=self.start)
        self.btn_start.pack(side="left", padx=6)
        self.btn_stop = ttk.Button(cfg, text="停止", command=self.stop, state="disabled")
        self.btn_stop.pack(side="left", padx=6)
        cfg2 = ttk.Frame(self, padding=(8, 0, 8, 4))
        cfg2.pack(fill="x")
        ttk.Button(cfg2, text="导出CSV", command=self.export_csv).pack(side="left", padx=6)
        ttk.Label(cfg2, text="提示音:").pack(side="left")
        self.sound_cb = ttk.Combobox(
            cfg2,
            values=("无", "系统提示", "双声高音(默认)", "自定义WAV"),
            width=13,
            state="readonly",
        )
        self.sound_cb.set(self.sound_mode)
        self.sound_cb.pack(side="left", padx=(2, 8))
        self.sound_cb.bind("<<ComboboxSelected>>", self._on_sound_select)
        ttk.Button(cfg2, text="清空已完赛", command=self._clear_finished).pack(
            side="left", padx=4
        )
        ttk.Button(cfg2, text="删除选中", command=self._delete_selected).pack(
            side="left", padx=4
        )
        ttk.Button(cfg2, text="全选删除", command=self._delete_all).pack(
            side="left", padx=4
        )
        self.auto_clear_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            cfg, text="完场自动清空", variable=self.auto_clear_var
        ).pack(side="left", padx=4)
        ttk.Button(cfg2, text="汇总发送", command=self._send_digest_now).pack(
            side="left", padx=4
        )
        ttk.Button(cfg2, text="邮箱通知", command=self._open_mail_settings).pack(
            side="left", padx=4
        )
        ttk.Button(cfg2, text="胜率统计", command=self._show_winrate).pack(
            side="left", padx=4
        )
        ttk.Button(cfg2, text="对比统计", command=self._show_ou_stats).pack(
            side="left", padx=4
        )
        ttk.Button(cfg2, text="联赛筛选", command=self._open_league_filter).pack(
            side="left", padx=4
        )
        self.all_leagues_var = tk.BooleanVar(value=self.all_leagues)
        ttk.Checkbutton(
            cfg2,
            text="全联赛(不过滤)",
            variable=self.all_leagues_var,
            command=self._toggle_all_leagues,
        ).pack(side="left", padx=4)
        self.status = ttk.Label(cfg, text="空闲", foreground="#1a6bb8")
        self.status.pack(side="right")

        body = ttk.Frame(self, padding=(8, 0, 8, 4))
        body.pack(fill="both", expand=True)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        cols = [c[1] for c in self.COLS]
        keys = [c[0] for c in self.COLS]
        self.tree = ttk.Treeview(body, columns=keys, show="headings", selectmode="browse")
        for (key, label, width), k in zip(self.COLS, keys):
            self.tree.heading(key, text=label, command=lambda k=key: self._sort_by(k))
            self.tree.column(key, width=width, anchor="w")
        self._apply_main_labels(47)
        vs = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        hs = ttk.Scrollbar(body, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        hs.grid(row=1, column=0, sticky="ew")
        self.tree.tag_configure("new", background="#fff3b0")
        self.tree.tag_configure("diff2", background="#ffe0dc")
        self.tree.tag_configure("buyrow", foreground="#d00000")

        logf = ttk.Frame(self, padding=(8, 0, 8, 8))
        logf.pack(fill="x")
        self.logtxt = tk.Text(logf, height=6, state="disabled", font=("Microsoft YaHei", 9))
        self.logtxt.pack(fill="x")

    def log(self, msg):
        self.events.put(("log", f"[{now()}] {msg}"))

    def start(self):
        try:
            thr = float(self.e_thr.get())
            cid = int(self.e_cid.get())
            interval = int(self.e_int.get())
            workers = int(self.e_workers.get())
        except ValueError:
            messagebox.showerror("参数错误", "阈值/公司ID/间隔/并发必须是数字")
            return
        self.thr, self.cid, self.interval, self.workers = thr, cid, interval, workers
        self._apply_main_labels(cid)
        self.running = True
        self.stop_ev.clear()
        self.alerted.clear()
        self.skip.clear()
        self.tend_sounded.update(
            str(r.get("sid"))
            for r in self.all_rows
            if r.get("bet_snapshot") and "倾向" in r["bet_snapshot"]
        )
        self._rechecked.clear()
        self._score_verified.clear()
        self._prematch_notified.clear()
        self._feed_seen.clear()
        self._feed_live.clear()
        self._live_done = {
            str(r.get("sid"))
            for r in self.all_rows
            if (r.get("live_state") or "").strip() == "-1"
        }
        for r in self.all_rows:
            sid = str(r.get("sid"))
            self.live_info[sid] = {
                "kickoff": r.get("kickoff"),
                "league": r.get("league", ""),
                "home": r.get("home", ""),
                "away": r.get("away", ""),
                "time": r.get("time", ""),
            }
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.sound_mode = self.sound_cb.get()
        if self.sound_mode == "自定义WAV" and not self.sound_wav:
            path = filedialog.askopenfilename(
                title="选择提示音文件",
                filetypes=[("WAV 音频", "*.wav"), ("所有文件", "*.*")],
            )
            if path:
                self.sound_wav = path
            else:
                self.sound_mode = "双声高音(默认)"
                self.sound_cb.set(self.sound_mode)
        self.status.config(text="运行中")
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()
        self.score_thread = threading.Thread(target=self._score_loop, daemon=True)
        self.score_thread.start()
        self.daily_thread = threading.Thread(target=self._daily_mail_loop, daemon=True)
        self.daily_thread.start()

    def stop(self):
        self.running = False
        self.stop_ev.set()
        self.status.config(text="停止中…")
        self.btn_stop.config(state="disabled")

    def _run(self):
        self.events.put(("log", f"启动: 阈值≥{self.thr} 公司ID={self.cid} 间隔{self.interval}s"))
        while self.running:
            t0 = time.time()
            try:
                matches = t.fetch_home_matches()
            except Exception as e:
                self.events.put(("log", f"比赛列表获取失败: {e}"))
                self._sleep(10)
                continue
            if not matches:
                self.events.put(("log", "比赛列表为空，稍后重试"))
                self._sleep(10)
                continue
            matches = [m for m in matches if m["sid"] not in self.skip]
            if self.league_kw and not self.all_leagues_var.get():
                before_filter = len(matches)
                matches = [
                    m for m in matches if self._league_ok(m.get("league", ""))
                ]
                if len(matches) != before_filter:
                    self.events.put(
                        (
                            "log",
                            f"联赛筛选: {before_filter} → {len(matches)} 场",
                        )
                    )
            self.events.put(("log", f"本轮 {len(matches)} 场，开始拉盘…"))
            total = len(matches)
            counters = {"ok": 0, "err": 0, "q": 0, "new": 0, "done": 0}
            results = []

            def on_result(r):
                if self.stop_ev.is_set():
                    return
                results.append(r)
                counters["done"] += 1
                if counters["done"] % 10 == 0:
                    self.events.put(
                        (
                            "log",
                            f"拉盘中 {counters['done']}/{total} "
                            f"(成功{counters['ok']}/失败{counters['err']})",
                        )
                    )
                if r.get("error"):
                    counters["err"] += 1
                    return
                counters["ok"] += 1
                d = r.get("diff")
                if d is not None and d + 1e-9 >= self.thr:
                    counters["q"] += 1
                    is_new = r["sid"] not in self.alerted
                    if is_new:
                        self.alerted.add(r["sid"])
                        counters["new"] += 1
                    self.live_sids.add(r["sid"])
                    self.live_meta[r["sid"]] = r.get("kickoff")
                    self.live_info[r["sid"]] = {
                        "kickoff": r.get("kickoff"),
                        "league": r.get("league", ""),
                        "home": r.get("home", ""),
                        "away": r.get("away", ""),
                        "time": r.get("time", ""),
                    }
                    self.events.put(("row", r, is_new))
                    try:
                        pf = sc.fetch_platform_ou(r["sid"])
                        if pf:
                            r["platform"] = pf
                            self.events.put(("row", r, False))
                            self.events.put(
                                (
                                    "log",
                                    f"全平台 {r['league']} {r['home']}vs{r['away']}: "
                                    f"{sc.platform_text(pf)}",
                                )
                            )
                    except Exception:
                        pass

            sc.scan_matches(
                matches,
                cid=self.cid,
                cid2=3,
                workers=self.workers,
                timeout=18,
                on_result=on_result,
                stop_check=self.stop_ev.is_set,
            )
            if not self.running:
                self.events.put(("stopped", None))
                return
            for r in results:
                if r.get("error") == "no-data":
                    self.skip.add(r["sid"])
            self.events.put(
                (
                    "passlog",
                    counters["ok"],
                    counters["err"],
                    counters["q"],
                    counters["new"],
                    time.time() - t0,
                )
            )
            cost = time.time() - t0
            self._sleep(max(5, self.interval - cost))
        self.events.put(("stopped", None))

    def _score_loop(self):
        from datetime import datetime, timedelta

        while self.running and not self.stop_ev.is_set():
            now = datetime.now()
            sids = []
            for sid in list(self.live_sids):
                ko = self.live_meta.get(sid)
                if ko:
                    try:
                        ko_dt = datetime.strptime(ko, "%Y-%m-%d %H:%M")
                        if now < ko_dt - timedelta(minutes=5):
                            continue
                    except (TypeError, ValueError):
                        pass
                if sid in self._live_done:
                    continue
                sids.append(sid)
            # 官方即时比分: 完场判定 + 实时比分(一次请求覆盖全部场次)
            if self.running and not self.stop_ev.is_set():
                self._feed_live = set()
                try:
                    states = t.fetch_live_states()
                except Exception:
                    states = {}
                for sid in list(self.live_sids):
                    st = states.get(sid)
                    if not st:
                        continue
                    self._feed_live.add(sid)
                    score = (st.get("score") or "").strip()
                    if st.get("finished"):
                        if score and self._feed_seen.get(sid) != ("完场", score):
                            self._feed_seen[sid] = ("完场", score)
                            self._live_done.add(sid)
                            self.events.put(("finish", sid, score))
                        continue
                    if not score:
                        continue
                    minute = self._est_minute(sid, st, now)
                    if self._feed_seen.get(sid) != (minute, score):
                        self._feed_seen[sid] = (minute, score)
                        self.events.put(("live", sid, score, minute))
            if sids and self.running:
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
                    fut_map = {
                        ex.submit(
                            t.fetch_company_ou_detail, sid, self.cid, 15
                        ): sid
                        for sid in sids
                    }
                    for fut in concurrent.futures.as_completed(fut_map):
                        sid = fut_map[fut]
                        try:
                            d = fut.result()
                        except Exception:
                            continue
                        if not d:
                            continue
                        if sid in self._feed_live:
                            # 分钟/比分由官方即时比分提供(盘口页常常停在最后一次变盘)
                            continue
                        score = (d.get("cur_score") or "").strip()
                        minute = (d.get("cur_minute") or "").strip()
                        key = (score, minute)
                        if self._last_live.get(sid) != key:
                            self._last_live[sid] = key
                            self.events.put(("live", sid, score, minute))
            # 完场后用 500.com 校准最终比分(每场一次)
            now3 = datetime.now()
            for sid, info in list(self.live_info.items()):
                if sid in self._score_verified:
                    continue
                ko = info.get("kickoff")
                if not ko:
                    continue
                try:
                    ko_dt = datetime.strptime(ko, "%Y-%m-%d %H:%M")
                except (TypeError, ValueError):
                    continue
                if now3 < ko_dt + timedelta(minutes=135):
                    continue
                try:
                    res = sc.match_final_score(info)
                except Exception:
                    res = None
                if res:
                    self._score_verified.add(sid)
                    score = f"{res['hg']}-{res['ag']}"
                    if self._last_live.get(sid) != (score, ""):
                        self._last_live[sid] = (score, "")
                        self.events.put(("live", sid, score, ""))
            # 已锁定的场次: 开赛前15分钟发临场提醒(原始倾向+当前盘口)
            for sid, info in list(self.live_info.items()):
                snap = info.get("snapshot")
                if not snap or sid in self._prematch_notified:
                    continue
                ko = info.get("kickoff")
                if not ko:
                    continue
                try:
                    ko_dt = datetime.strptime(ko, "%Y-%m-%d %H:%M")
                except (TypeError, ValueError):
                    continue
                if not (ko_dt - timedelta(minutes=15) <= now2 < ko_dt):
                    continue
                self._prematch_notified.add(sid)
                try:
                    m = {
                        "sid": sid,
                        "league": info.get("league", ""),
                        "home": info.get("home", ""),
                        "away": info.get("away", ""),
                        "time": info.get("time", ""),
                        "kickoff": ko,
                    }
                    r = sc.fetch_one(m, cid=self.cid, cid2=3, timeout=12)
                except Exception:
                    r = None
                if r and not r.get("error"):
                    self.live_info.setdefault(sid, {})["t15_pin"] = r.get("cur_line")
                    self.live_info.setdefault(sid, {})["t15_crown"] = r.get(
                        "c2_cur_line"
                    )
                    self.live_info.setdefault(sid, {})["t15_sig"] = sc.ou_signal(r)
                    cur_tend = sc.betting_reference(r)

                    def _norm(x):
                        return re.sub(r"[✔✘\s]|走盘", "", str(x))

                    if _norm(cur_tend) == _norm(snap):
                        check_txt = "与之前最终倾向一致"
                        extra = ""
                    else:
                        check_txt = "已变化(注意)"
                        _cl, _c2 = r.get("cur_line"), r.get("c2_cur_line")
                        if _cl is not None and _c2 is not None:
                            _d = round(_c2 - _cl, 3)
                            if abs(_d) < 1e-9:
                                _cmp = "与平博同盘"
                            elif _d > 0:
                                _cmp = f"皇冠高{sc.fmt_line(_d)}"
                            else:
                                _cmp = f"皇冠低{sc.fmt_line(abs(_d))}"
                        else:
                            _cmp = "皇冠无数据"
                        _al, _a2 = r.get("ah_cur_line"), r.get("c2ah_cur_line")
                        if _al is not None and _a2 is not None:
                            _ad = round(_a2 - _al, 3)
                            if abs(_ad) < 1e-9:
                                _acmp = "与平博同盘"
                            elif _ad > 0:
                                _acmp = f"皇冠高{sc.fmt_line(_ad)}"
                            else:
                                _acmp = f"皇冠低{sc.fmt_line(abs(_ad))}"
                        else:
                            _acmp = "皇冠无数据"
                        def _w(a, b):
                            return f"{a}/{b}" if a is not None and b is not None else "-"

                        _ah_txt = "无数据"
                        if _al is not None:
                            _ah_txt = (
                                f"平博 {sc.fmt_ah_line(_al)} 水{_w(r.get('ah_cur_water_h'), r.get('ah_cur_water_a'))}"
                            )
                            if _a2 is not None:
                                _ah_txt += (
                                    f" | 皇冠 {sc.fmt_ah_line(_a2)} "
                                    f"水{_w(r.get('c2ah_cur_water_h'), r.get('c2ah_cur_water_a'))}（{_acmp}）"
                                )
                        extra = (
                            f"\n当前倾向: {cur_tend}\n"
                            f"当前亚盘: {_ah_txt}\n"
                            f"当前大小球(仅参考): 平博 {sc.fmt_odds(_cl, r.get('cur_big'), r.get('cur_small'))}"
                            f" | 皇冠 {sc.fmt_odds(_c2, r.get('c2_cur_big'), r.get('c2_cur_small'))}"
                            f"（{_cmp}）"
                        )
                        _reason = []
                        if _al is None or _a2 is None:
                            _reason.append("亚盘数据不全")
                        elif _al * _a2 <= 0:
                            _reason.append("两家亚盘方向不一致")
                        else:
                            _wh = r.get("ah_cur_water_h")
                            _wa = r.get("ah_cur_water_a")
                            if _wh and _wa:
                                _ih, _ia = 1.0 / _wh, 1.0 / _wa
                                _ph = _ih / (_ih + _ia)
                                _prob = _ph if _al >= 0 else 1.0 - _ph
                                if _prob < 0.55:
                                    _reason.append(f"亚盘强度{_prob*100:.0f}%<55%")
                                else:
                                    _reason.append(f"亚盘强度{_prob*100:.0f}%")
                            else:
                                _reason.append("亚盘水位缺失")
                        _osig = sc.ou_signal(r) or "无"
                        _oscore = sc.size_score(r)["total"]
                        _reason.append(f"大小球信号:{_osig}")
                        _reason.append(f"大小球评分{_oscore}/35")
                        _pf = r.get("platform") or {}
                        if _pf:
                            _reason.append(
                                f"全平台主流{_pf.get('top')}({_pf.get('top_pct')}%)"
                            )
                        extra += "\n变化原因: " + " ｜ ".join(_reason)
                    body = (
                        f"开赛时间: {ko}\n"
                        f"联赛: {info.get('league', '')}\n"
                        f"主队: {info.get('home', '')}\n"
                        f"客队: {info.get('away', '')}\n"
                        f"原始倾向: {snap}\n"
                        f"开赛前15分钟复查: {check_txt}{extra}\n"
                    )
                    subject = (
                        f"临场提醒(15分钟): {info.get('league', '')} "
                        f"{info.get('home', '')} vs {info.get('away', '')}"
                    )
                    cfg = self.mail_cfg
                    if cfg.get("enabled") and all(
                        cfg.get(k) for k in ("sender", "auth", "to")
                    ):
                        threading.Thread(
                            target=self._mail_worker,
                            args=(cfg, subject, body),
                            daemon=True,
                        ).start()
                    self.events.put(("log", f"临场提醒已发送: {subject}"))
                else:
                    self.events.put(("log", f"临场提醒取数失败: {sid}"))
            # 开赛前 15 分钟最后复查一次倾向
            now2 = datetime.now()
            for sid, info in list(self.live_info.items()):
                if sid in self._rechecked:
                    continue
                ko = info.get("kickoff")
                if not ko:
                    continue
                try:
                    ko_dt = datetime.strptime(ko, "%Y-%m-%d %H:%M")
                except (TypeError, ValueError):
                    continue
                if now2 < ko_dt - timedelta(minutes=15) or now2 >= ko_dt:
                    continue
                self._rechecked.add(sid)
                try:
                    m = {
                        "sid": sid,
                        "league": info.get("league", ""),
                        "home": info.get("home", ""),
                        "away": info.get("away", ""),
                        "time": info.get("time", ""),
                        "kickoff": ko,
                    }
                    r = sc.fetch_one(m, cid=self.cid, cid2=3, timeout=12)
                    if r and not r.get("error"):
                        pf = sc.fetch_platform_ou(sid)
                        if pf:
                            r["platform"] = pf
                        self.events.put(("row", r, False))
                except Exception:
                    pass
            end = time.time() + 30
            while self.running and not self.stop_ev.is_set() and time.time() < end:
                time.sleep(0.5)

    def _sleep(self, secs):
        end = time.time() + secs
        while self.running and time.time() < end:
            time.sleep(0.5)

    def _est_minute(self, sid, st, now):
        """用官方即时比分状态 + 开赛时间推算当前比赛分钟。"""
        from datetime import datetime

        phase = (st.get("state") or "").strip()
        if phase == "2":
            return "中场"
        if phase not in ("1", "3", "4", "5"):
            return ""
        ko = self.live_meta.get(sid) or st.get("ko_time") or ""
        try:
            if len(ko) > 5:
                ko_dt = datetime.strptime(ko, "%Y-%m-%d %H:%M")
            else:
                ko_dt = datetime.strptime(
                    now.strftime("%Y-%m-%d ") + ko.strip(), "%Y-%m-%d %H:%M"
                )
        except (TypeError, ValueError):
            return ""
        mins = int((now - ko_dt).total_seconds() // 60)
        if phase == "1":
            return str(max(1, min(45, mins)))
        play = mins - 15
        if play < 46:
            play = 46
        if play > 90:
            return "90+"
        return str(play)

    def _on_sound_select(self, event=None):
        val = self.sound_cb.get()
        if val == "自定义WAV":
            path = filedialog.askopenfilename(
                title="选择提示音文件",
                filetypes=[("WAV 音频", "*.wav"), ("所有文件", "*.*")],
            )
            if path:
                self.sound_wav = path
                self.sound_mode = val
            else:
                self.sound_cb.set(self.sound_mode)
        else:
            self.sound_mode = val

    def _play_tend_sound(self):
        if self.sound_mode == "无" or winsound is None:
            return
        try:
            if self.sound_mode == "自定义WAV" and self.sound_wav:
                winsound.PlaySound(
                    self.sound_wav,
                    winsound.SND_FILENAME | winsound.SND_ASYNC,
                )
            elif self.sound_mode == "系统提示":
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            else:
                winsound.Beep(1200, 260)
                time.sleep(0.18)
                winsound.Beep(1200, 260)
        except Exception:
            pass

    def _delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            self._append_log("请先在表格里选中要删除的场次")
            return
        sid = str(sel[0])
        row = next(
            (r for r in self.all_rows if str(r.get("sid")) == sid), None
        )
        self.all_rows = [
            r for r in self.all_rows if str(r.get("sid")) != sid
        ]
        self.live_sids.discard(sid)
        self.live_meta.pop(sid, None)
        self.live_info.pop(sid, None)
        self.tend_sounded.discard(sid)
        self._rechecked.discard(sid)
        self._score_verified.discard(sid)
        self._render(self.all_rows, set())
        self._save_history()
        name = (
            f"{row.get('home', '')} vs {row.get('away', '')}"
            if row
            else sid
        )
        self._append_log(f"已删除场次: {name}")

    def _backup_history(self):
        src = self._history_path()
        if not os.path.exists(src):
            return None
        import shutil as _shutil

        bdir = os.path.join(app_dir(), "backups")
        os.makedirs(bdir, exist_ok=True)
        dst = os.path.join(
            bdir, f"track_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        try:
            _shutil.copy2(src, dst)
            self._append_log(f"已备份历史: {dst}")
            return dst
        except Exception as e:
            self._append_log(f"历史备份失败: {e}")
            return None

    def _delete_all(self):
        if not self.all_rows:
            self._append_log("当前没有可删除的记录")
            return
        if not messagebox.askyesno(
            "全选删除",
            f"确定要删除全部 {len(self.all_rows)} 条记录吗？"
            "（删除前会自动备份历史文件）",
        ):
            return
        self._backup_history()
        self.all_rows = []
        self.live_sids.clear()
        self.live_meta.clear()
        self.live_info.clear()
        self.tend_sounded.clear()
        self._rechecked.clear()
        self._score_verified.clear()
        self._prematch_notified.clear()
        self._render([], set())
        self._save_history()
        self._append_log("已全选删除: 全部记录已清空")

    def _clear_finished(self):
        self._backup_history()
        before = len(self.all_rows)
        self.all_rows = [
            r
            for r in self.all_rows
            if not sc.score_status(r).startswith("完场")
        ]
        removed = before - len(self.all_rows)
        self._render(self.all_rows, set())
        self._save_history()
        self._append_log(
            f"已清空 {removed} 场完赛记录，保留 {len(self.all_rows)} 场"
        )

    def _maybe_auto_clear(self):
        if self.auto_clear_var.get():
            before = len(self.all_rows)
            self.all_rows = [
                r
                for r in self.all_rows
                if not sc.score_status(r).startswith("完场")
            ]
            if len(self.all_rows) != before:
                self._render(self.all_rows, set())
                self._save_history()

    def _ou_stats_path(self):
        return os.path.join(app_dir(), "ou_compare_stats.json")

    def _load_ou_stats(self):
        p = self._ou_stats_path()
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    return [x for x in data if isinstance(x, dict)]
            except Exception:
                return []
        return []

    def _save_ou_stats(self):
        try:
            with open(self._ou_stats_path(), "w", encoding="utf-8") as f:
                json.dump(self.ou_stats, f, ensure_ascii=False, indent=1)
        except Exception as e:
            self._append_log(f"对比统计保存失败: {e}")

    def _record_ou_if_finished(self, row):
        if not row:
            return
        if not sc.score_status(row).startswith("完场"):
            return
        score = (row.get("cur_score") or "").strip()
        if "-" not in score:
            return
        sid = str(row.get("sid"))
        if sid in self.ou_recorded:
            return
        try:
            parts = score.split("-")
            total = int(parts[0].strip()) + int(parts[1].strip())
        except (ValueError, IndexError):
            return
        def _base(pin, crown):
            if pin is None or crown is None:
                return None
            diff = round(crown - pin, 3)
            if diff < -1e-9:
                cat = "皇冠低盘"
            elif diff > 1e-9:
                cat = "皇冠高盘"
            else:
                cat = "两家同盘"
            if total > pin + 1e-9:
                res = "大"
            elif total < pin - 1e-9:
                res = "小"
            else:
                res = "走盘"
            return {
                "pin": pin,
                "crown": crown,
                "diff": diff,
                "cat": cat,
                "result": res,
            }

        info = self.live_info.get(sid, {})
        b_t15 = _base(info.get("t15_pin"), info.get("t15_crown"))
        b_lock = _base(
            row.get("lock_pin_line") or row.get("lock2_pin_line"),
            row.get("lock_crown_line") or row.get("lock2_crown_line"),
        )
        b_last = _base(row.get("cur_line"), row.get("c2_cur_line"))
        if not (b_t15 or b_lock or b_last):
            return
        main = b_t15 or b_lock or b_last
        self.ou_stats.append(
            {
                "sid": sid,
                "date": row.get("kickoff", ""),
                "league": row.get("league", ""),
                "home": row.get("home", ""),
                "away": row.get("away", ""),
                "pin_line": main["pin"],
                "crown_line": main["crown"],
                "diff": main["diff"],
                "cat": main["cat"],
                "total": total,
                "big25": "大" if total >= 3 else "小",
                "result_vs_pin": main["result"],
                "t15": b_t15,
                "lock": b_lock,
                "last": b_last,
                "sig_t15": info.get("t15_sig"),
                "sig_lock": row.get("lock_sig") or row.get("lock2_sig"),
            }
        )
        self.ou_recorded.add(sid)
        self._save_ou_stats()

    def _show_ou_stats(self):
        def summarize(getter):
            groups = {}
            for rec in self.ou_stats:
                base = getter(rec)
                if not base:
                    continue
                g = groups.setdefault(
                    base.get("cat", "?"),
                    {"n": 0, "大": 0, "小": 0, "走": 0, "big大": 0, "big小": 0},
                )
                g["n"] += 1
                rp = base.get("result")
                if rp == "大":
                    g["大"] += 1
                elif rp == "小":
                    g["小"] += 1
                else:
                    g["走"] += 1
                if rec.get("big25") == "大":
                    g["big大"] += 1
                else:
                    g["big小"] += 1
            return groups

        lines = [f"累计样本: {len(self.ou_stats)} 场", ""]
        for title, getter in (
            ("【开赛前15分钟盘口】", lambda rec: rec.get("t15")),
            ("【第一次红标盘口】", lambda rec: rec.get("lock")),
        ):
            groups = summarize(getter)
            lines.append(title)
            any_row = False
            for cat in ("皇冠低盘", "两家同盘", "皇冠高盘"):
                g = groups.get(cat)
                if not g:
                    continue
                any_row = True
                pct = 100.0 * g["big大"] / g["n"] if g["n"] else 0
                lines.append(
                    f"  {cat}: {g['n']} 场 | 总进球≥3 {g['big大']} / ≤2 {g['big小']} | "
                    f"大球占比 {pct:.0f}% | 对主盘 大{g['大']}/小{g['小']}/走{g['走']}"
                )
            if not any_row:
                lines.append("  暂无样本")
            lines.append("")
        for label_txt, kw in (
            ("升盘+大升水(升盘阻大)", "升盘阻大"),
            ("降盘+大降水(可能诱大)", "诱大"),
        ):
            n = big = small = w = l = p = 0
            for rec in self.ou_stats:
                sig = (rec.get("sig_t15") or rec.get("sig_lock") or "")
                if kw not in sig:
                    continue
                n += 1
                if rec.get("big25") == "大":
                    big += 1
                else:
                    small += 1
                rp = (rec.get("t15") or rec.get("lock") or {}).get("result")
                if rp == "大":
                    w += 1
                elif rp == "小":
                    l += 1
                else:
                    p += 1
            pct = (100.0 * big / n) if n else 0
            lines.append(
                f"【专项】{label_txt}: {n} 场 | 总进球≥3 {big} / ≤2 {small} | "
                f"大球占比 {pct:.0f}% | 对主盘 大{w}/小{l}/走{p}"
            )
        lines.append("")
        lines.append("最近 20 场明细:")
        for rec in self.ou_stats[-20:]:
            base = rec.get("t15") or rec.get("lock") or rec.get("last") or {}
            lines.append(
                f"{rec.get('date', '')[:16]} {rec.get('league', '')} "
                f"{rec.get('home', '')} vs {rec.get('away', '')} | "
                f"平博 {base.get('pin')} 皇冠 {base.get('crown')} ({base.get('cat')}) | "
                f"总进球 {rec.get('total')} → {rec.get('big25')}"
            )
        text = "\n".join(lines)
        win = tk.Toplevel(self)
        win.title("盘口对比统计")
        win.transient(self)
        tk.Label(
            win, text=text, justify="left", font=("Microsoft YaHei", 10), padx=16, pady=12
        ).pack()
        ttk.Button(win, text="关闭", command=win.destroy).pack(pady=(0, 10))
        win.geometry(f"+{self.winfo_rootx() + 100}+{self.winfo_rooty() + 120}")
        self._append_log(f"对比统计: 样本 {len(self.ou_stats)} 场")

    def _mail_cfg_path(self):
        return os.path.join(app_dir(), "email_config.json")

    def _load_mail_cfg(self):
        p = self._mail_cfg_path()
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self.mail_cfg = data
            except Exception:
                self.mail_cfg = {}

    def _save_mail_cfg(self):
        try:
            with open(self._mail_cfg_path(), "w", encoding="utf-8") as f:
                json.dump(self.mail_cfg, f, ensure_ascii=False, indent=1)
        except Exception as e:
            self._append_log(f"邮箱配置保存失败: {e}")

    def _open_mail_settings(self):
        win = tk.Toplevel(self)
        win.title("QQ邮箱通知设置")
        win.transient(self)
        win.grab_set()
        win.resizable(False, False)
        pad = {"padx": 10, "pady": 4}

        def row(label):
            frm = ttk.Frame(win)
            frm.pack(fill="x", **pad)
            ttk.Label(frm, text=label, width=14).pack(side="left")
            e = ttk.Entry(frm, width=46)
            e.pack(side="left", fill="x", expand=True)
            return e

        e_sender = row("发件QQ邮箱:")
        e_auth = row("SMTP授权码:")
        e_to = row("收件邮箱(多地址用,分隔):")
        e_sender.insert(0, self.mail_cfg.get("sender", ""))
        e_auth.insert(0, self.mail_cfg.get("auth", ""))
        old_to = self.mail_cfg.get("to", "")
        if isinstance(old_to, list):
            old_to = ",".join(old_to)
        e_to.insert(0, old_to)
        enabled = tk.BooleanVar(value=bool(self.mail_cfg.get("enabled")))
        ttk.Checkbutton(win, text="启用邮箱通知", variable=enabled).pack(
            anchor="w", **pad
        )
        ttk.Label(
            win,
            text="授权码获取: mail.qq.com → 设置 → 账户 → 开启SMTP服务 → 生成授权码",
            foreground="#556",
        ).pack(anchor="w", **pad)

        def save():
            raw_to = e_to.get()
            to_list = [
                x.strip()
                for x in re.split(r"[，,;\s]+", raw_to)
                if "@" in x
            ]
            self.mail_cfg = {
                "smtp": "smtp.qq.com",
                "port": 465,
                "sender": e_sender.get().strip(),
                "auth": e_auth.get().strip(),
                "to": to_list,
                "enabled": enabled.get(),
            }
            self._save_mail_cfg()
            self._append_log("邮箱通知设置已保存")
            win.destroy()

        btns = ttk.Frame(win)
        btns.pack(pady=8)
        ttk.Button(btns, text="保存", command=save).pack(side="left", padx=8)
        ttk.Button(btns, text="取消", command=win.destroy).pack(side="left", padx=8)
        win.geometry(f"+{self.winfo_rootx() + 100}+{self.winfo_rooty() + 150}")
        self.wait_window(win)

    def _send_tend_mail(self, r):
        cfg = self.mail_cfg
        if not cfg.get("enabled") or not all(
            cfg.get(k) for k in ("sender", "auth", "to")
        ):
            return
        cell = r.get("bet_snapshot") or sc.betting_reference(r)
        body = (
            f"联赛: {r.get('league', '')}\n"
            f"开赛: {r.get('kickoff') or r.get('time', '')}\n"
            f"主队: {r.get('home', '')}\n"
            f"客队: {r.get('away', '')}\n"
            f"下注层: {cell}\n"
        )
        subject = f"东风-61洲际导弹 倾向提醒: {r.get('league', '')} {r.get('home', '')} vs {r.get('away', '')}"
        threading.Thread(
            target=self._mail_worker,
            args=(cfg, subject, body),
            daemon=True,
        ).start()

    def _mail_worker(self, cfg, subject, body, attachment=None):
        try:
            if attachment:
                from email.mime.base import MIMEBase
                from email.mime.multipart import MIMEMultipart
                from email import encoders

                msg = MIMEMultipart()
                msg.attach(MIMEText(body, "plain", "utf-8"))
                fname, data = attachment
                part = MIMEBase("text", "csv")
                part.set_payload(data)
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition", "attachment", filename=("utf-8", "", fname)
                )
                msg.attach(part)
            else:
                msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = Header(subject, "utf-8")
            msg["From"] = cfg["sender"]
            tos = cfg["to"] if isinstance(cfg["to"], list) else [cfg["to"]]
            msg["To"] = ", ".join(tos)
            with smtplib.SMTP_SSL(cfg["smtp"], int(cfg.get("port", 465)), timeout=25) as s:
                s.login(cfg["sender"], cfg["auth"])
                s.sendmail(cfg["sender"], tos, msg.as_string())
            self.events.put(("log", f"邮件已发送: {subject}"))
        except Exception as e:
            self.events.put(("log", f"邮件发送失败: {type(e).__name__}: {e}"))

    def _daily_state_path(self):
        return os.path.join(app_dir(), "daily_mail_state.json")

    def _daily_mail_loop(self):
        while True:
            try:
                now = datetime.now()
                if now.hour == 21 and now.minute < 5:
                    today = now.strftime("%Y-%m-%d")
                    try:
                        state = json.load(open(self._daily_state_path(), encoding="utf-8"))
                    except Exception:
                        state = {}
                    if state.get("last") != today:
                        state["last"] = today
                        try:
                            with open(self._daily_state_path(), "w", encoding="utf-8") as f:
                                json.dump(state, f, ensure_ascii=False)
                        except Exception:
                            pass
                        self.events.put(("daily_mail", today))
            except Exception:
                pass
            time.sleep(20)

    def _send_digest_now(self):
        day = datetime.now().strftime("%Y-%m-%d")
        self._send_daily_digest(day, tag="手动")

    def _send_daily_digest(self, day, tag="21:00"):
        rows = [r for r in self.all_rows if "倾向" in sc.bet_cell(r)]
        rows.sort(
            key=lambda r: (
                r.get("kickoff") or "9999-99-99 99:99",
                r.get("time") or "",
            )
        )
        if not rows:
            self._append_log(f"{day} {tag} 无建议下注，未发送邮件")
            return
        cfg = self.mail_cfg
        if not cfg.get("enabled") or not all(
            cfg.get(k) for k in ("sender", "auth", "to")
        ):
            self._append_log(f"{day} {tag} 有 {len(rows)} 场建议，但邮箱未配置")
            return
        import csv as _csv
        import io

        buf = io.StringIO()
        w = _csv.writer(buf)
        w.writerow(["联赛", "开赛", "比分/状态", "主队", "客队", "下注层"])
        for r in rows:
            w.writerow(
                [
                    r.get("league", ""),
                    r.get("time", ""),
                    sc.score_status(r),
                    r.get("home", ""),
                    r.get("away", ""),
                    sc.bet_cell(r),
                ]
            )
        text = buf.getvalue()
        subject = f"东风-61洲际导弹 每日建议下注 {day} ({len(rows)}场)"
        body = f"今日 21:00 建议下注汇总，共 {len(rows)} 场。\n\n" + text
        fname = f"建议下注_{day}.csv"
        data = ("\ufeff" + text).encode("utf-8")
        threading.Thread(
            target=self._mail_worker,
            args=(cfg, subject, body, (fname, data)),
            daemon=True,
        ).start()
        self._append_log(f"{day} {tag} 已发送建议下注汇总: {len(rows)} 场")

    def _proxy_cfg_path(self):
        return os.path.join(app_dir(), "proxy_config.json")

    def _load_proxy_cfg(self):
        p = self._proxy_cfg_path()
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return {
                        "host": str(data.get("host", "127.0.0.1")),
                        "port": int(data.get("port", 7890)),
                        "enabled": bool(data.get("enabled", True)),
                        "prefer": bool(data.get("prefer", True)),
                    }
            except Exception:
                pass
        return {"host": "127.0.0.1", "port": 7890, "enabled": True, "prefer": True}

    def _open_proxy_settings(self):
        win = tk.Toplevel(self)
        win.title("代理设置")
        win.transient(self)
        win.resizable(False, False)
        frm = ttk.Frame(win, padding=10)
        frm.pack(fill="x")
        ttk.Label(frm, text="代理地址:").grid(row=0, column=0, sticky="w", pady=4)
        e_host = ttk.Entry(frm, width=24)
        e_host.grid(row=0, column=1, pady=4)
        ttk.Label(frm, text="端口:").grid(row=1, column=0, sticky="w", pady=4)
        e_port = ttk.Entry(frm, width=10)
        e_port.grid(row=1, column=1, sticky="w", pady=4)
        e_host.insert(0, self.proxy_cfg.get("host", "127.0.0.1"))
        e_port.insert(0, str(self.proxy_cfg.get("port", 7890)))
        en = tk.BooleanVar(value=self.proxy_cfg.get("enabled", True))
        pf = tk.BooleanVar(value=self.proxy_cfg.get("prefer", True))
        ttk.Checkbutton(frm, text="启用代理", variable=en).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=2
        )
        ttk.Checkbutton(frm, text="优先走代理(直连被风控时勾选)", variable=pf).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=2
        )

        def save():
            try:
                port = int(e_port.get().strip())
            except ValueError:
                port = 7890
            self.proxy_cfg = {
                "host": e_host.get().strip() or "127.0.0.1",
                "port": port,
                "enabled": bool(en.get()),
                "prefer": bool(pf.get()),
            }
            try:
                with open(self._proxy_cfg_path(), "w", encoding="utf-8") as f:
                    json.dump(self.proxy_cfg, f, ensure_ascii=False, indent=1)
            except Exception as e:
                self._append_log(f"代理配置保存失败: {e}")
            t.set_proxy(
                self.proxy_cfg["host"],
                self.proxy_cfg["port"],
                self.proxy_cfg["enabled"],
                self.proxy_cfg["prefer"],
            )
            self._append_log(
                f"代理设置已保存: {self.proxy_cfg['host']}:{self.proxy_cfg['port']} "
                f"启用={self.proxy_cfg['enabled']} 优先={self.proxy_cfg['prefer']}"
            )
            win.destroy()

        btns = ttk.Frame(win)
        btns.pack(pady=8)
        ttk.Button(btns, text="保存", command=save).pack(side="left", padx=8)
        ttk.Button(btns, text="取消", command=win.destroy).pack(side="left", padx=8)
        win.geometry(f"+{self.winfo_rootx() + 120}+{self.winfo_rooty() + 140}")
        self.wait_window(win)

    def _league_filter_path(self):
        return os.path.join(app_dir(), "league_filter.json")

    def _load_league_filter(self):
        p = self._league_filter_path()
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self.league_kw = [str(x).strip() for x in data if str(x).strip()]
            except Exception:
                self.league_kw = []

    def _app_settings_path(self):
        return os.path.join(app_dir(), "app_settings.json")

    def _load_all_leagues(self):
        p = self._app_settings_path()
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return bool(data.get("all_leagues"))
            except Exception:
                return False
        return False

    def _toggle_all_leagues(self):
        self.all_leagues = bool(self.all_leagues_var.get())
        try:
            with open(self._app_settings_path(), "w", encoding="utf-8") as f:
                json.dump({"all_leagues": self.all_leagues}, f, ensure_ascii=False)
        except Exception as e:
            self._append_log(f"设置保存失败: {e}")
        self._append_log(
            "已切换为: 全联赛(不过滤)" if self.all_leagues else "已切换为: 按联赛名单过滤"
        )

    def _league_ok(self, name):
        if not self.league_kw:
            return True
        for k in self.league_kw:
            if k == "甲级":
                if "甲" in name:
                    return True
            elif k and k in name:
                return True
        return False

    def _open_league_filter(self):
        win = tk.Toplevel(self)
        win.title("联赛筛选设置")
        win.transient(self)
        win.resizable(False, False)
        ttk.Label(
            win,
            text="每行一个关键词(留空=扫全部联赛); 填“甲级”=所有名称含“甲”的联赛",
        ).pack(padx=10, pady=(8, 2))
        txt = tk.Text(win, width=44, height=12)
        txt.pack(padx=10)
        txt.insert("1.0", "\n".join(self.league_kw))

        def save():
            raw = txt.get("1.0", "end")
            self.league_kw = [
                x.strip() for x in raw.replace("，", ",").replace("\n", ",").split(",")
                if x.strip()
            ]
            try:
                with open(self._league_filter_path(), "w", encoding="utf-8") as f:
                    json.dump(self.league_kw, f, ensure_ascii=False, indent=1)
            except Exception as e:
                self._append_log(f"联赛筛选保存失败: {e}")
            self._append_log(f"联赛筛选已保存: {len(self.league_kw)} 个关键词")
            win.destroy()

        btns = ttk.Frame(win)
        btns.pack(pady=8)
        ttk.Button(btns, text="保存", command=save).pack(side="left", padx=8)
        ttk.Button(btns, text="取消", command=win.destroy).pack(side="left", padx=8)
        win.geometry(f"+{self.winfo_rootx() + 120}+{self.winfo_rooty() + 140}")
        self.wait_window(win)

    def _settled_stats(self):
        win = loss = push = 0
        for r in self.all_rows:
            snap = r.get("bet_snapshot") or ""
            if "倾向" not in snap:
                continue
            verdict = sc.result_verdict(r)
            if verdict == "✔":
                win += 1
            elif verdict == "✘":
                loss += 1
            elif verdict == "走盘":
                push += 1
        if win + loss == 0:
            rate_txt = "暂无胜率(等完场结算)"
        else:
            rate_txt = f"胜率 {100.0 * win / (win + loss):.1f}%"
        return {
            "win": win,
            "loss": loss,
            "push": push,
            "rate": rate_txt,
        }

    def _show_winrate(self):
        s = self._settled_stats()
        text = (
            f"已结算 {s['win'] + s['loss'] + s['push']} 场\n"
            f"命中 ✔: {s['win']} 场\n"
            f"未中 ✘: {s['loss']} 场\n"
            f"走盘: {s['push']} 场\n"
            f"当前命中率: {s['rate']}"
        )
        win = tk.Toplevel(self)
        win.title("胜率统计")
        win.transient(self)
        win.resizable(False, False)
        tk.Label(
            win, text=text, justify="left", font=("Microsoft YaHei", 11), padx=18, pady=12
        ).pack()
        ttk.Button(win, text="关闭", command=win.destroy).pack(pady=(0, 10))
        win.geometry(f"+{self.winfo_rootx() + 150}+{self.winfo_rooty() + 180}")
        self._append_log(f"胜率统计: {s['win']}中/{s['loss']}不中 走盘{s['push']} {s['rate']}")

    def _poll(self):
        try:
            while True:
                ev = self.events.get_nowait()
                kind = ev[0]
                if kind == "log":
                    self._append_log(ev[1])
                elif kind == "row":
                    r, is_new = ev[1], ev[2]
                    old_row = next(
                        (
                            x
                            for x in self.all_rows
                            if x.get("sid") == r["sid"]
                        ),
                        None,
                    )
                    self.all_rows = [
                        x for x in self.all_rows if x.get("sid") != r["sid"]
                    ]
                    if old_row:
                        for _k in (
                            "bet_snapshot",
                            "bet_snapshot2",
                            "lock_pin_line",
                            "lock_crown_line",
                            "lock2_pin_line",
                            "lock2_crown_line",
                            "lock_sig",
                            "lock2_sig",
                        ):
                            if old_row.get(_k) is not None:
                                r[_k] = old_row[_k]
                    if r.get("bet_snapshot"):
                        self.live_info.setdefault(r["sid"], {})[
                            "snapshot"
                        ] = r["bet_snapshot"]
                    self.all_rows.append(r)
                    self._render(self.all_rows, {r["sid"]} if is_new else set())
                    self._save_history()
                    self._maybe_auto_clear()
                    if is_new:
                        self._append_log(
                            "NEW "
                            f"{r['league']} {r['home']} vs {r['away']} id={r['sid']} "
                            f"{sc.fmt_odds(r.get('open_line'), r.get('open_big'), r.get('open_small'))} "
                            f"→ {sc.fmt_odds(r.get('cur_line'), r.get('cur_big'), r.get('cur_small'))} "
                            f"盘差 {r['diff']}"
                        )
                    cur_txt = sc.betting_reference(r)
                    has_tend = "倾向" in cur_txt
                    if has_tend and "bet_snapshot" not in r:
                        r["bet_snapshot"] = cur_txt
                        r["lock_pin_line"] = r.get("cur_line")
                        r["lock_crown_line"] = r.get("c2_cur_line")
                        r["lock_sig"] = sc.ou_signal(r)
                        self._save_history()
                    elif has_tend and not r.get("bet_snapshot2"):
                        def _mkt(x):
                            if "[亚盘]" in x:
                                return "亚盘"
                            if "[大小]" in x:
                                return "大小"
                            return "?"

                        if _mkt(cur_txt) != _mkt(r.get("bet_snapshot") or ""):
                            r["bet_snapshot2"] = cur_txt
                            r["lock2_pin_line"] = r.get("cur_line")
                            r["lock2_crown_line"] = r.get("c2_cur_line")
                            r["lock2_sig"] = sc.ou_signal(r)
                            self._save_history()
                            self._append_log(
                                f"已追加参考倾向: {r.get('league', '')} "
                                f"{r.get('home', '')} vs {r.get('away', '')} → {cur_txt}"
                            )
                    if has_tend and r["sid"] not in self.tend_sounded:
                        self.tend_sounded.add(r["sid"])
                        self._append_log(
                            "🔔 出现倾向: "
                            f"{r['league']} {r['home']} vs {r['away']} "
                            f"{sc.betting_reference(r)}"
                        )
                        self._play_tend_sound()
                        self._send_tend_mail(r)
                elif kind == "live":
                    sid, score, minute = ev[1], ev[2], ev[3]
                    for x in self.all_rows:
                        if x.get("sid") == sid:
                            x["cur_score"] = score
                            x["cur_minute"] = minute
                            break
                    for _x in self.all_rows:
                        if _x.get("sid") == sid:
                            self._record_ou_if_finished(_x)
                            break
                    self._render(self.all_rows, set())
                    self._save_history()
                    self._maybe_auto_clear()
                elif kind == "finish":
                    # 官方即时比分已判定完场 -> 定格比分并立即结算
                    sid, score = ev[1], ev[2]
                    for x in self.all_rows:
                        if x.get("sid") == sid:
                            if score:
                                x["cur_score"] = score
                            x["live_state"] = "-1"
                            self._append_log(
                                "🏁 完场: "
                                f"{x.get('league', '')} {x.get('home', '')} vs "
                                f"{x.get('away', '')} {score}"
                            )
                            self._record_ou_if_finished(x)
                            break
                    self._render(self.all_rows, set())
                    self._save_history()
                    self._maybe_auto_clear()
                elif kind == "daily_mail":
                    self._send_daily_digest(ev[1])
                elif kind == "passlog":
                    ok_c, err_c, q_c, new_c, cost = ev[1:]
                    self._append_log(
                        f"本轮完成: 成功 {ok_c} 失败 {err_c} 达标 {q_c} "
                        f"新增 {new_c} 耗时 {cost:.1f}s"
                    )
                    self.status.config(text=f"运行中 · 本轮达标 {q_c} 场")
                elif kind == "stopped":
                    self.status.config(text="已停止")
                    self.btn_start.config(state="normal")
                    self.btn_stop.config(state="disabled")
        except queue.Empty:
            pass
        self.after(200, self._poll)

    def _render(self, rows, new_sids):
        all_rows = self._sort_rows(rows)
        self.last_rows = all_rows
        disp = all_rows
        self.tree.delete(*self.tree.get_children())
        for r in disp:
            mark = ""
            cur_line = r.get("cur_line")
            c2_cur = r.get("c2_cur_line")
            if (
                cur_line is not None
                and c2_cur is not None
                and abs(float(cur_line) - float(c2_cur)) >= 1e-9
            ):
                mark = f"平{sc.fmt_line(cur_line)}≠皇{sc.fmt_line(c2_cur)}"
            if r["sid"] in new_sids:
                tag = "new"
            elif mark:
                tag = "diff2"
            else:
                tag = ""
            bet_txt = sc.betting_reference(r)
            bet_cell = sc.bet_cell(r)
            row_tags = []
            if tag:
                row_tags.append(tag)
            if "倾向" in bet_txt or (
                r.get("bet_snapshot") and "倾向" in r["bet_snapshot"]
            ):
                row_tags.append("buyrow")
            self.tree.insert(
                "",
                "end",
                iid=str(r["sid"]),
                values=(
                    r.get("league", ""),
                    r.get("time", ""),
                    sc.score_status(r),
                    r.get("home", ""),
                    r.get("away", ""),
                    sc.fmt_odds(r.get("open_line"), r.get("open_big"), r.get("open_small")),
                    sc.fmt_odds(r.get("cur_line"), r.get("cur_big"), r.get("cur_small")),
                    f"{r.get('diff', '')}",
                    r.get("open_time", ""),
                    r.get("cur_time", ""),
                    sc.fmt_odds(
                        r.get("c2_open_line"), r.get("c2_open_big"), r.get("c2_open_small")
                    ),
                    sc.fmt_odds(
                        r.get("c2_cur_line"), r.get("c2_cur_big"), r.get("c2_cur_small")
                    ),
                    bet_cell,
                ),
                tags=tuple(row_tags),
            )
        self.status.config(text=f"运行中 · 本轮达标 {len(disp)} 场")

    def _time_key(self, r):
        ko = (r.get("kickoff") or "").strip()
        if ko:
            return ko
        t = (r.get("time") or "").strip()
        return "9999-99-99 " + (t if re.match(r"^\d{1,2}:\d{2}$", t) else "99:99")

    def _sort_rows(self, rows):
        key = self.sort_key

        def kf(r):
            if key == "time":
                return self._time_key(r)
            if key in ("sid", "diff"):
                try:
                    return float(r.get(key) or 0)
                except (TypeError, ValueError):
                    return 0.0
            return str(r.get(key, "") or "")

        return sorted(rows, key=kf, reverse=self.sort_desc)

    def _sort_by(self, key):
        if self.sort_key == key:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_key = key
            self.sort_desc = False
        if self.last_rows:
            self._render(self.last_rows, set())

    def _append_log(self, msg):
        self.logtxt.config(state="normal")
        self.logtxt.insert("end", msg + "\n")
        self.logtxt.see("end")
        self.logtxt.config(state="disabled")

    def _notes_path(self):
        return os.path.join(app_dir(), "notes.json")

    def _load_notes(self):
        p = self._notes_path()
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self.notes = {str(k): str(v) for k, v in data.items()}
            except Exception:
                self.notes = {}

    def _save_notes(self):
        try:
            with open(self._notes_path(), "w", encoding="utf-8") as f:
                json.dump(self.notes, f, ensure_ascii=False, indent=1)
        except Exception as e:
            self._append_log(f"备注保存失败: {e}")

    def _history_path(self):
        return os.path.join(app_dir(), "track_history.json")

    def _save_history(self):
        try:
            with open(self._history_path(), "w", encoding="utf-8") as f:
                json.dump(self.all_rows, f, ensure_ascii=False, indent=1)
        except Exception as e:
            self._append_log(f"跟踪记录保存失败: {e}")

    def _load_history(self):
        p = self._history_path()
        if not os.path.exists(p):
            return
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return
        if not isinstance(data, list):
            return
        from datetime import datetime, timedelta

        now = datetime.now()
        kept = []
        for r in data:
            if not isinstance(r, dict) or not r.get("sid"):
                continue
            ko = r.get("kickoff")
            try:
                ko_dt = datetime.strptime(ko, "%Y-%m-%d %H:%M")
                if now - ko_dt > timedelta(days=3):
                    continue
            except (TypeError, ValueError):
                pass
            kept.append(r)
        self.all_rows = kept

    def _auto_note(self, sid):
        r = next((x for x in self.last_rows if str(x.get("sid")) == str(sid)), None)
        if not r:
            return ""
        cur_line = r.get("cur_line")
        c2_cur = r.get("c2_cur_line")
        if (
            cur_line is not None
            and c2_cur is not None
            and abs(float(cur_line) - float(c2_cur)) >= 1e-9
        ):
            return f"平{sc.fmt_line(cur_line)}≠皇{sc.fmt_line(c2_cur)}"
        return ""

    def _on_double_click(self, event):
        if self._edit_active:
            return
        colid = self.tree.identify_column(event.x)
        if not colid or colid == "#0":
            return
        idx = int(colid[1:]) - 1
        if idx < 0 or idx >= len(self.COLS) or self.COLS[idx][0] != "note":
            return
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        box = self.tree.bbox(iid, colid)
        if not box or box[2] <= 0:
            return
        x, y, w, h = box
        self._edit_active = True
        e = ttk.Entry(self.tree)
        e.place(x=x, y=y, width=max(60, w), height=max(20, h))
        e.insert(0, self.notes.get(iid, "") or self._auto_note(iid))
        e.focus_set()
        e.bind("<Return>", lambda ev: self._commit_edit(e, iid))
        e.bind("<FocusOut>", lambda ev: self._commit_edit(e, iid))
        e.bind("<Escape>", lambda ev: self._cancel_edit(e))

    def _commit_edit(self, e, iid):
        if not self._edit_active:
            return
        text = e.get().strip()
        self._edit_active = False
        e.destroy()
        self.notes[iid] = text
        self._save_notes()
        self._save_history()
        if self.tree.exists(iid):
            self.tree.set(iid, "note", text if text else self._auto_note(iid))

    def _cancel_edit(self, e):
        if not self._edit_active:
            return
        self._edit_active = False
        e.destroy()

    def _company_label(self, cid):
        return self.COMPANY_NAMES.get(cid, f"公司{cid}")

    def _apply_main_labels(self, cid):
        name = self._company_label(cid)
        self.tree.heading("open", text=f"{name}初盘")
        self.tree.heading("cur", text=f"{name}即时")
        self.tree.heading("c2cur", text="皇冠即时")

    def export_csv(self):
        scope = self._ask_export_scope()
        if not scope:
            return
        rows = self.last_rows
        if scope == "buy":
            rows = [
                r for r in self.last_rows if "倾向" in sc.bet_cell(r)
            ]
        if not rows:
            messagebox.showinfo("提示", "当前没有可导出的数据")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile=f"变盘报警_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        )
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["联赛", "开赛", "比分/状态", "主队", "客队", "下注层"])
            for r in rows:
                w.writerow(
                    [
                        r.get("league", ""),
                        r.get("time", ""),
                        sc.score_status(r),
                        r.get("home", ""),
                        r.get("away", ""),
                        sc.bet_cell(r),
                    ]
                )
        self._append_log(f"已导出 {path}")

    def _ask_export_scope(self):
        win = tk.Toplevel(self)
        win.title("导出范围")
        win.transient(self)
        win.grab_set()
        win.resizable(False, False)
        var = tk.StringVar(value="buy")
        ttk.Label(win, text="请选择导出范围:").pack(padx=14, pady=(12, 4), anchor="w")
        ttk.Radiobutton(
            win, text="只导出建议下注 (BUY)", value="buy", variable=var
        ).pack(padx=18, anchor="w")
        ttk.Radiobutton(
            win, text="导出全部", value="all", variable=var
        ).pack(padx=18, anchor="w")
        btns = ttk.Frame(win)
        btns.pack(pady=(8, 10))
        result = {}

        def ok():
            result["scope"] = var.get()
            win.destroy()

        def cancel():
            win.destroy()

        ttk.Button(btns, text="确定", command=ok).pack(side="left", padx=8)
        ttk.Button(btns, text="取消", command=cancel).pack(side="left", padx=8)
        win.geometry(f"+{self.winfo_rootx() + 80}+{self.winfo_rooty() + 120}")
        self.wait_window(win)
        return result.get("scope")

    def _on_close(self):
        self.running = False
        self._save_history()
        self.destroy()


def main():
    app = ScannerApp()
    if "--autostart" in sys.argv:
        app.start()
    app.mainloop()


if __name__ == "__main__":
    if sys.stdout is not None:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    main()
