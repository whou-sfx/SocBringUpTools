#!/usr/bin/env python

# usage: ./parse_vmlog.py
# log file name is 'vmlog.file'
# parse vmware project register dump log, it looks for 'Start dumping device'
# as starting point, and 'End dumping device' as end point. The register vals
# between the two markers are processed. the script supports multiple dump.
# 

import re
import datetime
import binascii

if __name__ == '__main__':
    print "#"
    print "#  Auto generated by parser_vmlog.py on ", datetime.date.today().ctime()
    print "# "
    print

    f2 = open('./vmlog.file', 'rb')
    
    strout = ''
    header_found = None
    footer_found = None
    dump_id = 0

    for logline in f2:
        if (header_found==None):
            header_found = re.search( r'Start dumping sfxdriver registers', logline, re.M|re.I)
            if(header_found): 
                f3_name = 'reg_dump_' + str(dump_id) + '.csv'
                f1 = open('./parser_regs.list', 'rU')
                f3 = open(f3_name, 'w')
                f3.write('register name, address, index, value\n')
        else:
            footer_found = re.search( r'End of sfxdriver registers', logline, re.M|re.I)
            if(footer_found==None): # register lines
                logline = re.sub(r'.*: SFXPK: \[.*CCS_SYS\]', "", logline).split()
                for item in logline:
                    f3.write(f1.readline().strip() + ' 0x' + item)
                    f3.write('\n')
            else:
                f1.close()
                f3.close()
                header_found = None
                footer_found = None
                print 'Parse register ' + str(dump_id) + ' is complete.'
                dump_id = dump_id + 1
