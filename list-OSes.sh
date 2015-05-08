#!/bin/sh
# Copyright (c) 2013-2015 Centre for Advanced Internet Architectures,
# Swinburne University of Technology. All rights reserved.
#
# Author: Grenville Armitage (garmitage@swin.edu.au)
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
# Tool to walk through experiments under the pwd, identifying all the
# experiment prefixes, then walking through the home directories
# of each experiment (by prefix) and extracting uname information
# for each machine participating in each experiment.
#
# SPATH="./"
# SPATH="/home/user/experiments"
SPATH=`pwd`

echo Identifying all experiment logfiles under $SPATH

# Use 'find' here so we can operate at different levels
# in the directory tree (e.g. experiments over a range of
# directories, or a subset of experiments under one directory)

# logfiles=`find ${SPATH} -type f -name "20*.log" | sort -u`
logfiles=`find ${SPATH} -type f -name "????????-??????_experiment.log" | sort -u`

for lfile in $logfiles
{
	# Identify experiment prefix and directory for this experiment

	lbase=${lfile##*/}	# lbase=`basename $lfile`
	ldir=${lfile%/*}	# ldir=`dirname $lfile`

	lprefix=`echo $lbase | cut -f 1 -d "."`

	# Locate the actual experiment raw data either under ${ldir} or ${ldir}/${lprefix}
	# (depends on whether the *.log file was a peer of, or above, the directory
	# containing the raw data)
	search_dir=${ldir}
	if [ -e ${ldir}/${lprefix} ] ; then
	{
 		search_dir=${ldir}/${lprefix}
	}
	fi
	echo Experiment $lprefix is located in $search_dir

	# Identify the uname files (start in $ldir rather than $SPATH for speed)
	# and extract one representative example from each host used (which
	# means we need to ignore all the many identical uname files from
	# distinct trials and runs under each experiment).

	# Note: using cut with "_" and specific fields can break on experiments
	# when "host_N" is used instead of a specific TCP CC name.
	#find $ldir -type f -name "${lprefix}*uname*" | cut -f 1,2,19,20 -d "_" | sort -u

	# Instead, find the full name (up to the "_run_NN" field) of on representative trial
	# then gzcat the contents of all *uname* variants of that trial.
	# We do it this way to auto-handle different numbers of active hosts in different experiments.
	# NOTE: The sed syntax means "replace the line with the matching subfield inside the ()",
	# which strips off the suffix beyond the run_NN field in the file names.

 	one_trialrun_prefix=`find $search_dir -type f -name "${lprefix}*uname*" | tail -1 | sed "s/\(.*_run_[0-9]_\).*/\1/"`

	for uname in ${one_trialrun_prefix}*uname*
	{
		echo -n "   " ; gzcat $uname
	}

}

