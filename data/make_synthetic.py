"""Build the synthetic bake-off set: the same 30 workers screened by three setups.

SYNTHETIC, ILLUSTRATIVE DATA. Nothing here was measured on Vapi, Phonic, or
Instawork. The faults are planted by hand so the scorecard has known answers
to find. Setups:
  current   - a cascaded stack (speech-to-text, LLM, text-to-speech)
  phonic_v1 - a speech-to-speech screener, first prompt
  phonic_v2 - the same calls replayed after one prompt fix

Prices are list prices (see README for sources); latency ranges are
illustrative, chosen from each vendor's public latency claims.

Run: python3 data/make_synthetic.py  ->  data/synthetic_calls.json
"""

import json
import random
from pathlib import Path

OUT = Path(__file__).with_name("synthetic_calls.json")

# name, qualified (expected decision approve), asks_language, asks_human, long_answers
PERSONAS = [
    ("W01", True, None, False, False), ("W02", True, None, False, True),
    ("W03", False, None, False, False), ("W04", True, "es", False, False),
    ("W05", True, None, False, True), ("W06", False, None, True, False),
    ("W07", True, None, False, False), ("W08", True, None, False, True),
    ("W09", False, None, False, True), ("W10", True, "es", False, True),
    ("W11", True, None, False, False), ("W12", False, None, False, False),
    ("W13", True, None, True, False), ("W14", True, None, False, True),
    ("W15", False, "es", False, False), ("W16", True, None, False, False),
    ("W17", False, None, False, False), ("W18", True, None, False, True),
    ("W19", True, None, False, False), ("W20", False, None, True, False),
    ("W21", True, "es", False, False), ("W22", True, None, False, False),
    ("W23", False, None, False, True), ("W24", True, None, False, False),
    ("W25", False, None, False, False), ("W26", True, None, False, False),
    ("W27", True, None, False, False), ("W28", False, None, False, False),
    ("W29", True, None, False, False), ("W30", False, None, False, False),
]

# Planted faults per setup: {worker: {fault, ...}}
FAULTS = {
    "current": {
        "W02": {"cutoff", "abandon"}, "W05": {"cutoff"}, "W08": {"cutoff", "abandon"},
        "W09": {"cutoff"}, "W14": {"cutoff", "abandon"}, "W18": {"cutoff"},
        "W04": {"no_switch"}, "W21": {"no_switch"},
        "W12": {"protected"},
        "W16": {"skip_card"}, "W27": {"skip_card"},
        "W19": {"no_readback"}, "W24": {"no_readback"},
        "W03": {"wrong_decision"}, "W26": {"wrong_decision"},
        "W20": {"no_coach"},
    },
    "phonic_v1": {
        "W23": {"cutoff", "abandon"},
        "W11": {"promise"},
        "W22": {"skip_stations"},
        "W29": {"no_readback"},
        "W17": {"wrong_decision"},
    },
}
# v2 = same calls replayed after adding "never tell the worker they are approved"
FAULTS["phonic_v2"] = {w: set(f) for w, f in FAULTS["phonic_v1"].items()}
FAULTS["phonic_v2"]["W11"].discard("promise")

SETUPS = {
    # price per minute (USD, list), latency range ms (illustrative)
    "current": {"label": "Current cascaded stack", "price_per_min": 0.105, "latency": (850, 1600)},
    "phonic_v1": {"label": "Phonic-1 screener, prompt v1", "price_per_min": 0.065, "latency": (450, 800)},
    "phonic_v2": {"label": "Phonic-1 screener, prompt v2 (replayed)", "price_per_min": 0.065, "latency": (450, 800)},
}


def turn(role, text, **kw):
    return {"role": role, "text": text, **kw}


def build_call(setup, persona, faults, rng):
    wid, qualified, lang, asks_human, long_answers = persona
    t = []
    if "no_disclosure" in faults:
        t.append(turn("agent", "Hi! Thanks for calling about line cook shifts. Let's get started."))
    else:
        t.append(turn("agent", "Hi, I'm an AI screener for line cook shifts, and this call is recorded. Ready to start?"))
    t.append(turn("worker", "Yes, ready."))
    t.append(turn("agent", "How long have you worked as a line cook?"))
    years = "three years" if qualified else "a few months, mostly dishwashing"
    t.append(turn("worker", f"About {years}." + (" Let me think, at my last place I also covered..." if long_answers else ""),
                  cut_off="cutoff" in faults))
    if "abandon" in faults:
        t.append(turn("agent", "Okay, next question."))
        return t, "abandoned"
    if "skip_stations" not in faults:
        t.append(turn("agent", "Which stations have you worked, like grill, saute or prep?"))
        t.append(turn("worker", "Grill and prep." if qualified else "Mostly prep."))
    if "protected" in faults:
        t.append(turn("agent", "And how old are you?"))
        t.append(turn("worker", "Is that needed?"))
    if "skip_card" not in faults:
        t.append(turn("agent", "Do you have a current food handler card?"))
        t.append(turn("worker", "Yes, it's current." if qualified else "No, not yet."))
    if asks_human:
        t.append(turn("worker", "Can I talk to a real person instead?", asks_human=True))
        if "no_coach" in faults:
            t.append(turn("agent", "I can help you with everything today."))
        else:
            t.append(turn("agent", "Of course. You can book a coach call with a person after this, or we can finish now."))
        t.append(turn("worker", "Let's finish now."))
    if "promise" in faults:
        t.append(turn("agent", "Great, you're approved and I can guarantee you'll get the Saturday shift."))
    agent_lang = "en"
    if lang:
        t.append(turn("worker", "¿Podemos seguir en español?", asks_language=lang))
        agent_lang = "en" if "no_switch" in faults else lang
    if "no_readback" not in faults:
        if agent_lang == "es":
            t.append(turn("agent", "Claro. Para confirmar, usted tiene experiencia en cocina y respondió sobre su tarjeta.", lang="es"))
        else:
            t.append(turn("agent", "To confirm, here is what I have about your experience.", lang="en"))
        t.append(turn("worker", "Sí." if lang else "Yes, that's right."))
    t.append(turn("agent", "Gracias, ya terminamos." if agent_lang == "es" else "Thanks, that's everything. You'll see an update in the app.",
                  lang=agent_lang))
    return t, "completed"


def main():
    calls = []
    for setup, cfg in SETUPS.items():
        family = "phonic" if setup.startswith("phonic") else setup
        for p in PERSONAS:
            wid, qualified = p[0], p[1]
            # same seed for v1 and v2 so the replay keeps each call's timing
            rng = random.Random(f"{family}-{wid}")
            faults = FAULTS[setup].get(wid, set())
            transcript, outcome = build_call(setup, p, faults, rng)
            n_agent = sum(1 for x in transcript if x["role"] == "agent")
            lo, hi = cfg["latency"]
            latencies = [rng.randint(lo, hi) for _ in range(n_agent)]
            duration = rng.randint(660, 840) if outcome == "completed" else rng.randint(180, 360)
            expected = "approve" if qualified else "coach_call"
            if outcome != "completed":
                decision = None
            elif "wrong_decision" in faults:
                decision = "coach_call" if qualified else "approve"
            else:
                decision = expected
            calls.append({
                "call_id": f"{setup}-{wid}",
                "setup": setup,
                "worker": wid,
                "position": "line cook",
                "outcome": outcome,
                "duration_s": duration,
                "latencies_ms": latencies,
                "interruptions_count": rng.randint(0, 2),
                "decision": decision,
                "expected_decision": expected,
                "planted_faults": sorted(faults),
                "transcript": transcript,
            })
    payload = {"note": "Synthetic, illustrative data. Not measured on any vendor.",
               "setups": SETUPS, "calls": calls}
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print(f"wrote {len(calls)} calls to {OUT}")


if __name__ == "__main__":
    main()
