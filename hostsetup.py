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
# Host setup
#
# $Id: hostsetup.py 1004 2015-02-18 01:35:37Z szander $

import sys
import time
import re
import csv
import socket
import os
import subprocess
import string
import pexpect # must use version 3.2, version 3.3 does not work
import pxssh
import config
from fabric.api import reboot, task, warn, local, puts, run, execute, abort, \
    hosts, env, settings, parallel, put, runs_once
from hosttype import get_type_cached, get_type
from hostint import get_netint_cached
from hostmac import get_netmac_cached


# Setup VLANs on switch 
# Parameters:
#       switch: switch name
#       port_prefix: prefix for ports at switch
#       port_offset: host number to port number offset
@task
# XXX parallel crashes when configuring switch. maybe just session limit on switch
# but to avoid overwhelming switch, run sequentially
#@parallel
def init_topology_switch(switch='switch2', port_prefix='Gi1/0/', port_offset = '5'):
    "Topology setup switch"

    if env.host_string not in config.TPCONF_hosts:
        abort('Host %s not found in TPCONF_hosts' % env.host_string)

    # get test ip 
    try:
        test_ip = config.TPCONF_host_internal_ip[env.host_string][0]
    except AttributeError:
        abort('No entry for host %s in TPCONF_host_internal_ip' %
              env.host_string)

    #
    # first switch VLANs on switch
    #

    host_string = env.host_string
    env.host_string = switch

    # create translation table
    all = string.maketrans('','')
    nodigs = all.translate(all, string.digits)
    # get port number and vlan id
    port_number = int(host_string.translate(all, nodigs)) + int(port_offset)
    a = test_ip.split('.')
    vlan = a[2]

    s = pexpect.spawn('ssh %s@%s' %
                     (env.user, env.host_string))
    s.setecho(False)
    s.logfile_read = sys.stdout
    s.logfile_send = sys.stdout
    ssh_newkey = 'Are you sure you want to continue connecting'
    i = s.expect([ssh_newkey, 'password:', pexpect.EOF, pexpect.TIMEOUT], timeout = 5)
    if i==0:
        s.sendline('yes')
        i = s.expect([ssh_newkey, 'password:', pexpect.EOF])
    if i==1:
        s.sendline(env.password)
    elif i==2:
        # have key"
        pass
    elif i==3: 
        # connection timeout
        abort('Timeout while waiting for password prompt') 

    s.expect('>')
    s.sendline('enable')
    s.expect('#')
    s.sendline('config')
    s.expect('#')
    s.sendline('int %s%i' % (port_prefix, port_number))
    s.expect('#')
    s.sendline('switchport access vlan %s' % vlan)
    s.expect('#')
    s.sendline('exit')
    s.expect('#')
    s.sendline('exit')
    s.expect('#')
    s.sendline('show interfaces switchport %s%i' % (port_prefix, port_number))
    s.expect('#')
    s.close()
    print('\n')

    env.host_string = host_string


# Setup NIC & routing on hosts 
# Parameters:
@task
@parallel
def init_topology_host():
    "Topology setup host"

    if env.host_string not in config.TPCONF_hosts:
        abort('Host %s not found in TPCONF_hosts' % env.host_string)

    # get test ip 
    try:
        test_ip = config.TPCONF_host_internal_ip[env.host_string][0]
    except AttributeError:
        abort('No entry for host %s in TPCONF_host_internal_ip' %
             env.host_string)

    #
    # set network interface
    #

    a = test_ip.split('.')
    del a[3]
    test_subnet = '.'.join(a)
    subnet1 = config.TPCONF_host_internal_ip[config.TPCONF_router[0]][0]
    a = subnet1.split('.')
    del a[3]
    subnet1 = '.'.join(a)
    subnet2 = config.TPCONF_host_internal_ip[config.TPCONF_router[0]][1]
    a = subnet2.split('.')
    del a[3]
    subnet2 = '.'.join(a)

    # get type of current host
    htype = get_type_cached(env.host_string)

    if htype == 'Linux':
        test_if_config = "BOOTPROTO='static'\n" + \
                         "BROADCAST=''\n" + \
                         "ETHTOOL_OPTIONS=''\n" + \
                         "IPADDR='" + test_ip + "/24'\n" + \
                         "MTU=''\n" + \
                         "NAME='Test IF'\n" + \
                         "NETWORK=''\n" + \
                         "REMOTE_IPADDR=''\n" + \
                         "STARTMODE='auto'\n" + \
                         "USERCONTROL='no'"

        fname = env.host_string + '_test_if_config'
        with open(fname, 'w') as f:
             f.write(test_if_config)

        put(fname, '/etc/sysconfig/network/ifcfg-eth1')
        os.remove(fname)

        if test_subnet == subnet1:
            route = subnet2 + '.0 ' + subnet1 + '.1 255.255.255.0 eth1'
            #route = subnet2 + '.0 ' + subnet1 + '.1 255.255.255.0 enp2s0'
        else:
            route = subnet1 + '.0 ' + subnet2 + '.1 255.255.255.0 eth1'
            #route = subnet1 + '.0 ' + subnet2 + '.1 255.255.255.0 enp2s0'

        run('echo %s > /etc/sysconfig/network/routes' % route)

        #run('/etc/rc.d/network restart')
        run('systemctl restart network.service')

    elif htype == 'FreeBSD':
        run('cp -a /etc/rc.conf /etc/rc.conf.bak')
        run('cat /etc/rc.conf | egrep -v ^static_routes | ' \
            'egrep -v route_ | egrep -v ^ifconfig_em1 > __tmp')
        run('mv __tmp /etc/rc.conf')

        # the most insane quoting ever :). Since fabric will quote command in double quotes and root has
        # csh we cannot echo a double quote with /". We must terminate Fabrics double quotes and put the
        # echo string in single quotes. We must use raw strings to be able to pass \" to shell. We must
        # also tell Fabric to not escape doubel quotes with \.
        run('echo "\'%s\' >> /etc/rc.conf"' % (r'ifconfig_em1=\"' + test_ip + r' netmask 255.255.255.0\"'),
            shell_escape=False)

        if test_subnet == subnet1 :
            route1 = r'static_routes=\"internalnet2\"'
            route2 = r'route_internalnet2=\"-net ' + subnet2 + r'.0/24 ' + subnet1 + r'.1\"'
        else:
            route1 = r'static_routes=\"internalnet1\"'
            route2 = r'route_internalnet1=\"-net ' + subnet1 + r'.0/24 ' + subnet2 + r'.1\"'

        run('echo "\'%s\' >> /etc/rc.conf"' % route1, shell_escape=False)
        run('echo "\'%s\' >> /etc/rc.conf"' % route2, shell_escape=False)

        # restart network
        run('/etc/rc.d/netif restart')
        with settings(warn_only=True):
            run('/etc/rc.d/routing restart')

    elif htype == 'CYGWIN':
        # remove all testbed routes
        run('route delete %s.0 -p' % subnet1)
        run('route delete %s.0 -p' % subnet2)

        # search for right interface based on start of MAC
        interface = ''
        interfaces_all = run('ipconfig /all')
        for line in interfaces_all.splitlines():
            if line.find('Ethernet adapter') > -1:
                interface = line.replace('Ethernet adapter ', '').replace(':','').rstrip()
            if line.find('68-05-CA-') > -1 :
                break

        # interface config
        cmd = r'netsh interface ip set address \"%s\" static %s 255.255.255.0' % (interface, test_ip)
        run('"\'%s\'"' % cmd, pty=False, shell_escape=False)

        time.sleep(5)

        # set static route
        # first need to find interface id for routing purposes based on MAC
        interface = '' 
        interfaces_all = run('route print')
        for line in interfaces_all.splitlines():
            if line.find('68 05 ca') > -1 :
                interface = line.lstrip()[0:2]
                interface = interface.replace('.', '')
                break

        if test_subnet == subnet1 :
            route = 'route add ' + subnet2 + '.0 mask 255.255.255.0 ' + subnet1 + '.1 if %s -p' % interface
        else:
            route = 'route add ' + subnet1 + '.0 mask 255.255.255.0 ' + subnet2 + '.1 if %s -p' % interface

        run(route, pty=False)

    elif htype == 'Darwin':
        # remove all testbed routes
        run('route -n delete %s.0/24' % subnet1)
        run('route -n delete %s.0/24' % subnet2)

        # setup interface
        run('networksetup -setmanual "Ethernet" %s 255.255.255.0' % test_ip)

        # set static route
        if test_subnet == subnet1 :
            par1 = subnet2
            par2 = subnet1
        else :
            par1 = subnet1
            par2 = subnet2
            
        interface = 'en0'
        run('route -n add %s.0/24 -interface %s' % (par2, interface))
        run('cat /Library/StartupItems/AddRoutes/AddRoutes | sed "s/route add .*$/route add %s.0\/24 %s.1/" > __tmp' \
            ' && mv __tmp /Library/StartupItems/AddRoutes/AddRoutes' % 
            (par1, par2))
        run('chmod a+x /Library/StartupItems/AddRoutes/AddRoutes')
            
        run('/Library/StartupItems/AddRoutes/AddRoutes start')


# Setup testbed network topology
# XXX router is currently static and cannot be changed
# This tasks makes a number of assumptions:
# - hosts are numbered and numbers relate to the switch port 
#   (starting from first port)
# - VLAN number is the same as 3rd octet of IP
# - there are two test subnets 172.16.10.0/24, 172.16.11.0/24
# - interface names are known/hardcoded
# Parameters:
#       switch: switch name
#       port_prefix: prefix for ports at switch
#       port_offset: host number to port number offset
@task
# we need to invoke this task with runs_once, as otherwise this task will run once for each host listed in -H
@runs_once
def init_topology(switch='switch2', port_prefix='Gi1/0/', port_offset = '5'):
    "Topology setup"

    # sequentially configure switch
    execute(init_topology_switch, switch, port_prefix, port_offset)
    # configure hosts in parallel
    execute(init_topology_host)


# Power cycle hosts via the 9258HP power controllers
# Parameters:
@task
@parallel
def power_cycle():
    "Power cycle host using the power controller"

    # check for wget
    local('which wget')

    # check if user name and password defined
    try:
       x = config.TPCONF_power_admin_name
       x = config.TPCONF_power_admin_pw
    except AttributeError:
        abort('TPCONF_power_admin_name  and TPCONF_power_admin_pw must be set')

    # get type of power controller
    try:
        ctrl_type = config.TPCONF_power_ctrl_type
    except AttributeError:
        ctrl_type = '9258HP'

    # get IP of power controller and port number of 9258HP host is connected to
    try:
        ctrl_ip, ctrl_port = config.TPCONF_host_power_ctrlport[env.host_string]
    except KeyError:
        abort(
            'No power controller IP/port defined for host %s' %
            env.host_string)

    if ctrl_type == '9258HP':

    	# turn power off
    	cmd = 'wget -o /dev/null -O /dev/null http://%s/SetPower.cgi?user=%s+pass=%s+p%s=0' % \
        	(ctrl_ip,
         	config.TPCONF_power_admin_name,
         	config.TPCONF_power_admin_pw,
         	ctrl_port)
    	local(cmd)

    	time.sleep(2)

    	# turn power on
    	cmd = 'wget -o /dev/null -O /dev/null http://%s/SetPower.cgi?user=%s+pass=%s+p%s=1' % \
        	(ctrl_ip,
         	config.TPCONF_power_admin_name,
         	config.TPCONF_power_admin_pw,
        	 ctrl_port)
    	local(cmd)

    elif ctrl_type == 'SLP-SPP1008':

	s = ''
        for i in range(1,9):
            if i == int(ctrl_port):
                s += '1'
            else:
                s += '0'
        s += '00000000' + '00000000' 

        # turn power off
        cmd = 'wget --user=%s --password=%s -o /dev/null -O /dev/null http://%s/offs.cgi?led=%s' % \
                (config.TPCONF_power_admin_name,
                config.TPCONF_power_admin_pw,
                ctrl_ip,
                s)
        local(cmd)

        time.sleep(2)

        # turn power on
        cmd = 'wget --user=%s --password=%s -o /dev/null -O /dev/null http://%s/ons.cgi?led=%s' % \
                (config.TPCONF_power_admin_name,
                config.TPCONF_power_admin_pw,
                ctrl_ip,
                s)
        local(cmd)

    else:
        abort('Unsupported power controller \'%s\'' % ctrl_type)


# Boot host into selected OS
# Parameters:
#	file_prefix: prefix for generated pxe boot file
#	os_list: comma-separated string of OS (Linux, FreeBSD, CYGWIN), one for each host
#	force_reboot: '0' (host will only be rebooted if OS should be changed,
#                     '1' (host will always be rebooted)
#	do_power_cycle: '0' (never power cycle host),
#                       '1' (power cycle host if host does not come up after timeout
#	boot_timeout: reboot timeout in seconds (integer)
#	local_dir: directory to put the generated .ipxe files in
#	linux_kern_router: Linux kernel to boot on router
#	linux_kern_hosts: Linux kernel to boot on hosts
#	tftp_server: of the form <server_ip>:<port> 
@task
@parallel
def init_os(file_prefix='', os_list='', force_reboot='0', do_power_cycle='0',
            boot_timeout='100', local_dir='.',
            linux_kern_router='3.10.18-vanilla-10000hz',
            linux_kern_hosts='3.9.8-desktop-web10g',
            tftp_server='10.1.1.11:8080'):
    "Boot host with selected operating system"

    _boot_timeout = int(boot_timeout)

    if _boot_timeout < 60:
        warn('Boot timeout value too small, using 60 seconds')
        _boot_timeout = '60'

    host_os_vals = os_list.split(',')
    if len(env.all_hosts) < len(host_os_vals):
        abort('Number of OSs specified must be the same as number of hosts')
    # duplicate last one until we reach correct length
    while len(host_os_vals) < len(env.all_hosts):
        host_os_vals.append(host_os_vals[-1])        

    # get type of current host
    htype = get_type_cached(env.host_string)

    # get dictionary from host and OS lists
    host_os = dict(zip(env.all_hosts, host_os_vals))

    # os we want
    target_os = host_os.get(env.host_string, '')

    kern = ''
    target_kern = ''
    if target_os == 'Linux':
        if env.host_string in config.TPCONF_router:
            target_kern = linux_kern_router
        else:
            target_kern = linux_kern_hosts

        kern = run('uname -r')
        if target_kern == 'running' or target_kern == 'current':
            target_kern = kern

    if target_os != '' and (
            force_reboot == '1' or target_os != htype or target_kern != kern):
        # write pxe config file
        pxe_template = config.TPCONF_script_path + \
            '/conf-macaddr_xx\:xx\:xx\:xx\:xx\:xx.ipxe.in'
        mac = get_netmac_cached(env.host_string)
        file_name = 'conf-macaddr_' + mac + '.ipxe'

	hdd_partition = ''
        if target_os == 'CYGWIN':
            hdd_partition = '(hd0,0)'
        elif target_os == 'Linux':
            hdd_partition = '(hd0,1)'
        elif target_os == 'FreeBSD':
            hdd_partition = '(hd0,2)' 
        try:
            hdd_partition = config.TPCONF_os_partition[target_os]
        except AttributeError:
            pass

        if target_os == 'Linux':
            # could remove the if, but might need in future if we specify
            # different options for router and hosts
            if env.host_string in config.TPCONF_router:
                config_str = 'root ' + hdd_partition + '; kernel \/boot\/vmlinuz-' + \
                    target_kern + ' splash=0 quiet showopts; ' + \
                    'initrd \/boot\/initrd-' + target_kern
            else:
                config_str = 'root ' + hdd_partition + '; kernel \/boot\/vmlinuz-' + \
                    target_kern + ' splash=0 quiet showopts; ' + \
                    'initrd \/boot\/initrd-' + target_kern
        elif target_os == 'CYGWIN':
            if env.host_string in config.TPCONF_router:
                abort('Router has no Windows')
            config_str = 'root ' + hdd_partition + '; chainloader +1'
        elif target_os == 'FreeBSD':
            config_str = 'root ' + hdd_partition + '; chainloader +1'
        elif target_os == 'Darwin':
            pass
        else:
            abort('Unknown OS %s' % target_os)

        if force_reboot == '1':
            puts('Forced reboot (TPCONF_force_reboot = \'1\')')
        puts(
            'Switching %s from OS %s %s to OS %s %s' %
            (env.host_string, htype, kern, target_os, target_kern))

        if htype != 'Darwin':
            # no PXE booting for Macs
            local(
                'cat %s | sed -e "s/@CONFIG@/%s/" | sed -e "s/@TFTPSERVER@/%s/" > %s' %
                (pxe_template, config_str, tftp_server, file_name))
            # make backup of current file if not exists yet
            full_file_name = config.TPCONF_tftpboot_dir + '/' + file_name
            full_file_name_backup = config.TPCONF_tftpboot_dir + \
                '/' + file_name + '.bak'
            with settings(warn_only=True):
                local('mv -f %s %s' % (full_file_name, full_file_name_backup))
                local('rm -f %s' % full_file_name)
            # XXX should combine the next two into one shell command to make it
            # more atomic
            local('cp %s %s' % (file_name, config.TPCONF_tftpboot_dir))
            local('chmod a+rw %s' % full_file_name)
            if file_prefix != '':
                file_name2 = local_dir + '/' + file_prefix + '_' + file_name
                local('mv %s %s' % (file_name, file_name2))

        # reboot
        with settings(warn_only=True):
            if htype == 'Linux' or htype == 'FreeBSD' or htype == 'Darwin':
                run('shutdown -r now', pty=False)
            elif htype == 'CYGWIN':
                run('shutdown -r -t 0', pty=False)

        # give some time to shutdown
        puts('Waiting for reboot...')
        time.sleep(60)

        # wait until up
        t = 60
        while t <= _boot_timeout:
            # ret = local('ping -c 1 %s' % env.host_string) # ping works before
            # ssh and can't ping from inside jail
            with settings(warn_only=True):
                try:
                    ret = run(
                        'echo waiting for OS %s to start' %
                        target_os,
                        timeout=2,
                        pty=False)
                    if ret.return_code == 0:
                        break
                except:
                    pass

            time.sleep(8)
            t += 10

        if t > _boot_timeout and do_power_cycle == '1':
            # host still not up, may be hanging so power cycle it

            puts('Power cycling host...')
            execute(power_cycle)
            puts('Waiting for reboot...')
            time.sleep(60)

            # wait until up
            t = 60
            while t <= _boot_timeout:
                # ret = local('ping -c 1 %s' % env.host_string) # ping works
                # before ssh and can't ping from inside jail
                with settings(warn_only=True):
                    try:
                        ret = run(
                            'echo waiting for OS %s to start' %
                            target_os,
                            timeout=2,
                            pty=False)
                        if ret.return_code == 0:
                            break
                    except:
                        pass

                time.sleep(8)
                t += 10

        # finally check if host is up again with desired OS

        # XXX if the following fails because we can't connect to host Fabric
        # will crash with weird error (not super important since we would abort
        # anyway but annoying)
        htype = execute(get_type, hosts=[env.host_string])[env.host_string]
        if target_os == 'Linux':
            kern = run('uname -r')

        if htype == target_os and kern == target_kern:
                puts(
                'Host %s running OS %s %s' %
                (env.host_string, target_os, target_kern))
        else:
            abort(
                'Error switching %s to OS %s %s' %
                (env.host_string, target_os, target_kern))
    else:
        if target_os == '':
            target_os = htype
        puts(
            'Leaving %s as OS %s %s' %
            (env.host_string, target_os, target_kern))


# Boot host into right kernel/OS
# Parameters:
#       file_prefix: prefix for generated pxe boot file
#       local_dir: directory to put the generated .ipxe files in
def init_os_hosts(file_prefix='', local_dir='.'):

    # create hosts list
    hosts_list = config.TPCONF_router + config.TPCONF_hosts 
 
    # create comma-separated string of OSs to pass to init_os task
    os_list = []
    for host in hosts_list:
        os_list.append(config.TPCONF_host_os[host])
    os_list_str = ','.join(os_list)

    # for backwards compatibility we need to check if TPCONF_linux_kern_router
    # and TPCONF_linux_kern_hosts exist using the try/except
    linux_kern_router = '3.10.18-vanilla-10000hz'
    try:
        if config.TPCONF_linux_kern_router != '':
            linux_kern_router = config.TPCONF_linux_kern_router
    except AttributeError:
        pass

    linux_kern_hosts = '3.9.8-desktop-web10g'
    try:
        if config.TPCONF_linux_kern_hosts != '':
            linux_kern_hosts = config.TPCONF_linux_kern_hosts
    except AttributeError:
        pass
  
    do_power_cycle = '0'
    try:
        do_power_cycle = config.TPCONF_do_power_cycle
    except AttributeError:
        pass

    tftp_server = '10.1.1.11:8080'
    try:
        tftp_server = config.TPCONF_tftpserver
    except AttributeError:
        pass

    execute(init_os, file_prefix, os_list=os_list_str,
            force_reboot=config.TPCONF_force_reboot,
            do_power_cycle=do_power_cycle,
            boot_timeout=config.TPCONF_boot_timeout, local_dir=local_dir,
            linux_kern_router=linux_kern_router, linux_kern_hosts=linux_kern_hosts,
            tftp_server=tftp_server,
            hosts=hosts_list)


# Initialise host
# Parameters:
# interfaces: list of testbed network interfaces (XXX this parameter
# should be removed I think, leftover from an old version)
@task
@parallel
def init_host(interfaces=''):
    "Perform host initialization"

    # get type of current host
    htype = get_type_cached(env.host_string)

    if htype == 'FreeBSD':
        # record the number of reassembly queue overflows
        run('sysctl net.inet.tcp.reass.overflows')

        # disable tso
        run('sysctl net.inet.tcp.tso=0')

        # send and receiver buffer max (2MB by default on FreeBSD 9.2 anyway)
        run('sysctl net.inet.tcp.sendbuf_max=2097152')
        run('sysctl net.inet.tcp.recvbuf_max=2097152')

        # clear host cache quickly, otherwise successive TCP connections will
        # start with ssthresh and cwnd from the end of most recent tcp
        # connections to the same host
        run('sysctl net.inet.tcp.hostcache.expire=1')
        run('sysctl net.inet.tcp.hostcache.prune=5')
        run('sysctl net.inet.tcp.hostcache.purge=1')

    elif htype == 'Linux':

        # disable host cache
        run('sysctl net.ipv4.tcp_no_metrics_save=1')
        # disable auto-tuning of receive buffer
        run('sysctl net.ipv4.tcp_moderate_rcvbuf=0')

        if interfaces == '':
            interfaces = get_netint_cached(env.host_string, int_no=-1)

        # disable all offloading, e.g. tso = tcp segment offloading
        for interface in interfaces:
            run('ethtool -K %s tso off' % interface)
            run('ethtool -K %s gso off' % interface)
            run('ethtool -K %s lro off' % interface)
            run('ethtool -K %s gro off' % interface)
            run('ethtool -K %s ufo off' % interface)

        # send and recv buffer max (set max to 2MB)
        run('sysctl net.core.rmem_max=2097152')
        run('sysctl net.core.wmem_max=2097152')
        # tcp recv buffer max (min 4kB, default 87kB, max 6MB; this is standard
        # on kernel 3.7)
        run('sysctl net.ipv4.tcp_rmem=\'4096 87380 6291456\'')
        # tcp send buffer max (min 4kB, default 32kB, max 6MB; doubled default
        # otherwise standard on kernel 3.7)
        run('sysctl net.ipv4.tcp_wmem=\'4096 65535 4194304\'')

    elif htype == 'Darwin':

        # disable tso
        run('sysctl -w net.inet.tcp.tso=0')
	# diable lro (off by default anyway)
        run('sysctl -w net.inet.tcp.lro=0')

        # disable auto tuning of buffers
        run('sysctl -w net.inet.tcp.doautorcvbuf=0')
        run('sysctl -w net.inet.tcp.doautosndbuf=0')

        # send and receive buffer max (2MB). kern.ipc.maxsockbuf max be the sum
        # (but is 4MB by default anyway)
        run('sysctl -w kern.ipc.maxsockbuf=4194304')
        run('sysctl -w net.inet.tcp.sendspace=2097152')
	run('sysctl -w net.inet.tcp.recvspace=2097152')

        # set the auto receive/send buffer max to 2MB as well just in case
        run('sysctl -w net.inet.tcp.autorcvbufmax=2097152')
        run('sysctl -w net.inet.tcp.autosndbufmax=2097152')

    elif htype == 'CYGWIN':

        # disable ip/tcp/udp offload processing
        run('netsh int tcp set global chimney=disabled', pty=False)
        run('netsh int ip set global taskoffload=disabled', pty=False)
        # enable tcp timestamps
        run('netsh int tcp set global timestamps=enabled', pty=False)
        # disable tcp window scaling heuristics, enforce user-set auto-tuning
        # level
        run('netsh int tcp set heuristics disabled', pty=False)

        if interfaces == '':
            interfaces = get_netint_cached(env.host_string, int_no=-1)

        for interface in interfaces:
            # stop and restart interface to make the changes
            run('netsh int set int "Local Area Connection %s" disabled' %
                interface, pty=False)
            run('netsh int set int "Local Area Connection %s" enabled' %
                interface, pty=False)

        # XXX send and recv buffer max (don't know how to set this)
        # defaults to 256 receive and 512 transmits buffer (each 1500bytes?),
        # so 3-4MB receive and 7-8MB send)


# Enable/disable ECN
# paramters: ecn: '0' (disable ecn), '1' (enable ecn)
@task
@parallel
def init_ecn(ecn='0'):
    "Initialize whether ECN is used or not"

    if ecn != '0' and ecn != '1':
        abort("Parameter ecn must be set to '0' or '1'")

    # get type of current host
    htype = get_type_cached(env.host_string)

    # enable/disable RED
    if htype == 'FreeBSD':
        run('sysctl net.inet.tcp.ecn.enable=%s' % ecn)
    elif htype == 'Linux':
        run('sysctl net.ipv4.tcp_ecn=%s' % ecn)
    elif htype == 'Darwin':
       run('sysctl -w net.inet.tcp.ecn_initiate_out=%s' % ecn)
       run('sysctl -w net.inet.tcp.ecn_negotiate_in=%s' % ecn)
    elif htype == 'CYGWIN':
        if ecn == '1':
            run('netsh int tcp set global ecncapability=enabled', pty=False)
        else:
            run('netsh int tcp set global ecncapability=disabled', pty=False)
    else:
        abort("Can't enable/disable ECN for OS '%s'" % htype)


# Function to replace the variable names with the values
def _param(name, adict):
    "Get parameter value"

    val = adict.get(name, '')
    if val == '':
        warn('Parameter %s is undefined' % name)

    return val


# Set congestion control algo parameters
# Parameters:
#       algo: name of congestion control algorithm
#             (newreno, cubic, cdg, hd, htcp, compound, vegas)
#	args: arguments
#	kwargs: keyword arguments
def init_cc_algo_params(algo='newreno', *args, **kwargs):
    "Initialize TCP congestion control algorithm"

    host_config = config.TPCONF_host_TCP_algo_params.get(env.host_string, None)
    if host_config is not None:
        algo_params = host_config.get(algo, None)
        if algo_params is not None:
            # algo params is a list of strings of the form sysctl=value
            for entry in algo_params:
                sysctl_name, val = entry.split('=')
                sysctl_name = sysctl_name.strip()
                val = val.strip()
                # eval the value (could be variable name)
                val = re.sub(
                    "(V_[a-zA-Z0-9_-]*)",
                    "_param('\\1', kwargs)",
                    val)
                val = eval('%s' % val)
                # set with sysctl
                run('sysctl %s=%s' % (sysctl_name, val))


# Set congestion control algo
# Parameters:
#	algo: name of congestion control algorithm
#              (newreno, cubic, cdg, hd, htcp, compound, vegas) or
#	      'default' which will choose the default based on the OS or
#	      'host<N>' where <N> ist an integer starting with 0 to select
#                       OS from TPCONF_host_TCP_algos
#       args: arguments
#       kwargs: keyword arguments
@task
@parallel
def init_cc_algo(algo='default', *args, **kwargs):
    "Initialize TCP congestion control algorithm"

    if algo[0:4] == 'host':
        arr = algo.split('t')
        if len(arr) == 2 and arr[1].isdigit():
            num = int(arr[1])
        else:
            abort('If you specify host<N>, the <N> must be an integer number')

        algo_list = config.TPCONF_host_TCP_algos.get(env.host_string, [])
        if len(algo_list) == 0:
            abort(
                'No TCP congestion control algos defined for host %s' %
                env.host_string)

        if num > len(algo_list) - 1:
            warn(
                'No TCP congestion control algo specified for <N> = %d, ' \
                'setting <N> = 0' % num)
            num = 0
        algo = algo_list[num]

        puts('Selecting TCP congestion control algorithm: %s' % algo)

    if algo != 'default' and algo != 'newreno' and algo != 'cubic' and \
            algo != 'cdg' and algo != 'htcp' and \
            algo != 'compound' and algo != 'hd' and algo != 'vegas':
        abort(
            'Available TCP algorithms: ' +
            'default, newreno, cubic, cdg, hd, htcp, compound, vegas')

    # get type of current host
    htype = get_type_cached(env.host_string)

    if htype == 'FreeBSD':
        if algo == 'newreno' or algo == 'default':
            algo = 'newreno'
        elif algo == 'cubic':
            with settings(warn_only=True):
                ret = run('kldstat | grep cc_cubic')
            if ret.return_code != 0:
                run('kldload cc_cubic')
        elif algo == 'hd':
            with settings(warn_only=True):
                ret = run('kldstat | grep cc_hd')
            if ret.return_code != 0:
                run('kldload cc_hd')
        elif algo == 'htcp':
            with settings(warn_only=True):
                ret = run('kldstat | grep cc_htcp')
            if ret.return_code != 0:
                run('kldload cc_htcp')
        elif algo == 'cdg':
            with settings(warn_only=True):
                ret = run('kldstat | grep cc_cdg')
            if ret.return_code != 0:
                # cdg is only available by default since FreeBSD 9.2
                run('kldload cc_cdg')
        elif algo == 'vegas':
            with settings(warn_only=True):
                ret = run('kldstat | grep cc_vegas')
            if ret.return_code != 0:
                run('kldload cc_vegas')
        else:
            abort("Congestion algorithm '%s' not supported by FreeBSD" % algo)

        run('sysctl net.inet.tcp.cc.algorithm=%s' % algo)

    elif htype == 'Linux':
        if algo == 'newreno':
            # should be there by default
            algo = 'reno'
        elif algo == 'cubic' or algo == 'default':
            # should also be there by default
            algo = 'cubic'
        elif algo == 'htcp':
            run('modprobe tcp_htcp')
        elif algo == 'vegas':
            run('modprobe tcp_vegas')
        else:
            abort("Congestion algorithm '%s' not supported by Linux" % algo)

        run('sysctl net.ipv4.tcp_congestion_control=%s' % algo)

    elif htype == 'Darwin':
        if algo == 'newreno' or algo == 'default':
            algo = 'newreno'
        else:
            abort("Congestion algorithm '%s' not supported by MacOS" % algo)

    elif htype == 'CYGWIN':
        if algo == 'newreno' or algo == 'default':
            run('netsh int tcp set global congestionprovider=none', pty=False)
        elif algo == 'compound':
            run('netsh int tcp set global congestionprovider=ctcp', pty=False)
        else:
            abort("Congestion algorithm '%s' not supported by Windows" % algo)
    else:
        abort("Can't set TCP congestion control algo for OS '%s'" % htype)

    # now set the cc algorithm parameters
    execute(init_cc_algo_params, algo=algo, *args, **kwargs)


# Initialise dummynet
# assume: ipfw is running in open mode, so we can login to the machine
# Parameters:
def init_dummynet():

    with settings(warn_only=True):
        ret = run('kldstat | grep dummynet')

    if ret.return_code != 0:
        # this will load ipfw and dummynet
        run('kldload dummynet')
        # check again (maybe a bit paranoid)
        run('kldstat | grep dummynet')

    # allow packet to go through multiple pipes
    run('sysctl net.inet.ip.fw.one_pass=0')
    # disable firewall and flush everything
    run('ipfw disable firewall')
    run('ipfw -f flush')
    run('ipfw -f pipe flush')
    run('ipfw -f queue  flush')
    # make sure we add a final allow and enable firewall
    run('ipfw add 65534 allow ip from any to any')
    run('ipfw enable firewall')


# Initialise Linux tc
# assume: the Linux firewall is turned off or "open"
# Parameters:
def init_tc():

    # load pseudo interface mdoule
    run('modprobe ifb')

    # get all interfaces
    interfaces = get_netint_cached(env.host_string, int_no=-1)

    # delete all rules
    for interface in interfaces:
        with settings(warn_only=True):
            # run with warn_only since it will return error if no tc commands
            # exist
            run('tc qdisc del dev %s root' % interface)

        # set root qdisc
        run('tc qdisc add dev %s root handle 1 htb' % interface)

    # bring up pseudo ifb interfaces (for netem)
    cnt = 0
    for interface in interfaces:
        pseudo_interface = 'ifb' + str(cnt)

        run('ifconfig %s down' % pseudo_interface)
        run('ifconfig %s up' % pseudo_interface)

        with settings(warn_only=True):
            # run with warn_only since it will return error if no tc commands
            # exist
            run('tc qdisc del dev %s root' % pseudo_interface)

        # set root qdisc
        run('tc qdisc add dev %s root handle 1 htb' % pseudo_interface)

        cnt += 1

    run('iptables -t mangle -F')
    # this is just for counting all packets
    run('iptables -t mangle -A POSTROUTING -j MARK --set-mark 0')


# Initialise the router
# Parameters:
@task
@parallel
def init_router():
    "Initialize router"

    # get type of current host
    htype = get_type_cached(env.host_string)

    if htype == 'FreeBSD':
        execute(init_dummynet)
    elif htype == 'Linux':

        interfaces = get_netint_cached(env.host_string, int_no=-1)

        # disable all offloading, e.g. tso = tcp segment offloading
        for interface in interfaces:
            run('ethtool -K %s tso off' % interface)
            run('ethtool -K %s gso off' % interface)
            run('ethtool -K %s lro off' % interface)
            run('ethtool -K %s gro off' % interface)
            run('ethtool -K %s ufo off' % interface)

        execute(init_tc)
    else:
        abort("Router must be running FreeBSD or Linux")


# Custom host initialisation
# Parameters:
#       args: arguments
#	kwargs: keyword arguments
@task
@parallel
def init_host_custom(*args, **kwargs):
    "Perform host custom host initialization"

    cmds = config.TPCONF_host_init_custom_cmds.get(env.host_string, None)
    if cmds is not None:
        for cmd in cmds:
            # replace V_ variables
            cmd = re.sub(
                "(V_[a-zA-Z0-9_-]*)",
                lambda m: "{}".format(
                    kwargs[
                        m.group(1)]),
                cmd)
            # execute
            run(cmd)


# Do all host init
# Parameters:
#	ecn: '0' ECN off, '1' ECN on
#	tcp_cc_algo: TCP congestion control algo (see init_cc_algo() for info)
def init_hosts(ecn='0', tcp_cc_algo='default', *args, **kwargs):
    execute(init_host, hosts=config.TPCONF_hosts)
    execute(init_ecn, ecn, hosts=config.TPCONF_hosts)
    execute(
        init_cc_algo,
        tcp_cc_algo,
        hosts=config.TPCONF_hosts,
        *args,
        **kwargs)
    execute(init_router, hosts=config.TPCONF_router)
    execute(
        init_host_custom,
        hosts=config.TPCONF_router +
        config.TPCONF_hosts,
        *
        args,
        **kwargs)

