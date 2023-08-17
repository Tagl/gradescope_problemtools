#!/usr/bin/env bash

MAINDIR="/autograder/source"
PROBLEMSDIR="/autograder/source/problems"

pushd "$MAINDIR"
apt-get update && \
apt-get install -y \
        automake \
        g++ \
        git \
        libboost-all-dev \
        libgmp-dev \
        libgmp10 \
        libgmpxx4ldbl \
        openjdk-11-jdk \
        python3-minimal \
        python3-pip \
        python3-plastex \
        python3-yaml \
        texlive-fonts-recommended \
        texlive-lang-cyrillic \
        texlive-latex-extra \
        texlive-plain-generic \
        tidy \
        vim

pip3 install git+https://github.com/kattis/problemtools
pip3 install -r requirements.txt

add-apt-repository ppa:pypy/ppa
apt update
apt install -y pypy3

g++ -O3 -o default_validator default_validator.cpp
popd

if [ -d "$PROBLEMSDIR" ]; then
    for problemdir in "$PROBLEMSDIR/*"; do
        [ -e "$problemdir" ] || continue
        pushd "$problemdir"
        pushd "data"
        if [ -e generator ]; then
            dos2unix generator
            . ./generator
        fi
        popd
        echo "Determining time limit..."
        verifyproblem . -p submissions | grep "setting timelim to" | cut -d ' ' -f 11 > .timelimit
        echo -n "Time limit in seconds set to: "
        cat .timelimit
        popd
    done
else
    mkdir -p "$PROBLEMSDIR"
fi
