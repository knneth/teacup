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
# compare different TCP CC algos (assumes no more than 4 TCPs)
# one page per type (cwnd, spprtt, tcprtt, throughout)
#
# $Id: tcp_comparison.sh 958 2015-02-12 04:52:49Z szander $

if [ $# -ne 2 ] ; then
	echo "Usage: $0 <prefix> <out_prefix>"
	echo "		<prefix>	prefix of input pdf files to compare"
	echo "		<out_prefix>	prefix of output pdf file"
	exit 1
fi

PREFIX=$1
OUT_PREFIX=$2
SPATH=`dirname $0`

TYPES="cwnd spprtt tcprtt throughput"
for TYPE in ${TYPES} ; do
	echo "${SPATH}/combine_graphs.sh -o ${OUT_PREFIX}_${TYPE}_different_tcps.pdf `find . -name "${PREFIX}*${TYPE}*.pdf" | sort`"
	${SPATH}/combine_graphs.sh -o ${OUT_PREFIX}_${TYPE}_different_tcps.pdf `find . -name "${PREFIX}*${TYPE}*.pdf" | sort`
done
