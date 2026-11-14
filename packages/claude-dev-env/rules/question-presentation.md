# Present questions clearly

Before every ask, repeats too, give a short chat brief with context, each choice's effect, and helpful visuals.

Ask one short question per item, never a chat list, with two or three choices, each a short label and sentence. Reuse labels in brief, comparison, and picker. Keep the turn's chat text before a question to 450 words and 15 list or table items; a Claude hook refuses more.

Find the native question tool. Claude may use `AskUserQuestion`; Codex may use `request_user_input_async` or `request_user_input`. Honor mode rules. Put the question and choices in its fields. If unusable, ask in chat.

When the user asks for option cards or a Codex visual comparison, read the full text first.

**Full text:** [`~/.claude/docs/rule-guides/question-presentation.md`](../docs/rule-guides/question-presentation.md).
