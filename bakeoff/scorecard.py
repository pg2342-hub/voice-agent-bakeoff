"""Scorecard and rollout gate for a voice-agent bake-off.

Compares a candidate setup against the current one on the same calls and
says whether the candidate may take the next step of traffic
(replay -> 10% live -> 50% live).
"""

import math
from statistics import median

from .criteria import CRITERIA, FAIL, PASS, grade


def p90(values):
    if not values:
        return None
    s = sorted(values)  # nearest-rank percentile
    k = max(0, math.ceil(0.9 * len(s)) - 1)
    return s[k]


def summarize(calls, price_per_min, verdicts=None):
    """Metrics for one setup. `verdicts` maps call_id -> {criterion: verdict};
    if missing, the rule grader is used (synthetic mode)."""
    verdicts = verdicts or {c["call_id"]: grade(c) for c in calls}
    n = len(calls)
    completed = [c for c in calls if c["outcome"] == "completed"]
    lat = [x for c in calls for x in c["latencies_ms"]]
    minutes = sum(c["duration_s"] for c in calls) / 60
    cost = minutes * price_per_min
    passes = fails = 0
    per_crit = {}
    failing_calls = {}
    for cr in CRITERIA:
        p = f = na = 0
        for c in calls:
            v = verdicts[c["call_id"]][cr.id]
            if v == PASS:
                p += 1
            elif v == FAIL:
                f += 1
                failing_calls.setdefault(cr.id, []).append(c["call_id"])
            else:
                na += 1
        per_crit[cr.id] = {"pass": p, "fail": f, "na": na}
        passes += p
        fails += f
    critical = [(cr.id, cid) for cr in CRITERIA if cr.critical for cid in failing_calls.get(cr.id, [])]
    decided = [c for c in completed if c.get("expected_decision") is not None]
    agree = sum(1 for c in decided if c["decision"] == c["expected_decision"])
    return {
        "calls": n,
        "completed": len(completed),
        "completion_rate": len(completed) / n if n else 0,
        "criteria_pass": passes,
        "criteria_judged": passes + fails,
        "criteria_pass_rate": passes / (passes + fails) if passes + fails else 0,
        "critical_failures": critical,
        "decision_agree": agree,
        "decision_total": len(decided),
        "latency_p50_ms": round(median(lat)) if lat else None,
        "latency_p90_ms": p90(lat),
        "minutes": round(minutes, 1),
        "cost_usd": round(cost, 2),
        "cost_per_completed_screen": round(cost / len(completed), 3) if completed else None,
        "per_criterion": per_crit,
        "failing_calls": failing_calls,
    }


DECISION_BAR = 0.90


def gate(candidate, current):
    """Rollout gate: every line must hold for the candidate to take the next traffic step."""
    checks = [
        ("No critical failures (disclosure, protected-class questions, promises)",
         not candidate["critical_failures"],
         f"{len(candidate['critical_failures'])} critical failure(s)"),
        ("Completion rate at least the current stack's",
         candidate["completion_rate"] >= current["completion_rate"],
         f"{candidate['completed']}/{candidate['calls']} vs {current['completed']}/{current['calls']}"),
        ("Criteria pass rate at least the current stack's",
         candidate["criteria_pass_rate"] >= current["criteria_pass_rate"],
         f"{candidate['criteria_pass']}/{candidate['criteria_judged']} vs {current['criteria_pass']}/{current['criteria_judged']}"),
        (f"Approve/coach-call decision matches the reviewer on at least {int(DECISION_BAR*100)}% of completed screens",
         candidate["decision_total"] > 0 and candidate["decision_agree"] / candidate["decision_total"] >= DECISION_BAR,
         f"{candidate['decision_agree']}/{candidate['decision_total']}"),
        ("p90 response latency no worse than the current stack's",
         candidate["latency_p90_ms"] is not None and current["latency_p90_ms"] is not None
         and candidate["latency_p90_ms"] <= current["latency_p90_ms"],
         f"{candidate['latency_p90_ms']} ms vs {current['latency_p90_ms']} ms"),
        ("Cost per completed screen no higher than the current stack's",
         candidate["cost_per_completed_screen"] is not None and current["cost_per_completed_screen"] is not None
         and candidate["cost_per_completed_screen"] <= current["cost_per_completed_screen"],
         f"${candidate['cost_per_completed_screen']} vs ${current['cost_per_completed_screen']}"),
    ]
    ok = all(c[1] for c in checks)
    return {"go": ok, "checks": [{"rule": r, "pass": p, "detail": d} for r, p, d in checks]}


ROLLOUT = ["Replay recorded calls", "10% of live screens", "50% of live screens"]


def next_step(stage_index, gate_result):
    """stage_index: 0 = replay, 1 = 10%, 2 = 50%. Returns the recommendation text."""
    if not gate_result["go"]:
        return f"HOLD at '{ROLLOUT[stage_index]}': fix the failing gate lines and re-run on the same calls."
    if stage_index + 1 < len(ROLLOUT):
        extra = " after one full week at this level meets the gate" if stage_index >= 1 else ""
        return f"GO: move from '{ROLLOUT[stage_index]}' to '{ROLLOUT[stage_index + 1]}'{extra}."
    return "GO: hold at 50% and plan the full cutover with the customer."
