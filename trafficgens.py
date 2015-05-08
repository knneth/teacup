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
# Traffic generators
#
# $Id: trafficgens.py 1000 2015-02-17 06:38:35Z szander $

import time
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

# Start nttcp server (UDP only)
# Parameters:
#       counter: unique ID
#       file_prefix: file prefix for log file (nttcp server output)
#       remote_dir: directory to create log file in
#       port: listen on this port
#       srv_host: bind to interface with this address
#       buf_size: size of send buffer
#       extra_params: extra params to be set
#       check: '0' don't check for nttcp executable,
#              '1' check for nttcp executable
#       wait: time to wait before process is started
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


# Start nttcp client (UDP only)
# Parameters:
#       counter: unique ID
#       file_prefix: file prefix for log file (nttcp client output)
#       remote_dir: directory to create log file in
#       port: listen on this port
#       srv_host: bind to interface with this address
#       duration: duration in seconds
#	interval: packet interval in milliseconds
#	psize: size of the UDP payload (excluding IP/UDP header) in bytes
#       buf_size: size of send buffer
#       extra_params: extra params to be set
#       check: '0' don't check for nttcp executable,
#              '1' check for nttcp executable
#       wait: time to wait before process is started
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


# Start nttcp sender and receiver
# Parameters:
#       see start_nttcp_client() and start_nttcp_server()
#	local_dir: local directory to put files in (not used)
#@task
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


#@task
def stop_nttcp(counter='1', file_prefix='', remote_dir='', local_dir="."):
    "Stop nttcp (NOT IMPLEMENTED)"
    pass


#
# iperf
#

# Start iperf server
# Parameters:
#	counter: unique ID
#	file_prefix: file prefix for log file (iperf server output)
#	remote_dir: directory to create log file in
#	port: listen on this port
#	srv_host: bind to interface with this address
#       duration: duration in seconds (only used if kill='1')
#       mss: maximum segment size
#       buf_size: size of send and receive buffer
#                 (assumes iperf modified with CAIA patch)
#	proto: must be 'tcp' or 'udp'
#	extra_params: extra params to be set
#	check: '0' don't check for iperf executable, '1' check for iperf executable
#	wait: time to wait before process is started
#       kill: '0' server will terminate according to duration (default),
#             '1' kill server after duration to work around
#               "feature" in iperf that prevents it from stopping after duration
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


# Start iperf client
# Parameters:
#       counter: unique ID
#       file_prefix: file prefix for log file (iperf server output)
#       remote_dir: directory to create log file in
#       port: listen on this port
#       srv_host: bind to interface with this address
# 	duration: duration in seconds
#	congestion_algo: congestion control algo to use (Linux only!)
#       mss: maximum segment size
#       buf_size: size of send and receive buffer
#                 (assumes iperf modified with CAIA patch)
#       proto: must be 'tcp' or 'udp'
# 	bandw: bandwidth in n[KM] (K for kilo, M for mega)
#       extra_params: extra params to be set
#       check: '0' don't check for iperf executable,
#              '1' check for iperf executable
#       wait: time to wait before process is started
#       kill: '0' client will terminate according to duration (default),
#             '1' kill client after duration to work around
#               "feature" in iperf that prevents it from stopping after duration
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


# Start iperf sender and receiver
# Parameters:
#	see start_iperf_client() and start_iperf_server()
#       local_dir: local directory to put files in (not used)
#	kill: '0' client and server will terminate according to duration (default),
#             '1' kill client/server after duration to work around
#		"feature" in iperf that prevents it from stopping after duration
#@task
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


# Stop iperf sender and receiver
#       counter: unique ID
#       file_prefix: file prefix for log file (iperf server output)
#       remote_dir: directory to create log file in
#	local_dir: local dir to copy log file into
#@task
def stop_iperf(counter='1', file_prefix='', remote_dir='', local_dir="."):
    "Stop iperf traffic sender and receiver"

    pid = bgproc.get_proc_pid(env.host_string, 'iperf', counter)

    with settings(warn_only=True):
        if pid != '':
            run('kill %s' % pid, pty=False)
        else:
            run('killall iperf', pty=False)

    if file_prefix != '' or remote_dir != '':
        file_name = remote_dir + file_prefix + '_' + \
            env.host_string.replace(':', '_') + '_' + counter + '_iperf.log'
    else:
        file_name = bgproc.get_proc_log(env.host_string, 'iperf', counter)

    getfile(file_name, local_dir)
    bgproc.remove_proc(env.host_string, 'iperf', counter)


#
# ping
#

# Start ping
# Parameters:
#       counter: unique ID
#       file_prefix: file prefix for log file (iperf server output)
#       remote_dir: directory to create log file in
#       dest: target to ping
#       duration: duration in seconds
#	rate: number of pings per second
#	extra_params: other parameters passed directly to ping
#       check: '0' don't check for ping executable, '1' check for ping executable
#       wait: time to wait before process is started
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


# Start ping wrapper
# Parameters:
#	see _start_ping()
#       local_dir: local directory to put files in (not used)
#@task
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


# Stop ping
# Parameters:
#       counter: unique ID
#       file_prefix: file prefix for log file (iperf server output)
#       remote_dir: directory to create log file in
#	local_dir: local directory to copy log file into
#@task
def stop_ping(counter='1', file_prefix='', remote_dir='', local_dir="."):
    "Stop ping"

    pid = bgproc.get_proc_pid(env.host_string, 'ping', counter)
    with settings(warn_only=True):
        if pid != "":
            run('kill %s' % pid, pty=False)
        else:
            run('killall ping', pty=False)

    if file_prefix != "" or remote_dir != "":
        file_name = remote_dir + file_prefix + '_' + \
            env.host_string.replace(':', '_') + '_' + counter + '_ping.log'
    else:
        file_name = bgproc.get_proc_log(env.host_string, 'ping', counter)

    getfile(file_name, local_dir)
    bgproc.remove_proc(env.host_string, 'ping', counter)


#
# httperf
#


# Return default document root depending on host OS
# Parameters:
# 	htype: host type string
def _get_document_root(htype):
    if htype == 'FreeBSD':
        docroot = '/usr/local/www/data'
    elif htype == 'Darwin':
        docroot = '/opt/local/www/htdocs'
    else:
        docroot = '/srv/www/htdocs'

    return docroot


# Start lighttpd web server
# Parameters:
#	counter: unique ID
#       file_prefix: file prefix for log file (iperf server output)
#       remote_dir: directory to create log file in
#       local_dir: local directory to put files in
#	port: port to listen to
#	config_dir: directory that contains config file
#	config_in: config file template to use
#	docroot: document root on server
# check: '0' don't check for lighttpd executable, '1' check for lighttpd
# executable
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


# Start lighttpd web server wrapper
# Parameters:
#       counter: unique ID
#       file_prefix: file prefix for log file (iperf server output)
#       remote_dir: directory to create log file in
#       local_dir: local directory to put files in
#	server: host to run server on
#       port: port to listen to
#       config_dir: directory that contains config file
#       config_in: config file template to use
#       docroot: document root on server
#       check: '0' don't check for lighttpd executable,
#              '1' check for lighttpd executable
#@task
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


# Create DASH content on web server
#       counter: unique ID
#       file_prefix: file prefix for log file (iperf server output)
#       local_dir: local directory to put files in
#       docroot: document root on server
#	duration: duration of 'video' files in seconds
#	rates: comma-separated list of 'video' rates
#	cycles: comma-separated list of cycle times
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


# Create DASH content on web server wrapper
#       counter: unique ID
#       file_prefix: file prefix for log file (iperf server output)
#       remote_dir: not used, only for symmetry with the other functions
#       local_dir: local directory to put files in
#       server: host to run server on
#       docroot: document root on server
#       duration: duration of 'video' files in seconds
#       rates: comma-separated list of 'video' rates
#       cycles: comma-separated list of cycle times
#	check: not used, only for symmetry with the other functions
#	wait: not used, only for symmetry with the other functions
#@task
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


# Create incast content on web server
#       counter: unique ID
#       file_prefix: file prefix for log file (iperf server output)
#       local_dir: local directory to put files in
#       docroot: document root on server
#       duration: not used
#       sizes: comma-separated list of file sizes
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


# Create incast content on web server wrapper
#       counter: unique ID
#       file_prefix: file prefix for log file (iperf server output)
#       remote_dir: not used, only for symmetry with the other functions
#       local_dir: local directory to put files in
#       server: host to run server on
#       docroot: document root on server
#       duration: not used
#       sizes: comma-separated list of file sizes
#	check: not used, only for symmetry with the other functions
#	wait: not used, only for symmetry with the other functions
#@task
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


# XXX not implemented yet cause we have stop_processes
#@task
def stop_http_server(
        counter='1', file_prefix='', remote_dir='', local_dir="."):
    "Stop HTTP server (NOT IMPLEMENTED)"
    pass


# Start httperf
# Parameters:
#       counter: unique ID
#       file_prefix: file prefix for log file (iperf server output)
#       remote_dir: directory to create log file in
#	port: server port
#	server: server host
#	conns: number of connections
#	rate: connections per second
#	timeout: timeout for each connection
#	calls: number of calls
#	burst: length of burst
#	wsesslog: session description (requests to send)
#	wsesslog_timeout: default timeout for session in wsesslog
#	period: time between sessions/bursts
#	sessions: number of sessions
#	call_stats: maximum number of slots for call_stats
#                   (one usef for each request)
#	extra_params: extra parameters
#       check: '0' don't check for ping executable,
#              '1' check for ping executable
#       wait: time to wait before process is started
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


# Start httperf wrapper
# Parameters:
#       counter: unique ID
#       file_prefix: file prefix for log file (iperf server output)
#       remote_dir: directory to create log file in
#       local_dir: local directory to put files in (not used)
#       port: server port
#       client: client host
#       server: server host
#       conns: number of connections
#       rate: connections per second
#       timeout: timeout for each connection
#       calls: number of calls
#       burst: length of burst
#       wsesslog: session description (requests to send)
#       wsesslog_timeout: default timeout for session in wsesslog
#       period: time between sessions/bursts
#       sessions: number of sessions
#       extra_params: extra parameters
#       check: '0' don't check for ping executable, '1' check for ping executable
#       wait: time to wait before process is started
#@task
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


# XXX not implemented yet cause we have stop_processes
#@task
def stop_httperf(counter='1', file_prefix='', remote_dir='', local_dir="."):
    "Stop httperf (NOT IMPLEMENTED)"
    pass


# Start httperf DASH-like client
# Parameters:
#       counter: unique ID
#       file_prefix: file prefix for log file (iperf server output)
#       remote_dir: directory to create log file in
#       local_dir: local directory to put files in
#       port: server port
#       server: server host
#       duration: duration of session in seconds
#	rate: DASH rate in kbps
#	cycle: cycle length in seconds
#	prefetch: prefetch time in seconds of 'content' to prefetch
#                 (specified as float) (default = 0.0)
#       extra_params: extra parameters
#       with_timeout: '0' no timeouts for requests (default),
#                     '1' with timeouts for request
#	(httperf will close connection if timeout expires and start a new connection)
#       check: '0' don't check for ping executable, '1' check for ping executable
#       wait: time to wait before process is started
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

    play_cnt = int(float(duration) / float(cycle))
    # allow for a tiny bit of slack with the cycles
    play_timeout = str(float(cycle) * 1.01)
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
                 chunk_size,
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
                    chunk_size,
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


# Start httperf DASH-like client wrapper
# Parameters:
#       counter: unique ID
#       file_prefix: file prefix for log file (iperf server output)
#       remote_dir: directory to create log file in
#       local_dir: local directory to put files in
#       port: server port
#	client: client host
#       server: server host
#       duration: duration of session in seconds
#       rate: DASH rate in kbps
#       cycle: cycle length in seconds
#       prefetch: prefetch time in seconds of 'content' to prefetch
#                 (currently must be multiple of cycle)
#       extra_params: extra parameters
#       with_timeout: '0' no timeouts for requests (default),
#                     '1' with timeouts for request
#       (httperf will close connection if timeout expires and start a new connection)
#       check: '0' don't check for ping executable, '1' check for ping executable
#       wait: time to wait before process is started
#@task
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


#@task
def stop_httperf_dash(
        counter='1', file_prefix='', remote_dir='', local_dir="."):
    "Stop httperf DASH client (NOT IMPLEMENTED)"
    pass


# Start httperf incast congestion querier
# Parameters:
#       counter: unique ID
#       file_prefix: file prefix for log file (iperf server output)
#       remote_dir: directory to create log file in
#       local_dir: local directory to put files in
#       servers: comma-separated list of servers
#                (server1:port1,server2:port2,...,serverN:portN)
#       duration: duration of session in seconds
#       period: time between queries
#       burst_size: number of queries to send to each server
#       response_size: size of the response in kB
#       extra_params: extra parameters
#       check: '0' don't check for ping executable, '1' check for ping executable
#       wait: time to wait before process is started
def _start_httperf_incast(
        counter='1', file_prefix='', remote_dir='', local_dir='', servers='',
        duration='', period='', burst_size='', response_size='', extra_params='',
        check='1', wait=''):

    # generate session log
    spath = '/incast_files-%s' % (response_size)
    wlog = file_prefix + '_' + env.host_string + '_' + counter + '_wlog.log'
    wlog_local = local_dir + '/' + wlog
    cpath = '/tmp/' + wlog

    request_cnt = int(duration) / int(period)
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


# Start httperf incast congestion querier wrapper
# Parameters:
#       counter: unique ID
#       file_prefix: file prefix for log file (iperf server output)
#       remote_dir: directory to create log file in
#       local_dir: local directory to put files in
# 	client: client host
#       servers: comma-separated list of servers
#                (server1:port,server2:port,...,serverN:port)
#       duration: duration of session in seconds
#       period: time between queries
#       burst_size: number of queries to send to each server
#       response_size: size of the response in kB
#       extra_params: extra parameters
#       check: '0' don't check for ping executable, '1' check for ping executable
#       wait: time to wait before process is started
#@task
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


#@task
def stop_httperf_incast(
        counter='1', file_prefix='', remote_dir='', local_dir="."):
    "Stop httperf incast client (NOT IMPLEMENTED)"
    pass


# Start incast with n responders
# Parameters:
#       counter: unique ID
#       file_prefix: file prefix for log file (iperf server output)
#       remote_dir: directory to create log file in
#       local_dir: local directory to put files in
#       client: client host
#       servers: comma-separated list of all possible servers, but only num_responders
#                are used
#                (server1:port,server2:port,...,serverN:port)
#       duration: duration of session in seconds
#       period: time between queries
#       burst_size: number of queries to send to each server
#       response_size: size of the response in kB
# 	server_port_start: first server port to use, each server will run on different
#                          consecutive port starting with this port number
#       config_dir: directory that contains config file
#       config_in: config file template to use
#       docroot: document root on server
#       sizes: comma-separated list of file sizes on server
#       num_responders: number of responders actually used
#       extra_params: extra parameters
#       check: '0' don't check for executable, '1' check for executable
#       wait: time to wait before process is started
#@task
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


# Start broadcast ping for post timestamp correction
# Router does the broadcast as control host in jail may not be able to
# Broadcast on the control subnet, so we don't interfere with data traffic
# Parameters:
#       file_prefix: file prefix for log file (iperf server output)
#       remote_dir: directory to create log file in
#       local_dir: local directory to put files in
#	bc_addr: broadcast or multicast address
#	rate: pings per second
#       use_multicast: '' use broadcast address (default) 
#                      'interface' IP of the outgoing interface 
#@task
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


#@task
def stop_bc_ping(file_prefix='', remote_dir='', local_dir=''):
    "Stop broadcast ping (NOT IMPLEMENTED)"
    pass

