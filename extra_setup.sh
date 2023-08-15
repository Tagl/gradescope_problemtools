#!/usr/bin/env bash

MAINDIR="/autograder/source"
PROBLEMSDIR="/autograder/source/problems"

pushd "$MAINDIR"
apt-get install -y python3 python3-pip python3-dev g++
add-apt-repository ppa:pypy/ppa
apt update
apt install -y pypy3
pip3 install -r requirements.txt
g++ -O3 -o default_validator default_validator.cpp
popd

if [ -d "$PROBLEMSDIR" ]; then
    for problemdir in "$PROBLEMSDIR/*"; do
        [ -e "$problemdir" ] || continue
        pushd "$problemdir/data"
        if [ -e generator ]; then
            dos2unix generator
            . ./generator
        fi
        popd
    done
else
    mkdir -p "$PROBLEMSDIR"
fi
