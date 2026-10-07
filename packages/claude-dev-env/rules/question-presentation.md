# Present questions clearly

Before asking, give a short formatted chat brief with context and each choice's effect. Add helpful visuals or artifacts.

Ask one short, self-contained question with two or three choices. Give each a short label and one short sentence. Reuse labels in the brief, comparison, and picker.

Find the native question tool and schema. Claude may use `AskUserQuestion`; Codex may use `request_user_input_async` or `request_user_input`. Honor mode rules. Put the question in its title or question field and choices in string or object fields. If unusable, ask in chat.

When the user asks for option cards, or for a Codex visual comparison, read the full text first.

**Full text:** [`docs/rule-guides/question-presentation.md`](../docs/rule-guides/question-presentation.md).
