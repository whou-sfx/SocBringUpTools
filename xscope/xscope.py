#!/usr/bin/python
################################################################################
#  
################################################################################
import argparse
import os.path
import sys
import re
initPath = os.getcwd()
sys.path.append(".")
from xscope_quince.xconsole import XConsole

################################################################################
# Main
################################################################################
#Parse command line arguments
parser = argparse.ArgumentParser()
parser.add_argument("--script", help="Init script")
parser.add_argument("--boots", help="boots args")
parser.add_argument("--pciPort", help="pci port info")
parser.add_argument("--read_jscript", help="Jlink read script")
parser.add_argument("--write_jscript", help="Jlink write script")
parser.add_argument("--set_dev", help="set nvme device")
parser.add_argument("--set_slot", help="set PCIe slot")
parser.add_argument("--cmd", help="Run command then exit")
args = parser.parse_args()
#print args.echo
pcimemFile = os.path.join(os.path.dirname(os.path.join(initPath, sys.argv[0])), 'pcimem')
os.chdir(os.path.dirname(pcimemFile))
if not os.path.exists(pcimemFile):
    os.system('make')
if args.pciPort:
    console = XConsole("Xscope 0.1.0\nCopyright (C) Scaleflux Inc. 2021\n", "XScope> ", pciPort=args.pciPort, dev=args.set_dev, slot=args.set_slot)
else:
    console = XConsole("Xscope 0.1.0\nCopyright (C) Scaleflux Inc. 2021\n", "XScope> ")

########PROCESS Command######################################################
if args.read_jscript:
    console.do_jlink_script_read(args.read_jscript)
    sys.exit()

if args.write_jscript:
    console.do_jlink_script_write(args.write_jscript)
    sys.exit()

if args.set_dev:
    print("xscope dev name: "), args.set_dev
    pattern = '^nvme\d+$'
    patternMode = re.compile(pattern)
    if patternMode.search(args.set_dev):
        console.onecmd('set_dev ' + args.set_dev)
    else:
        print("input invalid dev, example: nvme0")
        sys.exit()

if args.set_slot:
    print("xscope slot name: "), args.set_slot
    console.onecmd('set_slot ' + args.set_slot)

if args.cmd:
    console.onecmd(args.cmd)
    sys.exit()

########CMD LOOP ###############################################################
console.cmdloop()

