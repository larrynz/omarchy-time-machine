#!/usr/bin/env bash
check_sched() {
  local v="$1"
  case "$v" in
    *[!-A-Za-z0-9*:.,~/[:space:]]*) printf '%-24s : caught\n' "$(printf '%s' "$v" | tr '\n' '@')" ;;
    *)                              printf '%-24s : clean\n' "$v" ;;
  esac
}
check_delay() {
  local v="$1"
  case "$v" in
    *[!-0-9A-Za-z[:space:]]*)       printf '%-24s : caught\n' "$(printf '%s' "$v" | tr '\n' '@')" ;;
    *)                              printf '%-24s : clean\n' "$v" ;;
  esac
}

check_sched 'abc'
check_sched 'a
b'
check_sched '*-*-* 03:00:00'
check_sched '*-*-* 03:00:00/60'
check_sched '*-*-~ 03:00:00'
check_sched 'Manually/5min'
check_sched $'tab\tsep'
check_delay '15m'
check_delay '2h30m'
check_delay '15m
Nice=-20'
check_delay '-20'
