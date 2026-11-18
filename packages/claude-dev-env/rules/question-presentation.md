# Present questions clearly

Before every ask, repeats too, brief in chat: context, each choice's effect, visuals.

One question per item, no chat list: two or three choices, each a label and sentence. Reuse labels in brief, comparison, picker. Cap a turn's pre-question chat at 450 words and 15 list or table items; a Claude hook refuses more.

Question tools: Claude `AskUserQuestion`, Codex `request_user_input_async` or `request_user_input`. Honor mode rules. Its fields hold question and choices; if unusable, ask in chat.

End a user-started session with a card per open item. While work is in progress, end on an `In progress:` footer, one plain-words list item per piece of running work; with nothing running, end with no closing line. A Claude hook holds the stop.

Read the full text for a step handover, option cards, or Codex visual comparison.

**Full text:** [`~/.claude/docs/rule-guides/question-presentation.md`](../docs/rule-guides/question-presentation.md).
