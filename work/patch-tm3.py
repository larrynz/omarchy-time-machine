#!/usr/bin/env python3
import sys

path = "bin/omarchy-time-machine"
with open(path) as f:
    src = f.read()

old = r'''  [[ "$schedule" == *[!A-Za-z0-9*:.,~/ -]* ]] &&
    die "schedule of $name contains characters a calendar spec cannot use; refusing to write them into a unit file"
  [[ "$delay" == *[!0-9A-Za-z ]* ]] &&
    die "randomized_delay of $name contains characters a time span cannot use; refusing to write them into a unit file"'''
new = r'''  # case, not [[ ]]: a literal space inside a bracket class is a syntax error
  # in bash conditional expressions, and [:space:] is the one way to say it.
  case "$schedule" in
    *[!-A-Za-z0-9*:.,~/[:space:]]*)
      die "schedule of $name contains characters a calendar spec cannot use; refusing to write them into a unit file" ;;
  esac
  case "$delay" in
    *[!-0-9A-Za-z[:space:]]*)
      die "randomized_delay of $name contains characters a time span cannot use; refusing to write them into a unit file" ;;
  esac'''

n = src.count(old)
if n != 1:
    print(f"FAIL: found {n} occurrences"); sys.exit(1)
with open(path, "w") as f:
    f.write(src.replace(old, new))
print("ok   F2: case-based checks")
