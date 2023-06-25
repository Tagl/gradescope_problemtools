#!/usr/bin/python3
import random
import sys

random.seed(sys.argv[-1])

min_x = int(sys.argv[1])
max_x = int(sys.argv[2])
min_y = int(sys.argv[3])
max_y = int(sys.argv[4])

x = random.randint(min_x, max_x)
y = random.randint(min_y, max_y)
print(x)
print(y)
