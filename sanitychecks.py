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
# Sanity checks
#
# $Id: sanitychecks.py 1000 2015-02-17 06:38:35Z szander $

import sys
import os
import re
import datetime
import config
from fabric.api import task, warn, local, run, execute, abort, hosts, \
    env, settings, parallel, serial, puts, put
from hosttype import get_type_cached
from hostint import get_netint_cached, get_netint_windump_cached
from hostmac import get_netmac_cached

from trafficgens import start_iperf, stop_iperf, start_ping, stop_ping, \
    start_http_server, stop_http_server, start_httperf, stop_httperf, \
    start_httperf_dash, stop_httperf_dash, create_http_dash_content, \
    create_http_incast_content, start_httperf_incast, \
    stop_httperf_incast, start_nttcp, start_httperf_incast_n


def _args(*_nargs, **_kwargs):
    "Collect parameters for a call"
    return _nargs, _kwargs


# helper method for variable name checking
def _reg_vname(name, vnames, entry):
    vnames[name] = entry
    # hacky: return 0 so we don't break mathematical operations on the
    # parameters and eval fails
    return 0


# Check config file settings
# Parameters:
@task
def check_config():
    "Check config file"

    # XXX add checks for existance of some variables before using them

    config_file = str(
        sys.modules['config']).split(' ')[3].replace(
        '\'',
        '').replace(
            '>',
        '')
    puts('Config file: %s' % config_file)

    if config.TPCONF_script_path == '' or not os.path.exists(
            config.TPCONF_script_path):
        abort(
            'TPCONF_script_path must be set to existing directory ' +
            'containing the .py files')

    # test if path incorrectly set
    file_name = config.TPCONF_script_path + '/sanitychecks.py'
    try:
        with open(file_name):
            pass
    except IOError:
        abort(
            'TPCONF_script_path seems to be incorrect, could not ' +
            'find sanitychecks.py')

    version_file = config.TPCONF_script_path + '/VERSION'
    version = 'no version info'
    try:
        with open(version_file) as f:
            version = f.readlines()[0]
    except IOError:
        pass

    version = version.rstrip()

    puts('Script path: %s' % config.TPCONF_script_path)
    puts('Script version: %s' % version)
 
    tftpboot_dir = ''
    try:
        tftpboot_dir = config.TPCONF_tftpboot_dir
    except AttributeError:
        pass

    if tftpboot_dir != '' and not os.path.exists(
            tftpboot_dir):
        abort('TPCONF_tftpboot_dir must be set to existing directory')

    if tftpboot_dir != '':
        # test if path incorrectly set
        file_name = tftpboot_dir + '/conf.ipxe'
        try:
            with open(file_name):
                pass
        except IOError:
            abort(
                'TPCONF_tftpboot_dir seems to be incorrect, could not ' +
                'find conf.ipxe')

    do_power_cycle = '0'
    try:
        do_power_cycle = config.TPCONF_do_power_cycle
    except AttributeError:
        pass

    if do_power_cycle == '1':
        # check that we have entry for all hosts
        for h in (config.TPCONF_router + config.TPCONF_hosts):
            if h not in config.TPCONF_host_power_ctrlport:
                abort('No entry in TPCONF_host_power_ctrlport for host %s' % h)

        if config.TPCONF_power_admin_name == '':
            abort('TPCONF_power_admin_name not defined')
        if config.TPCONF_power_admin_pw == '':
            abort('TPCONF_power_admin_pw not defined')

    if config.TPCONF_test_id == '':
        warn('TPCONF_test_id is not set in config file')

    if len(config.TPCONF_router) == 0:
        abort('TPCONF_router must define router')

    if len(config.TPCONF_hosts) == 0:
        abort('TPCONF_hosts must define at least one host')

    # check that we have internal IPs defined
    for h in (config.TPCONF_router + config.TPCONF_hosts):
        if h not in config.TPCONF_host_internal_ip:
            abort('Internal IP not defined for host %s' % h)
        if not isinstance(config.TPCONF_host_internal_ip[h], list):
            abort('Internal IP(s) are not a list for host %s' % h)
        if len(config.TPCONF_host_internal_ip[h]) < 1:
            abort('Must specify at least one internal IP for host %s' % h)

    # if host operating system spec exist check that we have one entry
    # for each host and that OS names are correct
    try:
        host_os = config.TPCONF_host_os 
        for h in (config.TPCONF_router + config.TPCONF_hosts):
            if h not in host_os:
                abort('OS not defined for host %s' % h)
            if host_os[h] != 'FreeBSD' and host_os[h] != 'Linux' and \
               host_os[h] != 'CYGWIN' and host_os[h] != 'Darwin':
                abort('Unknown OS for host %s, OS name must be FreeBSD, Linux, ' \
                      'CYGWIN or Darwin' % h)
            if host_os[h] == 'Linux' and h in config.TPCONF_router:
                try:
                    x = config.TPCONF_linux_kern_router
                except AttributeError:
                    abort('If router OS is set to Linux, you must specify ' \
                          'TPCONF_linux_kern_router')
            if host_os[h] == 'Linux' and h in config.TPCONF_hosts:
                try:
                    x = config.TPCONF_linux_kern_hosts
                except AttributeError:
                    abort('If host OS is set to Linux, you must specify ' \
                          'TPCONF_linux_kern_hosts')
    except AttributeError:
        pass
        

    try:
        duration = int(config.TPCONF_duration)
    except ValueError:
        abort('TPCONF_duration is not an integer')

    try:
        for v in config.TPCONF_ECN:
            if v != '0' and v != '1':
                abort('TPCONF_ECN entries must be either \'0\' or \'1\'')
    except AttributeError:
        pass

    vnames_referenced = {}

    ids = {}
    entry = 1
    for c, v in config.TPCONF_router_queues:
        # insert all variable names used in vnames referenced
        v = re.sub(
            "(V_[a-zA-Z0-9_-]*)",
            "_reg_vname('\\1', vnames_referenced, 'TPCONF_router_queues entry %s')" %
            entry,
            v)
        eval('_args(%s)' % v)

        if c in ids:
            abort(
                'TPCONF_router_queues entry %s: reused id value %i' %
                (entry, c))

        ids[c] = 1
        entry += 1

    if len(config.TPCONF_traffic_gens) == 0:
        abort('TPCONF_traffic_gens must define at least one traffic generator')
    else:
        ids = {}
        entry = 1
        for t, c, v in config.TPCONF_traffic_gens:
            # insert all variable names used in vnames referenced
            v = re.sub(
                "(V_[a-zA-Z0-9_-]*)",
                "_reg_vname('\\1', vnames_referenced, 'TPCONF_traffic_gens entry %s')" %
                entry,
                v)
            eval('_args(%s)' % v)

            try:
                t = float(t)
            except ValueError:
                abort(
                    'TPCONF_traffic_gens entry %s: time is not a float' %
                    entry)

            try:
                c = int(c)
            except ValueError:
                abort(
                    'TPCONF_traffic_gens entry %s: id is not an inetger' %
                    entry)

            if c in ids:
                abort(
                    'TPCONF_traffic_gens entry %s: reused id value %i' %
                    (entry, c))

            ids[c] = 1
            entry += 1

    for k in config.TPCONF_vary_parameters:
        if k not in config.TPCONF_parameter_list:
            abort(
                'Parameter \'%s\' used in TPCONF_vary_parameters not defined in '
                'TPCONF_parameter_list' %
                k)

    vnames_defined = {}
    for k in config.TPCONF_parameter_list:
        names, short_names, val_list, extra = config.TPCONF_parameter_list[k]

        if len(names) < 1:
            abort(
                'Empty variable name list for parameter \'%s\' in TPCONF_parameter_list' %
                k)
        if len(short_names) < 1:
            abort(
                'Empty short name list for parameter \'%s\' in TPCONF_parameter_list' %
                k)
        if len(val_list) < 1:
            abort(
                'No parameter values for parameter \'%s\' in TPCONF_parameter_list' %
                k)
        if len(names) != len(short_names):
            abort(
                'Number of variable names and short names is not equal for parameter '
                '\'%s\' in TPCONF_parameter_list' %
                k)
        for name in names:
            if name[0:2] != 'V_':
                abort(
                    'Variable name does not start with V_ for parameter \'%k\' in '
                    'TPCONF_parameter_list' %
                    k)
            if name in vnames_defined:
                abort(
                    'Variable name \'%s\' defined twice in TPCONF_variable_list' %
                    name)
            vnames_defined[name] = 1

        val_set = {}
        for val in val_list:
            if len(names) == 1:
                # single values
                if str(val) == '':
                    abort('Empty value for parameter \'%s\'' % k)
            else:
                # tuples
                for c in range(len(val)):
                    if str(val[c]) == '':
                        abort('Empty value in tuple for parameter \'%s\'' % k)
   
            # lookup single values or tuples converted to strings
            val_str = str(val)
            if val_str in val_set:
                abort('Duplicate value \'%s\' for parameter \'%s\'' % (val_str, k))
 
            val_set[val_str] = 1

    for k in config.TPCONF_variable_defaults:
        if k not in vnames_defined:
            vnames_defined[k] = 1

    for k in vnames_referenced:
        if k not in vnames_defined:
            abort(
                'Variable name %s referenced in %s but not defined in '
                'TPCONF_parameter_list or TPCONF_variable_defaults' %
                (k, vnames_referenced[k]))

    try:
        config.TPCONF_debug_level
    except AttributeError:
        config.TPCONF_debug_level = 0

    puts('Config file looks OK')


# Check hosts for necessary tools (run in parallel on each host)
# Parameters:
@task
@parallel
def check_host():
    "Check that needed tools are installed on hosts"

    # get type of current host
    htype = get_type_cached(env.host_string)

    # run checks
    if env.host_string in config.TPCONF_router:
        if htype == 'FreeBSD':
            run('which ipfw')
        if htype == "Linux":
            run('which tc')
            run('which iptables')
        # XXX check that kernel tick rate is high (>= 1000)
    else:
        if htype == 'FreeBSD':
            run('which md5')
            run('which tcpdump')
        elif htype == 'Darwin':
            run('which md5')
            run('which tcpdump')
            run('which dsiftr-osx-teacup.d')
        elif htype == 'Linux':
            run('which ethtool')
            run('which md5sum')
            run('which tcpdump')
            #run('which web10g-listconns')
            #run('which web10g-readvars')
            run('which web10g-logger')
        elif htype == 'CYGWIN':
            run('which WinDump', pty=False)
            run('which win-estats-logger', pty=False)

	    # if we don't have proper ntp installed then
            # start time service if not started and force resync
            with settings(warn_only=True):
                ret = run('ls "/cygdrive/c/Program Files (x86)/NTP/bin/ntpq"')
                if ret.return_code != 0: 
                    run('net start w32time', pty=False)
                    run('w32tm /resync', pty=False)

            # try to enable any test network interfaces that are (accidently)
            # disabled after reboot
            with settings(warn_only=True):
                interfaces = get_netint_cached(env.host_string, int_no=-1)
                for interface in interfaces:
                    run('netsh int set int "Local Area Connection %s" enabled' %
                        interface, pty=False)

        run('which killall', pty=False)
        run('which pkill', pty=False)
        run('which ps', pty=False)
        run('which gzip', pty=False)
        run('which dd', pty=False)

        # check for traffic sender/receiver tools
        run('which iperf', pty=False)
        run('which ping', pty=False)
        run('which httperf', pty=False)
        run('which lighttpd', pty=False)
        run('which nttcp', pty=False)

    put(config.TPCONF_script_path + '/runbg_wrapper.sh', '/usr/bin')
    run('chmod a+x /usr/bin/runbg_wrapper.sh', pty=False)
    run('which runbg_wrapper.sh', pty=False)

    put(config.TPCONF_script_path + '/kill_iperf.sh', '/usr/bin')
    run('chmod a+x /usr/bin/kill_iperf.sh', pty=False)
    run('which kill_iperf.sh', pty=False)


# Check connectivity and also prime switch CAM table (run in parallel on each host)
# Parameters:
@task
@parallel
def check_connectivity():
    "Check connectivity between each pair of hosts with ping"

    # get type of current host
    htype = get_type_cached(env.host_string)

    all_hosts = config.TPCONF_router + config.TPCONF_hosts
    for host in all_hosts:
        for ihost in config.TPCONF_host_internal_ip[host]:
            if htype == "CYGWIN":
                run('ping -n 2 %s' % ihost, pty=False)
            else:
                run('ping -c 2 %s' % ihost, pty=False)


# Check time synchronisation with control machine (must not run in parallel!)
# This is only a simple check to detect if clocks are completely out of sync
# Assumes:
# - the control machine is synchronised (i.e. uses NTP)
# Parameters:
@task
def check_time_sync():
    "Check time synchronisation between control host and testbed host clocks"

    allowed_time_diff = 1
    try:
        allowed_time_diff = config.TPCONF_max_time_diff
    except AttributeError:
        pass

    # get type of current host
    htype = get_type_cached(env.host_string)

    # get timestamps in unix time to avoid having to do time format conversions

    t1 = datetime.datetime.now()
    if htype == 'FreeBSD' or htype == 'Linux' or htype == 'Darwin':
        rdate = run('date +\'%s\'')
    elif htype == 'CYGWIN':
        rdate = run('date +\'%s\'', pty=False)

    ldate = local('date +\'%s\'', capture=True)
    t2 = datetime.datetime.now()

    dt_diff = t2 - t1
    sec_diff = (dt_diff.days * 24 * 3600 + dt_diff.seconds) + \
        (dt_diff.microseconds / 1000000.0)

    puts(
        'Local time: %s, remote time: %s, proc delay: %s' %
        (ldate, rdate, str(sec_diff)))

    diff = abs(int(ldate) - int(rdate) - sec_diff)
    if diff > allowed_time_diff:
        abort(
            'Host %s time synchronisation error (difference > %s seconds)' %
            (env.host_string, str(allowed_time_diff)))


# Kill any old processes (run on parallel on each host)
# Parameters:
@task
@parallel
def kill_old_processes():
    "Kill old logging or traffic generation processes still running"

    # get type of current host
    htype = get_type_cached(env.host_string)

    with settings(warn_only=True):
        if htype == 'FreeBSD':
            run('killall tcpdump', pty=False)
        elif htype == 'Linux':
            run('killall tcpdump', pty=False)
            #run('killall web10g_logger.sh')
            run('killall web10g-logger')
        elif htype == 'Darwin':
            run('killall tcpdump', pty=False)
            run('killall dsiftr-osx-teacup.d', pty=False)
        elif htype == 'CYGWIN':
            run('killall WinDump', pty=False)
            run('killall win-estats-logger', pty=False)

        if htype == 'CYGWIN':
            # on new cygwin does stop anymore on sigterm
            run('killall -9 iperf', pty=False)
        else:
            run('killall iperf', pty=False)
        run('killall ping', pty=False)
        run('killall httperf', pty=False)
        run('killall lighttpd', pty=False)
        # delete old lighttp pid files (XXX would be better to delete after
        # experiment)
        run('rm -f /var/run/*lighttpd.pid', pty=False)
        run('killall runbg_wrapper.sh', pty=False)
        run('killall nttcp')

    # remove old log stuff in /tmp
    run('rm -f /tmp/*.log', pty=False)


# Collect host info, prefill caches
# this must not be run in parallel!!!
# any parallel task cannot fill the caches cause the parallel execution
# is done with fork()
# Parameters:
#	htype: '0' don't get host OS, '1' get host OS
#	netint: '0' don't get network interface names,
#               '1' get network interface names
#	netmac: '0' don't get MAC addresses, '1' get MAC addresses
#@task
@serial
def get_host_info(htype='1', netint='1', netmac='1'):
    "Populate the host info caches"

    if htype == '1':
        get_type_cached(env.host_string)
    if netint == '1':
        get_netint_cached(env.host_string, int_no=-1)
        get_netint_windump_cached(env.host_string, int_no=-1)
	get_netint_cached(env.host_string, int_no=-1, internal_int='0')
        get_netint_windump_cached(env.host_string, int_no=-1, 
                                  internal_int='0')
    if netmac == '1':
        get_netmac_cached(env.host_string)


# Run all sanity checks
# Parameters:
@task
def sanity_checks():
    "Perform all sanity checks, e.g. check for needed tools and connectivity"

    execute(check_host, hosts=config.TPCONF_router + config.TPCONF_hosts)
    execute(
        check_connectivity,
        hosts=config.TPCONF_router +
        config.TPCONF_hosts)
    execute(
        kill_old_processes,
        hosts=config.TPCONF_router +
        config.TPCONF_hosts)
    execute(check_time_sync, hosts=config.TPCONF_router + config.TPCONF_hosts)
