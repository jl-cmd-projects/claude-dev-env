# Present questions clearly

Before asking for input, give a short formatted brief in chat. Put the context and the effect of each choice there. Add a visual or artifact only when it helps the decision.

Ask one short, self-contained question with two or three clear choices. Use short labels, and keep each supported choice description to one short sentence. Use the same labels in the chat brief and the picker.

Discover the current session's native question tool and its schema. Claude may expose `AskUserQuestion`.
Codex may expose `request_user_input_async` or `request_user_input`. Follow the tool's mode restrictions.
Put the question in its declared title or question field and choices in its declared string or object fields.
When no native tool is usable, ask the short question and choices in chat.
