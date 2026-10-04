# -*- coding: utf-8 -*-
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

TOKEN = os.environ["GH_TOKEN"]
OWNER = "372840493-cyber"
REPO = "-dongfeng611--odds-monitor"
API = "https://api.github.com"
HEADERS = {
    "Authorization": "token " + TOKEN,
    "User-Agent": "codex-upload",
    "Accept": "application/vnd.github+json",
}


def req(method, url, payload=None, timeout=90):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    r = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    if data:
        r.add_header("Content-Type", "application/json; charset=utf-8")
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        body = resp.read()
        return json.loads(body.decode("utf-8")) if body else {}


repo_info = req("GET", f"{API}/repos/{OWNER}/{REPO}")
branch = repo_info.get("default_branch", "main")
print("REPO", repo_info["full_name"], "branch", branch, flush=True)

files = [
    f.strip()
    for f in subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    if f.strip()
]
print("FILES", len(files), flush=True)
ok = fail = 0
for i, rel in enumerate(files, 1):
    full = rel.replace("/", os.sep)
    if not os.path.exists(full):
        print("SKIP_MISSING", rel, flush=True)
        continue
    with open(full, "rb") as f:
        raw = f.read()
    b64 = base64.b64encode(raw).decode("ascii")
    done = False
    for attempt in range(1, 4):
        try:
            sha = None
            try:
                info = req("GET", f"{API}/repos/{OWNER}/{REPO}/contents/{rel}")
                if isinstance(info, dict):
                    sha = info.get("sha")
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    raise
            payload = {"message": f"更新 {rel}", "content": b64, "branch": branch}
            if sha:
                payload["sha"] = sha
            req("PUT", f"{API}/repos/{OWNER}/{REPO}/contents/{rel}", payload)
            ok += 1
            print(f"OK {i}/{len(files)} {rel}", flush=True)
            done = True
            break
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")[:150]
            print(f"HTTPFAIL {rel} try{attempt} {e.code} {msg}", flush=True)
            if e.code in (401, 403):
                break
            time.sleep(3)
        except Exception as e:
            print(f"RETRY {rel} try{attempt} {type(e).__name__}", flush=True)
            time.sleep(3)
    if not done:
        fail += 1
    time.sleep(0.2)
print("DONE ok", ok, "fail", fail, flush=True)
