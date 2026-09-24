# Time Machine

Time Machine is a backup plugin for Omarchy. It uses [restic](https://restic.net) to copy your folders to a destination you choose, on a schedule you choose, and it shows one icon in your bar. The icon is green when the latest backup succeeded and red when it did not, so you never have to open anything to know whether your backups are working.

Backups are kept according to a retention schedule: by default 7 daily, 4 weekly, 12 monthly, and 3 yearly snapshots, with older ones pruned automatically. Files can be restored from a backup.

![Time Machine](screenshots/panel.png)

## Install

```bash
sudo pacman -S restic
omarchy plugin add https://github.com/jankeesvw/omarchy-time-machine
omarchy plugin enable jankeesvw.time-machine
omarchy bar move jankeesvw.time-machine --section right
```

restic is the only dependency.

### The command line

Some tasks are easier from a terminal. The plugin's command is not installed on your `PATH`; it lives inside the plugin directory:

```bash
~/.config/omarchy/plugins/jankeesvw.time-machine/bin/omarchy-time-machine
```

Every `omarchy-time-machine ...` example below refers to that path. To type it comfortably, add an alias to your `~/.bashrc`:

```bash
alias omarchy-time-machine=~/.config/omarchy/plugins/jankeesvw.time-machine/bin/omarchy-time-machine
```

## Setting up backups

Click the icon and choose **Setup Backups**. The form has five fields:

1. **Name.** Used for the key file, the systemd unit, and the log directory. Allowed characters are letters, digits, dashes, dots, and underscores, and it must start with a letter or digit.
2. **Repository.** The restic repository that stores your backups, for example `/run/media/you/backup/restic`.
3. **Source folders.** What gets backed up. The form starts with your home folder. **Add folder...** opens a file browser, which also lists hidden folders such as `.config`, because those are backed up too. The × button removes a folder from the list.
4. **Password.** Encrypts the backups. The row under the field chooses how it is stored; see below.
5. **Schedule.** How often backups run. Click the row to cycle through: daily, weekly, monthly, hourly, and custom. The field under it shows the exact time the preset fires, as a systemd `OnCalendar` expression, and it is editable: `*-*-* 03:00:00` can become `*-*-* 05:30:00`, or `Mon..Fri *-*-* 09,17:00:00` for weekdays at 9 and 5. Custom starts with an empty field; leaving it empty means no schedule, so backups run only when started from the panel. The expression is validated when you apply; a typo is refused with a message.

**Apply** does everything in one step: it writes the config, stores the password, creates the repository with `restic init` if needed, and enables the schedule. Applying an existing destination merges by name: the fields you changed are updated and every setting you did not send (retention, `pre_command`, the password source) survives, so small changes never mean retyping everything. **Cancel** closes the form, and everything you typed stays there until you apply it.

With a configuration already in place, the panel offers **Edit Configuration...**. It opens the setup form pre-filled from the first configured destination: name, repository, schedule, folders and password mode. The mode is detected from the config, so no toggling is needed. When the destination fetches its password with a command, that command is shown in the field, ready to edit -- it is not a secret, the config already holds it in plain text. When the destination uses a key file, the field is left empty because the password itself is never shown back, and the stored password is kept unless you type a new one.

If you prefer editing the config directly, choose **Create Configuration** instead. It writes a starter file and opens it in your editor.

## Where backups go

A repository can be a folder, another machine, or cloud storage. Anything restic supports works:

```json
{ "name": "drive",   "repository": "/run/media/you/backup/restic" }
{ "name": "nas",     "repository": "sftp:you@nas:/volume1/backup" }
{ "name": "offsite", "repository": "s3:s3.amazonaws.com/my-bucket" }
```

You can configure any number of destinations. Each one appears in the panel with its own schedule and history.

If the repository URL contains a username and password, percent-encode the password: `p@ss` must be written as `p%40ss`. A raw `@`, `/`, or space makes the URL unreadable to restic.

## The backup password

Backups are encrypted. If a disk is stolen or a storage account is compromised, the data cannot be read without the password.

The password field supports two storage modes, and clicking the row under the field switches between them:

- **Stored in a key file.** The text you type is the password itself. It is written to `~/.config/omarchy-time-machine/<name>.key` with mode 600. It is never written to the config file, and it never appears in a process list.
- **Fetched with a command.** The text you type is a command that prints the password, stored as `password_command` in the config. Examples: `pass show omarchy/backup-drive`, `op read <secret>`, `bw get <item>`. The command runs on this machine whenever a backup runs, so the password manager's CLI must be installed and unlocked here. Scheduled runs have no terminal to prompt in, so the command must answer without asking: keep the agent's passphrase cached or configure loopback pinentry.

Setting both a password and a password command is refused. In the config, only one of these may be set:

```json
{ "name": "backup-drive", "password_file": "~/.config/omarchy-time-machine/backup-drive.key" }
{ "name": "backup-drive", "password_command": "pass show omarchy/backup-drive" }
```

The password encrypts backup contents only. Storage credentials such as S3 access keys belong in the env file described below. Each destination has its own backup password.

### Keep a copy outside this machine

The password is stored in your home folder, and your home folder is a backup source. If the machine is lost, the stored password is lost with it, and nobody can open the backups. Make a second copy now:

```bash
omarchy-time-machine key show --dest backup-drive
```

Save the output in your password manager, or print it and store it somewhere physical.

With 1Password:

```bash
omarchy-time-machine key save-1password --dest backup-drive
```

This creates a vault item named "Time Machine backup key (backup-drive)". It refuses to overwrite an item that already exists under that name.

With `pass`:

```bash
omarchy-time-machine key show --dest backup-drive | pass insert -m omarchy/backup-drive
```

## Extra credentials

Destinations such as S3 or REST servers need more than the backup password. Each destination can have an env file at `~/.config/omarchy-time-machine/<name>.env`, or at the path configured in `secrets_file`, holding `KEY=VALUE` lines. A `${NAME}` in the repository URL is replaced with the value of `NAME` from that file:

```json
{ "name": "offsite", "repository": "s3:s3.amazonaws.com/${bucket}" }
```

Everything in the env file is exported to restic and to every command a backup run spawns, so keep it limited to what the backup needs.

## Restoring files

Click the icon and choose **Restore Files**. Pick a destination and a date, then browse the snapshot like any file listing. Arrow keys move the cursor, Enter opens a folder, and typing filters the list. Switching dates keeps your current folder, which makes it easy to compare two days.

You can restore a single file, or the folder you are currently viewing.

Restored files are written to `~/Restored/`, never over your current files. Move them into place yourself so nothing is replaced by accident. When a restore finishes, a notification appears, and clicking it opens your file manager with the restored file selected.

![Browsing a backup](screenshots/restore.png)

## Settings

Only `name` and `repository` are required. Everything else has a default:

| Setting | Default | Purpose |
|---|---|---|
| `source` | your home folder | What gets backed up: one path, or a list like `["~", "/etc", "/srv/data"]`. If a listed path is missing, the backup fails instead of silently skipping it. Editable in the setup form. |
| `exclude_file` | `excludes.txt` next to the config | Patterns to skip: caches, downloads, VM images. |
| `retention` | 7 daily, 4 weekly, 12 monthly, 3 yearly | Which backups are kept. Older ones are pruned. |
| `schedule` | none | When backups run: a preset word (`daily`, `weekly`, `monthly`, `hourly`) or a systemd `OnCalendar` expression such as `Mon..Fri *-*-* 09,17:00:00`. Without a schedule, backups run only when started from the panel. |
| `display_name` | the `name` | The label shown in the panel. |
| `pre_command` | none | A command that runs before every backup, to mount or wake the destination. |
| `on_failure_command` | none | A command that runs when a backup fails. |

Run `omarchy-time-machine install` after changing a schedule, so the systemd units are rewritten.

Also run it once after updating from a version older than 1.1.0. Timers written before 1.1.0 carried a `Requires=` dependency on the backup service: stopping a running backup also stopped its timer, so no further backups were scheduled. Running `install` rewrites and re-enables the units.

Times use a 24-hour clock. For AM/PM, set `timeFormat` on the widget in `shell.json`:

```json
{ "id": "jankeesvw.time-machine", "timeFormat": "h:mm AP" }
```

### Destinations that are not always available

An external drive may need to be mounted first, or a NAS may be asleep. Set `pre_command` so the backup can reach it:

```json
{ "name": "usb",
  "repository": "/run/media/you/backup/restic",
  "pre_command": "systemctl --user start mount-backup-disk" }
```

The command runs before every backup. It should be quick, and safe to run when the destination is already available.

## Troubleshooting

The panel shows the time of the last failed backup and of the last successful one. For more detail:

```bash
omarchy-time-machine log --dest backup-drive                 # the last run's log
systemctl --user list-timers 'omarchy-time-machine@*'  # upcoming schedules
omarchy-time-machine backup --dest backup-drive --dry-run    # run without writing anything
omarchy-time-machine check --dest backup-drive               # verify backup integrity
```

To list destinations and their last run times:

```
$ omarchy-time-machine destinations
NAME           LABEL                  WHERE                                  SCHEDULE       LAST BACKUP
nas            Office NAS             sftp:me@nas:/volume1/backup            *-*-* 03:00:00 2026-08-25 03:07
usb            USB drive              /run/media/me/backup/restic            on request     2026-08-18 06:50
offsite        Offsite                s3:s3.eu-central-1.amazonaws.com/attic *-*-* 04:30:00 never

35 snapshots, 373 GB stored in total
```

This reads only the config and one local state file, so it answers immediately whether or not the destination is connected.

Run `omarchy-time-machine` with no arguments to list all commands.

## Uninstalling

Removing the plugin leaves your backups, configuration, and schedule in place:

```bash
omarchy plugin remove jankeesvw.time-machine
```

To remove the schedule and the stored settings as well:

```bash
systemctl --user disable --now 'omarchy-time-machine@*.timer'
rm -f ~/.config/systemd/user/omarchy-time-machine*
systemctl --user daemon-reload

rm -rf ~/.config/omarchy-time-machine        # config and backup passwords
rm -rf ~/.local/state/omarchy-time-machine   # run history and logs
```

`~/.config/omarchy-time-machine` holds the backup passwords. Deleting it without another copy makes the backups permanently unreadable. `~/.local/state/omarchy-time-machine` holds run history and thirty days of logs, including the names of files that could not be read.

The backups themselves are never removed by any of these commands. Anyone with the password can still open them.

## Licence

MIT.

`icon.svg` embeds the `fa-history` outline from [Font Awesome Free](https://fontawesome.com), licensed CC BY 4.0.

The wallpaper behind the screenshots is a pattern built from [Heroicons](https://heroicons.com), licensed MIT, Copyright (c) Tailwind Labs, Inc.
