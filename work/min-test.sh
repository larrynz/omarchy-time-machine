#!/usr/bin/env bash
case "a b" in *" "*) echo "1 space-glob: ok";; esac
case "a b" in *[!ab]*) echo "2 negated: ok";; esac
case "a b" in *[!ab ]*) echo "3 space-in-class: ok";; esac
case "x" in *[!a~]*) echo "4 tilde-in-class: ok";; esac
case "x" in *[!a-z]*) echo "5 range: ok";; esac
case "x" in *[!a:-]*) echo "6 dash-last: ok";; esac
case "x" in *[-!a:]*) echo "7 dash-first: ok";; esac
