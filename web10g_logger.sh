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
# log tcp info using the web10g tools
# this script is outdated, it has been replaced by the C program web10g-logger
#
# $Id: web10g_logger.sh 958 2015-02-12 04:52:49Z szander $

if [ $# -lt 2 -o $# -gt 3 ] ; then
        echo "Usage: $0 <interval> <log_file> [<exclude>]"
        echo "          <interval>      poll interval as fraction of seconds"
        echo "          <log_file>      log file to write the data to"
        echo "          <exclude>       IP address to exclude, no data is logged for this IP"
        exit 1
fi

# Poll interval in seconds
INTERVAL=$1
# Log file
LOG_FILE=$2
# exclude flows with this IP (control interface), can be empty string (all will be included)
EXCLUDE=$3

rm -f $LOG_FILE

while [ 1 ] ; do
	TIME_1=`date +%s.%N`
	CIDS=`web10g-listconns | awk -v exclude=$EXCLUDE '{ if ( $2 != exclude && $4 != exclude ) print $1 }' | egrep "^[0-9]+$"`
	echo " " >> $LOG_FILE
	echo "POLL $TIME_1" >> $LOG_FILE
	for CID in $CIDS ; do
		CONN_DETAILS=`web10g-listconns | awk '{ print "CID: " $1 "  Local: " $2 ":" $3 "  Remote: " $4 ":" $5 }' | egrep "^CID: $CID "`
		echo " " >> $LOG_FILE
		echo "TCP FLOW: $CONN_DETAILS" >> $LOG_FILE
		web10g-readvars $CID 2>&1 >> $LOG_FILE
	done

	TIME_2=`date +%s.%N`
	SLEEP_TIME=`echo $TIME_1 $TIME_2 $INTERVAL | awk '{ st = $3 - ($2 - $1) ; if ( st < 0 ) st = 0 ; print st }'`
	sleep $SLEEP_TIME
done
