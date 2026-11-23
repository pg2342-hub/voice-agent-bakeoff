# Voice agent bake-off

[![CI](https://github.com/pg2342-hub/voice-agent-bakeoff/actions/workflows/ci.yml/badge.svg)](https://github.com/pg2342-hub/voice-agent-bakeoff/actions/workflows/ci.yml)

Demo page: https://pg2342-hub.github.io/voice-agent-bakeoff/

A scorecard for switching a voice screening agent to a new model. The same calls go through the current stack and the new one; every call is graded on yes/no criteria, and a rollout gate decides whether the new setup may take the next step of traffic: replay recorded calls, then 10% of live screens, then 50% after a full week that meets the gate.

The worked example is a staffing marketplace's AI screener for line cook shifts: a worker adds experience in the app, takes a 10 to 15 minute screening call, and the screen ends in "approve" or "coach call with a person". The candidate setup is a speech-to-speech screener on [Phonic-1](https://phonic.ai).

**The demo data is synthetic.** `data/make_synthetic.py` builds 30 workers screened by three setups (current cascaded stack, Phonic-1 prompt v1, the same calls replayed on prompt v2), with faults planted by hand so the scorecard has known answers. Nothing in it was measured on Vapi, Phonic, or any staffing company.

## What it measures

| Line | Why a screening team cares |
|---|---|
| Finished screens | An abandoned screen is a worker who never gets approved for shifts |
| Criteria passed | 10 yes/no rules, 3 of them critical (AI and recording disclosure, no protected-class questions, no promises of approval, shifts or pay) |
| Approve / coach-call matches the reviewer | The screen's real output |
| Response latency p50 / p90 | Slow turns get the agent talked over, or flagged as a bot |
| Cost per finished screen | All minutes, including abandoned calls, times list price, divided by finished screens |

The criteria are written the way Phonic's [Evals Guide](https://docs.phonic.ai/docs/build/agents/evals_guide) asks: binary, observable, one behavior each. Conditional ones ("if the worker asked for a person...") return "not triggered" when the situation never came up, like Phonic's "undecided".

## Results on the synthetic set

| | Current cascaded stack | Phonic-1, prompt v1 | Phonic-1, prompt v2 (replayed) |
|---|---|---|---|
| Finished screens | 27 of 30 | 29 of 30 | 29 of 30 |
| Criteria passed | 224 of 238 | 240 of 244 | 241 of 244 |
| Critical failures | 1 (asked a worker's age) | 1 (promised a shift) | 0 |
| Decision matches reviewer | 25 of 27 | 28 of 29 | 28 of 29 |
| Latency p50 / p90 | 1183 / 1541 ms | 617 / 768 ms | 616 / 768 ms |
| Cost per finished screen | $1.36 | $0.82 | $0.82 |

Gate: prompt v1 is held (one critical failure) even though it wins every other line; after one prompt fix, v2 passes all six gate lines and may move to 10% of live screens. The rule grader matches the answer key on 900 of 900 verdicts.

Prices are list prices: $0.105/min for the current stack, the middle of the Deepgram, OpenAI and ElevenLabs stack in Vapi's own pricing calculator, including Vapi's $0.05/min hosting fee ($0.082 to $0.129/min, [vapi.ai/pricing](https://vapi.ai/pricing)); $0.065/min for Phonic Pro ([phonic.ai/pricing](https://phonic.ai/pricing)). Latency ranges are illustrative. The cost model bills every minute at the list rate, so it ignores Phonic-1's 95% discount on silences longer than 10 seconds and slightly overstates Phonic's cost.

## Live run on Phonic-1

`live/` runs the same scorecard on real calls:

1. `python3 -m live.phonic_setup` creates the screener agent (`agent/screener_prompt_v1.md`), loads the 10 criteria as Phonic eval prompts, and creates an extraction schema for the screen outcome.
2. The 20 scripted callers in `agent/caller_scripts.md` call the agent.
3. `python3 -m live.pull_calls --since <date>` pulls the calls, grades them with Phonic's own evals, extracts the outcome, and `python3 -m bakeoff.report --live live/out/live_calls.json` scores them.
4. After a prompt fix, `python3 -m live.phonic_setup --v2` and `python3 -m live.replay_v2 --since <date>` replay each call's recorded audio through the new prompt, so v1 and v2 are judged on the same callers.

The API key is read from `PHONIC_API_KEY` or `~/.config/phonic/.env` and never stored in the repo.

## Run it

```
python3 -m unittest
python3 -m bakeoff.report          # prints the scorecard, writes docs/data.json
```

No dependencies beyond Python 3.10+.
