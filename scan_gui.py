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
        ("note", "备注", 110),
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
        self.geometry("1560x920")
        self.running = False
        self.stop_ev = threading.Event()
        self.worker = None
        self.score_thread = None
        self._last_live = {}
        self.live_meta = {}
        self.live_info = {}
        self._rechecked = set()
        self._score_verified = set()
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
        ttk.Button(cfg, text="导出CSV", command=self.export_csv).pack(side="left", padx=6)
        ttk.Label(cfg, text="提示音:").pack(side="left")
        self.sound_cb = ttk.Combobox(
            cfg,
            values=("无", "系统提示", "双声高音(默认)", "自定义WAV"),
            width=13,
            state="readonly",
        )
        self.sound_cb.set(self.sound_mode)
        self.sound_cb.pack(side="left", padx=(2, 8))
        self.sound_cb.bind("<<ComboboxSelected>>", self._on_sound_select)
        ttk.Button(cfg, text="清空已完赛", command=self._clear_finished).pack(
            side="left", padx=4
        )
        ttk.Button(cfg, text="删除选中", command=self._delete_selected).pack(
            side="left", padx=4
        )
        self.auto_clear_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            cfg, text="完场自动清空", variable=self.auto_clear_var
        ).pack(side="left", padx=4)
        ttk.Button(cfg, text="邮箱通知", command=self._open_mail_settings).pack(
            side="left", padx=4
        )
        ttk.Button(cfg, text="胜率统计", command=self._show_winrate).pack(
            side="left", padx=4
        )
        ttk.Button(cfg, text="联赛筛选", command=self._open_league_filter).pack(
            side="left", padx=4
        )
        ttk.Button(cfg, text="代理设置", command=self._open_proxy_settings).pack(
            side="left", padx=4
        )
        self.all_leagues_var = tk.BooleanVar(value=self.all_leagues)
        ttk.Checkbutton(
            cfg,
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
                sids.append(sid)
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
            # 开赛前 10 分钟最后复查一次倾向
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
                if now2 < ko_dt - timedelta(minutes=10) or now2 >= ko_dt:
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

    def _clear_finished(self):
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

    def _mail_worker(self, cfg, subject, body):
        try:
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
                    old_snap = next(
                        (
                            x.get("bet_snapshot")
                            for x in self.all_rows
                            if x.get("sid") == r["sid"]
                        ),
                        None,
                    )
                    self.all_rows = [
                        x for x in self.all_rows if x.get("sid") != r["sid"]
                    ]
                    if old_snap:
                        r["bet_snapshot"] = old_snap
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
                    has_tend = "倾向" in sc.betting_reference(r)
                    if has_tend and "bet_snapshot" not in r:
                        r["bet_snapshot"] = sc.betting_reference(r)
                        self._save_history()
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
                    self._render(self.all_rows, set())
                    self._save_history()
                    self._maybe_auto_clear()
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
            manual = self.notes.get(str(r["sid"]), "")
            note_txt = manual if manual else mark
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
                    note_txt,
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
