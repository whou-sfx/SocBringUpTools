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

######## MACRON DEFINES###########
MAX_NR_SECTORS = 256    # for 16MB flash
BL2_0_OFFSET = (64 * 1024)
BL2_1_OFFSET = (512 * 1024)
BL3_OFFSET = (1024 * 1024)

# TODO polling time chage ???
SPI_NOR_POLLING_LOOP  =   5000
SPI_NOR_POLLING_US    =   1000
SPI_NOR_PGM_POLLING_LOOP = 10

QSPI_DIRECT_READ_BASE   =    0x20000000

MICRON_ID = 0x20
MXIC_ID = 0xC2

WRITE_ONLY = 1
READ_ONLY = 2
WRITE_READ = 3
READ_WRITE = 4
WRITE_TOKEN_READ = 5
READ_TOKEN_WRITE = 6
NONE_DATA = 7
DUMMY_WRITE = 8
DUMMY_READ = 9

NOR_STA_WBUSY			=	(1 << 0)
NOR_STA_WEN_LATCHED		=	(1 << 1)
######## END OF MACRON DEFINES###########

def print_hex(data=[]):
    l = [hex(int(i)) for i in data]
    print((" ".join(l)))

def split_list_by_n(data, n):
    for i in range(0, len(data), n):
        yield data[i: i + n]

def MDELAY(delay_in_ms):
    ms = delay_in_ms / 1000
    time.sleep(ms)  # TODO need replace by the fun that can delay ms ???

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
    addr = QSPI_DIRECT_READ_BASE + offset
    if reg_debug:
        print('DirectRead 0x%08x' %addr)
    if fake == 0 :
        val = xhal.read_hex(addr);
    return val

##########End of Hook functions

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


def reg_spi_timing_wr(sclk_div = 0x0, t_cshigh= 0x0, t_cs2sclk = 0x0):
    val = (sclk_div & 0xff) | ((t_cshigh & 0xff) << 8) | ((t_cs2sclk & 0xff) << 16)
    SPI_REG_WR(rl['spi_timing'][1], val)

def reg_spi_ctrl_wr(spi_rst = 0x0, rxfifo_rst=0x0, txfifo_rst=0x0, rx_dma_en=0x0, tx_dma_en=0x0, p2a_fifo_rst=0x0, \
                    a2p_fifo_rst=0x0, rx_thres=0x0, tx_thres=0x0, rxfifo_auto_clr=0x0, spi_debug_clk_en=0x0, spi_debug_en=0x0):
    val = (spi_rst & 0x1) | ((rxfifo_rst & 0x1) << 1) | ((txfifo_rst & 0x1) << 2) | ((rx_dma_en & 0x1) << 3) | ((tx_dma_en & 0x1) << 4) \
        | ((p2a_fifo_rst & 0x1) << 5) | ((a2p_fifo_rst & 0x1) << 6) | ((rx_thres & 0x7f) << 8) | ((tx_thres & 0x7f) << 16) \
         | ((rxfifo_auto_clr & 0x1) << 27) | ((spi_debug_clk_en & 0x1) << 28) | ((spi_debug_en & 0x1) << 31)
    SPI_REG_WR(rl['spi_ctrl'][1], val) 

def reg_spi_format_wr(cpha = 0x0, cpol=0x0, lsb=0x0, mosibidir=0x0, datamerge=0x0, \
                     addrlen=0x0, fifo_ctrl_sel=0x0, axi_wr_mode=0x0, axi_rd_mode=0x0):
    val = (cpha & 0x1) | ((cpol & 0x1) << 1) | ((lsb & 0x1) << 2) | ((mosibidir & 0x1) << 3) | ((datamerge & 0x1) << 4) \
        | ((addrlen & 0x3) << 8) | ((fifo_ctrl_sel & 0x1) << 12) | ((axi_wr_mode & 0x1) << 16) | ((axi_rd_mode & 0x1) << 20)
    SPI_REG_WR(rl['spi_format'][1], val)     

def reg_spi_trans_ctrl_wr(dummy_num = 0x0, token_num=0x0, dummy_val_en=0x0, dummy_en=0x0, data_fmt=0x0, \
                     trans_mode=0x0, addr_fmt=0x0, addr_en=0x0, cmd_en=0x0):
    val = (dummy_num & 0xff) | ((token_num & 0x7) << 8) | ((dummy_val_en & 0x1) << 11) | ((dummy_en & 0x1) << 21) | ((data_fmt & 0x3) << 22) \
        | ((trans_mode & 0xf) << 24) | ((addr_fmt & 0x1) << 28) | ((addr_en & 0x1) << 29) | ((cmd_en & 0x1) << 30)
    SPI_REG_WR(rl['spi_trans_ctrl'][1], val) 

def reg_spi_trans_num_wr(rd_trans_num=0x0, wr_trans_num=0x0):
    val = (rd_trans_num & 0xfff) | ((wr_trans_num & 0xfff) << 16)
    SPI_REG_WR(rl['spi_trans_num'][1], val)
    


def trans_ctrl_set(addr_en, trans_mode):
    reg_spi_trans_ctrl_wr(cmd_en = 1, addr_en = addr_en, trans_mode = trans_mode)

def qspi_trans_ctrl_read_reg():
    trans_ctrl_set(0, READ_ONLY)

def qspi_trans_ctrl_write_reg():
    trans_ctrl_set(0, WRITE_ONLY)

def qspi_trans_ctrl_write_no_data():
    trans_ctrl_set(1, NONE_DATA)

def qspi_trans_ctrl_reset():
    trans_ctrl_set(0, NONE_DATA)

def qspi_trans_ctrl_write():
    trans_ctrl_set(1, WRITE_ONLY)

def qspi_trans_ctrl_read():
    trans_ctrl_set(1, READ_ONLY)

def qspi_trans_ctrl_read_quad():
    reg_spi_trans_ctrl_wr(cmd_en = 1, addr_en = 1, trans_mode = DUMMY_READ, data_fmt = 2, dummy_en = 1, dummy_num = 7)

def qspi_trans_ctrl_write_quad():
    reg_spi_trans_ctrl_wr(cmd_en = 1, addr_en = 1, trans_mode = WRITE_ONLY, data_fmt = 2)

def qspi_switch_axi_read(enable):
    reg_spi_format_wr(cpha = 1, cpol = 1, datamerge = 1, addrlen = 3, axi_rd_mode = enable, fifo_ctrl_sel = enable)        


#SPI NOR ACCESS Class
class XSpi_nor:
    def __init__(self, haps=0, debug=0, verbo=0, dev="", slot=""):
        # debug output
        self.debug = debug
        self.verbose = verbo
        self.haps = haps
        self.nor_indirect_rd = 0    # only support direct mode now 
        #self.nor_erase_max_retry = 3
        #self.nor_write_max_retry = 3
        
        # Reg access Interface
        self.xhal = XHal(dev=dev, slot=slot)

        #print('haps %d debug %d, verbo %d' % (haps,debug,verbo))
        # init qspi
        self._qspi_nor_init()

    def _wait_for_idle(self):
        if self.debug and self.verbose:
            print("   >wait_for_idle")

        busy = 0
        loop = 0
        MAX_TRY_TIME = 1000
        while loop < MAX_TRY_TIME: 
            busy = SPI_REG_RD(rl['spi_sts'][1]) & 0x1
            #Delay is necessary to make indirect_reg access finish
            if busy == 0: # wait for spi_busy to be cleared
                break
            loop += 1
            if self.haps: # TODO may need to chose an appropriate delay for haps and asic
                MDELAY(2)
        else:
            print('   Warning: _wait_for_idle timeout')

        if self.debug and self.verbose:
            print("   =wait_for_idle end")
        return busy
            
    def _flush_tx_fifo(self): # TODO may loop forever
        if self.debug and self.verbose:
            print("   >_flush_tx_fifo")

        self._wait_for_idle()
        reg_spi_ctrl_wr(txfifo_rst = 1, p2a_fifo_rst = 1, rx_thres = 0x32)

        status = SPI_REG_RD(rl['spi_ctrl'][1]) 
        while status & 0x24: # 0x24 = mask of (txfifo_rst | p2a_fifo_rst), wait for all field to be cleared
            status = SPI_REG_RD(rl['spi_ctrl'][1])
        
        if self.debug and self.verbose:
            print("   =_flush_tx_fifo end")

    def _qspi_nor_write_data_raw(self, start_addr = 0, data = [], nbytes = 0, quad = 0):
        if self.debug and self.verbose:
            print("  >>qspi_nor_write_data_raw start")

        self._wait_for_idle()
        self._qspi_write_enable()
        self._wait_for_idle()

        if quad:
            qspi_trans_ctrl_write_quad()
        else:
            qspi_trans_ctrl_write()

        self._flush_tx_fifo()
        SPI_REG_WR(rl['spi_addr'][1], start_addr)
        reg_spi_trans_num_wr(0, nbytes - 1)

        self._wait_for_idle()
        cmd = ncmd['EXT_QUAD_I_FAST_PROG_4B'] if quad else ncmd['PAGE_PROG_4B']
        SPI_REG_WR(rl['spi_cmd'][1], cmd)
        
        # push data
        for wdata in data:
            SPI_REG_WR(rl['spi_data'][1], wdata)

        self._wait_for_idle()

        if self.debug  and self.verbose:
            print("  ==spi_nor_write_data_raw end")
        
        return 0


    def _nor_erase_write_polling_compl(self):
        ret = 0
        if self.debug and self.verbose:
            print("  >nor_erase_write_polling_compl start")

        loop = 0
        while loop < SPI_NOR_PGM_POLLING_LOOP: 
            status = self._qspi_nor_read_status()
            if (status & NOR_STA_WBUSY) == 0:
                break
            loop += 1
        else:
            print('write or erase fail, wait for ready timeout')
            ret = -1
        
        if self.debug and self.verbose:
            print("   =nor_erase_write_polling_compl end, loop %d"%loop)
        return ret

    def _qspi_nor_check_status(self, mask, val):
        if self.debug:
            print("   >spi_nor_check_status start: mask 0x%02x val 0x%02x"%(mask, val))

        loop = 0
        status = self._qspi_nor_read_status()
        while (status & mask) != (val & mask):
            status = self._qspi_nor_read_status()
            MDELAY(1)
            loop += 1
            if loop % SPI_NOR_PGM_POLLING_LOOP == 0:
                print('Warning: read check status timeout, expect 0x%02x, current 0x%02x' %((val & mask), (status & mask)))
                return -1
        return 0

    def _qspi_nor_reset(self):
        if self.haps :
            sclk_div = 0x4
            t_cshigh = 0x4
            qspi_delay = 0x4
        else : # asic may need to change this parameter
            sclk_div  =0x4
            t_cshigh = 0x4
            qspi_delay = 0x4

        reg_spi_timing_wr(sclk_div, t_cshigh, qspi_delay)
        SPI_REG_WR(rl['spi_rclk_dly'][1], qspi_delay)

        reg_spi_ctrl_wr(spi_rst=1, rxfifo_rst=1, txfifo_rst=1, p2a_fifo_rst=1, a2p_fifo_rst=1, rx_thres=0x32)
        status = SPI_REG_RD(rl['spi_ctrl'][1]) 
        loop = 0
        while status & 0x25: # 0x25 = mask of (spi_rst | txfifo_rst | p2a_fifo_rst), wait for all field been cleared
            status = SPI_REG_RD(rl['spi_ctrl'][1])
            loop += 1
            if loop % 10000 == 0:
                break
        if (status & 0x25):
            print('Warning: wait spi_ctrl status timeout, ' + 'status 0x%02x'%status)

        self._wait_for_idle()

    def _qspi_nor_init(self):
        if self.debug:
            print(">>>Initlize QSPI NOR Flash")
        self._qspi_nor_reset()
        vender_id = self.nor_read_id()
        if MXIC_ID == vender_id:
            status = self._qspi_nor_read_status()
            if ((status & (1<<6)) == 0):    # set MXIC_STA.qe
                status |= (1<<6)
                self._qspi_nor_write_status(status)
        if self.debug:
            print("===Finish QSPI NOR initialization")

    # program  256B data into nor at offset
    # can't program bigger than 256B each time, looks like the buffer in Nor has limimt
    def _nor_write_data_256B(self, offset=0, data=[]):
        print(" >>>>Start program %d B data at 0x%08x..."%(len(data)*4, offset))
        if self.debug and self.verbose:
            print_hex(data)

        self._qspi_nor_write_data_raw(offset, data, len(data)*4, 0)
        ret = self._nor_erase_write_polling_compl()
 
        if self.debug and self.verbose:
            print(" ====End program data, ret %d"%ret)
        return ret

    def _qspi_nor_erase_raw(self, start_addr, sector_enabled):
        self._qspi_write_enable()
        self._wait_for_idle()
        qspi_trans_ctrl_write_no_data()
        SPI_REG_WR(rl['spi_addr'][1], start_addr)
        reg_spi_trans_num_wr(0, 0)
        self._wait_for_idle()

        cmd = ncmd['SECT_ERASE_4B'] if sector_enabled else ncmd['SUBSECT_ERASE_4KB_4B']
        SPI_REG_WR(rl['spi_cmd'][1], cmd)
        self._wait_for_idle()

        return 0

    def _nor_micron_update_protect_area(self, area):
        status = self._qspi_nor_read_status()
        status = (status & ~gMicronPtArea['PT_MASK']) | gMicronPtArea[_get_pt_area(area)]
        self._qspi_nor_write_status(status)
        return self._qspi_nor_check_status(gMicronPtArea['PT_MASK'], status)

    def _nor_mxic_update_protect_area(self, area):
        status = self._qspi_nor_read_status()
        status = (status & ~gMXICPtArea['PT_MASK']) | gMXICPtArea[_get_pt_area(area)]

        cfg = self._qspi_nor_read_cfg_reg()
        if (cfg & MXIC_B_SELECT) :
            ret = self._qspi_nor_write_status(status)
        else :
            cfg = cfg | MXIC_B_SELECT
            ret = self._qspi_nor_write_status_ex(status, cfg)

        return ret

    def _qspi_write_enable(self):
        if self.debug and self.verbose:
            print("   >_qspi_write_enable")
        qspi_switch_axi_read(0)
        self._wait_for_idle()
        qspi_trans_ctrl_reset()
        SPI_REG_WR(rl['spi_cmd'][1], ncmd['WR_EN'])
        self._wait_for_idle()

        loop = 0
        while loop < SPI_NOR_POLLING_LOOP: 
            status = self._qspi_nor_read_status()
            if (status & NOR_STA_WEN_LATCHED):
                break
            loop += 1
        else:
            print('spi write enable failed! ' + 'status 0x%02x'%(status&0xff))
            return -1
        if self.debug and self.verbose:
            print("   =_qspi_write_enable end")

        return 0

    def _qspi_nor_read_register(self, opcode, len=4):
        self._wait_for_idle()
        qspi_switch_axi_read(0)
        qspi_trans_ctrl_read_reg()

        reg_spi_trans_num_wr(wr_trans_num = 0, rd_trans_num = len - 1)

        self._wait_for_idle()
        SPI_REG_WR(rl['spi_cmd'][1], opcode)

        self._wait_for_idle()
        data = SPI_REG_RD(rl['spi_data'][1])
        
        return data
    def _qspi_nor_read_status(self):
        status = self._qspi_nor_read_register(opcode = ncmd['RD_STA_REG'])
        return status

    def _qspi_nor_read_cfg_reg(self):
        flag = self._qspi_nor_read_register(opcode = ncmd['RD_CFG_REG'])
        return flag    
    
    def _qspi_nor_write_status(self, status):
        self._wait_for_idle()
        self._qspi_write_enable()
        self._wait_for_idle()
        qspi_trans_ctrl_write_reg()

        reg_spi_trans_num_wr(rd_trans_num=0x0, wr_trans_num=0xff)

        self._wait_for_idle()
        SPI_REG_WR(rl['spi_cmd'][1], ncmd['WR_STA_REG'])
        SPI_REG_WR(rl['spi_data'][1], status)
        self._wait_for_idle()

        ret = self._nor_erase_write_polling_compl()
        if ret:
            print('write nor status register fail')
        return ret
    
    def _testqspi_nor_write_status(self, status):
        
        #self._wait_for_idle()
        qspi_trans_ctrl_write_reg()#from here

        reg_spi_trans_num_wr(rd_trans_num=0x0, wr_trans_num=0xff)

        self._wait_for_idle()
        print('---------------------------')
        SPI_REG_WR(rl['spi_cmd'][1], ncmd['WR_STA_REG'])
        #self._wait_for_idle()##
        print('sssssssssssssssss')
        SPI_REG_WR(rl['spi_data'][1], status)
        print('----------------333-----------')
        #return
        self._wait_for_idle() # 0xfffffff here internal
        print('----------------444-----------')

        
    def _qspi_nor_write_status_ex(self, status, cfg):
        self._wait_for_idle()
        self._qspi_write_enable()
        self._wait_for_idle()
        qspi_trans_ctrl_write_reg()

        reg_spi_trans_num_wr(rd_trans_num=0x1, wr_trans_num=0xff)

        self._wait_for_idle()
        SPI_REG_WR(rl['spi_cmd'][1], ncmd['WR_STA_REG'])
        SPI_REG_WR(rl['spi_data'][1], status | ((cfg & 0xf) << 8))
        self._wait_for_idle()

        ret = self._nor_erase_write_polling_compl()
        if ret:
            print('write nor status ex register fail')
        return ret

#-----------------------------------------------------------------------------#    
    ## Exposed APIs
    def nor_read_data(self, offset=0, size_in_bytes = 4):
        data = []
        if size_in_bytes % 4:
            size = size_in_bytes / 4 + 1
        else:
            size = size_in_bytes / 4
        if self.debug:
            print('>>>Read %d words from offset 0x%08x' %(size, offset))
        if offset % 4:
            print("Error: offset has to be 4bytes aligned")

        if self.nor_indirect_rd: # TODO support indirect read mode 
            print("don't support indirect mode yet")
        else :
             # direct read mode
            qspi_switch_axi_read(1)
            qspi_trans_ctrl_read_quad()
            SPI_REG_WR(rl['spi_cmd'][1], ncmd['QUAD_O_FAST_RD_4B'])
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

        self._qspi_nor_erase_raw(start_addr, 0)
        ret = self._nor_erase_write_polling_compl()
        """
        # TODO get operate result
        if 0 == ret:
            return qspi_get_operate_result(NOR_ERASE_OPERATION);
        """
        if self.debug:
            print("===Finsh 4k subsector erase, ret %d"%(ret))
        return ret

     # erase 64K subsector
    def nor_erase_sector(self, start_addr=0):
        ret = 0
        if self.debug:
            print("====Start erase 64k sector at 0x%08x"%start_addr)

        self._qspi_nor_erase_raw(start_addr, 1)
        ret = self._nor_erase_write_polling_compl()
        """
        # TODO get operate result
        if 0 == ret:
            return qspi_get_operate_result(NOR_ERASE_OPERATION);
        """

        if self.debug:
            print("====End erase 64K sector, status %d"%ret)
        return ret
            

    # data is U32 list array
    def nor_write_data(self, offset=0, data=[]):
        ret = 0
        errCnt = 0
        if self.debug:
            print(">>>Program %d B data at 0x%08x"%(len(data)*4, offset))
        
        if offset % 256:    # TODO : write offset that don't align to 256 bytes 
            print('err: offset should align to hwPageSize(256 bytes)')
            return -1

        data_256B = split_list_by_n(data, 64)
        for i in data_256B:
            ret = self._nor_write_data_256B(offset, i)
            if ret:
                print('   err: _nor_write_data_256B failed at offset 0x%02x' %offset)
                errCnt += 1
            offset += 256

        if self.debug:
            print("===Program data finished")
        
        if errCnt:
            return -1
        return 0

    
    def nor_update_protect_area(self, area):
        if self.debug:
            print("   >nor_update_protect_area")
        nor_id = self.nor_read_id()
        if MXIC_ID == nor_id:
            self._nor_mxic_update_protect_area(area)
        else:
            self._nor_micron_update_protect_area(area)
        if self.debug:
            print("   =nor_update_protect_area end")

    def nor_read_id(self):
        vendor_id = self._qspi_nor_read_register(opcode = ncmd['RD_DID']) & 0xff
        print("manufacturer id: 0x%02x"%vendor_id)
        return vendor_id


    def nor_program_img(self, offset=0, filename=""):
        if self.debug and self.verbose:
            print("   >nor_program_img")

        print("update img from file %s"%filename)
        # program bl1/bl2/bl3_golen img to nor

        #load file to list, each element is 4B
        #ref:http://cn.voidcc.com/question/p-cgzoaijl-bex.html
        #  text=np.fromfile(filename, dtype='<i4')
        text = []
        with open(filename, 'rb') as fileobj:
            for chunk in iter(lambda: fileobj.read(4), ''):
                if (len(chunk) == 4):
                    text.append(struct.unpack('<I', chunk)[0]) #TODO how to treat big endian and small endian ???
                else: # TODO how to write last chunk and break ???
                    print(chunk)    
                    print("len =", len(chunk)) 
                    #text.append(struct.unpack('<I', chunk)[0])  # struct.error: unpack requires a buffer of 4 bytes
                    break             
        self.nor_update_protect_area(0)
        #split text to 4K bytes each for each subsector
        data = split_list_by_n(text, 1024)
        for i in data:
            self.nor_erase_subsector(offset)
            self.nor_write_data(offset, i)
            offset += 4096
        self.nor_update_protect_area(2)

        if self.debug and self.verbose:
            print("   =nor_program_img end")

    def nor_update_boot_opt(self, val=0):
        #update nor boot option
        # TODO only handle primary boot option now
        offset = (MAX_NR_SECTORS -1 ) * (64 *1024)
        self.nor_erase_subsector(offset)
        data = []
        data.append(val)
        self.nor_write_data(offset, data)
        data = self.nor_read_data(offset)
        print("Update boot_opt %d to Nor."%data[0])
        return data[0]


    def nor_ncl2(self):
        bl2_pri__off = BL2_0_OFFSET
        if self.haps:
            bl2_pri__off = 0
        # only erase first sector of bl2
        self.nor_update_protect_area(0)
        self.nor_erase_subsector(bl2_pri__off)
        self.nor_erase_subsector(BL2_1_OFFSET)
        self.nor_update_protect_area(2)
        print("BL2 img erased.")

    def nor_ncl3(self):
        # only erase first sector of bl3
        self.nor_update_protect_area(1)
        self.nor_erase_subsector(BL3_OFFSET)
        self.nor_update_protect_area(2)
        print("BL3 img erased.")


################################################################################
if __name__ == '__main__':
    print("Build Pass")
    nor = XSpi_nor();

    nor.nor_update_boot_opt(0)
    #  addr=0x100000
    #  nor.nor_erase_subsector(addr)
    #  data= [0x12, 0x1234, 0x123456, 0x12345678]
    #  nor.nor_write_data(addr, data)
    #  #Read start from 1M offset
    #  data = nor.nor_read_data(addr, 32)
