#!/usr/bin/env python

#Register Name,Register Description,Register Address,Register Width,
#Register Access,Register Reset Value,Register Constraints,Register Custom Type,
#Field Name,Field Description,Field Offset,Field Width,Field Access,
#Field Reset Value,Field is Covered,Field is Reserved,Field is Volatile,
#Field Constraints

import xml.etree.ElementTree as ET
import re
import datetime

_TAG='{http://www.accellera.org/XMLSchema/IPXACT/1685-2014}'

full_regs_list = []

def xparser(xml_name, base_addr):
    _base_addr = int(base_addr, 16)
    tree = ET.parse(xml_name)
    root = tree.getroot()
    
    regs_list = []

    # memoryMaps=root.find('{http://www.accellera.org/XMLSchema/IPXACT/1685-2014}memoryMaps')
    # memoryMap=memoryMaps.find('{http://www.accellera.org/XMLSchema/IPXACT/1685-2014}memoryMap')

    print("#############################################################")
    print("#\t\t%s" % (xml_name))
    print("#############################################################")

    for register in root.iter(_TAG+'register'):
        my_reg = []

        dim = register.find(_TAG+'dim')
        if dim != None:  dim = dim.text.strip()                              
        else: dim = '1'

        # 0 Name
        my_reg.append(register.find(_TAG+'name').text.strip())
        # 1 Description
        my_reg.append(register.find(_TAG+'description').text.strip())
        # 2 Address
        my_reg.append(register.find(_TAG+'addressOffset').text.strip())  
        # 3 Size
        my_reg.append(register.find(_TAG+'size').text.strip())           
        # 4 Access
        my_reg.append(register.find(_TAG+'access').text.strip(),)         
        # 5 Dim
        my_reg.append(dim)
        # 6 Fields
        my_reg.append([])
        # 7 decode flag
        my_reg.append(1)

        if my_reg[0] == 'cpu_pcie_cplmem' or my_reg[0] == 'cpu_pcie_ptlpmem' :
            my_reg[3] = '256'
            my_reg[5] = '4'
            my_reg[7] = 0 # just dumping hex
        elif my_reg[0] == 'nvme_cmd_mem':
            my_reg[3] = '512'
            my_reg[5] = '256'
            my_reg[7] = 0 # just dumping hex
        elif my_reg[0] == 'flash_wdma_mem' \
          or my_reg[0] == 'flash_rdma_mem' :
            my_reg[3] = '256'
            my_reg[5] = '256'
            my_reg[7] = 0 # just dumping hex
        elif my_reg[0] == 'nvme_wrses_mem'  \
          or my_reg[0] == 'pcie_mailbox'  \
          or my_reg[0] == 'pcie_cap_map' :
            my_reg[7] = 0 # just dumping hex
        # elif dim != '1':
        #     lines = my_reg[1].split('\n')
        #     m = re.search('{(.+?)}', lines[2])
        #     # print m.group(1)
        #     if m:
        #         f = m.group(1).split(',')
        #         for item in f:
        #             my_field = ()
        #             item = item.strip()
        #             _m = re.search('(.+?)\[(.+?)]', item)
        #             if _m:
        #                 my_field += (_m.group(1), _m.group(1), )

        #                 _bits = _m.group(2).split(':')
        #                 if len(_bits) == 1 :
        #                     my_field += (_bits[0], '1', '0x0')
        #                 else :
        #                     my_field += (_bits[1], str(int(_bits[0])-int(_bits[1])+1), '0x0')

        #             else :
        #                 my_field += (item, item, '0', '1', '0x0' )

        #             my_reg[6].append(my_field)
        #         # print my_reg[6]
        else :

            for field in register.iter(_TAG+'field'):
                my_field = ()
                my_field += (field.find(_TAG+'name').text.strip(),)            #0
                my_field += (field.find(_TAG+'description').text.strip(),)     #1
                my_field += (field.find(_TAG+'bitOffset').text.strip(),)       #2
                my_field += (field.find(_TAG+'bitWidth').text.strip(),)        #3

                resets = field.find(_TAG+'resets')
                if resets != None:
                    my_field += (resets[0][0].text.strip(),)                   #4  
                else:
                    my_field += ('0x0',)

                ### Special handling for hba[63:2], cq_base_addr[63:2], lower 2 bits are zero
                if ( my_field[0] == 'hba' ) \
                 or( my_field[0] == 'cq_base_addr') \
                 or( my_field[0] == 'sq_base_addr') :
                    my_field += ('2',)

                my_reg[6].append(my_field)

        if my_reg[0] == 'flash_opst_mem' :
            my_reg[3] = '256'
            my_reg[5] = '256'
        elif my_reg[0] == 'nvme_sqst_mem' \
          or my_reg[0] == 'nvme_cqst_mem' \
          or my_reg[0] == 'nvme_cmdst_mem' :
            my_reg[3] = '128'
            my_reg[5] = '256'

    ### 1. Handle Atomic register array, update its width (and dim)


    ### 2. Setup register array, per entry based, 
    ### 3. Regenerate fields, bease on in-descirption field definition (if any)

        regs_list.append(my_reg)
        full_regs_list.append(my_reg)

    # find register array

    ## reg_list exmaple
    print("\n# \n")
    print("# reg_obj = \n")
    print("#       (name, (address, address_end), description, \n")
    print("#       [ (field, bit, bit_end,description)....],  \n")
    print("#       width, dimension )")
    print("#\n")

    ### decoding registers
    for reg in regs_list:
        reg.append(_base_addr)
        address = int(reg[2],16)+int(_base_addr)
        dim = int(reg[5])
        size = int(int(reg[3])/8)  # in byte
        address_end = int(address + size*dim);


        print('reg_%s = ( ' % reg[0])
        print('    %s,' % reg[0].__repr__())
        print('    (0x%08x, 0x%08x),' % (address, address_end))
        print('    %s,' % reg[1].__repr__())
        print('    [ ')

        for field in reg[6]:
            offset = int(field[2])
            width = int(field[3])
            if ( len(field) == 6) : 
                print('       (%s, %d, %d, %s, %s),'  \
                    % (field[0].__repr__(), offset, offset+width-1, field[1].__repr__(), field[5] ))
            else:
                print('       (%s, %d, %d, %s),' % (field[0].__repr__(), offset, offset+width-1, field[1].__repr__() ))

        print('    ], ')
        print('    0x%x,' % size)
        print('    0x%x,' % dim)
        print('    %d,' % reg[7])
        print('    )')

################################################################################
if __name__ == '__main__':
    print("#")
    print("#  Auto generated by parser_xml.py on ", datetime.date.today().ctime())
    print("# ")
    print()

    xparser('i2c_csr.xml',       '0x00000000')
    xparser('gpio_csr.xml',      '0x00000000')
    xparser('uart_csr.xml',      '0x00000000')
    xparser('sfl_csr.xml',       '0x30100000')
    xparser('dfd_csr_auto.xml',  '0x8009c000')
    xparser('ace_csr_auto.xml',  '0x83d10000')
    xparser('wdt_csr.xml',       '0x22220000')
    xparser('dcs_csr_auto.xml',  '0x83470000')
    xparser('feace_csr_auto.xml','0x83460000')
    xparser('fce_csr_auto.xml',  '0x83410000')
    xparser('bm_csr_auto.xml',   '0x83430000')
    xparser('ccs_csr_auto.xml',  '0x83440000')
    xparser('sdsw_csr_auto.xml', '0x83450000')
    xparser('chip_csr_auto.xml', '0x83400000')
    xparser('pss_csr_auto.xml',  '0x83500000')
    xparser('qspi_csr_auto.xml', '0x83010000')



    ## prolog,
    print("# \n# key:regname, (obj, start,stop, size, dim) \n#")
    print("reg_list = { ")
    for reg in full_regs_list:
        address = int(reg[2],16)+int(reg[8])
        dim = int(reg[5])
        size = int(int(reg[3])/8)  # in byte
        address_end = address + size*dim;

        print('    %-26s: (%-26s, 0x%08x, 0x%08x, %s, %d),' % \
            ( reg[0].__repr__(), 'reg_'+reg[0], address, address_end, reg[3], dim ))

    ## epilog
    print('    } #reg_list')  

    print() 
