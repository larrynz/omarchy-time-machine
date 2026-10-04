# Manage backups: design

Status: implemented (CLI + tests + README + panel), design report and code on
branch work-notes.

## The ask

A new "Manage Backups" option in the panel, using a picker similar to
Restore Files, with an option to delete the backup. Deleting is irreversible,
so the design was agreed with the user before implementation.

## Decisions

1. **Delete means forget and prune now.** `restic forget <id> --prune`:
   the snapshot is removed and the space is reclaimed immediately. The
   operation can take minutes on a large repository, so the picker shows a
   busy line that says so rather than looking wedged. Forget alone was
   rejected: it removes the snapshot from the list but leaves the data
   waiting for the next backup's prune, which reads as "deleted" doing
   nothing.

2. **Delete only; no manual retention pass.** The backup already prunes to
   the configured retention (7 daily, 4 weekly, 12 monthly, 3 yearly) after
   every run, so a "prune to retention now" button would only force the same
   pass early. Scope stays at single-snapshot delete.

3. **One CLI command, shaped like the others.**
   `omarchy-time-machine delete --dest <name> --snapshot <id>`. The option is
   `--snapshot`, matching restore, ls and snapshots. JSON output names what
   was deleted (`{ok:true, deleted:<id>}`); restic's own output, including
   the prune report, lands in the destination's log file, which `log` then
   reports as the most recent log. The delete is never recorded in
   `last_run`: it is a manual action like restore, not a backup, so a
   deletion does not disturb the verdict lines the panel shows.

4. **The picker mirrors the restore picker, one level up.** Restore walks
   into a snapshot's files; manage stays at the snapshot itself: the same
   destination dropdown (when there is a choice) and snapshot dropdown, a
   summary of what the backup holds, one destructive delete row, and the
   confirm dialog. No file listing, no folder browsing, no filter: there is
   nothing to walk into, and a filter with twelve rows would be a control
   pretending there is.

5. **Two interactions from an irreversible operation.** Pick a date, click
   the red delete row, and the confirm dialog spells out the date and the
   destination: "Delete the backup from <date> from <destination>? This
   cannot be undone." The dialog's Delete button is the only thing that
   reaches the command. The destination label goes through `plain()` for the
   same reason a filename does: it is user-controlled text and ConfirmDialog
   sets no textFormat.

6. **Keyboard.** The browser's key sink owns the keyboard while it is on
   screen, the same as the restore browser. Escape cancels an open confirm,
   then goes back; Enter accepts. Everything else is left unaccepted: with
   no listing to walk, the arrow keys have nothing to do, and the panel's
   key catcher is blocked while managing, so they fall through harmlessly.

7. **The list reloads after a delete.** The store's staleness key is
   `last_success_at`, which does not move when a snapshot is deleted, so the
   date the user just deleted would sit in the picker until the next backup.
   The delete completion reloads the list itself, and the picker lands on
   the newest remaining backup.

8. **restic locks are the concurrency story.** A delete while a backup is
   running waits for the repository lock (`--retry-lock 10m`), the same way
   two simultaneous backups would. The picker stays offered while a backup
   runs; the lock, not the UI, serializes the work.

9. **"latest" is accepted but never passed.** The id validator takes
   "latest" or 8-64 hex, and the CLI keeps that rule, but the widget always
   passes the full id out of the snapshots list, so the one id that is easy
   to type destructively never arrives by accident through the panel.

## Tests

A "Manage backups" group at the end of `test/run-tests.sh`, against the real
repository the suite already builds: delete removes a snapshot and exits 0,
the JSON output names what was deleted, the list is shorter by one, a missing
snapshot id and an unknown destination are refused, and demo mode makes the
delete a no-op that still reports success.

## Fixes found after implementation

Three bugs surfaced in real use after the feature shipped, all picker-side:

1. **A failed run's snapshots were invisible.** The store cached the
   snapshots list keyed on `last_success_at`, which by design does not move
   on a failed run. A failed run that still wrote a snapshot (the unreadable
   case: restic writes a holed snapshot and exits 3) never refreshed the
   cache, and neither of its snapshots appeared in the picker. The cache is
   now also keyed on the run's own finish time, which moves on every run. A
   delete moves neither key, so the delete completion still reloads the list
   itself, as decision 7 says.

2. **A delete's reload could leave a picker holding a vanished id.** The
   reload replaces the list, but a dropdown selected on an id that is no
   longer in it rendered the raw 64-character hex id and could not resolve a
   summary. Both browsers now reconcile on every reload: an id no longer in
   the list re-picks the newest remaining backup, and an empty list clears
   the picker.

3. **The unreadable count double-counted a path.** restic can report the
   same path twice in one run (once per scan pass), and each event appended
   a line, so one unreadable path made the notification say "and 1 more".
   The audit file already deduplicated; the notification's count now does
   too.

A fourth fix landed on the audit rather than the picker: paths matching an
exclude pattern count as by-design even when they are also unreadable, so a
root-owned directory named in the exclude file does not sit in the panel's
unreadable count forever. The README documents that under "Folders the
backup cannot read".
