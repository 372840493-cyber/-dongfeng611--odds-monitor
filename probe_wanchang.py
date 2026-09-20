# -*- coding: utf-8 -*-
import re, sys
sys.path.insert(0, ".")
import titan_common as t
h = t.fetch_text("https://live.500.com/wanchang.php", timeout=25)
ms = list(re.finditer(r'<tr id="a(\d+)"', h))
print("MATCHES", len(ms))
m = ms[0]
start = m.start(); end = h.find('</tr>', start); seg = h[start:end]
print("END", end, "SEGLEN", len(seg))
print("clientName", seg.count('clientName'), "clt1", seg.count('clt1'), "td_center", seg.count('<td align="center">'))
print("SEG", re.sub(r"\s+", " ", seg)[:600])
