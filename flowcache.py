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
## @package flowcache
# Functions to cache flows of experiments 
#
# $Id: flowcache.py 1257 2015-04-20 08:20:40Z szander $

import os
import config
from fabric.api import task, warn, local, run, execute, abort, hosts, env


## Cache file name
CACHE_FILE_NAME = 'teacup_flow_cache.txt'
## Flow cache. Index is the file name for which we have flows cached 
## (e.g. tcpdump file), value is a list of flows (which can be empty) 
flow_cache = {}

## Read cache file if exists
def read_flow_cache():

    if not os.path.isfile(CACHE_FILE_NAME):
        return

    with open(CACHE_FILE_NAME, 'r') as f:
        lines = f.readlines()
        for line in lines:
            fields = line.split()
            if len(fields) == 2:
                flow_cache[fields[0]] = fields[1].split(';')
            else:
                flow_cache[fields[0]] = []


## Append to cache if entry not in there yet. note that flows may be empty in which
## case the flow field in the cache file will be empty
#  @param fname File name
#  @param flows List of flows (5-tuples)
def append_flow_cache(fname, flows):

    if fname not in flow_cache:
        with open(CACHE_FILE_NAME, 'a') as f:
            f.write('%s %s\n' % (fname, ';'.join(flows)))


## Perform cache lookup. If we have entry for file name return list of flows that can be
## empty, otherwise return None 
#  @param fname File name for which we want to know flows
#  @return List of flows (semicolon separated) or None
def lookup_flow_cache(fname):

    # load cache first if cache is empty
    if len(flow_cache) == 0:
        read_flow_cache()

    if fname in flow_cache:
        return flow_cache[fname]
    else:
        return None 

