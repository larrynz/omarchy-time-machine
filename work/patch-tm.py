#!/usr/bin/env python3
"""Apply the security-review fixes to omarchy-time-machine.

Every old/new block is a raw string: backslashes in the target files must
arrive literally, and tool-call content has been shown to mangle them, so the
script itself is written through the file path, not a shell heredoc.
"""
import sys

def rep(path, old, new, name):
    with open(path) as f:
        src = f.read()
    n = src.count(old)
    if n != 1:
        print(f"FAIL {name}: found {n} occurrences in {path}")
        sys.exit(1)
    with open(path, "w") as f:
        f.write(src.replace(old, new))
    print(f"ok   {name}")

BIN = "bin/omarchy-time-machine"
README = "README.md"
TESTS = "test/run-tests.sh"

# --- F1: the key must not sit on jq's command line ---------------------------
rep(BIN,
r'''  template="$(jq -n \
    --arg title "$title" \
    --arg password "$(cat -- "$keyfile")" \
    --arg notes "$notes" \
    '{title: $title,
      category: "PASSWORD",
      fields: [{id: "password", type: "CONCEALED", purpose: "PASSWORD",
                label: "password", value: $password},
               {id: "notesPlain", type: "STRING", purpose: "NOTES",
                label: "notesPlain", value: $notes}]}')" ||
    die "could not build the 1Password item"''',
r'''  # --rawfile, not --arg: an --arg value sits on jq's own command line, and
  # /proc/PID/cmdline is 0444 -- readable by every account on the machine,
  # which is the exact route this script refuses everywhere else. rtrimstr
  # takes off the trailing newline that `key set` writes, so what 1Password
  # stores is the password itself, not the file contents.
  template="$(jq -n \
    --arg title "$title" \
    --rawfile password "$keyfile" \
    --arg notes "$notes" \
    '{title: $title,
      category: "PASSWORD",
      fields: [{id: "password", type: "CONCEALED", purpose: "PASSWORD",
                label: "password", value: ($password | rtrimstr("\n"))},
               {id: "notesPlain", type: "STRING", purpose: "NOTES",
                label: "notesPlain", value: $notes}]}')" ||
    die "could not build the 1Password item"''',
"F1: rawfile")

# --- F3: redaction must cover passwords that carry a colon -------------------
rep(BIN,
r'''# `sftp:user@host:/path` has no `//` at all and can never carry a password,
# since restic authenticates it over SSH.
sanitize_repository() {
  printf '%s' "$1" | sed -E '
    s#//([^/@:[:space:]]+):[^/@:[:space:]]*@#//\1@#g;
    s#//:[^/@:[:space:]]*@#//#g;
    s#^([a-z0-9+.-]+:)([^/@:[:space:]]+):[^/@:[:space:]]*@#\1\2@#'
}''',
r'''# `sftp:user@host:/path` has no `//` at all and can never carry a password,
# since restic authenticates it over SSH.
#
# The password part may carry a colon: restic parses URLs with Go's net/url,
# which splits the user info at the last `@` and the first `:`, so in
# `me:hu:nter2@nas` the password is `hu:nter2` and the URL is one restic will
# happily use. A fixed character set for the password cannot describe that --
# `hu:nter2` used to survive redaction whole and land in status.json, the log
# and the panel. The classes therefore match anything but `@` and `/`, and the
# host part stops at the first slash, so a URL whose path happens to contain
# an `@` still displays correctly. A raw `/` in a password is not covered, but
# net/url cannot read such a URL either; percent-encoding is the way, and the
# README says so.
sanitize_repository() {
  printf '%s' "$1" | sed -E '
    s#//:[^/@:[:space:]]*@#//#g;
    s#//([^/:]*):([^@/]*)@([^/]*)#//\1@\3#g;
    s#^([a-z0-9+.-]+:)([^:@/]*):([^@/]*)@#\1\2@#'
}''',
"F3: sanitize")

# --- F5a: no symlink on the log file name ------------------------------------
rep(BIN,
r'''open_log() {
  local dir="$LOG_ROOT/$DEST_NAME"
  mkdir -p -m 700 -- "$dir"
  LOG_FILE="$dir/$(date +%Y-%m-%d_%H%M%S).log"
  : > "$LOG_FILE"
  chmod 600 -- "$LOG_FILE"
}''',
r'''open_log() {
  local dir="$LOG_ROOT/$DEST_NAME"
  mkdir -p -m 700 -- "$dir"
  LOG_FILE="$dir/$(date +%Y-%m-%d_%H%M%S).log"
  # The sweep in private_dir keeps logs/ itself, so a symlink can sit on the
  # one name this file is about to take: truncating through it would send
  # every line to a file somebody else chose. Remove the entry instead, the
  # same rule the state-file sweep applies.
  if [ -L "$LOG_FILE" ] || { [ -e "$LOG_FILE" ] && [ ! -f "$LOG_FILE" ]; }; then
    rm -f -- "$LOG_FILE"
  fi
  : > "$LOG_FILE"
  chmod 600 -- "$LOG_FILE"
}''',
"F5a: open_log")

# --- F2: unit values validated before they are written ------------------------
rep(BIN,
r'''# ---------------------------------------------------------------------------
# systemd
# ---------------------------------------------------------------------------

# systemd user services do not inherit the shell PATH.''',
r'''# ---------------------------------------------------------------------------
# systemd
# ---------------------------------------------------------------------------

# The schedule and its delay are interpolated verbatim into a unit file, and
# unit files are parsed line by line: a newline in either value would inject
# whatever follows as unit directives -- an ExecStartPre of somebody else's
# choosing, enabled by install without asking. `name` is restricted to a safe
# character set for the same reason; these get the same treatment. Calendar
# specs and time spans are ASCII by nature, so the character check is strict,
# and systemd-analyze -- the same parser the unit will get -- catches the
# typo'd spec that would otherwise fail to schedule silently.
check_unit_values() {
  local name="$1" schedule="$2" delay="$3"
  [[ "$schedule" == *[!A-Za-z0-9*:.,~/ -]* ]] &&
    die "schedule of $name contains characters a calendar spec cannot use; refusing to write them into a unit file"
  [[ "$delay" == *[!0-9A-Za-z ]* ]] &&
    die "randomized_delay of $name contains characters a time span cannot use; refusing to write them into a unit file"
  if command -v systemd-analyze >/dev/null 2>&1; then
    systemd-analyze calendar "$schedule" >/dev/null 2>&1 ||
      die "schedule of $name is not a calendar spec systemd accepts: \"$schedule\" (check with: systemd-analyze calendar \"$schedule\")"
  fi
  return 0
}

# systemd user services do not inherit the shell PATH.''',
"F2: helper")

rep(BIN,
r'''    delay="$(jq -r --arg n "$name" '.destinations[] | select(.name==$n) | .randomized_delay // "15m"' <<<"$CONFIG_JSON")"
    names+=("$name")''',
r'''    delay="$(jq -r --arg n "$name" '.destinations[] | select(.name==$n) | .randomized_delay // "15m"' <<<"$CONFIG_JSON")"
    check_unit_values "$name" "$schedule" "$delay"
    names+=("$name")''',
"F2: call")

# --- F5b: never restore into / or $HOME ---------------------------------------
rep(BIN,
r'''  target="$(expand_tilde "$OPT_TARGET")"
  [ -n "$target" ] || target="$HOME/Restored/$(date +%Y-%m-%d-%H%M)"
  mkdir -p -- "$target" || die "could not create $target"''',
r'''  target="$(expand_tilde "$OPT_TARGET")"
  [ -n "$target" ] || target="$HOME/Restored/$(date +%Y-%m-%d-%H%M)"
  # restic overwrites what is already in the target, so a stray --target /
  # typed by hand would lay old files over the running system. The widget
  # never passes --target; these two are the values a typo can produce, and
  # the two that must never be one.
  if [ "$target" = "/" ] || [ "$target" = "$HOME" ]; then
    die "refusing to restore into $target; pick a directory that holds nothing else"
  fi
  mkdir -p -- "$target" || die "could not create $target"''',
"F5b: target guard")

# --- README: percent-encoding note -------------------------------------------
rep(README,
"Anywhere restic can write works: a local disk, SFTP, a REST server, S3, Minio, Wasabi, Backblaze B2, Azure Blob, Google Cloud Storage, Alibaba OSS, OpenStack Swift, or anything rclone can reach. A drive in your bag and a bucket in the cloud is a good pair: one is fast, the other survives your house.",
r'''Anywhere restic can write works: a local disk, SFTP, a REST server, S3, Minio, Wasabi, Backblaze B2, Azure Blob, Google Cloud Storage, Alibaba OSS, OpenStack Swift, or anything rclone can reach. A drive in your bag and a bucket in the cloud is a good pair: one is fast, the other survives your house.

If a URL carries a username and password, percent-encode the password: `p@ss` becomes `p%40ss`. A raw `/` or space breaks the URL for restic itself, and a password restic cannot parse is also one the panel cannot reliably hide -- percent-encoding is the one form every backend accepts.''',
"README: percent-encoding")

# --- README: document the per-destination env file ----------------------------
rep(README,
r'''That writes it into your vault as "Time Machine backup key (backup-drive)", with a note saying which destination it opens. It refuses if an item by that name already exists, because two of them is how you end up trying the wrong one in a year.

## Getting files back''',
r'''That writes it into your vault as "Time Machine backup key (backup-drive)", with a note saying which destination it opens. It refuses if an item by that name already exists, because two of them is how you end up trying the wrong one in a year.

### Credentials beyond the password

Some destinations need more than a password: an access key for a bucket, a token for a rest server. Every destination can carry an env file at `~/.config/omarchy-time-machine/<name>.env` -- or wherever `secrets_file` in the config points -- holding `KEY=VALUE` lines. A `${NAME}` in the repository URL is replaced with the matching value:

```json
{ "name": "offsite", "repository": "s3:s3.amazonaws.com/${bucket}" }
```

Everything in that file is exported to restic and to the commands the backup runs around it, `pre_command` included. Put in it only what the backup needs: anything there reaches every process a run spawns.

## Getting files back''',
"README: env file")

# --- Tests: the two negative assertions never actually failed -----------------
rep(TESTS,
r'''grep -q "test-password" "$WORK/op-argv" 2>/dev/null && false || true
check $? "the key never appears in op's arguments"''',
r'''grep -q "test-password" "$WORK/op-argv" 2>/dev/null
[ $? -ne 0 ]
check $? "the key never appears in op's arguments"

# op is only half of that trip. The template is built by jq, and an --arg value
# sits on jq's own command line, where /proc/PID/cmdline is readable by every
# account on the machine. The stub below wraps the real jq and records what it
# was handed.
cat > "$WORK/stub/jq" <<STUB
#!/usr/bin/env bash
printf '%s\0' "\$@" >> "\$JQ_ARGV"
exec $(command -v jq) "\$@"
STUB
chmod +x "$WORK/stub/jq"
OP_ARGV="$WORK/op-argv" OP_CAPTURE="$WORK/op-stdin" JQ_ARGV="$WORK/jq-argv" PATH="$WORK/stub:$PATH" \
  $CLI key save-1password --dest test >/dev/null 2>&1

grep -q "test-password" "$WORK/jq-argv" 2>/dev/null
[ $? -ne 0 ]
check $? "and it never reaches jq's command line either"''',
"TESTS: jq argv")

rep(TESTS,
r'''grep -q "hunter2" "$WORK/op-stdin" 2>/dev/null && false || true
check $? "and the note names the destination without its password"''',
r'''grep -q "hunter2" "$WORK/op-stdin" 2>/dev/null
[ $? -ne 0 ]
check $? "and the note names the destination without its password"''',
"TESTS: note redaction")

# --- Tests: unit value injection ----------------------------------------------
rep(TESTS,
r'''  check $? "systemd accepts the generated service"
fi

# --- multiple destinations -------------------------------------------------''',
r'''  check $? "systemd accepts the generated service"
fi

# The schedule and its delay are interpolated verbatim into the unit file, and
# unit files are parsed line by line: a newline in either value would inject
# whatever follows as unit directives, and install enables the unit without
# asking. The refusal has to happen before the write, so the timer is removed
# first and what is under test is whether it comes back.
group "Unit value injection"

rm -f "$XDG_CONFIG_HOME/systemd/user/omarchy-time-machine@test.timer"
jq '.destinations[0].schedule = ("*-*-* 03:00:00\n\n[Service]\nExecStartPre=/tmp/evil")' \
  "$CONFIG" > "$CONFIG.n" && mv "$CONFIG.n" "$CONFIG"
$CLI install >/dev/null 2>&1
[ "$?" != "0" ]
check $? "install refuses a schedule with unit directives in it"
[ ! -e "$XDG_CONFIG_HOME/systemd/user/omarchy-time-machine@test.timer" ]
check $? "and nothing of it reached the timer file"

jq '.destinations[0].schedule = "*-*-* 03:00:00"
    | .destinations[0].randomized_delay = "15m\nNice=-20"' "$CONFIG" > "$CONFIG.n" && mv "$CONFIG.n" "$CONFIG"
$CLI install >/dev/null 2>&1
[ ! -e "$XDG_CONFIG_HOME/systemd/user/omarchy-time-machine@test.timer" ]
check $? "a randomized_delay with a newline is refused as well"

cp "$WORK/config.bak" "$CONFIG"

# --- multiple destinations -------------------------------------------------''',
"TESTS: unit injection")

# --- Tests: password redaction -------------------------------------------------
rep(TESTS,
r'''cp "$WORK/config.bak" "$CONFIG"

# --- more than one source ---------------------------------------------------''',
r'''cp "$WORK/config.bak" "$CONFIG"

# --- password redaction -----------------------------------------------------
#
# What reaches status.json and the panel is the repository with the password
# removed and the username kept. The password part may carry a colon: restic
# parses URLs with Go's net/url, which splits the user info at the last `@`
# and the first `:`, so a fixed character set for the password cannot describe
# every URL restic will actually use.

group "Password redaction"

jq '.destinations[0].repository = "rest:http://me:hu:nter2@nas:8000/"' "$CONFIG" > "$CONFIG.n" && mv "$CONFIG.n" "$CONFIG"
$CLI destinations --json 2>/dev/null | jq -e '[.destinations[].repository_display] | all(. | test("hu:nter2") | not)' >/dev/null 2>&1
check $? "a password carrying a colon does not survive redaction"

jq '.destinations[0].repository = "rest:http://:hunter2@nas:8000/"' "$CONFIG" > "$CONFIG.n" && mv "$CONFIG.n" "$CONFIG"
$CLI destinations --json 2>/dev/null | jq -e '[.destinations[].repository_display] | all(. | test("hunter2") | not)' >/dev/null 2>&1
check $? "and neither does one with no username in front of it"

jq '.destinations[0].repository = "rest:http://me:hunter2@nas:8000/a@b"' "$CONFIG" > "$CONFIG.n" && mv "$CONFIG.n" "$CONFIG"
$CLI destinations --json 2>/dev/null | jq -e '[.destinations[].repository_display] | all(. | test("nas:8000/a@b"))' >/dev/null 2>&1
check $? "a path containing an @ still displays intact"

cp "$WORK/config.bak" "$CONFIG"

# --- more than one source ---------------------------------------------------''',
"TESTS: redaction group")

# --- Tests: never restore into / or $HOME --------------------------------------
rep(TESTS,
r'''$CLI restore --dest test --snapshot "zzz" --path /tmp --json | jq -e '.ok == false' >/dev/null 2>&1
check $? "restore refuses an invalid id (die inside \$( ) would only kill a subshell)"''',
r'''$CLI restore --dest test --snapshot "zzz" --path /tmp --json | jq -e '.ok == false' >/dev/null 2>&1
check $? "restore refuses an invalid id (die inside \$( ) would only kill a subshell)"

$CLI restore --dest test --snapshot "$SNAP" --path / --target / --json 2>/dev/null | jq -e '.ok == false' >/dev/null 2>&1
check $? "restoring into / is refused, not executed"

$CLI restore --dest test --snapshot "$SNAP" --path / --target "$HOME" --json 2>/dev/null | jq -e '.ok == false' >/dev/null 2>&1
check $? "and so is restoring into the home directory itself"''',
"TESTS: target guard")

print("all edits applied")
