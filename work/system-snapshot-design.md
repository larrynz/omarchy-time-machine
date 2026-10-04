# System snapshots: pair a bootable rollback point with each backup

Status: implemented (CLI + tests + README + panel), design report and code on
branch work-notes; test suite 163 passed, 0 failed.

## The feature

A per-destination toggle in the setup form — **System snapshot**, off by
default. When on, every scheduled backup first creates a system snapshot with
Omarchy's own `omarchy-snapshot create`, so each backup is paired with a
bootable "system as it backed itself up" rollback point in the limine boot
menu, exactly like an update-time snapshot.

The snapshot step can never fail the backup, and never blocks it for long:
one attempt, a 120-second timeout, a classified verdict in `status.json`, and
the restic run proceeds whatever the verdict was.

## The sudo design (the settled decision)

The whole command runs under `sudo -n`, not the `sudo snapper` calls it makes
internally:

```
timeout "$SYSTEM_SNAPSHOT_TIMEOUT" sudo -n -- /usr/bin/omarchy-snapshot create
```

The prerequisite is a single exact-argv sudoers line (arguments in a rule mean
exact match — no wildcards, no `snapper delete` reachable):

```
youruser ALL=(root) NOPASSWD: /usr/bin/omarchy-snapshot create
```

Properties, verified on the box:

- `sudo` never prompts root, so the internal `sudo snapper create/cleanup`
  calls need no rules of their own — there are no NOPASSWD entries for
  snapper at all.
- `restore` — the destructive sibling, which runs `limine-snapper-restore` —
  can never be invoked through this grant.
- `/usr/bin/omarchy-snapshot` is a root-owned package file (0755, identical to
  `/usr/share/omarchy/bin/omarchy-snapshot`), and every helper it calls
  (`omarchy-cmd-missing`, `omarchy-version`, `snapper`, `awk`) also exists in
  `/usr/bin`, so it resolves under both the unit's PATH and sudo's
  `secure_path`.
- Without the rule, `sudo -n` refuses instantly ("a password is required") —
  which is the `needs-sudo` verdict, not a hang and not a failed backup.

**Why no time window** (asked and answered): sudoers cannot express "when",
and a simulated window — installing/removing the rule around 3AM, the way
`omarchy-sudo-passwordless` does — defends against the wrong threat (local
processes can fire during the window) and breaks `Persistent=true` catch-up,
which runs at *login*, outside any 3AM window. Locking *what* (one fixed-argv,
non-destructive subcommand) is the real control; the always-on residual is
"anyone can create a snapshot", which number cleanup caps at 5 anyway.

## Post-implementation addendum: the copy in the backup

The original design paired a snapshot with each backup and stopped there.
After a review of what the pairing actually protects, the scope grew one
step: the backup also stores a copy of the snapshot it just took.

The snapshot lives on the same disk as the system, so a pairing alone dies
with the disk. The copy makes the system's installed state part of the
backup itself, and deleting the backup deletes the copy with it, which the
Manage Backups confirmation already spells out.

The design that makes the copy possible, all covered by the suite:

- **The two snapper lines** (`ALLOW_GROUPS="wheel"`, `SYNC_ACL="yes"` in
  `/etc/snapper/configs/root`) let the backup read the newest snapshot as
  the user. Snapper applies the ACL to snapshots created after SYNC_ACL is
  set, so the next backup picks it up with no further steps.
  `work/snapper-acl-wizard.sh` sets the lines up and verifies the result.
- **The path comes from the directory, not the command**: the snapshot
  command prints nothing, so `system_snapshot_path` reads the newest entry
  under the snapshots dir (SNAPSHOT_DIR inside SUBVOLUME from the config,
  default `/.snapshots`). `OMARCHY_SNAPSHOT_DIR` overrides it in tests.
- **A copy that cannot be read is not a copy**: `system_snapshot_readable`
  requires a non-empty readable directory, because an unmounted snapshot
  subvolume reads as an empty folder and copying air would look exactly
  like a copy that worked. When the read fails, the verdict says so and
  the reason names the fix.
- **Root-only files are excluded by name**: the files inside the snapshot
  that even the group ACL leaves closed (shadow, host keys, /root) are
  collected before the run and handed to restic as `--exclude` arguments
  before the `--` separator, where everything after `--` is a path. The
  backup runs as the user, and restic reports unreadable paths as errors,
  so without this the copy would fail every run.
- **The audit counts the copy as a source**: the copy path joins the
  audit's source walk, and its root-only files classify as by-design, the
  same as any other path the user cannot reach. On an on-demand audit no
  copy ran and the copy's paths are extra snapshot content the diff never
  checks, so nothing about it shows up there.
- **The package cache rides along**: the copy brings
  `/var/cache/pacman/pkg` into the backup, which turns over constantly;
  the README tells the user to add it to the exclude file when the setting
  is on.

The real-box check is the wizard: it sets up the lines, creates a snapshot
passwordless through the sudoers line, and verifies the tree is readable
and that root-only files stay closed.

## Verdicts

| Verdict | Detection |
|---|---|
| `created` | exit 0 |
| `needs-sudo` | stderr matches "a password is required" / "a terminal is required" |
| `snapper-unconfigured` | stderr contains "No Snapper configs" (script exits 1) |
| `snapper-missing` | exit 127 (the script's own code for no snapper binary) |
| `failed` | timeout, or anything else; reason = first output line, ANSI stripped |
| `unavailable` | `omarchy-snapshot` not found (non-Omarchy box) — the toggle is greyed out |

`needs-sudo` carries an actionable reason: "passwordless sudo for
omarchy-snapshot is required; see System snapshots in the README".

## Scheduling semantics (the three scenarios)

| Scenario | What happens |
|---|---|
| Machine off at 3AM | Boot is unaffected — nothing in the feature touches boot. The missed run catches up **at next login** (`Persistent=true`); the snapshot and backup then describe that moment, as a consistent pair |
| On, logged in at 3AM | Timer fires 3:00–3:15 (`RandomizedDelaySec`); with the sudoers line → `created`; without → `needs-sudo`. Being logged in does not help sudo: the service has no TTY and sudo's cache is per-TTY |
| On, not logged in | Nothing at 3AM — `Linger=no` is the Omarchy default, so no user manager runs. Catch-up at next login. With linger on, identical to the logged-in case; headless-safe precisely because nothing needs a prompt |

## Honest downsides (all stated in the README)

1. The NOPASSWD line is a real, if modest, security-tradeoff: every process
   running as the user gains passwordless `omarchy-snapshot create`. Scoped to
   the least-destructive thing the command can do.
2. Snapshot history is shallow and shared: snapper's `NUMBER_LIMIT=5` is the
   same pool omarchy-update draws from, so paired snapshots rotate out within
   days. The promise is "a recent rollback point", not "the system state at
   every backup I keep"; raise NUMBER_LIMIT for the latter.
3. Boot-menu entries are indistinguishable from update snapshots (the script
   labels both with the Omarchy version). The plugin correlates by timestamp.
4. On a stock box without the sudoers line, every run records `needs-sudo` —
   the toggle looks on but nothing happens at 3AM. Mitigated by the
   actionable reason string; the future pkexec one-click helper (optional
   polish, not v1) would install the sudoers line from a desktop click.

## CLI surface

- Config: `system_snapshot` (boolean) on a destination; `apply-setup` writes
  it when the document carries it, preserves it when the document omits it;
  `config_problem` rejects non-boolean values.
- `status --json`: per destination `system_snapshot_enabled` (from config) and
  `last_run.system_snapshot` (from the run); global
  `system_snapshot_available` (does `omarchy-snapshot` exist — the probe the
  form uses to grey the toggle on non-Omarchy boxes).
- `record_status` gains two args (result, reason); the verdict lands inside
  `last_run`, so the panel gets it through the existing `$stored` passthrough.
- `OMARCHY_SNAPSHOT_CMD` env override picks the command handed to `sudo -n` —
  test-suite hook only; the sudoers line still gates what can actually run.

## Test plan (test/run-tests.sh, group "System snapshot")

Fake `omarchy-snapshot` via `OMARCHY_SNAPSHOT_CMD`, `SYSTEM_SNAPSHOT_TIMEOUT=1`:
`created` on exit 0; `needs-sudo` (backup still green); `snapper-missing`
(127); `snapper-unconfigured` (message sniff); timeout → `failed`; `unavailable`
when the override points nowhere; dry-run skips the snapshot entirely;
apply-setup round-trip (write, preserve-on-omit, refuse non-boolean).
