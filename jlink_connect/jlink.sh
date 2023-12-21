#! /bin/sh

coreid=$1

if [ ${coreid} -ge 1 -a ${coreid} -le 7 ]; then
echo "connect to core${coreid}"
JLinkExe -JLinkScriptFile cortexa53_connect_core${coreid}.script -device CORTEX-A53 -if JTAG -jtagconf -1,-1 -speed 15000 -autoconnect 1
else
echo "connect to core0"
JLinkExe -device CORTEX-A53 -if JTAG -jtagconf -1,-1 -speed 15000 -autoconnect 1
fi

