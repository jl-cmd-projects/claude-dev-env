---
name: mod-playbooks
description: >-
  Map of playbooks for driving a Claude Code mod (plugin) and seeing its screen: press keys, open menus and drawers, hover a reply to show its action row, click a dropdown, type in a field, fire a toast or a question card, and capture each screen as text and PNG. Use when an agent must test a mod, check a fix by looking at it, or show a mod to the operator on their own desktop.
---

# Mod playbooks

## Principle

An agent proves a mod works by driving it and reading the screen. It needs no person for that. A
cloud session runs Claude Code in a pseudo-terminal, plays the steps, and reads each capture. The
operator's desktop comes last, when a person wants to look.

## Pick the route

| Goal | Route | Reference |
| --- | --- | --- |
| Test a mod, or check a fix, with no person | Drive it in a pseudo-terminal and read the captures | [cloud-drive.md](references/cloud-drive.md) |
| Let the operator watch the mod on their own screen | Open a desktop window from a Remote Control session | [desktop-window.md](references/desktop-window.md) |
| Prove what the operator's window shows | Capture that window to a PNG | [desktop-capture.md](references/desktop-capture.md) |

When the mod's repository ships a driver and playbooks, use them first. Look for a `drive.mjs` beside
a `playbooks/` folder and a playbook guide in its docs. Read the guide, run the matching playbook, and
add a playbook for any new screen you test.

## Playbook map

Each row is one thing an agent does to a mod, and the input that does it. The bytes are in
[cloud-drive.md](references/cloud-drive.md).

| Do this | Input | Check on screen |
| --- | --- | --- |
| Send a prompt | Type the text, then Enter | The scripted reply |
| Open a slash-command menu or pane | Type the command, then Enter | The pane's title |
| Open a pane from a footer pill | Click the pill's label | The pane's title |
| Move between buttons in a pane | Tab forward, Shift+Tab back, Enter to press | The focused button |
| Toggle a control | Click its label | The control's new state |
| Close a pane | Escape | The prompt again |
| Show a reply's action row | Hover the reply text; the row draws only under the pointer | The action labels |
| Pick from a dropdown | Click the action, click the choice, click the confirm button | The confirm line |
| Type in a text field | Click the field label, type, then Enter | The saved text |
| Fire a toast | Script a tool turn the mod watches, and allow that tool | The toast's words, top right |
| Raise a question card | Script a question tool turn, then click an option | The answered line |

## Self-resolve loop

1. Change the mod.
2. Run the playbook for the screen you changed.
3. Read the `.txt` capture for words, and open the `.png` for color and layout.
4. On a failed step, read `failure.png`, fix the cause, and run again.
5. Keep the passing captures as the proof, then show the operator if they asked to see it.

## Limits

- The cloud route proves the mod's screens. It runs a mock model, so it proves nothing about model output.
- The desktop route opens and captures a window. Typing or clicking into that window is not proven; drive input in the cloud route.
- A screen that needs the operator's account, files or network stays on the desktop route.
