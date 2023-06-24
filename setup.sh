#!/usr/bin/env bash

apt-get install -y python3 python3-pip python3-dev g++

pip3 install -r /autograder/source/requirements.txt

g++ -O3 -o default_validator default_validator.cpp
