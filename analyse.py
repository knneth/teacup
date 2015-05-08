# Copyright (c) 2013-2015 Centre for Advanced Internet Architectures,
# Swinburne University of Technology. All rights reserved.
#
# Author: Sebastian Zander (szander@swin.edu.au)
#         Grenville Armitage (garmitage@swin.edu.au)
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
# Analyse experiment data
#
# $Id: analyse.py 1012 2015-02-20 07:21:57Z szander $

import os
import errno
import time
import datetime
import re
import socket
from fabric.api import task, warn, put, puts, get, local, run, execute, \
    settings, abort, hosts, env, runs_once, parallel

import config
from hostint import get_address_pair
import clockoffset
from clockoffset import adjust_timestamps

# dictionary for lookups
source_filter = {}
# list to preserve the original order
source_filter_list = []


#######################################################################
# Source filter functions
#######################################################################

# Build a flow filter
# Paramter:
#	filter_str: string of multiple flows,
#                   format (S|D)_srcip_srcport[;(S|D)_srcip_srcport]*
#	srcport can be wildcard character '*'
def _build_source_filter(filter_str):
    global source_filter

    if len(source_filter) == 0:
        for fil in filter_str.split(';'):
            fil = fil.strip()
            arr = fil.split('_')
            if len(arr) != 3:
                abort('Incorrect source filter entry %s' % fil)
            if arr[0] != 'S' and arr[0] != 'D':
                abort('Incorrect source filter entry %s' % fil)

            key = arr[0] + '_' + arr[1]  # (S|D)_ip
            val = arr[2]  # port
            source_filter[key] = val
            source_filter_list.append(fil)


# Check if flow in flow filter
# Parameters:
#	fow: flow string
def _in_source_filter(flow):
    global source_filter

    if len(source_filter) == 0:
        return True

    arr = flow.split('_')
    sflow = 'S_' + arr[0]
    sflow_port = arr[1]
    dflow = 'D_' + arr[2]
    dflow_port = arr[3]

    if sflow in source_filter and (
            source_filter[sflow] == '*' or source_filter[sflow] == sflow_port):
        return True
    elif dflow in source_filter and \
            (source_filter[dflow] == '*' or source_filter[dflow] == dflow_port):
        return True
    else:
        return False


#############################################################################
# Flow sorting functions
#############################################################################


def _cmp_src_port(x, y):
    "Compare flow keys by flow source port (lowest source port first)"

    xflow = str(x)
    yflow = str(y)

    # split into src/dst IP/port
    xflow_arr = xflow.split('_')
    yflow_arr = yflow.split('_')

    # sort by numeric source port
    return cmp(int(xflow_arr[1]), int(yflow_arr[1]))


def _cmp_dst_port(x, y):
    "Compare flow keys by flow dest port (lowest dest port first)"

    xflow = str(x)
    yflow = str(y)

    # split into src/dst IP/port
    xflow_arr = xflow.split('_')
    yflow_arr = yflow.split('_')

    # sort by numeric dest port
    return cmp(int(xflow_arr[3]), int(yflow_arr[3]))


# If all flows are bidirectional sort so that server-client flows appear
# at left and client-server flows at right
# Otherwise we always have server-client flow followed by client-server
# flow (if the latter exists)
# Paramters
#	files: name <-> file name map
# Returns
#	List of tuples (<flow_name>, <file_name>)
def sort_by_flowkeys(files={}, groups={}):
    "Sort flow names"
    global source_filter

    sorted_files = []

    # if filter string was specified graph in order of filters
    if len(source_filter_list) > 0:
        for fil in source_filter_list:
            # strip of the (S|D) part a the start
            arr = fil.split('_')
            if arr[2] == '*':
                fil = arr[1] + '_'
            else:
                fil = arr[1] + '_' + arr[2]
            # find the file entry that matches the filter
            for name in files:
                if fil in name:
                    sorted_files.append((name, files[name]))

        return sorted_files

    # otherwise do our best to make sure we have a sensible and consistent
    # ordering based on server ports
    rev_files = {}

    # sort by dest port if and only if dest port is always lower than source
    # port
    cmp_fct = _cmp_dst_port
    for name in files:
        a = name.split('_')
        if int(a[1]) < int(a[3]):
            cmp_fct = _cmp_src_port
            break

    for name in sorted(files, cmp=cmp_fct):
        # print(name)
        if rev_files.get(name, '') == '':
            sorted_files.append((name, files[name]))
            a = name.split('_')
            rev_name = a[2] + '_' + a[3] + '_' + a[0] + '_' + a[1]
            if files.get(rev_name, '') != '':
                sorted_files.append((rev_name, files[rev_name]))
                rev_files[rev_name] = files[rev_name]

    if len(rev_files) == len(files) / 2:
        # order them so that server-client are left and client-server are right
        # in plot
        sorted_files_c2sleft = [('', '')] * len(files)

        idx = 0
        for name, file_name in sorted_files:
            if idx % 2 == 0:
                sorted_files_c2sleft[int(idx / 2)] = (name, file_name)
            else:
                sorted_files_c2sleft[
                    int((idx - 1) / 2) + len(files) / 2] = (name, file_name)
            idx += 1

        return sorted_files_c2sleft
    else:
        return sorted_files


# if we have groups make sure that group order is the same for all flows
# Parameters
#       files: <flow_name>,<file_name> tuples (sorted by sort_by_flowkeys)
#	groups: <file_name>,<group_number> map
# Returns
# 	List
def sort_by_group_id(files={}, groups={}):

    sorted_files = [('', '')] * len(files)

    if max(groups.values()) == 1:
        return files
    else:
        num_groups = max(groups.values())
        cnt = 0
        for fil in files:
            start = int(cnt / num_groups)
            grp = groups[fil[1]]
            sorted_files[start * num_groups + grp - 1] = fil
            cnt += 1

        return sorted_files


###########################################################################
# Helper functions
###########################################################################


# Build a list of strings from a number of string lines
# Parameters:
#       lines: string lines
# Return:
#       List with one entry per line
def _list(lines):
    ret = []
    for line in lines.split('\n'):
        if line != '':
            ret.append(line)

    return ret


# mkdir -p in python
# Parameters:
#	path: directory to create
def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc: # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else: 
            raise


# make sure the specified directory adds with a trailing slash
# Parameters:
#       path: directory
def valid_dir(path): 
    if len(path) > 0 and path[-1] != '/':
        path += '/'

    return path 


#############################################################################
# Plot functions
#############################################################################

# Plot time series
# Parameters:
#	title: title of plot at the top
#	files: dictionary with legend names (keys) and files with the data
#              to plot (values)
#	ylab: label for y-axis
#	yindex: index of the column in data file to plot
#	yscaler: scaler for y-values (data in file is multiplied with the scaler)
#	otype: type of output file
#	oprefix: output file name prefix
#	pdf_dir: output directory for graphs
#	sep: character that separates columns in data file
#	aggr: aggregation of data in time intervals
#	omit_const: '0' don't omit anything,
#                   '1' omit any series that are 100% constant
#                       (e.g. because there was no data flow)
#	ymin: minimum value on y-axis
#	ymax: maximum value on y-axis
#       lnames: semicolon-separated list of legend names
#       stime: start time of plot window in seconds
#              (by default 0.0 = start of experiment)
#       etime: end time of plot window in seconds
#              (by default 0.0 = end of experiment)
#       groups: put data files in groups (all files of same experiment must have
#               same group number)
#	sort_flowkey: '1' sort by flow key (default)
#                 '0' don't sort by flow key
#       boxplot: '0' normal time series
#                '1' do boxplot for all values at one point in time
#       plot_params: parameters passed to plot function via environment variables
#       plot_script: specify the script used for plotting, must specify full path
#                    (default is config.TPCONF_script_path/plot_time_series.R)
def plot_time_series(title='', files={}, ylab='', yindex=2, yscaler=1.0, otype='',
                     oprefix='', pdf_dir='', sep=' ', aggr='', omit_const='0',
                     ymin=0, ymax=0, lnames='',
                     stime='0.0', etime='0.0', groups={}, sort_flowkey='1',
                     boxplot='', plot_params='', plot_script=''):

    file_names = []
    leg_names = []
    _groups = []

    #print(files)
    if sort_flowkey == '1':
        sorted_files = sort_by_flowkeys(files)
    else:
        sorted_files = files.items()
    sorted_files = sort_by_group_id(sorted_files, groups)
    for name, file_name in sorted_files:
        leg_names.append(name)
        file_names.append(file_name)
        _groups.append(groups[file_name])

    if lnames != '':
        lname_arr = lnames.split(';')
        if boxplot == '0' and len(lname_arr) != len(leg_names):
            abort(
                'Number of legend names must be the same as the number of flows')
        else:
            leg_names = lname_arr

    # get the directory name here if not specified
    if pdf_dir == '':
        pdf_dir = os.path.dirname(file_names[0]) + '/'
    else:
        pdf_dir = valid_dir(pdf_dir)
        # make it relative to experiment_dir
        # assume experiment dir is part before first slash
        pdf_dir = file_names[0].split('/')[0] + '/' + pdf_dir
        # if pdf_dir specified create if it doesn't exist
        mkdir_p(pdf_dir)

    if plot_script == '':
        plot_script = 'R CMD BATCH --vanilla %s/plot_time_series.R' % \
                      config.TPCONF_script_path

    # interface between this code and the plot function are environment variables
    # the following variables are passed to plot function:
    # TITLE:  character string that is plotted over the graph
    # FNAMES: comma-separated list of file names (each file contains one date series,
    #         e.g. data for one flow). The format of each file is CSV-style, but the
    #         separator does not have to be a comma (can be set with SEP). The first
    #         column contains the timestamps. The second, third etc. columns contain
    #         data, but only one of these columns will be plotted (set with YINDEX). 
    # LNAMES: comma-separated list of legend names. this list has the same length
    #         as FNAMES and each entry corresponds to data in file name with the
    #         same index in FNAMES
    # YLAB:   y-axis label character string
    # YINDEX: index of data column in file to plot on y-axis (file can have more than
    #         one data column)
    # YSCALER: factor which is multiplied with each data value before plotting
    # SEP:    column separator used in data file
    # OTYPE:  type of output graph (default is 'pdf')
    # OPREFIX: the prefix (first part) of the graph file name
    # ODIR:   directory where output files, e.g. pdfs are placed
    # AGGR:   set to '1' means data is aggregated over time intervals, more specifically
    #         the data is summed over the time intervals (used to determine throughput
    #         over time windows based on packet lengths)  
    #         set to '0' means plot data as is 
    # OMIT_CONST: '0' don't omit anything,
    #             '1' omit any data series from plot that are 100% constant 
    # YMIN:   minimum value on y-axis (for zooming in), default is 0 
    # YMAX:   maximum value on y-axis (for zooming in), default is 0 meaning the 
    #         maximum value is determined from the data
    # STIME:  start time on x-axis (for zooming in), default is 0.0 meaning the start 
    #         of an experiment
    # ETIME:  end time on x-axis (for zooming in), default is 0.0 meaning the end of an
    #         experiment a determined from the data
    # GROUPS: comma-separated list of group IDs (integer numbers). This list has  
    #         the same length as FNAMES. If data from different experiments is plotted,
    #         each experiment will be assigned a different number and these are passed
    #         via GROUPS. This allows the plotting function to determine which data
    #         series are (or are not) from the same experiment, so that results 
    #         from different experiments, that started at different times, can be 
    #         plotted in the same graph.
    # BOXPL:  '0' plot each point on time axis
    #         '1' plot a boxplot over all data points from all data seres for each 
    #         distinct timestamp (instead of a point for each a data series) 

    local('which R')
    local('TITLE="%s" FNAMES="%s" LNAMES="%s" YLAB="%s" YINDEX="%d" YSCALER="%f" '
          'SEP="%s" OTYPE="%s" OPREFIX="%s" ODIR="%s" AGGR="%s" OMIT_CONST="%s" '
          'YMIN="%s" YMAX="%s" STIME="%s" ETIME="%s" GROUPS="%s" BOXPL="%s" %s '
          '%s %s%s_plot_time_series.Rout' %
          (title, ','.join(file_names), ','.join(leg_names), ylab, yindex, yscaler,
           sep, otype, oprefix, pdf_dir, aggr, omit_const, ymin, ymax, stime, etime,
           ','.join(map(str, _groups)), boxplot, plot_params,
           plot_script, pdf_dir, oprefix))

    if config.TPCONF_debug_level == 0:
	local('rm -f %s%s_plot_time_series.Rout' % (pdf_dir, oprefix))


# Plot DASH goodput
# Parameters:
#       title: title of plot at the top
#       files: dictionary with legend names (keys) and files with the data to plot
#              (values)
#       ylab: label for y-axis
#       otype: type of output file
#       oprefix: output file name prefix
#       pdf_dir: output directory for graphs
#       sep: character that separates columns in data file
#       ymin: minimum value on y-axis
#       ymax: maximum value on y-axis
#       lnames: semicolon-separated list of legend names
#       stime: start time of plot window in seconds
#              (by default 0.0 = start of experiment)
#       etime: end time of plot window in seconds (by default 0.0 = end of
#              experiment)
#       plot_params: parameters passed to plot function via environment variables
#       plot_script: specify the script used for plotting, must specify full path
#                    (default is config.TPCONF_script_path/plot_dash_goodput.R)
def plot_dash_goodput(title='', files={}, ylab='', otype='', oprefix='',
                      pdf_dir='', sep=' ', ymin=0, ymax=0, lnames='', stime='0.0', 
                      etime='0.0', plot_params='', plot_script=''):

    file_names = []
    leg_names = []

    for name in sorted(files):
        leg_names.append(name)
        file_names.append(files[name])

    if lnames != '':
        lname_arr = lnames.split(';')
        if len(lname_arr) != len(leg_names):
            abort(
                'Number of legend names must be the same as the number of flows')
        else:
            leg_names = lname_arr

    # get the directory name here if not specified
    if pdf_dir == '':
        pdf_dir = os.path.dirname(file_names[0]) + '/'
    else:
        pdf_dir = valid_dir(pdf_dir)
        # make it relative to experiment_dir
        # assume experiment dir is part before first slash
        pdf_dir = file_names[0].split('/')[0] + '/' + pdf_dir
        # if pdf_dir specified create if it doesn't exist
        mkdir_p(pdf_dir)

    if plot_script == '':
        plot_script = 'R CMD BATCH --vanilla %s/plot_dash_goodput.R' % \
                      config.TPCONF_script_path
 
    # interface between this code and the plot function are environment variables
    # the following variables are passed to plot function:
    # TITLE:  character string that is plotted over the graph
    # FNAMES: comma-separated list of file names (each file contains one date series,
    #         e.g. data for one flow). The format of each file is CSV-style, but the
    #         separator does not have to be a comma (can be set with SEP). The first
    #         column contains the timestamps. The second, third etc. columns contain
    #         data, but only one of these columns will be plotted (set with YINDEX). 
    # LNAMES: comma-separated list of legend names. this list has the same length
    #         as FNAMES and each entry corresponds to data in file name with the
    #         same index in FNAMES
    # YLAB:   y-axis label character string
    # SEP:    column separator used in data file
    # OTYPE:  type of output graph (default is 'pdf')
    # OPREFIX: the prefix (first part) of the graph file name
    # ODIR:   directory where output files, e.g. pdfs are placed
    # YMIN:   minimum value on y-axis (for zooming in), default is 0 
    # YMAX:   maximum value on y-axis (for zooming in), default is 0 meaning the 
    #         maximum value is determined from the data
    # STIME:  start time on x-axis (for zooming in), default is 0.0 meaning the start 
    #         of an experiment
    # ETIME:  end time on x-axis (for zooming in), default is 0.0 meaning the end of an
    #         experiment a determined from the data

    local('which R')
    local('TITLE="%s" FNAMES="%s" LNAMES="%s" YLAB="%s" SEP="%s" OTYPE="%s" '
          'OPREFIX="%s" ODIR="%s" YMIN="%s" YMAX="%s" STIME="%s" ETIME="%s" %s '
          '%s %s%s_plot_dash_goodput.Rout' %
          (title, ','.join(file_names), ','.join(leg_names), ylab, sep, otype, oprefix,
           pdf_dir, ymin, ymax, stime, etime, plot_params, plot_script, 
           pdf_dir, oprefix))

    if config.TPCONF_debug_level == 0:
        local('rm -f %s%s_plot_dash_goodput.Rout' % (pdf_dir, oprefix))



# plot_incast_ACK_series
#
# (based on plot_time_series, but massages the filenames and legend names a little
# differently to handle a trial being broken into 'bursts'.)
#
# Parameters:
#   title: title of plot at the top
#   files: dictionary with legend names (keys) and files with the data
#              to plot (values)
#   ylab: label for y-axis
#   yindex: index of the column in data file to plot
#   yscaler: scaler for y-values (data in file is multiplied with the scaler)
#   otype: type of output file
#   oprefix: output file name prefix
#   pdf_dir: output directory for graphs
#   sep: character that separates columns in data file
#   aggr: aggregation of data in 1-seond intervals
#   omit_const: '0' don't omit anything,
#                   '1' omit any series that are 100% constant
#                       (e.g. because there was no data flow)
#   ymin: minimum value on y-axis
#   ymax: maximum value on y-axis
#   lnames: semicolon-separated list of legend names
#   stime: start time of plot window in seconds
#              (by default 0.0 = start of experiment)
#   etime: end time of plot window in seconds
#              (by default 0.0 = end of experiment)
#   groups: put data files in groups (all files of same experiment must have
#               same group number)
#   sort_flowkey: '1' sort by flow key (default)
#                 '0' don't sort by flow key
#   boxplot: '0' normal time series (no other value is currently valid in this context)
#   burst_sep: '0' plot seq numbers as they come, relative to 1st seq number
#                > '0' plot seq numbers relative to 1st seq number after gaps
#                   of more than burst_sep seconds (e.g. incast query/response bursts)
#                < 0,  plot seq numbers relative to 1st seq number after each abs(burst_sep)
#                   seconds since the first burst @ t = 0 (e.g. incast query/response bursts)
#   sburst: Default 1, or a larger integer indicating the burst number of the first burst
#           in the provided list of filenames. Used as an offset to calculate new legend suffixes.
#       plot_params: parameters passed to plot function via environment variables
#       plot_script: specify the script used for plotting, must specify full path
#                    (default is config.TPCONF_script_path/plot_time_series.R)
def plot_incast_ACK_series(title='', files={}, ylab='', yindex=2, yscaler=1.0, otype='',
                     oprefix='', pdf_dir='', sep=' ', aggr='', omit_const='0',
                     ymin=0, ymax=0, lnames='',
                     stime='0.0', etime='0.0', groups={}, sort_flowkey='1',
                     boxplot='0',burst_sep='1.0', sburst=1,
                     plot_params='', plot_script=''):

    file_names = []
    leg_names = []
    _groups = []

    # Pick up case where the user has supplied a number of legend names
    # that doesn't match the number of distinct trials (as opposed to the
    # number of bursts detected within each trial)
    if lnames != '':
        if boxplot == '0' and len(lnames.split(";")) != len(files.keys()) :
            abort(
                'Number of legend names must be the same as the number of flows')


    if sort_flowkey == '1':
        sorted_files = sort_by_flowkeys(files)
    else:
        sorted_files = files.items()

    #print("MAIN: sorted_files: %s" % sorted_files)

    # gja 5feb15, TBD -- revise the sort by group ID to cope with
    #       multiple per-burst files associated with a flowID in sorted_files
    #       at this point
    #
    ###sorted_files = sort_by_group_id(sorted_files, groups)

    for name, file_name in sorted_files:
        # Create a sequence of burst-specific legend names,
        # derived from the flowID-based legend name.
        # Keep the .R code happy by creating a groups entry
        # for each burst-specific file.
        for burst_index in range(len(file_name)) :
            leg_names.append(name+"%"+str(burst_index+sburst))
            file_names.append(file_name[burst_index])
            _groups.append(groups[file_name[burst_index]])

    if lnames != '':
        # Create a sequence of burst-specific legend names,
        # derived from the per-trial legend names provided by user.
        lname_arr_orig = lnames.split(';')
        lname_arr = []
        i = 0
        for name, file_name in sorted_files:
            for burst_index in range(len(file_name)) :
                lname_arr.append(lname_arr_orig[i]+"%"+str(burst_index+sburst))
            i += 1

        if boxplot == '0' and len(lname_arr) != len(leg_names):
            abort(
                'Number of legend names must be the same as the number of flows')
        else:
            leg_names = lname_arr

    # get the directory name here if not specified
    if pdf_dir == '':
        pdf_dir = os.path.dirname(file_names[0]) + '/'
    else:
        pdf_dir = valid_dir(pdf_dir)
        # make it relative to experiment_dir
        # assume experiment dir is part before first slash
        pdf_dir = file_names[0].split('/')[0] + '/' + pdf_dir
        # if pdf_dir specified create if it doesn't exist
        mkdir_p(pdf_dir)

    if plot_script == '':
        plot_script = 'R CMD BATCH --vanilla %s/plot_time_series.R' % \
                       config.TPCONF_script_path

    #local('which R')
    local('TITLE="%s" FNAMES="%s" LNAMES="%s" YLAB="%s" YINDEX="%d" YSCALER="%f" '
          'SEP="%s" OTYPE="%s" OPREFIX="%s" ODIR="%s" AGGR="%s" OMIT_CONST="%s" '
          'YMIN="%s" YMAX="%s" STIME="%s" ETIME="%s" GROUPS="%s" BOXPL="%s" %s '
          '%s %s%s_plot_time_series.Rout' %
          (title, ','.join(file_names), ','.join(leg_names), ylab, yindex, yscaler,
           sep, otype, oprefix, pdf_dir, aggr, omit_const, ymin, ymax, stime, etime,
           ','.join(map(str, _groups)), boxplot, plot_params,
           plot_script, pdf_dir, oprefix))

    if config.TPCONF_debug_level == 0:
        local('rm -f %s%s_plot_time_series.Rout' % (pdf_dir, oprefix))





###################################################################################
# Helper functions for extract and plot functions
###################################################################################


# Get graph output file name
# Paramters:
#       test_id_arr:
#       out_name:
def get_out_name(test_id_arr=[], out_name=''):
    if len(test_id_arr) > 1:
        if out_name != '':
            return out_name + '_' + test_id_arr[0] + '_comparison'
        else:
            return test_id_arr[0] + '_comparison'
    else:
        if out_name != '':
            return out_name + '_' + test_id_arr[0]
        else:
            return test_id_arr[0]


# Return list of files
# Parameters:
# 	file_list_fname: name of file containing a list of full log file names 
#       test_id: semicolon separated list of test ids
#       file_ext: characteristic rightmost part of file (file extension)
#       pipe_cmd: one or more shell command that are executed in pipe with the
#                 find command
def get_testid_file_list(file_list_fname='', test_id='', file_ext='', pipe_cmd=''):

    file_list = []
    test_id_arr = test_id.split(';')

    if file_list_fname == '':
        # read from test_id list specified, this always overrules list in file if
        # also specified

        if len(test_id_arr) == 0 or test_id_arr[0] == '':
            abort('Must specify test_id parameter')

        if pipe_cmd != '':
            pipe_cmd = ' | ' + pipe_cmd

        for test_id in test_id_arr:
            file_list += _list(
                local(
                    'find -L . -name "%s*%s" -print | sed -e "s/\.\///"%s' %
                    (test_id, file_ext, pipe_cmd),
                    capture=True))
    else:
        # read list of files from file 

        try:
            lines = []
            with open(file_list_fname) as f:
                lines = f.readlines()
            for fname in lines:
                fname = fname.rstrip()
                file_list += _list(
                    local(
                        'find -L . -name "%s" -print | sed -e "s/\.\///"' %
                        fname,
                        capture=True))
        except IOError:
            abort('Cannot open file %s' % file_list_fname)

        test_id_arr[0] = file_list_fname 

    return (test_id_arr, file_list)


# check number of data rows and include file if over minimum
def enough_rows(name='', fname='', min_values='3'):

    rows = int(local('wc -l %s | awk \'{ print $1 }\'' %
                   fname, capture=True))
    if rows > int(min_values):
        return True 
    else:
        return False


# filter out data files with fewer than min_values data points
def filter_min_values(files={}, groups={}, min_values='3'):

    out_files = {}
    out_groups = {}
 
    for name in files:
        fname = files[name]

        if isinstance(fname, list) :
            # the ackseq method actually creates a name to list of file names
            # mapping, i.e. multiple file names per dataset name
            for _fname in fname:
                if enough_rows(name, _fname, min_values):
                    if not name in out_files:
                        out_files[name] = []
                    out_files[name].append(_fname)
                    out_groups[_fname] = groups[_fname]

        else:
            if enough_rows(name, fname, min_values):
                out_files[name] = fname
                out_groups[fname] = groups[fname]
 
    return (out_files, out_groups)


###################################################################################
# Main extract and plot functions
###################################################################################


# Extract DASH goodput data from httperf log files
# The extracted files have an extension of .dashgp. The format is CSV with the
# columns:
# 1. Timestamp of request (second.microsecond)
# 2. Size of requested/downloaded block (bytes)
# 3. Byte rate (mbps), equivalent to size devided by response time times 8
# 4. Response time (seconds)
# 5. Nominal/definded cycle length (seconds)
# 6. Nominal/defined rate (kbps)
# 7. Block number
# Parameters:
#       test_id: test ID prefix of experiment to analyse
#       out_dir: output directory for results
#       replot_only: don't extract already extracted data
#       dash_log_list: file name with a list of dash logs
#       ts_correct: '0' use timestamps as they are (default)
#                   '1' correct timestamps based on clock offsets estimated
#                       from broadcast pings
def _extract_dash_goodput(test_id='', out_dir='', replot_only='0', dash_log_list='',
                          ts_correct='0'):
    "Extract DASH goodput from httperf logs"

    # extension of input data files
    ifile_ext = '_httperf_dash.log.gz'
    # extension of output data files
    ofile_ext = '.dashgp'

    # files with extracted data
    out_files = {}
    # input dash log files
    dash_files = []

    # make sure specified dir has valid form
    out_dir = valid_dir(out_dir)

    (test_id_arr, dash_files) = get_testid_file_list(dash_log_list, test_id,
					ifile_ext, '') 

    for dash_file in dash_files:
        # get input directory name and create result directory if necessary
        dir_name = os.path.dirname(dash_file)
        mkdir_p(dir_name + '/' + out_dir)

        dash_file = dash_file.strip()
        name = os.path.basename(dash_file.replace(ifile_ext, ''))
        out = dir_name + '/' + out_dir + name + ofile_ext 

        # this extracts the req time, request size, byte rate, response time,
        # nominal cycle length, nominal rate in kbps and block number
        #(requires modified httperf output)
        # the sed here parses the nominal cycle length, nominal rate in kbps
        # and block number from the file name
        if replot_only == '0' or not os.path.isfile(out):
            local(
                'zcat %s | grep video_files | grep -v NA | '
                'awk \'{ print $1 "," $5 "," $7 "," $10 "," $14 }\' | '
                'sed "s/\/video_files-\([0-9]*\)-\([0-9]*\)\/\([0-9]*\)/\\1,\\2,\\3/" > %s' %
                (dash_file, out))

        if ts_correct == '1':
            host = local(
                'echo %s | sed "s/.*_\([a-z0-9\.]*\)_[0-9]*%s/\\1/"' %
                (dash_file, ifile_ext), capture=True)
            test_id = local(
                'echo %s | sed "s/\(.*\)_%s_.*/\\1/"' %
                (host, name), capture=True)
            out = adjust_timestamps(test_id, out, host, ',')

        out_files[name] = out

    return (test_id_arr, out_files)


# Extract DASH goodput data from httperf log files
# SEE _extract_dash_goodput()
@task
def extract_dash_goodput(test_id='', out_dir='', dash_log_list='',
                         out_name='', ts_correct='0', replot_only='0'):
    "Extract DASH goodput from httperf logs"

    _extract_dash_goodput(test_id, out_dir, dash_log_list, ts_correct, 
                          replot_only)

    # done
    puts('\n[MAIN] COMPLETED extracting DASH goodput %s \n' % test_id)


# Plot DASH goodput from httperf log files
# Parameters:
#       test_id: test ID prefix of experiment to analyse
#       out_dir: output directory for results
#       replot_only: don't extract data again, just redo the plot
#	dash_log_list: file name with a list of dash logs
#	lnames: semicolon-separated list of legend names
#       out_name: name prefix
#       pdf_dir: output directory for pdf files (graphs),
#                if not specified it is the same as out_dir
#       ymin: minimum value on y-axis
#       ymax: maximum value on y-axis
#       stime: start time of plot window in seconds
#              (by default 0.0 = start of experiment)
#       etime: end time of plot window in seconds (by default 0.0 = end of
#              experiment)
#       ts_correct: '0' use timestamps as they are (default)
#                   '1' correct timestamps based on clock offsets estimated
#                       from broadcast pings
#       plot_params: parameters passed to plot function via environment variables
#       plot_script: specify the script used for plotting, must specify full path
@task
def analyse_dash_goodput(test_id='', out_dir='', replot_only='0', dash_log_list='',
                         lnames='', out_name='', pdf_dir='', ymin=0, ymax=0,
                         stime='0.0', etime='0.0', ts_correct='0', plot_params='',
                         plot_script=''):
    "Plot DASH goodput from httperf logs"

    # get list of test_ids and data files for plot
    (test_id_arr, out_files) = _extract_dash_goodput(test_id, out_dir,
                                       dash_log_list, ts_correct, replot_only) 

    out_name = get_out_name(test_id_arr, out_name)
    plot_dash_goodput(
        test_id,
        out_files,
        'Transferred (MB)',
        'pdf',
        out_name +
        '_dashgp',
        pdf_dir=pdf_dir,
        sep=',',
        ymin=float(ymin),
        ymax=float(ymax),
        lnames=lnames,
        stime=float(stime),
        etime=float(etime),
        plot_params=plot_params,
        plot_script=plot_script)

    # done
    puts('\n[MAIN] COMPLETED plotting DASH goodput %s \n' % test_id)


# Extract RTT for flows using SPP
# The extracted files have an extension of .rtts. The format is CSV with the
# columns:
# 1. Timestamp RTT measured (seconds.microseconds)
# 2. RTT (seconds)
# Parameters:
#	test_id: test ID prefix of experiment to analyse
#	out_dir: output directory for results
#	replot_only: don't extract data again that is already extracted
#	source_filter: filter on specific sources
#	udp_map: map that defines unidirectional UDP flows to combine. Format:
#	<ip1>,<port1>:<ip2>,<port2>[;<ip3>,<port3>:<ip4>,<port4>]*
#       ts_correct: '0' use timestamps as they are (default)
#                   '1' correct timestamps based on clock offsets estimated
#                       from broadcast pings
def _extract_rtt(test_id='', out_dir='', replot_only='0', source_filter='',
                udp_map='', ts_correct='0'):
    "Extract RTT of flows with SPP"

    ifile_ext = '.dmp.gz'
    ofile_ext = '.rtts'

    out_files = {}
    out_groups = {}
    udp_reverse_map = {}

    test_id_arr = test_id.split(';')
    if len(test_id_arr) == 0 or test_id_arr[0] == '':
        abort('Must specify test_id parameter')

    if source_filter != '':
        _build_source_filter(source_filter)

    local('which spp')

    # make sure specified dir has valid form
    out_dir = valid_dir(out_dir)

    if udp_map != '':
        entries = udp_map.split(';')
        for entry in entries:
            # need to add forward and reverse mapping
            k, v = entry.split(':')
            udp_reverse_map[k] = v
            udp_reverse_map[v] = k

    group = 1
    for test_id in test_id_arr:

        # first process tcpdump files (ignore router and ctl interface tcpdumps)
        (test_id_arr, tcpdump_files) = get_testid_file_list('', test_id,
                                       ifile_ext, 
                                       'grep -v "router.dmp.gz" | grep -v "ctl.dmp.gz"')

        for tcpdump_file in tcpdump_files:
            # get input directory name and create result directory if necessary
            dir_name = os.path.dirname(tcpdump_file)
            mkdir_p(dir_name + '/' + out_dir)

            # unique flows
            flows = _list(local('zcat %s | tcpdump -nr - "tcp" | '
                                'awk \'{ if ( $2 == "IP" ) { print $3 " " $5 " tcp" } }\' | '
                                'sed "s/://" | '
                                'sed "s/\.\([0-9]*\) /,\\1 /g" | sed "s/ /,/g" | '
                                'LC_ALL=C sort -u' %
                                tcpdump_file, capture=True))
            flows += _list(local('zcat %s | tcpdump -nr - "udp" | '
                                 'awk \'{ if ( $2 == "IP" ) { print $3 " " $5 " udp" } }\' | '
                                 'sed "s/://" | '
                                 'sed "s/\.\([0-9]*\) /,\\1 /g" | sed "s/ /,/g" | '
                                 'LC_ALL=C sort -u' %
                                 tcpdump_file, capture=True))

            # since client sends first packet to server, client-to-server flows
            # will always be first

            for flow in flows:

                src, src_port, dst, dst_port, proto = flow.split(',')

                # get external and internal addresses
                src, src_internal = get_address_pair(src, do_abort='0')
                dst, dst_internal = get_address_pair(dst, do_abort='0')

                if src == '' or dst == '':
                    continue

                # flow name
                name = src_internal + '_' + src_port + \
                    '_' + dst_internal + '_' + dst_port
                rev_name = dst_internal + '_' + dst_port + \
                    '_' + src_internal + '_' + src_port

                if name not in out_files and rev_name not in out_files:

                    # the two dump files
                    dump1 = dir_name + '/' + test_id + '_' + src + ifile_ext 
                    dump2 = dir_name + '/' + test_id + '_' + dst + ifile_ext 

                    # control the fields used by spp for generating the packet
                    # ids (hashes)
                    if proto == 'udp':
                        pid_fields = 2111
                    else:
                        pid_fields = 511

                    if proto == 'tcp':
                        filter1 = 'host ' + src_internal + \
                            ' && port ' + src_port
                        filter2 = 'host ' + src_internal + \
                            ' && port ' + src_port
                    else:
                        entry = udp_reverse_map.get(
                            src_internal + ',' + src_port, '')
                        if entry != '':
                            src2_internal, src2_port = entry.split(',')
                            name = src_internal + '_' + src_port + \
                                '_' + src2_internal + '_' + src2_port
                            rev_name = src2_internal + '_' + src2_port + \
                                '_' + src_internal + '_' + src_port
                            filter1 = '( host ' + src_internal + ' && port ' + src_port + \
                                ') || ( host ' + src2_internal + \
                                ' && port ' + src2_port + ')'
                            filter2 = '( host ' + src_internal + ' && port ' + src_port + \
                                ') || ( host ' + src2_internal + \
                                ' && port ' + src2_port + ')'
                            if rev_name in out_files:
                                continue

                    out1 = dir_name + '/' + out_dir + test_id + \
                        '_' + src + '_filtered_' + name + '_ref.dmp'
                    out2 = dir_name + '/' + out_dir + test_id + \
                        '_' + dst + '_filtered_' + name + '_mon.dmp'
                    out_rtt = dir_name + '/' + out_dir + \
                        test_id + '_' + name + ofile_ext 
                    rev_out_rtt = dir_name + '/' + out_dir + \
                        test_id + '_' + rev_name + ofile_ext 

                    if replot_only == '0' or not ( os.path.isfile(out_rtt) and \
                                                   os.path.isfile(rev_out_rtt) ): 
                        # create filtered tcpdumps
                        local(
                            'zcat %s | tcpdump -nr - -w %s "%s"' %
                            (dump1, out1, filter1))
                        local(
                            'zcat %s | tcpdump -nr - -w %s "%s"' %
                            (dump2, out2, filter2))

                        # compute rtts with spp
                        local(
                            'spp -# %s -a %s -f %s -A %s -F %s > %s' %
                            (pid_fields, src_internal, out1, dst_internal, out2, out_rtt))
                        local(
                            'spp -# %s -a %s -f %s -A %s -F %s > %s' %
                            (pid_fields,
                             dst_internal,
                             out2,
                             src_internal,
                             out1,
                             rev_out_rtt))

                        # remove filtered tcpdumps
                        local('rm -f %s %s' % (out1, out2))

                    if _in_source_filter(name):
                        if ts_correct == '1':
                            out = adjust_timestamps(test_id, out_rtt, src, ' ')
                        out_files[name] = out_rtt
                        out_groups[out_rtt] = group

                    if _in_source_filter(rev_name):
                        if ts_correct == '1':
                            out = adjust_timestamps(test_id, rev_out_rtt, dst, ' ')
                        out_files[rev_name] = rev_out_rtt
                        out_groups[rev_out_rtt] = group

        group += 1

    return (test_id_arr, out_files, out_groups)


# Extract RTT for flows using SPP
# SEE _extract_rtt()
@task
def extract_rtt(test_id='', out_dir='', replot_only='0', source_filter='',
                udp_map='', ts_correct='0'):
    "Extract RTT of flows with SPP"

    _extract_rtt(test_id, out_dir, replot_only, source_filter,
                udp_map, ts_correct)

    # done
    puts('\n[MAIN] COMPLETED extracting RTTs %s \n' % test_id)


# Plot RTT for flows using SPP
# Parameters:
#       test_id: test ID prefix of experiment to analyse
#       out_dir: output directory for results
#       replot_only: don't extract data again, just redo the plot
#       source_filter: filter on specific sources
#       min_values: minimum number of data points in file, if fewer points
#                   the file is ignored
#       udp_map: map that defines unidirectional UDP flows to combine. Format:
#       <ip1>,<port1>:<ip2>,<port2>[;<ip3>,<port3>:<ip4>,<port4>]*
#       omit_const: '0' don't omit anything,
#                   '1' omit any series that are 100% constant
#                       (e.g. because there was no data flow)
#       ymin: minimum value on y-axis
#       ymax: maximum value on y-axis
#       lnames: semicolon-separated list of legend names
#       stime: start time of plot window in seconds
#              (by default 0.0 = start of experiment)
#       etime: end time of plot window in seconds
#              (by default 0.0 = end of experiment)
#       out_name: name prefix
#       pdf_dir: output directory for pdf files (graphs), if not specified it is
#                the same as out_dir
#       ts_correct: '0' use timestamps as they are (default)
#                   '1' correct timestamps based on clock offsets estimated
#                       from broadcast pings
#       plot_params: set env parameters for plotting
#       plot_script: specify the script used for plotting, must specify full path
@task
def analyse_rtt(test_id='', out_dir='', replot_only='0', source_filter='',
                min_values='3', udp_map='', omit_const='0', ymin='0', ymax='0',
                lnames='', stime='0.0', etime='0.0', out_name='', pdf_dir='',
                ts_correct='0', plot_params='', plot_script=''):
    "Plot RTT of flows with SPP"

    (test_id_arr, 
     out_files, 
     out_groups) = _extract_rtt(test_id, out_dir, replot_only, 
                                 source_filter, udp_map, ts_correct)

    (out_files, out_groups) = filter_min_values(out_files, out_groups, min_values)
    out_name = get_out_name(test_id_arr, out_name)
    plot_time_series(out_name, out_files, 'SPP RTT (ms)', 2, 1000.0, 'pdf',
                     out_name + '_spprtt', pdf_dir=pdf_dir, omit_const=omit_const,
                     ymin=float(ymin), ymax=float(ymax), lnames=lnames,
                     stime=stime, etime=etime, groups=out_groups, plot_params=plot_params,
                     plot_script=plot_script)

    # done
    puts('\n[MAIN] COMPLETED plotting RTTs %s \n' % test_id)


# Extract data from siftr files
# Parameters:
#       test_id: test ID prefix of experiment to analyse
#	out_dir: output directory for results
#       replot_only: don't extract data again, just redo the plot
#       source_filter: filter on specific sources
#	attributes: comma-separated list of attributes to extract from siftr file
#                   (refer to siftr documentation for column description)
#	out_file_ext: extension for the output file containing the extracted data
#	post_proc: name of function used for post-processing the extracted data
#       ts_correct: '0' use timestamps as they are (default)
#                   '1' correct timestamps based on clock offsets estimated
#                       from broadcast pings
#       io_filter:  'i' only use statistics from incoming packets
#                   'o' only use statistics from outgoing packets
#                   'io' use statistics from incooming and outgoing packets
def extract_siftr(test_id='', out_dir='', replot_only='0', source_filter='',
                  attributes='', out_file_ext='', post_proc=None, 
                  ts_correct='0', io_filter='o'):

    out_files = {}
    out_groups = {}

    if io_filter != 'i' and io_filter != 'o' and io_filter != 'io':
        abort('Invalid parameter value for io_filter')
    if io_filter == 'io':
        io_filter = '(i|o)'

    test_id_arr = test_id.split(';')

    if source_filter != '':
        _build_source_filter(source_filter)

    group = 1
    for test_id in test_id_arr:

        # first process siftr files
        siftr_files = _list(
            local(
                'find -L . -name "%s*siftr.log.gz" -print | sed -e "s/\.\///"' %
                test_id,
                capture=True))

        for siftr_file in siftr_files:
            # get input directory name and create result directory if necessary
            dir_name = os.path.dirname(siftr_file)
            mkdir_p(dir_name + '/' + out_dir)

            # check that file is complete, i.e. we have the disable line
            with settings(warn_only=True):
                last_line = local(
                    'zcat %s | tail -1 | grep disable_time_secs' %
                    siftr_file,
                    capture=True)
            if last_line == '':
                abort('Incomplete siftr file %s' % siftr_file)

            # check that we have patched siftr (27 columns)
            cols = int(
                local(
                    'zcat %s | head -2 | tail -1 | sed "s/,/ /g" | wc -w' %
                    siftr_file,
                    capture=True))
            if cols < 27:
                abort('siftr needs to be patched to output ertt estimates')

            # we need to stop reading before the log disable line
            rows = str(int(
                local('zcat %s | wc -l | awk \'{ print $1 }\'' %
                      (siftr_file), capture=True)) - 3)
            # unique flows
            flows = _list(
                local(
                    'zcat %s | grep -v enable | head -%s | '
                    'egrep "^%s" | '
                    'cut -d\',\' -f 4,5,6,7 | LC_ALL=C sort -u' %
                    (siftr_file, rows, io_filter), capture=True))

            for flow in flows:

                src, src_port, dst, dst_port = flow.split(',')

                # get external and internal addresses
                src, src_internal = get_address_pair(src, do_abort='0')
                dst, dst_internal = get_address_pair(dst, do_abort='0')

                if src == '' or dst == '':
                    continue

                flow_name = flow.replace(',', '_')
                out = dir_name + '/' + out_dir + test_id + \
                    '_' + flow_name + '_siftr.' + out_file_ext
                if replot_only == '0' or not os.path.isfile(out) :
                    local(
                        'zcat %s | grep -v enable | head -%s | '
                        'egrep "^%s" | '
                        'cut -d\',\' -f 3,4,5,6,7,%s | '
                        'grep "%s" | cut -d\',\' -f 1,6- > %s' %
                        (siftr_file, rows, io_filter, attributes, flow, out))

                    if post_proc is not None:
                        post_proc(siftr_file, out)

                if _in_source_filter(flow_name):
                    if ts_correct == '1':
                        host = local(
                            'echo %s | sed "s/.*_\([a-z0-9\.]*\)_siftr.log.gz/\\1/"' %
                            siftr_file,
                            capture=True)
                        out = adjust_timestamps(test_id, out, host, ',')

                    out_files[flow_name] = out
                    out_groups[out] = group

        group += 1

    return (out_files, out_groups)


# guess web10g version (based on first file only!)
# Parameters:
#       test_id: test ID prefix of experiment to analyse
def guess_version_web10g(test_id=''):

    test_id_arr = test_id.split(';')
    test_id = test_id_arr[0]
    web10g_files = _list(
       	  local('find -L . -name "%s*web10g.log.gz" -print | sed -e "s/\.\///"' %
              	test_id, capture=True))

    # if there are no web10g files the following will return '2.0.7', but in this
    # case we don't care anyway 
    try:
        web10g_file = web10g_files[0]
        colnum = local('zcat %s | sed -e "s/,/ /g" | head -1 | wc -w' % web10g_file,
		capture=True)

        if int(colnum) == 122:
	    return '2.0.7'
	elif int(colnum) == 128:
	    return '2.0.9'
	else:
	    return '2.0.7'
    except:
        return '2.0.7'


# Extract data from web10g files
# Parameters:
#       test_id: test ID prefix of experiment to analyse
#	out_dir: output directory for results
#       replot_only: don't extract data again, just redo the plot
#       source_filter: filter on specific sources
#       attributes: comma-separated list of attributes to extract from web10g file
#                   (refer to web10g documentation for column description)
#       out_file_ext: extension for the output file containing the extracted data
#       post_proc: name of function used for post-processing the extracted data
#       ts_correct: '0' use timestamps as they are (default)
#                   '1' correct timestamps based on clock offsets estimated
#                       from broadcast pings
def extract_web10g(test_id='', out_dir='', replot_only='0', source_filter='',
                   attributes='', out_file_ext='', post_proc=None,
                   ts_correct='0'):

    out_files = {}
    out_groups = {}

    test_id_arr = test_id.split(';')

    if source_filter != '':
        _build_source_filter(source_filter)

    group = 1
    for test_id in test_id_arr:

        # second process web10g files
        web10g_files = _list(
            local(
                'find -L . -name "%s*web10g.log.gz" -print | sed -e "s/\.\///"' %
                test_id,
                capture=True))
        for web10g_file in web10g_files:
            # get input directory name and create result directory if necessary
            dir_name = os.path.dirname(web10g_file)
            mkdir_p(dir_name + '/' + out_dir)

            # make sure we have exit status 0 for this, hence the final echo
            errors = local(
                'zcat %s | grep -v "runbg_wrapper.sh" | grep -v "Timestamp" ' 
                'egrep "[a-z]+" ; echo -n ""' %
                web10g_file,
                capture=True)
            if errors != '':
                warn('Errors in %s:\n%s' % (web10g_file, errors))

            # unique flows
            # the sed command here suppresses the last line, cause that can be
            # incomplete
            flows = _list(
                local(
                    'zcat %s | egrep -v "[a-z]+" | sed -n \'$!p\' | '
                    'cut -d\',\' -f 3,4,5,6 | LC_ALL=C sort -u' %
                    (web10g_file),
                    capture=True))

            for flow in flows:

                src, src_port, dst, dst_port = flow.split(',')

                # get external aNd internal addresses
                src, src_internal = get_address_pair(src, do_abort='0')
                dst, dst_internal = get_address_pair(dst, do_abort='0')

                if src == '' or dst == '':
                    continue

                flow_name = flow.replace(',', '_')
                out = dir_name + '/' + out_dir + test_id + \
                    '_' + flow_name + '_web10g.' + out_file_ext
                if replot_only == '0' or not os.path.isfile(out) :
                    # the first grep removes lines with netlink errors printed out
                    # or last incomplete lines (sed '$d')
                    # (not sure how to suppress them in web10g)
                    # the awk command here is a little trick to not print out lines when
                    # no data is flying around; basically it does suppress lines if
                    # there is no change with respect to the fields specified.
                    # this makes the output comparable to siftr where we only
                    # have output if data is flying around.
                    local('zcat %s | egrep -v "[a-z]+" | sed \'$d\' | '
                          'cut -d\',\' -f 1,3,4,5,6,7,8,13,14,%s | grep "%s" | '
                          'awk -F \',\' \'!a[$2$3$4$5$6$7$8$9]++\' | cut -d\',\' -f 1,10- > %s' %
                          (web10g_file, attributes, flow, out))

                    if post_proc is not None:
                        post_proc(web10g_file, out)

                if _in_source_filter(flow_name):
		    if ts_correct == '1':
                        host = local(
                            'echo %s | sed "s/.*_\([a-z0-9\.]*\)_web10g.log.gz/\\1/"' %
                            web10g_file,
                            capture=True)

                        out = adjust_timestamps(test_id, out, host, ',') 

                    out_files[flow_name] = out
                    out_groups[out] = group

        group += 1

    return (out_files, out_groups)


# siftr prints out very high cwnd (max cwnd?) values for some tcp algorithms
# at the start, remove them
# Parameters:
#	siftr_file: the data extracted from siftr log
#	out_file: file name for post processed data
def post_proc_siftr_cwnd(siftr_file, out_file):
    tmp_file = local('mktemp "tmp.XXXXXXXXXX"', capture=True)
    local(
        'cat %s | sed -e "1,2d\" > %s && mv %s %s' %
        (out_file, tmp_file, tmp_file, out_file))


# Extract cwnd over time
# The extracted files have an extension of .cwnd. The format is CSV with the
# columns:
# 1. Timestamp RTT measured (seconds.microseconds)
# 2. CWND 
# Parameters:
#       test_id: test ID prefix of experiment to analyse
#       out_dir: output directory for results
#       replot_only: don't extract data again that is extracted already
#       source_filter: filter on specific sources
#       ts_correct: '0' use timestamps as they are (default)
#                   '1' correct timestamps based on clock offsets estimated
#                       from broadcast pings
#       io_filter:  'i' only use statistics from incoming packets
#                   'o' only use statistics from outgoing packets
#                   'io' use statistics from incooming and outgoing packets
#                   (only effective for SIFTR files)
def _extract_cwnd(test_id='', out_dir='', replot_only='0', source_filter='',
                 ts_correct='0', io_filter='o'):
    "Extract CWND over time"

    test_id_arr = test_id.split(';')
    if len(test_id_arr) == 0 or test_id_arr[0] == '':
        abort('Must specify test_id parameter')

    # make sure specified dir has valid form
    out_dir = valid_dir(out_dir)

    (files1,
     groups1) = extract_siftr(test_id,
                              out_dir,
                              replot_only,
                              source_filter,
                              '9',
                              'cwnd',
                              post_proc_siftr_cwnd,
                              ts_correct=ts_correct,
                              io_filter=io_filter)
    (files2,
     groups2) = extract_web10g(test_id,
                               out_dir,
                               replot_only,
                               source_filter,
                               '26',
                               'cwnd',
                               ts_correct=ts_correct)

    all_files = dict(files1.items() + files2.items())
    all_groups = dict(groups1.items() + groups2.items())

    return (test_id_arr, all_files, all_groups)


# Extract cwnd over time
# SEE _extract_cwnd
@task
def extract_cwnd(test_id='', out_dir='', replot_only='0', source_filter='',
                 ts_correct='0', io_filter='o'):
    "Extract CWND over time"

    _extract_cwnd(test_id, out_dir, replot_only, source_filter, ts_correct,
                  io_filter)

    # done
    puts('\n[MAIN] COMPLETED extracting CWND %s \n' % test_id)


# Analyse cwnd over time
# Parameters:
#       test_id: test ID prefix of experiment to analyse
#	out_dir: output directory for results
#       replot_only: don't extract data again, just redo the plot
#       source_filter: filter on specific sources
#       min_values: minimum number of data points in file, if fewer points
#                   the file is ignored
#       omit_const: '0' don't omit anything,
#                   '1' omit any series that are 100% constant
#                       (e.g. because there was no data flow)
#       ymin: minimum value on y-axis
#       ymax: maximum value on y-axis
#       lnames: semicolon-separated list of legend names
#       stime: start time of plot window in seconds
#              (by default 0.0 = start of experiment)
#       etime: end time of plot window in seconds
#              (by default 0.0 = end of experiment)
#       out_name: name prefix
#       pdf_dir: output directory for pdf files (graphs), if not specified it is
#                the same as out_dir
#       ts_correct: '0' use timestamps as they are (default)
#                   '1' correct timestamps based on clock offsets estimated
#                       from broadcast pings
#       io_filter:  'i' only use statistics from incoming packets
#                   'o' only use statistics from outgoing packets
#                   'io' use statistics from incooming and outgoing packets
#                   (only effective for SIFTR files)
#       plot_params: set env parameters for plotting
#       plot_script: specify the script used for plotting, must specify full path
@task
def analyse_cwnd(test_id='', out_dir='', replot_only='0', source_filter='',
                 min_values='3', omit_const='0', ymin='0', ymax='0', lnames='',
                 stime='0.0', etime='0.0', out_name='', pdf_dir='', ts_correct='0',
                 io_filter='o', plot_params='', plot_script=''):
    "Plot CWND over time"

    (test_id_arr,
     out_files, 
     out_groups) = _extract_cwnd(test_id, out_dir, replot_only, 
                                 source_filter, ts_correct, io_filter)

    if len(out_files) > 0:
        (out_files, out_groups) = filter_min_values(out_files, out_groups, min_values)
        out_name = get_out_name(test_id_arr, out_name)
        plot_time_series(out_name, out_files, 'CWND (k)', 2, 0.001, 'pdf',
                         out_name + '_cwnd', pdf_dir=pdf_dir, sep=",",
                         omit_const=omit_const, ymin=float(ymin), ymax=float(ymax),
                         lnames=lnames, stime=stime, etime=etime, groups=out_groups,
                         plot_params=plot_params, plot_script=plot_script)

    # done
    puts('\n[MAIN] COMPLETED plotting CWND %s \n' % test_id)


# siftr values are in units of tcp_rtt_scale*hz, so we need to convert to milliseconds
# Parameters:
#       siftr_file: the data extracted from siftr log
#       out_file: file name for post processed data
def post_proc_siftr_rtt(siftr_file, out_file):

    hz = local(
        'zcat %s | head -1 | awk \'{ print $4 }\' | cut -d\'=\' -f 2' %
        siftr_file,
        capture=True)
    tcp_rtt_scale = local(
        'zcat %s | head -1 | awk \'{ print $5 }\' | cut -d\'=\' -f 2' %
        siftr_file,
        capture=True)
    scaler = str(float(hz) * float(tcp_rtt_scale) / 1000)
    # XXX hmm maybe do the following in python
    tmp_file = local('mktemp "tmp.XXXXXXXXXX"', capture=True)
    local('cat %s | awk -v scaler=%s \'BEGIN { FS = "," } ; '
          '{ printf("%%s,%%.0f,%%s\\n", $1, $2/scaler, $3) }\' > %s && mv %s %s' %
          (out_file, scaler, tmp_file, tmp_file, out_file))


# Extract RTT over time estimated by TCP 
# The extracted files have an extension of .tcp_rtt. The format is CSV with the
# columns:
# 1. Timestamp RTT measured (seconds.microseconds)
# 2. Smoothed RTT
# 3. Sample/Unsmoothed RTT 
# Parameters:
#       test_id: test ID prefix of experiment to analyse
#       out_dir: output directory for results
#       replot_only: don't extract data again that is extracted already
#       source_filter: filter on specific sources
#       ts_correct: '0' use timestamps as they are (default)
#                   '1' correct timestamps based on clock offsets estimated
#                       from broadcast pings
#       io_filter:  'i' only use statistics from incoming packets
#                   'o' only use statistics from outgoing packets
#                   'io' use statistics from incooming and outgoing packets
#                   (only effective for SIFTR files)
#       web10g_version: web10g version string (default is 2.0.9) 
def _extract_tcp_rtt(test_id='', out_dir='', replot_only='0', source_filter='',
                     ts_correct='0', io_filter='o', web10g_version='2.0.9'):
    "Extract RTT as seen by TCP (smoothed RTT)"

    test_id_arr = test_id.split(';')
    if len(test_id_arr) == 0 or test_id_arr[0] == '':
        abort('Must specify test_id parameter')

    # make sure specified dir has valid form
    out_dir = valid_dir(out_dir)

    # output smoothed rtt and improved sample rtt (patched siftr required),
    # post process to get rtt in milliseconds
    (files1,
     groups1) = extract_siftr(test_id,
                              out_dir,
                              replot_only,
                              source_filter,
                              '17,27',
                              'tcp_rtt',
                              post_proc_siftr_rtt,
                              ts_correct=ts_correct,
                              io_filter=io_filter)

    # output smoothed RTT and sample RTT in milliseconds
    
    if web10g_version == '2.0.9':
        web10g_version = guess_version_web10g(test_id)

    if web10g_version == '2.0.7':
        data_columns = '23,45'
    elif web10g_version == '2.0.9':
        data_columns = '23,47'
    else:
        data_columns = '23,45'

    (files2,
     groups2) = extract_web10g(test_id,
                               out_dir,
                               replot_only,
                               source_filter,
                               data_columns,
                               'tcp_rtt',
                               ts_correct=ts_correct)

    all_files = dict(files1.items() + files2.items())
    all_groups = dict(groups1.items() + groups2.items())

    return (test_id_arr, all_files, all_groups)


# Extract RTT over time estimated by TCP 
# SEE _extract_tcp_rtt
@task
def extract_tcp_rtt(test_id='', out_dir='', replot_only='0', source_filter='',
                     ts_correct='0', io_filter='o', web10g_version='2.0.9'):
    "Extract RTT as seen by TCP (smoothed RTT)"

    _extract_tcp_rtt(test_id, out_dir, replot_only, source_filter, 
                     ts_correct, io_filter, web10g_version)

    # done
    puts('\n[MAIN] COMPLETED extracting TCP RTTs %s \n' % test_id)


# Plot RTT over time estimated by tcp
# Parameters:
#       test_id: test ID prefix of experiment to analyse
#	out_dir: output directory for results
#       replot_only: don't extract data again, just redo the plot
#       source_filter: filter on specific sources
#       min_values: datasets with fewer values won't be plotted
#	smoothed: '0' plot non-smooth RTT (enhanced RTT in case of FreeBSD),
#                 '1' plot smoothed RTT estimates (non enhanced RTT in case of FreeBSD)
#       omit_const: '0' don't omit anything,
#                   '1' omit any series that are 100% constant
#                       (e.g. because there was no data flow)
#       ymin: minimum value on y-axis
#       ymax: maximum value on y-axis
#       lnames: semicolon-separated list of legend names
#       stime: start time of plot window in seconds
#              (by default 0.0 = start of experiment)
#       etime: end time of plot window in seconds
#              (by default 0.0 = end of experiment)
#       out_name: name prefix
#       pdf_dir: output directory for pdf files (graphs), if not specified it is
#                the same as out_dir
#       ts_correct: '0' use timestamps as they are (default)
#                   '1' correct timestamps based on clock offsets estimated
#                       from broadcast pings
#       io_filter:  'i' only use statistics from incoming packets
#                   'o' only use statistics from outgoing packets
#                   'io' use statistics from incooming and outgoing packets
#                   (only effective for SIFTR files)
# 	web10g_version: web10g version string (default is 2.0.9) 
#       plot_params: set env parameters for plotting
#       plot_script: specify the script used for plotting, must specify full path
@task
def analyse_tcp_rtt(test_id='', out_dir='', replot_only='0', source_filter='',
                    min_values='3', smoothed='1', omit_const='0', ymin='0', ymax='0',
                    lnames='', stime='0.0', etime='0.0', out_name='', pdf_dir='',
                    ts_correct='0', io_filter='o', web10g_version='2.0.9',
                    plot_params='', plot_script=''):
    "Plot RTT as seen by TCP (smoothed RTT)"

    (test_id_arr,
     out_files, 
     out_groups) = _extract_tcp_rtt(test_id, out_dir, replot_only, 
                              source_filter, ts_correct, io_filter, web10g_version)
 
    if len(out_files) > 0:
        (out_files, out_groups) = filter_min_values(out_files, out_groups, min_values)
        out_name = get_out_name(test_id_arr, out_name)
        if smoothed == '1':
            plot_time_series(out_name, out_files, 'Smoothed TCP RTT (ms)', 2, 1.0,
                             'pdf', out_name + '_smooth_tcprtt', pdf_dir=pdf_dir,
                             sep=",", omit_const=omit_const,
                             ymin=float(ymin), ymax=float(ymax), lnames=lnames,
                             stime=stime, etime=etime, groups=out_groups,
                             plot_params=plot_params, plot_script=plot_script)
        else:
            plot_time_series(out_name, out_files, 'TCP RTT (ms)', 3, 1.0, 'pdf',
                             out_name + '_tcprtt', pdf_dir=pdf_dir, sep=",",
                             omit_const=omit_const, ymin=float(ymin),
                             ymax=float(ymax), lnames=lnames, stime=stime,
                             etime=etime, groups=out_groups, 
                             plot_params=plot_params, plot_script=plot_script)

    # done
    puts('\n[MAIN] COMPLETED plotting TCP RTTs %s \n' % test_id)


# Extract some TCP statistic (based on siftr/web10g output)
# The extracted files have an extension of .tcpstat_<num>, where <num> is the index
# of the statistic. The format is CSV with the columns:
# 1. Timestamp RTT measured (seconds.microseconds)
# 2. TCP statistic chosen 
# Parameters:
#       test_id: test ID prefix of experiment to analyse
#       out_dir: output directory for results
#       replot_only: don't extract data again that is already extracted
#       source_filter: filter on specific sources
#       siftr_index: an integer number of the column in siftr log files
#                    (note if you have sitfr and web10g logs, you must also
#                     specify web10g_index) (default = 9, CWND)
#       web10g_index: an integer number of the column in web10g log files (note if
#                     you have web10g and siftr logs, you must also specify siftr_index)
#                     (default = 26, CWND)
#                     example: analyse_tcp_stat(siftr_index=17,web10_index=23,...)
#                     would plot smoothed RTT estimates.
#       ts_correct: '0' use timestamps as they are (default)
#                   '1' correct timestamps based on clock offsets estimated
#                       from broadcast pings
#       io_filter:  'i' only use statistics from incoming packets
#                   'o' only use statistics from outgoing packets
#                   'io' use statistics from incooming and outgoing packets
#                   (only effective for SIFTR files)
def _extract_tcp_stat(test_id='', out_dir='', replot_only='0', source_filter='',
                     siftr_index='9', web10g_index='26', ts_correct='0',
                     io_filter='o'):
    "Extract TCP Statistic"

    test_id_arr = test_id.split(';')
    if len(test_id_arr) == 0 or test_id_arr[0] == '':
        abort('Must specify test_id parameter')

    # make sure specified dir has valid form
    out_dir = valid_dir(out_dir)

    # output smoothed rtt and improved sample rtt (patched siftr required),
    # post process to get rtt in milliseconds
    (files1,
     groups1) = extract_siftr(test_id,
                              out_dir,
                              replot_only,
                              source_filter,
                              siftr_index,
                              'tcpstat_' + siftr_index,
                              ts_correct=ts_correct,
                              io_filter=io_filter)

    # output smoothed RTT and sample RTT in milliseconds
    (files2,
     groups2) = extract_web10g(test_id,
                               out_dir,
                               replot_only,
                               source_filter,
                               web10g_index,
                               'tcpstat_' + web10g_index,
                               ts_correct=ts_correct)

    all_files = dict(files1.items() + files2.items())
    all_groups = dict(groups1.items() + groups2.items())

    return (test_id_arr, all_files, all_groups)


# Extract some TCP statistic (based on siftr/web10g output)
# SEE _extract_tcp_stat
@task
def extract_tcp_stat(test_id='', out_dir='', replot_only='0', source_filter='',
                     siftr_index='9', web10g_index='26', ts_correct='0',
                     io_filter='o'):
    "Extract TCP Statistic"

    _extract_tcp_stat(test_id, out_dir, replot_only, source_filter,
                      siftr_index, web10g_index, ts_correct, io_filter)

    # done
    puts('\n[MAIN] COMPLETED extracting TCP Statistic %s \n' % test_id)


# Plot some TCP statistic (based on siftr/web10g output)
# Parameters:
#       test_id: test ID prefix of experiment to analyse
#       out_dir: output directory for results
#       replot_only: don't extract data again, just redo the plot
#       source_filter: filter on specific sources
#       min_values: minimum number of data points in file, if fewer points
#                   the file is ignored
#       omit_const: '0' don't omit anything,
#                   '1' omit any Series that are 100% constant
#                       (e.g. because there was no data flow)
#	siftr_index: an integer number of the column in siftr log files
#                    (note if you have sitfr and web10g logs, you must also
#                     specify web10g_index) (default = 9, CWND)
#	web10g_index: an integer number of the column in web10g log files (note if
#                     you have web10g and siftr logs, you must also specify siftr_index)
#                     (default = 26, CWND)
#		      example: analyse_tcp_stat(siftr_index=17,web10_index=23,...)
#                     would plot smoothed RTT estimates.
#	ylabel: label for y-axis in plot
#	yscaler: scaler for y-axis values (must be a floating point number)
#       ymin: minimum value on y-axis
#       ymax: maximum value on y-axis
#       lnames: semicolon-separated list of legend names
#       stime: start time of plot window in seconds (by default 0.0 = start of experiment)
#       etime: end time of plot window in seconds (by default 0.0 = end of experiment)
#       out_name: name prefix
#       pdf_dir: output directory for pdf files (graphs), if not specified it is
#                the same as out_dir
#       ts_correct: '0' use timestamps as they are (default)
#                   '1' correct timestamps based on clock offsets estimated
#                       from broadcast pings
#       io_filter:  'i' only use statistics from incoming packets
#                   'o' only use statistics from outgoing packets
#                   'io' use statistics from incooming and outgoing packets
#                   (only effective for SIFTR files)
#       plot_params: set env parameters for plotting
#       plot_script: specify the script used for plotting, must specify full path
@task
def analyse_tcp_stat(test_id='', out_dir='', replot_only='0', source_filter='',
                     min_values='3', omit_const='0', siftr_index='9', web10g_index='26',
                     ylabel='', yscaler='1.0', ymin='0', ymax='0', lnames='',
                     stime='0.0', etime='0.0', out_name='', pdf_dir='', ts_correct='0',
                     io_filter='o', plot_params='', plot_script=''):
    "Compute TCP Statistic"

    (test_id_arr,
     out_files,
     out_groups) =_extract_tcp_stat(test_id, out_dir, replot_only, source_filter,
                      siftr_index, web10g_index, ts_correct, io_filter)

    if len(out_files) > 0:
        (out_files, out_groups) = filter_min_values(out_files, out_groups, min_values)
        out_name = get_out_name(test_id_arr, out_name)
        plot_time_series(out_name, out_files, ylabel, 2, float(yscaler), 'pdf',
                         out_name + '_tcpstat_' +
                         siftr_index + '_' + web10g_index,
                         pdf_dir=pdf_dir, sep=",", omit_const=omit_const,
                         ymin=float(ymin), ymax=float(ymax), lnames=lnames, stime=stime,
                         etime=etime, groups=out_groups, plot_params=plot_params,
                         plot_script=plot_script)

    # done
    puts('\n[MAIN] COMPLETED plotting TCP Statistic %s \n' % test_id)


# Extract throughput. Note the data files do not contain throughput values, but
# packet sizes. Only the plot function computes throughput based on the packet sizes.
# The extracted files have an extension of .psiz. The format is CSV with the
# columns:
# 1. Timestamp RTT measured (seconds.microseconds)
# 2. Packet size (bytes) 
# Parameters:
#       test_id: test ID prefix of experiment to analyse
#       out_dir: output directory for results
#       replot_only: don't extract data again that is already extracted 
#       source_filter: filter on specific sources
#       link_len: '0' throughput based on IP length (default),
#                 '1' throughput based on link-layer length
#       ts_correct: '0' use timestamps as they are (default)
#                   '1' correct timestamps based on clock offsets estimated
#                       from broadcast pings
def _extract_throughput(test_id='', out_dir='', replot_only='0', source_filter='',
                       link_len='0', ts_correct='0'):
    "Extract throughput for generated traffic flows"

    ifile_ext = '.dmp.gz'
    ofile_ext = '.psiz'

    out_files = {}
    out_groups = {}

    test_id_arr = test_id.split(';')
    if len(test_id_arr) == 0 or test_id_arr[0] == '':
        abort('Must specify test_id parameter')

    if source_filter != '':
        _build_source_filter(source_filter)

    # make sure specified dir has valid form
    out_dir = valid_dir(out_dir)

    group = 1
    for test_id in test_id_arr:

        # first process tcpdump files (ignore router and ctl interface tcpdumps)
        (test_id_arr, tcpdump_files) = get_testid_file_list('', test_id,
                                       ifile_ext,
                                       'grep -v "router.dmp.gz" | grep -v "ctl.dmp.gz"')

        for tcpdump_file in tcpdump_files:
            # get input directory name and create result directory if necessary
            dir_name = os.path.dirname(tcpdump_file)
            mkdir_p(dir_name + '/' + out_dir)

            # unique flows
            flows = _list(local('zcat %s | tcpdump -nr - "tcp" | '
                                'awk \'{ if ( $2 == "IP" ) { print $3 " " $5 " tcp" } }\' | '
                                'sed "s/://" | '
                                'sed "s/\.\([0-9]*\) /,\\1 /g" | sed "s/ /,/g" | '
                                'LC_ALL=C sort -u' %
                                tcpdump_file, capture=True))
            flows += _list(local('zcat %s | tcpdump -nr - "udp" | '
                                 'awk \'{ if ( $2 == "IP" ) { print $3 " " $5 " udp" } }\' | '
                                 'sed "s/://" | '
                                 'sed "s/\.\([0-9]*\) /,\\1 /g" | sed "s/ /,/g" | '
                                 'LC_ALL=C sort -u' %
                                 tcpdump_file, capture=True))

            # since client sends first packet to server, client-to-server flows
            # will always be first

            for flow in flows:

                src, src_port, dst, dst_port, proto = flow.split(',')

                # get external and internal addresses
                src, src_internal = get_address_pair(src, do_abort='0')
                dst, dst_internal = get_address_pair(dst, do_abort='0')

                if src == '' or dst == '':
                    continue

                # flow name
                name = src_internal + '_' + src_port + \
                    '_' + dst_internal + '_' + dst_port
                rev_name = dst_internal + '_' + dst_port + \
                    '_' + src_internal + '_' + src_port 

                # the two dump files
                dump1 = dir_name + '/' + test_id + '_' + src + ifile_ext 
                dump2 = dir_name + '/' + test_id + '_' + dst + ifile_ext 

                # tcpdump filters and output file names
                filter1 = 'src host ' + src_internal + ' && src port ' + src_port + \
                    ' && dst host ' + dst_internal + ' && dst port ' + dst_port
                filter2 = 'src host ' + dst_internal + ' && src port ' + dst_port + \
                    ' && dst host ' + src_internal + ' && dst port ' + src_port
                out_size1 = dir_name + '/' + out_dir + \
                    test_id + '_' + name + ofile_ext 
                out_size2 = dir_name + '/' + out_dir + \
                    test_id + '_' + rev_name + ofile_ext 

                if replot_only == '0' or not ( os.path.isfile(out_size1) and \
                                               os.path.isfile(out_size2) ):
                    # make sure for each flow we get the packet sizes captured
                    # at the _receiver_, hence we use filter1 with dump2 ...
                    if link_len == '0':
                        local(
                            'zcat %s | tcpdump -v -tt -nr - "%s" | '
                            'awk \'{ print $1 " " $NF }\' | grep ")$" | sed -e "s/)//" > %s' %
                            (dump2, filter1, out_size1))
                        local(
                            'zcat %s | tcpdump -v -tt -nr - "%s" | '
                            'awk \'{ print $1 " " $NF }\' | grep ")$" | sed -e "s/)//" > %s' %
                            (dump1, filter2, out_size2))
                    else:
                        local(
                            'zcat %s | tcpdump -e -tt -nr - "%s" | grep "ethertype IP" | '
                            'awk \'{ print $1 " " $9 }\' | sed -e "s/://" > %s' %
                            (dump2, filter1, out_size1))
                        local(
                            'zcat %s | tcpdump -e -tt -nr - "%s" | grep "ethertype IP" | '
                            'awk \'{ print $1 " " $9 }\' | sed -e "s/://" > %s' %
                            (dump1, filter2, out_size2))

                if name not in out_files:
                    if _in_source_filter(name):
                        if ts_correct == '1':
                            out_size1 = adjust_timestamps(test_id, out_size1, dst, ' ')
                        out_files[name] = out_size1
                        out_groups[out_size1] = group

                if rev_name not in out_files:
                    if _in_source_filter(rev_name):
                        if ts_correct == '1':
                            out_size2 = adjust_timestamps(test_id, out_size2, src, ' ')
                        out_files[rev_name] = out_size2
                        out_groups[out_size2] = group

        group += 1

    return (test_id_arr, out_files, out_groups)


# Extract throughput. Note the data files do not contain throughput values, but
# packet sizes. Only the plot function computes throughput based on the packet sizes.
# SEE _extract_throughput
@task
def extract_throughput(test_id='', out_dir='', replot_only='0', source_filter='',
                       link_len='0', ts_correct='0'):
    "Extract throughput for generated traffic flows"

    _extract_throughput(test_id, out_dir, replot_only, source_filter, link_len,
                        ts_correct)
    # done
    puts('\n[MAIN] COMPLETED extracting throughput %s \n' % test_id)


# Plot throughput
# Parameters:
#       test_id: test ID prefix of experiment to analyse
#	out_dir: output directory for results
#       replot_only: don't extract data again, just redo the plot
#       source_filter: filter on specific sources
#       min_values: minimum number of data points in file, if fewer points
#                   the file is ignored
#       omit_const: '0' don't omit anything,
#                   '1' omit any series that are 100% constant
#                       (e.g. because there was no data flow)
#       ymin: minimum value on y-axis
#       ymax: maximum value on y-axis
#       lnames: semicolon-separated list of legend names
#	link_len: '0' throughput based on IP length (default),
#                 '1' throughput based on link-layer length
#       stime: start time of plot window in seconds
#              (by default 0.0 = start of experiment)
#       etime: end time of plot window in seconds (by default 0.0 = end of experiment)
#       out_name: name prefix
#       pdf_dir: output directory for pdf files (graphs), if not specified it is
#                the same as out_dir
#       ts_correct: '0' use timestamps as they are (default)
#                   '1' correct timestamps based on clock offsets estimated
#                       from broadcast pings
#       plot_params: set env parameters for plotting
#       plot_script: specify the script used for plotting, must specify full path
@task
def analyse_throughput(test_id='', out_dir='', replot_only='0', source_filter='',
                       min_values='3', omit_const='0', ymin='0', ymax='0', lnames='',
                       link_len='0', stime='0.0', etime='0.0', out_name='',
                       pdf_dir='', ts_correct='0', plot_params='', plot_script=''):
    "Plot throughput for generated traffic flows"

    (test_id_arr,
     out_files, 
     out_groups) =_extract_throughput(test_id, out_dir, replot_only, 
                              source_filter, link_len, ts_correct)

    (out_files, out_groups) = filter_min_values(out_files, out_groups, min_values)
    out_name = get_out_name(test_id_arr, out_name)
    plot_time_series(out_name, out_files, 'Throughput (kbps)', 2, 0.008, 'pdf',
                     out_name + '_throughput', pdf_dir=pdf_dir, aggr='1',
                     omit_const=omit_const, ymin=float(ymin), ymax=float(ymax),
                     lnames=lnames, stime=stime, etime=etime, groups=out_groups,
                     plot_params=plot_params, plot_script=plot_script)

    # done
    puts('\n[MAIN] COMPLETED plotting throughput %s \n' % test_id)


# Get list of experiment IDs
# Parameters:
#       exp_list: list of all test IDs
#       test_id: test ID prefix of experiment to analyse 
def get_experiment_list(exp_list='', test_id=''):

    if test_id != '':
        experiments = [test_id]
    else:
        try:
            with open(exp_list) as f:
                # read lines without newlines
                experiments = f.read().splitlines()
        except IOError:
            abort('Cannot open file %s' % exp_list)

    return experiments


# Do all extraction 
# Parameters:
#       exp_list: list of all test IDs
#       test_id: test ID prefix of experiment to analyse
#       out_dir: output directory for result files
#       replot_only: don't extract data again, just redo the plot
#       source_filter: filter on specific sources
#       smoothed: '0' plot non-smooth RTT (enhanced RTT in case of FreeBSD),
#                 '1' plot smoothed RTT estimates (non enhanced RTT in case of FreeBSD)
#       resume_id: resume analysis with this test_id (ignore all test_ids before this),
#                  only effective if test_id is not specified
#       link_len: '0' throughput based on IP length (default),
#                 '1' throughput based on link-layer length
#       ts_correct: '0' use timestamps as they are (default)
#                   '1' correct timestamps based on clock offsets estimated
#                       from broadcast pings
#       io_filter:  'i' only use statistics from incoming packets
#                   'o' only use statistics from outgoing packets
#                   'io' use statistics from incooming and outgoing packets
#                   (only effective for SIFTR files)
#       web10g_version: web10g version string (default is 2.0.9)
@task
def extract_all(exp_list='experiments_completed.txt', test_id='', out_dir='',
                replot_only='0', source_filter='', smoothed='1', resume_id='', 
                link_len='0', ts_correct='0', io_filter='o', web10g_version='2.0.9'):
    "Extract SPP RTT, TCP RTT, CWND and throughput statistics"

    experiments = get_experiment_list(exp_list, test_id)

    do_analyse = True
    if resume_id != '':
        puts('Resuming analysis with test_id %s' % resume_id)
        do_analyse = False

    for test_id in experiments:

        if test_id == resume_id:
            do_analyse = True

        if do_analyse:
            execute(extract_rtt, test_id, out_dir, replot_only, source_filter,
                    ts_correct=ts_correct)
            execute(extract_cwnd, test_id, out_dir, replot_only, source_filter, 
                    ts_correct=ts_correct, io_filter=io_filter)
            execute(extract_tcp_rtt, test_id, out_dir, replot_only, source_filter, 
                    ts_correct=ts_correct, io_filter=io_filter, web10g_version=web10g_version)
            execute(extract_throughput, test_id, out_dir, replot_only, source_filter,
                    link_len=link_len, ts_correct=ts_correct)


# Do all analysis
# Parameters:
#       exp_list: list of all test IDs
#       test_id: test ID prefix of experiment to analyse
#	out_dir: output directory for result files
#       replot_only: don't extract data again, just redo the plot
#       source_filter: filter on specific sources
#	min_values: ignore flows with less output values 
#       omit_const: '0' don't omit anything, ]
#                   '1' omit any series that are 100% constant
#                   (e.g. because there was no data flow)
#       smoothed: '0' plot non-smooth RTT (enhanced RTT in case of FreeBSD),
#                 '1' plot smoothed RTT estimates (non enhanced RTT in case of FreeBSD)
# 	resume_id: resume analysis with this test_id (ignore all test_ids before this),
#                  only effective if test_id is not specified
#       lnames: semicolon-separated list of legend names
#       link_len: '0' throughput based on IP length (default),
#                 '1' throughput based on link-layer length
#	stime: start time of plot window in seconds
#              (by default 0.0 = start of experiment)
#	etime: end time of plot window in seconds
#              (by default 0.0 = end of experiment)
#       out_name: name prefix
#       pdf_dir: output directory for pdf files (graphs), if not specified it is
#                the same as out_dir
#       ts_correct: '0' use timestamps as they are (default)
#                   '1' correct timestamps based on clock offsets estimated
#                       from broadcast pings
#       io_filter:  'i' only use statistics from incoming packets
#                   'o' only use statistics from outgoing packets
#                   'io' use statistics from incooming and outgoing packets
#                   (only effective for SIFTR files)
#       web10g_version: web10g version string (default is 2.0.9)
#       plot_params: parameters passed to plot function via environment variables
#       plot_script: specify the script used for plotting, must specify full path
@task
def analyse_all(exp_list='experiments_completed.txt', test_id='', out_dir='',
                replot_only='0', source_filter='', min_values='3', omit_const='0',
                smoothed='1', resume_id='', lnames='', link_len='0', stime='0.0',
                etime='0.0', out_name='', pdf_dir='', ts_correct='0',
                io_filter='o', web10g_version='2.0.9', plot_params='', plot_script=''):
    "Compute SPP RTT, TCP RTT, CWND and throughput statistics"

    experiments = get_experiment_list(exp_list, test_id)

    do_analyse = True
    if resume_id != '':
        puts('Resuming analysis with test_id %s' % resume_id)
        do_analyse = False

    for test_id in experiments:

        if test_id == resume_id:
            do_analyse = True

        if do_analyse:
            execute(analyse_rtt, test_id, out_dir, replot_only, source_filter,
                    min_values, omit_const=omit_const, lnames=lnames, stime=stime,
                    etime=etime, out_name=out_name, pdf_dir=pdf_dir,
                    ts_correct=ts_correct, plot_params=plot_params, plot_script=plot_script)
            execute(analyse_cwnd, test_id, out_dir, replot_only, source_filter, min_values,
                    omit_const=omit_const, lnames=lnames, stime=stime, etime=etime,
                    out_name=out_name, pdf_dir=pdf_dir, ts_correct=ts_correct,
                    io_filter=io_filter, plot_params=plot_params, plot_script=plot_script)
            execute(analyse_tcp_rtt, test_id, out_dir, replot_only, source_filter, min_values,
                    omit_const=omit_const, smoothed=smoothed, lnames=lnames,
                    stime=stime, etime=etime, out_name=out_name, pdf_dir=pdf_dir,
                    ts_correct=ts_correct, io_filter=io_filter, web10g_version=web10g_version,
                    plot_params=plot_params, plot_script=plot_script)
            execute(analyse_throughput, test_id, out_dir, replot_only, source_filter,
                    min_values, omit_const=omit_const, lnames=lnames, link_len=link_len,
                    stime=stime, etime=etime, out_name=out_name, pdf_dir=pdf_dir,
                    ts_correct=ts_correct, plot_params=plot_params, plot_script=plot_script)


# read experiment IDs
# Parameters:
#       exp_list: list of all test IDs (allows to filter out certain experiments,
#                 i.e. specific value comnbinations)
def read_experiment_ids(exp_list):
    # read test ids
    try:
        with open(exp_list) as f:
            # read lines without newlines
            experiments = f.read().splitlines()
    except IOError:
        abort('Cannot open file %s' % exp_list)

    if len(experiments) < 1:
        abort('No experiment IDs specified')

    return experiments


# get path from first experiment in list
# Parameters:
#       experiments: list of experiment ids
def get_first_experiment_path(experiments):
    # get path based on first experiment id 
    dir_name = ''
    files = _list(
                  local(
                  'find -L . -name "%s*" | LC_ALL=C sort' %
                  experiments[0], capture=True))
    if len(files) > 0:
        dir_name = os.path.dirname(files[0])
    else:
        abort('Cannot find experiment %s' % experiments[0])

    return dir_name


# build match string to match test IDs based on specified variables, and s second
# string to extract the test id prefix
# Parameters:
#       variables: semicolon-separated list of <var>=<value> where <value> means
#                  we only want experiments where <var> had the specific value
def build_match_strings(variables):

    match_str = ''
    var_dict = {}

    if variables != '':
        for var in variables.split(';'):
            name, val = var.split('=')
            var_dict[name] = val

    for vary in config.TPCONF_vary_parameters:
        # get var name used in file
        names = config.TPCONF_parameter_list[vary][1]

        for name in names:
            val = var_dict.get(name, '')
            if val == '':
                # we specify only fixed so this is a wildcard then
                match_str += '(' + name + '_.*)' + '_'
            else:
                match_str += '(' + name + '_' + val + ')' + '_'

    match_str = match_str[:-1]  # chomp of last underscore
    match_str2 = '(.*)_' + match_str
    # print(match_str)
    # print(match_str2)

    return (match_str, match_str2)


# filter out experiments based on the variables and also return 
# test id prefix and list of labels to plot underneath x-axis
# Parameters:
#	experiments: experiment list
def filter_experiments(experiments, match_str, match_str2):
    fil_experiments = []
    test_id_pfx = ''
    xlabs = []

    for experiment in experiments:
        # print(experiment)
        res = re.search(match_str, experiment)
        if res:
            fil_experiments.append(experiment)
            xlabs.append('\n'.join(map(str, res.groups())))
            if test_id_pfx == '':
                res = re.search(match_str2, experiment)
                if res:
                    test_id_pfx = res.group(1)

    # print(fil_experiments)
    # print(xlabs)

    return (fil_experiments, test_id_pfx, xlabs)


# get parameters based on metric
def get_metric_params(metric='', smoothed='0', ts_correct='0', stat_index='0', dupacks='0',
                     cum_ackseq='1'):

    diff = '0'
    if metric == 'throughput':
        ext = '.psiz'
        ylab = 'Throughput (kbps)'
        yindex = 2
        yscaler = 0.008
        sep = ' '
        aggr = '1'
    elif metric == 'spprtt':
        ext = '.rtts'
        ylab = 'SPP RTT (ms)'
        yindex = 2
        yscaler = 1000.0
        sep = ' '
        aggr = '0'
    elif metric == 'tcprtt':
        ext = '.tcp_rtt'
        ylab = 'TCP RTT (ms)'
        if smoothed == '1':
            yindex = 2
        else:
            yindex = 3
        yscaler = 1.0
        sep = ','
        aggr = '0'
    elif metric == 'cwnd':
        ext = '.cwnd'
        ylab = 'CWND'
        yindex = 2
        yscaler = 1.0
        sep = ','
        aggr = '0'
    elif metric == 'tcpstat':
        ext = '.tcpstat_' + stat_index 
        ylab = 'TCP statistic ' + stat_index 
        yindex = 2
        yscaler = 1.0
        sep = ','
        aggr = '0'
    elif metric == 'ackseq':
        ext = '.acks.0'
        if dupacks == '0' :
            if cum_ackseq == '1':
                ylab = 'Bytes acknowledged (Kbytes)'
            else:
                ylab = 'Bytes acknowledged (Kbytes/s)'
            yindex = 2
            yscaler =  (1.0 / 1024.0)
        else :
            if cum_ackseq == '1':
                ylab = 'Cummulative dupACKs'
            else:
                ylab = 'dupACKs per second'
            yindex = 3
            yscaler = 1.0
        sep = ' '
        if cum_ackseq == '1':
            aggr = '0'
            diff = '0'
        else:
            aggr = '1'
            diff = '1'
    # elif add more
    else:
        return None

    if ts_correct == '1':
        ext += clockoffset.DATA_CORRECTED_FILE_EXT

    return (ext, ylab, yindex, yscaler, sep, aggr, diff)


def get_extract_function(metric='', link_len='0', stat_index='0'):

    # define a map of metrics and corresponding extract functions
    extract_functions = {
        'throughput' : _extract_throughput,
        'spprtt'     : _extract_rtt,
        'tcprtt'     : _extract_tcp_rtt,
        'cwnd'       : _extract_cwnd,
        'tcpstat'    : _extract_tcp_stat,
        'ackseq'     : _extract_ackseq,
    }

    # additonal arguments for extract functions
    extract_kwargs = {
        'throughput' : { 'link_len' : link_len },
        'spprtt'     : { },
        'tcprtt'     : { },
        'cwnd'       : { },
        'tcpstat'    : { 'siftr_index'  : stat_index, 
                         'web10g_index' : stat_index },
        'ackseq'     : { 'burst_sep'    : 0.0 }, 
    }

    return (extract_functions[metric], extract_kwargs[metric])


# Function that plots mean, median, boxplot of throughput,
# RTT for different parameter combinations
# XXX currently can't reorder the parameters, order is the one given by
#     config.py (and in the file names)
# Parameters:
#	exp_list: list of all test IDs (allows to filter out certain experiments,
#                 i.e. specific value comnbinations)
#	res_dir: directory with result files from analyse_all
#       out_dir: output directory for result files
#       source_filter: filter on specific sources
#                      (number of filters must be smaller equal to 12)
#       min_values: ignore flows with less output values / packets
#       omit_const: '0' don't omit anything,
#                   '1' omit any series that are 100% constant
#                       (e.g. because there was no data flow)
#	metric: 'throughput', 'spprtt' (spp rtt), 'tcprtt' (unsmoothed tcp rtt), 'cwnd',
#               'tcpstat', with 'tcpstat' must specify siftr_index or web10g_index 
#	ptype: plot type: 'mean', 'median', 'box' (boxplot)
#	variables: semicolon-separated list of <var>=<value> where <value> means
#                  we only want experiments where <var> had the specific value
#	out_name: file name prefix
#       ymin: minimum value on y-axis
#       ymax: maximum value on y-axis
#       lnames: semicolon-separated list of legend names
#	group_by_prefix: group by prefix instead of group by traffic flow
#	omit_const_xlab_vars: '0' show all variables in the x-axis labels,
#                             '1' omit constant variables in the x-axis labels
#       pdf_dir: output directory for pdf files (graphs), if not specified it
#                is the same as out_dir
#       stime: start time of time window to analyse
#              (by default 0.0 = start of experiment)
#       etime: end time of time window to analyse (by default 0.0 = end of
#              experiment)
#       ts_correct: '0' use timestamps as they are (default)
#                   '1' correct timestamps based on clock offsets estimated
#                       from broadcast pings
#       smoothed: '0' plot non-smooth RTT (enhanced RTT in case of FreeBSD),
#                 '1' plot smoothed RTT estimates (non enhanced RTT in case of FreeBSD)
#       link_len: '0' throughput based on IP length (default),
#                 '1' throughput based on link-layer length
#       replot_only:  '0' extract data
#                     '1' don't extract data again, just redo the plot
#       plot_params: parameters passed to plot function via environment variables
#       plot_script: specify the script used for plotting, must specify full path
#                    (default is config.TPCONF_script_path/plot_cmp_experiments.R)
#       stat_index: an integer number of the column in siftr/web10g log files
#                   need when metric is 'tcpstat'
#       dupacks: '0' to plot ACKed bytes vs time
#                '1' to plot dupACKs vs time
#       cum_ackseq: '0' average per time window data 
#                   '1' cummulative counter data
@task
def analyse_cmpexp(exp_list='experiments_completed.txt', res_dir='', out_dir='',
                   source_filter='', min_values='3', omit_const='0', metric='throughput',
                   ptype='box', variables='', out_name='', ymin='0', ymax='0', lnames='',
                   group_by_prefix='0', omit_const_xlab_vars='0', replot_only='0',
                   pdf_dir='', stime='0.0', etime='0.0', ts_correct='0', smoothed='1',
                   link_len='0', plot_params='', plot_script='', stat_index='',
                   dupacks='0', cum_ackseq='1'):
    "Compare metrics for different experiments"

    if ptype != 'box' and ptype != 'mean' and ptype != 'median':
        abort('ptype must be either box, mean or median')

    check = get_metric_params(metric, smoothed, ts_correct)
    if check == None:
        abort('Unknown metric %s specified' % metric)

    if source_filter == '':
        abort('Must specify at least one source filter')

    if len(source_filter.split(';')) > 12:
        abort('Cannot have more than 12 filters')

    # XXX more param checking

    # make sure res_dir has valid form (out_dir is handled by extract methods)
    res_dir = valid_dir(res_dir)

    if source_filter != '':
        _build_source_filter(source_filter)

    # read test ids
    experiments = read_experiment_ids(exp_list)

    # get path based on first experiment id 
    dir_name = get_first_experiment_path(experiments)

    # if we haven' got the extracted data run extract method(s) first
    if res_dir == '':
        for experiment in experiments:
            
            (ex_function, kwargs) = get_extract_function(metric, link_len,
                                    stat_index)

            ex_function(
                test_id=experiment, out_dir=out_dir,  
                source_filter=source_filter, 
                replot_only=replot_only, 
                ts_correct=ts_correct,
                **kwargs)
        
        res_dir = dir_name + '/' + out_dir 
    else:
        res_dir = dir_name + '/' + res_dir

    res_dir = valid_dir(res_dir)

    if pdf_dir == '':
        pdf_dir = res_dir
    else:
        pdf_dir = valid_dir(pdf_dir)
        pdf_dir = dir_name + '/' + pdf_dir
        # if pdf_dir specified create if it doesn't exist
        mkdir_p(pdf_dir)

    #
    # build match string from variables
    #

    (match_str, match_str2) = build_match_strings(variables)

    #
    # filter out the experiments to plot, generate x-axis labels, get test id prefix
    #

    (fil_experiments, 
     test_id_pfx,
     xlabs) = filter_experiments(experiments, match_str, match_str2)

    #
    # get out data files based on filtered experiment list and source_filter
    #

    (ext, 
     ylab, 
     yindex, 
     yscaler, 
     sep, 
     aggr,
     diff) = get_metric_params(metric, smoothed, ts_correct, stat_index, dupacks,
                              cum_ackseq)

    leg_names = source_filter.split(';')

    file_names = []
    for experiment in fil_experiments:
        out_files = {}

        files = _list(
            local(
                'find -L %s -name "%s*%s" | LC_ALL=C sort' %
                (res_dir, experiment, ext), capture=True))

        # print(files)
        match_str = '.*_([0-9\.]*_[0-9]*_[0-9\.]*_[0-9]*)[0-9a-z_.]*' + ext
        for f in files:
            # print(f)
            res = re.search(match_str, f)
            if res and _in_source_filter(res.group(1)):
                # only add file if enough data points
                rows = int(
                    local('wc -l %s | awk \'{ print $1 }\'' %
                          f, capture=True))
                if rows > int(min_values):
                    out_files[res.group(1)] = f

        if len(out_files) < len(leg_names):
            abort(
                'No data files for some of the source filters for experiment %s' %
                experiment)

        sorted_files = sort_by_flowkeys(out_files)

        for name, file_name in sorted_files:
            file_names.append(file_name)

    if group_by_prefix == '1':
        # group by test prefix (and flow)

        # first, get all test id prefixes
        test_id_pfxs = {}
        for experiment in fil_experiments:
            res = re.search(match_str2, experiment)
            if res:
                test_id_pfxs[res.group(1)] = 1

        # second, sort files so that same parameter combinations foor different
        # prefixes are together
        # if we have multiple prefixes, create legend entry for each
        # prefix+flow combination
        _file_names = [''] * len(file_names)
        _leg_names = []
        pfx_cnt = len(test_id_pfxs)
        i = 0
        j = -1
        last_pfx = ''
        for name in file_names:
            for p in test_id_pfxs:
                if name.find(p) > -1:
                    curr_pfx = p
                    break

            if curr_pfx != last_pfx:
                i = 0
                j += 1
                for l in leg_names:
                    _leg_names.append(curr_pfx + '-' + l)

            _file_names[i * pfx_cnt + j] = name

            i += 1
            last_pfx = curr_pfx

        file_names = _file_names
        leg_names = _leg_names

        # remove duplicates in the x-axis labels
        xlabs = xlabs[0:len(file_names) / pfx_cnt]

    if lnames != '':
        lnames_arr = lnames.split(';')
        if len(lnames_arr) != len(leg_names):
            abort(
                'Number of legend names must be qual to the number of source filters')
        leg_names = lnames_arr

    # filter out unchanged variables in the x labels
    if omit_const_xlab_vars == '1':

        xlabs_arrs = {}
        xlabs_changed = {}

        for i in range(len(xlabs)):
            xlabs_arrs[i] = xlabs[i].split('\n')

        for i in range(len(xlabs_arrs[0])):
            changed = False
            xlab_var = xlabs_arrs[0][i]
            for j in range(1, len(xlabs)):
                if xlabs_arrs[j][i] != xlab_var:
                    changed = True
                    break

            xlabs_changed[i] = changed

        for i in range(len(xlabs)):
            tmp = []
            for j in range(len(xlabs_arrs[i])):
                if xlabs_changed[j]:
                    tmp.append(xlabs_arrs[i][j].replace('_', ' ', 1))

            xlabs[i] = '\n'.join(tmp)

    print(leg_names)
    print(file_names)

    #
    # pass the data files and auxilary info to plot function
    #

    if out_name != '':
        oprefix = out_name + '_' + test_id_pfx + '_' + metric + '_' + ptype
    else:
        oprefix = test_id_pfx + '_' + metric + '_' + ptype
    title = oprefix

    if plot_script == '':
        plot_script = '%s/plot_cmp_experiments.R' % config.TPCONF_script_path

    # interface between this code and the plot function are environment variables
    # the following variables are passed to plot function:
    # TITLE:  character string that is plotted over the graph
    # FNAMES: comma-separated list of file names (each file contains one date series,
    #         e.g. data for one flow). The format of each file is CSV-style, but the
    #         separator does not have to be a comma (can be set with SEP). The first
    #         column contains the timestamps. The second, third etc. columns contain
    #         data, but only one of these columns will be plotted (set with YINDEX). 
    # LNAMES: comma-separated list of legend names. this list has the same length
    #         as FNAMES and each entry corresponds to data in file name with the
    #         same index in FNAMES
    # XLABS:  comma-separated list of labels for the x-axis ticks, one for each parameter
    #         combination that is plotted 
    # YLAB:   y-axis label character string
    # YINDEX: index of data column in file to plot on y-axis (file can have more than
    #         one data column)
    # YSCALER: factor which is multiplied with each data value before plotting
    # SEP:    column separator used in data file
    # OTYPE:  type of output graph (default is 'pdf')
    # OPREFIX: the prefix (first part) of the graph file name
    # ODIR:   directory where output files, e.g. pdfs are placed
    # AGGR:   set to '1' means data is aggregated over time intervals, more specifically
    #         the data is summed over the time intervals (used to determine throughput
    #         over time windows based on packet lengths)  
    #         set to '0' means plot data as is 
    # OMIT_CONST: '0' don't omit anything,
    #             '1' omit any data series from plot that are 100% constant 
    # PTYPE:  the type of plot identified by name, it can be 'box', 'mean' or 'median' 
    #         for the default R script
    # YMIN:   minimum value on y-axis (for zooming in), default is 0 
    # YMAX:   maximum value on y-axis (for zooming in), default is 0 meaning the 
    #         maximum value is determined from the data
    # STIME:  start time on x-axis (for zooming in), default is 0.0 meaning the start 
    #         of an experiment
    # ETIME:  end time on x-axis (for zooming in), default is 0.0 meaning the end of an
    #         experiment a determined from the data

    local('which R')
    local('TITLE="%s" FNAMES="%s" LNAMES="%s" XLABS="%s" YLAB="%s" YINDEX="%d" '
          'YSCALER="%f" SEP="%s" OTYPE="%s" OPREFIX="%s" ODIR="%s" AGGR="%s" DIFF="%s" '
          'OMIT_CONST="%s" PTYPE="%s" YMIN="%s" YMAX="%s" STIME="%s" ETIME="%s" %s '
          'R CMD BATCH --vanilla %s %s%s_plot_cmp_experiments.Rout' %
          (title, ','.join(file_names), ','.join(leg_names), ','.join(xlabs), ylab,
           yindex, yscaler, sep, 'pdf', oprefix, pdf_dir, aggr, diff,
           omit_const, ptype, ymin, ymax, stime, etime, plot_params,
           plot_script, pdf_dir, oprefix))

    if config.TPCONF_debug_level == 0:
        local('rm -f %s%s_plot_cmp_experiments.Rout' % (pdf_dir, oprefix)) 

    # done
    puts('\n[MAIN] COMPLETED analyse_cmpexp %s \n' % test_id_pfx)


# Extract incast 
# The extracted files have an extension of .rtimes. The format is CSV with the
# columns:
# 1. Timestamp RTT measured (seconds.microseconds)
# 2. Response time (seconds) 
# Parameters:
#       test_id: test ID prefix of experiment to analyse
#       out_dir: output directory for results
#       replot_only: don't extract data again that is already extracted
#       source_filter: filter on specific sources
#       ts_correct: '0' use timestamps as they are (default)
#                   '1' correct timestamps based on clock offsets estimated
#                       from broadcast pings
def _extract_incast(test_id='', out_dir='', replot_only='0', source_filter='',
                    ts_correct='0'):
    "Extract incast response times for generated traffic flows"

    ifile_ext = 'httperf_incast.log.gz'
    ofile_ext = '.rtimes'

    out_files = {}
    out_groups = {}

    test_id_arr = test_id.split(';')
    if len(test_id_arr) == 0 or test_id_arr[0] == '':
        abort('Must specify test_id parameter')

    if source_filter != '':
        _build_source_filter(source_filter)

    # make sure specified dir has valid form
    out_dir = valid_dir(out_dir)

    group = 1
    for test_id in test_id_arr:

        # first find httperf files (ignore router and ctl interface tcpdumps)
        (test_id_arr, log_files) = get_testid_file_list('', test_id,
                                   ifile_ext, '')

        for log_file in log_files:
            # get input directory name and create result directory if necessary
            dir_name = os.path.dirname(log_file)
            mkdir_p(dir_name + '/' + out_dir)

            flows = []

            # get src ip from file name
            src = local(
                'echo %s | sed "s/.*_\([a-z0-9\.]*\)_[0-9]*_httperf_incast.log.gz/\\1/"' %
                log_file,
                capture=True)
            # don't know source port, use it to differentiate experiments
            # must use high port otherwise the later sorting will fail
            src_port = str(50000 + group)

            # get destination ip and port from log file
            responders = _list(
                local(
                    'zcat %s | grep "hash_enter" | grep -v localhost | cut -d" " -f 2,3' %
                    log_file, capture=True))

            cnt = 0
            for _resp in responders:
                dst = _resp.split(' ')[0]
                dst_port = _resp.split(' ')[1]

                # get external and internal addresses
                src, src_internal = get_address_pair(src, do_abort='0')
                dst, dst_internal = get_address_pair(dst, do_abort='0')

                #print(src, src_port, dst, dst_port)

                if src == '' or dst == '':
                    continue

                # flow name
                name = src_internal + '_' + src_port + \
                    '_' + dst_internal + '_' + dst_port

                if not _in_source_filter(name):
                    continue

                out_fname = dir_name + '/' + out_dir + \
                    test_id + '_' + name + ofile_ext 

                out_files[name] = out_fname
                out_groups[out_fname] = group

                if replot_only == '0' or not os.path.isfile(out_fname) :
                    f = open(out_fname, 'w')

                    responses = _list(local('zcat %s | grep "incast_files"' %
                        log_file, capture=True))

                    time = 0.0
                    for response in responses:
                        responder_id = int(response.split()[2])
                        response_time = response.split()[9]
                        interval = float(response.split()[11])
                        timed_out = response.split()[12]

                        if responder_id == cnt:
                            if timed_out == 'no':
                                f.write('%f %s\n' % (time, response_time))
                            else:
                                f.write('%f NA\n' % time)

                            time += interval

                    f.close()

                cnt += 1

        group += 1

    return (test_id_arr, out_files, out_groups)


# Extract incast 
# SEE _extract_incast
@task
def extract_incast(test_id='', out_dir='', replot_only='0', source_filter='',
                   ts_correct='0'):
    "Extract incast response times for generated traffic flows"

    _extract_incast(test_id, out_dir, replot_only, source_filter, ts_correct)

    # done
    puts('\n[MAIN] COMPLETED extracting incast response times %s\n' % test_id)


# Plot incast response times 
# Parameters:
#       test_id: test ID prefix of experiment to analyse
#       out_dir: output directory for results
#       replot_only: don't extract data again, just redo the plot
#       source_filter: filter on specific sources
#       omit_const: '0' don't omit anything,
#                   '1' omit any series that are 100% constant
#                       (e.g. because there was no data flow)
#       ymin: minimum value on y-axis
#       ymax: maximum value on y-axis
#       lnames: semicolon-separated list of legend names
#       stime: start time of plot window in seconds
#              (by default 0.0 = start of experiment)
#       etime: end time of plot window in seconds (by default 0.0 = end of experiment)
#       out_name: name prefix
#       pdf_dir: output directory for pdf files (graphs), if not specified it is
#                the same as out_dir
#       ts_correct: '0' use timestamps as they are (default)
#                   '1' correct timestamps based on clock offsets estimated
#                       from broadcast pings
#       slowest_only: '0' plot response times for individual responders 
#                     '1' plot slowest response time across all responders
#       boxplot: '0' normal time series (default)
#                '1' boxplot for each point in time
#       plot_params: set env parameters for plotting
#       plot_script: specify the script used for plotting, must specify full path
@task
def analyse_incast(test_id='', out_dir='', replot_only='0', source_filter='',
                       min_values='3', omit_const='0', ymin='0', ymax='0', lnames='',
                       stime='0.0', etime='0.0', out_name='',
                       pdf_dir='', ts_correct='0', slowest_only='0',
                       boxplot='0', plot_params='', plot_script=''):
    "Plot incast response times for generated traffic flows"

    ofile_ext = '.rtimes'
    pdf_name_part = '_restime'
    sort_flowkey = '1'

    (test_id_arr,
     out_files,
     out_groups) = _extract_incast(test_id, out_dir, replot_only, source_filter, 
                                   ts_correct) 

    if slowest_only == '1':
        # get list of slowest response times over time
        slowest = {} 

        for group in out_groups.values():
            for name in out_files.keys():
                if out_groups[out_files[name]] == group:
                    # get directory of data file
                    dir_name = os.path.dirname(out_files[name])

                    # read data file and adjust slowest
                    f = open(out_files[name], 'r')
                    for line in f.readlines():
                        _time = float(line.split()[0])
                        _res_time = float(line.split()[1])
                        if _time not in slowest:
                            slowest[_time] = _res_time
                        else:
                            if _res_time > slowest[_time]:
                                slowest[_time] = _res_time 
                    f.close()

	            # delete entries for single responders
                    del out_groups[out_files[name]]
                    del out_files[name]

            name = 'Experiment ' + str(group) + ' slowest'
            test_id = test_id_arr[group - 1]
            fname = dir_name + '/' + \
                    test_id + '_' + 'exp_' + str(group) + \
                    '_slowest' + ofile_ext 

            # write file for slowest response times
            f = open(fname, 'w')
            for _time in sorted(slowest.keys()):
                f.write('%f %s\n' % (_time, slowest[_time]))
            f.close()

            out_files[name] = fname
            out_groups[fname] = group

            pdf_name_part = '_restime_slowest'
            sort_flowkey = '0'

    out_name = get_out_name(test_id_arr, out_name)
    plot_time_series(out_name, out_files, 'Response time (s)', 2, 1.0, 'pdf',
                     out_name + pdf_name_part, pdf_dir=pdf_dir,
                     ymin=float(ymin), ymax=float(ymax),
                     lnames=lnames, stime=stime, etime=etime, 
                     groups=out_groups, sort_flowkey=sort_flowkey, 
                     boxplot=boxplot, plot_params=plot_params, plot_script=plot_script) 

    # done
    puts('\n[MAIN] COMPLETED plotting incast response times %s\n' % test_id)



# extract_dupACKs_bursts
#
# Parameters:
#   acks_file   Full path to a specific .acks file which is to be parsed
#               for dupACKs and (optionally) extract sequence of ACK bursts
#   burst_sep   = 0, Just calculate running total of dupACKs and create acks_file+".0" output file
#               < 0, extract bursts into acks_file+".N" outputfiles (for burst N),
#                   where burst starts @ t=0 and then burst_sep seconds after start of previous burst
#               > 0, extract bursts into acks_file+".N" outputfiles (for burst N)
#                   where burst starts @ t=0 and then burst_sep seconds after end of previous burst
#   time_offset = 0, adjust the timestamps of each burst to start at zero (0) (to overlap bursts on graph)
#               = 1, leave original unix timestamps for each burst
#
# First task is to calculate the number of duplicate ACKs. Define
# them as ACKs whose sequence number is unchanged from the immediately
# preceding ACK.
#
# Generate .acks.0 file with this format:
#
#   <time>  <ack_seq_no>  <cumulative_dupACK_count>
#
#
#If burst_sep != 0 then we try to further subdivide into "bursts"
#
# Output is multiple .acks.N files, containing only the lines for
# burst N:
#
#   <time>  <ack_seq_no>  <cumulative_dupACK_count>
#
# The <ack_seq_no> starts at 0 for burst 1 (since the first
# ACK is assuemd to be the end of the handshake rather than ACK'ing
# a Data packet), but starts at a small non-zero value for the first
# ACK of bursts 2..N.
#
# The <cumulative_dupACK_count> restarts at 0 for each burst.
#
# Return:
#   Returns a vector of one or more filenames (corresponding to each new file created)
#
# NOTE: This function relies on there being no re-ordering of ACK packets on
#       the return path.
#

def extract_dupACKs_bursts(acks_file='', burst_sep=0, time_offset=0):

    # New filenames (source file + ".0" or ".1,.2,....N" for bursts)
    new_fnames = [];

    # Internal variables
    burstN = 1
    firstTS = -1

    try:
        _acks = []
        # First read the entire contents of a .acks file
        with open(acks_file) as f:
            _acks = f.readlines()
            #print _acks

            if burst_sep != 0 :
                # Create the first .acks.N output file
                out_f = open(acks_file+"."+"1","w")
                new_fnames.append(acks_file+"."+"1")
            else:
                out_f = open(acks_file+"."+"0","w")
                new_fnames.append(acks_file+"."+"0")

            # Now walk through every line of the .acks file
            for oneline in _acks:
                # ackdetails[0] is the timestamp, ackdetails[1] is the seq number
                ackdetails = oneline.split()

                if firstTS == -1 :
                    # This is first time through the loop, so set some baseline
                    # values for later offsets
                    firstTS = ackdetails[0]
                    prev_ACKTS = firstTS
                    firstBytes = 0

                # Is this ACK a dupACK ?
                if int(ackdetails[1]) == 0 :
                    # Only the first ACK line has zero seq number. Special case, reset dupACKs count
                    dupACKs = 0
                    prev_seqno = ackdetails[1]
                else:
                    # Define dupACK as an ACK with unchanged seq number wrt preceding ACK
                    if (int(ackdetails[1]) - int(prev_seqno)) == 0 :
                        dupACKs += 1

                # If burst_sep == 0 the only thing we're calculating is a
                # cumulative running total of dupACKs, so we only do burst
                # identification if burst_sep != 0

                if burst_sep != 0 :

                    if burst_sep < 0 :
                        # ack_gap is time since first ACK of this burst
                        # (i.e. relative to firstTS)
                        ack_gap = float(ackdetails[0]) - float(firstTS)
                    else:
                        # ack_gap is time since previous ACK in this burst
                        # (i.e. relative to prev_ACKTS)
                        ack_gap = float(ackdetails[0]) - float(prev_ACKTS)

                    # New burst begins when time between this ACK and previous
                    # exceeds abs(burst_sep)
                    if (ack_gap >= abs(burst_sep)) :
                        # We've found the first ACK of the _next_ burst

                        # Close previous burst output file
                        out_f.close()

                        # Move on to the next burst
                        burstN += 1

                        print ("Burst: %3i, ends at %f sec, data: %i bytes, gap: %3.6f sec, dupACKs: %i" %
                        ( (burstN-1),  float(prev_ACKTS), int(prev_seqno) - int(firstBytes), ack_gap, dupACKs ) )

                        # Reset firstTS to the beginning (first timestamp) of this new burst
                        firstTS = ackdetails[0]

                        # The sequence number of first ACK of bursts 2...N must be considered
                        # relative to LAST seq number of PREVIOUS burst in order to calculate
                        # how many bytes were fully sent in bursts 2...N.
                        firstBytes = prev_seqno

                        # Reset the dupACKs counter
                        dupACKs = 0

                        # Create the next .acks.N output file
                        out_f = open(acks_file+"."+str(burstN),"w")
                        new_fnames.append(acks_file+"."+str(burstN))


                # How many bytes were ACK'ed since beginning? (Of entire file or of burst N)
                # This must be calculated _after_ firstBytes is potentially reset on
                # the boundary between bursts.
                bytes_gap = int(ackdetails[1]) - int(firstBytes)

                #print "Burst: ", burstN, "  Time ", ackdetails[0] ," Bytes ", bytes_gap, "   DupACKS ", dupACKs

                # Write to burst-specific output file
                # <time>  <ACK seq number>  <dupACK count>
                if time_offset == 0 :
                    out_f.write(str(float(ackdetails[0]) - float(firstTS))+" "+str(bytes_gap)+" "+str(dupACKs)+"\n")
                else:
                    out_f.write(ackdetails[0]+" "+str(bytes_gap)+" "+str(dupACKs)+"\n")

                # Store the seq number for next time around the loop
                prev_seqno = ackdetails[1]
                prev_ACKTS = ackdetails[0]

            # Close the last output file
            out_f.close()

    except IOError:
        print('extract_dupACKs_bursts(): File access problem while working on %s' % acks_file)

    return new_fnames



# Extract cumulative bytes ACKnowledged and cumulative dupACKs
# XXX move sburst and eburst to the plotting task and here extract all?
#
# Parameters:
#   test_id: semicolon-separated list of test ID prefixes of experiments to analyse
#   out_dir: output directory for results
#   replot_only: '1' don't extract raw ACK vs time data per test_ID if already done,
#           but still re-calculate dupACKs and bursts (if any) before plotting results
#   source_filter: filter on specific flows to process
#   ts_correct: '0' use timestamps as they are (default)
#               '1' correct timestamps based on clock offsets estimated
#                       from broadcast pings
#   burst_sep: '0' plot seq numbers as they come, relative to 1st seq number
#               > '0' plot seq numbers relative to 1st seq number after gaps
#               of more than burst_sep milliseconds (e.g. incast query/response bursts)
#               < 0,  plot seq numbers relative to 1st seq number after each abs(burst_sep)
#               seconds since the first burst @ t = 0 (e.g. incast query/response bursts)
#   sburst: Start plotting with burst N (bursts are numbered from 1)
#   eburst: End plotting with burst N (bursts are numbered from 1)
#
# Intermediate files end in ".acks", ".acks.N", ".acks.tscorr" or ".acks.tscorr.N"
#
def _extract_ackseq(test_id='', out_dir='', replot_only='0', source_filter='',
                    ts_correct='0', burst_sep='0.0',
                    sburst='1', eburst='0'):
    "Extract cumulative bytes ACKnowledged vs time / extract incast bursts"

    ifile_ext = '.dmp.gz'
    ofile_ext = '.acks'

    sburst = int(sburst)
    eburst = int(eburst)
    burst_sep = float(burst_sep)

    out_files = {}
    out_groups = {}

    test_id_arr = test_id.split(';')
    if len(test_id_arr) == 0 or test_id_arr[0] == '':
        abort('Must specify test_id parameter')

    if source_filter != '':
        _build_source_filter(source_filter)

    if len(out_dir) > 0 and out_dir[-1] != '/':
        out_dir += '/'

    group = 1
    for test_id in test_id_arr:

        # first process tcpdump files (ignore router and ctl interface tcpdumps)
        tcpdump_files = _list(
            local(
                'find -L . -name "%s*.dmp.gz" -print | grep -v "router.dmp.gz" | '
                'grep -v "ctl.dmp.gz" | '
                'sed -e "s/\.\///"' %
                test_id,
                capture=True))

        for tcpdump_file in tcpdump_files:
            # get input directory name and create result directory if necessary
            dir_name = os.path.dirname(tcpdump_file)
            local('mkdir -p %s' % dir_name + '/' + out_dir)

            # unique flows
            flows = _list(local('zcat %s | tcpdump -nr - "tcp" | '
                                'awk \'{ if ( $2 == "IP" ) { print $3 " " $5 " tcp" } }\' | '
                                'sed "s/://" | '
                                'sed "s/\.\([0-9]*\) /,\\1 /g" | sed "s/ /,/g" | '
                                'LC_ALL=C sort -u' %
                                tcpdump_file, capture=True))

            # since client sends first packet to server, client-to-server flows
            # will always be first

            for flow in flows:

                src, src_port, dst, dst_port, proto = flow.split(',')

                # get external and internal addresses
                src, src_internal = get_address_pair(src, do_abort='0')
                dst, dst_internal = get_address_pair(dst, do_abort='0')

                if src == '' or dst == '':
                    continue

                # flow name
                name = src_internal + '_' + src_port + \
                    '_' + dst_internal + '_' + dst_port
                rev_name = dst_internal + '_' + dst_port + \
                    '_' + src_internal + '_' + src_port

                # the two dump files
                dump1 = dir_name + '/' + test_id + '_' + src + ifile_ext 
                dump2 = dir_name + '/' + test_id + '_' + dst + ifile_ext 

                # tcpdump filters and output file names
                # 'tcp[tcpflags] == tcp-ack' rule to extract only ACK packets (eliminate SYN and FIN, even if ACK also set)
                filter1 = 'src host ' + src_internal + ' && src port ' + src_port + \
                    ' && dst host ' + dst_internal + ' && dst port ' + dst_port + \
                    ' && tcp[tcpflags] == tcp-ack'
                filter2 = 'src host ' + dst_internal + ' && src port ' + dst_port + \
                    ' && dst host ' + src_internal + ' && dst port ' + src_port + \
                    ' && tcp[tcpflags] == tcp-ack'

                out_acks1 = dir_name + '/' + out_dir + \
                    test_id + '_' + name + ofile_ext 
                out_acks2 = dir_name + '/' + out_dir + \
                    test_id + '_' + rev_name + ofile_ext 

                if replot_only == '0' or not ( os.path.isfile(out_acks1) and \
                                               os.path.isfile(out_acks2) ):

                    # make sure for each flow we get the ACKs captured
                    # at the _receiver_, hence we use filter1 with dump2 ...
                    # Use "-S" option to tcpdump so ACK sequence numbers are always absolute

                    # Grab first ACK sequence numbers for later use as a baseline

                    baseACK1 = local(
                        'zcat %s | tcpdump -c 1 -S -tt -nr - "%s" | '
                        'awk \'{ FS=" " ; for(i=2;i<=NF;i++) { if ( $i  == "ack") { print $(i+1) }  } ; }\' | sed \'s/,//\' ' %
                        (dump2, filter1), capture=True)
                    baseACK2 = local(
                        'zcat %s | tcpdump -c 1 -S -tt -nr - "%s" | '
                        'awk \'{ FS=" " ; for(i=2;i<=NF;i++) { if ( $i  == "ack") { print $(i+1) }  } ; }\' | sed \'s/,//\' ' %
                        (dump1, filter2), capture=True)

                    #puts('\n[MAIN] BASEACKs %s %s\n' % (baseACK1, baseACK2))

                    # Now extract all ACK sequence numbers, normalised to baseACK{1,2}

                    local(
                        'zcat %s | tcpdump -S -tt -nr - "%s" | '
                        'awk \'{ FS=" " ; for(i=2;i<=NF;i++) { if ( $i  == "ack") { print $1 " " $(i+1) - %s }  } ; }\' | sed \'s/,//\'  > %s' %
                        (dump2, filter1, baseACK1, out_acks1))
                    local(
                        'zcat %s | tcpdump -S -tt -nr - "%s" | '
                        'awk \'{ FS=" " ; for(i=2;i<=NF;i++) { if ( $i  == "ack") { print $1 " " $(i+1) - %s }  } ; }\' | sed \'s/,//\'  > %s' %
                        (dump1, filter2, baseACK2, out_acks2))

                # If we haven't already processed files for this forward flow/direction
                # then do it now -- check that flow matches source_filter
                if name not in out_files:
                    if _in_source_filter(name):
                        if ts_correct == '1':
                            out_acks1 = adjust_timestamps(test_id, out_acks1, dst, ' ')

                        # do the dupACK calculations and burst extraction here,
                        # return a new vector of one or more filenames, pointing to file(s) containing
                        # <time> <seq_no> <dupACKs>
                        #
                        out_acks1_dups_bursts = extract_dupACKs_bursts(acks_file = out_acks1, 
                                                          burst_sep = burst_sep, time_offset=0)
                        # Incorporate the extracted .N files
                        # as a new, expanded set of filenames to be plotted.
                        # Update the out_files dictionary (key=interim legend name based on flow, value=file)
                        # and out_groups dictionary (key=file name, value=group)
                        if burst_sep == 0.0:
                            # Assume this is a single plot (not broken into bursts)
                            # The plot_time_series() function expects key to have a single string
                            # value rather than a vector. Take the first (and presumably only)
                            # entry in the vector returned by extract_dupACKs_bursts()
                            out_files[name] = out_acks1_dups_bursts[0]
                            out_groups[out_acks1_dups_bursts[0]] = group
                        else:
                            # This trial has been broken into one or more bursts.
                            # plot_incast_ACK_series() knows how to parse a key having a
                            # 'vector of strings' value.
                            # Also filter the selection based on sburst/eburst nominated by user
                            if eburst == 0 :
                                eburst = len(out_acks1_dups_bursts)
                            # Catch case when eburst was set non-zero but also > number of actual bursts
                            eburst = min(eburst,len(out_acks1_dups_bursts))
                            if sburst <= 0 :
                                sburst = 1
                            # Catch case where sburst set greater than eburst
                            if sburst > eburst :
                                sburst = eburst

                            out_files[name] = out_acks1_dups_bursts[sburst-1:eburst]
                            for tmp_f in out_acks1_dups_bursts[sburst-1:eburst] :
                                out_groups[tmp_f] = group

                # If we haven't already processed files for this reverse flow/direction
                # then do it now -- check that flow matches source_filter
                if rev_name not in out_files:
                    if _in_source_filter(rev_name):
                        if ts_correct == '1':
                            out_acks2 = adjust_timestamps(test_id, out_acks2, src, ' ')

                        # do the dupACK calculations burst extraction here
                        # return a new vector of one or more filenames, pointing to file(s) containing
                        # <time> <seq_no> <dupACKs>
                        #
                        out_acks2_dups_bursts = extract_dupACKs_bursts(acks_file = out_acks2, 
                                                          burst_sep = burst_sep, time_offset=0)

                        # Incorporate the extracted .N files
                        # as a new, expanded set of filenames to be plotted.
                        # Update the out_files dictionary (key=interim legend name based on flow, value=file)
                        # and out_groups dictionary (key=file name, value=group)
                        if burst_sep == 0.0:
                            # Assume this is a single plot (not broken into bursts)
                            # The plot_time_series() function expects key to have a single string
                            # value rather than a vector. Take the first (and presumably only)
                            # entry in the vector returned by extract_dupACKs_bursts()
                            out_files[name] = out_acks2_dups_bursts[0]
                            out_groups[out_acks2_dups_bursts[0]] = group
                        else:
                            # This trial has been broken into bursts.
                            # plot_incast_ACK_series() knows how to parse a key having a
                            # 'vector of strings' value.
                            # Also filter the selection based on sburst/eburst nominated by user
                            if eburst == 0 :
                                eburst = len(out_acks2_dups_bursts)
                            # Catch case when eburst was set non-zero but also > number of actual bursts
                            eburst = min(eburst,len(out_acks2_dups_bursts))
                            if sburst <= 0 :
                                sburst = 1
                            # Catch case where sburst set greater than eburst
                            if sburst > eburst :
                                sburst = eburst

                            out_files[name] = out_acks2_dups_bursts[sburst-1:eburst]
                            for tmp_f in out_acks2_dups_bursts[sburst-1:eburst] :
                                out_groups[tmp_f] = group

        group += 1

        return (test_id_arr, out_files, out_groups)


# Extract cumulative bytes ACKnowledged and cumulative dupACKs
#
# Parameters:
# 	SEE _extract_ackseq
@task
def extract_ackseq(test_id='', out_dir='', replot_only='0', source_filter='',
                    ts_correct='0', burst_sep='0.0',
                    sburst='1', eburst='0'):
    "Extract cumulative bytes ACKnowledged vs time / extract incast bursts"

    _extract_ackseq(test_id, out_dir, replot_only, source_filter, ts_correct,
                    burst_sep, sburst, eburst)

    # done
    puts('\n[MAIN] COMPLETED extracting ackseq %s \n' % test_id)


# Plot cumulative bytes ACKnowledged or cumulative dupACKs vs time
#
# Parameters:
#   test_id: semicolon-separated list of test ID prefixes of experiments to analyse
#   out_dir: output directory for results
#   replot_only: '1' don't extract raw ACK vs time data per test_ID if already done,
#           but still re-calculate dupACKs and bursts (if any) before plotting results
#   source_filter: filter on specific flows to process
#   omit_const: '0' don't omit anything,
#               '1' omit any series that are 100% constant
#               (e.g. because there was no data flow)
#   ymin: minimum value on y-axis
#   ymax: maximum value on y-axis
#   lnames: semicolon-separated list of legend names per flow
#           (each name will have burst numbers appended if burst_sep is set)
#   stime: start time of plot window in seconds
#           (by default 0.0 = start of experiment)
#   etime: end time of plot window in seconds (by default 0.0 = end of experiment)
#   out_name: prefix for filenames of resulting pdf files
#   pdf_dir: output directory for pdf files (graphs), if not specified it is
#                the same as out_dir
#   ts_correct: '0' use timestamps as they are (default)
#               '1' correct timestamps based on clock offsets estimated
#                       from broadcast pings
#   burst_sep: '0' plot seq numbers as they come, relative to 1st seq number
#               > '0' plot seq numbers relative to 1st seq number after gaps
#               of more than burst_sep milliseconds (e.g. incast query/response bursts)
#               < 0,  plot seq numbers relative to 1st seq number after each abs(burst_sep)
#               seconds since the first burst @ t = 0 (e.g. incast query/response bursts)
#   sburst: Start plotting with burst N (bursts are numbered from 1)
#   eburst: End plotting with burst N (bursts are numbered from 1)
#   dupacks: '0' to plot ACKed bytes vs time
#            '1' to plot cumulative dupACKs vs time
#   plot_params: parameters passed to plot function via environment variables
#   plot_script: specify the script used for plotting, must specify full path
#
# Intermediate files end in ".acks", ".acks.N", ".acks.tscorr" or ".acks.tscorr.N"
# Output pdf files end in:
#   "_ackseqno_time_series.pdf",
#   "_ackseqno_bursts_time_series.pdf",
#   "_comparison_ackseqno_time_series.pdf"
#   "_comparison_ackseqno_bursts_time_series.pdf"
#   (if dupacks=1, then as above with "dupacks" instead of "ackseqno")
#
@task
def analyse_ackseq(test_id='', out_dir='', replot_only='0', source_filter='',
                       min_values='3', omit_const='0', ymin='0', ymax='0', lnames='',
                       stime='0.0', etime='0.0', out_name='',
                       pdf_dir='', ts_correct='0', burst_sep='0.0',
                       sburst='1', eburst='0', dupacks='0',
                       plot_params='', plot_script=''):
    "Plot cumulative bytes ACKnowledged vs time / extract incast bursts"

    (test_id_arr,
     out_files,
     out_groups) =  _extract_ackseq(test_id, out_dir, replot_only, source_filter, 
                    ts_correct, burst_sep, sburst, eburst)

    (out_files, out_groups) = filter_min_values(out_files, out_groups, min_values)
    out_name = get_out_name(test_id_arr, out_name)

    # Set plot conditions based on whether user wants dupacks or acked bytes vs time
    if dupacks == '0' :
        yaxistitle = 'Bytes acknowledged (Kbytes)'
        ycolumn = 2
        yaxisscale =  (1.0/1024.0)
        oname = '_ackseqno'
    else :
        yaxistitle = 'Cumulative dupACKs'
        ycolumn = 3
        yaxisscale = 1.0
        oname = '_dupacks'

    # NOTE: Turn off aggregation with aggr=''
    if burst_sep == 0.0:
        # Regular plots, each trial has one file containing data
        plot_time_series(out_name, out_files, yaxistitle, ycolumn, yaxisscale, 'pdf',
                        out_name + oname, pdf_dir=pdf_dir, aggr='',
                        omit_const=omit_const, ymin=float(ymin), ymax=float(ymax),
                        lnames=lnames, stime=stime, etime=etime, groups=out_groups,
                        plot_params=plot_params, plot_script=plot_script)
    else:
        # Each trial has multiple files containing data from separate ACK bursts detected within the trial
        plot_incast_ACK_series(out_name, out_files, yaxistitle, ycolumn, yaxisscale, 'pdf',
                        out_name + oname + '_bursts', pdf_dir=pdf_dir, aggr='',
                        omit_const=omit_const, ymin=float(ymin), ymax=float(ymax),
                        lnames=lnames, stime=stime, etime=etime, groups=out_groups, burst_sep=burst_sep, 
                        sburst=int(sburst), plot_params=plot_params, plot_script=plot_script)

    # done
    puts('\n[MAIN] COMPLETED plotting ackseq %s \n' % out_name)


# Function that does a 2d density plot with one paramter on x, one one y and the third
# one expressed as different colours of the "blobs" 
# Parameters:
#       exp_list: list of all test IDs (allows to filter out certain experiments,
#                 i.e. specific value comnbinations)
#       res_dir: directory with result files from analyse_all
#       out_dir: output directory for result files
#       source_filter: filter on specific sources
#                      (number of filters must be smaller equal to 12)
#       min_values: ignore flows with less output values / packets
#       xmetric: 'throughput', 'spprtt' (spp rtt), 'tcprtt' (unsmoothed tcp rtt), 'cwnd',
#               'tcpstat', with 'tcpstat' must specify siftr_index or web10g_index 
#       ymetric: 'throughput', 'spprtt' (spp rtt), 'tcprtt' (unsmoothed tcp rtt), 'cwnd',
#               'tcpstat', with 'tcpstat' must specify siftr_index or web10g_index 
#       variables: semicolon-separated list of <var>=<value> where <value> means
#                  we only want experiments where <var> had the specific value
#       out_name: file name prefix
#       xmin: minimum value on x-axis
#       xmax: maximum value on x-axis
#       ymin: minimum value on y-axis
#       ymax: maximum value on y-axis
#       lnames: semicolon-separated list of legend names
#       group_by: semicolon-separated list of variables that defines the different categories 
#                 the variables are the variable names used in the file names
#       pdf_dir: output directory for pdf files (graphs), if not specified it
#                is the same as out_dir
#       ts_correct: '0' use timestamps as they are (default)
#                   '1' correct timestamps based on clock offsets estimated
#                       from broadcast pings
#       smoothed: '0' plot non-smooth RTT (enhanced RTT in case of FreeBSD),
#                 '1' plot smoothed RTT estimates (non enhanced RTT in case of FreeBSD)
#       link_len: '0' throughput based on IP length (default),
#                 '1' throughput based on link-layer length
#       replot_only:  '0' extract data
#                     '1' don't extract data again, just redo the plot
#       plot_params: parameters passed to plot function via environment variables
#       plot_script: specify the script used for plotting, must specify full path
#                    (default is config.TPCONF_script_path/plot_contour.R)
#       xstat_index: an integer number of the column in siftr/web10g log files (for xmetric)
#       ystat_index: an integer number of the column in siftr/web10g log files (for ymetric)
#       dupacks: '0' to plot ACKed bytes vs time
#                '1' to plot dupACKs vs time
# NOTE: that xmin, xmax, ymin and ymax don't just zoom, but govern the selection of data points
#       used for the density estimation. this is how ggplot2 works by default, although possibly
#       can be changed
@task
def analyse_2d_density(exp_list='experiments_completed.txt', res_dir='', out_dir='',
                   source_filter='', min_values='3', xmetric='throughput',
                   ymetric='tcprtt', variables='', out_name='', xmin='0', xmax='0',
                   ymin='0', ymax='0', lnames='', group_by='aqm', replot_only='0',
                   pdf_dir='', ts_correct='0', smoothed='1', link_len='0',
                   plot_params='', plot_script='', xstat_index='', ystat_index='',
                   dupacks='0'):
    "Bubble plot for different experiments"

    test_id_pfx = ''

    check = get_metric_params(xmetric, smoothed, ts_correct)
    if check == None:
        abort('Unknown metric %s specified with xmetric' % xmetric)
    check = get_metric_params(ymetric, smoothed, ts_correct)
    if check == None:
        abort('Unknown metric %s specified with ymetric' % ymetric)

    #if source_filter == '':
    #    abort('Must specify at least one source filter')

    if len(source_filter.split(';')) > 12:
        abort('Cannot have more than 12 filters')

    # XXX more param checking

    # make sure res_dir has valid form (out_dir is handled by extract methods)
    res_dir = valid_dir(res_dir)

    if source_filter != '':
        _build_source_filter(source_filter)

    # read test ids
    experiments = read_experiment_ids(exp_list)

    # get path based on first experiment id 
    dir_name = get_first_experiment_path(experiments)

    # if we haven' got the extracted data run extract method(s) first
    if res_dir == '':
        for experiment in experiments:

            (ex_function, kwargs) = get_extract_function(xmetric, link_len,
                                    xstat_index)

            ex_function(
                test_id=experiment, out_dir=out_dir,
                source_filter=source_filter,
                replot_only=replot_only,
                ts_correct=ts_correct,
                **kwargs)

            (ex_function, kwargs) = get_extract_function(ymetric, link_len,
                                    ystat_index)

            ex_function(
                test_id=experiment, out_dir=out_dir,
                source_filter=source_filter,
                replot_only=replot_only,
                ts_correct=ts_correct,
                **kwargs)

        res_dir = dir_name + '/' + out_dir
    else:
        res_dir = dir_name + '/' + res_dir

    res_dir = valid_dir(res_dir)

    if pdf_dir == '':
        pdf_dir = res_dir
    else:
        pdf_dir = valid_dir(pdf_dir)
        pdf_dir = dir_name + '/' + pdf_dir
        # if pdf_dir specified create if it doesn't exist
        mkdir_p(pdf_dir)

    #
    # build match string from variables
    #

    (match_str, match_str2) = build_match_strings(variables)

    #
    # filter out the experiments to plot, generate x-axis labels, get test id prefix
    #

    (fil_experiments,
     test_id_pfx,
     dummy) = filter_experiments(experiments, match_str, match_str2)

    #
    # get groups based on group_by variable
    #

    group_idx = 1
    levels = {}
    groups = []
    leg_names = []
    _experiments = []
    for experiment in fil_experiments:
        level = ''
        add_exp = True 
        for g in group_by.split(';'):
            p = experiment.find(g)
            if p > -1:
                s = experiment.find('_', p)
                s += 1
                e = experiment.find('_', s)
                level += g + ':' + experiment[s:e] + ' '
            else:
                add_exp = False
                break

        # remove the final space from the string
        level = level[:-1]

        if add_exp == True:
            _experiments.append(experiment)
            #print('level: ' + level)
        
            if level not in levels:
                levels[level] = group_idx
                group_idx += 1
                leg_names.append(level)

            groups.append(levels[level])

    fil_experiments = _experiments

    #
    # get metric parameters and list of data files
    #

    # get the metric parameter for both x and y
    x_axis_params = get_metric_params(xmetric, smoothed, ts_correct, xstat_index, dupacks, 0)
    y_axis_params = get_metric_params(ymetric, smoothed, ts_correct, ystat_index, dupacks, 0)

    x_files = []
    y_files = []
    for experiment in fil_experiments:
        _x_files = []
        _y_files = []

        _x_files += _list(
            local(
                'find -L %s -name "%s*%s" | LC_ALL=C sort' %
                (res_dir, experiment, x_axis_params[0]), capture=True))

        _y_files += _list(
            local(
                'find -L %s -name "%s*%s" | LC_ALL=C sort' %
                (res_dir, experiment, y_axis_params[0]), capture=True))

        match_str = '.*_([0-9\.]*_[0-9]*_[0-9\.]*_[0-9]*)[0-9a-z_.]*' + x_axis_params[0]
        for f in _x_files:
            print(f)
            res = re.search(match_str, f)
            print(res.group(1))
            if res and _in_source_filter(res.group(1)):
                # only add file if enough data points
                rows = int(
                    local('wc -l %s | awk \'{ print $1 }\'' %
                          f, capture=True))
                if rows > int(min_values):
                    x_files.append(f)
        match_str = '.*_([0-9\.]*_[0-9]*_[0-9\.]*_[0-9]*)[0-9a-z_.]*' + y_axis_params[0]
        for f in _y_files:
            # print(f)
            res = re.search(match_str, f)
            if res and _in_source_filter(res.group(1)):
                # only add file if enough data points
                rows = int(
                    local('wc -l %s | awk \'{ print $1 }\'' %
                          f, capture=True))
                if rows > int(min_values):
                    y_files.append(f)

    yindexes = [str(x_axis_params[2]), str(y_axis_params[2])]
    yscalers = [str(x_axis_params[3]), str(y_axis_params[3])]
    aggr_flags = [x_axis_params[5], y_axis_params[5]]
    diff_flags = [x_axis_params[6], y_axis_params[6]]

    if lnames != '':
        lnames_arr = lnames.split(';')
        if len(lnames_arr) != len(leg_names):
            abort(
                'Number of legend names must be qual to the number of source filters')
        leg_names = lnames_arr

    print(x_files)
    print(y_files)
    print(groups)
    print(leg_names)

    #
    # pass the data files and auxilary info to plot function
    #

    if out_name != '':
        oprefix = out_name + '_' + test_id_pfx + '_' + xmetric + '_' + ymetric
    else:
        oprefix = test_id_pfx + '_' + xmetric + '_' + ymetric
    title = oprefix

    if plot_script == '':
        plot_script = '%s/plot_contour.R' % config.TPCONF_script_path

    local('which R')
    local('TITLE="%s" XFNAMES="%s" YFNAMES="%s", LNAMES="%s" XLAB="%s" YLAB="%s" YINDEXES="%s" '
          'YSCALERS="%s" XSEP="%s" YSEP="%s" OTYPE="%s" OPREFIX="%s" ODIR="%s" AGGRS="%s" '
          'DIFFS="%s" XMIN="%s" XMAX="%s" YMIN="%s" YMAX="%s" GROUPS="%s" %s '
          'R CMD BATCH --vanilla %s %s%s_plot_contour.Rout' %
          (title, ','.join(x_files), ','.join(y_files), ','.join(leg_names),
           x_axis_params[1], y_axis_params[1], ','.join(yindexes), ','.join(yscalers),
           x_axis_params[4], y_axis_params[4], 'pdf', oprefix, pdf_dir, ','.join(aggr_flags),
           ','.join(diff_flags), xmin, xmax, ymin, ymax, ','.join([str(x) for x in groups]), 
           plot_params, plot_script, pdf_dir, oprefix))

    if config.TPCONF_debug_level == 0:
        local('rm -f %s%s_plot_contour.Rout' % (pdf_dir, oprefix))

    # done
    puts('\n[MAIN] COMPLETED analyse_2d_density %s \n' % test_id_pfx)

