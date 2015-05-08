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
# fabfile
#
# $Id: fabfile.py 1012 2015-02-20 07:21:57Z szander $

import datetime
from fabric.api import execute, task

# this will print paramiko errors on stderr
import logging
logging.getLogger('paramiko.transport').addHandler(logging.StreamHandler())

import config
from experiment import run_experiment
from hosttype import get_type
from hostint import get_netint
from hostmac import get_netmac
from sanitychecks import check_host, check_connectivity, kill_old_processes, \
    sanity_checks, get_host_info, check_config, check_time_sync
from hostsetup import init_host, init_ecn, init_cc_algo, init_router, \
    init_hosts, init_os, power_cycle, init_host_custom, init_topology
from loggers import start_tcpdump, stop_tcpdump, start_tcp_logger, \
    stop_tcp_logger, start_dummynet_logger, stop_dummynet_logger, start_loggers, \
    log_sysdata, log_queue_stats, log_config_params, log_host_tcp
from routersetup import init_pipe, show_pipes
from trafficgens import start_iperf, stop_iperf, start_ping, stop_ping, \
    start_http_server, stop_http_server, start_httperf, stop_httperf, \
    start_httperf_dash, stop_httperf_dash, create_http_dash_content, \
    create_http_incast_content, start_httperf_incast, \
    stop_httperf_incast, start_httperf_incast_n
from analyse import analyse_rtt, analyse_cwnd, analyse_tcp_rtt, \
    analyse_throughput, analyse_all, analyse_dash_goodput, analyse_tcp_stat, \
    analyse_cmpexp, analyse_incast, extract_rtt, extract_cwnd, extract_tcp_rtt, \
    extract_throughput, extract_all, extract_dash_goodput, extract_tcp_stat, \
    extract_incast, analyse_ackseq, analyse_2d_density, extract_ackseq
from util import exec_cmd, authorize_key, copy_file
from clockoffset import get_clock_offsets, adjust_timestamps

# set to zero if we don't need OS initialisation anymore
# XXX this is a bit ugly as a global
do_init_os = '1'

# list of experiment completed (from experiments_completed.txt)
experiments_done = {}


# sets all basic parameters not yet set to single values
def _fill_missing(*nargs, **kwargs):

    global do_init_os

    for k, v in config.TPCONF_variable_defaults.items():
        if k not in kwargs:
            kwargs[k] = v

    # for compatibility with internal parameters
    if 'V_ecn' in kwargs:
    	kwargs['ecn'] = kwargs['V_ecn']
    if 'V_tcp_cc_algo' in kwargs:
        kwargs['tcp_cc_algo'] = kwargs['V_tcp_cc_algo']
    kwargs['duration'] = kwargs['V_duration']

    # set special defaults
    if 'run' not in kwargs:
        kwargs['run'] = 0
    if 'do_init_os' not in kwargs:
        kwargs['do_init_os'] = do_init_os

    return nargs, kwargs


# check if experiment test_id has been done before based on
# experiments_completed.txt file
def _experiment_done(test_id=''):
    global experiments_done

    if len(experiments_done) == 0:
        try:
            with open('experiments_completed.txt') as f:
                experiments = f.readlines()

            for experiment in experiments:
                experiments_done[experiment.strip()] = 1
        except IOError:
            # don't care if experiments_completed.txt does not exist, it
            # will be created after the next experiment
            pass

    if experiments_done.get(test_id, 0) == 0:
        return False
    else:
        return True


# Run single experiment
# Parameters:
#	test_id: test ID prefix
#	nargs, kwargs: various parameters
@task
def run_experiment_single(test_id='', *nargs, **kwargs):
    "Run a single experiment"

    if test_id == '':
        test_id = config.TPCONF_test_id

    execute(check_config, hosts=['MAIN'])  # use a dummy host here

    _nargs, _kwargs = _fill_missing(*nargs, **kwargs)
    execute(run_experiment, test_id, test_id, *_nargs, **_kwargs)


# Generic function for varying a parameter
# Parameters:
#	test_id: test ID
#	test_id_pfx: test ID prefix
#	resume: '0' do all experiment, '1' do not repeat experiment if done according
#               to experiments_completed.txt
#	var_list: list of parameters to vary
#	names: list of variable names corrsponding to parameters
#	short_names: list of short names used in file names corrsponding to parameters
#	val_list: list of variable values corrsponding to parameters
#	extra_params: extra variables we need to set
#	nargs, kwargs: variables we set and finally pass to run_experiment
def _generic_var(test_id='', test_id_pfx='', resume='0', var_list=[], names=[
], short_names=[], val_list=[], extra_params={}, *nargs, **kwargs):

    global do_init_os

    # set if not set yet
    if test_id == '':
        test_id = config.TPCONF_test_id
    if test_id_pfx == '':
        test_id_pfx = test_id

    # remove current variable
    var_list.pop(0)

    for k, v in extra_params.items():
        kwargs[k] = v

    for val in val_list:
        if len(names) == 1:
            # add parameter and parameter value to test_id
            _test_id = test_id + '_' + \
                short_names[0] + '_' + str(val).replace('_', '-')
            # push value on parameter list
            kwargs[names[0]] = val
        else:
            _test_id = test_id
            c = 0
            for name in names:
                # add parameter and parameter value to test_id
                _test_id = _test_id + '_' + \
                    short_names[c] + '_' + str(val[c]).replace('_', '-')
                # push value on parameter list
                kwargs[name] = val[c]
                c += 1

        if len(var_list) > 0:
            # if we have another parameter to vary call the appropriate
            # function
            next_var = var_list[0]
            _names, _short_names, _val_list, _extra_params = config.TPCONF_parameter_list[
                next_var]
            # important that we pass a copy of var_list here and not a
            # reference
            _generic_var(
                _test_id,
                test_id_pfx,
                resume,
                list(var_list),
                _names,
                _short_names,
                _val_list,
                _extra_params,
                *nargs,
                **kwargs)
        else:
            # else fill in any missing parameters and start experiment
            _nargs, _kwargs = _fill_missing(*nargs, **kwargs)
            if resume == '0' or not _experiment_done(_test_id):
                #print('run', _test_id, _nargs, _kwargs)
                execute(
                    run_experiment,
                    _test_id,
                    test_id_pfx,
                    *_nargs,
                    **_kwargs)
                do_init_os = '0'


# This is the enrty point when we want to a series of experiments varying
# different things
# Parameters:
#       test_id: test ID prefix
#       resume: '0' do all experiment, '1' do not repeat experiment if done
#               according to experiments_completed.txt
#       nargs, kwargs: various parameters
@task
def run_experiment_multiple(test_id='', resume='0', *nargs, **kwargs):
    "Run series of experiments"

    if test_id == '':
        test_id = config.TPCONF_test_id

    execute(check_config, hosts=['MAIN'])  # use a dummy host here

    var_list = config.TPCONF_vary_parameters

    if len(var_list) > 0:
        # if we have another parameter to vary call the appropriate function
        next_var = var_list[0]
        names, short_names, val_list, extra_params = config.TPCONF_parameter_list[
            next_var]
        # important that we pass a copy of var_list here and not a reference
        _generic_var(
            test_id,
            test_id,
            resume,
            list(var_list),
            names,
            short_names,
            val_list,
            extra_params,
            *nargs,
            **kwargs)
    else:
        # else fill in any missing parameters and start experiment
        _nargs, _kwargs = _fill_missing(*nargs, **kwargs)
        if resume == '0' or not _experiment_done(test_id):
            #print('run', test_id, _nargs, _kwargs)
            execute(run_experiment, test_id, test_id, *_nargs, **_kwargs)
            do_init_os = '0'
