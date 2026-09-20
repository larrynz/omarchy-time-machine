# Tighten redaction, validate unit values, guard log and restore paths

Follow-ups from a security review of the backup path. Details, evidence and before/after output for each finding are in the companion issue.

## What changed

**`bin/omarchy-time-machine`**

- `sanitize_repository` — the password part is matched greedily up to the last `@` before the first slash, the same split Go's net/url (which restic uses) makes. A password carrying a `:` or an `@` itself no longer leaves a fragment behind, and `sftp::pass@host` no longer keeps its password whole. Verified against 14 URL shapes, including every shape the old code already handled correctly.
- `install` — `schedule` and `randomized_delay` are validated against calendar-spec and time-span character sets, plus a `systemd-analyze calendar` check, **before** anything is written into a unit file. A newline in either value would have injected unit directives into a unit that install then enables.
- `key save-1password` — the password reaches jq via `--rawfile`, not `--arg`, so it never sits on jq's command line where `/proc/PID/cmdline` is readable by every account on the machine. `rtrimstr` takes off the trailing newline that `key set` writes, so 1Password stores the password itself.
- `open_log` — removes a symlink sitting on the log file name before truncating, instead of writing through it.
- `restore` — refuses `--target /` and `--target $HOME`; restic overwrites what is already in the target, and those two are the values a typo can produce.

**`README.md`**

- Documents percent-encoding for passwords in repository URLs (the one form every backend accepts, and the one form the panel can reliably hide).
- New section on the per-destination env file: `<name>.env`, `${NAME}` substitution in the repository URL, and the warning that everything in it is exported to restic and to the commands around the backup.
- "Pick a password" now separates the repository password from storage credentials and API keys -- it encrypts only the backup contents, and every destination has its own -- documents the two ways a destination can fetch the password itself (`password_command` / `password_file`, never both) with a `pass` example and the non-interactive caveat for scheduled runs, and adds a `pass` one-liner next to the 1Password shortcut.

**`test/run-tests.sh`**

- Fixes two negative assertions that used `grep -q X && false || true` — an expression that always exits 0, so "the key never appears in op's arguments" and "the note names the destination without its password" could never fail, including through the jq-argv bug above.
- New coverage: the key on jq's command line (via a jq stub that records its argv), unit value injection for both `schedule` and `randomized_delay` (timer removed first, so the test proves nothing is written back), four password-redaction shapes, restore-target refusals, and a `password_command` destination backing up with no key file at all (plus `key set` refusing it).

## Verification

- `test/run-tests.sh`: **96 passed, 0 failed**.
- Redaction verified against 14 URL shapes (colon in password, `@` in password, empty user, `@` in path, two-scheme URLs, ports, no trailing slash, scheme forms with and without passwords, plain local paths).
