#
# List of traffic generators
#
# $Id: $

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

traffic_iperf = [
    # Specifying external addresses traffic will be created using the _first_
    # internal addresses (according to TPCONF_host_internal_ip)
    ('0.0', '1', " start_iperf, client='newtcp27', server='newtcp20', port=5000, "
     " duration=V_duration "),
    ('0.0', '2', " start_iperf, client='newtcp27', server='newtcp20', port=5001, "
     " duration=V_duration "),
    # Or using internal addresses
    #( '0.0', '1', " start_iperf, client='172.16.11.2', server='172.16.10.2', "
    #              " port=5000, duration=V_duration " ),
    #( '0.0', '2', " start_iperf, client='172.16.11.2', server='172.16.10.2', "
    #              " port=5001, duration=V_duration " ),
]

