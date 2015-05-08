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
## @package routersetup
# Router setup
#
# $Id: routersetup.py 1268 2015-04-22 07:04:19Z szander $

import config
from fabric.api import task, hosts, run, execute, abort, env, settings
from hostint import get_netint_cached, get_address_pair
from hosttype import get_type_cached


## Initialise single dummynet pipe
#  Same queue but different delay/loss emulation
#  @param counter Queue ID number 
#  @param source Source, can be an IP address or hostname or a subnet
#                (e.g. 192.168.1.0/24)
#  @param dest Destination, can be an IP address or hostname or a subnet
#              (e.g. 192.168.1.0/24)
#  @param rate Rate limit in bytes, e.g. 100000000 (100Mbps in bytes),
#              10kbit, 100mbit
#  @param delay Emulated delay in millieseconds
#  @param rtt Emulated rtt in millieseconds (needed only for determining 
#             queue size if not explicitly specified)
#  @param loss Loss rate
#  @param queue_size Queue size in slots (if a number) or bytes
#                    (e.g. specified as XKbytes, where X is a number)
#  @param queue_size_mult Multiply 'bdp' queue size with this factor
#                        (must be a floating point)
#  @param queue_disc Queueing discipline: fifo (default), red (RED)
#  @param queue_disc_params: If queue_disc=='red' this must be set to:
#                w_q/min_th/max_th/max_p  (see ipfw man page for details)
#  @param bidir If '0' pipe only in forward direction, if '1' two pipes (one 
#               in foward and one in backward direction)
def init_dummynet_pipe(counter='1', source='', dest='', rate='', delay='',
                       rtt='', loss='', queue_size='', queue_size_mult='1.0',
                       queue_disc='', queue_disc_params='', bidir='0'):

    queue_size = str(queue_size)
    if queue_size.lower() == 'bdp':
        # this only works if rate is specified as a number of bytes/second
        if rtt == '':
            rtt = str(2 * int(delay))
        queue_size = int(float(rate) * (float(rtt) / 1000.0) / 8)
        if queue_size < 2048:
            queue_size = 2048
        if queue_size_mult != '1.0':
            queue_size = int(float(queue_size) * float(queue_size_mult))
        queue_size = str(queue_size)

    if queue_disc != 'fifo' and queue_disc != 'red':
        abort("Only queuing disciplines for Dummynet are 'fifo' and 'red'")

    # ipfw rule number
    rule_no = str(int(counter) * 100)

    # configure pipe
    config_pipe_cmd = 'ipfw pipe %s config' % counter
    if rate != '':
        config_pipe_cmd += ' bw %sbits/s' % rate
    if delay != '':
        config_pipe_cmd += ' delay %sms' % delay
    if loss != "":
        config_pipe_cmd += ' plr %s' % loss
    if queue_size != "":
        config_pipe_cmd += ' queue %s' % queue_size
    if queue_disc == 'red':
        config_pipe_cmd += ' red %s' % queue_disc_params
    run(config_pipe_cmd)

    # create pipe rule
    create_pipe_cmd = 'ipfw add %s pipe %s ip from %s to %s out' % (
        rule_no, counter, source, dest)
    run(create_pipe_cmd)
    if bidir == '1':
        create_pipe_cmd = 'ipfw add %s pipe %s ip from %s to %s out' % (
            rule_no, counter, dest, source)
        run(create_pipe_cmd)


## Initialse tc (Linux)
## setup a class (htb qdisc) for each interface with rate limits
## setup actual qdisc (e.g. codel) as leaf qdisc for class
## then redirect traffic to pseudo interface and apply netem to emulate
## delay and/or loss
#  @param counter Queue ID number
#  @param source Source, can be an IP address or hostname or a subnet
#                (e.g. 192.168.1.0/24)
#  @param dest Destination, can be an IP address or hostname or a subnet
#              (e.g. 192.168.1.0/24)
#  @param rate Rate limit in bytes, e.g. 100000000 (100Mbps in bytes), 10kbit, 100mbit
#  @param delay Emulated delay in millieseconds
#  @param rtt Emulated rtt in millieseconds (needed only for determining 
#            queue size if not explicitly specified)
#  @param loss Loss rate
#  @param queue_size Can be in packets or bytes depending on queue_disc; if in bytes
#                    can use units, e.g. 1kb
#  @param queue_size_mult Multiply 'bdp' queue size with this factor
#                         (must be a floating point)
#  @param queue_disc fifo (mapped to pfifo, FreeBSD compatibility), fq_codel, codel, red,
#                    choke, pfifo, pie (only as patch), ...
#  @param queue_disc_params Parameters for queing discipline, see man pages for queuing
#                           disciplines
#  @param bidir If '0' (pipe only in forward direction), 
#               if '1' (two pipes in both directions)
#  @param attach_to_queue Specify number of existing queue to use, but emulate
#                         different delay/loss
def init_tc_pipe(counter='1', source='', dest='', rate='', delay='', rtt='', loss='',
                 queue_size='', queue_size_mult='1.0', queue_disc='', 
                 queue_disc_params='', bidir='0', attach_to_queue=''):

    # compatibility with FreeBSD
    if queue_disc == 'fifo':
        # pfifo is the default for HTB classes
        queue_disc = 'pfifo'

    queue_size = str(queue_size)
    if queue_size.lower() == 'bdp':
        _rate = rate.replace('kbit', '000')
        _rate = _rate.replace('mbit', '000000')
        if rtt == '':
            rtt = str(2 * int(delay))
        if queue_disc == 'pfifo' or queue_disc == 'codel' or \
           queue_disc == 'fq_codel' or queue_disc == 'pie':
            # queue size in packets
            avg_packet = 600  # average packet size
            queue_size = int(
                float(_rate) * (float(rtt) / 1000.0) / 8 / avg_packet)
            if queue_size_mult != '1.0':
                queue_size = int(float(queue_size) * float(queue_size_mult))
            if queue_size < 1:
                queue_size = 1  # minimum 1 packet
            queue_size = str(queue_size)
        elif queue_disc == 'bfifo' or queue_disc == 'red':
            # queue size in bytes
            queue_size = int(float(_rate) * (float(rtt) / 1000.0) / 8)
            if queue_size_mult != '1.0':
                queue_size = int(float(queue_size) * float(queue_size_mult))
            if queue_size < 2048:
                queue_size = 2048  # minimum 2kB
            queue_size = str(queue_size)
        else:
            abort(
                'Can\'t specify \'bdp\' for queuing discipline %s' %
                queue_disc)

    # class/handle numbers
    class_no = str(int(counter) + 0)
    if attach_to_queue == '':
        queue_class_no = class_no
    else:
        # if attach_to_queue is set we attach this to existing (previously
        # configured pipe). this means packets will go through an existing htb
        # and leaf qdisc, but a separate netem.
        # so we can have different flows going through the same bottleneck
        # queue, but with different emulated delays or loss rates
        queue_class_no = attach_to_queue
    netem_class_no = class_no
    qdisc_no = str(int(counter) + 1000)
    netem_no = str(int(counter) + 1000)

    # disciplines: fq_codel, codel, red, choke, pfifo, pfifo_fast (standard
    # magic), pie (only as patch), ...
    if queue_disc == '':
        queue_disc = 'pfifo'
    # for pie we need to make sure the kernel module is loaded (for kernel pre
    # 3.14 only, for new kernels it happens automatically via tc use!)
    if queue_disc == 'pie':
        with settings(warn_only=True):
            run('modprobe pie')

    if rate == '':
        rate = '1000mbit'
    if queue_size == '':
        # set default queue size to 1000 packet (massive but default for e.g.
        # codel)
        queue_size = '1000'

    if loss != '':
        # convert to percentage
        loss = str(float(loss) * 100)

    interfaces = get_netint_cached(env.host_string, int_no=-1)

    # our approach works as follows:
    # - shaping, aqm and delay/loss emulation is done on egress interface
    #   (as usual)
    # - use htb qdisc for rate limiting with the aqm qdisc (e.g. pfifo, codel)
    #   as leave node
    # - after shaping and aqm, emulate loss and delay with netem
    # - for each "pipe" we setup a new class on all (two) interfaces
    # - if pipes are unidirectional a class is only used on one of the two ifaces;
    #   otherwise it is used on both interfaces (XXX could optimise the
    #   unidirectional case and omit unused pipes)
    # - traffic flow is as follows:
    #   1. packets are marked by iptables in mangle table POSTROUTING hook
    #      depending on defined source/dest (unique mark for each pipe)
    #   2. marked packets are classified into appropriate class (1-1 mapping
    #      between marks and classes) and redirected to pseudo interface
    #   3. pseudo interface does the shaping with htb and aqm (leaf qdisc)
    #   4. packets go back to actual interface
    #   5. actual interface does network emulation (delay/loss), here htb is set to
    # max rate (1Gbps) and pfifo is used (effectively no shaping or aqm here)

    # note that according to my information the htb has a build-in buffer of 1
    # packet as well (cannot be changed)

    cnt = 0
    for interface in interfaces:

        pseudo_interface = 'ifb' + str(cnt)

        # config rate limiting on pseudo interface
        config_tc_cmd = 'tc class add dev %s parent 1: classid 1:%s htb rate %s ceil %s' % \
            (pseudo_interface, queue_class_no, rate, rate)
        if attach_to_queue == '':
            run(config_tc_cmd)

        # config queuing discipline and buffer limit on pseudo interface
        config_tc_cmd = 'tc qdisc add dev %s parent 1:%s handle %s: %s limit %s %s' % \
            (pseudo_interface,
             queue_class_no,
             qdisc_no,
             queue_disc,
             queue_size,
             queue_disc_params)
        if attach_to_queue == '':
            run(config_tc_cmd)

        # configure filter to classify traffic based on mark on pseudo device
        config_tc_cmd = 'tc filter add dev %s protocol ip parent 1: ' \
                        'handle %s fw flowid 1:%s' % (
                            pseudo_interface, class_no, queue_class_no)
        run(config_tc_cmd)

        # configure class for actual interface with max rate
        config_tc_cmd = 'tc class add dev %s parent 1: classid 1:%s ' \
                        'htb rate 1000mbit ceil 1000mbit' % \
            (interface, netem_class_no)
        run(config_tc_cmd)

        # config netem on actual interface
        config_tc_cmd = 'tc qdisc add dev %s parent 1:%s handle %s: ' \
                        'netem limit 1000' % (
                            interface, netem_class_no, netem_no)
        if delay != "":
            config_tc_cmd += " delay %sms" % delay
        if loss != "":
            config_tc_cmd += " loss %s%%" % loss
        run(config_tc_cmd)

        # configure filter to redirect traffic to pseudo device first and also
        # classify traffic based on mark after leaving the pseudo interface traffic
        # will go back to actual interface
        config_tc_cmd = 'tc filter add dev %s protocol ip parent 1: handle %s ' \
                        'fw flowid 1:%s action mirred egress redirect dev %s' % \
            (interface, class_no, netem_class_no, pseudo_interface)
        run(config_tc_cmd)

        cnt += 1

    # filter on specific ips
    config_it_cmd = 'iptables -t mangle -A POSTROUTING -s %s -d %s -j MARK --set-mark %s' % \
        (source, dest, class_no)
    run(config_it_cmd)
    if bidir == '1':
        config_it_cmd = 'iptables -t mangle -A POSTROUTING -s %s -d %s -j MARK --set-mark %s' % \
            (dest, source, class_no)
        run(config_it_cmd)


## Show dummynet pipes
def show_dummynet_pipes():
    run('ipfw -a list')
    run('ipfw -a pipe list')


## Show tc setup
def show_tc_setup():

    interfaces = get_netint_cached(env.host_string, int_no=-1)

    run('tc -d -s qdisc show')
    cnt = 0
    for interface in interfaces:
        run('tc -d -s class show dev %s' % interface)
        run('tc -d -s filter show dev %s' % interface)
        pseudo_interface = 'ifb' + str(cnt)
        run('tc -d -s class show dev %s' % pseudo_interface)
        run('tc -d -s filter show dev %s' % pseudo_interface)
        cnt += 1
    run('iptables -t mangle -vL')


## Show pipe setup
@task
def show_pipes():
    "Show pipe setup on router"

    # get type of current host
    htype = get_type_cached(env.host_string)

    if htype == 'FreeBSD':
        execute(show_dummynet_pipes)
    elif htype == 'Linux':
        execute(show_tc_setup)
    else:
        abort("Router must be running FreeBSD or Linux")


## Configure a pipe on the router, encompassing rate shaping, AQM, 
## loss/delay emulation
## For parameter explanations see descriptions of init_dummynet_pipe() and init_tc_pipe()
## Note: attach_to_queue only works for Linux
@task
def init_pipe(counter='1', source='', dest='', rate='', delay='', rtt='', loss='',
              queue_size='', queue_size_mult='1.0', queue_disc='', 
              queue_disc_params='', bidir='0', attach_to_queue=''):
    "Configure pipe on router, including rate shaping, AQM, loss/delay emulation"

    # get internal addresses
    dummy, source_internal = get_address_pair(source)
    dummy, dest_internal = get_address_pair(dest)

    # get type of current host
    htype = get_type_cached(env.host_string)

    if htype == 'FreeBSD':
        execute(
            init_dummynet_pipe,
            counter,
            source_internal,
            dest_internal,
            rate,
            delay,
            rtt,
            loss,
            queue_size,
            queue_size_mult,
            queue_disc,
            queue_disc_params,
            bidir)
    elif htype == 'Linux':
        execute(
            init_tc_pipe,
            counter,
            source_internal,
            dest_internal,
            rate,
            delay,
            rtt,
            loss,
            queue_size,
            queue_size_mult,
            queue_disc,
            queue_disc_params,
            bidir,
            attach_to_queue)
    else:
        abort("Router must be running FreeBSD or Linux")
