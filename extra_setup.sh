#!/usr/bin/env bash

MAINDIR="/autograder/source"
PROBLEMSDIR="/autograder/source/problems"

pushd "$MAINDIR"
apt-get install -y \
        automake \
        chicken-bin \
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
        swi-prolog \
        texlive-fonts-recommended \
        texlive-lang-cyrillic \
        texlive-latex-extra \
        texlive-plain-generic \
        tidy \
        vim

wget -O mlton.tgz https://altushost-swe.dl.sourceforge.net/project/mlton/mlton/20210117/mlton-20210117-1.amd64-linux-glibc2.31.tgz
mkdir mlton
tar -xf mlton.tgz --strip-components=1 -C ./mlton
for f in ./mlton/bin/*; do
    cp -r "$f" /usr/bin/
done
for f in ./mlton/lib/*; do
    cp -r "$f" /usr/lib/
done

pip3 install git+https://github.com/Tagl/problemtools@gradescope_autograder
pip3 install -r requirements.txt

g++ -O3 -o default_validator default_validator.cpp
popd

if [ -d "$PROBLEMSDIR" ]; then
    for problemdir in "$PROBLEMSDIR"/*; do
        [ -d "$problemdir" ] || continue
        pushd "$problemdir"
        echo "Determining time limit..."
        verifyproblem . -p submissions | tee verifyoutput 
        cat verifyoutput | grep "setting timelim to" | cut -d ' ' -f 11 > .timelimit
        echo -n "Time limit in seconds set to: "
        cat .timelimit
        popd
    done
else
    mkdir -p "$PROBLEMSDIR"
fi
