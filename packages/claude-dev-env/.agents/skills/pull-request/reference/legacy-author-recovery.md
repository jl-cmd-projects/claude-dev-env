# Recover a selected legacy author record

Run `.agents/skills/pull-request/scripts/recover_legacy_author.py
<exact-state-file> --confirm-inactive` only when the user selects one legacy
state file. The command checks the record's age, secure file metadata, and
contents. The confirmation flag records that the caller verified inactivity.
Leave every other record untouched. Delete the selected record only after a
successful restore.

A record older than 30 minutes can still belong to a live session. Require
`--confirm-inactive` before recovery.
