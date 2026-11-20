"""Print the bake-off scorecard and write docs/data.json for the demo page.

  python3 -m bakeoff.report                       # synthetic set
  python3 -m bakeoff.report --live live/out/live_calls.json
"""

import argparse
import json
from pathlib import Path

from .criteria import BY_ID, CRITERIA, expected_verdicts, grade
from .scorecard import ROLLOUT, gate, next_step, summarize

ROOT = Path(__file__).resolve().parent.parent


def grader_check(calls):
    """How often the rule grader agrees with the answer key (synthetic only)."""
    agree = total = 0
    misses = []
    for c in calls:
        got, want = grade(c), expected_verdicts(c)
        for k in want:
            total += 1
            if got[k] == want[k]:
                agree += 1
            else:
                misses.append((c["call_id"], k, got[k], want[k]))
    return agree, total, misses


def pct(x):
    return f"{100 * x:.0f}%"


def print_summary(label, s):
    print(f"\n== {label}")
    print(f"  completed screens   {s['completed']}/{s['calls']} ({pct(s['completion_rate'])})")
    print(f"  criteria passed     {s['criteria_pass']}/{s['criteria_judged']} ({pct(s['criteria_pass_rate'])})")
    print(f"  critical failures   {len(s['critical_failures'])} {s['critical_failures'] or ''}")
    print(f"  decision matches    {s['decision_agree']}/{s['decision_total']}")
    print(f"  latency p50 / p90   {s['latency_p50_ms']} / {s['latency_p90_ms']} ms")
    print(f"  cost / completed    ${s['cost_per_completed_screen']}  ({s['minutes']} min, ${s['cost_usd']})")


def run_synthetic():
    data = json.loads((ROOT / "data" / "synthetic_calls.json").read_text())
    setups = data["setups"]
    by_setup = {k: [c for c in data["calls"] if c["setup"] == k] for k in setups}
    summaries = {k: summarize(by_setup[k], setups[k]["price_per_min"]) for k in setups}
    agree, total, misses = grader_check(data["calls"])
    print("SYNTHETIC, ILLUSTRATIVE DATA (not measured on any vendor)")
    print(f"Grader check: rule grader matches the answer key on {agree} of {total} verdicts")
    for k in setups:
        print_summary(setups[k]["label"], summaries[k])
    out = {"mode": "synthetic", "note": data["note"], "grader_check": [agree, total],
           "criteria": [{"id": c.id, "name": c.name, "text": c.text, "critical": c.critical} for c in CRITERIA],
           "setups": {}, "gates": {}, "rollout": ROLLOUT, "calls": []}
    for k in setups:
        out["setups"][k] = {"label": setups[k]["label"], "price_per_min": setups[k]["price_per_min"], **summaries[k]}
    for cand in ("phonic_v1", "phonic_v2"):
        g = gate(summaries[cand], summaries["current"])
        g["recommendation"] = next_step(0, g)
        out["gates"][cand] = g
        print(f"\nGate: {setups[cand]['label']} vs current -> {'GO' if g['go'] else 'HOLD'}")
        for c in g["checks"]:
            print(f"  [{'x' if c['pass'] else ' '}] {c['rule']}  ({c['detail']})")
        print("  " + g["recommendation"])
    for c in data["calls"]:
        v = grade(c)
        out["calls"].append({"call_id": c["call_id"], "setup": c["setup"], "worker": c["worker"],
                             "outcome": c["outcome"], "decision": c["decision"],
                             "expected_decision": c["expected_decision"],
                             "fails": [BY_ID[k].name for k, x in v.items() if x == "fail"],
                             "transcript": c["transcript"]})
    return out


def run_live(path):
    """Live mode: calls pulled from Phonic with Phonic's own eval verdicts (live/pull_calls.py)."""
    data = json.loads(Path(path).read_text())
    errors = [(c["call_id"], k) for c in data["calls"] for k, v in c["verdicts"].items() if v == "error"]
    if errors:
        raise SystemExit(f"Grader returned 'error' on {len(errors)} verdicts; re-run evals first: {errors[:10]}")
    critical = {c.id for c in CRITERIA if c.critical}
    undecided = [(c["call_id"], k) for c in data["calls"] for k, v in c["verdicts"].items() if v == "na" and k in critical]
    if undecided:
        print("Hand-check these undecided verdicts on critical criteria:", undecided)
    out = {"mode": "live", "note": data.get("note", ""), "setups": {}, "gates": {}, "rollout": ROLLOUT,
           "criteria": [{"id": c.id, "name": c.name, "text": c.text, "critical": c.critical} for c in CRITERIA],
           "calls": []}
    for k, cfg in data["setups"].items():
        calls = [c for c in data["calls"] if c["setup"] == k]
        verdicts = {c["call_id"]: c["verdicts"] for c in calls}
        s = summarize(calls, cfg["price_per_min"], verdicts)
        out["setups"][k] = {"label": cfg["label"], "price_per_min": cfg["price_per_min"], **s}
        print_summary(cfg["label"], s)
    if "phonic_v1" in out["setups"] and "phonic_v2" in out["setups"]:
        g = gate(out["setups"]["phonic_v2"], out["setups"]["phonic_v1"])
        g["recommendation"] = next_step(0, g)
        out["gates"]["phonic_v2"] = g
        print("\nGate: prompt v2 vs prompt v1 ->", "GO" if g["go"] else "HOLD")
        for c in g["checks"]:
            print(f"  [{'x' if c['pass'] else ' '}] {c['rule']}  ({c['detail']})")
    for c in data["calls"]:
        out["calls"].append({"call_id": c["call_id"], "setup": c["setup"], "worker": c["worker"],
                             "outcome": c["outcome"], "decision": c["decision"],
                             "expected_decision": c["expected_decision"],
                             "fails": [BY_ID[k].name for k, x in c["verdicts"].items() if x == "fail"],
                             "transcript": c["transcript"]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", help="path to live_calls.json from live/pull_calls.py")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    out = run_live(a.live) if a.live else run_synthetic()
    if not a.no_write:
        name = "live.json" if a.live else "data.json"
        (ROOT / "docs" / name).write_text(json.dumps(out, indent=1, ensure_ascii=False))
        print(f"\nwrote docs/{name}")


if __name__ == "__main__":
    main()
