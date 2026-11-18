# Present questions clearly

Full text behind [`rules/question-presentation.md`](../../rules/question-presentation.md).

## A question that stays open

The user may see only the question dialog or the closing line of a reply. Each time a question stays open, send it through the question tool again, with the context inside the question text and each option's effect in its description. A closing line that repeats the question reaches the user with no brief. The `final_reply_gate.py` Stop hook blocks a reply whose last paragraph ends with a question mark, or says a question still stands, when the turn sent no question tool call.

## A step that waits on the user

An item can close while it sits on a list. Before a reply or a sent file says something waits on the user, read the live state of each item it shows as open: the pull request, the session, the setting, or the log. Drop each one that is done. Send each step that still stands open as its own question through the question tool: one short sentence on what the step does, with the command block to paste or the link to open inside the question. Where the host has no question tool, give each step its own short paragraph with its block or link.

Remove completed items from the task list before the turn ends, so the list shows only open work.

## Questions stay out of files and pages

A file or page the user reads can carry the context for a question. The question itself goes through the question tool, where the user answers it. On Claude, the `sent_file_question_gate.py` PreToolUse hook refuses a `SendUserFile` call or an `Artifact` page publish when a Markdown, text, or HTML file it sends asks the user something: a "Questions for you" or "Decisions needed" section, or a sentence that ends with a question mark and names the reader, asks for a go-ahead, or offers a choice. The refusal quotes the question. Ask it through the question tool, remove it from the file, and send the file again. A page that collects the answer itself, such as option cards, declares the `db` or `artifact` capability that saves the answer, and the hook lets it through.

The `open_tasks_stop_gate.py` Stop hook holds the turn once when completed items sit beside open ones on the session's own task list. It also holds the turn once when the closing reply, or a Markdown, text, or HTML file the turn sent, says something waits on the user and the turn ran no read call or sent no question tool call. It also holds the turn once when the closing reply lists 3 or more open items, such as a deferred list or next steps, under a lead that names open work, and the turn sent no question tool call. The hold tells the agent to act on each item it can settle and to send each item that needs the user's judgment through the question tool. It holds the turn once, too, when the closing reply promises the user a later report that no typed prompt asked for. A held reply's text counts toward the limits below, so the first question call after such a hold can be refused once; the same call sent again passes.

## Several items, one question at a time

When the user has several items to review or decide, such as test cases, findings, or a plan's steps, do not post the list in chat and ask about it as a whole. Send the first item through the question tool with a short brief: its context and each choice's effect. Send the next item after the user answers. A long list in chat makes the user read everything at once, and the user asked for the items bit by bit.

The limit is 450 words and 15 list or table items of chat text before a question, counted from the start of the question's turn. A turn starts at a message the user types, at an answer or refusal of an earlier question, or at the first input after the previous turn ends, so text from an earlier turn never counts. A Stop hook that holds a reply keeps the turn open, so that reply's text counts. Each bullet or numbered line is one item, and each table row below the header is one item. Lines inside a code fence are not items. On Claude, the `question_brief_gate.py` PreToolUse hook refuses an `AskUserQuestion` call past either limit and names the limit it passed. The hook reads only the last 1 MB of the transcript, so a long review followed by more than 1 MB of tool output in the same turn is not seen. The text has already posted by then, so do not repeat it. Shorten the brief to the context and each choice's effect, or split the question and ask about one item now.

## The closing round

A session the user started ends with a round of question cards on what it leaves open. While work is still in progress, a reply after work ends with the In progress footer, so a user who reads the session on a phone sees what is running:

```
In progress:
- I am fixing the list reader in pull request 8801. I am waiting for the last tests to finish.
- I am watching the discount ledger run. At 9:00 I will open its pull request if the run passes.
```

Write one list item per piece of running work, in first person and plain words, in about 25 words at most. Give background work one short clause that says what it does for the user. Leave out task numbers, commit ids, agent or session names, file paths, and tool or process words such as agent, subagent, shell, monitor, lint, cron, wake, push, or branch. Spell out each short form, so PR becomes pull request. A pull request number and the names of the user's own tools and projects may stay. When nothing is in progress and no background work runs, the reply ends with no closing line. On Claude, the `closing_question_round_gate.py` Stop hook holds the stop until the cards or the footer follow.

### What the gate checks

The gate reads the stretch: the session's records after the last question tool call that reached the user, then the payload's `last_assistant_message`. Claude Code runs Stop hooks before it writes the closing reply to the transcript, so the payload holds the newest text. When the transcript already ends with that text, it is read once: its last assistant record, question calls left aside, ends in the same text. A text that sits before a later work call is an older reply, so the payload text is read as new. The closing reply is the newest text after the last work call. Work is in progress when the session's own task list holds a task in progress, or the payload's `background_tasks` is a non-empty list, object, or string. The list is the task store under `~/.claude/tasks/<session id>/`, or the task calls in the transcript when no store exists. It holds in four cases.

1. The stretch holds an open-item line. The reason quotes the lines. The footer does not release this hold. The footer is cut off the closing reply first, so a marker such as "waiting" or "blocked" inside the footer does not count. While background work runs, this check is skipped.
2. The closing reply ends with the old line `Open items: none.` while a task is in progress. A side question does not close the goal the tasks track, so a "nothing is open" card does not release this hold.
3. The stretch holds work, work is in progress, and the closing reply ends with no footer. Work is any tool call of the main thread other than a question call: an edit, a shell command, a read, or a subagent. Work counts from the last reply in the stretch that ended with the footer.
4. The footer leaves out a task in progress. The gate matches each task by the words of its subject that name the thing worked on. It drops verbs such as fix and watch, and words only an agent uses, such as lint and wake. When another open task shares a word, it uses only the words unique to the task. A footer word matches on its first five letters. The reason names each task it misses, with its key words in brackets.

The footer and declaration reasons list each task in progress with its key words and say how to write the footer in plain words. They carry no example sentence to copy. A stretch with no work passes with no footer, so a chat-only answer needs none, though a footer it writes is still checked. Nothing in progress passes with no closing line. A reply that ends with the footer closes the work before it, so a later turn of chat only needs no footer. An open-item line written before that reply still holds.

Fences, HTML blocks, quoted paragraphs, code spans, and indented code blocks are left out. An indented code block is a run of lines indented by four spaces or a tab after a blank line, outside a list item. Tool inputs, tool results, and thinking are never read.

Each paragraph is matched with its single line breaks folded to spaces, so a marker split across a soft line break, such as "out of" and "scope" on the next line, still counts. The reason quotes the line, or the lines the marker spans. A line that holds a deferral, uncertainty, or judgment marker is an open-item line. Markers include "deferred", "follow-up", "parked", "out of scope", "for later", "later pull request", "separate PR", "pending", "TODO", "skipped", "blocked", "not run", "known gap", "open question", "not sure", "I assumed", "unverified", "untested", "did not test", "could not confirm", "not yet implemented", "your call", "up to you", "you may want to", "your judgment", "need your input", and "waiting on you". A line of chat text that ends with a question mark is an open-item line too. A marker reads as a whole word, and one to three underscores around it read as emphasis, so `_untested_` and `__untested__` count, and `retry_untested_flag` and `retry__untested__flag` do not. A marker inside a file name with a short lower-case extension, such as `todo.md`, or inside a path of two or more names that ends in a slash or a file name, such as `docs/pending/`, does not count either. A marker joined to another word, such as `skipped/untested`, and a marker of two or more words, such as `not tested`, still count. The module docstring of `closing_question_round_open_items.py` lists every marker. A negation does not cancel a marker, so "Nothing is deferred." is held. That hold costs one extra card.

The footer counts when the closing reply ends with a line that holds only `In progress:`, alone or in one bold mark, followed by one or more `-`, `*`, or `+` list items, and nothing else after them except indented lines that carry an item on. The heading in a list item, in a fence, or with more words on its line does not count, and neither does a footer with prose after it.

### The stretch

A call reached the user when the transcript holds its tool result, matched by `tool_use_id`, and that result is no error. A call a hook refused, a call that errored, and a call with no result yet do not end the stretch, so send the call again after a refusal. A later turn that a task notification starts does not clear what an earlier turn left open. Answers come back in the same turn, so act on them at once. An open-item line written after the cards starts a new stretch, and it needs its own cards. Work after the cards needs the footer again while work is in progress.

### Sessions the gate leaves alone

- A subagent, and a Cursor session.
- A headless run, where `CLAUDE_CODE_SESSION_ATTENDED` is `0`.
- A session no person typed into: a `claude -p` run, a session another agent created, or a scheduled run. A prompt a person typed carries `turnOrigin` equal to `human`, and so does a custom slash command. Once a person types a prompt there, the gate covers the session. On a host whose records carry no `turnOrigin` field at all, a session with a prompt counts as started by a person when `CLAUDE_CODE_SESSION_ATTENDED` is `1`.
- A session whose transcript cannot be read.
- A stop the gate cannot finish within 7 seconds by its own clock checks. The check runs in a child process, which is killed 8 seconds after the payload read starts, so one long step, such as a JSON parse, cannot keep the stop waiting. A watchdog thread ends a payload read that never finishes at 8.5 seconds. It reads the clock between lines, texts, and windows of each marker scan. A single regular expression pass over one text cannot be cut short, which is why a text over 2 MiB is skipped. In local runs, a 190 MB transcript of short prompt lines took 4.5 seconds, and 160 to 180 MB transcripts that hold many 2 MiB texts of code spans reached the deadline and passed in 7.3 to 7.4 seconds.
- A stop where the gate itself fails, or where a standard stream is closed or cannot be written. It passes with exit code 0. A hold whose output write has not finished 1 second after it starts, such as a write to a full pipe nobody reads, ends with exit code 0.

### Two holds

The gate counts its own holds, as feedback records that open with the first sentence of a reason, since the later of the last typed prompt and the last answered question call, and it allows the stop after two. Every reason counts. It checks every stop again, also one a Stop hook already held, so a reply in plain text does not release a hold. A host with no question tool gets two holds and then stops. There, give each open item its own short paragraph in the reply.

### How to run a round

1. Find the items. Look in the task list, your running notes, worker reports, the "Not covered" section of each pull request body, and your own words in the transcript.
2. Read the live state of each item, and drop each one that is done.
3. Write one chat brief before the first call. Say where things stand in two or three lines. Then give each item one short paragraph that names each option label and its effect, with its links. The brief covers every item, because the user answers the first set of cards before the second set shows. `question_brief_gate.py` counts the chat text since the last typed prompt or question result, the held reply included, and refuses a call past 450 words or 15 list or table items. When the held reply is already past that, write a one-line brief and send the cards. That call is refused, and a refused question starts a new count, so send the same cards again at once with no new text.
4. Send each item as its own question. One call holds at most four questions, so a longer round takes more calls. Give each question a header of 12 characters or fewer and two or three options, with your recommendation first. Give each option a one-sentence description. A card shows plain text, so write a link in a card as a bare URL.
5. An answer can be free text. Follow what it says, and treat new work it adds as an ask.
6. Close in plain words with what you did with each answer, and do not restate the items. A reply after the cards that repeats a marker, such as "The backoff setting stays deferred", starts a new stretch and is held. Write "The backoff setting stays as it is" there. When work is still in progress, end with the In progress footer.

When the lines name nothing that is still open, send one question that says so and lets the user add an item.

### Limits

- The gate holds at most twice per typed prompt or answered card.
- A marker can hold a line that names no open item, such as a negation or a line about the word itself. That hold costs one card.
- An item recorded only in a file is not seen, and neither is a pending task in the task list. The hold reason tells the agent to read those. A task in progress holds the old line `Open items: none.`
- A card about another subject still ends the stretch.
- A session whose only prompts came from an agent is not covered.
- A scheduled wake inside a session a person started is held like any other stop.
- A payload over 16 MiB passes unread. A transcript line over 16 MiB or a text over 2 MiB is skipped, and a stop the gate cannot finish within 7 seconds passes.
- The gate counts one of its holds only when the feedback record starts with "Stop hook feedback" and carries the first sentence of the reason in its first 200 characters. A host that writes the feedback in another shape gets a hold on every stop, up to its own limit.
- Text inside an HTML block is not read.
- A marker joined to a word by four or more underscores still reads as a marker.
- A marker joined to a file name by a hyphen, such as `todo-list.md`, still reads as a marker.
- Text the masking misses reads as prose and can hold, such as an unclosed fence or a quote indented four spaces inside a nested list item.
- A question call whose id holds a character the transcript escapes outside printable ASCII, such as `"` or `é`, is not matched to its result, so the stretch does not end there. Claude Code writes ids of letters, digits, and underscores.
- The gate runs on Claude Code only.

## Codex visual comparisons

For Codex visual comparisons, find Page creation, visualization upload, and Page opening tools. Create the comparison, upload its visualization, and open its Page here before asking. If tools are missing, steps fail, or opening queues, compare in chat before asking. Put inline Visualize references only in final replies. An async acknowledgement or saved visual is context only; wait for and use the submitted answer before dependent work.

## Option cards

When the user asks for option cards, build an Artifact page with the `html-plan:html-plan` skill and follow `~/.claude/docs/templates/html-plan/README.md`. Load the `artifact-capabilities` skill and declare the capability that saves the answer where you can read it. A tap selects a card, a second tap clears it, a picked card shows "Change it" with a notes field, and only Send delivers. After publishing, read the saved answer back before dependent work. If no capability can return the answer, use the native question tool with the same labels.
