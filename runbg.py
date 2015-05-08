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
# Command to run background processes
#
# $Id: runbg.py 958 2015-02-12 04:52:49Z szander $

import time
import bgproc
from fabric.api import task, run, execute, env, settings, puts, parallel
from hosttype import get_type_cached
from getfile import getfile


# Run background command on remote (this just makes sure we can detach
# properly from shell without having to resort to dtach etc.)
# Parameters:
#       command: command to execute
#       out_file: file where stdout is redirected to
#	wait: wait time in seconds.milliseconds before execute
#	shell: False: don't execute in separate shell,
#              True: execute in separate shell (see Fabric documentation)
# pty: False -> don't use pseudo terminal, True -> use pseudo terminal
# (see Fabric documentation)
def runbg(command, wait='0.0', out_file="/dev/null",
          err_file=None, shell=False, pty=True):

    # get type of current host
    htype = get_type_cached(env.host_string)

    # on Linux with pty set to true, we don't get tool output in log,
    # but that doesn't matter so much, since we are starting most things
    # delayed with runbg_wrapper.sh. problem with pty=false is that
    # with small sleep values processes may not get started on Linux (on
    # slow systems such as VMs)
    if htype == 'Linux' or htype == 'FreeBSD' or htype == 'Darwin':
        result = run(
            'nohup runbg_wrapper.sh %s %s >%s & sleep 0.1 ; echo "[1] $!" ' %
            (wait, command, out_file), shell, pty)
    else:
        result = run(
            'nohup runbg_wrapper.sh %s %s >%s & sleep 0.1 ; echo "[1] $!" ' %
            (wait, command, out_file), shell, pty=False)

    # get pid from output
    result = result.replace('\r', '')
    out_array = result.split('\n')
    for line in out_array:
        if line.find('[1] ') > -1:
            pid = line.split(" ")[-1]
            break

    # check it is actually running (XXX slightly delay this?)
    # if command executes very fast, this will cause task to fail, but quick
    # commands should not be run with runbg()
    run('kill -0 %s' % pid, pty=False)

    return pid


@task
# Stop a process
# Parameters:
#       pid: process ID
def stop_process(pid):
    # first: kill child process(es) started started by process (e.g.
    # runbg_wrapper start child processes)
    with settings(warn_only=True):
        ret = run('pkill -P %s' % pid, pty=False)
    if ret.return_code != 0:
        puts(
            'pkill may have failed because child process(es) terminated already')

    # second: kill process (if we used runbg_wrapper then it should be dead
    # already but who knows)
    with settings(warn_only=True):
        ret = run('kill %s' % pid, pty=False)
    if ret.return_code != 0:
        puts('kill may have failed because process terminated already')


# must import this down here to make circular dependency work (XXX move
# stop functions into separate file?)
from loggers import stop_tcp_logger, stop_dummynet_logger


# Stop all processes
# XXX stop processes in parallel (tried to implement this but didn't
# work with fabric)
# Parameters:
#       local_dir: local directory to download log file to
@task
def stop_processes(local_dir='.'):

    # first: stop processes and tcp loggers
    for k, v in sorted(bgproc.get_proc_list_items()):
        if v.pid != '0':
            execute(stop_process, v.pid, hosts=[v.host])  # kill process
        else:
            # handle siftr and dummynet logger
            if k.find('tcplogger') > -1:
                execute(stop_tcp_logger, local_dir=local_dir, hosts=[v.host])
            elif k.find('dummynetlogger') > -1:
                execute(
                    stop_dummynet_logger,
                    local_dir=local_dir,
                    hosts=[
                        v.host])

    # second: get log files
    for k, v in sorted(bgproc.get_proc_list_items()):
        if v.pid != '0' and v.log != '':
            execute(
                getfile,
                file_name=v.log,
                local_dir=local_dir,
                hosts=[
                    v.host])  # get log file

    # finally clear process list
    bgproc.clear_proc_list()
