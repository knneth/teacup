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
## @package experiment
# Run a single experiment
#
# $Id: experiment.py 1313 2015-05-05 05:58:01Z szander $

import time
import datetime
import re
import socket
from fabric.api import task, warn, put, puts, get, local, run, execute, \
    settings, abort, hosts, env, runs_once, parallel
from fabric.network import disconnect_all

import config
from internalutil import mkdir_p
from bgproc import file_cleanup, print_proc_list
from runbg import stop_processes
from hosttype import get_type_cached, get_type, clear_type_cache
from hostint import get_netint_cached, get_netint
from sanitychecks import check_config, check_host, check_connectivity, \
    kill_old_processes, sanity_checks, get_host_info
from hostsetup import init_host, init_ecn, init_cc_algo, init_router, \
    init_hosts, init_os_hosts, init_host_custom, init_topology_switch, \
    init_topology_host 
from loggers import start_tcpdump, stop_tcpdump, start_tcp_logger, \
    stop_tcp_logger, start_loggers, log_sysdata, log_queue_stats, \
    log_config_params, log_host_tcp, start_bc_ping_loggers
from routersetup import init_pipe, show_pipes
from trafficgens import start_iperf, start_ping, \
    start_http_server, start_httperf, \
    start_httperf_dash, create_http_dash_content, \
    create_http_incast_content, start_httperf_incast, \
    start_nttcp, start_bc_ping, \
    start_httperf_incast_n, start_fps_game


## Collect all the arguments
#  @param _nargs Arguments
#  @param kwargs Keyword arguments
def _args(*_nargs, **_kwargs):
    "Collect parameters for a call"
    return _nargs, _kwargs


## Function to replace the variable names with the values
#  @param name Name of variable
#  @param adict Dictionary to lookup
def _param(name, adict):
    "Get parameter value"
    val = adict.get(name, '')
    if val == '':
        warn('Parameter %s is undefined' % name)

    return val


## Function to compare the time keys of the traffic generator list
## Used for sorting the list in ascending order
#  @param x First entry 
#  @param y Second entry 
def _cmp_timekeys(x, y):
    "Compare for time keys"
    xtime = x[0]
    ytime = y[0]

    try:
        xtime = float(xtime)
        ytime = float(ytime)
    except ValueError:
        abort("Time is not a float")

    return cmp(xtime, ytime)


## configure queues on one router
#  @param queue_spec Queue specification from config file 
#  @param router Router host
#  @param kwargs Keyword argument dictionary
def config_router_queues(queue_spec, router, **kwargs):

    for c, v in queue_spec:
        # add the kwargs parameter to the call of _param
        v = re.sub("(V_[a-zA-Z0-9_-]*)", "_param('\\1', kwargs)", v)

        # trim white space at both ends
        v = v.strip()

        # prepend the task name
        v = 'init_pipe, "' + str(c) + '", ' + v

        # append the host to execute (router)
        if v[-1] != ',':
            v = v + ','
        v = v + ' hosts = router'

        _nargs, _kwargs = eval('_args(%s)' % v)
        execute(*_nargs, **_kwargs)


## Run experiment
#  @param test_id Experiment ID
#  @param test_id_pfx Experiment ID prefix
#  @param args Arguments
#  @param kwargs Keyword arguments
def run_experiment(test_id='', test_id_pfx='', *args, **kwargs):

    do_init_os = kwargs.get('do_init_os', '1')
    ecn = kwargs.get('ecn', '0')
    tcp_cc_algo = kwargs.get('tcp_cc_algo', 'default')
    duration = kwargs.get('duration', '')
    if duration == '':
        abort('No experiment duration specified')

    # create sub directory for test id prefix
    mkdir_p(test_id_pfx)

    # log experiment in started list
    local('echo "%s" >> experiments_started.txt' % test_id)

    puts('\n[MAIN] Starting experiment %s \n' % test_id)

    tftpboot_dir = ''
    try:
        tftpboot_dir = config.TPCONF_tftpboot_dir
    except AttributeError:
        pass

    # initialise
    if tftpboot_dir != '' and do_init_os == '1':
        execute(
            get_host_info,
            netint='0',
            hosts=config.TPCONF_router +
            config.TPCONF_hosts)
        execute(
            init_os_hosts,
            file_prefix=test_id_pfx,
            local_dir=test_id_pfx)  # reboot
        clear_type_cache()  # clear host type cache
        disconnect_all()  # close all connections
        time.sleep(30)  # give hosts some time to settle down (after reboot)

    # initialise topology
    try:
        switch = '' 
        port_prefix = ''
        port_offset = 0
        try:
            switch = config.TPCONF_topology_switch
            port_prefix = config.TPCONF_topology_switch_port_prefix
            port_offset = config.TPCONF_topology_switch_port_offset
        except AttributeError:
            pass 

        if config.TPCONF_config_topology == '1' and do_init_os == '1' and  \
           not len(config.TPCONF_router) > 1:
            # we cannot call init_topology directly, as it is decorated with
            # runs_once. in experiment.py we have empty host list whereas if we
            # run init_topology from command line we have the -H host list. executing
            # an runs_once task with empty host list (hosts set in execute call), it
            # will only be executed for the first host, which is not what we
            # want. in contrast if we have a host list in context, execute will be
            # executed once for each host (hence we need runs_once when called from
            # the command line).

            # sequentially configure switch
            execute(init_topology_switch, switch, port_prefix, port_offset,
                   hosts = config.TPCONF_hosts)
            # configure hosts in parallel
            execute(init_topology_host, hosts = config.TPCONF_hosts)

    except AttributeError:
        pass

    file_cleanup(test_id_pfx)  # remove any .start files
    execute(
        get_host_info,
        netmac='0',
        hosts=config.TPCONF_router +
        config.TPCONF_hosts)
    execute(sanity_checks)
    execute(init_hosts, *args, **kwargs)

    # first is the legacy case with single router and single queue definitions
    # second is the multiple router case with several routers and several queue
    # definitions 
    if isinstance(config.TPCONF_router_queues, list):
        # start queues/pipes
        config_router_queues(config.TPCONF_router_queues, config.TPCONF_router, 
                             **kwargs)
        # show pipe setup
        execute(show_pipes, hosts=config.TPCONF_router)
    elif isinstance(config.TPCONF_router_queues, dict):
        for router in config.TPCONF_router_queues.keys():
            # start queues/pipes for router r
            config_router_queues(config.TPCONF_router_queues[router], [router], 
                                 **kwargs)
            # show pipe setup
            execute(show_pipes, hosts=[router])

    # log config parameters
    execute(
        log_config_params,
        file_prefix=test_id,
        local_dir=test_id_pfx,
        hosts=['MAIN'],
        *args,
        **kwargs)
    # log host tcp settings
    execute(
        log_host_tcp,
        file_prefix=test_id,
        local_dir=test_id_pfx,
        hosts=['MAIN'],
        *args,
        **kwargs)

    # start all loggers
    execute(
        start_loggers,
        file_prefix=test_id,
        local_dir=test_id_pfx,
        remote_dir=config.TPCONF_remote_dir)

    # Start broadcast ping and loggers (if enabled)
    try: 
        if config.TPCONF_bc_ping_enable == '1':
            # for multicast need IP of outgoing interface
            # which is router's control interface
            use_multicast = socket.gethostbyname(
                    config.TPCONF_router[0].split(':')[0])
 
            # get configured broadcast or multicast address
            bc_addr = '' 
            try:
                bc_addr = config.TPCONF_bc_ping_address
            except AttributeError:
                # use default multicast address
                bc_addr = '224.0.1.199'

            execute(
                start_bc_ping_loggers,
                file_prefix=test_id,
                local_dir=test_id_pfx,
                remote_dir=config.TPCONF_remote_dir,
                bc_addr=bc_addr)

            try:
                bc_ping_rate = config.TPCONF_bc_ping_rate
            except AttributeError:
                bc_ping_rate = '1'

            # start the broadcst ping on the first router
            execute(start_bc_ping,
                file_prefix=test_id,
                local_dir=test_id_pfx,
                remote_dir=config.TPCONF_remote_dir,
                bc_addr=bc_addr,
                rate=bc_ping_rate,
                use_multicast=use_multicast,
                hosts = [config.TPCONF_router[0]])
    except AttributeError:
        pass

    # start traffic generators
    sync_delay = 5.0
    max_wait_time = sync_delay
    start_time = datetime.datetime.now()
    for t, c, v in sorted(config.TPCONF_traffic_gens, cmp=_cmp_timekeys):

        try:
            # delay everything to have synchronised start
            next_time = float(t) + sync_delay
        except ValueError:
            abort('Traffic generator entry key time must be a float')

        if next_time > max_wait_time:
            max_wait_time = next_time

        # add the kwargs parameter to the call of _param
        v = re.sub("(V_[a-zA-Z0-9_-]*)", "_param('\\1', kwargs)", v)

        # trim white space at both ends
        v = v.strip()

        if v[-1] != ',':
            v = v + ','
        # add counter parameter
        v += ' counter="%s"' % c
        # add file prefix parameter
        v += ', file_prefix=test_id'
        # add remote dir
        v += ', remote_dir=\'%s\'' % config.TPCONF_remote_dir
        # add test id prefix to put files into correct directory
        v += ', local_dir=\'%s\'' % test_id_pfx
        # we don't need to check for presence of tools inside start functions
        v += ', check="0"'

        # set wait time until process is started
        now = datetime.datetime.now()
        dt_diff = now - start_time
        sec_diff = (dt_diff.days * 24 * 3600 + dt_diff.seconds) + \
            (dt_diff.microseconds / 1000000.0)
        if next_time - sec_diff > 0:
            wait = str(next_time - sec_diff)
        else:
            wait = '0.0'
        v += ', wait="' + wait + '"'

        _nargs, _kwargs = eval('_args(%s)' % v)
        execute(*_nargs, **_kwargs)

    # print process list
    print_proc_list()

    # wait until finished (add additional 5 seconds to be sure)
    total_duration = float(duration) + max_wait_time + 5.0
    puts('\n[MAIN] Running experiment for %i seconds\n' % int(total_duration))
    time.sleep(total_duration)

    # shut everything down and get log data
    execute(stop_processes, local_dir=test_id_pfx)
    execute(
        log_queue_stats,
        file_prefix=test_id,
        local_dir=test_id_pfx,
        hosts=config.TPCONF_router)

    # log test id in completed list
    local('echo "%s" >> experiments_completed.txt' % test_id)

    # kill any remaining processes
    execute(kill_old_processes,
            hosts=config.TPCONF_router +
            config.TPCONF_hosts)

    # done
    puts('\n[MAIN] COMPLETED experiment %s \n' % test_id)
