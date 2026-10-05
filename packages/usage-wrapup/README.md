# usage-wrapup

A Claude Code mod. When your plan usage gets low, it tells every running agent to wrap up — so you don't get cut off mid-task with half-edited files and no handoff.

## What it does

- Watches your rate-limit windows (5-hour, weekly, spend limit).
- When any window has **5% or less left** (configurable), every tool result — in the main agent **and** in subagents — carries a note telling the model to:
  1. start no new work,
  2. finish or safely pause the current step,
  3. write a short handoff (done / left / next step),
  4. arm one wake for just after the reset time, such as `send_later` to its own session or a `create_trigger` routine, so the paused work resumes without a person,
  5. stop and answer.
- Shows `⚠ N% left — wrapping up` in the status line and a one-time toast.
- Compacts the conversation when usage is nearly gone. This happens when the 5-hour window is 97% used or more, or the weekly window is 99% used or more.
  - It compacts when a turn ends, so the next turn starts with a smaller context.
  - It compacts once per window. When the window resets, it can compact again.
  - The summary keeps the current task, its state, the files it touched, and the next steps.
  - It skips a turn you interrupted, and it skips subagent turns.

Only works on a Claude subscription (Pro/Max/Team), where Claude Code gets rate-limit data.

## Install

```sh
git clone https://github.com/DaKev/usage-wrapup ~/claude-mods/usage-wrapup
claude --plugin-dir ~/claude-mods/usage-wrapup
```

## Configure

`/config` has three options:

- **Wrap-up threshold (% left)**. Default `5`.
- **Compact at 5-hour usage (% used)**. Default `97`.
- **Compact at weekly usage (% used)**. Default `99`.

## Test

```sh
claude plugin validate .
claude plugin test .
```

MIT license. See [LICENSE](LICENSE).
