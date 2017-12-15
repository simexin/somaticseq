FROM ubuntu:16.04

MAINTAINER Li Tai Fang <li_tai.fang@roche.com>

RUN apt-get update && apt-get install -y vcftools wget && apt-get clean
RUN cd /opt && wget https://www.dropbox.com/s/bpv098m36j8ljk4/vcftools.script.sh && chmod a+x vcftools.script.sh
