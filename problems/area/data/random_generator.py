#!/usr/bin/python3
import random
import sys

random.seed(sys.argv[-1])

min_x = float(sys.argv[1])
max_x = float(sys.argv[2])
min_y = float(sys.argv[3])
max_y = float(sys.argv[4])

x = random.uniform(min_x, max_x)
y = random.uniform(min_y, max_y)
print(f"{x:.2f}")
print(f"{y:.2f}")
