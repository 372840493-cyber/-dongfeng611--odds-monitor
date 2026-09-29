# -*- coding: utf-8 -*-
import csv
import io
import json
import os
import smtplib
import sys
from datetime import datetime
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders

sys.path.insert(0, ".")
import scanner_core as sc

cfg = json.load(open("email_config.json", encoding="utf-8"))
rows_all = json.load(open("track_history.json", encoding="utf-8"))
rows = [r for r in rows_all if "倾向" in sc.bet_cell(r)]
day = datetime.now().strftime("%Y-%m-%d")

buf = io.StringIO()
w = csv.writer(buf)
w.writerow(["联赛", "开赛", "比分/状态", "主队", "客队", "下注层"])
for r in rows:
    w.writerow([
        r.get("league", ""), r.get("time", ""), sc.score_status(r),
        r.get("home", ""), r.get("away", ""), sc.bet_cell(r),
    ])
text = buf.getvalue()

msg = MIMEMultipart()
body = f"[测试] 每日建议下注汇总 {day}，共 {len(rows)} 场。\n\n" + text
msg.attach(MIMEText(body, "plain", "utf-8"))
part = MIMEBase("text", "csv")
part.set_payload(("\ufeff" + text).encode("utf-8"))
encoders.encode_base64(part)
part.add_header("Content-Disposition", "attachment", filename=("utf-8", "", f"建议下注_测试_{day}.csv"))
msg.attach(part)
msg["Subject"] = Header(f"[测试] 东风-61洲际导弹 每日建议下注 {day} ({len(rows)}场)", "utf-8")
msg["From"] = cfg["sender"]
tos = cfg["to"] if isinstance(cfg["to"], list) else [cfg["to"]]
msg["To"] = ", ".join(tos)
print("ROWS", len(rows), "TO", tos)
print("CSV_PREVIEW", text.strip().splitlines()[:4])
try:
    with smtplib.SMTP_SSL(cfg["smtp"], int(cfg.get("port", 465)), timeout=30) as s:
        s.login(cfg["sender"], cfg["auth"])
        s.sendmail(cfg["sender"], tos, msg.as_string())
    print("SEND_OK", day)
except Exception as e:
    print("SEND_FAIL", type(e).__name__, str(e)[:300])
