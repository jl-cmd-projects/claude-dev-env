# Present questions clearly

Brief each ask in chat, repeats too: context, each choice's effect, visuals.

Run gate steps unasked. Card only a job-stopping blocker; note one-item needs under `Noted for you:`. One question per item, no chat list: 2 or 3 choices, each a label and sentence. Reuse labels in brief and picker. Cap a turn's pre-ask chat at 450 words and 15 list or table items; a Claude hook refuses more.

Ask in the tool: Claude `AskUserQuestion`, Codex `request_user_input_async` or `request_user_input`. Honor mode rules; if unusable, ask in chat.

End a user-started session with a card per blocker; after work, while a job runs, a plain-words `In progress:` list, resent on change. A hook enforces it.

**Full text:** [guide](../docs/rule-guides/question-presentation.md); it covers handovers, option cards, Codex visuals.
