import os
import struct
import time
from .xreg_for_quince import reg_list as rl
from .nor_cmd import nor_cmds as ncmd
from .xhal import XHal



# Reg access Interface
xhal = XHal()
#Debug Reg Access Flow
reg_debug = 0
#Fake Reg Access
fake = 0

def MDELAY(delay_in_ms):
    ms = delay_in_ms / 1000
    time.sleep(ms)
def DELAY(delay_in_sec):
    time.sleep(delay_in_sec);


#Hook functions to do hw reg access throught pcimem which called by xhal
def SPI_REG_WR(addr = 0, value = 0):
    if reg_debug:
        print('Write [0x%08x] = 0x%08x' %(addr, value))
    if fake == 0 :
        xhal._write_hex(addr, value)

def SPI_REG_RD(addr = 0):
    val = 0
    if fake == 0 :
        val = xhal.read_hex(addr);
    if reg_debug:
        print('Read 0x%08x, value 0x%08x' %(addr,val))

    return val

def SPI_DIRECT_RD(offset = 0):
    val = 0
    NOR_DIRECT_READ_BASE=0x80000000
    addr = NOR_DIRECT_READ_BASE + offset
    if reg_debug:
        print('DirectRead 0x%08x' %addr)
    if fake == 0 :
        val = xhal.read_hex(addr);
    return val

##########End of Hook functions


######## MACRON DEFINES###########
MAX_NR_SECTORS = 512
BL2_0_OFFSET = 0
BL2_1_OFFSET = (512 * 1024)
BL3_OFFSET = (1024 * 1024)

#Micron protect area bitmap
gMicronPtArea = {
'PT_NONE'	:(1<<5),
'PT_1M'	    :((1<<5) | (1<<2) | (1<<4)),
'PT_8M'	    :((1<<5) | (1<<6)),
'PT_16M'	:((1<<5) | (1<<2) | (1<<6)),
'PT_32M'	:((1<<5) | (1<<3) | (1<<6)),
'PT_ALL'	:((1<<5) | (1<<2) | (1<<3) | (1<<4) | (1<<6)),
'PT_MASK'	:((0x1F << 2) | (1 << 7))
}

MXIC_B_SELECT=(1 << 3)
gMXICPtArea = {
'PT_NONE'   :(0),
'PT_1M'     :((1 << 2) | (1 << 4)),
'PT_8M'     :(1 << 5),
'PT_16M'    :((1 << 2) | (1 << 5)),
'PT_32M'    :((1 << 3) | (1 << 5)),
'PT_ALL'    :((1 << 2) | (1 << 3) | (1 << 4) | (1 << 5)),
'PT_MASK'   :((0xF << 2) | (1 << 7))
}


def _get_pt_area(type):
    if type == 0:
        return "PT_NONE"
    elif type == 1:
        return "PT_1M"
    elif type == 2:
        return "PT_8M"
    elif type == 3:
        return "PT_16M"
    else:
        return "PT_ALL"


def print_hex(data=[]):
    l = [hex(int(i)) for i in data]
    print((" ".join(l)))

def split_list_by_n(data, n):
    for i in range(0, len(data), n):
        yield data[i: i + n]


#SPI NOR ACCESS Class
class XSpi_nor:
    def __init__(self, haps=0, debug=0, verbo=0, dev="", slot=""):
        # debug output
        self.debug = debug
        self.verbose = verbo
        self.haps = haps
        self.nor_indirect_rd = 0
        self.nor_erase_max_retry = 3
        self.nor_write_max_retry = 3
        # Reg access Interface
        self.xhal = XHal(dev=dev, slot=slot)

        #print('haps %d debug %d, verbo %d' % (haps,debug,verbo))

        # test on haps or asic, they has different clk

        # should set clk_div by check haps and read_mode
        if self.haps:
            self.clk_div = 2
        else:
            if self.nor_indirect_rd:
                self.clk_div = 16
            else:
                self.clk_div = 24
        # init spi
        self._spi_nor_init()

    def _wait_for_idle(self):
        if self.debug and self.verbose:
            print("   >wait_for_idle")
        loop = 0
        status = SPI_REG_RD(rl['SSPSR'][1])
        while status & 0x10:
            status = SPI_REG_RD(rl['SSPSR'][1])
            #Delay is necessary to make indirect_reg access finish
            loop += 1
            if loop % 100 == 0:
                print('Warning: _wait_for_idle timeout' + 'status 0x%02x'%status)
                break
        if self.debug and self.verbose:
            print("   =wait_for_idle end")
    
    def _flush_rx_fifo(self):
        if self.debug and self.verbose:
            print("   >flush_rx_fifo")
        self._wait_for_idle();
        loop = 0
        SPI_REG_RD(rl['SSPDR'][1])
        status = SPI_REG_RD(rl['SSPSR'][1])
        while status & 0x4:
            SPI_REG_RD(rl['SSPDR'][1])
            status = SPI_REG_RD(rl['SSPSR'][1])
            loop += 1
            if loop % 1000 == 0:
                print('Warning: _flush_rx_fifo timeout' + 'status 0x%02x'%status)
                break
        if self.debug and self.verbose:
            print("   =flush_rx_fifo end")

    def _dummy_read(self, cnt = 1):
        if self.debug and self.verbose:
            print("   >dummy_read %d"%cnt)
        for i in range(cnt):
            SPI_REG_RD(rl['SSPDR'][1]) 
        if self.debug and self.verbose:
            print("   =dummy_read end")

    #send sector/sub_sector_erase cmd to nor
    def _spi_nor_erase_raw(self, start_addr = 0, subsector_erase=0):
        if self.debug and self.verbose:
            print("  >>spi_nor_erase_raw at offst 0x%08x subsec=%d"%(start_addr, subsector_erase))

        SPI_REG_WR(rl['SSPCS_IND_CS'][1], 0x1)
        #erase command
        if subsector_erase :
            SPI_REG_WR(rl['SSPDR'][1], ncmd['SUBSECT_ERASE_4KB_4B'])
        else :
            SPI_REG_WR(rl['SSPDR'][1], ncmd['SECT_ERASE_4B'])
        #push 4 Bytes address
        SPI_REG_WR(rl['SSPDR'][1], ((start_addr >> 24) & 0xFF))
        SPI_REG_WR(rl['SSPDR'][1], ((start_addr >> 16) & 0xFF))
        SPI_REG_WR(rl['SSPDR'][1], ((start_addr >> 8) & 0xFF))
        SPI_REG_WR(rl['SSPDR'][1], (start_addr & 0xFF))
        self._wait_for_idle()
        self._dummy_read(5)
        SPI_REG_WR(rl['SSPCS_IND_CS'][1], 0x0)
        
        if subsector_erase == 0:
            DELAY(3)
        if self.debug and self.verbose:
            print("  ==spi_nor_erase_raw end")

    def _spi_nor_write_data_raw(self, start_addr = 0, data = []):
        if self.debug and self.verbose:
            print("  >>spi_nor_write_data_raw start")

        SPI_REG_WR(rl['SSPCS_IND_CS'][1], 0x1)
        #program command
        SPI_REG_WR(rl['SSPDR'][1], ncmd['PAGE_PROG_4B'])
        #push 4 Bytes address
        SPI_REG_WR(rl['SSPDR'][1], ((start_addr >> 24) & 0xFF))
        SPI_REG_WR(rl['SSPDR'][1], ((start_addr >> 16) & 0xFF))
        SPI_REG_WR(rl['SSPDR'][1], ((start_addr >> 8) & 0xFF))
        SPI_REG_WR(rl['SSPDR'][1], (start_addr & 0xFF))
        self._wait_for_idle()
        self._dummy_read(5)
        
        # push data
        for wdata in data:
            SPI_REG_WR(rl['SSPDR'][1], (wdata & 0xFF))
            SPI_REG_WR(rl['SSPDR'][1], ((wdata >> 8) & 0xFF))
            SPI_REG_WR(rl['SSPDR'][1], ((wdata >> 16) & 0xFF))
            SPI_REG_WR(rl['SSPDR'][1], ((wdata >> 24) & 0xFF))
            self._wait_for_idle()
            self._dummy_read(4)

        #Unselect the CS
        SPI_REG_WR(rl['SSPCS_IND_CS'][1], 0x0)

        if self.debug  and self.verbose:
            print("  ==spi_nor_write_data_raw end")
      

    # check spi execute cmd status
    def _spi_nor_read_status(self):
        if self.debug and self.verbose:
            print("   >spi_read_status start")

        SPI_REG_WR(rl['SSPCS_IND_CS'][1], 0x0001)
        SPI_REG_WR(rl['SSPDR'][1], ncmd['RD_STA_REG'])
        self._wait_for_idle()
        self._dummy_read(1)

        SPI_REG_WR(rl['SSPDR'][1], 0x0)
        self._wait_for_idle()
        status = SPI_REG_RD(rl['SSPDR'][1])
        SPI_REG_WR(rl['SSPCS_IND_CS'][1], 0x0000)

        if self.debug and self.verbose:
            print("   =spi_read_status end status 0x%02x"%status) 


        return status

    # read nor configuration register
    def _spi_nor_read_cfg_reg(self):
        if self.debug and self.verbose:
            print("   >spi_read_cfg_reg start")

        SPI_REG_WR(rl['SSPCS_IND_CS'][1], 0x0001)
        SPI_REG_WR(rl['SSPDR'][1], ncmd['RD_CFG_REG'])
        self._wait_for_idle()
        self._dummy_read(1)

        SPI_REG_WR(rl['SSPDR'][1], 0x0)
        self._wait_for_idle()
        regVal = SPI_REG_RD(rl['SSPDR'][1])
        SPI_REG_WR(rl['SSPCS_IND_CS'][1], 0x0000)

        if self.debug and self.verbose:
            print("   =spi_read_cfg_reg end val 0x%02x"%regVal)


        return regVal


    def _nor_erase_write_polling_compl(self):
        if self.debug and self.verbose:
            print("  >nor_erase_write_polling_compl start")
        loop = 0
        status = self._spi_nor_read_status()
        while status & 0x1:
            status = self._spi_nor_read_status()
            MDELAY(1)
            loop += 1
            if loop % 1000 == 0:
                print('Warning: nor_erase_write not complete more than  1s' + 'status 0x%02x'%status)
                return -1
        if self.debug and self.verbose:
            print("   =nor_erase_write_polling_compl end, loop %d"%loop)
        return 0

    def _spi_nor_check_status(self, mask, val):
        if self.debug:
            print("   >spi_nor_check_status start: mask 0x%02x val 0x%02x"%(mask, val))

        loop = 0
        status = self._spi_nor_read_status()
        while (status & mask) != (val & mask):
            status = self._spi_nor_read_status()
            MDELAY(1)
            loop += 1
            if loop % 100 == 0:
                print('Warning: read check status timeout, expect 0x%02x, current 0x%02x' %((val & mask), (status & mask)))
                return -1
        return 0

    def _spi_write_enable(self):
        if self.debug and self.verbose:
            print("  >spi_write_enable start")
        loop = 0
        SPI_REG_WR(rl['SSPCS_IND_CS'][1], 0x0001)
        SPI_REG_WR(rl['SSPDR'][1], ncmd['WR_EN'])
        self._wait_for_idle()
        self._dummy_read(1)
        SPI_REG_WR(rl['SSPCS_IND_CS'][1], 0x0000)

        status = self._spi_nor_read_status()
        while (status & 0x2) == 0 :
            status = self._spi_nor_read_status()
            MDELAY(1)
            loop += 1
            if loop % 100 == 0:
                print('Warning: spi write enable timeout, status 0x%x'%status)
                return -1
        if self.debug and self.verbose:
            print("   =spi_write_enable end")
        return 0

    def _spi_nor_write_status(self, status):
        print("update protect area by status 0x%02x"%status)
        self._spi_write_enable()

        SPI_REG_WR(rl['SSPCS_IND_CS'][1], 0x0001)
        SPI_REG_WR(rl['SSPDR'][1], ncmd['WR_STA_REG'])
        SPI_REG_WR(rl['SSPDR'][1], status)
        self._wait_for_idle()
        self._dummy_read(2)
        SPI_REG_WR(rl['SSPCS_IND_CS'][1], 0x0000)

        ret = self._nor_erase_write_polling_compl()
        if ret != 0 :
            print("Write nor status register fail")

        if self.debug:
            print("   =spi_nor_write_status end ret 0x%02x"%ret)

        return ret

    def _spi_nor_write_status_ex(self, status, cfg):
        print("update protect area by status 0x%02x, cfg 0x%02x"%(status, cfg))
        self._spi_write_enable()

        SPI_REG_WR(rl['SSPCS_IND_CS'][1], 0x0001)
        SPI_REG_WR(rl['SSPDR'][1], ncmd['WR_STA_REG'])
        SPI_REG_WR(rl['SSPDR'][1], status)
        SPI_REG_WR(rl['SSPDR'][1], cfg)
        self._wait_for_idle()
        self._dummy_read(3)
        SPI_REG_WR(rl['SSPCS_IND_CS'][1], 0x0000)

        ret = self._nor_erase_write_polling_compl()
        if ret != 0 :
            print("Write nor status register fail")

        if self.debug:
            print("   =spi_nor_write_status end ret 0x%02x"%ret)

        return ret



    def _spi_nor_reset(self):
        SPI_REG_WR(rl['SSPCS_IND_CS'][1], 0x0001)
        SPI_REG_WR(rl['SSPDR'][1], 0x66)
        SPI_REG_WR(rl['SSPDR'][1], 0x99)
        self._wait_for_idle()
        SPI_REG_WR(rl['SSPCS_IND_CS'][1], 0x0000)
        self._dummy_read(2)


    def _spi_nor_init(self):
        if self.debug:
            print(">>>Initlize SPI NOR Flash")
        # Set data size select to 0111 8-bit data
        SPI_REG_WR(rl['SSPCR0'][1], 0x7)

        #Eable SSP operation
        SPI_REG_WR(rl['SSPCR1'][1], 0x2)

        #cfg clk
        SPI_REG_WR(rl['SSPCPSR'][1], self.clk_div)
        self._spi_nor_reset()
        if self.debug:
            print("===Finish SPI NOR initialization")

    # program  256B data into nor at offset
    # can't program bigger than 256B each time, looks like the buffer in Nor has limimt
    def _nor_write_data_256B(self, offset=0, data=[]):
        print(" >>>>Start program %d B data at 0x%08x..."%(len(data)*4, offset))
        if self.debug and self.verbose:
            print_hex(data)

        for retry in range(self.nor_write_max_retry):
            ret = self._spi_write_enable()
            if ret != 0 :
                print("write enable fail, try again %d"%retry)
                continue

            self._flush_rx_fifo()
            self._spi_nor_write_data_raw(offset, data)
            ret = self._nor_erase_write_polling_compl()
            if ret != 0 :
                continue
            else:
                break
        if self.debug and self.verbose:
            print(" ====End program data, status %d"%ret)
        return ret


    ## Exposed APIs
    def nor_read_data(self, offset=0, size_in_bytes = 4):
        data = []
        if size_in_bytes % 4:
            size = size_in_bytes / 4 + 1
        else:
            size = size_in_bytes / 4
        if self.debug:
            print('>>>Read %d words from offset 0x%08x' %(size, offset))
        if offset & 0x11:
            print("Error: offset has to be 4bytes aligned")

        if self.nor_indirect_rd:
            # indirect read mode
            SPI_REG_WR(rl['SSPCS_IND_CS'][1], 0x1)
            #read 4B cmd
            SPI_REG_WR(rl['SSPDR'][1], ncmd['RD_4B'])

            #push 4 Bytes address
            SPI_REG_WR(rl['SSPDR'][1], ((offset>> 24) & 0xFF))
            SPI_REG_WR(rl['SSPDR'][1], ((offset >> 16) & 0xFF))
            SPI_REG_WR(rl['SSPDR'][1], ((offset>> 8) & 0xFF))
            SPI_REG_WR(rl['SSPDR'][1], (offset & 0xFF))
            self._wait_idle()
            self._dummy_read(5)
 
            for i in range(size): 
                rdata = []
                #write data, TODO looks strange here, why write 0 to DR
                SPI_REG_WR(rl['SSPDR'][1], 0x0)
                SPI_REG_WR(rl['SSPDR'][1], 0x0)
                SPI_REG_WR(rl['SSPDR'][1], 0x0)
                SPI_REG_WR(rl['SSPDR'][1], 0x0)
                self._wait_for_idle()

                # Read 4 bytes from Reg
                for j in range(4):
                    val = SPI_REG_RD(rl['SSPDR'][1])
                    rdata.append(val)

                #construct to a word
                tmp_data = (rdata[3] << 24) | (rdata[2] << 16) | (rdata[1] << 8) | rdata[0]

                data.append(tmp_data)
                offset += 4
            SPI_REG_WR(rl['SSPCS_IND_CS'][1], 0x0)
        else :
             # direct read mode
            for i in range(int(size)):
                val = SPI_DIRECT_RD(offset)
                data.append(val)
                offset += 4
        if self.debug:
            print("====Nor ReadBack Data:")
            print_hex(data)

        return data    

    # erase 4K subsector
    def nor_erase_subsector(self, start_addr=0):
        ret = 0
        if self.debug:
            print(">>>Start erase 4k subsector at 0x%08x"%start_addr)

        for retry in range(self.nor_erase_max_retry):
            ret = self._spi_write_enable()
            if ret != 0 :
                continue
            self._flush_rx_fifo()

            self._spi_nor_erase_raw(start_addr, 1)
            ret = self._nor_erase_write_polling_compl()
            if ret != 0 :
                continue
            else:
                break
        if self.debug:
            print("===Finsh 4k subsector erase,  retry %d status %d"%(retry, ret))
        return ret

     # erase 4K subsector
    def nor_erase_sector(self, start_addr=0):
        ret = 0
        if self.debug:
            print("====Start erase 64k sector at 0x%08x"%start_addr)

        for retry in range(self.nor_erase_max_retry):
            ret = self._spi_write_enable()
            if ret != 0 :
                continue
            self._flush_rx_fifo()

            self._spi_nor_erase_raw(start_addr)
            ret = self._nor_erase_write_polling_compl()
            if ret != 0 :
                continue
            else:
                break
        if self.debug:
            print("====End erase 64K sector, status %d"%ret)
        return ret
            

    # data is U32 list array
    def nor_write_data(self, offset=0, data=[]):
        if self.debug:
            print(">>>Program %d B data at 0x%08x"%(len(data)*4, offset))
        if self.debug and self.verbose:
            print_hex(data)

        data_256B = split_list_by_n(data, 64)
        for i in data_256B:
            self._nor_write_data_256B(offset, i)
            offset += 256

        if self.debug:
            print("===Program data finished")


    def nor_micron_update_protect_area(self, area):
        status = self._spi_nor_read_status()
        status = (status & ~gMicronPtArea['PT_MASK']) | gMicronPtArea[_get_pt_area(area)]
        self._spi_nor_write_status(status)
        return self._spi_nor_check_status(gMicronPtArea['PT_MASK'], status)

    def nor_update_protect_area(self, area):
        status = self._spi_nor_read_status()
        status = (status & ~gMXICPtArea['PT_MASK']) | gMXICPtArea[_get_pt_area(area)]

        cfg = self._spi_nor_read_cfg_reg()
        if (cfg & MXIC_B_SELECT) :
            ret = self._spi_nor_write_status(status)
        else :
            cfg = cfg | MXIC_B_SELECT
            ret = self._spi_nor_write_status_ex(status, cfg)

        return ret


    def nor_read_id(self):
        #TODO read id might fail during data in fifo, need debug
        self._flush_rx_fifo()
        SPI_REG_WR(rl['SSPCS_IND_CS'][1], 0x0001)
        SPI_REG_WR(rl['SSPDR'][1], ncmd['RD_DID'])
        self._wait_for_idle()
        self._dummy_read(1)

        SPI_REG_WR(rl['SSPDR'][1], 0x0)
        self._wait_for_idle()
        mid = SPI_REG_RD(rl['SSPDR'][1])
        SPI_REG_WR(rl['SSPCS_IND_CS'][1], 0x0000)

        print("manufacturer id: 0x%02x"%mid)


    def nor_program_img(self, offset=0, filename=""):
        print("update BL2 img from file %s"%filename)
        # program bl1/bl2/bl3_golen img to nor

        #load file to list, each element is 4B
        #ref:http://cn.voidcc.com/question/p-cgzoaijl-bex.html
        #  text=np.fromfile(filename, dtype='<i4')
        text = []
        with open(filename, 'rb') as fileobj:
            for chunk in iter(lambda: fileobj.read(4), ''):
                if (len(chunk) == 4):
                    text.append(struct.unpack('<I', chunk)[0])

        self.nor_update_protect_area(0)
        #split text to 4K bytes each for each subsector
        data = split_list_by_n(text, 1024)
        for i in data:
            self.nor_erase_subsector(offset)
            self.nor_write_data(offset, i)
            offset += 4096
        self.nor_update_protect_area(2)

    def nor_update_boot_opt(self, val=0):
        #update nor boot option
        offset = (MAX_NR_SECTORS -1 ) * (64 *1024)
        self.nor_erase_subsector(offset)
        data = []
        data.append(val)
        self.nor_write_data(offset, data)
        data = self.nor_read_data(offset)
        print("Update boot_opt %d to Nor."%data[0])
        return data[0]


    def nor_ncl2(self):
        self.nor_update_protect_area(0)
        self.nor_erase_subsector(BL2_0_OFFSET)
        self.nor_erase_subsector(BL2_1_OFFSET)
        self.nor_update_protect_area(2)
        print("BL2 img erased.")

    def nor_ncl3(self):
        self.nor_update_protect_area(1)
        self.nor_erase_subsector(BL3_OFFSET)
        self.nor_update_protect_area(2)
        print("BL3 img erased.")


################################################################################
if __name__ == '__main__':
    print("Build Pass")
    #  print rl['SSPCR0'][1]
    nor = XSpi_nor();

    nor.nor_update_boot_opt(0)
    #  addr=0x100000
    #  nor.nor_erase_subsector(addr)
    #  data= [0x12, 0x1234, 0x123456, 0x12345678]
    #  nor.nor_write_data(addr, data)
    #  #Read start from 1M offset
    #  data = nor.nor_read_data(addr, 32)
