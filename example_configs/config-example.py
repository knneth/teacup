# example configuration
#

import sys
import datetime
from fabric.api import env


#
# Fabric config
#

# User and password
env.user = 'root'
env.password = 'rootpw'

# Set shell used to execute commands
env.shell = '/bin/sh -c'

# SSH connection timeout
env.timeout = 5

# Number of concurrent processes
env.pool_size = 10


#
# Testbed config
#

# Path to scripts
TPCONF_script_path = '/home/teacup/teacup-0.8'
# DO NOT remove the following line
sys.path.append(TPCONF_script_path)

# Set debugging level (0 = no debugging info output) 
TPCONF_debug_level = 0

# TFTP server to use
TPCONF_tftpserver = '10.1.1.11:8080'

# Path to tftp server handling the pxe boot
# Setting this to an empty string '' means no PXE booting, and TPCONF_host_os
# and TPCONF_force_reboot are simply ignored
TPCONF_tftpboot_dir = '/tftpboot'

# Host lists
TPCONF_router = ['newtcp5', ]
TPCONF_hosts = [
    'newtcp1', 'newtcp2', 'newtcp3', 'newtcp4', ]

# Map external IPs to internal IPs
TPCONF_host_internal_ip = {
    'newtcp5':  ['172.16.10.1', '172.16.11.1'],
    'newtcp1': ['172.16.10.2'],
    'newtcp2': ['172.16.10.3'],
    'newtcp3': ['172.16.11.2'],
    'newtcp4': ['172.16.11.3'],
}

# If set to '1' the hosts are configured with the above internal IPs.
# If set to '0' no cnfiguration is done, and it is assumed that the IPs
# configured above in TPCONF_host_internal_ip are correct.
# XXX network interface IDs are currently hardcoded in the init_topology
#     task
TPCONF_config_topology = '1'

# Host name or IP of switch hosts are connected to
TPCONF_topology_switch = 'switch2'

# Prefix for switch port names hosts are connected to
TPCONF_topology_switch_port_prefix = 'Gi1/0/'

# Offset between number in host name and switch port number
TPCONF_topology_switch_port_offset = 5

#
# Experiment settings
#

# Maximum allowed time difference between machines in seconds
# otherwise experiment will abort cause synchronisation problems
TPCONF_max_time_diff = 1

# Experiment name prefix used if not set on the command line
# The command line setting will overrule this config setting
now = datetime.datetime.today()
TPCONF_test_id = now.strftime("%Y%m%d-%H%M%S") + '_experiment'

# Directory to store log files on remote host
TPCONF_remote_dir = '/tmp/'

# Operating system config, machines that are not explicitely listed are
# left as they are (OS can be 'Linux', 'FreeBSD', 'CYGWIN' or 'Darwin')
TPCONF_host_os = {
    'newtcp5': 'Linux',
    'newtcp1': 'FreeBSD',
    'newtcp2': 'Linux',
    'newtcp3': 'Linux',
    'newtcp4': 'CYGWIN',
}

# Specify the Linux kernel to use, only used for machines running Linux
# (basically the full name without the vmlinuz-)
# Set variable to 'running' to choose currently running kernel
TPCONF_linux_kern_router = '3.17.4-vanilla-10000hz'
TPCONF_linux_kern_hosts = '3.17.4-vanilla-web10g'
#TPCONF_linux_kern_router = '3.14.5-vanilla-10000hz'
#TPCONF_linux_kern_hosts = '3.7.10-1.16-desktop-web10g'

# Force reboot
# If set to '1' will force a reboot of all hosts
# If set to '0' only hosts where OS is not the desired OS will be rebooted
TPCONF_force_reboot = '1'

# Time to wait for reboot in seconds (integer)
# if host is not back up within this time we either power cycle
# (if TPCONF_power_cycle is '1') or we give up
# Minimum timeout is 60 seconds
TPCONF_boot_timeout = 100

# If host does not come up within timeout force power cycle
# If set to '1' force power cycle if host not up within timeout
# If set to '0' never force power cycle
TPCONF_do_power_cycle = '0'

# Map OS to partition on hard disk (note the partition must be specified
# in the GRUB4DOS format, _not_ GRUB2 format) 
TPCONF_os_partition = {
	'CYGWIN':  '(hd0,0)',
	'Linux':   '(hd0,1)',
	'FreeBSD': '(hd0,2)',
}

# Maps host to power controller IP (or name) and power controller port number
TPCONF_host_power_ctrlport = {
    'newtcp5': ('10.0.0.100', '1'),
    'newtcp1': ('10.0.0.100', '2'),
    'newtcp2': ('10.0.0.100', '3'),
    'newtcp3': ('10.0.0.100', '4'),
    'newtcp4': ('10.0.0.100', '5'),
}

# Power controller admin user name
TPCONF_power_admin_name = 'admin'
# Power controller admin user password
TPCONF_power_admin_pw = env.password

# Type of power controller. Currently supported are only:
# IP Power 9258HP (9258HP) and Serverlink SLP-SPP1008-H (SLP-SPP1008)
TPCONF_power_ctrl_type = 'SLP-SPP1008'

# Time offset measurement options
# Enable broadcast ping on external/control interfaces
TPCONF_bc_ping_enable = '1'
# Specify rate of pings in packets/second
TPCONF_bc_ping_rate = 1
# Specify multicast address to use (must be broadcast or multicast address)
# If this is not specified, byt deafult the ping will be send to the subnet
# broadcast address.
TPCONF_bc_ping_address = '224.0.1.199'

# Specify the poll interval for web10g data logging in millieseconds (smallest
# supported value is currently 1ms). This is used for web10g on Linux as well
# as the EStats logger on Windows. The default value is 10ms.
TPCONF_web10g_poll_interval = 10 

# List of router queues/pipes

# Each entry is a tuple. The first value is the queue number and the second value
# is a comma separated list of parameters (see routersetup.py:init_pipe()).
# Queue numbers must be unique.

# Note that variable parameters must be either constants or or variable names
# defined by the experimenter. Variables are evaluated during runtime. Variable
# names must start with a 'V_'. Parameter names can only contain numbes, letter
# (upper and lower case), underscores (_), and hypen/minus (-).

# All variables must be defined in TPCONF_variable_list (see below).

# Note parameters must be configured appropriately for the router OS, e.g. there
# is no CoDel on FreeBSD; otherwise the experiment will abort witn an error.

TPCONF_router_queues = [
    # Can specify external addresses (will be mapped to the first internal
    # address according to TPCONF_host_internal_ip)
    #( '1', " source='newtcp1', dest='newtcp3', delay=V_delay, bidir='1' " ),
    # Can specify internal interfaces
    #( '1', " source='172.16.10.2', dest='172.16.11.2', delay=V_delay, bidir='1' " ),
    # With internal addresses we can use masks
    #( '1', " source='172.16.10.0/24', dest='172.16.11.0/24', delay=V_delay, "
    #       " bidir='1' " ),

    # Set same delay for every host
    ('1', " source='172.16.10.0/24', dest='172.16.11.0/24', delay=V_delay, "
     " loss=V_loss, rate=V_up_rate, queue_disc=V_aqm, queue_size=V_bsize "),
    ('2', " source='172.16.11.0/24', dest='172.16.10.0/24', delay=V_delay, "
     " loss=V_loss, rate=V_down_rate, queue_disc=V_aqm, queue_size=V_bsize "),

    # Demonstrate attach_to_queue with Linux router to create a single queue
    # but emulate different delays and/or loss rates
    # Also shows that parameters can be varied by using mathematical operations
    #( '1', " source='172.16.10.2', dest='172.16.11.0/24', delay=V_delay, "
    #       " loss=V_loss, rate=V_up_rate, queue_disc=V_aqm, queue_size=V_bsize " ),
    #( '2', " source='172.16.11.0/24', dest='172.16.10.2', delay=V_delay, "
    #       " loss=V_loss, rate=V_down_rate, queue_disc=V_aqm, queue_size=V_bsize " ),
    #( '3', " source='172.16.10.3', dest='172.16.11.0/24', delay=2*V_delay, "
    #       " loss=V_loss, attach_to_queue='1' " ),
    #( '4', " source='172.16.11.0/24', dest='172.16.10.3', delay=2*V_delay, "
    #       " loss=V_loss, attach_to_queue='2' " ),
]

# List of traffic generators

# Each entry is a 3-tuple. the first value of the tuple must be a float and is the
# time relative to the start of the experiment when tasks are excuted. If two tasks
# have the same start time their start order is arbitrary. The second entry of the
# tuple is the task number and  must be a unique integer (used as ID for the process).
# The last value of the tuple is a comma separated list of parameters (see the tasks
# defined in trafficgens.py); the first parameter of this list must be the
# task name.

# Client and server can be specified using the external/control IP addresses or host
# names. Then the actual interface used is the _first_ internal address (according to
# TPCONF_host_internal_ip). Alternativly, client and server can be specified as
# internal addresses, which allows to use any internal interfaces configured.

# More complicated scenario:
# newtcp1: DASH client
# newtcp2: download client
# newtcp3: DASH server
# newtcp4: download server
traffic_dash_plus_download = [
    ('0.0', '1', " start_http_server, server='newtcp3', port=80 "),
    ('0.0', '2', " create_http_dash_content, server='newtcp3', duration=2*V_duration, "
     " rates=V_dash_rates, cycles='5, 10' "),

    # Create DASH-like flows
    ('0.5', '3', " start_httperf_dash, client='newtcp1', server='newtcp3', port=80, "
     " duration=V_duration, rate=V_dash_rate, cycle=5, prefetch=2.0, "
     " prefetch_timeout=2.0 "),
    ('0.5', '4', " start_httperf_dash, client='newtcp1', server='newtcp3', port=80, "
     " duration=V_duration, rate=V_dash_rate, cycle=10, prefetch=2.0, "
     " prefetch_timeout=2.0 "),

    # Download traffic
    ('0.0', '5', " start_iperf, client='newtcp2', server='newtcp4', port=5000, "
     " duration=V_duration "),
    ('0.0', '6', " start_iperf, client='newtcp2', server='newtcp4', port=5001, "
     " duration=V_duration "),
]

# THIS is the traffic generator setup we will use
TPCONF_traffic_gens = traffic_dash_plus_download 

# Parameter ranges

# Duration in seconds
TPCONF_duration = 30

# Number of runs for each setting
TPCONF_runs = 1

# If '1' enable ecn for all hosts, if '0' disable ecn for all hosts
TPCONF_ECN = ['0', '1']

# TCP congestion control algorithm used
# Possible algos are: default, host<N>, newreno, cubic, cdg, hd, htcp, compound, vegas
# Note that the algo support is OS specific, so must ensure the right OS is booted
# Windows: newreno (default), compound
# FreeBSD: newreno (default), cubic, hd, htcp, cdg, vegas
# Linux: newreno, cubic (default), htcp, vegas
# If you specify 'default' the default algorithm depending on the OS will be used
# If you specify 'host<N>' where <N> is an integer starting from 0 to then the
# algorithm will be the N-th algorithm specified for the host in TPCONF_host_TCP_algos 
# (in case <N> is larger then the number of algorithms specified, it is set to 0
TPCONF_TCP_algos = ['newreno', 'cubic', 'htcp', ]

# Specify TCP congestion control algorithms used on each host
TPCONF_host_TCP_algos = {
    'newtcp1': ['default', 'newreno', ],
    'newtcp2': ['default', 'newreno', ],
    'newtcp3': ['default', 'newreno', ],
    'newtcp4': ['default', 'compound', ],
}

# Specify TCP parameters for each host and each TCP congestion control algorithm
# Each parameter is of the form <sysctl name> = <value> where <value> can be a constant
# or a V_ variable
TPCONF_host_TCP_algo_params = {
    'newtcp1': {'cdg': ['net.inet.tcp.cc.cdg.beta_delay = V_cdg_beta_delay',
                        'net.inet.tcp.cc.cdg.beta_loss = V_cdg_beta_loss',
                        'net.inet.tcp.cc.cdg.exp_backoff_scale = 3',
                        'net.inet.tcp.cc.cdg.smoothing_factor = 8',
                        'net.inet.tcp.cc.cdg.loss_compete_consec_cong = 5',
                        'net.inet.tcp.cc.cdg.loss_compete_hold_backoff = 5',
                        'net.inet.tcp.cc.cdg.alpha_inc = 0'],
                },

}

# Specify arbitray commands that are executed on a host at the end of the host 
# intialisation (after general host setup, ecn and tcp setup). The commands are
# executed in the shell as written after any V_ variables have been replaced.
# LIMITATION: only one V_ variable per command
TPCONF_host_init_custom_cmds = {
    #'newtcp1' : [ 'echo TEST' , 
    #		   'echo V_test',
    #		],
}

# Delays in ms
TPCONF_delays = [0, 25, 50, 100]

# Loss rates
TPCONF_loss_rates = [0, 0.001, 0.01]

# Bandwidth (downstream, upstream)
# Note: Linux syntax
TPCONF_bandwidths = [
    ('8mbit', '1mbit'),
    ('20mbit', '1.4mbit'),
]

# AQM
# Note this is router OS specific
# Linux: fifo (mapped to pfifo), pfifo, bfifo, fq_codel, codel, pie, red, ...
#        (see tc man page for full list)
# FreeBSD: fifo, red
TPCONF_aqms = ['pfifo', 'fq_codel', 'pie']

# Buffer size
# If router is Linux this is mostly in packets/slots, but it depends on AQM
# (e.g. for bfifo it's bytes)
# If router is FreeBSD this would be in slots by default, but we can specify byte sizes
# (e.g. we can specify 4Kbytes)
TPCONF_buffer_sizes = [100, 200]

# Dash content rates in kbps
TPCONF_dash_rates = [500, 1000, 2000]
TPCONF_dash_rates_str = ','.join(map(str, TPCONF_dash_rates))

# Incast content sizes and interval between queries (in seconds)
TPCONF_inc_content_sizes = [8, 16, 32, 64, 1000]
TPCONF_inc_content_sizes_str = ','.join(
    str(x) for x in TPCONF_inc_content_sizes)
TPCONF_inc_periods = [10]

# CDG parameters
# beta delay
TPCONF_cdg_beta_delay_facs = [70, 50, 90]
# beta loss
TPCONF_cdg_beta_loss_facs = [50, 30, 70]


# List of all parameters that can be varied

# The key of each item is the identifier that can be used in TPCONF_vary_parameters
# (see below).
# The value of each item is a 4-tuple. First, a list of variable names.
# Second, a list of short names uses for the file names.
# For each parameter varied a string '_<short_name>_<value>' is appended to the log
# file names (appended to chosen prefix). Note, short names should only be letters
# from a-z or A-Z. Do not use underscores or hyphens!
# Third, the list of parameters values. If there is more than one variable this must
# be a list of tuples, each tuple having the same number of items as teh number of
# variables. Fourth, an optional dictionary with additional variables, where the keys
# are the variable names and the values are the variable values.

TPCONF_parameter_list = {
#   Vary name		V_ variable	  file name	values			extra vars
    'ecns' 	    :  (['V_ecn'],	  ['ecn'], 	TPCONF_ECN, 		 {}),	  
    'delays' 	    :  (['V_delay'], 	  ['del'], 	TPCONF_delays, 		 {}),
    'loss'  	    :  (['V_loss'], 	  ['loss'], 	TPCONF_loss_rates, 	 {}),
    'tcpalgos' 	    :  (['V_tcp_cc_algo'],['tcp'], 	TPCONF_TCP_algos, 	 {}),
    'aqms'	    :  (['V_aqm'], 	  ['aqm'], 	TPCONF_aqms, 		 {}),
    'bsizes'	    :  (['V_bsize'], 	  ['bs'], 	TPCONF_buffer_sizes, 	 {}),
    'dash_rates'    :  (['V_dash_rate'],  ['dash'], 	TPCONF_dash_rates,
                     			    {'V_dash_rates': TPCONF_dash_rates_str}),
    'incast_periods':  (['V_inc_period'], ['incper'], 	TPCONF_inc_periods, 	 {}),
    'incast_sizes'  :  (['V_inc_size'],	  ['incsz'], 	TPCONF_inc_content_sizes,{}),
    'runs'	    :  (['V_runs'],       ['run'], 	range(TPCONF_runs), 	 {}),
    'bandwidths'    :  (['V_down_rate', 'V_up_rate'], ['down', 'up'], TPCONF_bandwidths, {}),
    'cdg_beta_dels' :  (['V_cdg_beta_delay'], ['cdgbdel'], TPCONF_cdg_beta_delay_facs, {}),
    'cdg_beta_loss' :  (['V_cdg_beta_loss'], ['cdgblo'],   TPCONF_cdg_beta_loss_facs,  {}),
}

# Default setting for variables (used for variables if not varied)

# The key of each item is the parameter  name. The value of each item is the default
# parameter value used if the variable is not varied.

TPCONF_variable_defaults = {
#   V_ variable			value
    'V_ecn'  		:	TPCONF_ECN[0],
    'V_duration'  	:	TPCONF_duration,
    'V_delay'  		:	TPCONF_delays[0],
    'V_loss'   		:	TPCONF_loss_rates[0],
    'V_tcp_cc_algo' 	:	TPCONF_TCP_algos[0],
    'V_down_rate'   	:	TPCONF_bandwidths[0][0],
    'V_up_rate'	    	:	TPCONF_bandwidths[0][1],
    'V_aqm'	    	:	TPCONF_aqms[0],
    'V_bsize'	    	:	TPCONF_buffer_sizes[0],
    'V_dash_rate'   	:	TPCONF_dash_rates[0],
    'V_dash_rates'  	:	str(TPCONF_dash_rates[0]),
    'V_inc_period'  	:	TPCONF_inc_periods[0],
    'V_inc_size'    	:	TPCONF_inc_content_sizes[0],
    'V_inc_content_sizes_str':	TPCONF_inc_content_sizes_str,
    'V_cdg_beta_delay'	: 	TPCONF_cdg_beta_delay_facs[0],
    'V_cdg_beta_loss'	: 	TPCONF_cdg_beta_loss_facs[0],
    'V_test'	    	:	'foobar',
}

# Specify the parameters we vary through all values, all others will be fixed
# according to TPCONF_variable_defaults
TPCONF_vary_parameters = ['dash_rates', 'tcpalgos', 'delays', 'loss', 'bandwidths',
                          'aqms', 'bsizes', 'runs', ]
