# Present questions clearly

Before asking for input, give a short formatted brief in chat. Put the context and the effect of each choice there. Add a visual or artifact only when it helps the decision.

For Codex, when a visual comparison helps, discover callable tools for Page creation, visualization upload, and Page opening. Create the comparison, upload its visualization, and open its Page in the current task before asking. If a tool is unavailable, creation, upload, or opening fails, or opening queues, put the comparison in chat before asking. Inline Visualize references appear only in final replies. Use the user's submitted answer for the decision. An async dispatch acknowledgement or saved visual supplies context only. Wait for the answer before work that depends on it.

Ask one short, self-contained question with two or three clear choices. Use short labels, and keep each supported choice description to one short sentence. Use the same labels in the chat brief, comparison, and picker.

Discover the current session's native question tool and its schema. Claude may expose `AskUserQuestion`.
Codex may expose `request_user_input_async` or `request_user_input`. Follow the tool's mode restrictions.
Put the question in its declared title or question field and choices in its declared string or object fields.
When no native tool is usable, ask the short question and choices in chat.

**Full text:** [`docs/rule-guides/question-presentation.md`](../docs/rule-guides/question-presentation.md)
