/*
 * ---------------------------------------------------------------------------
 *
 * Portions Copyright (c) 2015-2020, ScaleFlux, Inc.
 *
 * ALL RIGHTS RESERVED. These coded instructions and program statements are
 * copyrighted works and confidential proprietary information of Scaleflux Corp.
 * They may not be modified, copied, reproduced, distributed, or disclosed to
 * third parties in any manner, medium, or form, in whole or in part.
 *
 * ---------------------------------------------------------------------------
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
#include <sys/stat.h>
#include <unistd.h>

#define PRINT_ERROR \
    do { \
        fprintf(stderr, "Error at line %d, file %s (%d) [%s]\n", \
        __LINE__, __FILE__, errno, strerror(errno)); exit(1); \
    } while(0)

int main(int argc, char **argv) {
    int fd;
    void *map_base;
    void *ddr_base;
    void *axinic_offset_low; 
    void *axinic_offset_hi;
    char *filename;
    char *dumpfile;
    off_t target_base = 0;
    int map_size = 4096UL;
    long long int dump_ddr_addr;
    int len;
    int i;
    int j;
    int loop = 0;
    int last_loop = 0;
    int loopsize = 0x10000UL;
    uint32_t swap = 0;
    int issram;

    /* allocate memory for resource0 file */
    if(argc < 6) {
        // dump_ddr /sys/bus/pci/devices/0001\:00\:07.0/resource0 dumpfile dump_ddr_addr length issram
        // argv[0]   [1]                                            [2]         [3]       [4]   [5]
        fprintf(stderr, "\nUsage:\t%s { sysfile } { dumpfile } { dump_ddr_addr } { length }{ issram }\n"
            "\tsys file: sysfs file for the pci resource0 to act on\n"
            "\tdumpfile: dump file for ddr\n"
            "\tdump_ddr_addr: ddr base addr which user wanna dump\n"
            "\tlength: the length about data user wanna dump\n"
            "\tissram: the data if is in sram or not \n"
            "\t\n\n",
            argv[0]);
        exit(1);
    }
    filename = argv[1];
    dumpfile = argv[2];
    dump_ddr_addr = strtoul(argv[3], 0, 0);
    //printf("dump ddr addr :0x%llx\n", dump_ddr_addr);
    len = strtoul(argv[4], 0, 0);
    issram = strtoul(argv[5], 0, 0);

    if((fd = open(filename, O_RDWR | O_SYNC)) == -1) 
        PRINT_ERROR;

    //printf("%s opened.\n", filename);
    //printf("Target offset is 0x%x, page size is %ld\n", (int) target_base, sysconf(_SC_PAGE_SIZE));
    fflush(stdout);

    map_size = 32 * map_size;

    /* Map one page */
    //printf("mmap(%d, %d, 0x%x, 0x%x, %d, 0x%x)\n", 0, map_size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, (int) target_base);

    map_base = mmap(0, map_size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, target_base);
    if(map_base == (void *) -1) 
        PRINT_ERROR;
    
    ddr_base = map_base + 0x10000;
    axinic_offset_low = map_base + 0x8014;
    axinic_offset_hi = map_base + 0x8018;

    /* dump ddr data to file */
    *((uint32_t *)axinic_offset_low) = dump_ddr_addr & 0xFFFFFFFF;
    if(issram)
    {
        *((uint32_t *)axinic_offset_hi) = 0x0;
    }
    else
    {
        *((uint32_t *)axinic_offset_hi) = 0x70;
    }
    //printf("dump ddr addr :0x%x, high :0x%x\n", *((uint32_t *)axinic_offset_low), *((uint32_t *)axinic_offset_hi));
    // round up
    loop = len / loopsize;
    last_loop = len % loopsize;
    FILE *pFile = fopen(dumpfile, "wb+");
    if( pFile == NULL) {
        printf("Open dump File Error \n");
        exit(1);
    }

    printf(">>> Total   loop = %d \n", loop);
    printf(">>> Current loop =");
    fflush(stdout);
    for (i = 0; i < loop; i++) {
        printf(" %d", i);
        fflush(stdout);
        for (j = 0; j < loopsize / 4; j++) {
            swap = *(uint32_t *)(ddr_base + j * 4);
            fwrite(&swap, 4, 1, pFile);
        }
        dump_ddr_addr += 0x10000;
        *((uint32_t *)axinic_offset_low) = dump_ddr_addr & 0xFFFFFFFF;
        if(issram)
        {
            *((uint32_t *)axinic_offset_hi) = 0x0;
        }
        else
        {
            *((uint32_t *)axinic_offset_hi) = 0x70;
        }
        sleep(1);
    }

    if (last_loop > 0) {
        //fread(ddr_base, 1, last_loop, pFile);
        for (j = 0; j < last_loop / 4; j++) {
            swap = *(uint32_t *)(ddr_base + j * 4);
            fwrite(&swap, 4, 1, pFile);
        }
    }

    printf("\n>>> Loop finished!\n");
    if(munmap(map_base, map_size) == -1) 
        PRINT_ERROR;
    close(fd);
    fclose(pFile);
    return 0;
}