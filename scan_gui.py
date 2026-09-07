# -*- coding: utf-8 -*-
"""东风‑61 洲际导弹 - 作者：程序猿虾米（本软件只提供数据参考，禁止非法赌博行为）"""

import csv
import json
import os
import queue
import re
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
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
            "（本软件只提供数据参考，禁止非法赌博行为，如有不法行为后果自负）"
        )
        self.geometry("1560x920")
        self.running = False
        self.stop_ev = threading.Event()
        self.worker = None
        self.events = queue.Queue()
        self.alerted = set()
        self.skip = set()
        self.last_rows = []
        self.all_rows = []
        self.live_sids = set()
        self.tend_sounded = set()
        default_wav = os.path.join(app_dir(), "alert.wav")
        self.sound_wav = default_wav if os.path.exists(default_wav) else None
        self.sound_mode = "自定义WAV" if self.sound_wav else "双声高音(默认)"
        self.sort_key = "time"
        self.sort_desc = False
        self.notes = {}
        self._edit_active = False
        self._load_notes()
        self._build()
        self._load_history()
        self.live_sids = {str(r.get("sid")) for r in self.all_rows}
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
        self.e_workers.insert(0, "4")
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
        self.auto_clear_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            cfg, text="完场自动清空", variable=self.auto_clear_var
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
        self.tend_sounded.clear()
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
            self.events.put(("log", f"本轮 {len(matches)} 场，开始拉盘…"))
            counters = {"ok": 0, "err": 0, "q": 0, "new": 0}
            results = []

            def on_result(r):
                if self.stop_ev.is_set():
                    return
                results.append(r)
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
            for sid in list(self.live_sids):
                if not self.running:
                    break
                try:
                    d = t.fetch_company_ou_detail(sid, cid=self.cid, timeout=18)
                except Exception:
                    continue
                if d:
                    self.events.put(
                        (
                            "live",
                            sid,
                            (d.get("cur_score") or "").strip(),
                            (d.get("cur_minute") or "").strip(),
                        )
                    )
            cost = time.time() - t0
            self._sleep(max(5, self.interval - cost))
        self.events.put(("stopped", None))

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
                r for r in self.last_rows if "倾向" in sc.betting_reference(r)
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
            w.writerow(
                [
                    "联赛", "开赛", "比分/状态", "主队", "客队",
                    "主公司初盘", "主公司即时", "盘差", "初盘时间", "即时时间",
                    "皇冠初盘", "皇冠即时",
                    "下注层", "备注",
                ]
            )
            for r in rows:
                w.writerow(
                    [
                        r.get("league", ""), r.get("time", ""),
                        sc.score_status(r), r.get("home", ""),
                        r.get("away", ""),
                        sc.fmt_odds(r.get("open_line"), r.get("open_big"), r.get("open_small")),
                        sc.fmt_odds(r.get("cur_line"), r.get("cur_big"), r.get("cur_small")),
                        r.get("diff", ""),
                        r.get("open_time", ""), r.get("cur_time", ""),
                        sc.fmt_odds(
                            r.get("c2_open_line"), r.get("c2_open_big"), r.get("c2_open_small")
                        ),
                        sc.fmt_odds(
                            r.get("c2_cur_line"), r.get("c2_cur_big"), r.get("c2_cur_small")
                        ),
                        sc.bet_cell(r),
                        self.notes.get(str(r["sid"]), "")
                        or (
                            f"平{sc.fmt_line(r.get('cur_line'))}≠皇{sc.fmt_line(r.get('c2_cur_line'))}"
                            if (
                                r.get("cur_line") is not None
                                and r.get("c2_cur_line") is not None
                                and abs(float(r["cur_line"]) - float(r["c2_cur_line"])) >= 1e-9
                            )
                            else ""
                        ),
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
    app.mainloop()


if __name__ == "__main__":
    if sys.stdout is not None:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    main()
