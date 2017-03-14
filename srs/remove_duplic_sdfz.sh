#!/bin/bash

for file in /mnt/d/spring-analysis/replays/*.sdfz.sdfz
do
    mv "${file}" "${file%.sdfz}"

    echo "made ${file%.sdfz}"
done