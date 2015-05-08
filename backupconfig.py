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
## @package backupconfig
# Backup config files for each experiment 
#
# $Id: backupconfig.py 1268 2015-04-22 07:04:19Z szander $

import os
import shutil
import re
import inspect

from fabric.api import task, warn, put, puts, get, local, run, execute, \
    settings, abort, hosts, env, runs_once, parallel

import config


## Backup config files (TASK)
#  @param out_dir Experiment directory
@task
def backup_config(out_dir):
    "Backup config in experiment directory"

    # copy main config file
    # note that shutil.copy preserves the timestamps
    shutil.copy2('config.py', out_dir)

    # copy all files included with execfile()
    lines = inspect.getsourcelines(config)
    for line in lines[0]:
        res = re.search('execfile\("(.*)"\)', line)
        if res:
            fname = res.group(1)
            shutil.copy2(fname, out_dir) 
        
    local('cd %s && tar -czf %s_config.tar.gz *.py && rm -f *.py' % 
          (out_dir, out_dir)) 


## Dump all TPCONF_ variables in one file (TASK)
#  @param test_id_pfx Experiment ID prefix 
@task
def dump_config_vars(test_id_pfx):
    "Dump TPCONF variables from config into one file"

    fname = test_id_pfx + '/' + test_id_pfx + '_tpconf_vars.log'
    with open(fname, 'w') as f:
        names = dir(config) 
        for v in sorted(names):
            if v.startswith('TPCONF_'):
                # eval will evaluate the name so we get the content of the
                # variable. repr converts it into the official string 
                # representation, so we have quotes around strings etc.
                f.write(v + ' = ' + repr(eval('config.' + v)) + '\n')

    local('gzip -f %s' % fname)

