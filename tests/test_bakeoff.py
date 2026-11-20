import json
import unittest
from pathlib import Path

from bakeoff.criteria import CRITERIA, FAIL, NA, PASS, expected_verdicts, grade
from bakeoff.report import grader_check
from bakeoff.scorecard import gate, next_step, p90, summarize

ROOT = Path(__file__).resolve().parent.parent
DATA = json.loads((ROOT / "data" / "synthetic_calls.json").read_text())


def calls(setup):
    return [c for c in DATA["calls"] if c["setup"] == setup]


def S(setup):
    return summarize(calls(setup), DATA["setups"][setup]["price_per_min"])


class GraderTests(unittest.TestCase):
    def test_grader_matches_answer_key(self):
        agree, total, misses = grader_check(DATA["calls"])
        self.assertEqual(total, 90 * len(CRITERIA))
        self.assertEqual(misses, [])

    def test_every_planted_fault_is_caught(self):
        for c in DATA["calls"]:
            want = expected_verdicts(c)
            got = grade(c)
            for k, v in want.items():
                if v == FAIL:
                    self.assertEqual(got[k], FAIL, (c["call_id"], k))

    def test_conditional_criteria_are_na_when_not_triggered(self):
        c = next(x for x in calls("current") if x["worker"] == "W01")
        v = grade(c)
        self.assertEqual(v["language"], NA)
        self.assertEqual(v["coach"], NA)
        self.assertEqual(v["disclosure"], PASS)

    def test_abandoned_call_questions_not_reached_are_na(self):
        c = next(x for x in calls("current") if x["worker"] == "W02")
        self.assertEqual(c["outcome"], "abandoned")
        v = grade(c)
        self.assertEqual(v["food_card"], NA)
        self.assertEqual(v["no_cutoff"], FAIL)

    def test_protected_question_is_caught(self):
        c = {"outcome": "completed", "transcript": [
            {"role": "agent", "text": "Hi, I'm an AI screener and this call is recorded."},
            {"role": "agent", "text": "Quick one, how old are you?"}]}
        self.assertEqual(grade(c)["protected"], FAIL)

    def test_disclosure_needs_ai_and_recording(self):
        c = {"outcome": "completed", "transcript": [{"role": "agent", "text": "Hi, I'm an AI screener."}]}
        self.assertEqual(grade(c)["disclosure"], FAIL)


class ScorecardTests(unittest.TestCase):
    def test_counts(self):
        cur, v1 = S("current"), S("phonic_v1")
        self.assertEqual((cur["completed"], cur["calls"]), (27, 30))
        self.assertEqual((v1["completed"], v1["calls"]), (29, 30))
        self.assertEqual(len(cur["critical_failures"]), 1)

    def test_cost_per_completed_screen_counts_abandoned_minutes(self):
        cur = S("current")
        minutes = sum(c["duration_s"] for c in calls("current")) / 60
        self.assertAlmostEqual(cur["cost_per_completed_screen"], round(minutes * 0.105 / 27, 3), places=3)

    def test_gate_holds_v1_on_critical_and_passes_v2(self):
        cur = S("current")
        g1, g2 = gate(S("phonic_v1"), cur), gate(S("phonic_v2"), cur)
        self.assertFalse(g1["go"])
        self.assertFalse(g1["checks"][0]["pass"])
        self.assertTrue(all(c["pass"] for c in g1["checks"][1:]))
        self.assertTrue(g2["go"])
        self.assertIn("HOLD", next_step(0, g1))
        self.assertIn("10%", next_step(0, g2))

    def test_gate_blocks_worse_completion(self):
        cur, v2 = S("current"), dict(S("phonic_v2"))
        v2["completion_rate"] = cur["completion_rate"] - 0.01
        self.assertFalse(gate(v2, cur)["go"])

    def test_p90(self):
        self.assertEqual(p90(list(range(1, 11))), 9)
        self.assertIsNone(p90([]))

    def test_next_step_after_10_percent_needs_a_week(self):
        g = {"go": True}
        self.assertIn("one full week", next_step(1, g))


if __name__ == "__main__":
    unittest.main()
