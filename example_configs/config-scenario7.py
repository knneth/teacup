# Incast scenario, one querier and 10 responders, varying response  
# size 
#
# $Id: $

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

#
# Testbed config
#

# Path to teacup scripts
TPCONF_script_path = '/home/teacup/teacup-0.8'
# DO NOT remove the following line
sys.path.append(TPCONF_script_path)

# Set debugging level (0 = no debugging info output) 
TPCONF_debug_level = 0

# Host lists
TPCONF_router = ['newtcprt3', ]
TPCONF_hosts = [ 'newtcp20', 'newtcp21', 'newtcp22', 'newtcp23', 'newtcp24',
                 'newtcp25', 'newtcp26', 'newtcp27', 'newtcp28', 'newtcp29',
                 'newtcp30', ]

# Map external IPs to internal IPs
TPCONF_host_internal_ip = {
    'newtcprt3': ['172.16.10.1', '172.16.11.1'],
    'newtcp20':  ['172.16.10.60'], # querier
    'newtcp21':  ['172.16.11.61'], # responders...
    'newtcp22':  ['172.16.11.62'],
    'newtcp23':  ['172.16.11.63'],
    'newtcp24':  ['172.16.11.64'],
    'newtcp25':  ['172.16.11.65'],
    'newtcp26':  ['172.16.11.66'],
    'newtcp27':  ['172.16.11.67'],
    'newtcp28':  ['172.16.11.68'],
    'newtcp29':  ['172.16.11.69'],
    'newtcp30':  ['172.16.11.70'],
}

#
# Reboot configuration
#

#
# Experiment settings
#

# Maximum allowed time difference between machines in seconds
# otherwise experiment will abort cause synchronisation problems
TPCONF_max_time_diff = 1

# Experiment name prefix used if not set on the command line
# The command line setting will overrule this config setting
now = datetime.datetime.today()
TPCONF_test_id = now.strftime("%Y%m%d-%H%M%S") + '_scenario7'

# Directory to store log files on remote host
TPCONF_remote_dir = '/tmp/'

# Time offset measurement traffic 
# Enable broadcast ping on external/control interfaces
TPCONF_bc_ping_enable = '0'
# Specify rate of pings in packets/second
TPCONF_bc_ping_rate = 1
# Specify multicast address to use (must be broadcast or multicast address)
# If this is not specified, byt deafult the ping will be send to the subnet
# broadcast address.
TPCONF_bc_ping_address = '224.0.1.199'

#
# List of router queues/pipes
#

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
    # Set same delay for every host
    ('1', " source='172.16.10.0/24', dest='172.16.11.0/24', delay=V_delay, "
     " loss=V_loss, rate=V_up_rate, queue_disc=V_aqm, queue_size=V_bsize "),
    ('2', " source='172.16.11.0/24', dest='172.16.10.0/24', delay=V_delay, "
     " loss=V_loss, rate=V_down_rate, queue_disc=V_aqm, queue_size=V_bsize "),
]

#
# List of traffic generators
#

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

traffic_incast = [
    # Start servers and create contents (server must be started first)
    ('0.0', '1', " start_http_server, server='newtcp21', port=80 "),
    ('0.0', '2', " start_http_server, server='newtcp22', port=80 "),
    ('0.0', '3', " start_http_server, server='newtcp23', port=80 "),
    ('0.0', '4', " start_http_server, server='newtcp24', port=80 "),
    ('0.0', '5', " start_http_server, server='newtcp25', port=80 "),
    ('0.0', '6', " start_http_server, server='newtcp26', port=80 "),
    ('0.0', '7', " start_http_server, server='newtcp27', port=80 "),
    ('0.0', '8', " start_http_server, server='newtcp28', port=80 "),
    ('0.0', '9', " start_http_server, server='newtcp29', port=80 "),
    ('0.0', '10', " start_http_server, server='newtcp30', port=80 "),

    ('0.0', '11', " create_http_incast_content, server='newtcp21', duration=2*V_duration, "
     " sizes=V_inc_content_sizes_str "),
    ('0.0', '12', " create_http_incast_content, server='newtcp22', duration=2*V_duration, "
     " sizes=V_inc_content_sizes_str "),
    ('0.0', '13', " create_http_incast_content, server='newtcp23', duration=2*V_duration, "
     " sizes=V_inc_content_sizes_str "),
    ('0.0', '14', " create_http_incast_content, server='newtcp24', duration=2*V_duration, "
     " sizes=V_inc_content_sizes_str "),
    ('0.0', '15', " create_http_incast_content, server='newtcp25', duration=2*V_duration, "
     " sizes=V_inc_content_sizes_str "),
    ('0.0', '16', " create_http_incast_content, server='newtcp26', duration=2*V_duration, "
     " sizes=V_inc_content_sizes_str "),
    ('0.0', '17', " create_http_incast_content, server='newtcp27', duration=2*V_duration, "
     " sizes=V_inc_content_sizes_str "),
    ('0.0', '18', " create_http_incast_content, server='newtcp28', duration=2*V_duration, "
     " sizes=V_inc_content_sizes_str "),
    ('0.0', '19', " create_http_incast_content, server='newtcp29', duration=2*V_duration, "
     " sizes=V_inc_content_sizes_str "),
    ('0.0', '20', " create_http_incast_content, server='newtcp30', duration=2*V_duration, "
     " sizes=V_inc_content_sizes_str "),

    # Start querier 
    ('1.0', '30', " start_httperf_incast, client='newtcp20', "
     " servers='newtcp21:80,newtcp22:80,newtcp23:80,newtcp24:80,newtcp25:80,newtcp26:80, "
     " newtcp27:80,newtcp28:80,newtcp29:80,newtcp30:80', "
     " duration=V_duration, period=V_inc_period, response_size=V_inc_size"),
]

# THIS is the traffic generator setup we will use
TPCONF_traffic_gens = traffic_incast

#
# Traffic parameters 
#

# Duration in seconds of traffic
TPCONF_duration = 30

# Number of runs for each setting
TPCONF_runs = 1

# TCP congestion control algorithm used
# Possible algos are: default, host<N>, newreno, cubic, cdg, hd, htcp, compound, vegas
# Note that the algo support is OS specific, so must ensure the right OS is booted
# Windows: newreno (default), compound
# FreeBSD: newreno (default), cubic, hd, htcp, cdg, vegas
# Linux: newreno, cubic (default), htcp, vegas
# Mac: newreno
# If you specify 'default' the default algorithm depending on the OS will be used
# If you specify 'host<N>' where <N> is an integer starting from 0 to then the
# algorithm will be the N-th algorithm specified for the host in TPCONF_host_TCP_algos 
# (in case <N> is larger then the number of algorithms specified, it is set to 0
TPCONF_TCP_algos = ['newreno', 'cubic', ]

# Specify TCP congestion control algorithms used on each host
TPCONF_host_TCP_algos = {
}

# Specify TCP parameters for each host and each TCP congestion control algorithm
# Each parameter is of the form <sysctl name> = <value> where <value> can be a constant
# or a V_ variable
TPCONF_host_TCP_algo_params = {
}

# Specify arbitray commands that are executed on a host at the end of the host 
# intialisation (after general host setup, ecn and tcp setup). The commands are
# executed in the shell as written after any V_ variables have been replaced.
# LIMITATION: only one V_ variable per command
TPCONF_host_init_custom_cmds = {
}

# Emulated delays in ms
TPCONF_delays = [0, 25, 50]

# Emulated loss rates
TPCONF_loss_rates = [0]

# Emulated bandwidths (downstream, upstream)
TPCONF_bandwidths = [
    ('8mbit', '1mbit'),
    ('20mbit', '1.4mbit'),
]

# AQM
# Linux: fifo (mapped to pfifo), pfifo, bfifo, fq_codel, codel, pie, red, ...
#        (see tc man page for full list)
# FreeBSD: fifo, red
TPCONF_aqms = ['pfifo', 'codel', 'fq_codel', ]

# Buffer size
# If router is Linux this is mostly in packets/slots, but it depends on AQM
# (e.g. for bfifo it's bytes)
# If router is FreeBSD this would be in slots by default, but we can specify byte sizes
# (e.g. we can specify 4Kbytes)
TPCONF_buffer_sizes = [100]

# Incast content sizes in kB and interval between queries (in seconds)
TPCONF_inc_content_sizes = [8, 16, 32, 64, 128, 256]
TPCONF_inc_content_sizes_str = ','.join(
    str(x) for x in TPCONF_inc_content_sizes)
TPCONF_inc_periods = [10]

#
# List of all parameters that can be varied and default values
#

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
    'delays' 	    :  (['V_delay'], 	  ['del'], 	TPCONF_delays, 		 {}),
    'loss'  	    :  (['V_loss'], 	  ['loss'], 	TPCONF_loss_rates, 	 {}),
    'tcpalgos' 	    :  (['V_tcp_cc_algo'],['tcp'], 	TPCONF_TCP_algos, 	 {}),
    'aqms'	    :  (['V_aqm'], 	  ['aqm'], 	TPCONF_aqms, 		 {}),
    'bsizes'	    :  (['V_bsize'], 	  ['bs'], 	TPCONF_buffer_sizes, 	 {}),
    'runs'	    :  (['V_runs'],       ['run'], 	range(TPCONF_runs), 	 {}),
    'bandwidths'    :  (['V_down_rate', 'V_up_rate'], ['down', 'up'], TPCONF_bandwidths, {}),
    'incast_periods':  (['V_inc_period'], ['incper'],   TPCONF_inc_periods,      {}),
    'incast_sizes'  :  (['V_inc_size'],   ['incsz'],    TPCONF_inc_content_sizes,{}),
}

# Default setting for variables (used for variables if not varied)

# The key of each item is the parameter  name. The value of each item is the default
# parameter value used if the variable is not varied.

TPCONF_variable_defaults = {
#   V_ variable			value
    'V_duration'  	:	TPCONF_duration,
    'V_delay'  		:	TPCONF_delays[0],
    'V_loss'   		:	TPCONF_loss_rates[0],
    'V_tcp_cc_algo' 	:	TPCONF_TCP_algos[0],
    'V_down_rate'   	:	TPCONF_bandwidths[0][0],
    'V_up_rate'	    	:	TPCONF_bandwidths[0][1],
    'V_aqm'	    	:	TPCONF_aqms[0],
    'V_bsize'	    	:	TPCONF_buffer_sizes[0],
    'V_inc_period'      :       TPCONF_inc_periods[0],
    'V_inc_size'        :       TPCONF_inc_content_sizes[0],
    'V_inc_content_sizes_str':  TPCONF_inc_content_sizes_str,
}

# Specify the parameters we vary through all values, all others will be fixed
# according to TPCONF_variable_defaults
TPCONF_vary_parameters = ['incast_sizes', 'delays', 'bandwidths', 'aqms', 'runs',]
