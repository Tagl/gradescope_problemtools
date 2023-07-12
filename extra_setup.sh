#!/usr/bin/env bash

pushd /autograder/source
apt-get install -y python3 python3-pip python3-dev g++
add-apt-repository ppa:pypy/ppa
apt update
apt install -y pypy3
pip3 install -r requirements.txt
g++ -O3 -o default_validator default_validator.cpp
popd

pushd /autograder/source/problems/*/data
dos2unix generator
. ./generator
popd
