"""Replay every v1 test call's recorded audio through agent v2 (same caller, new prompt).

  python3 -m live.replay_v2 --since 2026-11-21

Uses POST /conversations/{id}/replay with agent=line-cook-screener-v2. Phonic may
ask for a payment method on file before replays (HTTP 402); if so, fall back to
turn replay on the failing turns (POST /conversation_items/{id}/replay with the
v2 system_prompt), which the scorecard reports separately.
"""

import argparse

from .phonic import call, list_conversations
from .pull_calls import agent_slug


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True)
    a = ap.parse_args()
    convs = sorted(list_conversations(started_at_min=a.since), key=lambda c: c.get("started_at") or "")
    v1 = [c for c in convs if agent_slug(c) == "line-cook-screener-v1" and c.get("origin") != "replay"][:20]
    for i, c in enumerate(v1, 1):
        res = call("POST", f"/conversations/{c['id']}/replay", {"agent": "line-cook-screener-v2"})
        print(f"script {i:02d}: {res.get('message')}")


if __name__ == "__main__":
    main()
