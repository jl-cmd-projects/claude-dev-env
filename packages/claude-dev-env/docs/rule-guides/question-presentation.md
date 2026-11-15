# Present questions clearly

Full text behind [`rules/question-presentation.md`](../../rules/question-presentation.md).

## A question that stays open

The user may see only the question dialog or the closing line of a reply. Each time a question stays open, send it through the question tool again, with the context inside the question text and each option's effect in its description. A closing line that repeats the question reaches the user with no brief. The `final_reply_gate.py` Stop hook blocks a reply whose last paragraph ends with a question mark, or says a question still stands, when the turn sent no question tool call.

## A step that waits on the user

An item can close while it sits on a list. Before a reply or a sent file says something waits on the user, read the live state of each item it shows as open: the pull request, the session, the setting, or the log. Drop each one that is done. Send each step that still stands open as its own question through the question tool: one short sentence on what the step does, with the command block to paste or the link to open inside the question. Where the host has no question tool, give each step its own short paragraph with its block or link.

Remove completed items from the task list before the turn ends, so the list shows only open work.

The `open_tasks_stop_gate.py` Stop hook holds the turn once when completed items sit beside open ones on the session's own task list. It also holds the turn once when the closing reply, or a Markdown, text, or HTML file the turn sent, says something waits on the user and the turn ran no read call or sent no question tool call. It also holds the turn once when the closing reply lists 3 or more open items, such as a deferred list or next steps, under a lead that names open work, and the turn sent no question tool call. The hold tells the agent to act on each item it can settle and to send each item that needs the user's judgment through the question tool. It holds the turn once, too, when the closing reply promises the user a later report that no typed prompt asked for. A held reply's text counts toward the limits below, so the first question call after such a hold can be refused once; the same call sent again passes.

## Several items, one question at a time

When the user has several items to review or decide, such as test cases, findings, or a plan's steps, do not post the list in chat and ask about it as a whole. Send the first item through the question tool with a short brief: its context and each choice's effect. Send the next item after the user answers. A long list in chat makes the user read everything at once, and the user asked for the items bit by bit.

The limit is 450 words and 15 list or table items of chat text before a question, counted from the start of the question's turn. A turn starts at a message the user types, at an answer or refusal of an earlier question, or at the first input after the previous turn ends, so text from an earlier turn never counts. A Stop hook that holds a reply keeps the turn open, so that reply's text counts. Each bullet or numbered line is one item, and each table row below the header is one item. Lines inside a code fence are not items. On Claude, the `question_brief_gate.py` PreToolUse hook refuses an `AskUserQuestion` call past either limit and names the limit it passed. The hook reads only the last 1 MB of the transcript, so a long review followed by more than 1 MB of tool output in the same turn is not seen. The text has already posted by then, so do not repeat it. Shorten the brief to the context and each choice's effect, or split the question and ask about one item now.

## Codex visual comparisons

For Codex visual comparisons, find Page creation, visualization upload, and Page opening tools. Create the comparison, upload its visualization, and open its Page here before asking. If tools are missing, steps fail, or opening queues, compare in chat before asking. Put inline Visualize references only in final replies. An async acknowledgement or saved visual is context only; wait for and use the submitted answer before dependent work.

## Option cards

When the user asks for option cards, build an Artifact page with the `html-plan:html-plan` skill and follow `~/.claude/docs/templates/html-plan/README.md`. Load the `artifact-capabilities` skill and declare the capability that saves the answer where you can read it. A tap selects a card, a second tap clears it, a picked card shows "Change it" with a notes field, and only Send delivers. After publishing, read the saved answer back before dependent work. If no capability can return the answer, use the native question tool with the same labels.
