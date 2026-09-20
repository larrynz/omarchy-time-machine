# Task State: omarchy-time-machine security review

## Status: COMPLETE (both parts committed, pushed, deployed)

## Commits (branch fix/security-review, pushed to larrynz/omarchy-time-machine)
- `eadfb49` "Make the setup path fail loudly and early" (Part A)
- `b89db98` "Add the guided setup: one form, one command" (Part B)
- Base: `94bc1ce`

## Part A (setup path fail-early) — DONE, 98 tests passed at commit time
1. `cmd_init` ends by naming the next command: "Now run: omarchy-time-machine install to switch on the schedule."
2. The no-key-file error names BOTH routes: `key set` OR `password_command` in the config.
3. `cmd_install` refuses a `pre_command` that starts a systemd user unit which does not exist — checked for every scheduled destination BEFORE anything is written (loop with jq, not `dest` — cmd_install never calls select_destination).
4. `cmd_install` preflight names unreadable source directories (`find "$src" -type d \! -readable | head -5`) before the first run, with the setfacl ACL fix in the message. Warning, not refusal.
5. `key_warning` is password_command-aware: a "Where this password lives" heredoc variant for destinations that fetch their own password.
6. Exit-3 log line: "Backup finished with gaps: $reason" + "A snapshot was still written and covers everything readable -- fix the cause and the next run goes green."
7. `config.json.bak` one-version backup on every config write (in the key-set password_file recording block).
Tests: pre_command validation + preflight (chmod 000 dir in $WORK/src) in test/run-tests.sh after the systemd-analyze test.

## Part B (guided setup) — DONE, 110 tests passed at commit time
1. **CLI `apply-setup`** (`cmd_apply_setup` in bin/omarchy-time-machine):
   - Reads JSON on stdin (or --file): `{name, display_name, repository, schedule, password}`.
   - Password via stdin — NEVER a command line (/proc/PID/cmdline).
   - Validates: name via `jq -en --arg n "$name" '$n | test("^[A-Za-z0-9][A-Za-z0-9._-]*$")'` (NOTE: raw name piped to jq fails — jq parses input as JSON; must use --arg + -n); newline checks on name/repository; schedule presets (hourly/daily/weekly/monthly → calendar exprs via `apply_setup_preset`) or raw spec via `check_unit_values` or manual/empty → no timer.
   - Fresh config → starter written via extracted `starter_config()` (shared with `config create`), destinations = [$obj] outright (placeholder replaced); existing config → merge replace-by-name.
   - Key install from `.password` field → 600 file + password_file recorded (+ config.json.bak).
   - `restic_context` called before init (sets RESTIC_REPOSITORY; falls back to $CONFIG_DIR/$DEST_NAME.key which the key install just wrote).
   - Init distinction: snapshots OK → "already exists -- keeping it"; init OK → "Repository created at"; init fails + `restic_run cat config` OK → "already exists"; else die (wrong password/path).
   - No password anywhere + no source → die "no password for $DEST_NAME...".
   - Then `cmd_install` + "Setup complete." line.
   - `parse_options` gained `--file`/`--password-file` cases; dispatch + usage updated.
2. **QML SetupScreen** (Panel.qml + TimeMachineStore.qml):
   - `property bool settingUp: false` + `setupValidationError` + `setupSchedule` ("daily") on Panel root.
   - Store: `setupBusy/setupError/setupDone/setupPendingDoc` + `applySetup(doc)` + `applyProc` (Process).
   - **CRITICAL quickshell semantics** (official docs verified): `Process.write()` "Does nothing if running is false" → the doc is written on the `onStarted` signal, NOT before `running = true`.
   - stdout collector trims the systemctl timer table (keeps pre-table lines + the "Setup complete" line); stderr → setupError (plain()ed, urgent color).
   - Setup view: Flickable+Column form — Name/Repository/Password TextFields (accent border on focus), Schedule preset-cycle MenuRow, validation error, CLI error, busy + result texts, Apply/Cancel MenuRows.
   - keyCatcher `blocked: root.browsing || root.settingUp`; Escape backs out; focus handoff onSettingUpChanged → setupName.forceActiveFocus().
   - Entry point: unconfigured → "Set Up Backups…" → settingUp = true (panel stays open); hint: "Set one up below and the panel walks you through it".
   - desiredWidth 420 for setup; contentHeight uses setupColumn.implicitHeight.
3. Tests: "apply-setup" group at suite end (valid apply: key 600 + repo created + timer + merge; second apply idempotent; malformed JSON; newline in repository; newline in schedule; name with space; no password; cleanup restore + reinstall).
4. qmllint passes clean (exit 0) on Panel.qml + TimeMachineStore.qml.

## Environment facts
- Real config: `~/.config/omarchy-time-machine/config.json` (NOT the plugins path — earlier summary was wrong). Installed plugin: `~/.config/omarchy/plugins/jankeesvw.time-machine/` (Panel.qml, TimeMachineStore.qml, bin/…, test/…).
- Unit instance = destination name (`omarchy-time-machine@$name.timer`); retention is global (`keep_value` + starter retention object) — no per-destination keep/machine fields needed.
- `restic_run() { restic ${RESTIC_ARGS+...} "$@"; }`; `restic_context` sets RESTIC_REPOSITORY/RESTIC_PASSWORD_FILE + REPO_DISPLAY (sanitized).
- Test env: WORK=mktemp -d, XDG_CONFIG_HOME=$WORK/config, CONFIG=$XDG_CONFIG_HOME/omarchy-time-machine/config.json. install exits non-zero under redirected XDG (enable fails) — known artifact; systemctl list-timers shows the REAL user session's timers (noise in test output).
- die() exits 0 under --json (QML gets {"ok":false}); apply-setup runs WITHOUT --json from QML so exitCode 1 on failure → stderr shown.
- quickshell Process API (verified via /usr/lib/qt6/qml/Quickshell/Io/quickshell-io.qmltypes): running, processId, command, environment, stdout/stderr, stdinEnabled, exited signal; methods exec(list), signal(int), write(QString). NO FileView in quickshell at all → file writing from QML unavailable.
- Patch-script lesson: python r''' strings break on backslash+3quotes adjacency — use `"''' + chr(92)` concatenation; chr(92)/chr(60)/chr(62) for needles.
