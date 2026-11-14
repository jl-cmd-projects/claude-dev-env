# Present questions clearly

Before every ask, repeats included, give a short formatted chat brief with context and each choice's effect. Add helpful visuals or artifacts.

Ask one short, self-contained question with two or three choices. Give each a short label and one short sentence. Reuse labels in the brief, comparison, and picker.

Find the native question tool and schema. Claude may use `AskUserQuestion`; Codex may use `request_user_input_async` or `request_user_input`. Honor mode rules. Put the question in its title or question field and choices in string or object fields. If unusable, ask in chat.

To hand the user a step, or when asked for option cards or a Codex visual comparison, read the full text first.

**Full text:** [`~/.claude/docs/rule-guides/question-presentation.md`](../docs/rule-guides/question-presentation.md).
