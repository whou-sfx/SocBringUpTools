#!/bin/bash
shopt -s xpg_echo expand_aliases

# ./jlink_load_scipts.sh --file=load_bl2.scripts

usage="Usage: $0 [... optional args ...]
\n
\nBuild asic Images for sfx cards
\n
\nGeneric Options:
\n\t[-h|--help]\t\tPrints this help-text
\n\t[--file]\t\tJlinks commands scripts file
\n"

CFG_FILE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --file*)     CFG_FILE=`echo $1 | sed -e 's/.*=//'` ;;
        -h|--help) echo $usage; exit 0 ;;
        *) echo "Error: unsupported arg: $1"; echo $usage; exit 1 ;;
    esac
    shift
done


JLinkExe -device CORTEX-A53 -if JTAG -speed 15000 -jtagconf -1,-1 -autoconnect 1 -CommandFile $CFG_FILE -nogui 1

