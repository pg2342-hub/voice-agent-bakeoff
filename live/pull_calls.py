"""Pull the live test calls from Phonic, grade them with Phonic's own eval
prompts, extract the screen outcome, and write live/out/live_calls.json.

  python3 -m live.pull_calls --since 2026-11-21            # v1 calls, in call order
  python3 -m live.pull_calls --since 2026-11-21 --with-v2  # also the replays through agent v2

Calls are matched to agent/caller_scripts.md by start order (call 1 = script 1).
Verdict mapping: successful -> pass, unsuccessful -> fail, undecided -> na, error -> error.
An "error" verdict blocks scoring (bakeoff.report --live refuses until it is re-run).
The approve / coach-call "decision" comes from Phonic's extraction applying the
review rule to what the worker said, not from the screener (which never decides).
"""

import argparse
import json
from pathlib import Path

from .phonic import call, list_conversations

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "live" / "out"
PRICE = 0.065  # Phonic Pro list price per minute, phonic.ai/pricing (2026-11-20)

# Answer key per script number (agent/caller_scripts.md)
EXPECTED = {1: "approve", 2: "coach_call", 3: "approve", 4: "coach_call", 5: "approve",
            6: "approve", 7: "approve", 8: "approve", 9: "approve", 10: None,
            11: "approve", 12: "approve", 13: "approve", 14: None, 15: "approve",
            16: "approve", 17: "coach_call", 18: "approve", 19: "approve", 20: "approve"}

VERDICT = {"successful": "pass", "unsuccessful": "fail", "undecided": "na", "error": "error"}


def agent_slug(conv):
    a = conv.get("agent") or {}
    return a.get("name") or a.get("slug")


def to_record(conv, ids, setup, script_no):
    cid = conv["id"]
    verdicts = {}
    for crit_id, prompt_id in ids["eval_prompts"].items():
        res = call("POST", f"/conversations/{cid}/evals", {"prompt_id": prompt_id})
        verdicts[crit_id] = VERDICT.get(res["evaluation"]["result"], "na")
    ext = call("POST", f"/conversations/{cid}/extractions", {"schema_id": ids["schema_id"]})["result"]
    completed = bool(ext.get("screen_completed"))
    rec = ext.get("recommendation")
    analysis = conv.get("analysis") or {}
    return {
        "call_id": f"{setup}-S{script_no:02d}",
        "phonic_conversation_id": cid,
        "setup": setup,
        "worker": f"S{script_no:02d}",
        "outcome": "completed" if completed else "abandoned",
        "duration_s": round((conv.get("duration_ms") or 0) / 1000),
        "latencies_ms": [round(x) for x in analysis.get("latencies_ms", [])],
        "interruptions_count": analysis.get("interruptions_count", 0),
        "decision": rec if rec in ("approve", "coach_call") and completed else None,
        "expected_decision": EXPECTED.get(script_no),
        "extraction": ext,
        "verdicts": verdicts,
        "transcript": [{"role": "agent" if it["role"] == "assistant" else "worker",
                        "text": it.get("post_call_transcript") or it.get("live_transcript") or ""}
                       for it in conv.get("items", [])],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True, help="UTC date the test calls started, e.g. 2026-11-21")
    ap.add_argument("--with-v2", action="store_true")
    a = ap.parse_args()
    ids = json.loads((OUT / "ids.json").read_text())
    convs = sorted(list_conversations(started_at_min=a.since), key=lambda c: c.get("started_at") or "")
    setups = {"phonic_v1": {"label": "Phonic-1 screener, prompt v1 (live calls)", "price_per_min": PRICE}}
    v1 = [c for c in convs if agent_slug(c) == "line-cook-screener-v1" and c.get("origin") != "replay"]
    calls = [to_record(c, ids, "phonic_v1", i + 1) for i, c in enumerate(v1[:20])]
    if a.with_v2:
        setups["phonic_v2"] = {"label": "Phonic-1 screener, prompt v2 (same audio replayed)", "price_per_min": PRICE}
        v2 = [c for c in convs if agent_slug(c) == "line-cook-screener-v2" and c.get("origin") == "replay"]
        calls += [to_record(c, ids, "phonic_v2", i + 1) for i, c in enumerate(v2[:20])]
    out = {"note": "Live calls on Phonic-1. The worker was played by the author from scripted personas.",
           "setups": setups, "calls": calls}
    (OUT / "live_calls.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"wrote {len(calls)} calls to live/out/live_calls.json")


if __name__ == "__main__":
    main()
