# -*- coding: utf-8 -*-
"""大小球变盘扫描器 - 会员版 (数据源: 程序猿：小虾米)"""

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


def now():
    return datetime.now().strftime("%H:%M:%S")


class ScannerApp(tk.Tk):
    COLS = [
        ("league", "联赛", 64),
        ("time", "开赛", 46),
        ("home", "主队", 96),
        ("away", "客队", 96),
        ("sid", "ID", 66),
        ("open", "初盘", 92),
        ("cur", "即时盘", 92),
        ("diff", "盘差", 46),
        ("open_time", "初盘时间", 74),
        ("cur_time", "即时时间", 74),
        ("c2cur", "皇冠即时", 92),
        ("note", "备注", 110),
    ]

    COMPANY_NAMES = {
        1: "澳门", 3: "皇冠", 8: "bet365", 9: "威廉希尔", 12: "易胜博",
        14: "伟德", 17: "明陞", 22: "10BET", 24: "12bet", 31: "利记",
        35: "盈禾", 42: "18bet", 47: "平博", 50: "1xBet",
    }

    def __init__(self):
        super().__init__()
        self.title("大小球变盘扫描器 - 会员版 (数据源: 程序猿：小虾米)")
        self.geometry("1280x760")
        self.running = False
        self.worker = None
        self.events = queue.Queue()
        self.alerted = set()
        self.skip = set()
        self.last_rows = []
        self.sort_key = "time"
        self.sort_desc = False
        self.notes = {}
        self._edit_active = False
        self._load_notes()
        self._build()
        self.after(200, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.tree.bind("<Double-1>", self._on_double_click)

    def _build(self):
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
        self.status = ttk.Label(cfg, text="空闲", foreground="#1a6bb8")
        self.status.pack(side="right")

        body = ttk.Frame(self, padding=(8, 0, 8, 4))
        body.pack(fill="both", expand=True)
        cols = [c[1] for c in self.COLS]
        keys = [c[0] for c in self.COLS]
        self.tree = ttk.Treeview(body, columns=keys, show="headings", selectmode="browse")
        for (key, label, width), k in zip(self.COLS, keys):
            self.tree.heading(key, text=label, command=lambda k=key: self._sort_by(k))
            self.tree.column(key, width=width, anchor="w")
        self._apply_main_labels(47)
        vs = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")
        self.tree.tag_configure("new", background="#fff3b0")
        self.tree.tag_configure("diff2", background="#ffe0dc")

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
        self.alerted.clear()
        self.skip.clear()
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.status.config(text="运行中")
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()

    def stop(self):
        self.running = False
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
            results = sc.scan_matches(
                matches, cid=self.cid, cid2=3, workers=self.workers, timeout=18
            )
            ok = [r for r in results if not r.get("error")]
            err = len(results) - len(ok)
            for r in results:
                if r.get("error") == "no-data":
                    self.skip.add(r["sid"])
            q = sc.qualify(results, self.thr)
            new = [r for r in q if r["sid"] not in self.alerted]
            for r in new:
                self.alerted.add(r["sid"])
            self.events.put(("rows", q, [r["sid"] for r in new]))
            self.events.put(
                (
                    "log",
                    f"成功 {len(ok)} 失败 {err} 达标 {len(q)} 新增 {len(new)} "
                    f"本轮耗时 {time.time() - t0:.1f}s",
                )
            )
            for r in new:
                self.events.put(
                    (
                        "new",
                        f"{r['league']} {r['home']} vs {r['away']} id={r['sid']} "
                        f"{sc.fmt_odds(r['open_line'], r['open_big'], r['open_small'])} "
                        f"→ {sc.fmt_odds(r['cur_line'], r['cur_big'], r['cur_small'])} "
                        f"盘差 {r['diff']}",
                    )
                )
            cost = time.time() - t0
            self._sleep(max(5, self.interval - cost))
        self.events.put(("stopped", None))

    def _sleep(self, secs):
        end = time.time() + secs
        while self.running and time.time() < end:
            time.sleep(0.5)

    def _poll(self):
        try:
            while True:
                ev = self.events.get_nowait()
                kind = ev[0]
                if kind == "log":
                    self._append_log(ev[1])
                elif kind == "rows":
                    self._render(ev[1], set(ev[2]))
                elif kind == "new":
                    self._append_log("NEW " + ev[1])
                    if winsound:
                        try:
                            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                        except Exception:
                            pass
                elif kind == "stopped":
                    self.status.config(text="已停止")
                    self.btn_start.config(state="normal")
                    self.btn_stop.config(state="disabled")
        except queue.Empty:
            pass
        self.after(200, self._poll)

    def _render(self, rows, new_sids):
        rows = self._sort_rows(rows)
        self.last_rows = rows
        self.tree.delete(*self.tree.get_children())
        for r in rows:
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
            self.tree.insert(
                "",
                "end",
                iid=str(r["sid"]),
                values=(
                    r.get("league", ""),
                    r.get("time", ""),
                    r.get("home", ""),
                    r.get("away", ""),
                    r.get("sid", ""),
                    sc.fmt_odds(r.get("open_line"), r.get("open_big"), r.get("open_small")),
                    sc.fmt_odds(r.get("cur_line"), r.get("cur_big"), r.get("cur_small")),
                    f"{r.get('diff', '')}",
                    r.get("open_time", ""),
                    r.get("cur_time", ""),
                    sc.fmt_odds(
                        r.get("c2_cur_line"), r.get("c2_cur_big"), r.get("c2_cur_small")
                    ),
                    note_txt,
                ),
                tags=(tag,),
            )
        self.status.config(text=f"运行中 · 本轮达标 {len(rows)} 场")

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
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "notes.json")

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
        if not self.last_rows:
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
                    "联赛", "开赛", "主队", "客队", "ID",
                    "主公司初盘", "主公司即时", "盘差", "初盘时间", "即时时间",
                    "皇冠即时", "备注",
                ]
            )
            for r in self.last_rows:
                w.writerow(
                    [
                        r.get("league", ""), r.get("time", ""), r.get("home", ""),
                        r.get("away", ""), r.get("sid", ""),
                        sc.fmt_odds(r.get("open_line"), r.get("open_big"), r.get("open_small")),
                        sc.fmt_odds(r.get("cur_line"), r.get("cur_big"), r.get("cur_small")),
                        r.get("diff", ""), r.get("open_time", ""), r.get("cur_time", ""),
                        sc.fmt_odds(
                            r.get("c2_cur_line"), r.get("c2_cur_big"), r.get("c2_cur_small")
                        ),
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

    def _on_close(self):
        self.running = False
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
