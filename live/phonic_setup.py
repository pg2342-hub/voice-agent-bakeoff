"""Create the screener agent, the eval prompts, and the extraction schema on Phonic.

  python3 -m live.phonic_setup            # agent v1 + evals + schema
  python3 -m live.phonic_setup --v2       # agent v2 from agent/screener_prompt_v2.md

Writes live/out/ids.json. Safe to re-run: existing agents are upserted by slug.
"""

import argparse
import json
from pathlib import Path

from bakeoff.criteria import CRITERIA
from .phonic import call, project_id

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "live" / "out"
IDS = OUT / "ids.json"

WELCOME = ("Hi, I'm Robin, an AI screener for line cook shifts, and this call is recorded. "
           "It takes about ten minutes. Are you ready to start?")

SCHEMA_FIELDS = [
    {"name": "screen_completed", "type": "bool",
     "description": "True if the screener asked its questions and read back a summary before the call ended."},
    {"name": "years_line_cook", "type": "float",
     "description": "Years the worker said they worked as a line cook. 0 if none."},
    {"name": "has_current_food_handler_card", "type": "bool",
     "description": "True only if the worker said their food handler card is current."},
    {"name": "stations", "type": "string[]", "description": "Kitchen stations the worker named."},
    {"name": "recommendation", "type": "string",
     "description": "approve if at least 1 year as a line cook and a current food handler card, else coach_call. none if the screen did not finish."},
    {"name": "language_at_end", "type": "string", "description": "ISO 639-1 code of the language the call ended in."},
]


def load_ids():
    return json.loads(IDS.read_text()) if IDS.exists() else {}


def save_ids(ids):
    OUT.mkdir(parents=True, exist_ok=True)
    IDS.write_text(json.dumps(ids, indent=1))


def upsert_agent(slug, prompt_file):
    body = {
        "name": slug,
        "slug": slug,
        "phone_number": "assign-automatically",
        "timezone": "America/Los_Angeles",
        "welcome_message": WELCOME,
        "system_prompt": (ROOT / "agent" / prompt_file).read_text(),
        "boosted_keywords": ["food handler card", "saute", "garde manger", "expo", "covers"],
    }
    res = call("PUT", "/agents/upsert", body)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v2", action="store_true")
    a = ap.parse_args()
    ids = load_ids()
    if a.v2:
        ids["agent_v2"] = upsert_agent("line-cook-screener-v2", "screener_prompt_v2.md")
        save_ids(ids)
        print("agent v2 ready:", json.dumps(ids["agent_v2"])[:300])
        return
    ids["agent_v1"] = upsert_agent("line-cook-screener-v1", "screener_prompt_v1.md")
    pid = project_id("main")
    ids["project_id"] = pid
    ids.setdefault("eval_prompts", {})
    for c in CRITERIA:
        if c.id not in ids["eval_prompts"]:
            ids["eval_prompts"][c.id] = call("POST", f"/projects/{pid}/conversation_eval_prompts",
                                             {"name": f"screener-{c.id}", "prompt": c.text})["id"]
    if "schema_id" not in ids:
        ids["schema_id"] = call("POST", "/extraction_schemas", {
            "name": "line-cook-screen",
            "prompt": "Extract the outcome of this line cook screening call.",
            "fields": SCHEMA_FIELDS})["id"]
    save_ids(ids)
    print("ready:", json.dumps(ids, indent=1)[:1200])


if __name__ == "__main__":
    main()
