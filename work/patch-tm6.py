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

# --- Fix 2: the "no key file" error names both routes --------------------------
rep(CLI,
r'''    die "no key file at $password_file, run: omarchy-time-machine key set --dest $DEST_NAME"''',
r'''    die "no key file at $password_file, run: omarchy-time-machine key set --dest $DEST_NAME, or set password_command in the config if the destination fetches its own password"''',
"fix2: no-key-file names both routes")

# --- Fix 1: init ends by naming the next step ----------------------------------
rep(CLI,
r'''  restic_run init || return 1
  printf '\n'
  key_warning
}''',
r'''  restic_run init || return 1
  printf '\n'
  key_warning
  printf 'Now run: omarchy-time-machine install to switch on the schedule.\n'
}''',
"fix1: init names the next step")

# --- Fix 5: the key warning is password_command-aware --------------------------
rep(CLI,
r"""key_warning() {
  cat <<'TEXT'""",
r"""key_warning() {
  if [ -n "$(dest '.password_command // empty' 2>/dev/null)" ]; then
    cat <<'TEXT'
── Where this password lives ───────────────────────────────────────
This destination fetches its password with password_command, so there
is no key file to save anywhere. The password lives wherever that
command gets it -- in pass, your existing secret store. The recovery
plan for this backup is whatever discipline you already have for that
store.
────────────────────────────────────────────────────────────────────
TEXT
    return 0
  fi
  cat <<'TEXT'""",
"fix5: key_warning knows about password_command")

# --- Fix 3 + 4a: install validates pre_command and names unreadable sources ----
rep(CLI,
r'''cmd_install() {
  load_config
  mkdir -p -- "$SYSTEMD_DIR"
''',
r'''cmd_install() {
  load_config
  mkdir -p -- "$SYSTEMD_DIR"

  # Name the source directories the backup will not be able to read, before
  # the first run finds out the hard way with a half-failed snapshot. A
  # warning, not a refusal: everything readable still gets backed up, and
  # the directories might be somebody else's problem to fix.
  unreadable=""
  while IFS= read -r src; do
    [ -n "$src" ] || continue
    src="$(expand_tilde "$src")"
    [ -d "$src" ] || continue
    found="$(find "$src" -type d \! -readable 2>/dev/null | head -5)"
    if [ -n "$found" ]; then
      unreadable="$unreadable$found
"
    fi
  done < <(cfg 'if (.source | type) == "array" then .source[] else (.source // empty) end' 2>/dev/null)
  if [ -n "$unreadable" ]; then
    printf 'Warning: the backup will not be able to read:\n%s' "$unreadable"
    printf 'Everything readable still gets backed up, but runs with unreadable files count as failed.\n'
    printf 'An ACL fixes it without touching ownership: setfacl -R -m u:%s:rX <dir> (plus -d for future files), or exclude the directory.\n\n' "$USER"
  fi

  # A pre_command that starts a systemd unit which does not exist fails every
  # run. Catch that at install time, where fixing it is cheap, instead of at
  # 3am or on the first manual run. Checked for every scheduled destination
  # before anything is written, so a refusal leaves nothing half-installed.
  while IFS= read -r name; do
    [ -n "$name" ] || continue
    [ -n "$(jq -r --arg n "$name" '.destinations[] | select(.name==$n) | .schedule // ""' <<<"$CONFIG_JSON")" ] || continue
    pc="$(jq -r --arg n "$name" '.destinations[] | select(.name==$n) | .pre_command // ""' <<<"$CONFIG_JSON")"
    unit_name="$(printf '%s' "$pc" | sed -n 's/^systemctl --user \(start\|restart\) \([^[:space:]]*\).*/\2/p')"
    if [ -n "$unit_name" ] && ! systemctl --user cat "$unit_name" >/dev/null 2>&1; then
      die "pre_command of $name starts $unit_name, which does not exist -- create the unit or change pre_command (an fstab automount needs no unit at all; see the README)"
    fi
  done < <(cfg '.destinations[].name')
''',
"fix3+4a: install preflight + pre_command validation")

# --- Fix 4b: the exit-3 log line says the snapshot was still written -----------
rep(CLI,
r'''      reason="$(unreadable_reason)"
      [ -n "$reason" ] || reason="some files could not be read"
      log_line "Backup failed: $reason"''',
r'''      reason="$(unreadable_reason)"
      [ -n "$reason" ] || reason="some files could not be read"
      log_line "Backup finished with gaps: $reason"
      log_line "A snapshot was still written and covers everything readable -- fix the cause and the next run goes green."''',
"fix4b: exit-3 wording says the snapshot exists")

# --- Fix 9: a one-version backup of config.json on every write ------------------
rep(CLI,
r'''      if [ -z "$(dest '.password_file // empty')" ]; then
        jq --arg n "$DEST_NAME" --arg p "$path" ''' + chr(92),
r'''      if [ -z "$(dest '.password_file // empty')" ]; then
        cp -- "$CONFIG_FILE" "$CONFIG_FILE.bak" 2>/dev/null || true
        jq --arg n "$DEST_NAME" --arg p "$path" ''' + chr(92),
"fix9: config.json.bak on write")

# --- Tests: pre_command validation + unreadable-source preflight ---------------
rep(TESTS,
r'''if command -v systemd-analyze >/dev/null 2>&1; then
  (cd "$XDG_CONFIG_HOME/systemd/user" && systemd-analyze --user verify ./omarchy-time-machine@.service >/dev/null 2>&1)
  check $? "systemd accepts the generated service"
fi''',
r'''if command -v systemd-analyze >/dev/null 2>&1; then
  (cd "$XDG_CONFIG_HOME/systemd/user" && systemd-analyze --user verify ./omarchy-time-machine@.service >/dev/null 2>&1)
  check $? "systemd accepts the generated service"
fi

# A pre_command that starts a systemd unit which does not exist fails every
# run. install catches that before anything is written -- the refusal has to
# name the unit and leave nothing half-installed.
jq '.destinations[0].pre_command = "systemctl --user start mount-backup-disk"' "$CONFIG" > "$CONFIG.n" && mv "$CONFIG.n" "$CONFIG"
OUT="$($CLI install 2>&1)"
grep -q "mount-backup-disk" <<<"$OUT" && grep -q "which does not exist" <<<"$OUT"
check $? "install refuses a pre_command that names a missing unit"
cp "$WORK/config.bak" "$CONFIG"

# The backup cannot read what the user cannot. install names those
# directories before the first run finds out with a half-failed snapshot.
mkdir -p "$WORK/src/secret" && chmod 000 "$WORK/src/secret"
OUT="$($CLI install 2>&1)"
grep -q "will not be able to read" <<<"$OUT" && grep -q "secret" <<<"$OUT"
check $? "install names unreadable source directories before the first run"
chmod 755 "$WORK/src/secret"''',
"tests: pre_command validation + preflight")

print("all edits applied")
