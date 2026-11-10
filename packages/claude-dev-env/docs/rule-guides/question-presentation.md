# Present questions clearly

Full text behind [`rules/question-presentation.md`](../../rules/question-presentation.md).

## A question that stays open

The user may see only the question dialog or the closing line of a reply. Each time a question stays open, send it through the question tool again, with the context inside the question text and each option's effect in its description. A closing line that repeats the question reaches the user with no brief. The `final_reply_gate.py` Stop hook blocks a reply whose last paragraph ends with a question mark, or says a question still stands, when the turn sent no question tool call.

## Codex visual comparisons

For Codex visual comparisons, find Page creation, visualization upload, and Page opening tools. Create the comparison, upload its visualization, and open its Page here before asking. If tools are missing, steps fail, or opening queues, compare in chat before asking. Put inline Visualize references only in final replies. An async acknowledgement or saved visual is context only; wait for and use the submitted answer before dependent work.

## Option cards

When the user asks for option cards, build an Artifact page with the `html-plan:html-plan` skill and follow `~/.claude/docs/templates/html-plan/README.md`. Load the `artifact-capabilities` skill and declare the capability that saves the answer where you can read it. A tap selects a card, a second tap clears it, a picked card shows "Change it" with a notes field, and only Send delivers. After publishing, read the saved answer back before dependent work. If no capability can return the answer, use the native question tool with the same labels.
