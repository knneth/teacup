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
## @package trafficgens
# Traffic generators
#
# $Id: trafficgens.py 1314 2015-05-05 06:50:00Z szander $

import time
import random
from fabric.api import task, warn, put, local, run, execute, abort, hosts, \
    env, settings
import bgproc
import config
from hosttype import get_type_cached
from hostint import get_address_pair
from getfile import getfile
from runbg import runbg


#
# nttcp
#

## Start nttcp server (UDP only)
#  @param counter Unique ID
#  @param file_prefix File prefix for log file (nttcp server output)
#  @param remote_dir Directory to create log file in
#  @param port Listen on this port
#  @param srv_host Bind to interface with this address
#  @param buf_size Size of send buffer
#  @param extra_params Extra params to be set
#  @param check '0' don't check for nttcp executable,
#               '1' check for nttcp executable
#  @param wait Time to wait before process is started
def start_nttcp_server(counter='1', file_prefix='', remote_dir='',
                       port='', srv_host='', buf_size='', extra_params='',
                       check='1', wait=''):
    if port == '':
        abort('Must specify port')
    if srv_host == '':
        abort('Must specify server host')

    if check == '1':
        # make sure we have executable
        run('which nttcp', pty=False)

    # start nttcp
    logfile = remote_dir + file_prefix + '_' + \
        env.host_string.replace(':', '_') + '_' + counter + '_nttcp.log'
    nttcp_cmd = 'nttcp -i -p %s -u -v' % port
    if buf_size != '':
        nttcp_cmd += ' -w %s' % buf_size  # can only set send buffer
    if extra_params != '':
        nttcp_cmd += ' ' + extra_params
    pid = runbg(nttcp_cmd, wait, out_file=logfile)
    bgproc.register_proc(env.host_string, 'nttcp', counter, pid, logfile)


## Start nttcp client (UDP only)
#  @param counter Unique ID
#  @param file_prefix File prefix for log file (nttcp client output)
#  @param remote_dir Directory to create log file in
#  @param port Listen on this port
#  @param srv_host Bind to interface with this address
#  @param duration Duration in seconds
#  @param interval Packet interval in milliseconds
#  @param psize Size of the UDP payload (excluding IP/UDP header) in bytes
#  @param buf_size Size of send buffer
#  @param extra_params Extra params to be set
#  @param check '0' don't check for nttcp executable,
#               '1' check for nttcp executable
#  @param wait Time to wait before process is started
def start_nttcp_client(counter='1', file_prefix='', remote_dir='', port='',
                       srv_host='', duration='', interval='1000', psize='100',
                       buf_size='', extra_params='', check='1', wait=''):

    if port == '':
        abort('Must specify port')
    if srv_host == '':
        abort('Must specify server host')
    if duration == '':
        abort('Must specify duration')

    if check == '1':
        # make sure we have nttcp
        run('which nttcp', pty=False)

    # start nttcp
    # number of bufs to send
    bufs = str(int(float(duration) / (float(interval) / 1000.0)))
    gap = str(int(interval) * 1000)  # gap in microseconds
    logfile = remote_dir + file_prefix + '_' + \
        env.host_string.replace(':', '_') + '_' + counter + '_nttcp.log'
    nttcp_cmd = 'nttcp -g %s -l %s -n %s -p %s -u -t -T -v' % (
        gap, psize, bufs, port)
    if buf_size != '':
        nttcp_cmd += ' -w %s' % buf_size  # can only set send buffer
    if extra_params != '':
        nttcp_cmd += ' ' + extra_params
    nttcp_cmd += ' %s' % srv_host
    pid = runbg(nttcp_cmd, wait, out_file=logfile)
    bgproc.register_proc(env.host_string, 'nttcp', counter, pid, logfile)


## Start nttcp sender and receiver
## For parameters see start_nttcp_client() and start_nttcp_server()
def start_nttcp(counter='1', file_prefix='', remote_dir='', local_dir='',
                port='', client='', server='', duration='', interval='', psize='',
                buf_size='', extra_params_client='', extra_params_server='',
                check='1', wait=''):
    "Start nttcp traffic sender and receiver"

    server, server_internal = get_address_pair(server)
    client, dummy = get_address_pair(client)
    execute(start_nttcp_server, counter, file_prefix, remote_dir, port,
            server_internal, buf_size, extra_params_server,
            check, wait, hosts=[server])
    execute(start_nttcp_client, counter, file_prefix, remote_dir, port,
            server_internal, duration, interval, psize, buf_size,
            extra_params_client, check, wait, hosts=[client])


#
# iperf
#

## Start iperf server
#  @param counter Unique ID
#  @param file_prefix File prefix for log file (iperf server output)
#  @param remote_dir Directory to create log file in
#  @param port Listen on this port
#  @param srv_host Bind to interface with this address
#  @param duration Duration in seconds (only used if kill='1')
#  @param mss Maximum segment size
#  @param buf_size Size of send and receive buffer
#                  (assumes iperf modified with CAIA patch)
#  @param proto Must be 'tcp' or 'udp'
#  @param extra_params Extra params to be set
#  @param check '0' don't check for iperf executable, '1' check for iperf executable
#  @param wait Time to wait before process is started
#  @param kill If '0' server will terminate according to duration (default),
#              if '1' kill server after duration to work around
#              "feature" in iperf that prevents it from stopping after duration
def start_iperf_server(counter='1', file_prefix='', remote_dir='', port='',
                       srv_host='', duration='', mss='', buf_size='', proto='tcp',
                       extra_params='', check='1', wait='', kill='0'):
    if port == '':
        abort('Must specify port')
    if srv_host == '':
        abort('Must specify server host')
    if proto != 'tcp' and proto != 'udp':
        abort("Protocol must be 'tcp' or 'udp'")

    if check == '1':
        # make sure we have iperf
        run('which iperf', pty=False)

    # start iperf
    logfile = remote_dir + file_prefix + '_' + \
        env.host_string.replace(':', '_') + '_' + counter + '_iperf.log'
    iperf_cmd = 'iperf -i 1 -s -p %s -B %s' % (port, srv_host)
    if proto == 'udp':
        iperf_cmd += ' -u'
    if mss != '':
        iperf_cmd += ' -M %s' % mss
    if buf_size != '':
        # only for CAIA patched iperf
        iperf_cmd += ' -j %s -k %s' % (buf_size, buf_size)
    if extra_params != '':
        iperf_cmd += ' ' + extra_params
    pid = runbg(iperf_cmd, wait, out_file=logfile)

    bgproc.register_proc(env.host_string, 'iperf', counter, pid, logfile)

    if kill == '1':
        if duration == '':
            abort("If kill is set to '1', duration must be specified")

        # kill iperf server (send SIGTERM first, then SIGKILL after 1 second)
        kill_cmd = 'kill_iperf.sh %s' % pid
        # do this shortly after iperf client is expected to finish
        wait = str(float(wait) + float(duration) + 2.0)
        pid = runbg(kill_cmd, wait)

        bgproc.register_proc(env.host_string, 'kill_iperf', counter, pid, '')


## Start iperf client
#  @param counter Unique ID
#  @param file_prefix File prefix for log file (iperf server output)
#  @param remote_dir Directory to create log file in
#  @param port Listen on this port
#  @param srv_host Bind to interface with this address
#  @param duration Duration in seconds
#  @param congestion_algo Congestion control algo to use (Linux only!)
#  @param mss Maximum segment size
#  @param buf_size Size of send and receive buffer
#                  (assumes iperf modified with CAIA patch)
#  @param proto Must be 'tcp' or 'udp'
#  @param bandw Bandwidth in n[KM] (K for kilo, M for mega)
#  @param extra_params Extra params to be set
#  @param check '0' don't check for iperf executable,
#               '1' check for iperf executable
#  @param wait Time to wait before process is started
#  @param kill If '0' client will terminate according to duration (default),
#              if '1' kill client after duration to work around
#              "feature" in iperf that prevents it from stopping after duration
def start_iperf_client(counter='1', file_prefix='', remote_dir='', port='',
                       srv_host='', duration='', congestion_algo='', mss='',
                       buf_size='', proto='tcp', bandw='', extra_params='',
                       check='1', wait='', kill='0'):

    if port == '':
        abort('Must specify port')
    if srv_host == '':
        abort('Must specify server host')
    if proto != 'tcp' and proto != 'udp':
        abort("Protocol must be 'tcp' or 'udp'")

    if check == '1':
        # make sure we have iperf
        run('which iperf', pty=False)

    # start iperf
    logfile = remote_dir + file_prefix + '_' + \
        env.host_string.replace(':', '_') + '_' + counter + '_iperf.log'
    iperf_cmd = 'iperf -i 1 -c %s -p %s -t %s' % (srv_host, port, duration)
    if proto == 'udp':
        iperf_cmd += ' -u'
        if bandw != '':
            iperf_cmd += ' -b %s' % bandw
    else:
        if bandw != '':
            # note that this option does not exist in older iperf versions!
            iperf_cmd += ' -a %s' % bandw
        if congestion_algo != '':
            iperf_cmd += ' -Z %s' % congestion_algo
        if mss != '':
            iperf_cmd += ' -M %s' % mss
    if buf_size != '':
        # only for CAIA patched iperf
        iperf_cmd += ' -j %s -k %s' % (buf_size, buf_size)
    if extra_params != '':
        iperf_cmd += ' ' + extra_params
    pid = runbg(iperf_cmd, wait, out_file=logfile)

    bgproc.register_proc(env.host_string, 'iperf', counter, pid, logfile)

    if kill == '1':
        if duration == '':
            abort("If kill is set to '1', duration must be specified")

        # kill iperf client (send SIGTERM first, then SIGKILL after 1 second)
        kill_cmd = 'kill_iperf.sh %s' % pid
        # do this shortly after iperf client is expected to finish
        wait = str(float(wait) + float(duration) + 1.0)
        pid = runbg(kill_cmd, wait)

        bgproc.register_proc(env.host_string, 'kill_iperf', counter, pid, '')


## Start iperf sender and receiver
## For parameters see start_iperf_client() and start_iperf_server()
def start_iperf(counter='1', file_prefix='', remote_dir='', local_dir='',
                port='', client='', server='', duration='', congestion_algo='',
                mss='', buf_size='', proto='tcp', rate='', extra_params_client='',
                extra_params_server='', check='1', wait='', kill='0'):
    "Start iperf traffic sender and receiver"

    server, server_internal = get_address_pair(server)
    client, dummy = get_address_pair(client)
    execute(start_iperf_server, counter, file_prefix, remote_dir, port,
            server_internal, duration, mss, buf_size, proto, extra_params_server,
            check, wait, kill, hosts=[server])
    execute(start_iperf_client, counter, file_prefix, remote_dir, port,
            server_internal, duration, congestion_algo, mss, buf_size,
            proto, rate, extra_params_client, check, wait, kill, hosts=[client])


#
# ping
#

## Start ping
#  @param counter Unique ID
#  @param file_prefix File prefix for log file (iperf server output)
#  @param remote_dir Directory to create log file in
#  @param dest Target to ping
#  @param duration Duration in seconds
#  @param rate Number of pings per second
#  @param extra_params Other parameters passed directly to ping
#  @param check: '0' don't check for ping executable, '1' check for ping executable
#  @param wait: time to wait before process is started
def _start_ping(counter='1', file_prefix='', remote_dir='', dest='',
                duration='', rate='1', extra_params='', check='1', wait=''):

    if check == '1':
        # make sure we have ping
        run('which ping', pty=False)

    # get host type
    htype = get_type_cached(env.host_string)

    logfile = remote_dir + file_prefix + '_' + \
        env.host_string.replace(':', '_') + '_' + counter + '_ping.log'
    if htype == 'CYGWIN':
        ping_cmd = 'ping -n %s' % duration
        # windows ping does not support setting the rate
        if rate != '1':
            warn(
                'windows ping does not support setting the rate, using rate=1')
    else:
        count = str(int(round(float(duration) * float(rate), 0)))
        ping_cmd = 'ping -c %s' % count
        if rate != '1':
            interval = str(round(1 / float(rate), 3))
            ping_cmd += ' -i %s' % interval

    if extra_params != '':
        ping_cmd += ' ' + extra_params

    ping_cmd += ' %s' % dest
    pid = runbg(ping_cmd, wait, out_file=logfile)
    bgproc.register_proc(env.host_string, 'ping', counter, pid, logfile)


## Start ping wrapper
#  @param counter Unique ID
#  @param file_prefix File prefix for log file (iperf server output)
#  @param remote_dir Directory to create log file in
#  @param local_dir Unused
#  @param client Host to run ping on
#  @param dest Target to ping
#  @param duration Duration in seconds
#  @param rate Number of pings per second
#  @param extra_params Other parameters passed directly to ping
#  @param check: '0' don't check for ping executable, '1' check for ping executable
#  @param wait: time to wait before process is started
def start_ping(counter='1', file_prefix='', remote_dir='', local_dir='',
               client='', dest='', duration='', rate='1', extra_params='',
               check='1', wait=''):
    "Start ping"

    if client == '':
        abort('Must specify client')
    if dest == "":
        abort("Must specify destination")

    client, dummy = get_address_pair(client)
    dummy, dest_internal = get_address_pair(dest)
    execute(
        _start_ping,
        counter,
        file_prefix,
        remote_dir,
        dest_internal,
        duration,
        rate,
        extra_params,
        check,
        wait,
        hosts=[client])


#
# httperf
#


## Return default document root depending on host OS
#  @param htype Host type string
def _get_document_root(htype):
    if htype == 'FreeBSD':
        docroot = '/usr/local/www/data'
    elif htype == 'Darwin':
        docroot = '/opt/local/www/htdocs'
    else:
        docroot = '/srv/www/htdocs'

    return docroot


## Start lighttpd web server
#  @param counter Unique ID
#  @param file_prefix File prefix for log file (iperf server output)
#  @param remote_dir Directory to create log file in
#  @param local_dir Local directory to put files in
#  @param port Port to listen to
#  @param config_dir Directory that contains config file
#  @param config_in Config file template to use
#  @param docroot Document root on server
#  @param check If '0' don't check for lighttpd executable, if '1' check for 
#               lighttpd executable
#  @param wait: time to wait before process is started
def _start_http_server(counter='1', file_prefix='', remote_dir='',
                       local_dir='', port='', config_dir='', config_in='',
                       docroot='', check='1'):
    global config

    if port == "":
        abort("Must specify port")

    if check == '1':
             # make sure we have lighttpd
        run('which lighttpd', pty=False)

    # get host type
    htype = get_type_cached(env.host_string)

    # automatic config if not specified explicitely
    if config_dir == '':
        if htype == 'FreeBSD':
            config_dir = '/usr/local/etc/lighttpd'
        elif htype == 'Darwin':
            config_dir = '/opt/local/etc/lighttpd'
        else:
            config_dir = '/etc/lighttpd'
    if config_in == '':
        config_in = config.TPCONF_script_path + \
            '/lighttpd_' + htype + '.conf.in'
    if docroot == '':
        docroot = _get_document_root(htype)

    # start server
    logfile = file_prefix + "_" + \
        env.host_string.replace(':', '_') + "_" + counter + "_access.log"
    # XXX currently we overwrite the main config file if we start multiple
    # servers
    config_file_remote = config_dir + '/lighttpd.conf'
    config_file = local_dir + '/' + file_prefix + '_' + \
        env.host_string.replace(':', '_') + '_' + counter + '_lighttpd.conf'
    docroot_sed = docroot.replace("/", "\/")
    pid_file = '/' + file_prefix + '_' + \
        env.host_string.replace(':', '_') + '_' + counter + '_lighttpd.pid'
    pid_file_sed = pid_file.replace("/", "\/")
    local('cat %s | sed -e "s/@SERVER_PORT@/%s/" | sed -e "s/@DOCUMENT_ROOT@/%s/" | '
          'sed -e "s/@ACCESS_LOG_NAME@/%s/" | sed -e "s/@PID_FILE@/%s/" > %s'
          % (config_in, port, docroot_sed, logfile, pid_file_sed, config_file))

    logdir = local(
        'cat %s | egrep "^var.log_root"' %
        config_file,
        capture=True)
    logdir = logdir.split(" ")[-1].replace('"', '')
    logfile = logdir + "/" + logfile
    statedir = local(
        'cat %s | egrep "^var.state_dir"' %
        config_file,
        capture=True)
    statedir = statedir.split(" ")[-1].replace('"', '')

    run('mkdir -p %s' % logdir, pty=False)
    with settings(warn_only=True):
        run('mkdir -p %s' % docroot, pty=False)
    put(config_file, config_file_remote)
    local('gzip %s' % config_file)
    run('rm -f %s' % logfile, pty=False)

    # generate dummy /index.html
    run('cd %s && dd if=/dev/zero of=index.html bs=1024 count=1' %
        docroot, pty=False)

    if htype == 'FreeBSD' or htype == 'Linux' or htype == 'Darwin':
        run('lighttpd -f %s ; sleep 0.1' % config_file_remote)
    elif htype == "CYGWIN":
        run('/usr/sbin/lighttpd -f %s ; sleep 0.1' %
            config_file_remote, pty=False)

    pid = run('cat %s%s' % (statedir, pid_file), pty=False)
    # currently we only download the access.log, but not the error.log
    bgproc.register_proc(env.host_string, 'lighttpd', counter, pid, logfile)


## Start lighttpd web server wrapper
#  @param counter Unique ID
#  @param file_prefix File prefix for log file (iperf server output)
#  @param remote_dir Directory to create log file in
#  @param server Server host 
#  @param local_dir Directory to create log file in
#  @param local_dir Local directory to put files in
#  @param port Port to listen to
#  @param config_dir Directory that contains config file
#  @param config_in Config file template to use
#  @param docroot Document root on server
#  @param check If '0' don't check for lighttpd executable, if '1' check for 
#               lighttpd executable
#  @param wait: time to wait before process is started
def start_http_server(counter='1', file_prefix='', remote_dir='', local_dir='',
                      server='', port='', config_dir='', config_in='', docroot='',
                      check='1', wait=''):
    "Start HTTP server"

    if server == '':
        abort('Must specify server')
    server, dummy = get_address_pair(server)
    execute(
        _start_http_server,
        counter,
        file_prefix,
        remote_dir,
        local_dir,
        port,
        config_dir,
        config_in,
        docroot,
        check,
        hosts=[server])


## Create DASH content on web server
#  @param counter Unique ID
#  @param file_prefix File prefix for log file (iperf server output)
#  @param local_dir Local directory to put files in
#  @param docroot Document root on server
#  @param duration Duration of 'video' files in seconds
#  @param rates Comma-separated list of 'video' rates
#  @param cycles Comma-separated list of cycle times
def _create_http_dash_content(
        counter='1', file_prefix='', local_dir='', docroot='', duration='',
        rates='', cycles=''):
    "Create dummy video chunks"

    # get host type
    htype = get_type_cached(env.host_string)

    if docroot == '':
        docroot = _get_document_root(htype)

    # make a copy of script and set parameters
    script_in = config.TPCONF_script_path + '/generate_http_content.sh.in'
    script_file = file_prefix + '_generate_http_content.sh'
    script_file_local = local_dir + '/' + script_file
    cycles = cycles.replace(',', ' ')
    rates = rates.replace(',', ' ')
    local('cat %s | sed -e "s/@PERIODS@/%s/" | sed -e "s/@BRATES@/%s/" | '
          'sed -e "s/@DURATION@/%s/" > %s'
          % (script_in, cycles, rates, duration, script_file_local))
    # upload, run script, remove script
    put(script_file_local, docroot)
    run('chmod a+x %s' % docroot + '/' + script_file, pty=False)
    run('cd %s && ./%s && rm -f %s' %
        (docroot, script_file, script_file), pty=False)


## Create DASH content on web server wrapper
#  @param counter Unique ID
#  @param file_prefix File prefix for log file (iperf server output)
#  @param remote_dir Not used, only for symmetry with the other functions
#  @param local_dir Local directory to put files in
#  @param server Host to run server on
#  @param docroot Document root on server
#  @param duration Duration of 'video' files in seconds
#  @param rates Comma-separated list of 'video' rates
#  @param cycles Comma-separated list of cycle times
#  @param check Not used, only for symmetry with the other functions
#  @param wait Not used, only for symmetry with the other functions
def create_http_dash_content(
        counter='1', file_prefix='', remote_dir='', local_dir='',
        server='', docroot='', duration='', rates='', cycles='',
        check='1', wait=''):
    "Setup content for DASH on HTTP server"

    if server == '':
        abort('Must specify server')
    server, dummy = get_address_pair(server)
    execute(
        _create_http_dash_content,
        counter,
        file_prefix,
        local_dir,
        docroot,
        duration,
        rates,
        cycles,
        hosts=[server])


## Create incast content on web server
#  @param counter Unique ID
#  @param file_prefix File prefix for log file (iperf server output)
#  @param local_dir Local directory to put files in
#  @param docroot Document root on server
#  @param duration Not used
#  @param sizes Comma-separated list of file sizes
def _create_http_incast_content(
        counter='1', file_prefix='', local_dir='', docroot='', duration='',
        sizes=''):
    "Create dummy content"

    # get host type
    htype = get_type_cached(env.host_string)

    if docroot == '':
        docroot = _get_document_root(htype)

    # make a copy of script and set parameters
    script_in = config.TPCONF_script_path + \
        '/generate_http_incast_content.sh.in'
    script_file = file_prefix + '_generate_http_incast_content.sh'
    script_file_local = local_dir + '/' + script_file
    sizes = sizes.replace(',', ' ')
    #duration = duration.replace(',', ' ')
    local('cat %s | sed -e "s/@SIZES@/%s/" > %s'
          % (script_in, sizes, script_file_local))
    # upload, run script, remove script
    put(script_file_local, docroot)
    run('chmod a+x %s' % docroot + '/' + script_file, pty=False)
    run('cd %s && ./%s && rm -f %s' %
        (docroot, script_file, script_file), pty=False)


## Create incast content on web server wrapper
#  @param counter Unique ID
#  @param file_prefix File prefix for log file (iperf server output)
#  @param remote_dir Not used, only for symmetry with the other functions
#  @param local_dir Local directory to put files in
#  @param server Host to run server on
#  @param docroot Document root on server
#  @param duration Not used
#  @param sizes Comma-separated list of file sizes
#  @param check Not used, only for symmetry with the other functions
#  @param wait Not used, only for symmetry with the other functions
def create_http_incast_content(
        counter='1', file_prefix='', remote_dir='',
        local_dir='', server='', docroot='', duration='', sizes='', check='1',
        wait=''):
    "Setup content for DASH on HTTP server"

    if server == '':
        abort('Must specify server')
    server, dummy = get_address_pair(server)
    execute(
        _create_http_incast_content,
        counter,
        file_prefix,
        local_dir,
        docroot,
        duration,
        sizes,
        hosts=[server])


## Start httperf
#  @param counter Unique ID
#  @param file_prefix File prefix for log file (iperf server output)
#  @param remote_dir Directory to create log file in
#  @param port Server port
#  @param server Server host
#  @param conns Number of connections
#  @param rate Connections per second
#  @param timeout Timeout for each connection
#  @param calls Number of calls
#  @param burst Length of burst
#  @param wsesslog Session description (requests to send)
#  @param wsesslog_timeout Default timeout for session in wsesslog
#  @param period Time between sessions/bursts
#  @param sessions Number of sessions
#  @param call_stats Maximum number of slots for call_stats
#                    (one usef for each request)
#  @param extra_params Extra parameters
#  @param check If '0' don't check for ping executable,
#               if '1' check for ping executable
#  @param wait Time to wait before process is started
def _start_httperf(counter='1', name='httperf', file_prefix='', remote_dir='',
                   port='80', server='', conns='', rate='', timeout='',
                   calls='', burst='', wsesslog='', wsesslog_timeout='0',
                   period='', sessions='1', call_stats=1000, extra_params='',
                   check='1', wait=''):

    if check == '1':
        # make sure we have httperf
        run('which httperf', pty=False)

    # set it to high value just in case...
    if call_stats < 1000:
        call_stats = 1000

    logfile = remote_dir + file_prefix + '_' + \
        env.host_string + '_' + counter + '_' + name + '.log'

    # set send and receive buffer to higher than default
    # need to set --call-stats (number of slots for stats),
    # otherwise the pace_time in wsesslog does not work properly
    # (without --call-stats>0 pace_time is basically the same as think)
    # also with call-stats>0 we get detailed statistics about each call/request
    # NOTE: setting send-buffer or recv-buffer to 2MB causes httperf to not
    #       run properly and finally crash on FreeBSD!
    #       also the whole FreeBSD machine becomes unresponsive!
    httperf_cmd = 'httperf --send-buffer=65536 --recv-buffer=1048576 ' \
                  '--call-stats=%s' % str(call_stats)

    if server != '':
        httperf_cmd += ' --server %s --port %s' % (server, port)
    if conns != '':
        httperf_cmd += ' --num-conns %s' % conns
    if rate != '':
        httperf_cmd += ' --rate %s' % rate
    if timeout != '':
        httperf_cmd += ' --timeout %s' % timeout
    if calls != '':
        httperf_cmd += ' --num-calls %s' % calls
    if burst != '':
        httperf_cmd += ' --burst-length %s' % burst
    if period != '':
        httperf_cmd += ' --period=%s' % period
    if wsesslog != '':
        # use set --retry-on-failure to avoid new connection in case of failure
        # (we should only have transient failures)
        httperf_cmd += ' --wsesslog %s,%s,%s --retry-on-failure' % (
            sessions, wsesslog_timeout, wsesslog)
    if extra_params != '':
        httperf_cmd += ' ' + extra_params

    pid = runbg(httperf_cmd, wait, out_file=logfile)
    bgproc.register_proc(env.host_string, name, counter, pid, logfile)


## Start httperf wrapper
#  @param counter Unique ID
#  @param file_prefix File prefix for log file (iperf server output)
#  @param remote_dir Directory to create log file in
#  @param local_dir Local directory to put files in (not used)
#  @param port Server port
#  @param client Client host
#  @param server Server host
#  @param conns Number of connections
#  @param rate Connections per second
#  @param timeout Timeout for each connection
#  @param calls Number of calls
#  @param burst Length of burst
#  @param wsesslog Session description (requests to send)
#  @param wsesslog_timeout Default timeout for session in wsesslog
#  @param period Time between sessions/bursts
#  @param sessions Number of sessions
#  @param extra_params Extra parameters
#  @param check If '0' don't check for ping executable,
#               if '1' check for ping executable
#  @param wait Time to wait before process is started
def start_httperf(counter='1', file_prefix='', remote_dir='', local_dir='', port='',
                  client='', server='', conns='', rate='', timeout='', calls='',
                  burst='', wsesslog='', wsesslog_timeout='', period='', sessions='1',
                  extra_params='', check='1', wait=''):
    "Start httperf on client"

    if client == '':
        abort('Must specify client')
    if server == "":
        abort("Must specify server")

    client, dummy = get_address_pair(client)
    dummy, server_internal = get_address_pair(server)
    execute(_start_httperf, counter=counter, name='httperf', file_prefix=file_prefix,
            remote_dir=remote_dir, port=port, server=server_internal,
            conns=conns, rate=rate, timeout=timeout, calls=calls, burst=burst,
            wsesslog=wsesslog, wsesslog_timeout=wsesslog_timeout,
            period=period, sessions=sessions, call_stats=1000,
            extra_params=extra_params, check=check, wait=wait, hosts=[client])


## Start httperf DASH-like client
#  @param counter Unique ID
#  @param file_prefix File prefix for log file (iperf server output)
#  @param remote_dir Directory to create log file in
#  @param local_dir Local directory to put files in
#  @param port Server port
#  @param server Server host
#  @param duration Duration of session in seconds
#  @param rate DASH rate in kbps
#  @param cycle Cycle length in seconds
#  @param prefetch Prefetch time in seconds of 'content' to prefetch
#                  (specified as float) (default = 0.0)
#  @param prefetch_timeout Timeout during prefetch phase
#  @param extra_params Extra parameters
#  @param with_timeout '0' no timeouts for requests (default),
#                      '1' with timeouts for request (httperf will close connection 
#                          if timeout expires and end session)
#  @param check '0' don't check for ping executable, '1' check for ping executable
#  @param wait Time to wait before process is started
def _start_httperf_dash(
        counter='1', file_prefix='', remote_dir='', local_dir='',
        port='', server='', duration='', rate='', cycle='', prefetch='0.0',
        prefetch_timeout='', extra_params='', with_timeout='0',
        check='1', wait=''):

    # generate session log
    spath = "/video_files-%s-%s" % (cycle, rate)
    wlog = file_prefix + "_" + env.host_string + "_" + counter + "_wlog.log"
    wlog_local = local_dir + '/' + wlog
    cpath = "/tmp/" + wlog

    # determine number of requests dpeending on duration and cycle length
    # round down to nearest integer, so the actual duration may be up to a cycle
    # shorter then duration (it must kept shorter than duration to collect
    # httperf log file)
    play_cnt = int(float(duration) / float(cycle))

    # with timeout for chplay chunk fetching, allow for a tiny bit of slack 
    # with the cycles by multiplying with 1.01
    play_timeout = str(float(cycle) * 1.01)
    
    # now determine size of play chunk in bytes
    play_chunk_size = str(float(cycle) * float(rate) * 1000 / 8)

    local('rm -f %s ; touch %s' % (wlog_local, wlog_local))

    if float(prefetch) > 60.0:
        abort('Prefetch time cannot be more than 60 seconds')

    if float(prefetch) > 0.0:
        prefetch_last_byte = str(
            int(float(prefetch) * float(rate) * 1000 / 8) - 1)
        prefetch_chunk_size = str(float(prefetch) * float(rate) * 1000 / 8)
        if prefetch_timeout == '':
            prefetch_timeout = play_timeout

        if with_timeout == '1':
            local(
                'echo %s/0 size=%s pace_time=0 timeout=%s headers=\\\'Range: '
                'bytes=0-%s\\\' >> %s' %
                (spath,
                 prefetch_chunk_size,
                 prefetch_timeout,
                 prefetch_last_byte,
                 wlog_local))
        else:
            local(
                'echo %s/0 size=%s pace_time=0 headers=\\\'Range: '
                'bytes=0-%s\\\' >> %s' %
                (spath, prefetch_chunk_size, prefetch_last_byte, wlog_local))

        # adjust the number of bursts
        play_cnt = int(
            (float(duration) -
             float(prefetch_timeout)) /
            float(cycle))

    calls = 1
    for i in range(play_cnt):
        if with_timeout == '1':
            local(
                'echo %s/%s size=%s pace_time=%s timeout=%s >> %s' %
                (spath,
                 str(calls),
                    play_chunk_size,
                    cycle,
                    play_timeout,
                    wlog_local))
        else:
            local(
                'echo %s/%s size=%s pace_time=%s >> %s' %
                (spath, str(calls), play_chunk_size, cycle, wlog_local))
        calls += 1

    # upload to client
    put(wlog_local, cpath)
    # gzip local copy
    local('gzip %s' % wlog_local)

    # start httperf
    execute(_start_httperf, counter=counter, name='httperf_dash',
            file_prefix=file_prefix, remote_dir=remote_dir, port=port,
            server=server, wsesslog=cpath, period=0.000001,
            wsesslog_timeout=play_timeout, call_stats=calls,
            extra_params=extra_params, check=check, wait=wait)


## Start httperf DASH-like client wrapper
#  @param counter Unique ID
#  @param file_prefix File prefix for log file (iperf server output)
#  @param remote_dir Directory to create log file in
#  @param local_dir Local directory to put files in
#  @param port Server port
#  @param client Client host
#  @param server Server host
#  @param duration Duration of session in seconds
#  @param rate DASH rate in kbps
#  @param cycle Cycle length in seconds
#  @param prefetch Prefetch time in seconds of 'content' to prefetch
#                  (specified as float) (default = 0.0)
#  @param prefetch_timeout Timeout during prefetch phase
#  @param extra_params Extra parameters
#  @param with_timeout '0' no timeouts for requests (default),
#                      '1' with timeouts for request (httperf will close connection 
#                          if timeout expires and start a new connection)
#  @param check '0' don't check for ping executable, '1' check for ping executable
#  @param wait Time to wait before process is started
def start_httperf_dash(counter='1', file_prefix='', remote_dir='', local_dir='',
                       port='', client='', server='', duration='', rate='', cycle='',
                       prefetch='', prefetch_timeout='', extra_params='',
                       with_timeout='0', check='1', wait=''):
    "Start httperf DASH client"

    if client == "":
        abort("Must specify client")

    client, dummy = get_address_pair(client)
    dummy, server_internal = get_address_pair(server)
    execute(_start_httperf_dash, counter, file_prefix, remote_dir, local_dir, port,
            server_internal, duration, rate, cycle, prefetch, prefetch_timeout,
            extra_params, with_timeout, check, wait, hosts=[client])


## Start httperf incast congestion querier
#  @param counter Unique ID
#  @param file_prefix File prefix for log file (iperf server output)
#  @param remote_dir Directory to create log file in
#  @param local_dir Local directory to put files in
#  @param servers Comma-separated list of servers
#                 (server1:port1,server2:port2,...,serverN:portN)
#  @param duration Duration of session in seconds
#  @param period Time between queries
#  @param burst_size Number of queries to send to each server
#  @param response_size Size of the response in kB
#  @param extra_params Extra parameters
#  @param check: '0' don't check for ping executable, '1' check for ping executable
#  @param wait: time to wait before process is started
def _start_httperf_incast(
        counter='1', file_prefix='', remote_dir='', local_dir='', servers='',
        duration='', period='', burst_size='', response_size='', extra_params='',
        check='1', wait=''):

    # generate session log
    spath = '/incast_files-%s' % (response_size)
    wlog = file_prefix + '_' + env.host_string + '_' + counter + '_wlog.log'
    wlog_local = local_dir + '/' + wlog
    cpath = '/tmp/' + wlog

    request_cnt = int(float(duration) / float(period))
    if burst_size == '':
        burst_size = '1'
    burst_cnt = int(burst_size) - 1

    local('rm -f %s ; touch %s' % (wlog_local, wlog_local))

    sessions = 0
    calls = 0
    for server in servers.split(','):
        server, port = server.split(':')
        # remove leading/trailing whitespaces
        server = server.strip()
        port = port.strip()
        # get internal address
        dummy, server_internal = get_address_pair(server)

        local(
            'echo session server=%s port=%s >> %s' %
            (server_internal, port, wlog_local))
        for i in range(request_cnt):
            for j in range(burst_cnt):
                local(
                    'echo %s/1 pace_time=0 timeout=%s >> %s' %
                    (spath, period, wlog_local))
                calls += 1

            _period = float(period)
            # if sessions == 0 and i == 0:
            if sessions == 0:
                # add 1ms from time for first server to better synchronise the 2-N bursts
                # for some reason there is a larger gap between first
                # server/session and the rest while the other session/servers
                # are well synchronised
                _period += 0.001

            local(
                'echo %s/1 pace_time=%f timeout=%f >> %s' %
                (spath, _period, _period, wlog_local))
            calls += 1

        local('echo \' \' >> %s' % wlog_local)
        sessions += 1

    # upload to client
    put(wlog_local, cpath)
    # gzip local copy
    local('gzip %s' % wlog_local)

    # start httperf
    execute(_start_httperf, counter=counter, name='httperf_incast',
            file_prefix=file_prefix, remote_dir=remote_dir, port='', server='',
            wsesslog=cpath, period=0.000001, sessions=sessions, call_stats=calls,
            extra_params=extra_params, check=check, wait=wait)


## Start httperf incast congestion querier wrapper
#  @param counter Unique ID
#  @param file_prefix File prefix for log file (iperf server output)
#  @param remote_dir Directory to create log file in
#  @param local_dir Local directory to put files in
#  @param client Client host
#  @param servers Comma-separated list of servers
#                 (server1:port1,server2:port2,...,serverN:portN)
#  @param duration Duration of session in seconds
#  @param period Time between queries
#  @param burst_size Number of queries to send to each server
#  @param response_size Size of the response in kB
#  @param extra_params Extra parameters
#  @param check: '0' don't check for ping executable, '1' check for ping executable
#  @param wait: time to wait before process is started
def start_httperf_incast(
        counter='1', file_prefix='', remote_dir='', local_dir='', client='', servers='',
        duration='', period='', burst_size='', response_size='', extra_params='',
        check='1', wait=''):
    "Start httperf incast congestion client"

    if client == "":
        abort("Must specify client")

    client, dummy = get_address_pair(client)
    execute(
        _start_httperf_incast,
        counter,
        file_prefix,
        remote_dir,
        local_dir,
        servers,
        duration,
        period,
        burst_size,
        response_size,
        extra_params,
        check,
        wait,
        hosts=[client])


## Start incast with n responders
#  @param counter Unique start ID
#  @param file_prefix File prefix for log file (iperf server output)
#  @param remote_dir Directory to create log file in
#  @param local_dir Local directory to put files in
#  @param client Client host
#  @param servers Comma-separated list of servers
#                 (server1:port1,server2:port2,...,serverN:portN)
#  @param duration Duration of session in seconds
#  @param period Time between queries
#  @param burst_size Number of queries to send to each server
#  @param response_size Size of the response in kB
#  @param server_port_start first server port to use, each server will run on different
#                           consecutive port starting with this port number
#  @param config_dir Directory that contains config file
#  @param config_in Config file template to use
#  @param docroot Document root on server
#  @param sizes Comma-separated list of file sizes on server
#  @param num_responders Number of responders actually used
#  @param extra_params Extra parameters
#  @param check: '0' don't check for ping executable, '1' check for ping executable
#  @param wait: time to wait before process is started
def start_httperf_incast_n(
        counter='1', file_prefix='', remote_dir='', local_dir='', client='', servers='',
        duration='', period='', burst_size='', response_size='', server_port_start='', 
        config_dir='', config_in='', docroot='', sizes='', num_responders='',
        extra_params='', check='1', wait=''):
    "Start httperf incast scenario with q querier and n responders"

    if client == "":
        abort("Must specify client")
    if servers == '':
        abort('Must specify servers')

    # convert to int to we can increment it
    counter = int(counter)

    num_responders_int = int(num_responders)
    servers_list = servers.split(',')
    if num_responders_int < 1:
        abort('num_responders must be at least 1')
    if num_responders_int > len(servers_list):
        abort('num_responders cannot exceed number of servers specified with servers')

    servers_list = servers_list[0:num_responders_int] 
    client_servers_list = [] # for client

    # start all servers
    port = int(server_port_start)
    for server in servers_list:
        server, dummy = get_address_pair(server)

        client_servers_list.append(server + ':' + str(port))

        execute(
            _start_http_server,
            str(counter),
            file_prefix,
            remote_dir,
            local_dir,
            str(port),
            config_dir,
            config_in,
            docroot,
            check,
            hosts=[server])

        counter += 1
        port += 1

    # wait for servers to come up
    time.sleep(0.5)

    # create content on all servers
    for server in servers_list:
        server, dummy = get_address_pair(server)

        execute(
            _create_http_incast_content,
            str(counter),
            file_prefix,
            local_dir,
            docroot,
            duration,
            sizes,
            hosts=[server])

        counter += 1

    # start client/querier
    client, dummy = get_address_pair(client)
    execute(
        _start_httperf_incast,
        str(counter),
        file_prefix,
        remote_dir,
        local_dir,
        ','.join(client_servers_list),
        duration,
        period,
        burst_size,
        response_size,
        extra_params,
        check,
        wait,
        hosts=[client])


## Start broadcast ping for post timestamp correction
## Router does the broadcast as control host in jail may not be able to
## Broadcast on the control subnet, so we don't interfere with data traffic
#  @param file_prefix File prefix for log file (iperf server output)
#  @param remote_dir Directory to create log file in
#  @param local_dir Local directory to put files in
#  @param bc_addr Broadcast or multicast address
#  @param rate Number of pings per second
#  @param use_multicast Empty string means use broadcast address (default), 
#                       otherwise must set this to IP of the outgoing interface 
def start_bc_ping(file_prefix='', remote_dir='', local_dir='', bc_addr='', 
                  rate='1', use_multicast=''):
    "Start broadcast ping"

    if bc_addr == '':
        abort('Must specify broadcast address')

    # get host type
    htype = get_type_cached(env.host_string)

    name = 'bc_ping'
    logfile = remote_dir + file_prefix + '_' + \
        env.host_string + '_' + name + '.log'

    # use stdbuf to turn off buffering of output
    # set size to 56 bytes (+ 8bytes header), this should be the default anyway
    ping_cmd = 'stdbuf -o0 -e0 ping -s 56'
    if use_multicast == '' and htype == 'Linux':
        ping_cmd += ' -b' # must explicitely set broadcast
    if use_multicast != '':
        ping_cmd += ' -I %s' % use_multicast 
    if rate != '1':
        interval = str(round(1 / float(rate), 3))
        ping_cmd += ' -i %s' % interval
    ping_cmd += ' %s' % bc_addr

    pid = runbg(ping_cmd, '0.0', out_file=logfile)
    bgproc.register_proc(env.host_string, name, '0', pid, logfile)


## Start server-to-client single traffic flow with BITSS pktgen
#  @param counter Unique ID
#  @param file_prefix File prefix for log file (iperf server output)
#  @param remote_dir Directory to create log file in
#  @param local_dir Local directory to put files in
#  @param game_type Set to q3, hl2cs, hl2dm, hlcs, hldm, et2pro or q4
#  @param client_num Total number of clients
#  @param port Client port
#  @param src_port Server port
#  @param client Client IP or name
#  @param pkt_interval Packet interval in seconds
#  @param duration Duration of traffic in seconds
#  @param extra_params Extra params to be set
#  @param check '0' don't check for pktgen executable,
#              '1' check for pktgen executable
#  @param wait Time to wait before process is started
def _start_s2c_game(counter='', file_prefix='', remote_dir='', local_dir='', 
                game_type='q3', client_num='', port='', src_port='', client='', 
                pkt_interval='0.05', duration='', extra_params='', check='1', wait=''):
    "Start s2c game traffic flow"

    if client_num == '':
        abort('Must specify number of clients with client_num')
    if client == '':
        abort('Must specify client')
    if port == '':
        abort('Must specify port')

    if check == '1':
        # make sure we have pktgen 
        run('which pktgen.sh', pty=False)

    # get client's internal address
    dummy, client_internal = get_address_pair(client) 

    # start pktgen 
    logfile = remote_dir + file_prefix + '_' + \
        env.host_string.replace(':', '_') + '_' + counter + '_pktgen.log'
    pktgen_cmd = 'pktgen.sh -w -game %s -N %s -IP %s -port %s -sport %s -iat %s -secs %s' % \
                 (game_type, client_num, client_internal, port, src_port, pkt_interval, 
                  duration)
    if extra_params != '':
        pktgen_cmd += ' ' + extra_params

    pid = runbg(pktgen_cmd, wait, out_file=logfile)
    bgproc.register_proc(env.host_string, 'pktgen', counter, pid, logfile)


## Start client-to-server single traffic flow with BITSS pktgen
#  @param counter Unique ID
#  @param file_prefix File prefix for log file (iperf server output)
#  @param remote_dir Directory to create log file in
#  @param local_dir Local directory to put files in
#  @param game_type Set to q3, hl2cs, hl2dm, hlcs, hldm, et2pro or q4
#  @param client_num Total number of clients
#  @param port Client port
#  @param src_port Server port
#  @param server Client IP or name
#  @param pkt_interval Packet interval in seconds
#  @param psize Packet size in bytes
#  @param duration Duration of traffic in seconds
#  @param extra_params Extra params to be set
#  @param check '0' don't check for pktgen executable,
#               '1' check for pktgen executable
#  @param wait Time to wait before process is started
def _start_c2s_game(counter='', file_prefix='', remote_dir='', local_dir='', 
                game_type='q3', client_num='', port='', src_port='', server='', 
                pkt_interval='0.05', psize='60', duration='', extra_params='', 
                check='1', wait=''):
    "Start c2s game traffic flow"

    if client_num == '':
        abort('Must specify number of clients with client_num')
    if server == '':
        abort('Must specify server')
    if port == '':
        abort('Must specify port')

    if check == '1':
        # make sure we have pktgen 
        run('which pktgen.sh', pty=False)

    # get client's internal address
    dummy, server_internal = get_address_pair(server)

    # start pktgen 
    logfile = remote_dir + file_prefix + '_' + \
        env.host_string.replace(':', '_') + '_' + counter + '_pktgen.log'
    pktgen_cmd = 'pktgen.sh -c -game %s -N %s -IP %s -port %s -sport %s -iat %s ' \
                 '-secs %s -c2s_psize %s' % \
                 (game_type, client_num, server_internal, port, src_port, 
                  pkt_interval, duration, psize)
    if extra_params != '':
        pktgen_cmd += ' ' + extra_params

    pid = runbg(pktgen_cmd, wait, out_file=logfile)
    bgproc.register_proc(env.host_string, 'pktgen', counter, pid, logfile)


## Start emulated FPS game traffic session with one server and n clients
## For server to client traffic we run the BITSS tool n times
## For client to server traffic we run nttcp in UDP mode to send from each
## client to the server (not very realistic but BITSS has not produced a
## client to server sending tool)
#  @param counter Unique ID start
#  @param file_prefix File prefix for log file (iperf server output)
#  @param remote_dir Directory to create log file in
#  @param local_dir Local directory to put files in
#  @param clients Comma-separated list of clients (name|IP:port) 
#  @param server Server (name|IP:port) 
#  @param game_type Set to q3, hl2cs, hl2dm, hlcs, hldm, et2pro or q4
#  @param c2s_interval Interval of client to server packets in seconds 
#  @param c2s_psize Packet size of client to server packets in bytes
#                   (size of UDP data)
#  @param s2c_interval Interval of server to client packets in seconds 
#  @param duration Duration of game in seconds
#  @param client_start_delay Number of seconds clients are started after servers
#                            are started
#  @param extra_params_client Extra params to be set for clients
#  @param extra_params_server Extra params to be set for server 
#  @param check '0' don't check for executable,
#               '1' check for executable
#  @param wait Time to wait before process is started
def start_fps_game(counter='', file_prefix='', remote_dir='', local_dir='', clients='',
                  server='', game_type='q3', c2s_interval='0.01', c2s_psize='60',
		  s2c_interval='0.05', duration='', client_start_delay='3.0',
                  extra_params_client='', extra_params_server='', check='1', wait=''):
    "Start FPS game traffic"

    if clients == '':
        abort('Must specify at least one client with clients')
    if server == '':
        abort('Must specify server')

    counter = int(counter)

    fields = server.split(':')
    server_name = fields[0]
    server_port = '27960' # not used yet
    if len(fields) > 1:
        server_port = fields[1]

    clients_list = clients.split(',')
    # make sure number of clients is within pktgen's allowed range 
    if len(clients_list) < 4 or len(clients_list) > 32:
        abort('Number of clients must be between 4 and 32')

    for client in clients_list:
        fields = client.split(':')
        client_name = fields[0]
        client_port = '27960' 
        if len(fields) > 1:
            client_port = fields[1]

        # start s2c traffic
        execute(_start_s2c_game,
                counter=str(counter),
                file_prefix=file_prefix,
                remote_dir=remote_dir,
                local_dir=local_dir,
                game_type=game_type,
                client_num=str(len(clients_list)),
                port=client_port,
                src_port=server_port,
                #src_port=client_port,
                client=client_name,
                pkt_interval=s2c_interval,
                duration=duration,
                extra_params=extra_params_server,
                check=check,
                # randomise the start times a bit
                wait=str(float(wait) + random.random()/25),
                hosts=[server_name])
                     
        counter += 1

    for client in clients_list:
        fields = client.split(':')
        client_name = fields[0]
        client_port = '27960'
        if len(fields) > 1:
            client_port = fields[1]

        # start c2s traffic
        execute(_start_c2s_game,
                counter=str(counter),
                file_prefix=file_prefix,
                remote_dir=remote_dir,
                local_dir=local_dir,
                game_type=game_type,
                client_num=str(len(clients_list)),
                port=server_port,
                #port=client_port,
                src_port=client_port,
                server=server_name,
                pkt_interval=c2s_interval,
                psize=c2s_psize,
                duration=duration,
                extra_params=extra_params_client,
                check=check,
                # delay client start to make sure server is started first
                # (pktgen is a bit slow to start). if we see failed connections
                # increase this number!
                wait=str(float(wait) + float(client_start_delay)),
                hosts=[client_name])

        counter += 1

