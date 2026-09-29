# -*- coding: utf-8 -*-
import subprocess
import sys

sys.path.insert(0, ".")
import titan_common as t

ms = t.fetch_home_matches()
print("MATCHES", len(ms))
for m in ms[:5]:
    u = f"https://vip.titan007.com/OverDown_n.aspx?id={m['sid']}&l=0"
    r = subprocess.run(
        ["curl.exe", "-sS", "--max-time", "15", "-A", "Mozilla/5.0",
         "-o", "NUL", "-w", "%{http_code}", u],
        capture_output=True,
    )
    print(m["sid"], m["league"], r.stdout.decode(errors="ignore"), r.stderr[:80])
