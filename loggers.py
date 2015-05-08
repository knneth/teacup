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
# Logger start/stop methods
#
# $Id: loggers.py 995 2015-02-17 00:06:12Z szander $

import re
import time
import socket
from fabric.api import task, warn, local, run, execute, abort, hosts, env, \
    settings, parallel, serial, put
import bgproc
import config
from hosttype import get_type_cached
from hostint import get_netint_cached, get_netint_windump_cached
from getfile import getfile
from runbg import runbg


# Collect all the arguments (here basically a dummy method because we
# don't used the return value)
def _args(*_nargs, **_kwargs):
    "Collect parameters for a call"
    return _nargs, _kwargs


# Function to collect used parameters
def _param_used(name, adict):
    "Store used paramter"
    adict[name] = 1

    return 0


# Function to replace the variable names with the values
def _param(name, adict):
    "Get parameter value"

    val = adict.get(name, '')
    if val == '':
        val = config.TPCONF_variable_defaults.get(name, '')
        if val == '':
            warn('Parameter %s is undefined' % name)

    return val


# Dump parameters from config
# Parameters:
#       file_prefix: prefix for file name
#       local_dir: directory on control host where file is copied to
#	only_used: '0' print all parameters defined (default),
#                  '1' print only used parameters
#       args: arguments
#       kwargs: keyword arguments
#@task
def log_config_params(
        file_prefix='', local_dir='.', only_used='0', *args, **kwargs):
    "Dump parameters from config file"

    cfg_vars = {}
    used_vars = {}

    fname = '%s/%s_config_vars.log' % (local_dir, file_prefix)

    # first identify all used parameters

    # add the special ones
    used_vars['V_duration'] = 1
    used_vars['V_ecn'] = 1
    used_vars['V_tcp_cc_algo'] = 1
    used_vars['V_runs'] = 1

    for c, v in config.TPCONF_router_queues:
        # prepare so that _params is called
        v = re.sub("(V_[a-zA-Z0-9_-]*)", "_param_used('\\1', used_vars)", v)
        # evaluate the string
        eval('_args(%s)' % v)

    for t, c, v in config.TPCONF_traffic_gens:
        # strip of the method name
        arg_list = v.split(',')
        arg_list.pop(0)
        v = ', '.join(arg_list)
        # prepare so that _params is called
        v = re.sub("(V_[a-zA-Z0-9_-]*)", "_param_used('\\1', used_vars)", v)
        # evaluate the string
        eval('_args(%s)' % v)

    for host_cfg in config.TPCONF_host_TCP_algo_params.values():
        for algo, algo_params in host_cfg.items():
            # XXX we don't yet check here which tcp the host is actually using
            for entry in algo_params:
                if entry != '':
                    sysctl_name, val = entry.split('=')
                    # eval the value (could be variable name)
                    val = re.sub(
                        "(V_[a-zA-Z0-9_-]*)",
                        "_param_used('\\1', used_vars)",
                        val)
                    eval('%s' % val)

    for cmds in config.TPCONF_host_init_custom_cmds.values():
        for cmd in cmds:
            if re.search("V_[a-zA-Z0-9_-]*", cmd):
                # XXX this only works if we have only V_ variable
                val = re.sub(
                    ".*(V_[a-zA-Z0-9_-]*).*",
                    "_param_used('\\1', used_vars)",
                    cmd)
                eval('%s' % val)

    # second write parameters to file

    with open(fname, 'w') as f:
        f.write(
            'Log of config.py V_ parameters for experiment (alphabetical order)\n\n')
        f.write('Legend:\n')
        f.write('U|N(=Used|Unused) Name: Value\n\n')

        for name in config.TPCONF_vary_parameters:
            entry = config.TPCONF_parameter_list[name]
            var_list = entry[0]
            add_vars = entry[3]

            for var in var_list:
                val = eval('_param(\'%s\', kwargs)' % var)
                cfg_vars[var] = val

            if len(add_vars) > 0:
                for var, val in add_vars.items():
                    cfg_vars[var] = val

        for var, val in config.TPCONF_variable_defaults.items():
            if var not in cfg_vars:
                cfg_vars[var] = val

        for var, val in sorted(cfg_vars.items()):
            if var in used_vars:
                f.write('U %s: %s\n' % (var, val))
            else:
                if only_used == '0':
                    f.write('N %s: %s\n' % (var, val))

    local('gzip -f %s' % fname)


# Log host tcp settings
# XXX should be unified with the code in hostsetup.py
# Parameters:
#       file_prefix: prefix for file name
#       local_dir: directory on control host where file is copied to
#       args: arguments
#       kwargs: keyword arguments
#@task
def log_host_tcp(file_prefix='', local_dir='.', *args, **kwargs):
    "Dump TCP configuration of hosts"

    fname = '%s/%s_host_tcp.log' % (local_dir, file_prefix)

    with open(fname, 'w') as f:
        f.write('Log of host TCP settings\n\n')
        f.write('Legend:\n')
        f.write('Host: TCP\n')
        f.write('   [TCP_param1]\n')
        f.write('   [TCP_param2]\n')
        f.write('   ...\n\n')

        cfg_algo = eval('_param(\'V_tcp_cc_algo\', kwargs)')

        for host in config.TPCONF_hosts:
            if cfg_algo[0:4] == 'host':
                arr = cfg_algo.split('t')
                if len(arr) == 2 and arr[1].isdigit():
                    num = int(arr[1])
                else:
                    abort(
                        'If you specify host<N>, ' +
                        'the <N> must be an integer number')

                algo_list = config.TPCONF_host_TCP_algos.get(host, [])
                if len(algo_list) == 0:
                    abort(
                        'No TCP congestion control algos defined for host %s' %
                        env.host_string)

                if num > len(algo_list) - 1:
                    num = 0
                algo = algo_list[num]
            else:
                algo = cfg_algo

            if algo == 'default':
                if config.TPCONF_host_os[host] == 'FreeBSD':
                    algo = 'newreno'
                elif config.TPCONF_host_os[host] == 'Linux':
                    algo = 'cubic'
                elif config.TPCONF_host_os[host] == 'CYGWIN':
                    algo = 'compound'

            f.write('%s: %s\n' % (host, algo))

            host_config = config.TPCONF_host_TCP_algo_params.get(host, None)
            if host_config is not None:
                algo_params = host_config.get(algo, None)
                if algo_params is not None:
                    # algo params is a list of strings of the form sysctl=value
                    for entry in algo_params:
                        if entry != '':
                            sysctl_name, val = entry.split('=')
                            # eval the value (could be variable name)
                            val = re.sub(
                                "(V_[a-zA-Z0-9_-]*)",
                                "_param('\\1', kwargs)",
                                val)
                            val = eval('%s' % val)
                            f.write('   %s = %s\n' % (sysctl_name, val))

    local('gzip -f %s' % fname)


# Log system data
# Parameters:
#	file_prefix: prefix for file name
#	remote_dir: directrory on remote where file is created
#	local_dir: directory on control host where file is copied to
@task
@parallel
def log_sysdata(file_prefix='', remote_dir='', local_dir='.'):
    "Log various information for each system"

    if remote_dir != '' and remote_dir[-1] != '/':
        remote_dir += '/'

    # get host type
    htype = get_type_cached(env.host_string)

    file_name = remote_dir + file_prefix + "_" + \
        env.host_string.replace(":", "_") + "_uname.log"
    run('uname -a > %s' % file_name, pty=False)
    getfile(file_name, local_dir)

    file_name = remote_dir + file_prefix + "_" + \
        env.host_string.replace(":", "_") + "_netstat.log"
    run('netstat -nr > %s' % file_name, pty=False)
    getfile(file_name, local_dir)

    file_name = remote_dir + file_prefix + "_" + \
        env.host_string.replace(":", "_") + "_sysctl.log"
    if htype == 'FreeBSD' or htype == 'Linux' or htype == 'Darwin':
        run('sysctl -a > %s' % file_name)
    else:
        run('echo "netsh int show int" > %s' % file_name, pty=False)
        run('netsh int show int >> %s' % file_name, pty=False)
        run('echo "netsh int tcp show global" >> %s' % file_name, pty=False)
        run('netsh int tcp show global >> %s' % file_name, pty=False)
        run('echo "netsh int tcp show heuristics" >> %s' %
            file_name, pty=False)
        run('netsh int tcp show heuristics >> %s' % file_name, pty=False)
        run('echo "netsh int tcp show security" >> %s' % file_name, pty=False)
        run('netsh int tcp show security >> %s' % file_name, pty=False)
        run('echo "netsh int tcp show chimneystats" >> %s' %
            file_name, pty=False)
        run('netsh int tcp show chimneystats >> %s' % file_name, pty=False)
        run('echo "netsh int ip show offload" >> %s' % file_name, pty=False)
        run('netsh int ip show offload >> %s' % file_name, pty=False)
        run('echo "netsh int ip show global" >> %s' % file_name, pty=False)
        run('netsh int ip show global >> %s' % file_name, pty=False)

    getfile(file_name, local_dir)

    file_name = remote_dir + file_prefix + "_" + \
        env.host_string.replace(":", "_") + "_ifconfig.log"
    if htype == 'FreeBSD' or htype == 'Linux' or htype == 'Darwin':
        run('ifconfig -a > %s' % file_name)
    else:
        run('ipconfig > %s' % file_name, pty=False)

    getfile(file_name, local_dir)

    file_name = remote_dir + file_prefix + "_" + \
        env.host_string.replace(":", "_") + "_procs.log"
    if htype == 'FreeBSD' or htype == 'Linux':
        run('ps -axu > %s' % file_name)
    elif htype == 'Darwin':
        run('ps -axu root > %s' % file_name)
    else:
        run('ps -alW > %s' % file_name, pty=False)

    getfile(file_name, local_dir)

    file_name = remote_dir + file_prefix + "_" + \
        env.host_string.replace(":", "_") + "_ntp.log"
    if htype == 'FreeBSD' or htype == 'Linux' or htype == 'Darwin':
        run('ntpq -4p > %s' % file_name)
    else:
        with settings(warn_only=True):
            # if we have ntp installed then use ntpq, otherwise use w32tm
            ret = run('ls "/cygdrive/c/Program Files (x86)/NTP/bin/ntpq"')
            if ret.return_code == 0:
                run('"/cygdrive/c/Program Files (x86)/NTP/bin/ntpq" -4p > %s' % 
                    file_name, pty=False)
            else:
                run('w32tm /query /status > %s' % file_name, pty=False)

    getfile(file_name, local_dir)

    # log tcp module parameters (Linux only)
    if htype == 'Linux':
        file_name = remote_dir + file_prefix + "_" + \
            env.host_string.replace(":", "_") + "_tcpmod.log"
        run("find /sys/module/tcp* -type f -exec grep -sH '' '{}' \; | "
            "grep -v Binary > %s" % file_name)
        getfile(file_name, local_dir)

        file_name = remote_dir + file_prefix + "_" + \
            env.host_string.replace(":", "_") + "_ethtool.log"

        run('touch %s' % file_name)
        interfaces = get_netint_cached(env.host_string, int_no=-1)
        for interface in interfaces:
            run('ethtool -k %s >> %s' % (interface, file_name))
        getfile(file_name, local_dir)


# Get queue statistics from router
# Parameters:
#       file_prefix: prefix for file name
#       remote_dir: directrory on remote where file is created
#       local_dir: directory on control host where file is copied to
@task
@parallel
def log_queue_stats(file_prefix='', remote_dir='', local_dir='.'):
    "Get queue statistics after experiment"

    if remote_dir != '' and remote_dir[-1] != '/':
        remote_dir += '/'

    # get host type
    htype = get_type_cached(env.host_string)

    file_name = remote_dir + file_prefix + "_" + \
        env.host_string.replace(":", "_") + "_queue_stats.log"

    if htype == 'FreeBSD':
        run('echo ipfw pipe show > %s' % file_name)
        run('ipfw pipe show >> %s' % file_name)
        run('echo ipfw show >> %s' % file_name)
        run('ipfw show >> %s' % file_name)
    elif htype == 'Linux':
        run('echo tc -d -s qdisc show > %s' % file_name)
        run('tc -d -s qdisc show >> %s' % file_name)

        interfaces = get_netint_cached(env.host_string, int_no=-1)
        cnt = 0
        for interface in interfaces:
            run('echo >> %s' % file_name)
            run('echo tc -s class show dev %s >> %s' % (interface, file_name))
            run('tc -s class show dev %s >> %s' % (interface, file_name))
            run('echo >> %s' % file_name)
            run('echo tc -s filter show dev %s >> %s' % (interface, file_name))
            run('tc -s filter show dev %s >> %s' % (interface, file_name))
            pseudo_interface = 'ifb' + str(cnt)
            run('echo >> %s' % file_name)
            run('echo tc -d -s class show dev %s >> %s' %
                (pseudo_interface, file_name))
            run('tc -d -s class show dev %s >> %s' %
                (pseudo_interface, file_name))
            run('echo >> %s' % file_name)
            run('echo tc -d -s filter show dev %s >> %s' %
                (pseudo_interface, file_name))
            run('tc -d -s filter show dev %s >> %s' %
                (pseudo_interface, file_name))
            cnt += 1

        run('echo iptables -t mangle -vL >> %s' % file_name)
        run('iptables -t mangle -vL >> %s' % file_name)

    getfile(file_name, local_dir)


# Start tcpdump (assume only one tcpdump per host)
# Parameters:
#       file_prefix: prefix for file name
#       remote_dir: directrory on remote where file is created
#       local_dir: directory for .start file
#	snap_len: tcpdump/windump snap length
#       tcpdump_filter: filter string passed to tcpdump
#	internal_int: '0' external (control) interface
#                     '1' internal (testbed) interface (default)
#@task
@parallel
def start_tcpdump(
        file_prefix='', remote_dir='', local_dir='.', snap_len='80',
        tcpdump_filter='', internal_int='1'):
    "Start tcpdump instance on host"

    # get host type
    htype = get_type_cached(env.host_string)

    if env.host_string in config.TPCONF_router:
        interfaces = get_netint_cached(env.host_string, int_no=-1,
                                       internal_int=internal_int)
    else:
        if htype == 'CYGWIN':
            interfaces = get_netint_windump_cached(env.host_string,
                                                    int_no=0,
                                                    internal_int=internal_int)
        else:
            interfaces = get_netint_cached(env.host_string,
                                            int_no=0,
                                            internal_int=internal_int)

    if len(interfaces) < 1:
        abort('Internal interface not specified')

    if remote_dir != '' and remote_dir[-1] != '/':
        remote_dir += '/'

    for interface in interfaces:

        if env.host_string in config.TPCONF_router:
	    if internal_int == '1':
                file_name = remote_dir + file_prefix + '_' + \
                    env.host_string.replace(':', '_') + \
                    '_' + interface + '_router.dmp'
            else:
                file_name = remote_dir + file_prefix + '_' + \
                    env.host_string.replace(':', '_') + '_ctl.dmp' 
        else:
            if internal_int == '1':
                file_name = remote_dir + file_prefix + '_' + \
                    env.host_string.replace(':', '_') + '.dmp'
            else:
                file_name = remote_dir + file_prefix + '_' + \
                    env.host_string.replace(':', '_') + '_ctl.dmp'

        if htype == 'FreeBSD' or htype == 'Linux' or htype == 'Darwin':
            tcpdump_cmd = 'tcpdump -n -s %s -i %s -w %s \'%s\'' % (
                snap_len, interface, file_name, tcpdump_filter)
        else:
            # CYGWIN
            tcpdump_cmd = 'WinDump -n -s %s -i %s -w ' \
                '"$(cygpath -aw "%s")" \'%s\'' % (
                    snap_len, interface, file_name, tcpdump_filter)
        pid = runbg(tcpdump_cmd)

        name = 'tcpdump-' + interface
        #bgproc.register_proc(env.host_string, name, '0', pid, file_name)
        bgproc.register_proc_later(
            env.host_string,
            local_dir,
            name,
            '0',
            pid,
            file_name)


# Stop tcpdump and get dump files
# Parameters:
#       file_prefix: prefix for file name
#       remote_dir: directrory on remote where file is created
#       local_dir: directory on control host where file is copied to
#@task
@parallel
def stop_tcpdump(file_prefix='', remote_dir='', local_dir='.'):
    "Stop tcpdump instance on host"

    pid = bgproc.get_proc_pid(env.host_string, 'tcpdump', '0')
    with settings(warn_only=True):
        if pid != "":
            run('kill %s' % pid, pty=False)
        else:
            # get host type
            htype = get_type_cached(env.host_string)
            if htype == "FreeBSD" or htype == "Linux" or htype == 'Darwin':
                run('killall tcpdump')
            else:
                run('killall WinDump', pty=False)

    if file_prefix != "" or remote_dir != "":
        file_name = remote_dir + file_prefix + "_" + \
            env.host_string.replace(":", "_") + ".dmp"
    else:
        file_name = bgproc.get_proc_log(env.host_string, 'tcpdump', '0')

    getfile(file_name, local_dir)
    bgproc.remove_proc(env.host_string, 'tcpdump', '0')


# Start tcp logger
# Parameters:
#       file_prefix: prefix for file name
#       remote_dir: directrory on remote where file is created
#       local_dir: directory for .start file
#@task
@parallel
def start_tcp_logger(file_prefix='', remote_dir='', local_dir='.'):
    "Start TCP information logger (e.g. siftr on FreeBSD)"

    if remote_dir != '' and remote_dir[-1] != '/':
        remote_dir += '/'

    # get host type
    htype = get_type_cached(env.host_string)

    if htype == 'FreeBSD':
        # load kernel module
        with settings(warn_only=True):
            run('kldunload siftr')
            # run('kldunload h_ertt') # do not attempt to unload, can cause
            # kernel panic

        # if h_ertt is loaded siftr outputs unsmoothed rtt as well???
        # h_ertt appears to have a bug that makes it impossible to unload,
        # so don't try to unload. test if present and only try to load if
        # not present
        with settings(warn_only=True):
            ret = run('kldstat | grep h_ertt')
        if ret.return_code != 0:
            run('kldload h_ertt')

        run('kldload siftr')

        # we need an absolute path
        if remote_dir == '':
            remote_dir = '/tmp/'

        logfile = remote_dir + file_prefix + '_' + \
            env.host_string.replace(":", "_") + "_siftr.log"
        run('sysctl net.inet.siftr.logfile=%s' % logfile)
        run('sysctl net.inet.siftr.ppl=1')
        run('sysctl net.inet.siftr.genhashes=1')
        run('sysctl net.inet.siftr.enabled=1')

        #bgproc.register_proc(env.host_string, 'tcplogger', '00', '0', logfile)
        bgproc.register_proc_later(
            env.host_string,
            local_dir,
            'tcplogger',
            '00',
            '0',
            logfile)

    elif htype == 'Linux':
        # set default sample interval to roughly 10ms
        sample_interval = 0.01

	try:
            sample_interval = float(config.TPCONF_web10g_poll_interval) / 1000.0
        except AttributeError:
            pass

        # with new web10g we use the provided web10g-logger which needs interval
        # in milliseconds, so convert here
        with settings(warn_only=True):
            out = run('web10g-logger -h | grep "poll interval given in seconds"')
            if out == '':
                sample_interval *= 1000

        # turn off logging and remove kernel module
        with settings(warn_only=True):
            run('echo 0 > /proc/sys/net/ipv4/tcp_estats') # version 2.0.8+
            run('rmmod tcp_estats_nl')

        # start kernel module
        run('modprobe tcp_estats_nl')

        # for new web10g (version 2.08 and higher) we need to turn it on, note
        # that /proc/sys/net/ipv4/tcp_estats is not just 0/1 but we need to
        # specify a bit mask to turn on/off different features.
        # we turn on all features to be compatible to previous version
        # (see /usr/src/<linux>/include/net/tcp_estats.h for bit flags,
        #  the TCP_ESTATS_TABLEMASK_* constants)
        with settings(warn_only=True):
            run('echo 95 > /proc/sys/net/ipv4/tcp_estats')

        # OLD:
        # check userland code is there
        #run('which web10g-listconns')
        #run('which web10g-readvars')
        # make sure script is there
        #put(config.TPCONF_script_path + '/web10g_logger.sh', '/usr/bin')
        #run('chmod a+x /usr/bin/web10g_logger.sh')

        # check userland code is there
        run('which web10g-logger')

        logfile = remote_dir + file_prefix + '_' + \
            env.host_string.replace(":", "_") + "_web10g.log"
        host = env.host_string.split(':')[0]

        # OLD:
        #pid = runbg('web10g_logger.sh %f %s %s' % (sample_interval, logfile, host))
        # run with high priority
        #run('renice -n -20 -p %s' % pid)

        # resolve to IP to make sure we filter on right address
        host_ip = socket.gethostbyname(host) 
        if host_ip == '':
            host_ip = host

        pid = runbg(
            'web10g-logger -e %s -i %f' %
            (host_ip, sample_interval), out_file=logfile)

        #bgproc.register_proc(env.host_string, 'tcplogger', '00', pid, logfile)
        bgproc.register_proc_later(
            env.host_string,
            local_dir,
            'tcplogger',
            '00',
            pid,
            logfile)

    elif htype == 'Darwin':
        # start dtrace based logging tool
        run('which dsiftr-osx-teacup.d')

        # since the Mac tool produces the same output as SIFTR 
        # we give it the same _siftr.log extension
        logfile = remote_dir + file_prefix + '_' + \
            env.host_string.replace(":", "_") + "_siftr.log"
        host = env.host_string.split(':')[0]

        # resolve to IP to make sure we filter on right address
        host_ip = socket.gethostbyname(host)
        if host_ip == '':
            host_ip = host

        pid = runbg(
            'dsiftr-osx-teacup.d "%s"' %
            (host_ip), out_file=logfile)

        #bgproc.register_proc(env.host_string, 'tcplogger', '00', pid, logfile)
        bgproc.register_proc_later(
            env.host_string,
            local_dir,
            'tcplogger',
            '00',
            pid,
            logfile)

    elif htype == 'CYGWIN':
        # set sample interval to roughly 10ms
        sample_interval = 0.01
        try:
            sample_interval = float(config.TPCONF_web10g_poll_interval) / 1000.0
        except AttributeError:
            pass

        # check userland code is there
        run('which win-estats-logger')

        # since the windows tool produces the same output as the web10g logger
        # we give it the same _web10g.log extension
        logfile = remote_dir + file_prefix + '_' + \
            env.host_string.replace(":", "_") + "_web10g.log"
        host = env.host_string.split(':')[0]

        # resolve to IP to make sure we filter on right address
        host_ip = socket.gethostbyname(host)
        if host_ip == '':
            host_ip = host

        pid = runbg(
            'win-estats-logger -q -e %s -i %f' %
            (host_ip, sample_interval), out_file=logfile)

        #bgproc.register_proc(env.host_string, 'tcplogger', '00', pid, logfile)
        bgproc.register_proc_later(
            env.host_string,
            local_dir,
            'tcplogger',
            '00',
            pid,
            logfile)

    else:
        warn("No TCP logger available on OS '%s'" % htype)


# Stop tcp logger
# This is only called for SIFTR
# Parameters:
#       file_prefix: prefix for file name
#       remote_dir: directrory on remote where file is created
#       local_dir: directory on control host where file is copied to
#@task
@parallel
def stop_tcp_logger(file_prefix='', remote_dir='', local_dir='.'):
    "Stop TCP logger (e.g. siftr on FreeBSD)"

    # get host type
    htype = get_type_cached(env.host_string)

    if htype == 'FreeBSD':
        run('sysctl net.inet.siftr.enabled=0')
        run('kldunload siftr')
        logfile = file_prefix + '_' + \
            env.host_string.replace(':', '_') + '_siftr.log'

    elif htype == 'Linux':
        #run('killall web100_logger')
        run('killall web100-logger')
        logfile = file_prefix + '_' + \
            env.host_string.replace(':', '_') + '_web10g.log'

    elif htype == 'Darwin':
        pass

    elif htype == 'CYGWIN':
        run('killall win-estats-logger')
        logfile = file_prefix + '_' + \
            env.host_string.replace(':', '_') + '_web10g.log'

    if logfile == '':
        if remote_dir != '':
            logfile = remote_dir + '/' + logfile

    if file_prefix != '' or remote_dir != '':
        file_name = logfile
    else:
        file_name = bgproc.get_proc_log(env.host_string, 'tcplogger', '00')

    # add a small delay to allow logger to write data to disk completely
    time.sleep(0.5)

    # commented out: I think it may be confusing if the stats not match etc.
    # if htype == 'FreeBSD':
    # filter out control traffic from siftr log but
    # stats and flow list in last line of log is left unchanged
    #host = env.host_string.split(':')[0]
    #tmp_file = local('mktemp "tmp.XXXXXXXXXX"', capture=True)
    # run('cat %s | grep -v ",%s," > %s && mv %s %s' % \
    #    (file_name, host, tmp_file, tmp_file, file_name))

    getfile(file_name, local_dir)
    bgproc.remove_proc(env.host_string, 'tcplogger', '00')


# Start dummynet logger
# Parameters:
#       file_prefix: prefix for file name
#       remote_dir: directrory on remote where file is created
#	local_dir: directory for .start file
#@task
@parallel
def start_dummynet_logger(file_prefix='', remote_dir='', local_dir='.'):
    "Start logging queue size with instrumented dummynet"

    if remote_dir != '' and remote_dir[-1] != '/':
        remote_dir += '/'

    # get host type
    htype = get_type_cached(env.host_string)

    if htype == 'FreeBSD':
        logfile = remote_dir + file_prefix + "_" + \
            env.host_string.replace(':', '_') + '_dummynet.log'
        run('sysctl net.inet.ip.dummynet.logfile=%s' % logfile)
        run('sysctl net.inet.ip.dummynet.enabled=1')
    else:
        abort("No dummynet logging available on OS '%s'" % htype)

    #bgproc.register_proc(env.host_string, 'dummynetlogger', '0', '0', logfile)
    bgproc.register_proc_later(
        env.host_string,
        local_dir,
        'dummynetlogger',
        '0',
        '0',
        logfile)


# Stop dummynet logger
# Parameters:
#       file_prefix: prefix for file name
#       remote_dir: directrory on remote where file is created
#       local_dir: directory on control host where file is copied to
#@task
@parallel
def stop_dummynet_logger(file_prefix='', remote_dir='', local_dir='.'):
    "Stop dummynet logging and get data"

    # get host type
    htype = get_type_cached(env.host_string)

    if htype == 'FreeBSD':
        run('sysctl net.inet.ip.dummynet.enabled=0')

        logfile = file_prefix + '_' + \
            env.host_string.replace(':', '_') + '_dummynet.log'
        if remote_dir != '':
            logfile = remote_dir + '/' + logfile

        if file_prefix != '' or remote_dir != '':
            file_name = logfile
        else:
            file_name = bgproc.get_proc_log(
                env.host_string,
                'dummynetlogger',
                '0')

        getfile(file_name, local_dir)
        bgproc.remove_proc(env.host_string, 'dummynetlogger', '0')


# Start all loggers
# Parameters:
#       file_prefix: prefix for file name
#       remote_dir: directrory on remote where file is created
#       local_dir: directory for .start file
#@task
@serial
def start_loggers(file_prefix='', remote_dir='', local_dir='.'):
    "Start all loggers"

    # log system data
    execute(
        log_sysdata,
        file_prefix,
        remote_dir,
        local_dir,
        hosts=config.TPCONF_router +
        config.TPCONF_hosts)
    # start tcpdumps on testbed interfaces
    execute(
        start_tcpdump,
        file_prefix,
        remote_dir,
        local_dir,
        snap_len=80,
        hosts=config.TPCONF_router +
        config.TPCONF_hosts)
    # start TCP loggers
    execute(
        start_tcp_logger,
        file_prefix,
        remote_dir,
        local_dir,
        hosts=config.TPCONF_hosts)
    # XXX don't have instrumented dummynet
    # execute(start_dummynet_logger, file_prefix, remote_dir, local_dir,
    #        hosts = config.TPCONF_router)

    # register logger processes started in parallel
    bgproc.register_deferred_procs(local_dir)


# Start broadcast ping loggers
# Parameters:
#       file_prefix: prefix for file name
#       remote_dir: directrory on remote where file is created
#       local_dir: directory for .start file
#       bc_addr: broadcast address used
#@task
@serial
def start_bc_ping_loggers(file_prefix='', remote_dir='', local_dir='.', bc_addr=''):
    "Start broadcast ping loggers"

    if bc_addr != '':
        filter_str = 'icmp && dst host %s' % bc_addr
    else:
        filter_str = 'icmp'

    # start tcpdumps on control interfaces
    execute(
        start_tcpdump,
        file_prefix,
        remote_dir,
        local_dir,
        snap_len=80,
        internal_int='0',
        tcpdump_filter=filter_str,
        hosts=config.TPCONF_router +
        config.TPCONF_hosts)

    # register logger processes started in parallel
    bgproc.register_deferred_procs(local_dir)
