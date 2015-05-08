#!/bin/sh
# Copyright (c) 2013-2015 Centre for Advanced Internet Architectures,
# Swinburne University of Technology. All rights reserved.
#
# Author: Sebastian Zander (szander@swin.edu.au)
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE AUTHOR AND CONTRIBUTORS ``AS IS'' AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE AUTHOR OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
# OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY
# OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
# SUCH DAMAGE.
#
# script to start a series of experiemnts
# usage: run.sh [<fabfile>]
#
# $Id: run.sh 958 2015-02-12 04:52:49Z szander $

PREFIX=`date +"%Y%m%d-%H%M%S"`_experiment

# optionally we can specify the fabfile
if [ "$1" != "" ] ; then
	FABFILE="-f $1"
else
	FABFILE=""
fi

# create sub directory for test id prefix
mkdir -p ${PREFIX}

#PYTHONPATH=. stdbuf -o0 -e0 fab ${FABFILE} --linewise run_experiment_multiple:test_id=${PREFIX} > ${PREFIX}/${PREFIX}.log 2>&1
# with --linewise it is ordered per host despite parallel, but output is delayed a lot, which is
# annoying for testing
PYTHONPATH=. stdbuf -o0 -e0 fab ${FABFILE} run_experiment_multiple:test_id=${PREFIX} > ${PREFIX}/${PREFIX}.log 2>&1

