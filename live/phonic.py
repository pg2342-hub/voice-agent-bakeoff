"""Tiny stdlib client for the Phonic REST API (https://docs.phonic.ai).

Reads PHONIC_API_KEY from the environment or from ~/.config/phonic/.env.
The key never goes in this repo.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://api.phonic.ai/v1"


def api_key():
    key = os.environ.get("PHONIC_API_KEY")
    if key:
        return key
    env = Path.home() / ".config" / "phonic" / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("PHONIC_API_KEY="):
                return line.split("=", 1)[1].strip().strip("'\"")
    raise SystemExit("Set PHONIC_API_KEY or create ~/.config/phonic/.env")


def call(method, path, body=None, query=None):
    url = BASE + path
    if query:
        url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {api_key()}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} {path} -> {e.code}: {e.read().decode()[:500]}")


def project_id(name="main"):
    res = call("GET", "/projects")
    for p in res.get("projects", res if isinstance(res, list) else []):
        if p.get("name") == name:
            return p["id"]
    raise SystemExit(f"project {name!r} not found: {res}")


def list_conversations(project="main", started_at_min=None):
    out, after = [], None
    while True:
        res = call("GET", "/conversations", query={"project": project, "limit": 50,
                                                   "after": after, "started_at_min": started_at_min})
        out.extend(res.get("conversations", []))
        after = (res.get("pagination") or {}).get("next_cursor")
        if not after:
            return out
