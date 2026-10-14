# Chat reply arena

This harness compares ways to keep a chat reply short and correct while the user reads one reply per turn.
Each contender is a settings file of hooks. The harness runs every contender on every prompt in `prompts.json` with headless `claude -p`.

## Run it

```bash
python3 tests/chat_reply_arena/run_arena.py --out /tmp/arena/rep1 --model opus --parallel 8
python3 tests/chat_reply_arena/run_arena.py --out /tmp/arena/rep2 --model opus --parallel 8
python3 tests/chat_reply_arena/score_arena.py --runs /tmp/arena --judge-model sonnet
```

Each run gets a fresh `--session-id`, an empty `CLAUDE_CONFIG_DIR`, `--setting-sources ""`, and a work folder that holds only copies of `chat_reply_gate.py` and `reply_length_gate.py`.
No user settings, plugins, or instruction files load, so the contender's settings file is the only change between runs.
The agent gets the `Read`, `Grep`, and `Glob` tools. Three prompts ask about the copied gate files and use them.

## Contenders

| Name | Settings |
|---|---|
| A | `chat_reply_gate.py` on UserPromptSubmit and Stop, cap 3 |
| B | A with `MAXIMUM_REWRITES_PER_TURN = 1` |
| C | A, and the Stop block reason carries a draft from a headless Haiku helper |
| D | A stronger UserPromptSubmit reminder with the full rule list, no Stop block |
| E | Baseline reminder plus a MessageDisplay hook, no Stop block |
| F | D's reminder plus E's MessageDisplay hook |
| G-haiku, G-sonnet, G-opus | Baseline reminder plus a `"type": "prompt"` Stop hook on that model, whose reason carries a rewrite |

The MessageDisplay hook in E and F holds each streamed batch, runs `reply_violation` on the whole message, and shows either the message or a Haiku draft that passes `reply_violation`.
The draft changes only the text on screen. The transcript keeps the original, so the next UserPromptSubmit tells the agent what the user saw.

## Metrics

| Metric | How it is measured |
|---|---|
| one reply only | exactly one text message after the last tool result |
| visible words | words in every text message the user saw in the turn, narration included |
| first pass | `reply_violation` on the agent's first text message after the last tool result |
| shown pass | `reply_violation` on the last text message the user saw |
| correct | a Sonnet judge sees the prompt, the key outcome from `prompts.json`, and only the text the user saw, and returns 0 or 1 |
| seconds, cost | wall time of the run, and agent cost plus helper cost in dollars |

Every contender logs what the user saw through a MessageDisplay hook into `display.jsonl`.
In `-p` mode MessageDisplay runs once per message with the full text, and the stream output carries the replaced text, so the scorer reads the original from the log.
