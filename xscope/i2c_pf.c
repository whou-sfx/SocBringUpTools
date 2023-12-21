/*
 * pcimem.c: Simple program to read/write from/to a pci device from userspace.
 *
 *  Copyright (C) 2010, Bill Farrow (bfarrow@beyondelectronics.us)
 *
 *  Based on the devmem2.c code
 *  Copyright (C) 2000, Jan-Derk Bakker (J.D.Bakker@its.tudelft.nl)
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
 *
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <unistd.h>
#include <string.h>
#include <errno.h>
#include <signal.h>
#include <fcntl.h>
#include <ctype.h>
#include <termios.h>
#include <sys/types.h>
#include <sys/mman.h>

#define PRINT_ERROR                                                                                           \
    do {                                                                                                      \
        fprintf(stderr, "Error at line %d, file %s (%d) [%s]\n", __LINE__, __FILE__, errno, strerror(errno)); \
        exit(1);                                                                                              \
    } while (0)

void write_reg(void *map_base, uint32_t addr, uint32_t val)
{
    void *virt_addr = map_base;
    *((uint32_t *)virt_addr) = addr;

    /////////////////////
    virt_addr = map_base + 4;
    *((uint32_t *)virt_addr) = val;
}

uint32_t read_reg(void *map_base, uint32_t addr)
{
    void *virt_addr = map_base;
    *((uint32_t *)virt_addr) = addr;

    /////////////////////
    virt_addr = map_base + 8;

    return *((uint32_t *)virt_addr);
}
//
int main(int argc, char **argv)
{
    int fd;
    void *map_base, *virt_addr;
    uint64_t read_result, writeval, prev_read_result = 0;
    char *filename;
    off_t target, target_base;
    int verbose = 0;
    int read_result_dupped = 0;
    int i;
    int map_size = 4096UL;

    if (argc < 2) {
        // i2c_pf /sys/bus/pci/devices/0001\:00\:07.0/resource0
        fprintf(stderr,
                "\nUsage:\t%s { sysfile }\n"
                "\tsys file: sysfs file for the pci resource to act on\n",
                argv[0]);
        exit(1);
    }

    filename = argv[1];

    if ((fd = open(filename, O_RDWR | O_SYNC)) == -1) PRINT_ERROR;

    map_base = mmap(0, map_size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0x8000);
    if (map_base == (void *)-1) PRINT_ERROR;

    // power loss 1st
    write_reg(map_base, 0x22200034, 0x00000066);
    write_reg(map_base, 0x2220002c, 0x00000001);
    write_reg(map_base, 0x22200030, 0x00000002);
    write_reg(map_base, 0x2220003c, 0x00000020);

    write_reg(map_base, 0x2220003c, 0x00000089);
    write_reg(map_base, 0x22200028, 0x00000009);

    uint32_t val = read_reg(map_base, 0x22200028);
    while (val & (1 << 3)) {
        val = read_reg(map_base, 0x22200028);
    }

    // power loss 2nd
    write_reg(map_base, 0x22200034, 0x00000066);
    write_reg(map_base, 0x2220002c, 0x00000001);
    write_reg(map_base, 0x22200030, 0x00000002);
    write_reg(map_base, 0x2220003c, 0x00000020);

    write_reg(map_base, 0x2220003c, 0x00000089);
    write_reg(map_base, 0x22200028, 0x00000009);

    val = read_reg(map_base, 0x22200028);
    while (val & (1 << 3)) {
        val = read_reg(map_base, 0x22200028);
    }

    // power on 1st
    write_reg(map_base, 0x22200034, 0x00000066);
    write_reg(map_base, 0x2220002c, 0x00000001);
    write_reg(map_base, 0x22200030, 0x00000002);
    write_reg(map_base, 0x2220003c, 0x00000020);

    write_reg(map_base, 0x2220003c, 0x00000088);
    write_reg(map_base, 0x22200028, 0x00000009);

    val = read_reg(map_base, 0x22200028);
    while (val & (1 << 3)) {
        val = read_reg(map_base, 0x22200028);
    }

    // power on 2nd
    write_reg(map_base, 0x22200034, 0x00000066);
    write_reg(map_base, 0x2220002c, 0x00000001);
    write_reg(map_base, 0x22200030, 0x00000002);
    write_reg(map_base, 0x2220003c, 0x00000020);

    write_reg(map_base, 0x2220003c, 0x00000088);
    write_reg(map_base, 0x22200028, 0x00000009);

    val = read_reg(map_base, 0x22200028);
    while (val & (1 << 3)) {
        val = read_reg(map_base, 0x22200028);
    }

    if (munmap(map_base, map_size) == -1) PRINT_ERROR;
    close(fd);
    return 0;
}
