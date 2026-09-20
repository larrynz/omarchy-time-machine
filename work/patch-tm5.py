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

TESTS = "test/run-tests.sh"

rep(TESTS,
r'''# The other half of that rule: a destination that fetches its own password
# works with no key file at all -- which is what proves restic is reading it
# from the command, not from the file this test just removed.
jq '.destinations[0].password_command = "echo test-password"' "$CONFIG" > "$CONFIG.n" && mv "$CONFIG.n" "$CONFIG"
rm -f "$XDG_CONFIG_HOME/omarchy-time-machine/test.key"''',
r'''# The other half of that rule: a destination that fetches its own password
# works with no key file and no password_file -- which is what proves restic
# is reading it from the command. key set recorded password_file in the
# config earlier, so the test deletes it; leaving it set would trip the
# exclusivity check instead of exercising the command.
jq '.destinations[0].password_command = "echo test-password"
    | del(.destinations[0].password_file)' "$CONFIG" > "$CONFIG.n" && mv "$CONFIG.n" "$CONFIG"
rm -f "$XDG_CONFIG_HOME/omarchy-time-machine/test.key"''',
"TESTS: del password_file")

print("all edits applied")
