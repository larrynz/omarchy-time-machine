# Security review: command-line key exposure, unit value injection, redaction fragments

A security review of the backup path surfaced five issues and one test-suite bug. All findings are reproduced below with before/after evidence; the fixes are in the attached PR.

## 1. The key sits on jq's command line (`key save-1password`)

`key_save_to_1password` builds the item template with:

```bash
template="$(jq -n --arg title "$title" --arg password "$(cat -- "$keyfile")" ...)"
```

An `--arg` value sits on jq's own command line, and `/proc/PID/cmdline` is mode 0444 — readable by every account on the machine while the command runs. The script is careful everywhere else (it refuses to pass the key as an argument to restic, it redacts it from status), but this one route exposes it.

**Fix**: pass the file with `--rawfile` instead, and `rtrimstr("\n")` the value so what 1Password stores is the password itself, not the file contents (`key set` writes a trailing newline).

## 2. A newline in `schedule` or `randomized_delay` injects unit directives (`install`)

Both values are interpolated verbatim into the generated unit file, and unit files are parsed line by line:

```json
{ "name": "test", "schedule": "*-*-* 03:00:00\n\n[Service]\nExecStartPre=/tmp/evil" }
```

produces a unit with an `ExecStartPre` of somebody else's choosing — and `install` enables the unit without asking. `name` is already restricted to a safe character set for exactly this reason; the two values beside it get none.

**Fix**: `install` now checks both values against calendar-spec and time-span character sets, and validates the schedule with `systemd-analyze calendar` (the same parser the unit will get) before anything is written. A poisoned schedule is refused before the write; a typo'd but harmless spec now fails with a message pointing at `systemd-analyze calendar` instead of failing to schedule silently.

## 3. Redaction leaves password fragments behind (`sanitize_repository`)

The password part of a repository URL is matched with a fixed character set that excludes `@`:

```
s#//([^/@:[:space:]]+):[^/@[:space:]]*@#//\1@#g;
```

Two consequences, both reproduced against the current code:

- A password carrying an `@` — which restic accepts, since Go's net/url splits the user info at the **last** `@` — only partially matches: `rest:http://me:p@ss@nas:8000/` displays as `rest:http://me@ss@nas:8000/`, leaving half the password in status.json, the log and the panel.
- With no username at all, `sftp::pass@host/backup` matches nothing and the password stays whole.

**Fix**: the password part is now matched greedily up to the last `@` before the first slash — the same split net/url makes:

```
s#//:[^/]*@#//#g;
s#//([^/:]*):[^/]*@#//\1@#g;
s#^([a-z0-9+.-]+:)([^:/]*):[^/]*@#\1\2@#'
```

Verified against 14 URL shapes, including the ones the old code handled correctly (colon-in-password, `@` in the path, two-scheme `rest:http://…`, port numbers, no-trailing-slash). A raw `/` in a password remains uncovered — net/url cannot read such a URL either; the README now documents percent-encoding as the way.

## 4. A symlink on the log file name is truncated through (`open_log`)

`private_dir` sweeps the state directory but deliberately keeps `logs/`, so a symlink can sit on the one name `open_log` is about to take; `: > "$LOG_FILE"` would then write through it to a file somebody else chose.

**Fix**: non-regular entries on the target name are removed first — the same rule the state-file sweep applies.

## 5. `restore --target /` lays old files over the running system

`restore` never passes `--target` itself, but the flag exists, and restic **overwrites** what is already in the target directory. A stray `--target /` or `--target ~` typed by hand restores snapshot contents in place.

**Fix**: both values are refused before the target is created.

## 6. Two negative assertions in the test suite never actually failed

`test/run-tests.sh` uses this pattern twice:

```bash
grep -q "test-password" "$WORK/op-argv" 2>/dev/null && false || true
check $? "the key never appears in op's arguments"
```

`A && false || true` evaluates to 0 whether or not `A` succeeded, so both assertions always passed — including through the bug in finding 1. Fixed to the `[ $? -ne 0 ]` form the suite already uses elsewhere, and extended: the key is now also checked on jq's command line (finding 1), and unit value injection, password redaction and restore-target guards are covered.

## Verification

`test/run-tests.sh`: **96 passed, 0 failed** (was 82 passed with two assertions that could not fail).
