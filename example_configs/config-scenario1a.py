# Simple experiment with two tcp flows with two hosts and one
# router
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

#
# Experiment settings
#

# Maximum allowed time difference between machines in seconds
# otherwise experiment will abort cause synchronisation problems
TPCONF_max_time_diff = 1

# Experiment name prefix used if not set on the command line
# The command line setting will overrule this config setting
now = datetime.datetime.today()
TPCONF_test_id = now.strftime("%Y%m%d-%H%M%S") + 'experiment'

# Directory to store log files on remote host
TPCONF_remote_dir = '/tmp/'

# Number of runs for each setting
TPCONF_runs = 1

#
# Testbed hosts config.
#

execfile('config-scenario1a-nodes.py')

#
# Router queue config
#

execfile('config-scenario1a-router.py')

#
# Traffic generators
#

execfile('config-scenario1a-traffic.py')

# THIS is the traffic generator setup we will use
TPCONF_traffic_gens = traffic_iperf

#
# Traffic parameters 
#

# Duration in seconds of traffic
TPCONF_duration = 30

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
TPCONF_TCP_algos = ['newreno', ]

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
TPCONF_aqms = ['pfifo', ]

# Buffer size
# If router is Linux this is mostly in packets/slots, but it depends on AQM
# (e.g. for bfifo it's bytes)
# If router is FreeBSD this would be in slots by default, but we can specify byte sizes
# (e.g. we can specify 4Kbytes)
TPCONF_buffer_sizes = [100]

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
}

# Specify the parameters we vary through all values, all others will be fixed
# according to TPCONF_variable_defaults
TPCONF_vary_parameters = ['delays', 'bandwidths', 'aqms', 'runs',]
