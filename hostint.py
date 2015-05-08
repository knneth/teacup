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
# Functions to determine the network interface based on an IP address
#
# $Id: hostint.py 958 2015-02-12 04:52:49Z szander $

import socket
import config
from fabric.api import task, warn, local, run, execute, abort, hosts, env, \
    puts
from hosttype import get_type_cached
from hostmac import get_netmac, get_netmac_cached


# maps external IPs or host names to internal network interfaces
# (automatically populated) dictionary of lists since there can be more
# than one interface per host
host_internal_int = {}

# maps external IPs or host names to external network interfaces
# (automatically populated) dictionary of lists since there can be more
# than one interface per host
host_external_int = {}

# maps internal IPs or host names to external network interfaces
# (automatically populated)
host_external_ip = {}

for external, v in config.TPCONF_host_internal_ip.items():
    for internal in config.TPCONF_host_internal_ip[external]:
        host_external_ip.update({internal: external})


# maps external IPs or host names to internal Windows interfaces for
# windump (automatically populated)
host_internal_windump_int = {}

# maps external IPs or host names to internal Windows interfaces for
# windump (automatically populated)
host_external_windump_int = {}


# Get network interface (the first by default)
# Parameters:
#	host: host identifier used by Fabric
#	int_no: interface number starting from 0 or -1 to get a list of
#               all interface
#       internal_int: '0' get external interface,
#                     '1' get internal interface(s) (default)
# Returns: interface name string, e.g. "em0"
def get_netint_cached(host='', int_no=0, internal_int='1'):
    global host_internal_int
    global host_external_int

    if internal_int == '1':
        if host not in host_internal_int:
            host_internal_int.update({host: []})
            for i in range(len(config.TPCONF_host_internal_ip[host])):
                host_internal_int[host].append(
                    execute(
                        get_netint,
                        int_no=i,
                        internal_int='1',
                        hosts=host)[host])

        res = host_internal_int.get(host, '')

        if int_no == -1:
            return res
        else:
            if len(res) > int_no:
                return [ res[int_no] ]
            else:
                return ['']

    else:
        if host not in host_external_int:
            host_external_int.update({host: []})
            host_external_int[host].append(
                execute(
                    get_netint,
                    int_no=0,
                    internal_int='0',
                    hosts=host)[host])

        res = host_external_int.get(host, '')

        return res


# Get network interface for windump (the first by default)
# We need this function since windump uses a differently ordered list than
# windows itself
# Parameters:
#       host: host identifier used by Fabric
#       int_no: interface number starting from 0 or -1 to get a list of all
#               interfaces
#       internal_int: '0' get external interface,
#                     '1' get internal interface(s) (default)
# Returns: interface name string (which is always a number), e.g. "1"
def get_netint_windump_cached(host='', int_no=0, internal_int='1'):
    global host_internal_windump_int
    global host_external_windump_int

    # get type of current host
    htype = get_type_cached(env.host_string)

    if internal_int == '1':
        if htype == 'CYGWIN' and host not in host_internal_windump_int:
            host_internal_windump_int.update({host: []})
            for i in range(len(config.TPCONF_host_internal_ip[host])):
                host_internal_windump_int[host].append(
                    execute(
                        get_netint,
                        int_no=i,
                        windump='1',
                        internal_int='1',
                        hosts=host)[host])

        res = host_internal_windump_int.get(host, '')

        if int_no == -1:
            return res
        else:
            if len(res) > int_no:
                return [ res[int_no] ]
            else:
                return ['']

    else:
        if htype == 'CYGWIN' and host not in host_external_windump_int:
            host_external_windump_int.update({host: []})
            host_external_windump_int[host].append(
                execute(
                    get_netint,
                    int_no=0,
                    windump='1',
                    internal_int='0',
                    hosts=host)[host])

        res = host_external_windump_int.get(host, '')

        return res


# Get host network interface name
# Parameters:
# 	int_no: interface number starting from 0 (internal only)
#	windump: '0' get interface names used by Windows, '1' get interface
#                name used by windump
#	internal_int: '0' get external interface,
#                     '1' get internal interface(s) (default)
# Returns: interface name string, e.g. "em0"
@task
def get_netint(int_no=0, windump='0', internal_int='1'):
    "Get network interface name"

    # need to convert if we run task from command line
    int_no = int(int_no)

    # check int_no paramter
    if int_no < 0:
        int_no = 0
    if int_no >= len(config.TPCONF_host_internal_ip[env.host_string]):
        int_no = len(config.TPCONF_host_internal_ip[env.host_string]) - 1

    # get type of current host
    htype = get_type_cached(env.host_string)

    if htype == 'FreeBSD' or htype == 'Linux' or htype == 'Darwin':
        # get  ip and set last octet to 0
        if internal_int == '1':
            iip = config.TPCONF_host_internal_ip[env.host_string][int_no]
        else:
            iip = socket.gethostbyname(env.host_string.split(':')[0])

        a = iip.split('.')
        del a[3]
        iip = '.'.join(a)

	int_name = ''
        field_idx = -1
        lines = run('netstat -nr', shell=False)
        for line in lines.split('\n'):
            if line != '':
	        fields = line.split()
                if len(fields) > 0 and fields[0] == 'Destination' and  \
                    int_name == '' :
                    for i in range(len(fields)) :
                        if fields[i] == 'Netif' :
                            field_idx = i 
                if len(fields) > 0 and (fields[0].split('/')[0] == iip + '.0' or 
                                        fields[0].split('/')[0] == iip) :
                    int_name = fields[field_idx]

        #puts('Interface: %s' % int_name)
        return int_name

    elif htype == "CYGWIN":
        # on windows we have two numbers
        # windows numbering of interfaces
        # numbering used by windump

        if windump == '0':

            # get interface IPs and numbers
            output = run(
                'ipconfig | egrep "Local Area|IPv4" | grep -v "Tunnel"',
                pty=False)

            lines = output.split("\n")
            for i in range(0, len(lines), 2):
                int_num = lines[i].replace(":", "").split(" ")[-1]
                if int_num == "": # XXX not sure what we are doing here
                    int_num = "1"
                int_ip = lines[i + 1].split(":")[1].strip()

                if internal_int == '1' and int_ip == config.TPCONF_host_internal_ip[
                        env.host_string][int_no] or \
                   internal_int == '0' and int_ip == socket.gethostbyname(
                        env.host_string.split(':')[0]):
                    puts('Interface: %s' % int_num)
                    return int_num

        else:
            # get list of interface numbers and interface IDs
            output = run(
                'winDUmp -D | sed "s/\([0-9]\)\.[^{]*{\([^}]*\).*/\\1 \\2/"',
                pty=False)

            # get list of interface macs and interface IDs
            output2 = run(
                'getmac | '
                'grep "^[0-9]" | sed "s/^\([0-9A-Fa-f-]*\)[^{]*{\([^}]*\).*/\\1 \\2/"',
                pty=False)

            # get mac of the internal/external interface
            mac = execute(
                get_netmac,
                internal_int=internal_int,
                hosts=[env.host_string]).values()[0]

            # find interface ID
            int_id = ''
            lines = output2.split("\n")
            for line in lines:
                _int_mac, _int_id = line.split(' ')

		# get mac print with '-' instead of ':'
                _int_mac = _int_mac.replace('-', ':').lower()
                if _int_mac == mac:
                    int_id = _int_id
                    break

            # get interface number (could use ID but it's a bit long)
            lines = output.split("\n")
            for line in lines:
                _int_num, _int_id = line.split(' ')
                if _int_id == int_id:
                    puts('Interface: %s' % _int_num)
                    return _int_num

    else:
        abort('Cannot determine network interface for OS %s' % htype)


# Get testbed address of host if parameter host is external address,
# otherwise return given address
# Parameters:
#	host: external address
# Returns: _first_ testbed address if host is external address, otherwise host
def get_internal_ip(host):
    addresses = config.TPCONF_host_internal_ip.get(host, [])
    if len(addresses) > 0:
        iaddr = addresses[0]
    else:
        iaddr = host

    return iaddr


# Get host external IP or host name for an internal/testbed address or host name
# Parameters:
#	ihost: internal address
#	do_abort: '0' do not abort if no external address found, '1' abort if no
#              external address found
# Returns: external address
def get_external_ip(ihost, do_abort='1'):

    # return dummy value if prefix is present, should only happen if called
    # from init_pipe() and in this case we _don't_ need any external address
    if ihost.find('/') > -1:
        return 'invalid'

    addr = host_external_ip.get(ihost, '')
    if addr == '' and do_abort == '1':
        abort('No external address for internal address %s' % ihost)

    return addr


# Get external and internal address
# Parameters:
#	host: internal or external address
#	do_abort: '0' do not abort if no external address found, '1' abort if no
#              external address found
# Returns pair of external address and internal address
def get_address_pair(host, do_abort='1'):
    internal = get_internal_ip(host)
    if internal == host:
        external = get_external_ip(host, do_abort)
        return (external, internal)
    else:
        return (host, internal)
