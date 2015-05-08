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
# Get log/dump file from remote
#
# $Id: getfile.py 958 2015-02-12 04:52:49Z szander $

import os
from fabric.api import get, local, run, abort, env, puts
from hosttype import get_type_cached


# Get md5 hash for file
# Parameters:
#       file_name: name of the file to compute MD5 over
#       for_local: '0' -> run on remote host, '1' -> run on local host
def _get_md5val(file_name='', for_local='0'):
    "Get MD5 hash for file depending on OS"

    # get type of current host
    htype = get_type_cached(env.host_string, for_local)

    if htype == 'FreeBSD' or htype == 'Darwin':
        md5_command = "md5 %s | awk '{ print $NF }'" % file_name
    elif htype == 'Linux' or htype == 'CYGWIN':
        md5_command = "md5sum %s | awk '{ print $1 }'" % file_name
    else:
        md5_command = ''

    if for_local == '1':
        local(md5_command, capture=True)
    else:
        run(md5_command, pty=False, shell=False)


# Collect log file
# Parameters:
#       file_name: name of the log file
#       local_dir: local directory to copy log file into
def getfile(file_name='', local_dir='.'):
    "Get file from remote and check that file is not corrupt"

    if file_name == '':
        abort('Must specify file name')

    if file_name[0] != '/':
        # get type of current host
        htype = get_type_cached(env.host_string)

        # need to guess the path
        if env.user == 'root' and not htype == 'CYGWIN':
            remote_dir = '/root'
        else:
            remote_dir = '/home/' + env.user

        file_name = remote_dir + '/' + file_name
    else:
        remote_dir = os.path.dirname(file_name)

    # gzip and download (XXX could use bzip2 instead, slower but better
    # compression)
    run('gzip -f %s' % file_name, pty=False)
    file_name += '.gz'
    local_file_name = get(file_name, local_dir)[0]

    # get MD5 on remote
    md5_val = _get_md5val(file_name, '0')
    if md5_val != '':
        # get MD5 for downloaded file
        local_md5_val = _get_md5val(local_file_name, '1')
        # check if MD5 is correct
        if md5_val != local_md5_val:
            abort('Failed MD5 check')
        else:
            puts('MD5 OK')

    run('rm -f %s' % file_name, pty=False)
