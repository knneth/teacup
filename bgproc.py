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
## @package bgproc
# Functions to manage background processes list
#
# $Id: bgproc.py 1257 2015-04-20 08:20:40Z szander $

import os
import threading
from collections import namedtuple
from fabric.api import puts, abort, local


## Background process list
proc_reg = {}
## Struct used for each entry in list
hostStruct = namedtuple("hostStruct", "host pid log")
## Lock to make access to prog_reg thread safe
lock = threading.Lock()


## Remove all old .start files
# @param local_dir Local directory for experiment files 
def file_cleanup(local_dir='.'):
    local('rm -f %s/*.start' % local_dir)


## Get key string handle based on host, process name and counter
#  @param host Host identifier used by Fabric
#  @param name Name of the process
#  @param counter Unique counter value for each process
#  @return String handle (key)
def _get_handle(host='', name='', counter=''):
    # put counter before name so processes that need to be stopped early
    # (e.g. tcp_logger) are the first in the list of processes for one host
    return host + '|' + counter + '|' + name


## Register process in list
#  @param host Host identifier used by Fabric
#  @param name Name of the process
#  @param counter Unique counter value for each process
#  @param pid Process id
#  @param log Log file name
def register_proc(host='', name='', counter='', pid='', log=''):
    handle = _get_handle(host, name, counter)
    hdata = hostStruct(host, pid, log)
    with lock:
        if handle not in proc_reg:
            proc_reg.update({handle: hdata})
        else:
            abort(
                "Duplicate process handle '%s', increase counter value" %
                handle)


## Write .start file that allows to register process in list later
#  @param host Host identifier used by Fabric
#  @param local_dir Directory for .start file
#  @param name Name of the process
#  @param counter Unique counter value for each process
#  @param pid Process id
#  @param log Log file name
def register_proc_later(
        host='', local_dir='.', name='', counter='', pid='', log=''):
    file_name = local_dir + '/' + host + '_' + \
        name + '_' + counter + '_' + pid + '.start'
    f = open(file_name, 'w')
    f.write(log)
    f.close()


## Register all processes based on .start files
#  @param local_dir Directory for .start file
def register_deferred_procs(local_dir='.'):
    for fn in os.listdir(local_dir):
        if fn.endswith('.start'):
            file_name = local_dir + '/' + fn
            s = fn.replace('.start', '')
            a = s.split('_')
            f = open(file_name, 'r')
            logfile = f.read()
            f.close()
            register_proc(a[0], a[1], a[2], a[3], logfile)
            os.remove(file_name)


## Remove process from list
#  @param host Host identifier used by Fabric
#  @param name Name of the process
#  @param counter Unique counter value for each process
def remove_proc(host='', name='', counter=''):
    handle = _get_handle(host, name, counter)
    with lock:
        if handle in proc_reg:
            del proc_reg[handle]


## Return pid of process
#  @param host Host identifier used by Fabric
#  @param name Name of the process
#  @param counter Unique counter value for each process
#  @return PID or process (if in list) or empty string (if not in list)
def get_proc_pid(host='', name='', counter=''):
    handle = _get_handle(host, name, counter)
    with lock:
        if handle in proc_reg:
            return proc_reg[handle].pid
        else:
            return ""


## Return log file name of process
#  @param host Host identifier used by Fabric
#  @param name Name of the process
#  @param counter Unique counter value for each process
#  @return Log file name of process (if in list) or empty string (if not in list)
def get_proc_log(host='', name='', counter=''):
    handle = _get_handle(host, name, counter)
    with lock:
        if handle in proc_reg:
            return proc_reg[handle].log
        else:
            return ""


## Dump process list
def print_proc_list():
    puts('\n[MAIN] Background processes:')
    with lock:
        for p in sorted(proc_reg):
            puts("[MAIN] %s : %s" % (p, proc_reg[p]))

    puts("\n")


## Clear process list
def clear_proc_list():
    with lock:
        proc_reg.clear()


## Get list of processes in list
#  @return List of processes
def get_proc_list_items():
    with lock:
        return proc_reg.iteritems()
