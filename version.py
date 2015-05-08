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
## @package version
# Print version number and svn revision info
#
# $Id: version.py 1257 2015-04-20 08:20:40Z szander $

import os
import sys
import config
from fabric.api import task, warn, local, run, execute, abort, hosts, env, \
    puts, hide


## Print out TEACUP version (TASK)
@task
def get_version():
    "Print TEACUP version information"
   
    # get version info from VERSION file
    sys.stdout.write('TEACUP Version ')
    with open(config.TPCONF_script_path + '/VERSION', 'r') as f:
        ver_info  = f.readlines() 

    # if no svn revision info in VERSION, then possibly this is a checked out
    # copy. try and get svn revision info from svn. 
    if ver_info[1].find('XXXX') > -1:
        if os.path.exists(config.TPCONF_script_path + '/.svn/'):
            curr_dir = os.getcwd()
            os.chdir(config.TPCONF_script_path)
            with hide('commands'):
                svn_info = local('./get_svn_info.sh', capture=True)
            os.chdir(curr_dir)
            ver_info = [ver_info[0] + svn_info + '\n']
  
    sys.stdout.writelines(ver_info)
    sys.stdout.write('Copyright (c) 2013-2015 Centre for Advanced Internet Architectures\n') 
    sys.stdout.write('Swinburne University of Technology. All rights reserved.\n') 
