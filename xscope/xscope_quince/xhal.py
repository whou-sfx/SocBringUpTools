from datetime import datetime
import os
import re
import subprocess
import sys
import time
import struct
import math
from .tqdm import tqdm
from ctypes import *
from fcntl import ioctl

from .xreg_for_quince import reg_list as rl

## key:regname, (start,stop, stride)
# reg_list = {
#     'nvme_cmd_mem': (0x10000, 0x14000, 0x40),
#     'nvme_cmdst_mem': (0x16000, 0x17000, 0x10),
#     'nvme_sqst_mem': (0x14000, 0x15000, 0x10),
#     'flash_opst_mem':  (0x17000, 0x19000, 0x20)
#     'flash_opst_mem':  (0x18000, 0x19000, 0x20)
#     }

multi_lun = 1
# enable cheeta version, i.e. two targets only
cheeta = 0 # set to 0 for 4CE, 1 for 2CE.
xi_phy = 1
ch_num = 16
ce_num = 4
lun_num = 1
skip_ch = []
DISK_NAME = "cc53"
pciList = subprocess.run("lspci -D -d '%s': | awk '{print $1}'" % DISK_NAME, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout.decode(errors='ignore').split()
input_args = ' '.join(sys.argv[1:]).split('--')
for arg in input_args:
    arg = arg.strip()
    if 'pciPort' in arg:
        if '=' in arg:
            _pciPort = arg.split('=')[-1]
        else:
            _pciPort = arg.split(" ")[-1]
        break
else:
    _pciPort = None
for arg in input_args:
    arg = arg.strip()
    if 'set_dev' in arg:
        if '=' in arg:
            _dev = arg.split('=')[-1]
        else:
            _dev = arg.split(" ")[-1]
        break
else:
    _dev = None
for arg in input_args:
    arg = arg.strip()
    if 'set_slot' in arg:
        if '=' in arg:
            _slot = arg.split('=')[-1]
        else:
            _slot = arg.split(" ")[-1]
        break
else:
    _slot = None
assert pciList, print("Can't find pci port")
jlink_basic_cmd = 'JLinkExe -device CORTEX-A53 -if JTAG -jtagconf -1,-1 -speed 15000 -autoconnect 1 '
jlink_script_file = 'jlink.jlink'
jlink_output_file = 'jlink.output'

def MDELAY(delay_in_ms):
    ms = delay_in_ms / 1000
    time.sleep(ms)
def DELAY(delay_in_sec):
    time.sleep(delay_in_sec);

class XHal:
    def __init__(self, pciPort=None, dev=None, slot=None):
        if pciPort is None and dev is None and slot is None:
            pciPort, dev, slot = _pciPort, _dev, _slot
        if dev != None:
            self.devName = '/sys/class/nvme/%s/device/resource0' % (dev)
        else:
            self.devName = '/sys/bus/pci/devices/%s/resource0' % (pciList[0])

        if slot != None:
            self.devName = '/sys/bus/pci/devices/0000\:%s/resource0' % (slot)

        if pciPort != None:
            for pciInfo in pciList:
                if ":" not in pciPort:
                    pciPort = '0%s' % (pciPort)
                    if int(pciInfo.split(':')[1], 16) == int(pciPort, 16):
                        pciPort = pciInfo
                        break
                else:
                    pattern = '[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}.[0-9a-fA-F]'
                    patternMode = re.compile(pattern)
                    if patternMode.search(pciPort):
                        if pciInfo == pciPort:
                            pciPort = pciInfo
                            break
                    else:
                        if pciPort in pciInfo:
                            pciPort = pciInfo
                            break
            self.devName = '/sys/bus/pci/devices/%s/resource0' % (pciPort)
        #print("Access:" + self.devName)

    def getvalue(self, data, start_bit, stop_bit, shift=0):
        _val = 0
        _len = stop_bit-start_bit+1
        _val = (data>>start_bit) & ((1<<_len)-1)
        _val = _val << shift
        return _val

    def dump(self, data, field_list):
        for item in field_list:
            if len(item) == 5:
                print("\t%-24s[%3d:%3d]:\t%x"%(item[0], item[2], item[1], self.getvalue(data, item[1], item[2], item[4])))
            else:
                # print "\t%16s  [%3d:%3d]:\t%x"%(item[0], item[2], item[1], self.getvalue(data, item[1], item[2]))
                print("\t%-24s[%3d:%3d]:\t%x"%(item[0], item[2], item[1], self.getvalue(data, item[1], item[2])))
        print()


    # addr, base addr, must be align with stride
    # field_list, [name, start bit, stop bit]
    # stride, size per entry, i.e. 16, 32-bytes
    def _decode(self, name, base_addr, addr, field_list, stride, val, desc=''):
        res = 0
        ''' because the indir rd register is u32, and if wanna read u64 register 
           we need to read twice for the high 32bit and get the result'''
        if int(stride) == 8:
            # base_addr + 4 is the high 32bit
            os.system("sudo ./pcimem %s 0x8000 w %s" % (self.devName, int(base_addr) + 4))
            _val = subprocess.run("sudo ./pcimem %s 0x8008 w" % (self.devName), shell=True, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT).stdout.decode(errors='ignore').strip()
            res = int (_val, 16) << 32 | int (val, 16)
            # print('0x%s: 0x%s 0x%x\n' % (_val, val, res))
        else:
            res = int (val, 16)
        print('0x%08x: %s: 0x%08x  %s' % (base_addr+addr, name, res, desc))
        #_val = hex (_val)
        #print '%x' %_val
        self.dump(res, field_list)

    def decode_obj(self, obj, base_addr, offset, val):
        lines = obj[2].split('\n')
        self._decode(obj[0], base_addr, offset, obj[3], obj[4], val, lines[0])
        rv = obj[4]

        return rv
  
    # read by register name
    def reads(self, name, length=1):
        if name in list(rl.keys()):
            # print 'Read %s %d 0x%08x' % (name, length, reg_list[name][0])
            # self.read(reg_list[name][0], length*reg_list[name][2]/4)
            # print 'Read %s %d 0x%08x %d' % (name, length, rl[name][1], rl[name][3] )
            # print rl[name][0]
            self.read(rl[name][1], length*rl[name][3]/4/8)

        else:
            print("Wrong register name %s!!!!" % name)

    # read by addr
    def read(self, addr=0x8010, length=1, needprint = True):
        #print 'Read 0x%08x'%addr + ' len=%d'%length
        i= 0

        # length is d-word level varible
        os.system("sudo ./pcimem %s 0x8010 w %s" % (self.devName, 0x0))
        while (i < length*4):
            #print(self.devName, addr, length)
            os.system("sudo ./pcimem %s 0x8000 w %s" % (self.devName, int(addr) + i))
            val = subprocess.run("sudo ./pcimem %s 0x8008 w" % (self.devName), shell=True, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT).stdout.decode(errors='ignore').strip()
            #print '%s' %val
            #val = int(val, 16)
            r = 0

            if needprint:
                if ( r == 0 ): # Try generic decoder
                    ret = 0
                    for k,o in list(rl.items()):
                        if ( (addr+i) >= o[0][1][0] and (addr+i)<o[0][1][1]):
                            obj = o[0]
                            break

                    if 'obj' in locals():
                        ret = self.decode_obj(obj, addr, i, val)
                    else:
                    # means the addr don't in xreg_for_quince.py
                        val = int (val, 16)   
                        print('0x%08x: 0x%08x\n' % (int(addr) + i, val))

                    r += ret

            if ( r != 0 ):
                i += r
            else:
            # means the addr don't in xreg_for_quince.py
                i += 4
        return val

    def read_ddr(self, addr, length=1):
        if (addr < 0x70_0000_0000 or addr > 0x70_17C0_0000):
            print("Wrong register addr 0x%x!!!!" % int(addr))
        else:
            os.system("sudo ./pcimem %s 0x8010 w %s" % (self.devName, 0x70))
            i= 0
            while (i < length*4):
                os.system("sudo ./pcimem %s 0x8000 w %s" % (self.devName, int(addr) + i))
                val = subprocess.run("sudo ./pcimem %s 0x8008 w" % (self.devName), shell=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT).stdout.decode(errors='ignore').strip()
                val = int (val, 16)   
                print('0x%08x: 0x%08x' % (int(addr) + i, val))
                i += 4
            return val

    def dump_ddr_to_bin(self, addr, length=1):
        if (addr < 0x70_0000_0000 or addr > 0x70_17C0_0000):
            print("Wrong register addr 0x%x!!!!" % int(addr))
        else:
            ct = time.time()
            secs = (ct - int(ct)) * 1000
            _time_str = time.strftime("%Y-%m-%d_%H-%M-%S-%d", time.localtime()) + '.%s' % secs
            filePath = os.getcwd() + "/"
            dumpfile = filePath + "memorydump%s.bin" % _time_str
            print("%s 0x%s %s" % (dumpfile, hex(addr), length))
            os.system("sudo ./dump_ddr %s %s %s %s 0" % (self.devName, dumpfile, addr, length*4))
    
    def read_sram(self, addr, length=1):
        if (addr < 0x7fe0_0000 or addr > 0x8000_0000):
            print("Wrong register addr 0x%x!!!!" % int(addr))
        else:
            os.system("sudo ./pcimem %s 0x8010 w %s" % (self.devName, 0x0))
            i= 0
            while (i < length*4):
                os.system("sudo ./pcimem %s 0x8000 w %s" % (self.devName, int(addr) + i))
                val = subprocess.run("sudo ./pcimem %s 0x8008 w" % (self.devName), shell=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT).stdout.decode(errors='ignore').strip()
                val = int (val, 16)   
                print('0x%08x: 0x%08x' % (int(addr) + i, val))
                i += 4
            return val
        
    def dump_sram_to_bin(self, addr, length=1):
        if (addr < 0x7fe0_0000 or addr > 0x8000_0000):
            print("Wrong register addr 0x%x!!!!" % int(addr))
        else:
            ct = time.time()
            secs = (ct - int(ct)) * 1000
            _time_str = time.strftime("%Y-%m-%d_%H-%M-%S-%d", time.localtime()) + '.%s' % secs
            filePath = os.getcwd() + "/"
            dumpfile = filePath + "memorydump%s.bin" % _time_str
            print("%s 0x%s %s" % (dumpfile, hex(addr), length))
            os.system("sudo ./dump_ddr %s %s %s %s 1" % (self.devName, dumpfile, addr, length*4))

    def dump_evtlog(self):
        addr0 = self.read_ddr(0x70_0000_0000 + 0x300)
        if ((addr0 == 0) or (addr0 == 0xffffffff)):
            print(">>> Wrong register addr0 0x%x!!!!\n" % int(addr0))
        else:
            addr = (0x70_0000_0000) | addr0
            print("g_evtbuf addr: 0x%lx" % addr)
            #1. read evtlog buffer's original data from DDR
            print("\n>>> Reading original data from DDR, processing ......")
            length = 0x80000
            temp_file = 'temp-evtlog.bin'
            file_name = 'dump-evtlog-%s.bin' % time.strftime("%Y-%m-%d-%H-%M-%S", time.localtime())
            os.system("sudo ./dump_ddr %s %s %s %s" % (self.devName, temp_file, addr, length*4))
            #2. get evtlog buffer's tail
            start = int(addr) + 148 + 1048576 * 2
            os.system("sudo ./pcimem %s 0x8000 w %s" % (self.devName, start))
            start_val = subprocess.run("sudo ./pcimem %s 0x8008 w" % (self.devName), shell=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT).stdout.decode(errors='ignore').strip()
            tail = int (start_val, 16)
            print(">>> Tail = %d" % (tail))
            if (tail == 0):
                print(">>> Warning!!! tail = 0!\n")
                print(">>> Output temp_evtlog.bin in the current folder!\n")
            elif (tail > 2097152):
                print(">>> Warning!!! The value of tail is more than 2MB!\n")
                print(">>> Output temp_evtlog.bin in the current folder!\n")
            else:
                #3. order the bin seq
                buf = bytearray(os.path.getsize(temp_file))
                with open(temp_file, 'rb') as f:
                    f.readinto(buf)
                with open(file_name, 'wb') as outfile:
                    outfile.write(buf[tail:])
                    outfile.write(buf[0:tail])
                print(">>> Complete! Output ddr evtlog %s in the current folder!\n" % file_name)

    def cmdtbl_dump(self):
        total_vld = 0
        total_err = 0
        start = 0x30B10000
        val = [ 0 for x in range(32)]
        print("\n\n==============================vld cmdtbl dump, all are hex============================\n")
        print("idx  v  opc  cid  adm  ns    dw9      dw8      dw11      dw10      dw12      sts  pn  rsn0  rsn1  sq  err err_slb err_ext acpl\n")
        for i in tqdm(range(0,512), desc='Processing cmdtbl dump'):
            offset = 0
            for k in range(32):
                val[k] = int(self.read(start + offset, 1, False), 16)
                if ((k == 0) and (val[0] & 0b1 == 0)):
                    err = int(self.read(start + 112, 1, False), 16)
                    if(err == 0):
                        break
                if ((k == 3) and val[3] & 0xff == 0):
                    break
                offset += 4
            start += 128
            vld = val[0] & 0b1
            opc = val[3] & 0xff
            err = val[28] & 0b1
            #opc
            if (opc  == 0):
                continue
            #vld and err
            if ((vld == 0) and (err  == 0)):
                continue
            #vld
            if (vld):
                total_vld +=1
            #err
            if (err):
                total_err +=1
            cid = (val[3] >> 16) & 0xffff
            adm = val[2] >> 27 & 0b1
            nsid = 0xffff if val[4] > 0xffff else val[4]
            nvmed07 = val[12]
            nvmed06 = val[11]
            dw11 = val[14]
            dw10 = val[13]
            dw12 = val[15]
            cmdsts = val[0] >> 4 & 0b11
            pns = val[19] >> 12 & 0b1111
            z0rsn = val[1] & 0xffff
            z1rsn = val[1] >> 16 & 0xffff
            lsqid = val[27] >> 20 & 0x03ff
            errcode = val[28] >> 4 & 0xf if err else 0
            errslbno = val[28] >> 8 & 0xffff
            exterr = val[28] >> 24 & 0b111
            acplen = val[2] >> 29 & 0b1

            print("%-3x  %x  %-3x  %-3x  %-3x  %-4x  %-8x %-8x %-8x  %-8x  %-8x  %-3x  %-2x  %-4x  %-4x  %-2x  %-3x %-7x %-7x %x\n" %(
                i, vld, opc, cid, adm, nsid, nvmed07,
                nvmed06, dw11, dw10, dw12, cmdsts, pns, z0rsn, z1rsn,
                lsqid, errcode, errslbno, exterr, acplen))
        print("\n=================vld_num:0x%x, err_num:0x%x======================\n" % (total_vld, total_err))
        print(">>> Cmdtbl dump success!\n")

    def pnsram_dump(self):
        print("\n=============pnsram dump=============\n")
        for offset in range(0, 0x2000):
            self.read(0x83482000 + offset * 4)
        print("\n=============pnsram dump=============\n")

    def nvmeipstatus_dump(self):
        print("\n=============nvme ip status dump=============\n")
        for offset in range(0, 0x20, 4):
            self.read(0x30900000 + offset)
        print("ERR NICta ")
        self.read(0x30900000 + 0x20c408)
        print("ERR NICtb ")
        self.read(0x30900000 + 0x20c40c)
        print("NIErrInfoL ")
        self.read(0x30900000 + 0x20c470)
        print("NIErrInfoH ")
        self.read(0x30900000 + 0x20c474)
        print("NICqcnt ")
        self.read(0x30900000 + 0x20c604)
        print("NlCECHGSum ")
        self.read(0x30900000 + 0x20c500)
        print("NlSHNCHGSum ")
        self.read(0x30900000 + 0x20c504)
        print("NlNSSREvtSum ")
        self.read(0x30900000 + 0x20c508)

    def nvmeipsqcq_dump(self):
        print("\n==============================ip sq dump================================\n")
        for sqid in range(0, 5):
            self._write(0x1400C000 + 0x20c100, 0x20000 + sqid, False)
            print("NLQPBSQDESPT0 of SQ%d::" % sqid)
            self.read(0x30900000 + 0x20110)
            print("NLQPBSQDESPT1 of SQ%d::" % sqid)
            self.read(0x30900000 + 0x20114)
            print("NLQPBSQDESPT2 of SQ%d::" % sqid)
            self.read(0x30900000 + 0x20118)
            print("NLQPBSQDESPT3 of SQ%d::" % sqid)
            self.read(0x30900000 + 0x2011c)
            print("NLQPBSQDESPT4 of SQ%d::" % sqid)
            self.read(0x30900000 + 0x20120)
        print("\n==============================ip sq dump================================\n")

        print("\n==============================ip cq dump================================\n")
        for cqid in range(0, 5):
            self._write(0x30900000 + 0x20c100, 0x30000 + cqid, False)
            print("NLQPBSQDESPT0 of CQ%d::" % cqid)
            self.read(0x30900000 + 0x20130)
            print("NLQPBSQDESPT1 of CQ%d::" % cqid)
            self.read(0x30900000 + 0x20134)
            print("NLQPBSQDESPT2 of CQ%d::" % cqid)
            self.read(0x30900000 + 0x20138)
            print("NLQPBSQDESPT3 of CQ%d::" % cqid)
            self.read(0x30900000 + 0x2013c)
            print("NLQPBSQDESPT4 of CQ%d::" % cqid)
            self.read(0x30900000 + 0x20140)
        print("\n==============================ip cq dump================================\n")

    def nlogcount_dump(self):
        print("\n=============Nlog count dump=============\n")
        self._write(0x30900000 + 0x22F000, 1<<8, False)
        self._write(0x30900000 + 0x22F000, (int(self.read(0x30900000 + 0x22F000, 1, False), 16) & (~(1<<8))), False)
        print("WCCNT LOW   %08x::0x%016x\n"%(0x30B2F000 + 0x10, int(self.read(0x30B2F000 + 0x14, 1, False), 16) << 32 | int(self.read(0x30B2F000 + 0x10, 1, False), 16)))
        print("WCCNT HIGH  %08x::0x%016x\n"%(0x30B2F000 + 0x18, int(self.read(0x30B2F000 + 0x1C, 1, False), 16) << 32 | int(self.read(0x30B2F000 + 0x18, 1, False), 16)))
        print("RCCNT LOW   %08x::0x%016x\n"%(0x30B2F000 + 0x20, int(self.read(0x30B2F000 + 0x24, 1, False), 16) << 32 | int(self.read(0x30B2F000 + 0x20, 1, False), 16)))
        print("RCCNT HIGH  %08x::0x%016x\n"%(0x30B2F000 + 0x28, int(self.read(0x30B2F000 + 0x2C, 1, False), 16) << 32 | int(self.read(0x30B2F000 + 0x28, 1, False), 16)))
        print("WDCNT LOW   %08x::0x%016x\n"%(0x30B2F000 + 0x30, int(self.read(0x30B2F000 + 0x34, 1, False), 16) << 32 | int(self.read(0x30B2F000 + 0x30, 1, False), 16)))
        print("WDCNT HIGH  %08x::0x%016x\n"%(0x30B2F000 + 0x38, int(self.read(0x30B2F000 + 0x3C, 1, False), 16) << 32 | int(self.read(0x30B2F000 + 0x38, 1, False), 16)))
        print("RDCNT LOW   %08x::0x%016x\n"%(0x30B2F000 + 0x40, int(self.read(0x30B2F000 + 0x44, 1, False), 16) << 32 | int(self.read(0x30B2F000 + 0x40, 1, False), 16)))
        print("RDCNT HIGH  %08x::0x%016x\n"%(0x30B2F000 + 0x48, int(self.read(0x30B2F000 + 0x4C, 1, False), 16) << 32 | int(self.read(0x30B2F000 + 0x48, 1, False), 16)))
        print("BSYCNT LOW  %08x::0x%016x\n"%(0x30B2F000 + 0x50, int(self.read(0x30B2F000 + 0x54, 1, False), 16) << 32 | int(self.read(0x30B2F000 + 0x50, 1, False), 16)))
        print("BSYCNT HIGH %08x::0x%016x\n"%(0x30B2F000 + 0x58, int(self.read(0x30B2F000 + 0x5C, 1, False), 16) << 32 | int(self.read(0x30B2F000 + 0x58, 1, False), 16)))
        print("RWCNT_LT1K  %08x::0x%08x\n"%(0x30B2F000 + 0x70, int(self.read(0x30B2F000 + 0x70, 1, False), 16)))
        print("IOCMDCNT    %08x::0x%08x\n"%(0x30B2F000 + 0x74, int(self.read(0x30B2F000 + 0x74, 1, False), 16)))
        print("NsTbl0CmdCntr %08x::0x%08x\n"%(0x30B2F000 + 0x88, int(self.read(0x30B2F000 + 0x88, 1, False), 16)))
        print("NsTbl1CmdCntr %08x::0x%08x\n"%(0x30B2F000 + 0x8C, int(self.read(0x30B2F000 + 0x8C, 1, False), 16)))
        print("\n=============Nlog count dump=============\n")

    def nfeerror_dump(self):
        print("\n=============NFE error dump=============\n")
        print("NfeNsum ")
        self.read(0x30900000 + 0x230024)
        print("NfeNsts ")
        self.read(0x30900000 + 0x230028)
        print("NfeEsum ")
        self.read(0x30900000 + 0x230030)
        print("NfeErrDw0 ")
        self.read(0x30900000 + 0x230040)
        print("NfeErrDw1 ")
        self.read(0x30900000 + 0x230044)
        print("NfeErrDw2 ")
        self.read(0x30900000 + 0x230048)
        print("NfeErrDw3 ")
        self.read(0x30900000 + 0x23004c)
        print("NfeStsInfo ")
        self.read(0x30900000 + 0x230070)
        print("NfeCmgr ")
        self.read(0x30900000 + 0x2301a8)
        print("\n=============NFE error dump=============\n")

    def apuerror_dump(self):
        print("\n=============APU error dump=============\n")
        print("NapuRcmd0 ")
        self.read(0x30900000 + 0x206000)
        print("NapuRcmd1 ")
        self.read(0x30900000 + 0x206004)
        print("NapuRcmd2 ")
        self.read(0x30900000 + 0x206008)
        print("NapuRcmd3 ")
        self.read(0x30900000 + 0x20600c)
        print("NapuCmdqSts ")
        self.read(0x30900000 + 0x206020)
        print("Napu0Wsts ")
        self.read(0x30900000 + 0x206030)
        print("Napu1Wsts ")
        self.read(0x30900000 + 0x206038)
        print("HWSTS ")
        self.read(0x30900000 + 0x204010)
        print("\n=============APU error dump=============\n")

    def plda_dump(self):
        print("\n===================================plda dump========================================\n")
        for offset1 in range(0, 0x20, 4):
            self.read(0x83ca0000 + 0x1200 + offset1)
        print("\n===================================plda dump========================================\n")

    def b2nprepstatus_dump(self):
        print("\n==================b2n_prep_status: 0x83440400 - 0x8344047c dump=====================\n")
        for offset1 in range(0, 0x7c, 4):
            self.read(0x83440400 + offset1)
        print("\n==================b2n_prep_status: 0x83440400 - 0x8344047c dump=====================\n")

    #def vendorreg_dump(self):
    #    print("\n==================0x28300000 - 0x28300c00 dump=====================\n")
    #    for offset1 in range(0, 0xC00, 4):
    #        self.read(0x28300000 + offset1)
    #    print("\n==================0x28300000 - 0x28300c00 dump=====================\n")

    def sysdmacsr_dump(self):
        #sysdma_csr_base = 0x83C10000
        print("\n===================sysdma0 status dump=====================\n")

        print("DMAC_CHENREG     : 0x%08x\n"% int (self.read(0x83C10000 + 0x0018, 1, False), 16))
        print("DMAC_IDREG     : 0x%08x\n"% int (self.read(0x83C10000 + 0x0, 1, False), 16))
        print("DMAC_COMPVERREG     : 0x%08x\n"% int (self.read(0x83C10000 + 0x8, 1, False), 16))
        print("DMAC_CFGREG     : 0x%08x\n"% int (self.read(0x83C10000 + 0x10, 1, False), 16))
        print("DMAC_CHSUSPREG     : 0x%08x\n"% int (self.read(0x83C10000 + 0x20, 1, False), 16))
        print("DMAC_CHABORTREG     : 0x%08x\n"% int (self.read(0x83C10000 + 0x28, 1, False), 16))
        print("DMAC_INTSTATUSREG     : 0x%08x\n"% int (self.read(0x83C10000 + 0x30, 1, False), 16))
        print("DMAC_COMMONREG_INTCLEARREG     : 0x%08x\n"% int (self.read(0x83C10000 + 0x38, 1, False), 16))
        print("DMAC_COMMONREG_INTSTATUS_ENABLEREG     : 0x%08x\n"% int (self.read(0x83C10000 + 0x40, 1, False), 16))
        print("DMAC_COMMONREG_INTSIGNAL_ENABLEREG     : 0x%08x\n"% int (self.read(0x83C10000 + 0x48, 1, False), 16))
        print("DMAC_COMMONREG_INTSTATUSREG     : 0x%08x\n"% int (self.read(0x83C10000 + 0x50, 1, False), 16))
        print("DMAC_RESETREG     : 0x%08x\n"% int (self.read(0x83C10000 + 0x58, 1, False), 16))
        print("DMAC_LOWPOWER_CFGREG     : 0x%08x\n"% int (self.read(0x83C10000 + 0x60, 1, False), 16))

        print("CH0_SAR          : 0x%08x\n"% int (self.read(0x83C10000 + 0x0100, 1, False), 16))
        print("CH0_DAR          : 0x%08x\n"% int (self.read(0x83C10000 + 0x0108, 1, False), 16))
        print("CH0_BLOCK_TS     : 0x%08x\n"% int (self.read(0x83C10000 + 0x0110, 1, False), 16))
        print("CH0_CTL          : 0x%08x\n"% int (self.read(0x83C10000 + 0x0118, 1, False), 16))
        print("CH0_CFG          : 0x%08x\n"% int (self.read(0x83C10000 + 0x0120, 1, False), 16))
        print("CH0_INTSTATUS    : 0x%08x\n"% int (self.read(0x83C10000 + 0x0188, 1, False), 16))

        print("CH1_SAR          : 0x%08x\n"% int (self.read(0x83C10000 + 0x0200, 1, False), 16))
        print("CH1_DAR          : 0x%08x\n"% int (self.read(0x83C10000 + 0x0208, 1, False), 16))
        print("CH1_BLOCK_TS     : 0x%08x\n"% int (self.read(0x83C10000 + 0x0210, 1, False), 16))
        print("CH1_CTL          : 0x%08x\n"% int (self.read(0x83C10000 + 0x0218, 1, False), 16))
        print("CH1_CFG          : 0x%08x\n"% int (self.read(0x83C10000 + 0x0220, 1, False), 16))
        print("CH1_INTSTATUS    : 0x%08x\n"% int (self.read(0x83C10000 + 0x0288, 1, False), 16))

        print("CH2_SAR          : 0x%08x\n"% int (self.read(0x83C10000 + 0x0300, 1, False), 16))
        print("CH2_DAR          : 0x%08x\n"% int (self.read(0x83C10000 + 0x0308, 1, False), 16))
        print("CH2_BLOCK_TS     : 0x%08x\n"% int (self.read(0x83C10000 + 0x0310, 1, False), 16))
        print("CH2_CTL          : 0x%08x\n"% int (self.read(0x83C10000 + 0x0318, 1, False), 16))
        print("CH2_CFG          : 0x%08x\n"% int (self.read(0x83C10000 + 0x0320, 1, False), 16))
        print("CH2_INTSTATUS    : 0x%08x\n"% int (self.read(0x83C10000 + 0x0388, 1, False), 16))

        print("CH3_SAR          : 0x%08x\n"% int (self.read(0x83C10000 + 0x0400, 1, False), 16))
        print("CH3_DAR          : 0x%08x\n"% int (self.read(0x83C10000 + 0x0408, 1, False), 16))
        print("CH3_BLOCK_TS     : 0x%08x\n"% int (self.read(0x83C10000 + 0x0410, 1, False), 16))
        print("CH3_CTL          : 0x%08x\n"% int (self.read(0x83C10000 + 0x0418, 1, False), 16))
        print("CH3_CFG          : 0x%08x\n"% int (self.read(0x83C10000 + 0x0420, 1, False), 16))
        print("CH3_INTSTATUS    : 0x%08x\n"% int (self.read(0x83C10000 + 0x0488, 1, False), 16))

        print("\n===================sysdma0 status dump=====================\n")

        print("\n===================sysdma1 status dump=====================\n")

        print("DMAC_CHENREG     : 0x%08x\n"% int (self.read(0x83C30000 + 0x0018, 1, False), 16))
        print("DMAC_IDREG     : 0x%08x\n"% int (self.read(0x83C30000 + 0x0, 1, False), 16))
        print("DMAC_COMPVERREG     : 0x%08x\n"% int (self.read(0x83C30000 + 0x8, 1, False), 16))
        print("DMAC_CFGREG     : 0x%08x\n"% int (self.read(0x83C30000 + 0x10, 1, False), 16))
        print("DMAC_CHSUSPREG     : 0x%08x\n"% int (self.read(0x83C30000 + 0x20, 1, False), 16))
        print("DMAC_CHABORTREG     : 0x%08x\n"% int (self.read(0x83C30000 + 0x28, 1, False), 16))
        print("DMAC_INTSTATUSREG     : 0x%08x\n"% int (self.read(0x83C30000 + 0x30, 1, False), 16))
        print("DMAC_COMMONREG_INTCLEARREG     : 0x%08x\n"% int (self.read(0x83C30000 + 0x38, 1, False), 16))
        print("DMAC_COMMONREG_INTSTATUS_ENABLEREG     : 0x%08x\n"% int (self.read(0x83C30000 + 0x40, 1, False), 16))
        print("DMAC_COMMONREG_INTSIGNAL_ENABLEREG     : 0x%08x\n"% int (self.read(0x83C30000 + 0x48, 1, False), 16))
        print("DMAC_COMMONREG_INTSTATUSREG     : 0x%08x\n"% int (self.read(0x83C30000 + 0x50, 1, False), 16))
        print("DMAC_RESETREG     : 0x%08x\n"% int (self.read(0x83C30000 + 0x58, 1, False), 16))
        print("DMAC_LOWPOWER_CFGREG     : 0x%08x\n"% int (self.read(0x83C30000 + 0x60, 1, False), 16))

        print("CH0_SAR          : 0x%08x\n"% int (self.read(0x83C30000 + 0x0100, 1, False), 16))
        print("CH0_DAR          : 0x%08x\n"% int (self.read(0x83C30000 + 0x0108, 1, False), 16))
        print("CH0_BLOCK_TS     : 0x%08x\n"% int (self.read(0x83C30000 + 0x0110, 1, False), 16))
        print("CH0_CTL          : 0x%08x\n"% int (self.read(0x83C30000 + 0x0118, 1, False), 16))
        print("CH0_CFG          : 0x%08x\n"% int (self.read(0x83C30000 + 0x0120, 1, False), 16))
        print("CH0_INTSTATUS    : 0x%08x\n"% int (self.read(0x83C30000 + 0x0188, 1, False), 16))

        print("CH1_SAR          : 0x%08x\n"% int (self.read(0x83C30000 + 0x0200, 1, False), 16))
        print("CH1_DAR          : 0x%08x\n"% int (self.read(0x83C30000 + 0x0208, 1, False), 16))
        print("CH1_BLOCK_TS     : 0x%08x\n"% int (self.read(0x83C30000 + 0x0210, 1, False), 16))
        print("CH1_CTL          : 0x%08x\n"% int (self.read(0x83C30000 + 0x0218, 1, False), 16))
        print("CH1_CFG          : 0x%08x\n"% int (self.read(0x83C30000 + 0x0220, 1, False), 16))
        print("CH1_INTSTATUS    : 0x%08x\n"% int (self.read(0x83C30000 + 0x0288, 1, False), 16))

        print("CH2_SAR          : 0x%08x\n"% int (self.read(0x83C30000 + 0x0300, 1, False), 16))
        print("CH2_DAR          : 0x%08x\n"% int (self.read(0x83C30000 + 0x0308, 1, False), 16))
        print("CH2_BLOCK_TS     : 0x%08x\n"% int (self.read(0x83C30000 + 0x0310, 1, False), 16))
        print("CH2_CTL          : 0x%08x\n"% int (self.read(0x83C30000 + 0x0318, 1, False), 16))
        print("CH2_CFG          : 0x%08x\n"% int (self.read(0x83C30000 + 0x0320, 1, False), 16))
        print("CH2_INTSTATUS    : 0x%08x\n"% int (self.read(0x83C30000 + 0x0388, 1, False), 16))

        print("CH3_SAR          : 0x%08x\n"% int (self.read(0x83C30000 + 0x0400, 1, False), 16))
        print("CH3_DAR          : 0x%08x\n"% int (self.read(0x83C30000 + 0x0408, 1, False), 16))
        print("CH3_BLOCK_TS     : 0x%08x\n"% int (self.read(0x83C30000 + 0x0410, 1, False), 16))
        print("CH3_CTL          : 0x%08x\n"% int (self.read(0x83C30000 + 0x0418, 1, False), 16))
        print("CH3_CFG          : 0x%08x\n"% int (self.read(0x83C30000 + 0x0420, 1, False), 16))
        print("CH3_INTSTATUS    : 0x%08x\n"% int (self.read(0x83C30000 + 0x0488, 1, False), 16))

        print("\n===================sysdma1 status dump=====================\n")

    def feacemonitor_dump(self):
        print("\n=============fe_ace_monitor dump=============\n")
        # monitor sel 0x200000 ~ 0x20000B
        for offset in range(0, 0xC):
            self._write(0x83D00000 + 0x470, 0x200000 + offset, False)
            val  = self.read(0x83D00478, 1, False)
            _val = self.read(0x83D0047C, 1, False)
            res  =  int (_val, 16) << 32 | int (val, 16)
            print("sel 0x%lx, val 0x%016lx\n" % (0x200000 + offset, res))
        # monitor sel 0x300000 ~ 0x300008
        for offset in range(0, 0x9):
            self._write(0x83D00000 + 0x470, 0x300000 + offset, False)
            val  = self.read(0x83D00478, 1, False)
            _val = self.read(0x83D0047C, 1, False)
            res  =  int (_val, 16) << 32 | int (val, 16)
            print("sel 0x%lx, val 0x%016lx\n" % (0x300000 + offset, res))
        # monitor sel 0x400000 ~ 0x400004
        for offset in range(0, 0x5):
            self._write(0x83D00000 + 0x470, 0x400000 + offset, False)
            val  = self.read(0x83D00478, 1, False)
            _val = self.read(0x83D0047C, 1, False)
            res  =  int (_val, 16) << 32 | int (val, 16)
            print("sel 0x%lx, val 0x%016lx\n" % (0x400000 + offset, res))
        # monitor sel 0x500000 ~ 0x500004
        for offset in range(0, 0xb):
            self._write(0x83D00000 + 0x470, 0x500000 + offset, False)
            val  = self.read(0x83D00478, 1, False)
            _val = self.read(0x83D0047C, 1, False)
            res  =  int (_val, 16) << 32 | int (val, 16)
            print("sel 0x%lx, val 0x%016lx\n" % (0x500000 + offset, res))
        # monitor sel 0x0_00000000 ~ 0xF_00000000
        for offset in range(0, 0x10):
            self._write(0x83D00000 + 0x470, offset << 32, False)
            self._write(0x83D00000 + 0x474, offset, False)
            val  = self.read(0x83D00478, 1, False)
            _val = self.read(0x83D0047C, 1, False)
            res  =  int (_val, 16) << 32 | int (val, 16)
            print("sel 0x%lx, val 0x%016lx\n" % (offset << 32, res))
        # monitor sel 0x20_00000000 ~ 0x2F_00000000
        for offset in range(0, 0x10):
            self._write(0x83D00000 + 0x470, (0x20 + offset) << 32, False)
            self._write(0x83D00000 + 0x474, 0x20 + offset, False)
            val  = self.read(0x83D00478, 1, False)
            _val = self.read(0x83D0047C, 1, False)
            res  =  int (_val, 16) << 32 | int (val, 16)
            print("sel 0x%lx, val 0x%016lx\n" % ((0x20 + offset) << 32, res))
        # monitor sel 0x60_00000000 ~ 0x68_00000000
        for offset in range(0, 0x9):
            self._write(0x83D00000 + 0x470, (0x60 + offset) << 32, False)
            self._write(0x83D00000 + 0x474, 0x60 + offset, False)
            val  = self.read(0x83D00478, 1, False)
            _val = self.read(0x83D0047C, 1, False)
            res  =  int (_val, 16) << 32 | int (val, 16)
            print("sel 0x%lx, val 0x%016lx\n" % ((0x60 + offset) << 32, res))
        # monitor sel 0x80_00000000 ~ 0x90_00000000
        for offset in range(0, 0x11):
            self._write(0x83D00000 + 0x470, (0x80 + offset) << 32, False)
            self._write(0x83D00000 + 0x474, 0x80 + offset, False)
            val  = self.read(0x83D00478, 1, False)
            _val = self.read(0x83D0047C, 1, False)
            res  =  int (_val, 16) << 32 | int (val, 16)
            print("sel 0x%lx, val 0x%016lx\n" % ((0x80 + offset) << 32, res))

        """
        # dump queue 0 ~ 8's property
        # There is a bug when use 32bit PCIe indirect to access ACQ register, disable this function
        for offset in range(0, 0x9):
            self._write(0x20f00000 + 0x0020, offset, True)
            #self._write(0x20f00000 + 0x0024, 0x0, True)
            print("\nacq 0x%x property:\n" % (offset))
            for j in range(0x28, 0x59, 0x8):
                low  = int(self.read(0x20f00000 + j, 1, True), 16)
                high = int(self.read(0x20f00000 + j + 0x4, 1, True), 16)
                res  =  ((high << 32) | low)
                print("addr 0x%lx, val 0x%08x\n" % (j, res))
        """
        print("\n=============fe_ace_monitor dump=============\n")

    def fis_dump(self):
        print("\n========================pss dump, base:%x=====================\n" % (0x83500000))
        print("pcie_err_ctrl                        %x:0x%08x\n" % (0x83500000 + 0x9000, int (self.read(0x83500000 + 0x9000, 1, False), 16)))
        print("pcie_tx_pll_ready_out_cnt_0          %x:0x%08x\n" % (0x83500000 + 0x901C, int (self.read(0x83500000 + 0x901C, 1, False), 16)))
        print("pcie_tx_pll_ready_out_cnt_1          %x:0x%08x\n" % (0x83500000 + 0x9020, int (self.read(0x83500000 + 0x9020, 1, False), 16)))
        print("pcie_rx_pll_ready_out_cnt_0          %x:0x%08x\n" % (0x83500000 + 0x9024, int (self.read(0x83500000 + 0x9024, 1, False), 16)))
        print("pcie_rx_pll_ready_out_cnt_1          %x:0x%08x\n" % (0x83500000 + 0x9028, int (self.read(0x83500000 + 0x9028, 1, False), 16)))

        print("\n========================fis dump, base:%x=====================\n" % (0x83480000))
        print("fis_nvme_status_1                    %x:0x%08x\n" % (0x83480000 + 0x1104, int (self.read(0x83480000 + 0x1104, 1, False), 16)))
        print("fis_nvme_status_2                    %x:0x%08x\n" % (0x83480000 + 0x110c, int (self.read(0x83480000 + 0x110c, 1, False), 16)))
        print("fis_nvme_rderr_rid                   %x:0x%08x\n" % (0x83480000 + 0x1110, int (self.read(0x83480000 + 0x10110, 1, False), 16)))
        print("fis_nvme_rderr1_rid                  %x:0x%08x\n" % (0x83480000 + 0x10114, int (self.read(0x83480000 + 0x10114, 1, False), 16)))

        print("nvme_event_cnt_ctrl                  %x:0x%08x\n" % (0x83480000 + 0x1200, int (self.read(0x83480000 + 0x1200, 1, False), 16)))
        print("fis_host_wcpl_vld_cnt                %x:0x%08x\n" % (0x83480000 + 0x1204, int (self.read(0x83480000 + 0x1204, 1, False), 16)))
        print("fis_host_rcpl_vld_cnt                %x:0x%08x\n" % (0x83480000 + 0x1208, int (self.read(0x83480000 + 0x1208, 1, False), 16)))
        print("fis_host_rcpl1_vld_cnt               %x:0x%08x\n" % (0x83480000 + 0x120C, int (self.read(0x83480000 + 0x120C, 1, False), 16)))
        print("fis_ace_fcq_rinc_cnt                 %x:0x%08x\n" % (0x83480000 + 0x1210, int (self.read(0x83480000 + 0x1210, 1, False), 16)))
        print("fis_ace_wcq_winc_cnt                 %x:0x%08x\n" % (0x83480000 + 0x1214, int (self.read(0x83480000 + 0x1214, 1, False), 16)))
        print("fis_ace_rcq_winc_cnt                 %x:0x%08x\n" % (0x83480000 + 0x1218, int (self.read(0x83480000 + 0x1218, 1, False), 16)))
        print("fis_ace_apurcq_winc_cnt              %x:0x%08x\n" % (0x83480000 + 0x121C, int (self.read(0x83480000 + 0x121C, 1, False), 16)))
        print("fis_ace_cplq_winc_cnt                %x:0x%08x\n" % (0x83480000 + 0x1220, int (self.read(0x83480000 + 0x1220, 1, False), 16)))
        print("fsm_state_axi                        %x:0x%08x\n" % (0x83480000 + 0x1230, int (self.read(0x83480000 + 0x1230, 1, False), 16)))
        print("==============================fis dump===================================\n")

    def locstatus_dump(self):
        print("\n===================================loc dump========================================\n")
        val = int(self.read(0x83460000 + 0x0200, 1, False), 16)
        raw_chk_en = (val >> 2) & 0b1
        war_chk_en = (val >> 1) & 0b1
        waw_chk_en = val & 0b1
        loc_nsid_byp = (val >> 8) & 0xFF
        print("raw chk:%d, war chk:%d, waw chk:%d, nsid_byp:0x%x\n" % (raw_chk_en, war_chk_en, waw_chk_en, loc_nsid_byp))
        print("loc status0:0x%x, blocked cmds num:0x%x, nsid_skip:0x%x\n" %(int(self.read(0x83460000 + 0x0208, 1, False), 16),
            int(self.read(0x83460000 + 0x0208, 1, False), 16) & 0x3F, int(self.read(0x83460000 + 0x0208, 1, False), 16) >> 8))
        print("loc status1, number of valid LOC cmds including blocked or not released:0x%x\n" % (int(self.read(0x83460000 + 0x020C, 1, False), 16)))
        print("loc status2, Accumulator Counter 2:0x%x\n" % (int(self.read(0x83460000 + 0x0210, 1, False), 16)))
        print("loc status3, Accumulator Counter 3:0x%x\n" % (int(self.read(0x83460000 + 0x0214, 1, False), 16)))
        print("\n===================================loc dump========================================\n")

    def feacestatus_dump(self):
        print("\n===================================feace dump========================================\n")
        print("loc_status0: 0x%x \n" % (int(self.read(0x83460000 + 0x0208, 1, False), 16)))
        print("loc_status1: 0x%x \n" % (int(self.read(0x83460000 + 0x020C, 1, False), 16)))
        print("loc_status2: 0x%x \n" % (int(self.read(0x83460000 + 0x0210, 1, False), 16)))
        print("loc_status3: 0x%x \n" % (int(self.read(0x83460000 + 0x0214, 1, False), 16)))

        print("act_status0: 0x%x \n" % (int(self.read(0x83460000 + 0x0220, 1, False), 16)))
        print("act_status1: 0x%x \n" % (int(self.read(0x83460000 + 0x0224, 1, False), 16)))
        print("Last to SDSW WCQ log 0 Register\n")
        print("wcq_sdsw0: 0x%x \n" % (int(self.read(0x83460000 + 0x0340, 1, False), 16)))
        print("wcq_sdsw1: 0x%x \n" % (int(self.read(0x83460000 + 0x0344, 1, False), 16)))
        print("wcq_sdsw2: 0x%x \n" % (int(self.read(0x83460000 + 0x0348, 1, False), 16)))
        print("wcq_sdsw3: 0x%x \n" % (int(self.read(0x83460000 + 0x034C, 1, False), 16)))
        print("FCQ  counter: 0x%x \n" % (int(self.read(0x83460000 + 0x0350, 1, False), 16)))
        print("CPLQ counter: 0x%x \n" % (int(self.read(0x83460000 + 0x0354, 1, False), 16)))
        print("RCQ  counter: 0x%x \n" % (int(self.read(0x83460000 + 0x0358, 1, False), 16)))
        print("WCQ  counter: 0x%x \n" % (int(self.read(0x83460000 + 0x035C, 1, False), 16)))
        print("WCPL counter: 0x%x \n" % (int(self.read(0x83460000 + 0x0360, 1, False), 16)))
        print("APURCQ counter: 0x%x \n" % (int(self.read(0x83460000 + 0x0364, 1, False), 16)))
        print("RCPL0  counter: 0x%x \n" % (int(self.read(0x83460000 + 0x0368, 1, False), 16)))
        print("RCPL1  counter: 0x%x \n" % (int(self.read(0x83460000 + 0x036C, 1, False), 16)))
        print("ACT WR counter: 0x%x \n" % (int(self.read(0x83460000 + 0x0370, 1, False), 16)))
        print("CMD WR counter: 0x%x \n" % (int(self.read(0x83460000 + 0x0374, 1, False), 16)))
        print("CPL RD counter: 0x%x \n" % (int(self.read(0x83460000 + 0x0378, 1, False), 16)))
        print("DMA TRIG counter: 0x%x \n" % (int(self.read(0x83460000 + 0x037C, 1, False), 16)))
        print("DMA CPL  counter: 0x%x \n" % (int(self.read(0x83460000 + 0x0380, 1, False), 16)))
        print("\n===================================feace dump========================================\n")

    def errcodedbg_dump(self):
        print("\n=============errcode debug dump=============\n")
        #self.read(0x24100e04)
        #self.read(0x24100e08)
        #self.read(0x24100e0c)

        #print("masteren_debug(0x24100e10)          : 0x%08x\n" % (int(self.read(0x24100e10, 1, False), 16)))
        #print("inst0_test_out_pcie_31_0(0x24100e14): 0x%08x\n" % (int(self.read(0x24100e14, 1, False), 16)))
        #print("pcie_axi_err_status0(0x24100e18)    : 0x%08x\n" % (int(self.read(0x24100e18, 1, False), 16)))

        #for i in range(0, 0x33):
        #    self._write(0x2009c000, 0x08000000 | i, False)
        #    print("sel 0x%08x,   val: 0x%08x\n" % (0x08000000 | i, int(self.read(0x2009c300, 1, False), 16)))
        #    self._write(0x2009c000, 0x08100000 | i, False)
        #    print("sel 0x%08x,   val: 0x%08x\n" % (0x08100000 | i, int(self.read(0x2009c300, 1, False), 16)))
        print("\n=============errcode debug dump=============\n")

    def beace_dump(self):
        # fcq property status dump
        self.fcq_status_dump()
        # cmd status memory dump
        self.cmd_status_dump()
        # beace monitor dump
        self.beace_monitor_dump()
        # fct poll base dump
        self.fct_base_dump()
        # fct poll config dump
        self.fct_pool_config_dump()

    def fcq_status_dump(self):
        print("\n\n===============fcq/dbl property status dump=============\n")
        for i in range (0, 128):
            self._write(0x83d11020, i)
            self.read(0x83d11028)
            self.read(0x83d11030)
            self.read(0x83d11040)
        print("===============fcq/dbl property status dump=============\n")

    def cmd_status_dump(self):
        print("\n\n===============cmd status memory dump=============\n")
        for i in range (0, 512):
            print('entry %d' % (i))
            os.system("sudo ./pcimem %s 0x8000 w %s" % (self.devName, 0x83d11710))
            os.system("sudo ./pcimem %s 0x8004 w 0x%x" % (self.devName, i))
            os.system("sudo ./pcimem %s 0x8000 w %s" % (self.devName, int(0x83d11718)))
            MDELAY(1)
            val = subprocess.run("sudo ./pcimem %s 0x8008 w" % (self.devName), shell=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT).stdout.decode(errors='ignore').strip()
            os.system("sudo ./pcimem %s 0x8000 w %s" % (self.devName, 0x83d11710))
            os.system("sudo ./pcimem %s 0x8004 w 0x%x" % (self.devName, i))
            os.system("sudo ./pcimem %s 0x8000 w %s" % (self.devName, int(0x83d1171c)))
            MDELAY(1)
            _val = subprocess.run("sudo ./pcimem %s 0x8008 w" % (self.devName), shell=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT).stdout.decode(errors='ignore').strip()
            res =  int (_val, 16) << 32 | int (val, 16)
            for k,o in list(rl.items()):
                if ( 0x83d11718 >= o[0][1][0] and 0x83d11718<o[0][1][1]):
                    obj = o[0]
                    break
            lines = obj[2].split('\n')
            print('0x%08x: %s: 0x%x  %s' % (0x83d11718, obj[0], res, lines[0]))
            self.dump(res, obj[3])
            self.read(0x83d11720)
        print("===============cmd status memory dump=============\n")
    
    def beace_monitor_dump(self):
        print("\n\n===============be ace monitor status dump=============\n")
        for i in range (0, 10):
            self._write(0x83d11740, i)
            self.read(0x83d11748)
        for i in range (0x1000, 0x1029):
            self._write(0x83d11740, i)
            self.read(0x83d11748)
        for i in range (0x2000, 0x2020):
            self._write(0x83d11740, i)
            self.read(0x83d11748)
        for i in range (0x3000, 0x3001):
            self._write(0x83d11740, i)
            self.read(0x83d11748)
        for i in range (0x4000, 0x400c):
            self._write(0x83d11740, i)
            self.read(0x83d11748)
        for i in range (0x5000, 0x5020):
            self._write(0x83d11740, i)
            self.read(0x83d11748)
        for i in range (0x6000, 0x600c):
            self._write(0x83d11740, i)
            self.read(0x83d11748)
        for i in range (0x7000, 0x7001):
            self._write(0x83d11740, i)
            self.read(0x83d11748)
        for i in range (0x8000, 0x8004):
            self._write(0x83d11740, i)
            self.read(0x83d11748)
        print("===============be ace monitor status dump=============\n")

    def fct_base_dump(self):
        print("\n\n===============fct pool base dump=============\n")
        for i in range (0, 16):
            self.read(0x83d11300 + (i << 5))
        for i in range (0, 16):
            self.read(0x83d11900 + (i << 5))
        print("===============fct pool base dump=============\n")

    def fct_pool_config_dump(self):
        print("\n\n===============fct pool config dump=============\n")
        for i in range (0, 16):
            self.read(0x83d11308 + (i << 5))
        for i in range (0, 16):
            self.read(0x83d11908 + (i << 5))
        print("===============fct pool config dump=============\n")

    def sdsr_dump(self):
        print("\n\n===================================sdsr dump========================================\n")
        for i in range (0x0, 0x8):
            self._write(0x83450210, i)
            self.read(0x83450214)
        for i in range (0x20, 0x28):
            self._write(0x83450210, i)
            self.read(0x83450214)
        for i in range (0x30, 0x39):
            self._write(0x83450210, i)
            self.read(0x83450214)
        for i in range (0x40, 0x45):
            self._write(0x83450210, i)
            self.read(0x83450214)
        for i in range (0x60, 0x68):
            self._write(0x83450210, i)
            self.read(0x83450214)
        for i in range (0x70, 0x78):
            self._write(0x83450210, i)
            self.read(0x83450214)
        for i in range (0x80, 0x83):
            self._write(0x83450210, i)
            self.read(0x83450214)
        for i in range (0xa0, 0xac):
            self._write(0x83450210, i)
            self.read(0x83450214)
        for i in range (0xc0, 0xc1):
            self._write(0x83450210, i)
            self.read(0x83450214)
        for i in range (0xd0, 0xd2):
            self._write(0x83450210, i)
            self.read(0x83450214)
        for i in range (0xe0, 0xec):
            self._write(0x83450210, i)
            self.read(0x83450214)
        for i in range (0xf0, 0xfc):
            self._write(0x83450210, i)
            self.read(0x83450214)
        print("===================================sdsr dump========================================\n")

    def sdsw_dump(self):
        self.sdsw_status_dump()
        self.sdsw_monitor_dump()
        
    def sdsw_status_dump(self):
        print("\n\n===================================sdsw dump========================================\n")
        for i in range (0, 7):
            self.read(0x83450018 + i * 4, 1)
        for i in range (0, 4):
            self.read(0x83450034 + i * 4, 1)
        for i in range (0, 11):
            self.read(0x83450094 + i * 4, 1)
        self.read(0x83450040, 1)
        self.read(0x834500c8, 1)
        print("===================================sdsw dump========================================\n")

    def sdsw_monitor_dump(self):
        print("\n\n=======sdsw monitor dump=======\n")
        for i in range (0x0, 0x6):
            self._write(0x83450044, i)
            self.read(0x83450048)
        for i in range (0x40, 0x50):
            self._write(0x83450044, i)
            self.read(0x83450048)
        for i in range (0x80, 0x82):
            self._write(0x83450044, i)
            self.read(0x83450048)
        for i in range (0x0, 0x9):
            self._write(0x83450044, 0x100 + (i<<4))
            self.read(0x83450048)
        for i in range (0x200, 0x201):
            self._write(0x83450044, i)
            self.read(0x83450048)
        for i in range (0x240, 0x241):
            self._write(0x83450044, i)
            self.read(0x83450048)
        for i in range (0x280, 0x288):
            self._write(0x83450044, i)
            self.read(0x83450048)
        for i in range (0x300, 0x303):
            self._write(0x83450044, i)
            self.read(0x83450048)
        for i in range (0x320, 0x323):
            self._write(0x83450044, i)
            self.read(0x83450048)
        for i in range (0x340, 0x358):
            self._write(0x83450044, i)
            self.read(0x83450048)
        for i in range (0x400, 0x404):
            self._write(0x83450044, i)
            self.read(0x83450048)
        for i in range (0x500, 0x524):
            self._write(0x83450044, i)
            self.read(0x83450048)
        for i in range (0x600, 0x608):
            self._write(0x83450044, i)
            self.read(0x83450048)
        for i in range (0x700, 0x708):
            self._write(0x83450044, i)
            self.read(0x83450048)
        for i in range (0x800, 0x808):
            self._write(0x83450044, i)
            self.read(0x83450048)
        for i in range (0x900, 0x908):
            self._write(0x83450044, i)
            self.read(0x83450048)
        for i in range (0xa00, 0xa16):
            self._write(0x83450044, i)
            self.read(0x83450048)
        for i in range (0xb00, 0xb16):
            self._write(0x83450044, i)
            self.read(0x83450048)
        print("=======sdsw monitor dump=======\n")

    def ccs_dump(self):
        print("\n\n===================================ccs dump========================================\n")
        self.ccs_cmd_and_cpl_dump()
        self.ccs_counter_dump()
        self.ccs_monitor_dump()
        self.ccs_status_dump()
        print("===================================ccs dump========================================\n")

    def ccs_cmd_and_cpl_dump(self):
        print("\n\n===============ccs command and completion dump=============\n\n")
        #define CCS_CMD_BUF_MAX 20
        ccs_cmd_buf=[]
        for i in range(0, 512):
            ccs_cmd_buf.append([])
            for j in range(0, 20):
                ccs_cmd_buf[i].append(0)
        printcnt1 = 0
        printcnt2 = 0
        min = 0xFFFF
        max = 0
        cur = 0
        val = 0

        for i in range(0, 512):
            print("\r", end="")
            print("process: {}/512: ".format(i), "▓" * (i // 5), end="")
            sys.stdout.flush()
            dataflag = 0
            for j in range(0, 10):
                self._write(0x83440068, (j << 16) | (i << 4) | 0, needprint = False)
                ccs_cmd_buf[i][j] = int(self.read(0x8344006c, needprint = False), 16)
                dataflag = dataflag | ccs_cmd_buf[i][j]
            ccs_cmd_buf[i][19] = dataflag;
            if dataflag == 0:
                continue
            for j in range(0, 8):
                self._write(0x83440068, (j << 16) | (i << 4) | 1, needprint = False)
                ccs_cmd_buf[i][j + 10] = int(self.read(0x8344006c, needprint = False), 16)
                cur = ccs_cmd_buf[i][16] & 0xFFFF
            printcnt1 += 1
            if cur < min:
                min = cur
            if cur > max:
                max = cur

        if (max - min) >= (min - max):
            min = max

        print()
        sub = 0x7FFF
        idx = 0
        for i in range(0, 512):
            got = 0

            for j in range(0, 512):
                if ccs_cmd_buf[j][19] != 0:
                    val = ccs_cmd_buf[j][16] & 0xFFFF
                    if got == 0:
                        idx = j
                        sub = (val - min)
                        got = 1
                    elif (val - min) < sub:
                        sub = (val - min)
                        idx = j
            if got == 0:
                break
            buf = ccs_cmd_buf[idx]
            print("op %2x %08x %08x %08x %08x %08x %08x %08x %08x %08x %08x s:%08x %08x %08x %08x %08x %08x %08x %08x"
                % ((buf[0] >> 8) & 0xFF, buf[0], buf[1], buf[2], buf[3], buf[4], buf[5], buf[6], buf[7], buf[8], buf[9],
                buf[10], buf[11], buf[12], buf[13], buf[14], buf[15], buf[16], buf[17]))

            ccs_cmd_buf[idx][19] = 0
            printcnt2 += 1

        if printcnt1 != printcnt2:
            print("ERR:printcnt1 %d  printcnt2 %d sortd ccs cmd print error.\n" % (printcnt1, printcnt2));

        print("===============ccs command and completion dump=============\n\n")

    def ccs_counter_dump(self):
        print("\n===============ccs counter dump=============\n")
        self._write(0x83440380, ((0x4 << 4) | 0))
        self.read(0x83440384)
        self._write(0x83440380, ((0x4 << 4) | 1))
        self.read(0x83440384)
        self._write(0x83440380, ((0x4 << 4) | 2))
        self.read(0x83440384)

        self._write(0x83440380, ((0x2 << 8) | (0x4 << 4) | 0))
        self.read(0x83440384)
        self._write(0x83440380, ((0x2 << 8) | (0x4 << 4) | 1))
        self.read(0x83440384)
        self._write(0x83440380, ((0x2 << 8) | (0x4 << 4) | 2))
        self.read(0x83440384)

        self._write(0x83440380, ((0xc << 4) | 0))
        self.read(0x83440384)
        self._write(0x83440380, ((0xc << 4) | 1))
        self.read(0x83440384)

        self._write(0x83440380, ((0xd << 4) | 3))
        self.read(0x83440384)
        self._write(0x83440380, ((0xd << 4) | 4))
        self.read(0x83440384)
        self._write(0x83440380, ((0xd << 4) | 0))
        self.read(0x83440384)
        self._write(0x83440380, ((0xd << 4) | 5))
        self.read(0x83440384)

        self._write(0x83440380, ((0x2 << 8) | (0x1 << 4) | 0))
        self.read(0x83440384)
        self._write(0x83440380, ((0x2 << 8) | (0x1 << 4) | 1))
        self.read(0x83440384)
        print("===============ccs counter dump=============\n")

    def ccs_monitor_dump(self):
        print("\n\n===============ccs monitor dump=============\n")
        for i in range (0x0, 0x2c1):
            self._write(0x83440380, i)
            self.read(0x83440384)
        print("===============ccs monitor dump=============\n")

    def ccs_status_dump(self):
        print("\n\n===============ccs status dump=============\n")
        self.read(0x83440054)
        self.read(0x83440058)
        self.read(0x8344005c)
        self.read(0x83440208)
        self.read(0x8344020c)
        self.read(0x83440210)
        self.read(0x83440214)
        self.read(0x83440218)
        self.read(0x8344021c)
        self.read(0x83440220)
        self.read(0x83440224)
        for i in range (0, 16):
            self.read(0x83440400 + (4 * i))
        for i in range (0, 16):
            self.read(0x83440480 + (4 * i))
        print("===============ccs status dump=============\n")

    def bm_dump(self):
        print("\n\n===================================bm dump========================================\n")
        self.bm_rsc_status_dump()
        self.bm_fsm_status_dump()
        self.bm_monitor()
        print("===================================bm dump========================================\n")

    def bm_rsc_status_dump(self):
        print("\n======bm rsc status dump=======\n")
        for i in range (0, 22):
            self.read(0x83430094 + (i * 4))
        print("=======bm rsc status dump=======\n")

    def bm_fsm_status_dump(self):
        print("\n=======bm fsm status dump=======\n")
        for i in range (0, 6):
            self.read(0x8343007c + (i * 4))
        print("=======bm fsm status dump=======\n")

    def bm_monitor(self):
        print("\n\n=======bm monitor dump=======\n")
        for i in range (0x0, 0x4):
            self._write(0x83430054, i)
            self.read(0x83430058)
        for i in range (0x10, 0x14):
            self._write(0x83430054, i)
            self.read(0x83430058)
        for i in range (0x20, 0x24):
            self._write(0x83430054, i)
            self.read(0x83430058)
        for i in range (0x30, 0x31):
            self._write(0x83430054, i)
            self.read(0x83430058)
        for i in range (0x40, 0x51):
            self._write(0x83430054, i)
            self.read(0x83430058)
        for i in range (0x100, 0x120):
            self._write(0x83430054, i)
            self.read(0x83430058)
        for i in range (0x200, 0x210):
            self._write(0x83430054, i)
            self.read(0x83430058)
        for i in range (0x300, 0x310):
            self._write(0x83430054, i)
            self.read(0x83430058)
        for i in range (0x400, 0x405):
            self._write(0x83430054, i)
            self.read(0x83430058)
        for i in range (0x500, 0x520):
            self._write(0x83430054, i)
            self.read(0x83430058)
        for i in range (0x600, 0x602):
            self._write(0x83430054, i)
            self.read(0x83430058)
        for i in range (0x640, 0x641):
            self._write(0x83430054, i)
            self.read(0x83430058)
        for i in range (0x680, 0x682):
            self._write(0x83430054, i)
            self.read(0x83430058)
        for i in range (0x700, 0x710):
            self._write(0x83430054, i)
            self.read(0x83430058)
        for i in range (0x800, 0x802):
            self._write(0x83430054, i)
            self.read(0x83430058)
        for i in range (0x900, 0x902):
            self._write(0x83430054, i)
            self.read(0x83430058)
        for i in range (0xa00, 0xa0c):
            self._write(0x83430054, i)
            self.read(0x83430058)
        for i in range (0xb00, 0xb01):
            self._write(0x83430054, i)
            self.read(0x83430058)
        print("=======bm monitor dump=======\n")

    def fce_dump(self):
        print("\n\n===================================fce dump========================================\n")
        self.fce_status_dump()
        self.fce_monitor_dump()
        print("===================================fce dump========================================\n")

    def fce_status_dump(self):
        self.read(0x8341000c)
        self.read(0x83410230)

    def fce_monitor_dump(self):
        print("\n\n==============fce monitor dump==============\n")
        for ch in range (0x0, 0x10):
            print("\n==============ch %d===========\n" % ch)
            for i in range (0x0, 0x70):
                self._write(0x83410430, (ch << 8 | i))
                self.read(0x83410434)
            print("==============ch %d===========\n\n" % ch)

        for i in range (0x1000, 0x1004):
            self._write(0x83410430, (i))
            self.read(0x83410434)
        for i in range (0x1100, 0x1110):
            self._write(0x83410430, (i))
            self.read(0x83410434)
        for i in range (0x1130, 0x113a):
            self._write(0x83410430, (i))
            self.read(0x83410434)
        for i in range (0x1200, 0x1204):
            self._write(0x83410430, (i))
            self.read(0x83410434)
        for i in range (0x1230, 0x1240):
            self._write(0x83410430, (i))
            self.read(0x83410434)
        for i in range (0x1300, 0x1310):
            self._write(0x83410430, (i))
            self.read(0x83410434)
        for i in range (0x1400, 0x1410):
            self._write(0x83410430, (i))
            self.read(0x83410434)
        for i in range (0x1500, 0x1501):
            self._write(0x83410430, (i))
            self.read(0x83410434)
        for i in range (0x1600, 0x1610):
            self._write(0x83410430, (i))
            self.read(0x83410434)
        for i in range (0x1700, 0x1710):
            self._write(0x83410430, (i))
            self.read(0x83410434)
        for i in range (0x1800, 0x180d):
            self._write(0x83410430, (i))
            self.read(0x83410434)
        for i in range (0x1900, 0x1902):
            self._write(0x83410430, (i))
            self.read(0x83410434)
        for i in range (0x1a00, 0x1a02):
            self._write(0x83410430, (i))
            self.read(0x83410434)
        for i in range (0x1a10, 0x1a20):
            self._write(0x83410430, (i))
            self.read(0x83410434)
        for i in range (0x1b00, 0x1b03):
            self._write(0x83410430, (i))
            self.read(0x83410434)
        for i in range (0x1c00, 0x1c01):
            self._write(0x83410430, (i))
            self.read(0x83410434)
        for i in range (0x1d00, 0x1d02):
            self._write(0x83410430, (i))
            self.read(0x83410434)
        for i in range (0x1e00, 0x1e10):
            self._write(0x83410430, (i))
            self.read(0x83410434)
        for i in range (0x1f00, 0x1f03):
            self._write(0x83410430, (i))
            self.read(0x83410434)
        for i in range (0x2000, 0x2003):
            self._write(0x83410430, (i))
            self.read(0x83410434)
        for i in range (0x2100, 0x2101):
            self._write(0x83410430, (i))
            self.read(0x83410434)
        for i in range (0x2200, 0x2220):
            self._write(0x83410430, (i))
            self.read(0x83410434)
        for i in range (0x2300, 0x2301):
            self._write(0x83410430, (i))
            self.read(0x83410434)
        print("==============fce monitor dump==============\n")

    def hw_cnfg_dump(self):
        print("\n\n\n===============================hw cnfg dump=================================\n\n")
        self.ccs_cnfg_dump()
        self.fce_cnfg_dump()
        self.sdsw_cnfg_dump()
        self.bm_cnfg_dump()
        self.sdsr_cnfg_dump()
        
        self.be_ace_cnfg_dump()
        print("\n\n===============================hw cnfg dump=================================\n\n\n")

    def ccs_cnfg_dump(self):
        print("=======ccs cnfg dump=======\n")
        self.read(0x83440000)
        self.read(0x83440004)
        self.read(0x83440008)
        self.read(0x8344000c)

        for i in range (0, 4):
            self.read(0x83440010 + (i * 0x4))
        for i in range (0, 4):
            self.read(0x83440020 + (i * 0x4)) 
        self.read(0x83440040)
        self.read(0x83440044)
        self.read(0x8344004c)
        self.read(0x83440050)
        self.read(0x83440080)
        self.read(0x83440090)
        self.read(0x83440100)
        self.read(0x83440104)
        self.read(0x83440108)
        self.read(0x8344010c)
        self.read(0x83440110)
        self.read(0x83440114)
        self.read(0x83440118)
        self.read(0x8344011c)
        self.read(0x83440120)
        self.read(0x83440200)
        self.read(0x83440204)
        print("=======ccs cnfg dump=======\n\n\n")

    def fce_cnfg_dump(self):
        print("=======fce cnfg dump=======\n")
        self.read(0x83410000)
        self.read(0x834101b0)
        self.read(0x83410060)
        self.read(0x83410064)
        self.read(0x83410004)
        self.read(0x83410008)
        self.read(0x83410200)
        self.read(0x83410020)
        self.read(0x83410024)
        self.read(0x83410030)
        self.read(0x834103f0)
        for i in range (0, 2):
            self.read(0x83410050 + (i * 4))
        self.read(0x83410058)
        for i in range (0, 32):
            self.read(0x83410120 + (i * 4))
        self.read(0x834101c0)
        print("=======fce cnfg dump=======\n\n\n")

    def sdsw_cnfg_dump(self):
        print("=======sdsw cnfg dump=======\n")
        self.read(0x83450000)
        self.read(0x83450004)
        self.read(0x83450008)
        self.read(0x8345000c)
        self.read(0x834500c0)
        self.read(0x834500cc)
        self.read(0x834500d0)
        print("=======sdsw cnfg dump=======\n\n\n")

    def bm_cnfg_dump(self):
        print("=======bm cnfg dump=======\n")
        self.read(0x83430000)
        self.read(0x83430004)
        self.read(0x83430008)
        self.read(0x8343000c)
        self.read(0x83430010)
        self.read(0x83430014)
        self.read(0x83430018)
        self.read(0x8343001c)
        for i in range (0, 7):
            self.read(0x83430020 + (i * 4))
        self.read(0x8343002c)
        self.read(0x83430030)
        self.read(0x83430034)
        self.read(0x83430038)
        self.read(0x83430100)
        self.read(0x83430108)
        self.read(0x8343010c)
        self.read(0x83430110)
        print("=======bm cnfg dump=======\n\n\n")

    def sdsr_cnfg_dump(self):
        print("=======sdsr cnfg dump=======\n")
        self.read(0x83450200)
        self.read(0x83450208)
        self.read(0x83450260)
        self.read(0x83450264)
        print("=======sdsr cnfg dump=======\n\n\n")

    def be_ace_cnfg_dump(self):
        print("=======be ace cnfg dump=======\n")
        for i in range (0x1500, 0x15cc, 8):
            self.read(0x83d10000 + i)
        self.read(0x83d11800)
        print("=======be ace cnfg dump=======\n\n\n")

    def _write(self, addr=0x8010, value=0xfee1dead ,needprint = True):
        try:
            if needprint:
                print('Write addr=0x%08x'%addr + ' value=0x%08x'%value)
            os.system("sudo ./pcimem %s 0x8000 w %s" % (self.devName, addr))
            #print("sudo ./pcimem %s 0x8000 w %s" % (self.devName, addr))
            os.system("sudo ./pcimem %s 0x8004 w 0x%x" % (self.devName, value))
            #print("sudo ./pcimem %s 0x8004 w %x" % (self.devName, value))
            _value = subprocess.run("sudo ./pcimem %s 0x8008 w" % (self.devName), shell=True, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT).stdout.decode(errors='ignore').strip()
            _value = int(_value, 16)
            if needprint:
                print('Read back addr=0x%08x'%addr + ' value=0x%x'%_value)
        except ValueError:
            print("Bad addr: %s value: %s" % (addr, value))

    #addr and value are both hex number
    def _write_hex(self, addr=0x8010, value=0xfee1dead):
        try:
            #print 'Write addr=0x%08x'%addr + ' value=0x%08x'%value
            os.system("sudo ./pcimem %s 0x8000 w 0x%08x" % (self.devName, addr))
            #print ("sudo ./pcimem %s 0x8000 w 0x%08x" % (self.devName, addr))
            os.system("sudo ./pcimem %s 0x8004 w 0x%x" % (self.devName, value))
            #print ("sudo ./pcimem %s 0x8004 w %x" % (self.devName, value))
            #self._write(addr, value)
            _value = subprocess.run("sudo ./pcimem %s 0x8008 w" % (self.devName), shell=True, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT).stdout.decode(errors='ignore').strip()
            #print ("sudo ./pcimem %s 0x8008 w" % (self.devName))
            #print _value
            _value = int(_value, 16)
            #print 'Read back addr=0x%08x'%addr + ' value=0x%x'%_value
        except ValueError:
            print("Bad addr: 0x%08x value: 0x%08x" % (addr, value))

    def write(self, args):
        __args = args.split()
        if len(__args) == 1 :
            print("Wrong format.")
        else:
            try:
                addr = int(__args[0],16)
            except ValueError:
                ## convert to address
                if __args[0] in rl:
                    addr = rl[__args[0]][1]

            try:
                value = int(__args[1], 16)
                print('Write addr=0x%08x'%addr + ' value=0x%08x'%value)
                os.system("sudo ./pcimem %s 0x8000 w %s" % (self.devName, addr))
                #print("sudo ./pcimem %s 0x8000 w %s" % (self.devName, addr))
                os.system("sudo ./pcimem %s 0x8004 w 0x%x" % (self.devName, value))
                #print("sudo ./pcimem %s 0x8004 w %x" % (self.devName, value))
                _value = subprocess.run("sudo ./pcimem %s 0x8008 w" % (self.devName), shell=True, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT).stdout.decode(errors='ignore').strip()
                _value = int(_value, 16)
                print('Read back addr=0x%08x'%addr + ' value=0x%x'%_value)
                # self.read(addr)
            except ValueError:
                print("Bad value: %s" % (__args[1]))

    def read_hex(self, addr=0x8010):
        #print ('Read_hex 0x%08x'%addr)
        os.system("sudo ./pcimem %s 0x8000 w 0x%08x" % (self.devName, addr))
        #print("sudo ./pcimem %s 0x8000 w 0x%08x" % (self.devName, addr))
        val = subprocess.run("sudo ./pcimem %s 0x8008 w" % (self.devName), shell=True, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT).stdout.decode(errors='ignore').strip()
        #print ("sudo ./pcimem %s 0x8008 w" % (self.devName))
        #prinu val
        return int(val,16)

    def jlink_script_read(self, regs_filename):
        regs_fp = open(regs_filename)
        script_fp = open(jlink_script_file, 'w+')
        regs_name = regs_fp.readlines()
        for line in regs_name:
            name = line.replace('\n', '')
            if name in list(rl.keys()):
                addr = rl[name][1]
                addr_str = str(hex(addr)).replace('0x', '').zfill(8)
                onecmd = 'mem32 ' + addr_str + ' 1' + '\n'
                script_fp.write(onecmd)
        script_fp.write('exit')
        script_fp.close()
        run_jlink_cmd = jlink_basic_cmd + '-CommanderScript ' + jlink_script_file + ' >' \
                         + jlink_output_file + ' 2>&1'
        os.system(run_jlink_cmd)
        output_fp = open(jlink_output_file, 'r')
        output = output_fp.readlines()
        for line in regs_name:
            name = line.replace('\n', '')
            if name in list(rl.keys()):
                addr = rl[name][1]
                addr_str = str(hex(addr)).replace('0x', '').zfill(8) + ' = '
                for result in output:
                    if addr_str in result:
                        val = result[(result.rfind('= ') + 2):] 
                        for k,o in list(rl.items()):
                            if ( (addr) >= o[0][1][0] and (addr)<o[0][1][1]):
                                obj = o[0]
                                break

                        if 'obj' in locals():
                            self.decode_obj(obj, addr, 0, val)
        print('\n')
        output_fp.close()
        regs_fp.close()
        if os.path.exists(jlink_script_file):
            os.remove(jlink_script_file)
        if os.path.exists(jlink_output_file):
            os.remove(jlink_output_file)

    def jlink_reads(self, name, length, quiet):
        if name in list(rl.keys()):
            self.jlink_read(rl[name][1], length*rl[name][3]/4/8, quiet)
        else:
            print("Wrong register name %s!!!!" % name)

    def jlink_read(self, addr, length=1, quiet=0):
        script_fp = open(jlink_script_file, 'w+') 
        onecmd = 'mem32 ' + str(hex(addr)) + ' ' + str(length) + '\n'
        script_fp.write(onecmd)
        script_fp.write('exit')
        script_fp.close()
        run_jlink_cmd = jlink_basic_cmd + '-CommanderScript ' + jlink_script_file + ' >' \
                     + jlink_output_file + ' 2>&1' 
        os.system(run_jlink_cmd)
        output_fp = open(jlink_output_file, 'r')
        output = output_fp.readlines()
        addr_str = str(hex(addr)).replace('0x', '')
        for line in output:
            if addr_str in line:
                val = line[(line.rfind('= ') + 2):] 
        output_fp.close()
        if (quiet == 0):
            for k,o in list(rl.items()):
                if ( (addr) >= o[0][1][0] and (addr)<o[0][1][1]):
                    obj = o[0]
                    break

            if 'obj' in locals():
                self.decode_obj(obj, addr, 0, val)
            print("\n")
        if os.path.exists(jlink_script_file):
            os.remove(jlink_script_file)
        if os.path.exists(jlink_output_file):
            os.remove(jlink_output_file)
        return val

    def jlink_script_write(self, regs_filename):
        regs_fp = open(regs_filename)
        script_fp = open(jlink_script_file, 'w+')
        regs_val = regs_fp.readlines()
        for line in regs_val:
            line = line.split()
            name = line[0]
            value = line[1]
            if name in list(rl.keys()):
                addr = rl[name][1]
                addr_str = str(hex(addr)).replace('0x', '').zfill(8)
                value= value.replace('0x', '').zfill(8)
                print(('Write register name ' + name + ' addr 0x' + addr_str + ' value 0x' + value))
                onecmd = 'w4 ' + addr_str + ' ' + value + '\n'
                script_fp.write(onecmd)
        script_fp.write('exit')
        script_fp.close()
        run_jlink_cmd = jlink_basic_cmd + '-CommanderScript ' + jlink_script_file + ' >' \
                         + jlink_output_file + ' 2>&1'
        os.system(run_jlink_cmd)
        print('\n')
        for line in regs_val:
            line = line.split()
            name = line[0]
            value = line[1]
            if name in list(rl.keys()):
                addr = rl[name][1]
                addr_str = str(hex(addr)).replace('0x', '').zfill(8)
                _value = self.jlink_read(addr, 1, quiet=1)
                addr_str = str(hex(addr)).replace('0x', '').zfill(8)
                print(('Read back register name ' + name + ' addr 0x' + addr_str + ' value 0x' + _value))
        regs_fp.close()
        if os.path.exists(jlink_script_file):
            os.remove(jlink_script_file)


    def jlink_write(self, args):
        __args = args.split()
        if len(__args) != 2:
           print("Wrong format.")
        else:
            try:
                addr = int(__args[0],16)
            except ValueError:
                ## convert to adress
                if __args[0] in rl:
                    addr = rl[__args[0]][1]
                else:
                    addr = -1
            if ( addr !=  -1 ) :
                try:
                    value = int(__args[1], 16)
                    f = open(jlink_script_file, 'w+') 
                    onecmd = 'w4 ' + str(hex(addr)) + ' ' + str(value) + '\n'
                    f.write(onecmd)
                    f.write('exit')
                    f.close()
                    run_jlink_cmd = jlink_basic_cmd + '-CommanderScript ' + jlink_script_file + ' >' \
                                 + jlink_output_file + ' 2>&1' 
                    os.system(run_jlink_cmd)
                    _value = self.jlink_read(addr, 1, quiet=1) 
                    _value = int(_value)
                    print('Read back addr=0x%08x'%addr + ' value=0x%x'%_value)
                except ValueError:
                    print("Bad value: %s" % (__args[1]))
            else:
                print("Bad register name: %s" % (__args[0]))

    def i2c_pf(self):
        os.popen("sudo ./i2c_pf %s"%self.devName)
