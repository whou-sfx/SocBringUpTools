
CC ?= gcc
CFLAGS ?= -Wall -g

main: pcimem dump_ddr i2c_pf

pcimem:
	gcc pcimem.c -o pcimem

dump_ddr:
	gcc dump_ddr.c -o dump_ddr

i2c_pf:
	gcc i2c_pf.c -o i2c_pf

clean:
	-rm -f *.o *~ core pcimem i2c_pf dump_ddr

