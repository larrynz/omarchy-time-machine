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

CLI = "bin/omarchy-time-machine"
TESTS = "test/run-tests.sh"

# --- parse_options: --file and --password-file ---------------------------------
rep(CLI,
r'''  OPT_DEST=""; OPT_SNAPSHOT=""; OPT_PATH=""; OPT_TARGET=""; OPT_VAULT=""; OPT_DRY_RUN=0; OPT_JSON=0''',
r'''  OPT_DEST=""; OPT_SNAPSHOT=""; OPT_PATH=""; OPT_TARGET=""; OPT_VAULT=""; OPT_DRY_RUN=0; OPT_JSON=0
  OPT_FILE=""; OPT_PASSWORD_FILE=""''',
"parse_options: init OPT_FILE/OPT_PASSWORD_FILE")

rep(CLI,
r'''      --dest) OPT_DEST="${2:-}"; shift 2 || shift ;;''',
r'''      --dest) OPT_DEST="${2:-}"; shift 2 || shift ;;
      --file) OPT_FILE="${2:-}"; shift 2 || shift ;;
      --password-file) OPT_PASSWORD_FILE="${2:-}"; shift 2 || shift ;;''',
"parse_options: --file and --password-file cases")

# --- cmd_config create uses the shared starter ---------------------------------
rep(CLI,
r'''  config_dir_secure
  cat <<'JSON' | write_private "$CONFIG_FILE" || die "could not write $CONFIG_FILE"
{
  "source": "~",
  "retention": { "daily": 7, "weekly": 4, "monthly": 12, "yearly": 3 },
  "destinations": [
    {
      "name": "backup-drive",
      "display_name": "Backup drive",
      "repository": "/run/media/CHANGE-ME/backup/restic",
      "schedule": "*-*-* 03:00:00"
    }
  ]
}
JSON''',
r'''  config_dir_secure
  starter_config | write_private "$CONFIG_FILE" || die "could not write $CONFIG_FILE"''',
"cmd_config create uses starter_config")

# --- guided setup: starter_config + presets + cmd_apply_setup -------------------
rep(CLI,
r'''  printf '%s\n' "$CONFIG_FILE"
}

# ---------------------------------------------------------------------------
# systemd
# ---------------------------------------------------------------------------''',
r'''  printf '%s\n' "$CONFIG_FILE"
}

# ---------------------------------------------------------------------------
# guided setup
# ---------------------------------------------------------------------------

# The starter configuration, shared by `config create` and `apply-setup`.
starter_config() {
  cat <<'JSON'
{
  "source": "~",
  "retention": { "daily": 7, "weekly": 4, "monthly": 12, "yearly": 3 },
  "destinations": [
    {
      "name": "backup-drive",
      "display_name": "Backup drive",
      "repository": "/run/media/CHANGE-ME/backup/restic",
      "schedule": "*-*-* 03:00:00"
    }
  ]
}
JSON
}

# Schedule presets for the setup screen: short words a person can cycle
# through, expanded to the calendar expressions the units use. Anything else
# falls through to the systemd-analyze check, so a hand-typed spec still
# works and a typo still refuses.
apply_setup_preset() {
  case "$1" in
    hourly)  printf '*-*-* *:00:00' ;;
    daily)   printf '*-*-* 03:00:00' ;;
    weekly)  printf 'Mon *-*-* 03:00:00' ;;
    monthly) printf '*-*-01 03:00:00' ;;
    *) return 1 ;;
  esac
}

# One command for a setup screen. Takes a small JSON document on stdin:
#   {"name": "backup", "repository": "/mnt/x/restic", "schedule": "daily",
#    "display_name": "Backup", "password": "..."}
# Validates it against the same rules the units will get, merges it into
# config.json -- replacing any destination of the same name, so applying
# twice corrects instead of duplicating -- installs the key, creates the
# repository, and switches on the schedule. The password arrives on stdin,
# never on a command line: a command line is readable by any process on the
# machine, stdin is not.
cmd_apply_setup() {
  parse_options "$@"

  local doc
  if [ -n "$OPT_FILE" ]; then
    user_file "$OPT_FILE" || die "could not read $OPT_FILE"
    doc="$(cat -- "$OPT_FILE")"
  else
    doc="$(cat)"
  fi

  # One jq parse before any field check: malformed JSON is refused here,
  # with a message, instead of producing a half-written config.
  doc="$(printf '%s' "$doc" | jq -c .)" || die "the setup document is not valid JSON"

  local name display_name repository schedule preset
  name="$(jq -r '.name // ""' <<<"$doc")"
  [ -n "$name" ] || die "the setup document has no name"
  case "$name" in
    *[$'\n\r']*) die "name contains a newline" ;;
  esac
  printf '%s' "$name" | jq -e 'test("^[A-Za-z0-9][A-Za-z0-9._-]*$")' >/dev/null 2>&1 \
    || die "name must start with a letter or digit, and contain only letters, digits, dashes, dots and underscores"

  repository="$(jq -r '.repository // ""' <<<"$doc")"
  [ -n "$repository" ] || die "the setup document has no repository"
  case "$repository" in
    *[$'\n\r']*)
      die "repository contains a newline; refusing to write it into a unit file" ;;
  esac

  display_name="$(jq -r '.display_name // ""' <<<"$doc")"
  display_name="$(printf '%s' "$display_name" | tr -d '\r\n')"
  [ -n "$display_name" ] || display_name="$name"

  schedule="$(jq -r '.schedule // ""' <<<"$doc")"
  if [ -n "$schedule" ] && [ "$schedule" != "manual" ]; then
    if preset="$(apply_setup_preset "$schedule")"; then
      schedule="$preset"
    else
      check_unit_values "$name" "$schedule" ""
    fi
  else
    schedule=""
  fi

  # The starter configuration when there is nothing yet, the real one
  # otherwise. On a fresh start the placeholder destination is replaced
  # outright -- it only exists to be pointed somewhere, and leaving it in
  # place means the panel lists a destination that cannot work.
  local fresh=0
  if ! user_file "$CONFIG_FILE"; then
    config_dir_secure
    starter_config | write_private "$CONFIG_FILE" || die "could not write $CONFIG_FILE"
    fresh=1
  fi
  load_config

  local obj
  obj="$(jq -cn --arg n "$name" --arg dn "$display_name" --arg r "$repository" --arg s "$schedule" \
    '{name: $n, display_name: $dn, repository: $r} + (if $s == "" then {} else {schedule: $s} end)')"
  if [ "$fresh" = "1" ]; then
    CONFIG_JSON="$(jq --argjson d "$obj" '.destinations = [$d]' <<<"$CONFIG_JSON")" \
      || die "could not set the destination in the configuration"
  else
    CONFIG_JSON="$(jq --argjson d "$obj" \
      '(.destinations = ((.destinations // []) | map(select(.name != $d.name)) + [$d]))' <<<"$CONFIG_JSON")" \
      || die "could not merge the destination into the configuration"
  fi
  write_private "$CONFIG_FILE" <<<"$CONFIG_JSON" || die "could not write $CONFIG_FILE"
  load_config
  select_destination "$name"

  # The key, if the document brought one and the destination has no password
  # source of its own. Straight into a 600 file -- the password never
  # touches a command line and never lands in config.json itself.
  local password keypath
  password="$(jq -r '.password // ""' <<<"$doc")"
  if [ -n "$(trim "$password")" ] && [ -z "$(dest '.password_file // empty')" ] \
     && [ -z "$(dest '.password_command // empty')" ]; then
    keypath="$CONFIG_DIR/$DEST_NAME.key"
    printf '%s\n' "$(trim "$password")" | write_private "$keypath" || die "could not write $keypath"
    cp -- "$CONFIG_FILE" "$CONFIG_FILE.bak" 2>/dev/null || true
    jq --arg n "$DEST_NAME" --arg p "$keypath" \
      '(.destinations[] | select(.name == $n) | .password_file) = $p' <<<"$CONFIG_JSON" \
      | write_private "$CONFIG_FILE" || die "could not record password_file in $CONFIG_FILE"
    CONFIG_JSON="$(jq --arg n "$DEST_NAME" --arg p "$keypath" \
      '(.destinations[] | select(.name == $n) | .password_file) = $p' <<<"$CONFIG_JSON")"
    printf 'Key written to %s (mode 600).\n' "$keypath"
  fi

  if [ -z "$(dest '.password_file // empty')" ] && [ -z "$(dest '.password_command // empty')" ] \
     && [ -z "$(trim "$password")" ]; then
    die "no password for $DEST_NAME -- the setup document needs a password field, or run omarchy-time-machine key set --dest $DEST_NAME first"
  fi

  # The repository, if it does not exist yet. restic init on an existing repo
  # is refused with "config file already exists" -- that is the second run of
  # setup, not a failure. A wrong password on an existing repo is the one
  # case that needs a different message.
  if restic_run snapshots >/dev/null 2>&1; then
    printf 'The repository already exists -- keeping it.\n'
  elif restic_run init >/dev/null; then
    printf 'Repository created at %s.\n' "$repository"
  elif restic_run cat config >/dev/null 2>&1; then
    printf 'The repository already exists -- keeping it.\n'
  else
    die "could not open or create the repository at $repository -- check the path, and the password if the repository exists elsewhere"
  fi

  cmd_install
  printf '\nSetup complete. The timer handles the schedule from here; the panel shows the state of every run.\n'
}

# ---------------------------------------------------------------------------
# systemd
# ---------------------------------------------------------------------------''',
"guided setup: starter_config + presets + cmd_apply_setup")

# --- dispatch + usage -----------------------------------------------------------
rep(CLI,
r'''    config) cmd_config "$@" ;;''',
r'''    apply-setup) cmd_apply_setup "$@" ;;
    config) cmd_config "$@" ;;''',
"dispatch: apply-setup")

rep(CLI,
r'''  install                             (re)write and enable the systemd units''',
r'''  install                             (re)write and enable the systemd units
  apply-setup [--file PATH]           guided setup: JSON on stdin becomes a
                                      config, a key, a repository and timers''',
"usage: apply-setup")

# --- tests ----------------------------------------------------------------------
rep(TESTS,
r'''# --- result ----------------------------------------------------------------''',
r'''# --- guided setup ------------------------------------------------------------

group "apply-setup"

# The whole first-run path in one command: a setup document on stdin becomes
# a merged config.json, a 600 key file, a created repository and enabled
# units. install exits non-zero under the redirected XDG_CONFIG_HOME, so what
# is under test is the output, not the exit status.
OUT="$(printf '%s' '{"name":"setup-test","display_name":"Setup test","repository":"'"$WORK"'/setup-repo","schedule":"daily","password":"setup-password"}' | $CLI apply-setup 2>&1)"
grep -q "Key written to" <<<"$OUT"
check $? "apply-setup installs the key from the document"
grep -q "Repository created" <<<"$OUT"
check $? "apply-setup creates the repository"
[ "$(stat -c %a "$XDG_CONFIG_HOME/omarchy-time-machine/setup-test.key")" = "600" ]
check $? "the key file is 600"
[ -f "$XDG_CONFIG_HOME/systemd/user/omarchy-time-machine@setup-test.timer" ]
check $? "apply-setup writes the timer"
jq -e '.destinations[] | select(.name == "setup-test")' "$XDG_CONFIG_HOME/omarchy-time-machine/config.json" >/dev/null
check $? "apply-setup merges the destination into config.json"

# Applying twice corrects instead of duplicating: the repository already
# exists, the destination is replaced by name.
OUT="$(printf '%s' '{"name":"setup-test","repository":"'"$WORK"'/setup-repo","schedule":"daily","password":"setup-password"}' | $CLI apply-setup 2>&1)"
grep -q "already exists" <<<"$OUT"
check $? "a second apply keeps the repository"
[ "$(jq '.destinations | map(select(.name == "setup-test")) | length' "$XDG_CONFIG_HOME/omarchy-time-machine/config.json")" = "1" ]
check $? "a second apply does not duplicate the destination"

# Malformed JSON, a newline in the repository, a newline in the schedule, a
# name with a space and a destination with no password are all refused with a
# message, before anything the user would have to untangle is written.
OUT="$(printf '%s' '{oops' | $CLI apply-setup 2>&1)"
grep -q "not valid JSON" <<<"$OUT"
check $? "apply-setup refuses malformed JSON"

OUT="$(printf '%s' '{"name":"x","repository":"a\nb"}' | $CLI apply-setup 2>&1)"
grep -q "newline" <<<"$OUT"
check $? "apply-setup refuses a newline in the repository"

OUT="$(printf '%s' '{"name":"x","repository":"/tmp/r","schedule":"daily\nrm"}' | $CLI apply-setup 2>&1)"
grep -q "calendar" <<<"$OUT"
check $? "apply-setup refuses a newline in the schedule"

OUT="$(printf '%s' '{"name":"two words","repository":"/tmp/r"}' | $CLI apply-setup 2>&1)"
grep -q "name must" <<<"$OUT"
check $? "apply-setup refuses a name with a space"

OUT="$(printf '%s' '{"name":"nopass","repository":"'"$WORK"'/nopass-repo"}' | $CLI apply-setup 2>&1)"
grep -q "no password" <<<"$OUT"
check $? "apply-setup refuses a destination with no password"

cp "$WORK/config.bak" "$CONFIG"
$CLI install >/dev/null 2>&1 || true

# --- result ----------------------------------------------------------------''',
"tests: apply-setup group")

print("all edits applied")
