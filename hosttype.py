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
# Functions to determine the type of host
#
# $Id: hosttype.py 958 2015-02-12 04:52:49Z szander $

from fabric.api import task, warn, local, run, execute, abort, hosts

# maps external ips/names to OS (automatically determined)
host_os = {}

# OS of control host (automatically determined)
ctrl_host_os = ""


# Get host type and populate host_os, ctrl_host_os
# Parameters:
#	host: the host IP or name
#	for_local: '0' get type of remote host,
#                  '1' get type of local host (where we execute this script)
# Return: operating system string, e.g. "FreeBSD" or "Linux" or "CYGWIN"
def get_type_cached(host='', for_local='0'):
    global host_os
    global ctrl_host_os

    if for_local == '1':
        if ctrl_host_os == "":
            ctrl_host_os = local('uname -s', capture=True)
        return ctrl_host_os
    else:
        if host not in host_os:
            host_os = dict(
                host_os.items() +
                execute(
                    get_type,
                    hosts=host).items())
        return host_os.get(host, '')


# Get host operating system type
# Return: operating system string, e.g. "FreeBSD" or "Linux" or "CYGWIN"
@task
def get_type():
    "Get type/OS of host, e.g. Linux"

    htype = run('uname -s', pty=False)
    # ignore Windows version bit of output
    if htype[0:6] == "CYGWIN":
        htype = "CYGWIN"

    return htype


# Clear host type cache
def clear_type_cache():
    global host_os

    host_os.clear()
