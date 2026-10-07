# Present questions clearly

Before asking, give a short formatted chat brief with context and each choice's effect. Add helpful visuals or artifacts.

For Codex visual comparisons, find Page creation, visualization upload, and Page opening tools. Create the comparison, upload its visualization, and open its Page here before asking. If tools are missing, steps fail, or opening queues, compare in chat before asking. Put inline Visualize references only in final replies. An async acknowledgement or saved visual is context only; wait for and use the submitted answer before dependent work.

Ask one short, self-contained question with two or three choices. Give each a short label and one short sentence. Reuse labels in the brief, comparison, and picker.

Find the native question tool and schema. Claude may use `AskUserQuestion`; Codex may use `request_user_input_async` or `request_user_input`. Honor mode rules. Put the question in its title or question field and choices in string or object fields. If unusable, ask in chat.

When the user asks for option cards, build an Artifact page from `~/.claude/docs/templates/artifact-page/template.html` and follow its README house rules. Load the `artifact-capabilities` skill and declare the capability that saves the answer where you can read it. A tap selects a card, a second tap clears it, a picked card shows "Change it" with a notes field, and only Send delivers. After publishing, read the saved answer back before dependent work. If no capability can return the answer, use the native question tool with the same labels.
