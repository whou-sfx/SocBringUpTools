#!/usr/bin/env python

import os
import cmd
import readline
import atexit
import re
import time
import sys

import subprocess

# from xhal import reg_list, XHal
from .xhal import XHal
from .xhal import cheeta
from .xhal import ch_num
from .xhal import ce_num
from .xhal import skip_ch
from .xhal import lun_num
from .xreg_for_quince import reg_list as rl
from .xspi_nor import XSpi_nor
from .scr_seed_lut import seed_lut

################################################################################
class ConsoleBase(cmd.Cmd):

    def __init__(self, histfile=os.path.expanduser("~/.console-history")):
        cmd.Cmd.__init__(self)
        self.prompt = "=>> "
        self.intro  = "Welcome to console!"  ## defaults to None
        self.init_history(histfile)

    def init_history(self, histfile):
        readline.parse_and_bind("tab: complete")
        if hasattr(readline, "read_history_file"):
            try:
                readline.read_history_file(histfile)
            except IOError:
                pass
            atexit.register(self.save_history, histfile)

    def save_history(self, histfile):
        readline.write_history_file(histfile)

    # ## Command definitions ##
    # def do_hist(self, args):
    #     """Print a list of commands that have been entered"""
    #     print self._hist

    def do_exit(self, args):
        """exit/quit/q, Exits from the console"""
        return -1

    ## Command definitions to support Cmd object functionality ##
    # def do_EOF(self, args):
    #     """Exit on system end of file character"""
    #     return self.do_exit(args)

    def do_shell(self, args):
        """shell/!, Pass command to a system shell when line begins with '!'"""
        os.system(args)

    def do_help(self, args):
        """help/?/h, Get help on commands
           'help' or '?' or 'h' with no arguments prints a list of commands for which help is available
           'help <command>' or '? <command>' gives help on <command>
        """
        ## The only reason to define this method is for the help text in the doc string
        cmd.Cmd.do_help(self, args)

    ## Override methods in Cmd object ##
    def preloop(self):
        """Initialization before prompting user for commands.
           Despite the claims in the Cmd documentaion, Cmd.preloop() is not a stub.
        """
        cmd.Cmd.preloop(self)   ## sets up command completion
        # self._hist    = []      ## No history yet
        self._locals  = {}      ## Initialize execution namespace for user
        self._globals = {}

    def postloop(self):
        """Take care of any unfinished business.
           Despite the claims in the Cmd documentaion, Cmd.postloop() is not a stub.
        """
        cmd.Cmd.postloop(self)   ## Clean up command completion
        print("Exiting...")

    def precmd(self, line):
        """ This method is called after the line has been input but before
            it has been interpreted. If you want to modifdy the input line
            before execution (for example, variable substitution) do it here.
        """
        line=line.strip()
        if line != "":
            #mapping command here
            # re.sub('^r ', 'read ', line)
            # re.sub('^w ', 'write ', line)
            line=re.sub('^quit', 'exit', line)
            line=re.sub('^q$','exit',line)
            line=re.sub('^h ','help ',line)
            line=re.sub('^h$','help',line)
        return line

    def postcmd(self, stop, line):
        """If you want to stop the console, return something that evaluates to true.
           If you want to do some post command processing, do it here.
        """
        return stop

    def emptyline(self):
        """Do nothing on empty input line"""
        pass


    def default(self, line):
        """Called on an input line when the command prefix is not recognized.
           In that case we execute the line as Python code.
        """
        try:
            exec((line), self._locals, self._globals)
        except Exception as e:
            print(e.__class__, ":", e)


################################################################################
class XConsole(ConsoleBase):
    def __init__(self, intro='XConsole', prompt='>', pciPort =None, dev =None, slot =None):
        ConsoleBase.__init__(self)
        self.prompt = prompt
        self.intro = intro
        self.xhal = XHal(pciPort, dev, slot)
        #if debug on asic, do XSpi_nor(0); if on haps, do XSpi_nor()
        #self.nor = XSpi_nor()
        self.nor = XSpi_nor(haps=1)
        # self.prompt = "XScope> "
        # self.intro  = "Xscope 0.1.0\nCopyright (C) Scaleflux Inc. 2015\n"  ## defaults to None

    def do_set_dev(self, args):
        """set target access device, set_dev nvme0"""
        __args = args.split()

        print('Access Dev %s'% (__args[0]))
        self.xhal = XHal(dev=__args[0])
        self.nor = XSpi_nor(haps=1, dev=__args[0])

    def do_set_slot(self, args):
        """set target access slot, set_slot 01:00.0"""
        __args = args.split()

        print('Access slot %s' % (__args[0]))
        self.xhal = XHal(slot=__args[0])
        self.nor = XSpi_nor(haps=1, slot=__args[0])

    def do_jlink_script_read(self, args):
        """Read Registers list in a file using jlink , jlink_script_read <regs_list_file>"""
        __args = args.split()
        self.xhal.jlink_script_read(__args[0])

    def do_jlink_read(self, args):
        """Read Register via jlink, jlink_read <addr/name> [length=1]"""
        __args = args.split()
        _maker = 0
        if len(__args) == 1:
            _maker = 1
            __args.append('1')
        try:
            self.xhal.jlink_read(int(__args[0], 16), int(__args[1]))
        except ValueError:
            if _maker == 1:
                __args[1] = '1'
            self.xhal.jlink_reads(__args[0], int(__args[1]), quiet=0)

    def do_jlink_script_write(self, args):
        """Write Registers list in a file using jlink, jlink_script_write <regs_list_file>"""
        self.xhal.jlink_script_write(args)

    def do_jlink_write(self, args):
        """Write Register via jlink, jlink_write <hex add rname> <hex value>"""
        self.xhal.jlink_write(args)

    def do_fcelmemdump(self, args):
        """loop 256 num to dump feace memory"""
        for i in range (0, 256):
            value = 0x3118
            self.xhal.write(0x83410410, value)
            self.xhal.read(0x83410418, 1)
            value += 0x4

    def do_cmdtbldump(self, args):
        """dump cmdtbl info as same as uart cmd cmdtbl"""
        self.xhal.cmdtbl_dump()

    def do_nvmedump(self, args):
        """dump nvme register as same as uart cmd nvmedbg"""
        print("\nFPGA version:")
        self.xhal.read(0x83400000, 1)
        # here is nvme ip status dump
        self.xhal.nvmeipstatus_dump()
        # here is nvme ip sq cq dump
        self.xhal.nvmeipsqcq_dump()
        # here is Nlog count dump
        self.xhal.nlogcount_dump()
        # here is NFE error dump
        self.xhal.nfeerror_dump()
        # here is APU error dump
        self.xhal.apuerror_dump()
        # here is plda dump
        self.xhal.plda_dump()
        # here is fe ace monitor dump
        self.xhal.feacemonitor_dump()
        # here is fis dump
        self.xhal.fis_dump()
        # here is loc status dump
        self.xhal.locstatus_dump()
        # here is fe ace status dump
        self.xhal.feacestatus_dump()
        # here is ip cmdtbl dump
        self.xhal.cmdtbl_dump()
        # here is errcode dbg dump
        self.xhal.errcodedbg_dump()
        # here is pnsram  dump
        self.xhal.pnsram_dump()

    def do_hwdump(self, args):
        """dump hw register as same as uart cmd hwdbg"""
        print("FPGA version:")
        self.xhal.read(0x83400000, 1)
        # here is BEACE dump
        self.xhal.beace_dump()
        # here is sdsr dump
        self.xhal.sdsr_dump()
        # here is sdsw dump
        self.xhal.sdsw_dump()
        # here is ccs dump
        self.xhal.ccs_dump()
        # here is bm dump
        self.xhal.bm_dump()
        # here is fce dump
        self.xhal.fce_dump()
        # here is b2n prep status dump
        self.xhal.b2nprepstatus_dump()
        # here is vendor reg dump
        #self.xhal.vendorreg_dump()
        # here is sysdma csr dump
        self.xhal.sysdmacsr_dump()
        # here is hw cnfg dump
        self.xhal.hw_cnfg_dump()
            

    def do_read(self, args):
        """Read Register, read <addr/name> [length=1], TAB to show/auto complete register list """
        __args = args.split()
        _maker = 0
        if len(__args) == 1:
            _maker = 1
            __args.append('1')
        # print 'Read {0} {1}'.format(__args[0], __args[1])
        try:
            self.xhal.read(int(__args[0], 16), int(__args[1], 16))
        except ValueError:
            if _maker == 1:
                __args[1] = '1'
            self.xhal.reads(__args[0], int(__args[1]))

    def do_read_ddr(self, args):
        """Read DDR, read_ddr <addr> [length=1]"""
        __args = args.split()
        if len(__args) == 1:
            __args.append('1')
        # print 'Read {0} {1}'.format(__args[0], __args[1])
        self.xhal.read_ddr(int(__args[0], 16), int(__args[1], 16))

    def do_dump_evtlog(self, args):
        """Read original evtlog data from DDR, 
           Usage: dump_evtlog
        """
        self.xhal.dump_evtlog()

    def do_dump_ddr(self, args):
        """Dump DDR to bin file, dump_ddr <addr> [length=1]"""
        __args = args.split()
        if len(__args) == 1:
            __args.append('1')
        self.xhal.dump_ddr_to_bin(int(__args[0], 16), int(__args[1], 16))

    def do_read_sram(self, args):
        """Read DDR, read_ddr <addr> [length=1]"""
        __args = args.split()
        if len(__args) == 1:
            __args.append('1')
        # print 'Read {0} {1}'.format(__args[0], __args[1])
        self.xhal.read_sram(int(__args[0], 16), int(__args[1], 16))
        
    def do_dump_sram(self, args):
        """Dump SRAM to bin file, dump_SRAM <addr> [length=1]"""
        __args = args.split()
        if len(__args) == 1:
            __args.append('1')
        self.xhal.dump_sram_to_bin(int(__args[0], 16), int(__args[1], 16))

    def do_write(self,args):
        """Write Register, write <addr> <value>, TAB to show/auto complete register list"""
        self.xhal.write(args)

    def do_pf(self, args):
        """trigger I2C pf"""
        self.xhal.i2c_pf()

    ### Nor ACCESS sub cmds ####
    def do_nor_erase_subsector(self, args):
        """erase 4k sub sector
           Usage: nor_erase_subsector $offset
           eg:    nor_erase_subsector 0x100000
        """
        self.nor.nor_erase_subsector(int(args, 16))

    def do_nor_erase_sector(self, args):
        """erase 64k sector
           Usage: nor_erase_sector $offset
           eg   : nor_erase_sector 0x100000
        """
        self.nor.nor_erase_sector(int(args, 16))

    def do_nor_read_data(self, args):
        """Read data from nor at offset
           Usage: nor_read_data $offset $len_in_bytes
           eg:    nor_read_data 0x1000000 32
        """
        __args = args.split()
        self.nor.nor_read_data(int(__args[0], 16), int(__args[1]))

    def do_nor_write_data(self, args):
        """Program data to nor at offset
           Usage: nor_write_data $offset  $data 
           eg:    nor_write_data 0x100000 [0xab, 0xabab, 0xababab, 0xababababab]
        """
        s_index = args.index("[")
        e_index = args.index("]")
        __args = args.split()
        addr = int(__args[0], 16)
        data = args[s_index+1:e_index].split(",")
        #iteratively covert str to hex number
        data = [int(i, 16) for i in data]
        self.nor.nor_write_data(addr, data)

    def do_nor_program_img(self, args):
        """program binary img to nor at offset
           Usage: nor_program_img $offset $input_bin_file
           eg:    nor_program_img 0x0 /home/tcn/xxx.bin
        """
        __args = args.split()
        self.nor.nor_program_img(int(__args[0], 16), __args[1])

    """
    # please use nor_program_img to program bl2
    def do_ndl2(self, args):
        #program bl2 img to nor
        #   Very slow, please be patient
        #   Usage: ndl2 $input_bin_file
        #   eg:    ndl2 /home/tcn/bl2.bin
        
        __args = args.split()
        self.nor.nor_program_img(0x0, __args[0]) # TODO may need to change if there exist a nor bl1
    """
    def do_ncl2(self, args):
        """clear bl2 golden img
           Usage: ncl2
        """
        __args = args.split()
        self.nor.nor_ncl2()

    def do_ncl3(self, args):
        """clear bl3 golden img
           Usage: ncl3
        """
        __args = args.split()
        self.nor.nor_ncl3()


    def do_npt(self, args):
        """update nor write protect area
           Usage: npt [0 1 2 3]
           0, PROTECT_NONE
           1, PROTECT_1M
           2, PROTECT_8M
           3, PROTECT_16M
           others, PROTECT_ALL
           eg:    npt 0
        """
        __args = args.split()
        self.nor.nor_update_protect_area(int(__args[0], 16))

    def do_boots(self, args):
        """update nor boot option
           Usage: boots [0 1 2 3 4]
           0, boot BL3 golden
           1 ~ 4: boot BL3 from RFS slot 1 ~ 4
           eg:    boots 0
        """
        __args = args.split()
        return self.nor.nor_update_boot_opt(int(__args[0], 16))

    def do_nortest(self, args):
        # tmp add for _testqspi_nor_write_status issue debug
        __args = args.split()
        self.nor._testqspi_nor_write_status(0x60606020)

    def do_nid(self, args):
        """Dump nor manufacturer id
           Usage: nid
        """
        self.nor.nor_read_id()

    ### End of NOR ACCESS sub cmds ###

    def complete_read(self, text, line, start_index, end_index):
        # print enumerate(xhal.reg_list.keys())
        if text:
            return [reg for reg in list(rl.keys())
                    if reg.startswith(text)]
        else:
            return list(rl.keys())

    def complete_desc(self, text, line, start_index, end_index):
        # print enumerate(xhal.reg_list.keys())
        return self.complete_read(text, line, start_index, end_index)

    def complete_write(self, text, line, start_index, end_index):
        # print enumerate(xhal.reg_list.keys())
        return self.complete_read(text, line, start_index, end_index)

    def precmd(self, line):
        """ This method is called after the line has been input but before
            it has been interpreted. If you want to modifdy the input line
            before execution (for example, variable substitution) do it here.
        """
        line=ConsoleBase.precmd(self,line)
        if line != "":
            #mapping command here
            line=re.sub('^r ', 'read ', line)
            line=re.sub('^w ', 'write ', line)
            if line[0] == '#':  # this is comments, skip it.
                line = ""
        return line

################################################################################
if __name__ == '__main__':
    console = XConsole()
    console . cmdloop()
