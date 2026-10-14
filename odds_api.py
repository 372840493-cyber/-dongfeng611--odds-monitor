import json
import http.server
import socketserver
import urllib.parse
import time

KEY = "d61-odds-2026"
DOC = r"C:\Users\Administrator\Documents\ChatGPT\足球500数据抓包\odds_scanner\track_history.json"


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        key = self.headers.get("X-Api-Key") or (query.get("key") or [""])[0]
        if key != KEY:
            payload = b'{"code": 401, "msg": "unauthorized"}'
            self.send_response(401)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        try:
            with open(DOC, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = []
        if not isinstance(data, list):
            data = []
        # 只输出"红色倾向"的建议（带「倾向」标记），其它场次不显示
        data = [
            x for x in data
            if isinstance(x, dict)
            and ("倾向" in str(x.get("bet_snapshot") or "") or "倾向" in str(x.get("bet_snapshot2") or ""))
        ]
        if query.get("key"):
            rows = []
            for it in data:
                snap = str(it.get("bet_snapshot") or "")
                rows.append(
                    "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                        it.get("kickoff") or "-",
                        it.get("league") or "-",
                        it.get("home") or "-",
                        it.get("away") or "",
                        snap.replace("倾向", "") or "-",
                        it.get("crown_cur_line") or it.get("cur_line") or "-",
                        it.get("crown_cur_water") or it.get("cur_big") or "-",
                    )
                )
            html = (
                "<html><head><meta charset='utf-8'><title>洲际导弹倾向</title>"
                "<meta http-equiv='refresh' content='20'>"
                "<style>body{font-family:Microsoft YaHei;padding:16px}"
                "table{border-collapse:collapse;width:100%}"
                "th,td{border:1px solid #ddd;padding:6px;font-size:14px}"
                "th{background:#f3f3f3}</style></head><body>"
                "<h3>洲际导弹倾向（共 " + str(len(data)) + " 条）</h3>"
                "<div style='color:#666;font-size:13px'>更新于 "
                + time.strftime("%H:%M:%S") + "（每 20 秒自动刷新）</div>"
                "<table><tr><th>开赛</th><th>联赛</th><th>主队</th><th>客队</th>"
                "<th>倾向</th><th>皇冠盘口</th><th>水位</th></tr>" + "".join(rows) + "</table>"
                "</body></html>"
            )
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = json.dumps({"code": 0, "count": len(data), "data": data}, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


socketserver.ThreadingTCPServer.allow_reuse_address = True
with socketserver.ThreadingTCPServer(("0.0.0.0", 18081), Handler) as server:
    server.serve_forever()
