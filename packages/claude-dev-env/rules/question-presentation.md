# Present questions clearly

Before each ask, repeats too, brief in chat: context, each choice's effect, visuals.

One question per item, no chat list: two or three choices, each a label and sentence. Reuse labels in brief, comparison, picker. Cap a turn's pre-question chat at 450 words and 15 list or table items; a Claude hook refuses more.

Question tools hold question and choices: Claude `AskUserQuestion`, Codex `request_user_input_async` or `request_user_input`. Honor mode rules; if unusable, ask in chat.

End a user-started session with a card per open item and, while work runs, a plain-words `In progress:` list, one per task. A Claude hook holds the stop.

**Full text:** [`~/.claude/docs/rule-guides/question-presentation.md`](../docs/rule-guides/question-presentation.md), for handovers, option cards, or Codex visual comparison.
