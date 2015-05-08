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
# covert config for physical testbed to config for VMs
#
# $Id: convert_config_addr.sh 958 2015-02-12 04:52:49Z szander $

if [ $# -ne 2 ] ; then
	echo "Usage: $0 <config_file> <ip_map_file>"
	echo "		<config_file>	teacup config.py"
	echo "		<ip_map_file>	address map file"
	echo "				format of each line is: <phy_address> <vm_address> | <phy_address> REMOVE <vm_address>"
	echo "				the first type will map a physical host to a VM host by replacing <phy_address> with <vm_address>"
	echo "				the second type will remove a physical host and map any queue or traffic generator commands to <vm_address>"
	exit 1
fi

# config file name
CONFIG=$1
# map of physical addresses to VM addresses
IPMAP=$2

cp $CONFIG ${CONFIG}.tmp

while read LINE ; do 
	COMMENT=`echo $LINE | grep "#"`
	if [ "$COMMENT" != "" ] ; then
		continue
	fi

	NTCP_ADDR=`echo $LINE | cut -d' ' -f 1`
	VM_ADDR=`echo $LINE | cut -d' ' -f 2`
	if [ "$VM_ADDR" != "REMOVE" ] ; then
		cat ${CONFIG}.tmp | sed -e "s/$NTCP_ADDR/$VM_ADDR/g" > ${CONFIG}.tmp2
	else
		VM_ADDR2=`echo $LINE | cut -d' ' -f 3`
		cat ${CONFIG}.tmp | sed -e "s/,[ ']*$NTCP_ADDR[ ']*,/,/g" > ${CONFIG}.tmp2
		mv -f ${CONFIG}.tmp2 ${CONFIG}.tmp
		# this removes lines in TPCONF_host_internal_ip and TPCONF_host_os
		cat ${CONFIG}.tmp | sed -e "s/.*[ ']*$NTCP_ADDR[ ']*:.*$//g" > ${CONFIG}.tmp2
		mv -f ${CONFIG}.tmp2 ${CONFIG}.tmp
		# this replaces address in queue or traffic generator commands 
		cat ${CONFIG}.tmp | sed -e "s/$NTCP_ADDR/$VM_ADDR2/g" > ${CONFIG}.tmp2
	fi
	mv -f ${CONFIG}.tmp2 ${CONFIG}.tmp
done < $IPMAP 

mv $CONFIG ${CONFIG}.bak
mv -f ${CONFIG}.tmp $CONFIG
