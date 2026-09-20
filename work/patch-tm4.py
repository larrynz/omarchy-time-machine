#!/usr/bin/env python3
import sys

def rep(path, old, new, name):
    with open(path) as f:
        src = f.read()
    n = src.count(old)
    if n != 1:
        print(f"FAIL {name}: found {n} occurrences in {path}"); sys.exit(1)
    with open(path, "w") as f:
        f.write(src.replace(old, new))
    print(f"ok   {name}")

README = "README.md"
TESTS = "test/run-tests.sh"
PR = "/tmp/pr-draft.md"

# --- README: what the password is NOT, and the alternatives to the key file ---
rep(README,
r'''Those three lines set the password, prepare the destination, and switch on the nightly schedule. That's the setup done. Go do something else.

## Now save that password somewhere else''',
r'''Those three lines set the password, prepare the destination, and switch on the nightly schedule. That's the setup done. Go do something else.

This password encrypts only the backup contents. It is not where API keys or storage credentials go -- those belong in the per-destination env file, or in whatever secret store you already use. And it is not one password for everything: every destination has its own.

If you would rather restic fetch this password from somewhere other than the local key file, set `password_command` or `password_file` in the config -- never both -- and the key file is not used at all:

```json
{ "name": "backup-drive", "password_command": "pass show omarchy/backup-drive" }
```

If your secrets live in `pass`, that line is the whole setup: pass handles the gpg underneath, and every backup picks the password up straight from your store. `key set` refuses a destination that uses `password_command`, because a key file would do nothing there -- and the password's recovery plan becomes whatever discipline you already have for that store. One operational caveat: a scheduled run has no terminal to prompt in, so the command has to answer without asking -- keep the gpg passphrase cached or set up loopback pinentry, or the run stops with an error instead of hanging.

## Now save that password somewhere else''',
"README: password framing + password_command")

# --- README: a pass one-liner next to the 1Password shortcut -------------------
rep(README,
r'''That writes it into your vault as "Time Machine backup key (backup-drive)", with a note saying which destination it opens. It refuses if an item by that name already exists, because two of them is how you end up trying the wrong one in a year.

### Credentials beyond the password''',
r'''That writes it into your vault as "Time Machine backup key (backup-drive)", with a note saying which destination it opens. It refuses if an item by that name already exists, because two of them is how you end up trying the wrong one in a year.

And if your password manager is `pass`, the same one-liner:

```bash
omarchy-time-machine key show --dest backup-drive | pass insert -m omarchy/backup-drive
```

### Credentials beyond the password''',
"README: pass one-liner")

# --- Tests: a destination that fetches its own password ------------------------
rep(TESTS,
r'''OUT="$($CLI backup --dest test 2>&1)"
grep -q "pick one" <<<"$OUT"
check $? "setting both password sources is refused rather than silently resolved"
cp "$WORK/config.bak" "$CONFIG"''',
r'''OUT="$($CLI backup --dest test 2>&1)"
grep -q "pick one" <<<"$OUT"
check $? "setting both password sources is refused rather than silently resolved"
cp "$WORK/config.bak" "$CONFIG"

# The other half of that rule: a destination that fetches its own password
# works with no key file at all -- which is what proves restic is reading it
# from the command, not from the file this test just removed.
jq '.destinations[0].password_command = "echo test-password"' "$CONFIG" > "$CONFIG.n" && mv "$CONFIG.n" "$CONFIG"
rm -f "$XDG_CONFIG_HOME/omarchy-time-machine/test.key"
$CLI backup --dest test >/dev/null 2>&1
[ "$?" = "0" ]
check $? "a password_command feeds restic with no key file present"

$CLI key set --dest test </dev/null 2>/dev/null
[ "$?" != "0" ]
check $? "and key set refuses a destination that fetches its own"

cp "$WORK/config.bak" "$CONFIG"
printf 'test-password\n' | $CLI key set --dest test >/dev/null 2>&1''',
"TESTS: password_command")

# --- PR draft: README bullets and test coverage --------------------------------
rep(PR,
r'''- Documents percent-encoding for passwords in repository URLs (the one form every backend accepts, and the one form the panel can reliably hide).
- New section on the per-destination env file: `<name>.env`, `${NAME}` substitution in the repository URL, and the warning that everything in it is exported to restic and to the commands around the backup.''',
r'''- Documents percent-encoding for passwords in repository URLs (the one form every backend accepts, and the one form the panel can reliably hide).
- New section on the per-destination env file: `<name>.env`, `${NAME}` substitution in the repository URL, and the warning that everything in it is exported to restic and to the commands around the backup.
- "Pick a password" now separates the repository password from storage credentials and API keys -- it encrypts only the backup contents, and every destination has its own -- documents the two ways a destination can fetch the password itself (`password_command` / `password_file`, never both) with a `pass` example and the non-interactive caveat for scheduled runs, and adds a `pass` one-liner next to the 1Password shortcut.''',
"PR: README bullets")

rep(PR,
r'''- New coverage: the key on jq's command line (via a jq stub that records its argv), unit value injection for both `schedule` and `randomized_delay` (timer removed first, so the test proves nothing is written back), four password-redaction shapes, and restore-target refusals.''',
r'''- New coverage: the key on jq's command line (via a jq stub that records its argv), unit value injection for both `schedule` and `randomized_delay` (timer removed first, so the test proves nothing is written back), four password-redaction shapes, restore-target refusals, and a `password_command` destination backing up with no key file at all (plus `key set` refusing it).''',
"PR: test coverage")

print("all edits applied")
