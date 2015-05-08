# Copyright (c) 2013-2015 Centre for Advanced Internet Architectures,
# Swinburne University of Technology. All rights reserved.
#
# Author: Sebastian Zander (szander@swin.edu.au)
#         Grenville Armitage (garmitage@swin.edu.au)
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
## @package sourcefilter 
# Flow filtering for analysis 
#
# $Id: sourcefilter.py 1269 2015-04-23 05:35:55Z szander $

from fabric.api import abort


class SourceFilter:

    ## dictionary of (S|D)_<ip> that points to list of ports 
    source_filter = {}

    ## Build flow filter
    #  @param filter_str String of multiple flows,
    #                    format (S|D)_srcip_srcport[;(S|D)_srcip_srcport]*
    #                    srcport Port number, can be wildcard character '*'
    def __init__(self, filter_str):

   	if filter_str != '' and len(self.source_filter) == 0:
       	    for fil in filter_str.split(';'):
           	fil = fil.strip()
                arr = fil.split('_')
            	if len(arr) != 3:
                    abort('Incorrect source filter entry %s' % fil)
                if arr[0] != 'S' and arr[0] != 'D':
                    abort('Incorrect source filter entry %s' % fil)

                key = arr[0] + '_' + arr[1]  # (S|D)_<ip>
                val = arr[2]  # <port>

                if not key in self.source_filter:
                    self.source_filter[key] = []

                if val == '*':
                    # just insert wildcard and forget any other ports
                    self.source_filter[key] = [ val ]
                else:
                    # append new port unless we already have wildcard
                    if not '*' in self.source_filter[key]:
                        self.source_filter[key].append(val)


    ## Check if flow in flow filter list
    #  @param flow: flow string
    #  @return True if flow in list, false if flow is not in list
    def is_in(self, flow):

        if len(self.source_filter) == 0:
            return True

        arr = flow.split('_')
        sflow = 'S_' + arr[0]
        sflow_port = arr[1]
        dflow = 'D_' + arr[2]
        dflow_port = arr[3]

        if sflow in self.source_filter and (
            '*' in self.source_filter[sflow] or sflow_port in self.source_filter[sflow]):
            return True
        elif dflow in self.source_filter and ( 
            '*' in self.source_filter[dflow] or dflow_port in self.source_filter[dflow]):
            return True
        else:
            return False


    ## Clear source filter list
    def clear(self):
 
        self.source_filter.clear()

