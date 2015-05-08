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
## @package util
# utility functions
#
# $Id: util.py 1257 2015-04-20 08:20:40Z szander $

import os

import time
import config
from fabric.api import reboot, task, warn, local, put, puts, run, execute, \
    abort, hosts, env, settings, parallel


## Copy file to hosts
#  @param file_name Name of file
#  @param remote_path Path to copy file to on remote host
#  @param method Copy method (put or scp)
def _copy_file(file_name='', remote_path='', method='put'):
    if remote_path == '':
        remote_path = os.path.dirname(os.path.abspath(file_name))
    if method == 'scp':
        local(
            'scp %s %s@%s:%s' %
            (file_name,
             env.user,
             env.host_string,
             remote_path))
    else:
        put(file_name, remote_path)


## Copy file to hosts
## Uses hosts specified on command line, or hosts specified in config
## (if no hosts are specified on command line)
#  @param file_name Name of file
#  @param remote_path Path to copy file to on remote host
#  @param method Copy method (put or scp)
@task
def copy_file(file_name='', remote_path='', method='put'):
    "Copy file to specified set of hosts"

    if len(env.all_hosts) == 0:
        # if no hosts specified on command use all hosts specified in config
        execute(
            _copy_file,
            file_name,
            remote_path,
            method,
            hosts=config.TPCONF_router +
            config.TPCONF_hosts)
    else:
        execute(
            _copy_file,
            file_name,
            remote_path,
            method,
            hosts=env.host_string)


## Add current user public key to authorized keys
## Assumes ~/.ssh/id_rsa.pub exists
@task
def authorize_key():
    "Add current user's public key to authorised keys"

    put('~/.ssh/id_rsa.pub', '/tmp')
    run('touch ~/.ssh/authorized_keys && ' +
        'cat ~/.ssh/authorized_keys /tmp/id_rsa.pub > /tmp/authorized_keys && ' +
        'mv /tmp/authorized_keys ~/.ssh/authorized_keys && rm -f /tmp/id_rsa.pub',
        pty=False)


## General method to execute a command on a set of hosts
#  @param cmd Command to be executed
def _exec_cmd(cmd):
    with settings(warn_only=True):
        run(cmd, pty=False)


## General method to execute a command on a set of hosts
## Uses hosts specified on command line, or hosts specified in config
## (if no hosts are specified on command line)
#  @param cmd Command to be executed
@task
def exec_cmd(cmd=''):
    "Execute specified command on specified set of hosts"

    if len(env.all_hosts) == 0:
        # if no hosts specified on command use all hosts specified in config
        execute(
            _exec_cmd,
            cmd,
            hosts=config.TPCONF_router +
            config.TPCONF_hosts)
    else:
        execute(_exec_cmd, cmd, hosts=env.host_string)
