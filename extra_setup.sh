#!/usr/bin/env bash

MAINDIR="/autograder/source"
PROBLEMSDIR="/autograder/source/problems"

pushd "$MAINDIR"
apt install -y automake g++ make libboost-regex-dev libgmp-dev libgmp10 libgmpxx4ldbl python3 python3-pip python3-dev python3-pytest python3-setuptools python3-yaml python3-plastex
apt install -y ghostscript libgmpxx4ldbl python3-minimal python-pkg-resources python3-plastex python3-yaml texlive-fonts-recommended texlive-lang-cyrillic texlive-latex-extra texlive-plain-generic tidy
pip3 install git+https://github.com/kattis/problemtools
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
