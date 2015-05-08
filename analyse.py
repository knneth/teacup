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
## @package analyse
# Analyse experiment data
#
# $Id: analyse.py 1316 2015-05-06 06:53:17Z szander $

import os
import errno
import time
import datetime
import re
import socket
import imp
from fabric.api import task, warn, put, puts, get, local, run, execute, \
    settings, abort, hosts, env, runs_once, parallel, hide

import config
from internalutil import _list, mkdir_p, valid_dir
from hostint import get_address_pair
from clockoffset import adjust_timestamps, DATA_CORRECTED_FILE_EXT
from filefinder import get_testid_file_list
from flowcache import append_flow_cache, lookup_flow_cache
from sourcefilter import SourceFilter


#############################################################################
# Flow sorting functions
#############################################################################


## Compare low keys by flow source port (lowest source port first)
#  @param x Flow key of the form something_<src_ip>_<src_port>_<dst_ip>_<dst_port>
#  @param y Flow key of the form something_<src_ip>_<src_port>_<dst_ip>_<dst_port>
def _cmp_src_port(x, y):
    "Compare flow keys by flow source port (lowest source port first)"

    xflow = str(x)
    yflow = str(y)

    # split into src/dst IP/port
    xflow_arr = xflow.split('_') 
    xflow_arr = xflow_arr[len(xflow_arr)-4:len(xflow_arr)]
    yflow_arr = yflow.split('_')
    yflow_arr = yflow_arr[len(yflow_arr)-4:len(yflow_arr)]

    # sort by numeric source port
    return cmp(int(xflow_arr[1]), int(yflow_arr[1]))


## Compare flow keys by flow dest port (lowest dest port first)
#  @param x Flow key of the form something_<src_ip>_<src_port>_<dst_ip>_<dst_port>
#  @param y Flow key of the form something_<src_ip>_<src_port>_<dst_ip>_<dst_port>
def _cmp_dst_port(x, y):
    "Compare flow keys by flow dest port (lowest dest port first)"

    xflow = str(x)
    yflow = str(y)

    # split into src/dst IP/port
    xflow_arr = xflow.split('_')
    xflow_arr = xflow_arr[len(xflow_arr)-4:len(xflow_arr)]
    yflow_arr = yflow.split('_')
    yflow_arr = yflow_arr[len(yflow_arr)-4:len(yflow_arr)]

    # sort by numeric dest port
    return cmp(int(xflow_arr[3]), int(yflow_arr[3]))


## Sort flow keys
## If all flows are bidirectional, sort so that server-client flows appear
## at left and client-server flows at right. Otherwise we always have 
## server-client flow followed by client-server flow (if the latter exists)
#  @param files Name to file name map
#  @param source_filter Source filter
#  @return List of sorted (flow_name, file_name) tuples
def sort_by_flowkeys(files={}, source_filter=''):
    "Sort flow names"

    sorted_files = []

    # convert source_filter string into list of source filters
    source_filter_list = []
    if source_filter != '':
        for fil in source_filter.split(';'):
            fil = fil.strip()
            source_filter_list.append(fil)

    #
    # 1. if filter string was specified graph in order of filters
    #

    if len(source_filter_list) > 0:
        for fil in source_filter_list:
            # strip of the (S|D) part a the start
            arr = fil.split('_')
            if arr[2] == '*':
                fil = arr[1] + '_'
            else:
                fil = arr[1] + '_' + arr[2]

            # find the file entries that matches the filter
            # then alphabetically sort file names for each filter
            # before adding to return array. note we sort the reversed
            # file names, so order is determined by flow tuple which is
            # at the end of the names ([::-1] reverses the string)
            # make sure we only add entry if it is not in the list yet
            tmp = []
            for name in files:
                if fil in name and (name, files[name]) not in tmp and \
                   (name, files[name]) not in sorted_files:
                    tmp.append((name, files[name]))

            sorted_files.extend(sorted(tmp, key=lambda x: x[1][::-1]))

        return sorted_files

    #
    # 2. otherwise do our best to make sure we have a sensible and consistent
    #    ordering based on server ports

    rev_files = {}

    # sort by dest port if and only if dest port is always lower than source
    # port
    cmp_fct = _cmp_dst_port
    for name in files:
        a = name.split('_')
        a = a[len(a)-4:len(a)]
        if int(a[1]) < int(a[3]):
            cmp_fct = _cmp_src_port
            break

    for name in sorted(files, cmp=cmp_fct):
        # print(name)
        if rev_files.get(name, '') == '':
            sorted_files.append((name, files[name]))
            a = name.split('_')
            a = a[len(a)-4:len(a)]
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


## Sort flow keys by group ID
## If we have groups make sure that group order is the same for all flows
#  @param files (flow name, file name) tuples (sorted by sort_by_flowkeys)
#  @param groups File name to group number map
#  @return List of sorted (flow_name, file_name) tuples 
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


## Sort flow keys by group ID
## like sort_by_group_id()  function, but the tuples in files are (string,list) instead
# of (string, string). Assumption: all files in one list belong to the same group! 
#  @param files (flow name, file name) tuples (sorted by sort_by_flowkeys)
#  @param groups File name to group number map
#  @return List of sorted (flow_name, file_name) tuples
def sort_by_group_id2(files={}, groups={}):

    sorted_files = [('', [])] * len(files)

    if max(groups.values()) == 1:
        return files
    else:
        num_groups = max(groups.values())
        cnt = 0
        for fil in files:
            start = int(cnt / num_groups)
            grp = groups[fil[1][0]]
            sorted_files[start * num_groups + grp - 1] = fil
            cnt += 1

        return sorted_files


###########################################################################
# Helper functions
###########################################################################


## Figure out directory for output files and create if it doesn't exist
## If out_dir is a relative path, the actual out_dir will be the directory where
## the file fname is concatenated with out_dir. If out_dir is an absolute path
## then the final out_dir will be out_dir. 
#  @param fname Path name of file
#  @param out_dir Output directory supplied by user
#  @return Path name
def get_out_dir(fname, out_dir): 

    #print(fname, out_dir)
    if out_dir == '' or out_dir[0] != '/':
        dir_name = os.path.dirname(fname)
        out_dir = dir_name + '/' + out_dir

    if len(out_dir) > 0 and out_dir[-1] != '/':
        out_dir += '/'

    mkdir_p(out_dir)

    return out_dir 


#############################################################################
# Plot functions
#############################################################################

## Plot time series
#  @param title Title of plot at the top
#  @param files Dictionary with legend names (keys) and files with the data
#               to plot (values)
#  @param ylab Label for y-axis
#  @param yindex Index of the column in data file to plot
#  @param yscaler Scaler for y-values (data in file is multiplied with the scaler)
#  @param otype Type of output file
#  @param oprefix Output file name prefix
#  @param pdf_dir Output directory for graphs
#  @param sep Character that separates columns in data file
#  @param aggr Aggregation of data in time intervals
#  @param omit_const '0' don't omit anything,
#                    '1' omit any series that are 100% constant
#                       (e.g. because there was no data flow)
#  @param ymin Minimum value on y-axis
#  @param ymax Maximum value on y-axis
#  @param lnames Semicolon-separated list of legend names
#  @param stime Start time of plot window in seconds
#               (by default 0.0 = start of experiment)
#  @param etime End time of plot window in seconds
#               (by default 0.0 = end of experiment)
#  @param groups Map data files to groups (all files of same experiment must have
#                same group number)
#  @param sort_flowkey '1' sort by flow key (default)
#                      '0' don't sort by flow key
#  @param boxplot '0' normal time series
#                 '1' do boxplot for all values at one point in time
#  @param plot_params Parameters passed to plot function via environment variables
#  @param plot_script Specify the script used for plotting, must specify full path
#                     (default is config.TPCONF_script_path/plot_time_series.R)
#  @param source_filter Source filter
def plot_time_series(title='', files={}, ylab='', yindex=2, yscaler=1.0, otype='',
                     oprefix='', pdf_dir='', sep=' ', aggr='', omit_const='0',
                     ymin=0, ymax=0, lnames='',
                     stime='0.0', etime='0.0', groups={}, sort_flowkey='1',
                     boxplot='', plot_params='', plot_script='', source_filter=''):

    file_names = []
    leg_names = []
    _groups = []

    #print(files)
    if sort_flowkey == '1':
        sorted_files = sort_by_flowkeys(files, source_filter)
    else:
        sorted_files = files.items()

    print(sorted_files)
    sorted_files = sort_by_group_id(sorted_files, groups)
    print(sorted_files)

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
        # if not absolute dir, make it relative to experiment_dir
        # assume experiment dir is part before first slash
        if pdf_dir[0] != '/':
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


## Plot DASH goodput
#  @param title Title of plot at the top
#  @param files Dictionary with legend names (keys) and files with the data to plot
#               (values)
#  @param groups Map data files to groups (all files of same experiment must have
#                same group number)
#  @param ylab Label for y-axis
#  @param otype Type of output file
#  @param oprefix Output file name prefix
#  @param pdf_dir Output directory for graphs
#  @param sep Character that separates columns in data file
#  @param ymin Minimum value on y-axis
#  @param ymax Maximum value on y-axis
#  @param lnames Semicolon-separated list of legend names
#  @param stime Start time of plot window in seconds
#               (by default 0.0 = start of experiment)
#  @param etime End time of plot window in seconds (by default 0.0 = end of
#               experiment)
#  @param plot_params Parameters passed to plot function via environment variables
#  @param plot_script Specify the script used for plotting, must specify full path
#                     (default is config.TPCONF_script_path/plot_dash_goodput.R)
def plot_dash_goodput(title='', files={}, groups={}, ylab='', otype='', oprefix='',
                      pdf_dir='', sep=' ', ymin=0, ymax=0, lnames='', stime='0.0', 
                      etime='0.0', plot_params='', plot_script=''):

    file_names = []
    leg_names = []

    sorted_files = sorted(files.items())
    sorted_files = sort_by_group_id(sorted_files, groups)
    #print(sorted_files)

    for name, file_name in sorted_files:
        leg_names.append(name)
        file_names.append(file_name)

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
        # if not absolute dir, make it relative to experiment_dir
        # assume experiment dir is part before first slash
        if pdf_dir != '/':
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

    #local('which R')
    local('TITLE="%s" FNAMES="%s" LNAMES="%s" YLAB="%s" SEP="%s" OTYPE="%s" '
          'OPREFIX="%s" ODIR="%s" YMIN="%s" YMAX="%s" STIME="%s" ETIME="%s" %s '
          '%s %s%s_plot_dash_goodput.Rout' %
          (title, ','.join(file_names), ','.join(leg_names), ylab, sep, otype, oprefix,
           pdf_dir, ymin, ymax, stime, etime, plot_params, plot_script, 
           pdf_dir, oprefix))

    if config.TPCONF_debug_level == 0:
        local('rm -f %s%s_plot_dash_goodput.Rout' % (pdf_dir, oprefix))



## plot_incast_ACK_series
## (based on plot_time_series, but massages the filenames and legend names a little
## differently to handle a trial being broken into 'bursts'.)
#  @param title Title of plot at the top
#  @param files Dictionary with legend names (keys) and files with the data
#               to plot (values)
#  @param ylab Label for y-axis
#  @param yindex Index of the column in data file to plot
#  @param yscaler Scaler for y-values (data in file is multiplied with the scaler)
#  @param otype Type of output file
#  @param oprefix Output file name prefix
#  @param pdf_dir Output directory for graphs
#  @param sep Character that separates columns in data file
#  @param aggr Aggregation of data in 1-seond intervals
#  @param omit_const '0' don't omit anything,
#                    '1' omit any series that are 100% constant
#                       (e.g. because there was no data flow)
#  @param ymin Minimum value on y-axis
#  @param ymax Maximum value on y-axis
#  @param lnames Semicolon-separated list of legend names
#  @param stime Start time of plot window in seconds
#               (by default 0.0 = start of experiment)
#  @param etime End time of plot window in seconds
#               (by default 0.0 = end of experiment)
#  @param groups Map data files to groups (all files of same experiment must have
#                same group number)
#  @param sort_flowkey '1' sort by flow key (default)
#                      '0' don't sort by flow key
#  @param burst_sep '0' plot seq numbers as they come, relative to 1st seq number
#                   > '0' plot seq numbers relative to 1st seq number after gaps
#                         of more than burst_sep seconds (e.g. incast query/response bursts)
#                   < 0,  plot seq numbers relative to 1st seq number after each abs(burst_sep)
#                         seconds since the first burst @ t = 0 (e.g. incast query/response bursts)
#  @param sburst Default 1, or a larger integer indicating the burst number of the first burst
#                in the provided list of filenames. Used as an offset to calculate new legend suffixes.
#  @param plot_params Parameters passed to plot function via environment variables
#  @param plot_script Specify the script used for plotting, must specify full path
#                    (default is config.TPCONF_script_path/plot_bursts.R)
#  @param source_filter Source filter
def plot_incast_ACK_series(title='', files={}, ylab='', yindex=2, yscaler=1.0, otype='',
                     oprefix='', pdf_dir='', sep=' ', aggr='', omit_const='0',
                     ymin=0, ymax=0, lnames='', stime='0.0', etime='0.0', 
                     groups={}, sort_flowkey='1', burst_sep='1.0', sburst=1,
                     plot_params='', plot_script='', source_filter=''):

    file_names = []
    leg_names = []
    _groups = []

    # Pick up case where the user has supplied a number of legend names
    # that doesn't match the number of distinct trials (as opposed to the
    # number of bursts detected within each trial)
    if lnames != '':
        if len(lnames.split(";")) != len(files.keys()) :
            abort(
                'Number of legend names must be the same as the number of flows')

    if sort_flowkey == '1':
        sorted_files = sort_by_flowkeys(files, source_filter)
    else:
        sorted_files = files.items()

    #print("MAIN: sorted_files: %s" % sorted_files)

    # sort by group id
    sorted_files = sort_by_group_id2(sorted_files, groups)

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
        # if no absolute path make it relative to experiment_dir
        # assume experiment dir is part before first slash
        if pdf_dir[0] != '/':
            pdf_dir = file_names[0].split('/')[0] + '/' + pdf_dir
        # if pdf_dir specified create if it doesn't exist
        mkdir_p(pdf_dir)

    if plot_script == '':
        plot_script = 'R CMD BATCH --vanilla %s/plot_bursts.R' % \
                       config.TPCONF_script_path

    #local('which R')
    local('TITLE="%s" FNAMES="%s" LNAMES="%s" YLAB="%s" YINDEX="%d" YSCALER="%f" '
          'SEP="%s" OTYPE="%s" OPREFIX="%s" ODIR="%s" AGGR="%s" OMIT_CONST="%s" '
          'YMIN="%s" YMAX="%s" STIME="%s" ETIME="%s" GROUPS="%s" %s '
          'BURST_SEP=1 '
          '%s %s%s_plot_bursts.Rout' %
          (title, ','.join(file_names), ','.join(leg_names), ylab, yindex, yscaler,
           sep, otype, oprefix, pdf_dir, aggr, omit_const, ymin, ymax, stime, etime,
           ','.join(map(str, _groups)), plot_params, plot_script, pdf_dir, oprefix))

    if config.TPCONF_debug_level == 0:
        local('rm -f %s%s_plot_bursts.Rout' % (pdf_dir, oprefix))


###################################################################################
# Helper functions for extract and plot functions
###################################################################################


## Get graph output file name
#  @param test_id_arr List of test IDs
#  @param out_name Output file name prefix
#  @return Output file name
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


## Check number of data rows and include file if over minimum
#  @param fname Data file name
#  @param min_values Minimum number of values required
#  @return True if file has more than minimum rows, False otherwise
def enough_rows(fname='', min_values='3'):

    min_values = int(min_values)

    #rows = int(local('wc -l %s | awk \'{ print $1 }\'' %
    #               fname, capture=True))
    rows = 0
    with open(fname, 'r') as f:
        while f.readline():
            rows += 1
            if rows > min_values:
                break

    if rows > min_values:
        return True 
    else:
        return False


## Filter out data files with fewer than min_values data points
#  @param files File names indexed by flow names
#  @param groups Group ids indexed by file names
#  @param min_values Minimum number of values required
#  @return Filtered file names and groups
def filter_min_values(files={}, groups={}, min_values='3'):

    out_files = {}
    out_groups = {}
 
    for name in files:
        fname = files[name]

        if isinstance(fname, list) :
            # the ackseq method actually creates a name to list of file names
            # mapping, i.e. multiple file names per dataset name
            for _fname in fname:
                if enough_rows(_fname, min_values):
                    if not name in out_files:
                        out_files[name] = []
                    out_files[name].append(_fname)
                    out_groups[_fname] = groups[_fname]

        else:
            if enough_rows(fname, min_values):
                out_files[name] = fname
                out_groups[fname] = groups[fname]
 
    return (out_files, out_groups)


## Extract data per incast burst
#  @param data_file File with data
#  @param burst_sep Time between bursts (0.0 means no burst separation)
#  @param normalize 0: leave metric values as they are (default)
#                  1: normalise metric values on first value or first value
#                     fo each burst (if burst_sep > 0.0)        
#  @return List of file names (one file per burst)
def extract_bursts(data_file='', burst_sep=0.0, normalize=0):

    # New filenames (source file + ".0" or ".1,.2,....N" for bursts)
    new_fnames = [];

    # Internal variables
    burstN = 1
    firstTS = -1
    prev_data = -1 

    try:
        lines = []
        # First read the entire contents of a data file
        with open(data_file) as f:
            lines = f.readlines()

            if burst_sep != 0 :
                # Create the first .N output file
                out_f = open(data_file + "." + "1", "w")
                new_fnames.append(data_file + "." + "1")
            else:
                out_f = open(data_file + "." + "0", "w")
                new_fnames.append(data_file + "." + "0")

            # Now walk through every line of the data file
            for oneline in lines:
                # fields[0] is the timestamp, fields[1] is the statistic 
                fields = oneline.split()

                if firstTS == -1 :
                    # This is first time through the loop, so set some baseline
                    # values for later offsets
                    firstTS = fields[0]
                    prevTS = firstTS
                    if normalize == 1:
                        first_data = fields[1] 
                    else:
                        first_data = '0.0' 

                # If burst_sep == 0 the only thing we're calculating is a
                # cumulative running total, so we only do burst
                # identification if burst_sep != 0

                if burst_sep != 0 :

                    if burst_sep < 0 :
                        # gap is time since first statistic of this burst
                        # (i.e. relative to firstTS)
                        gap = float(fields[0]) - float(firstTS)
                    else:
                        gap = float(fields[0]) - float(prevTS)


                    # New burst begins when time between this statistic and previous
                    # exceeds abs(burst_sep)
                    if (gap >= abs(burst_sep)) :
                        # We've found the first one of the _next_ burst

                        # Close previous burst output file
                        out_f.close()

                        # Move on to the next burst
                        burstN += 1

                        print ("Burst: %3i, ends at %f sec, data: %f bytes, gap: %3.6f sec" %
                        ( (burstN - 1),  float(prevTS), float(prev_data) - float(first_data), gap ) )

                        # Reset firstTS to the beginning (first timestamp) of this new burst
                        firstTS = fields[0]

                        # first data value of next burst must be considered relative to the last 
                        # data value of the previous burst if we normalize 
                        if normalize == 1:
                            first_data = prev_data

                        # Create the next .N output file
                        out_f = open(data_file + "." + str(burstN), "w")
                        new_fnames.append(data_file + "." + str(burstN))


                # data value (potentially normalised based on first value / first value of burst
                data_gap = float(fields[1]) - float(first_data)

                # Write to burst-specific output file
                # <time>  <data>
                out_f.write(fields[0] + " " + str(data_gap) + "\n")

                # Store the seq number for next time around the loop
                prev_data = fields[1]
                prevTS = fields[0]

            # Close the last output file
            out_f.close()

    except IOError:
        print('extract_ursts(): File access problem while working on %s' % data_file)

    return new_fnames


## Select bursts to plot and add files to out_files and out_groups 
#  @param name Flow name
#  @param group Flow group
#  @param data_file Data file for flow
#  @param burst_sep Time between bursts in seconds
#  @param sburst First burst in output
#  @param eburst Last burst in output
#  @param out_files Map of flow names to file names
#  @param out_groups Map of file names to group numbers
#  @return Updated file and group lists (with burst file data)
def select_bursts(name='', group='', data_file='', burst_sep='0.0', sburst='1', eburst='0', 
                  out_files={}, out_groups={}):

    burst_sep = float(burst_sep)
    sburst = int(sburst)
    eburst = int(eburst)
 
    # do the burst extraction here,
    # return a new vector of one or more filenames, pointing to file(s) containing
    # <time> <statistic> 
    #
    out_burst_files = extract_bursts(data_file = data_file, burst_sep = burst_sep)
    # Incorporate the extracted .N files
    # as a new, expanded set of filenames to be plotted.
    # Update the out_files dictionary (key=interim legend name based on flow, value=file)
    # and out_groups dictionary (key=file name, value=group)
    if burst_sep == 0.0:
        # Assume this is a single plot (not broken into bursts)
        # The plot_time_series() function expects key to have a single string
        # value rather than a vector. Take the first (and presumably only)
        # entry in the vector returned by extract_bursts()
        out_files[name] = out_burst_files[0]
        out_groups[out_burst_files[0]] = group
    else:
        # This trial has been broken into one or more bursts.
        # plot_incast_ACK_series() knows how to parse a key having a
        # 'vector of strings' value.
        # Also filter the selection based on sburst/eburst nominated by user
        if eburst == 0 :
            eburst = len(out_burst_files)
        # Catch case when eburst was set non-zero but also > number of actual bursts
        eburst = min(eburst,len(out_burst_files))
        if sburst <= 0 :
            sburst = 1
        # Catch case where sburst set greater than eburst
        if sburst > eburst :
            sburst = eburst

        out_files[name] = out_burst_files[sburst-1:eburst]
        for tmp_f in out_burst_files[sburst-1:eburst] :
            out_groups[tmp_f] = group

    return (out_files, out_groups)


## Merge several data files into one data file 
#  @param in_files List of file names
#  @return List with merged file name 
def merge_data_files(in_files):

    # resulting file name will be the first file name with the flow tuple replaced by
    # 0.0.0.0_0_0.0.0.0_0 indicating a merged file 
    merge_fname = re.sub('_[0-9]*\.[0-9]*\.[0-9]*\.[0-9]*_[0-9]*_[0-9]*\.[0-9]*\.[0-9]*\.[0-9]*_[0-9]*', 
                        '_0.0.0.0_0_0.0.0.0_0', in_files[0])
    merge_fname += '.all'
    #print(merge_fname)

    f_out = open(merge_fname, 'w')

    for fname in sorted(in_files):
        with open(fname) as f:
            lines = f.readlines()
        f_out.writelines(lines)

    f_out.close()

    return [merge_fname]


## global list of participating hosts for each experiment
part_hosts = {} 

## Get list of hosts that participated in experiment
#  @param test_id Experiment id
#  @return List of hosts 
def get_part_hosts(test_id):
    global part_hosts

    if test_id not in part_hosts:

        part_hosts[test_id] = []

        # first process tcpdump files (ignore router and ctl interface tcpdumps)
        uname_files = get_testid_file_list('', test_id,
                                   'uname.log.gz', '')

        for f in uname_files:
            res = re.search('.*_(.*)_uname.log.gz', f)
            if res:
                part_hosts[test_id].append(res.group(1))

    return part_hosts[test_id]


## map test IDs or directory names to TPCONF_host_internal_ip structures
host_internal_ip_cache = {}
## map test IDs or directory names to list of hosts (TPCONF_router + TPCONF_hosts) 
host_list_cache = {}

## Get external and internal address for analysis functions
#  @param test_id Experiment id
#  @param host Internal or external address
#  @param do_abort '0' do not abort if no external address found, '1' abort if no
#                  external address found
#  @return Pair of external address and internal address, or pair of empty strings
#          if host not part of experiment
def get_address_pair_analysis(test_id, host, do_abort='1'):
    global host_internal_ip_cache
    global host_list_cache
    internal = ''
    external = ''
    TMP_CONF_FILE = '___oldconfig.py'

    # XXX the whole old config access should be moved into separate module as 
    # similar code is also in clockoffset
   
    # prior to TEACUP version 0.9 it was required to run the analysis with a config
    # file that had config.TPCONF_host_internal_ip as it was used to run the experiment
    # (or a superset of it). Since version 0.9 we use config.TPCONF_host_internal_ip
    # (as well as config.TPCONF_hosts and config.TPCONF_router) from the file 
    # <test_id_prefix>_tpconf_vars.log.gz in the test experiment directory.

    if test_id not in host_internal_ip_cache:
        # first find the directory but looking for mandatory uname file
        uname_file = get_testid_file_list('', test_id,
                                          'uname.log.gz', '')
        dir_name = os.path.dirname(uname_file[0])

        if dir_name in host_internal_ip_cache:
            # create test id cache entry from directory entry 
            host_internal_ip_cache[test_id] = host_internal_ip_cache[dir_name] 
            if host_internal_ip_cache[test_id] != None:
                host_list_cache[test_id] = host_list_cache[dir_name] 
        else:
            # try to find old config information

            # look for tpconf_vars.log.gz file in that directory 
            var_file = local('find -L %s -name "*tpconf_vars.log.gz"' % dir_name,
                             capture=True)

            if len(var_file) > 0:
                # new approach without using config.py

                # unzip archived file
                local('gzip -cd %s > %s' % (var_file, TMP_CONF_FILE))

                # load the TPCONF_variables into oldconfig
                oldconfig = imp.load_source('oldconfig', TMP_CONF_FILE)

                # remove temporary unzipped file 
                try:
                    os.remove(TMP_CONF_FILE)
                    os.remove(TMP_CONF_FILE + 'c') # remove the compiled file as well
                except OSError:
                    pass

                # store data in cache (both under test id and directory name)
                host_internal_ip_cache[test_id] = oldconfig.TPCONF_host_internal_ip
                host_list_cache[test_id] = oldconfig.TPCONF_hosts + oldconfig.TPCONF_router
                host_internal_ip_cache[dir_name] = oldconfig.TPCONF_host_internal_ip
                host_list_cache[dir_name] = oldconfig.TPCONF_hosts + oldconfig.TPCONF_router
            else:
                # old approach using the functions in hostint.py that access config.py
                # store empty value in cache (both under test id and directory name)
                host_internal_ip_cache[test_id] = None
                host_internal_ip_cache[dir_name] = None

    if host_internal_ip_cache[test_id] != None:
        # new approach

        # pretend it is an external name and perform lookup
        internal = host_internal_ip_cache[test_id].get(host, [])
        if len(internal) == 0:
            # host is internal name, so need to find external name
            internal = host
            for e, i in host_internal_ip_cache[test_id].items():
                if i[0] == host:
                    external = e 
        else:
            # host is external name
            internal = internal[0]
            external = host

        hosts = host_list_cache[test_id] 

    else:
        # old approach
    
        (external, internal) = get_address_pair(host, do_abort)

        hosts = get_part_hosts(test_id)

    if external not in hosts:
        return ('', '')
    else:
        return (external, internal)


###################################################################################
# Main extract and plot functions
###################################################################################


## Extract DASH goodput data from httperf log files
## The extracted files have an extension of .dashgp. The format is CSV with the
## columns:
## 1. Timestamp of request (second.microsecond)
## 2. Size of requested/downloaded block (bytes)
## 3. Byte rate (mbps), equivalent to size devided by response time times 8
## 4. Response time (seconds)
## 5. Nominal/definded cycle length (seconds)
## 6. Nominal/defined rate (kbps)
## 7. Block number
#  @param test_id Test ID prefix of experiment to analyse
#  @param out_dir Output directory for results
#  @param replot_only If '1' don't extract already extracted data
#                     if '0' extract data (default)
#  @param dash_log_list File name with a list of dash logs
#  @param ts_correct If '0' use timestamps as they are (default)
#                    if '1' correct timestamps based on clock offsets estimated
#                    from broadcast pings
#  @return Test ID list, map of flow names to interim data file names, map of files
#          and group ids
def _extract_dash_goodput(test_id='', out_dir='', replot_only='0', dash_log_list='',
                          ts_correct='1'):
    "Extract DASH goodput from httperf logs"

    # extension of input data files
    ifile_ext = '_httperf_dash.log.gz'
    # extension of output data files
    ofile_ext = '.dashgp'

    # files with extracted data
    out_files = {}
    # group ids (map each file to an experiment)
    out_groups = {}
    # input dash log files
    dash_files = []
 
    test_id_arr = test_id.split(';')
    dash_files = get_testid_file_list(dash_log_list, test_id,
				      ifile_ext, '') 

    for dash_file in dash_files:
        # set and create result directory if necessary
        out_dirname = get_out_dir(dash_file, out_dir)

        dash_file = dash_file.strip()
        name = os.path.basename(dash_file.replace(ifile_ext, ''))
        out = out_dirname + name + ofile_ext 

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

        host = local(
            'echo %s | sed "s/.*_\([a-z0-9\.]*\)_[0-9]*%s/\\1/"' %
            (dash_file, ifile_ext), capture=True)
        test_id = local(
            'echo %s | sed "s/.*\/\(.*\)_%s_.*/\\1/"' %
            (dash_file, host), capture=True)

        if ts_correct == '1':
            out = adjust_timestamps(test_id, out, host, ',', out_dir)

        if dash_log_list != '':
            # need to build test_id_arr
            if test_id not in test_id_arr:
                test_id_arr.append(test_id) 
        # else test_id_arr has the list of test ids

        # group number is just the index in the list plus one (start with 1)
        group = test_id_arr.index(test_id) + 1

        out_files[name] = out
        out_groups[out] = group

    return (test_id_arr, out_files, out_groups)


## Extract DASH goodput data from httperf log files (TASK)
## SEE _extract_dash_goodput()
@task
def extract_dash_goodput(test_id='', out_dir='', replot_only='0', dash_log_list='',
                         out_name='', ts_correct='1'):
    "Extract DASH goodput from httperf logs"

    _extract_dash_goodput(test_id, out_dir, replot_only, dash_log_list, ts_correct) 

    # done
    puts('\n[MAIN] COMPLETED extracting DASH goodput %s \n' % test_id)


## Plot DASH goodput from httperf log files
#  @param test_id Test IDs of experiments to analyse (ignored if dash_log_list
#                 is specified)
#  @param out_dir Output directory for results
#  @param replot_only Don't extract data again, just redo the plot
#  @param dash_log_list File name with a list of dash logs
#  @param lnames Semicolon-separated list of legend names
#  @param out_name Name prefix for resulting pdf file
#  @param pdf_dir Output directory for pdf files (graphs),
#                 if not specified it is the same as out_dir
#  @param ymin Minimum value on y-axis
#  @param ymax Maximum value on y-axis
#  @param stime Start time of plot window in seconds
#               (by default 0.0 = start of experiment)
#  @param etime End time of plot window in seconds (by default 0.0 = end of
#               experiment)
#  @param ts_correct '0' use timestamps as they are (default)
#                    '1' correct timestamps based on clock offsets estimated
#                        from broadcast pings
#  @param plot_params Parameters passed to plot function via environment variables
#  @param plot_script Specify the script used for plotting, must specify full path
@task
def analyse_dash_goodput(test_id='', out_dir='', replot_only='0', dash_log_list='',
                         lnames='', out_name='', pdf_dir='', ymin=0, ymax=0,
                         stime='0.0', etime='0.0', ts_correct='1', plot_params='',
                         plot_script=''):
    "Plot DASH goodput from httperf logs"

    # get list of test_ids and data files for plot
    (test_id_arr, 
     out_files, 
     out_groups) = _extract_dash_goodput(test_id, out_dir, replot_only, dash_log_list, 
                                         ts_correct) 

    # set output file name and plot title
    out_name = ''
    title = ''
    if dash_log_list != '':
        out_name = get_out_name(dash_log_list, out_name)
        title = dash_log_list
    else:
        out_name = get_out_name(test_id_arr, out_name)
        title = test_id_arr[0]

    # call plot function
    plot_dash_goodput(
        title,
        out_files,
        out_groups,
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
    puts('\n[MAIN] COMPLETED plotting DASH goodput %s \n' % out_name)


## Extract RTT for flows using SPP
## The extracted files have an extension of .rtts. The format is CSV with the
## columns:
## 1. Timestamp RTT measured (seconds.microseconds)
## 2. RTT (seconds)
#  @param test_id Test ID prefix of experiment to analyse
#  @param out_dir Output directory for results
#  @param replot_only Don't extract data again that is already extracted
#  @param source_filter Filter on specific sources
#  @param udp_map Map that defines unidirectional UDP flows to combine. Format:
#	          <ip1>,<port1>:<ip2>,<port2>[;<ip3>,<port3>:<ip4>,<port4>]*
#  @param ts_correct '0' use timestamps as they are (default)
#                    '1' correct timestamps based on clock offsets estimated
#                        from broadcast pings
#  @param burst_sep '0' plot seq numbers as they come, relative to 1st seq number
#                 > '0' plot seq numbers relative to 1st seq number after gaps
#                       of more than burst_sep milliseconds (e.g. incast query/response bursts)
#                 < 0,  plot seq numbers relative to 1st seq number after each abs(burst_sep)
#                       seconds since the first burst @ t = 0 (e.g. incast query/response bursts)
#  @param sburst Start plotting with burst N (bursts are numbered from 1)
#  @param eburst End plotting with burst N (bursts are numbered from 1)
#  @return Test ID list, map of flow names to interim data file names and 
#          map of file names and group IDs
def _extract_rtt(test_id='', out_dir='', replot_only='0', source_filter='',
                udp_map='', ts_correct='1', burst_sep='0.0', sburst='1', eburst='0'):
    "Extract RTT of flows with SPP"

    ifile_ext = '.dmp.gz'
    ofile_ext = '.rtts'

    already_done = {}
    out_files = {}
    out_groups = {}
    udp_reverse_map = {}

    test_id_arr = test_id.split(';')
    if len(test_id_arr) == 0 or test_id_arr[0] == '':
        abort('Must specify test_id parameter')

    # Initialise source filter data structure
    sfil = SourceFilter(source_filter)

    #local('which spp')

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
        tcpdump_files = get_testid_file_list('', test_id,
                                ifile_ext, 
                                'grep -v "router.dmp.gz" | grep -v "ctl.dmp.gz"')

        for tcpdump_file in tcpdump_files:
            # get input directory name and create result directory if necessary
            out_dirname = get_out_dir(tcpdump_file, out_dir) 
            dir_name = os.path.dirname(tcpdump_file)

            # get unique flows
            flows = lookup_flow_cache(tcpdump_file)
            if flows == None:
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

                append_flow_cache(tcpdump_file, flows)

            # since client sends first packet to server, client-to-server flows
            # will always be first

            for flow in flows:

                src, src_port, dst, dst_port, proto = flow.split(',')

                # get external and internal addresses
                src, src_internal = get_address_pair_analysis(test_id, src, do_abort='0')
                dst, dst_internal = get_address_pair_analysis(test_id, dst, do_abort='0')

                if src == '' or dst == '':
                    continue

                # flow name
                name = src_internal + '_' + src_port + \
                    '_' + dst_internal + '_' + dst_port
                rev_name = dst_internal + '_' + dst_port + \
                    '_' + src_internal + '_' + src_port
                # test id plus flow name
                if len(test_id_arr) > 1:
                    long_name = test_id + '_' + name
                    long_rev_name = test_id + '_' + rev_name
                else:
                    long_name = name
                    long_rev_name = rev_name

                if long_name not in already_done and long_rev_name not in already_done:

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
                        filter1 = '(src host ' + src_internal + ' && src port ' + src_port + \
                                  ') || (' + \
                                  'dst host ' + src_internal + ' && dst port ' + src_port + ')'
                        filter2 = filter1 
                    else:
                        entry = udp_reverse_map.get(
                            src_internal + ',' + src_port, '')
                        if entry != '':
                            src2_internal, src2_port = entry.split(',')
                            name = src_internal + '_' + src_port + \
                                '_' + src2_internal + '_' + src2_port
                            rev_name = src2_internal + '_' + src2_port + \
                                '_' + src_internal + '_' + src_port
                            filter1 = '(src host ' + src_internal + ' && src port ' + src_port + \
                                ') || ( ' + \
                                'src host ' + src2_internal + ' && src port ' + src2_port + ')'
                            filter2 = filter1 
                            if rev_name in out_files:
                                continue
                        else:
                            warn('No entry in udp_map for %s:%s' % (src_internal, src_port)) 
                            continue

                    out1 = out_dirname + test_id + \
                        '_' + src + '_filtered_' + name + '_ref.dmp'
                    out2 = out_dirname + test_id + \
                        '_' + dst + '_filtered_' + name + '_mon.dmp'
                    out_rtt = out_dirname + test_id + '_' + name + ofile_ext 
                    rev_out_rtt = out_dirname + test_id + '_' + rev_name + ofile_ext 

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

                    already_done[long_name] = 1
                    already_done[long_rev_name] = 1

                    if sfil.is_in(name):
                        if ts_correct == '1':
                            out_rtt = adjust_timestamps(test_id, out_rtt, src, ' ', out_dir)

                        (out_files, 
                         out_groups) = select_bursts(long_name, group, out_rtt, burst_sep, sburst, eburst,
                                      out_files, out_groups)

                    if sfil.is_in(rev_name):
                        if ts_correct == '1':
                            rev_out_rtt = adjust_timestamps(test_id, rev_out_rtt, dst, ' ',
                                          out_dir)

                        (out_files, 
                         out_groups) = select_bursts(long_rev_name, group, rev_out_rtt, burst_sep, sburst, 
                                      eburst, out_files, out_groups)

        group += 1

    return (test_id_arr, out_files, out_groups)


## Extract RTT for flows using SPP
## SEE _extract_rtt()
@task
def extract_rtt(test_id='', out_dir='', replot_only='0', source_filter='',
                udp_map='', ts_correct='1', burst_sep='0.0', sburst='1', eburst='0'):
    "Extract RTT of flows with SPP"

    _extract_rtt(test_id, out_dir, replot_only, source_filter,
                udp_map, ts_correct, burst_sep, sburst, eburst)

    # done
    puts('\n[MAIN] COMPLETED extracting RTTs %s \n' % test_id)


## Plot RTT for flows using SPP
#  @param test_id Test ID prefix of experiment to analyse
#  @param out_dir Output directory for results
#  @param replot_only Don't extract data again, just redo the plot
#  @param source_filter Filter on specific sources
#  @param min_values Minimum number of data points in file, if fewer points
#                    the file is ignored
#  @param udp_map Map that defines unidirectional UDP flows to combine. Format:
#                 <ip1>,<port1>:<ip2>,<port2>[;<ip3>,<port3>:<ip4>,<port4>]*
#  @param omit_const '0' don't omit anything,
#                    '1' omit any series that are 100% constant
#                       (e.g. because there was no data flow)
#  @param ymin Minimum value on y-axis
#  @param ymax Maximum value on y-axis
#  @param lnames Semicolon-separated list of legend names
#  @param stime Start time of plot window in seconds
#               (by default 0.0 = start of experiment)
#  @param etime End time of plot window in seconds
#               (by default 0.0 = end of experiment)
#  @param out_name Name prefix for resulting pdf file
#  @param pdf_dir Output directory for pdf files (graphs), if not specified it is
#                 the same as out_dir
#  @param ts_correct '0' use timestamps as they are (default)
#                    '1' correct timestamps based on clock offsets estimated
#                        from broadcast pings
#  @param plot_params Set env parameters for plotting
#  @param plot_script Specify the script used for plotting, must specify full path
#  @param burst_sep '0' plot seq numbers as they come, relative to 1st seq number
#                 > '0' plot seq numbers relative to 1st seq number after gaps
#                    of more than burst_sep milliseconds (e.g. incast query/response bursts)
#                 < 0,  plot seq numbers relative to 1st seq number after each abs(burst_sep)
#                    seconds since the first burst @ t = 0 (e.g. incast query/response bursts)
#   @param sburst Start plotting with burst N (bursts are numbered from 1)
#   @param eburst End plotting with burst N (bursts are numbered from 1)
@task
def analyse_rtt(test_id='', out_dir='', replot_only='0', source_filter='',
                min_values='3', udp_map='', omit_const='0', ymin='0', ymax='0',
                lnames='', stime='0.0', etime='0.0', out_name='', pdf_dir='',
                ts_correct='1', plot_params='', plot_script='', burst_sep='0.0',
                sburst='1', eburst='0'):
    "Plot RTT of flows with SPP"

    (test_id_arr, 
     out_files, 
     out_groups) = _extract_rtt(test_id, out_dir, replot_only, 
                                 source_filter, udp_map, ts_correct,
                                 burst_sep, sburst, eburst)

    (out_files, out_groups) = filter_min_values(out_files, out_groups, min_values)
    out_name = get_out_name(test_id_arr, out_name)
 
    burst_sep = float(burst_sep)
    if burst_sep == 0.0:
        plot_time_series(out_name, out_files, 'SPP RTT (ms)', 2, 1000.0, 'pdf',
                     out_name + '_spprtt', pdf_dir=pdf_dir, omit_const=omit_const,
                     ymin=float(ymin), ymax=float(ymax), lnames=lnames,
                     stime=stime, etime=etime, groups=out_groups, plot_params=plot_params,
                     plot_script=plot_script, source_filter=source_filter)
    else:
        # Each trial has multiple files containing data from separate bursts detected within the trial
        plot_incast_ACK_series(out_name, out_files, 'SPP RTT (ms)', 2, 1000.0, 'pdf',
                        out_name + '_spprtt', pdf_dir=pdf_dir, aggr='',
                        omit_const=omit_const, ymin=float(ymin), ymax=float(ymax),
                        lnames=lnames, stime=stime, etime=etime, groups=out_groups, burst_sep=burst_sep,
                        sburst=int(sburst), plot_params=plot_params, plot_script=plot_script,
                        source_filter=source_filter)


    # done
    puts('\n[MAIN] COMPLETED plotting RTTs %s \n' % out_name)


## Extract data from siftr files
#  @param test_id Test ID prefix of experiment to analyse
#  @param out_dir Output directory for results
#  @param replot_only Don't extract data again, just redo the plot
#  @param source_filter Filter on specific sources
#  @param attributes Comma-separated list of attributes to extract from siftr file,
#                    start index is 1
#                    (refer to siftr documentation for column description)
#  @param out_file_ext Extension for the output file containing the extracted data
#  @param post_proc Name of function used for post-processing the extracted data
#  @param ts_correct '0' use timestamps as they are (default)
#                    '1' correct timestamps based on clock offsets estimated
#                        from broadcast pings
#  @param io_filter  'i' only use statistics from incoming packets
#                    'o' only use statistics from outgoing packets
#                    'io' use statistics from incooming and outgoing packets
#  @return Map of flow names to interim data file names and 
#          map of file names and group IDs
def extract_siftr(test_id='', out_dir='', replot_only='0', source_filter='',
                  attributes='', out_file_ext='', post_proc=None, 
                  ts_correct='1', io_filter='o'):

    out_files = {}
    out_groups = {}

    if io_filter != 'i' and io_filter != 'o' and io_filter != 'io':
        abort('Invalid parameter value for io_filter')
    if io_filter == 'io':
        io_filter = '(i|o)'

    test_id_arr = test_id.split(';')

    # Initialise source filter data structure
    sfil = SourceFilter(source_filter)

    group = 1
    for test_id in test_id_arr:

        # first process siftr files
        siftr_files = get_testid_file_list('', test_id,
                                           'siftr.log.gz', '',  no_abort=True)

        for siftr_file in siftr_files:
            # get input directory name and create result directory if necessary
            out_dirname = get_out_dir(siftr_file, out_dir)

            if replot_only == '0':
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
            flows = lookup_flow_cache(siftr_file)
            if flows == None:
                flows = _list(
                    local(
                        'zcat %s | grep -v enable | head -%s | '
                        'egrep "^%s" | '
                        'cut -d\',\' -f 4,5,6,7 | LC_ALL=C sort -u' %
                        (siftr_file, rows, io_filter), capture=True))

                append_flow_cache(siftr_file, flows)

            for flow in flows:

                src, src_port, dst, dst_port = flow.split(',')

                # get external and internal addresses
                src, src_internal = get_address_pair_analysis(test_id, src, do_abort='0')
                dst, dst_internal = get_address_pair_analysis(test_id, dst, do_abort='0')

                if src == '' or dst == '':
                    continue

                flow_name = flow.replace(',', '_')
                # test id plus flow name
                if len(test_id_arr) > 1:
                    long_flow_name = test_id + '_' + flow_name
                else:
                    long_flow_name = flow_name
                out = out_dirname + test_id + '_' + flow_name + '_siftr.' + out_file_ext
                if replot_only == '0' or not os.path.isfile(out) :
                    local(
                        'zcat %s | grep -v enable | head -%s | '
                        'egrep "^%s" | '
                        'cut -d\',\' -f 3,4,5,6,7,%s | '
                        'grep "%s" | cut -d\',\' -f 1,6- > %s' %
                        (siftr_file, rows, io_filter, attributes, flow, out))

                    if post_proc is not None:
                        post_proc(siftr_file, out)

                if sfil.is_in(flow_name):
                    if ts_correct == '1':
                        host = local(
                            'echo %s | sed "s/.*_\([a-z0-9\.]*\)_siftr.log.gz/\\1/"' %
                            siftr_file,
                            capture=True)
                        out = adjust_timestamps(test_id, out, host, ',', out_dir)

                    out_files[long_flow_name] = out
                    out_groups[out] = group

        group += 1

    return (out_files, out_groups)


## Guess web10g version (based on first file only!)
#  @param test_id Test ID prefix of experiment to analyse
def guess_version_web10g(test_id=''):

    test_id_arr = test_id.split(';')
    test_id = test_id_arr[0]
    web10g_files = get_testid_file_list('', test_id,
                                        'web10g.log.gz', '', no_abort=True)

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


## Extract data from web10g files
#  @param test_id Test ID prefix of experiment to analyse
#  @param out_dir Output directory for results
#  @param replot_only Don't extract data again, just redo the plot
#  @param source_filter Filter on specific sources
#  @param attributes Comma-separated list of attributes to extract from web10g file,
#                    start index is 1
#                    (refer to web10g documentation for column description)
#  @param out_file_ext Extension for the output file containing the extracted data
#  @param post_proc Name of function used for post-processing the extracted data
#  @param ts_correct '0' use timestamps as they are (default)
#                    '1' correct timestamps based on clock offsets estimated
#                        from broadcast pings
#  @return Map of flow names to interim data file names and 
#          map of file names and group IDs
def extract_web10g(test_id='', out_dir='', replot_only='0', source_filter='',
                   attributes='', out_file_ext='', post_proc=None,
                   ts_correct='1'):

    out_files = {}
    out_groups = {}

    test_id_arr = test_id.split(';')

    # Initialise source filter data structure
    sfil = SourceFilter(source_filter)

    group = 1
    for test_id in test_id_arr:

        # second process web10g files
        web10g_files = get_testid_file_list('', test_id,
                                            'web10g.log.gz', '', no_abort=True)

        for web10g_file in web10g_files:
            # get input directory name and create result directory if necessary
            out_dirname = get_out_dir(web10g_file, out_dir)

            # check for errors, unless we replot
            # make sure we have exit status 0 for this, hence the final echo
            if replot_only == '0':
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
            flows = lookup_flow_cache(web10g_file)
            if flows == None:
                flows = _list(
                    local(
                        'zcat %s | egrep -v "[a-z]+" | sed -n \'$!p\' | '
                        'cut -d\',\' -f 3,4,5,6 | LC_ALL=C sort -u' %
                        (web10g_file),
                        capture=True))

                append_flow_cache(web10g_file, flows)

            for flow in flows:

                src, src_port, dst, dst_port = flow.split(',')

                # get external aNd internal addresses
                src, src_internal = get_address_pair_analysis(test_id, src, do_abort='0')
                dst, dst_internal = get_address_pair_analysis(test_id, dst, do_abort='0')

                if src == '' or dst == '':
                    continue

                flow_name = flow.replace(',', '_')
                # test id plus flow name
                if len(test_id_arr) > 1:
                    long_flow_name = test_id + '_' + flow_name
                else:
                    long_flow_name = flow_name
                out = out_dirname + test_id + '_' + flow_name + '_web10g.' + out_file_ext
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

                if sfil.is_in(flow_name):
		    if ts_correct == '1':
                        host = local(
                            'echo %s | sed "s/.*_\([a-z0-9\.]*\)_web10g.log.gz/\\1/"' %
                            web10g_file,
                            capture=True)

                        out = adjust_timestamps(test_id, out, host, ',', out_dir) 

                    out_files[long_flow_name] = out
                    out_groups[out] = group

        group += 1

    return (out_files, out_groups)


## SIFTR prints out very high cwnd (max cwnd?) values for some tcp algorithms
## at the start, remove them
#  @param siftr_file Data extracted from siftr log
#  @param out_file File name for post processed data
def post_proc_siftr_cwnd(siftr_file, out_file):
    tmp_file = local('mktemp "tmp.XXXXXXXXXX"', capture=True)
    local(
        'cat %s | sed -e "1,2d\" > %s && mv %s %s' %
        (out_file, tmp_file, tmp_file, out_file))


## Extract cwnd over time
## The extracted files have an extension of .cwnd. The format is CSV with the
## columns:
## 1. Timestamp RTT measured (seconds.microseconds)
## 2. CWND 
#  @param test_id Test ID prefix of experiment to analyse
#  @param out_dir Output directory for results
#  @param replot_only Don't extract data again that is extracted already
#  @param source_filter Filter on specific sources
#  @param ts_correct '0' use timestamps as they are (default)
#                    '1' correct timestamps based on clock offsets estimated
#                        from broadcast pings
#  @param io_filter  'i' only use statistics from incoming packets
#                    'o' only use statistics from outgoing packets
#                    'io' use statistics from incooming and outgoing packets
#                    (only effective for SIFTR files)
#  @return Test ID list, map of flow names to interim data file names and 
#          map of file names and group IDs
def _extract_cwnd(test_id='', out_dir='', replot_only='0', source_filter='',
                 ts_correct='1', io_filter='o'):
    "Extract CWND over time"

    test_id_arr = test_id.split(';')
    if len(test_id_arr) == 0 or test_id_arr[0] == '':
        abort('Must specify test_id parameter')

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


## Extract cwnd over time
## SEE _extract_cwnd
@task
def extract_cwnd(test_id='', out_dir='', replot_only='0', source_filter='',
                 ts_correct='1', io_filter='o'):
    "Extract CWND over time"

    _extract_cwnd(test_id, out_dir, replot_only, source_filter, ts_correct,
                  io_filter)

    # done
    puts('\n[MAIN] COMPLETED extracting CWND %s \n' % test_id)


## Analyse cwnd over time
#  @param test_id Test ID prefix of experiment to analyse
#  @param out_dir Output directory for results
#  @param replot_only Don't extract data again, just redo the plot
#  @param source_filter Filter on specific sources
#  @param min_values Minimum number of data points in file, if fewer points
#                    the file is ignored
#  @param omit_const '0' don't omit anything,
#                    '1' omit any series that are 100% constant
#                        (e.g. because there was no data flow)
#  @param ymin Minimum value on y-axis
#  @param ymax Maximum value on y-axis
#  @param lnames Semicolon-separated list of legend names
#  @param stime Start time of plot window in seconds
#               (by default 0.0 = start of experiment)
#  @param etime End time of plot window in seconds
#               (by default 0.0 = end of experiment)
#  @param out_name Name prefix for resulting pdf file
#  @param pdf_dir Output directory for pdf files (graphs), if not specified it is
#                 the same as out_dir
#  @param ts_correct '0' use timestamps as they are (default)
#                    '1' correct timestamps based on clock offsets estimated
#                        from broadcast pings
#  @param io_filter  'i' only use statistics from incoming packets
#                    'o' only use statistics from outgoing packets
#                    'io' use statistics from incooming and outgoing packets
#                    (only effective for SIFTR files)
#  @param plot_params Set env parameters for plotting
#  @param plot_script specify the script used for plotting, must specify full path
@task
def analyse_cwnd(test_id='', out_dir='', replot_only='0', source_filter='',
                 min_values='3', omit_const='0', ymin='0', ymax='0', lnames='',
                 stime='0.0', etime='0.0', out_name='', pdf_dir='', ts_correct='1',
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
                         plot_params=plot_params, plot_script=plot_script,
                         source_filter=source_filter)

    # done
    puts('\n[MAIN] COMPLETED plotting CWND %s \n' % out_name)


## SIFTR values are in units of tcp_rtt_scale*hz, so we need to convert to milliseconds
#  @param siftr_file Data extracted from siftr log
#  @param out_file File name for post processed data
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


## Extract RTT over time estimated by TCP 
## The extracted files have an extension of .tcp_rtt. The format is CSV with the
## columns:
## 1. Timestamp RTT measured (seconds.microseconds)
## 2. Smoothed RTT
## 3. Sample/Unsmoothed RTT 
#  @param test_id Test ID prefix of experiment to analyse
#  @param out_dir Output directory for results
#  @param replot_only Don't extract data again that is extracted already
#  @param source_filter Filter on specific sources
#  @param ts_correct '0' use timestamps as they are (default)
#                    '1' correct timestamps based on clock offsets estimated
#                        from broadcast pings
#  @param io_filter  'i' only use statistics from incoming packets
#                    'o' only use statistics from outgoing packets
#                    'io' use statistics from incooming and outgoing packets
#                    (only effective for SIFTR files)
#  @param web10g_version web10g version string (default is 2.0.9) 
#  @return Test ID list, map of flow names to interim data file names and 
#          map of file names and group IDs
def _extract_tcp_rtt(test_id='', out_dir='', replot_only='0', source_filter='',
                     ts_correct='1', io_filter='o', web10g_version='2.0.9'):
    "Extract RTT as seen by TCP (smoothed RTT)"

    test_id_arr = test_id.split(';')
    if len(test_id_arr) == 0 or test_id_arr[0] == '':
        abort('Must specify test_id parameter')

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


## Extract RTT over time estimated by TCP 
## SEE _extract_tcp_rtt
@task
def extract_tcp_rtt(test_id='', out_dir='', replot_only='0', source_filter='',
                     ts_correct='1', io_filter='o', web10g_version='2.0.9'):
    "Extract RTT as seen by TCP (smoothed RTT)"

    _extract_tcp_rtt(test_id, out_dir, replot_only, source_filter, 
                     ts_correct, io_filter, web10g_version)

    # done
    puts('\n[MAIN] COMPLETED extracting TCP RTTs %s \n' % test_id)


## Plot RTT estimated by TCP over time 
#  @param test_id Test ID prefix of experiment to analyse
#  @param out_dir Output directory for results
#  @param replot_only Don't extract data again, just redo the plot
#  @param source_filter Filter on specific sources
#  @param min_values Datasets with fewer values won't be plotted
#  @param smoothed '0' plot non-smooth RTT (enhanced RTT in case of FreeBSD),
#                  '1' plot smoothed RTT estimates (non enhanced RTT in case of FreeBSD)
#  @param omit_const '0' don't omit anything,
#                    '1' omit any series that are 100% constant
#                       (e.g. because there was no data flow)
#  @param ymin Minimum value on y-axis
#  @param ymax Maximum value on y-axis
#  @param lnames Semicolon-separated list of legend names
#  @param stime Start time of plot window in seconds
#               (by default 0.0 = start of experiment)
#  @param etime End time of plot window in seconds
#               (by default 0.0 = end of experiment)
#  @param out_name Name prefix for resulting pdf file
#  @param pdf_dir Output directory for pdf files (graphs), if not specified it is
#                 the same as out_dir
#  @param ts_correct '0' use timestamps as they are (default)
#                    '1' correct timestamps based on clock offsets estimated
#                        from broadcast pings
#  @param io_filter 'i' only use statistics from incoming packets
#                   'o' only use statistics from outgoing packets
#                   'io' use statistics from incooming and outgoing packets
#                   (only effective for SIFTR files)
#  @param web10g_version web10g version string (default is 2.0.9) 
#  @param plot_params Set env parameters for plotting
#  @param plot_script Specify the script used for plotting, must specify full path
@task
def analyse_tcp_rtt(test_id='', out_dir='', replot_only='0', source_filter='',
                    min_values='3', smoothed='1', omit_const='0', ymin='0', ymax='0',
                    lnames='', stime='0.0', etime='0.0', out_name='', pdf_dir='',
                    ts_correct='1', io_filter='o', web10g_version='2.0.9',
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
                             plot_params=plot_params, plot_script=plot_script,
                             source_filter=source_filter)
        else:
            plot_time_series(out_name, out_files, 'TCP RTT (ms)', 3, 1.0, 'pdf',
                             out_name + '_tcprtt', pdf_dir=pdf_dir, sep=",",
                             omit_const=omit_const, ymin=float(ymin),
                             ymax=float(ymax), lnames=lnames, stime=stime,
                             etime=etime, groups=out_groups, 
                             plot_params=plot_params, plot_script=plot_script,
                             source_filter=source_filter)

    # done
    puts('\n[MAIN] COMPLETED plotting TCP RTTs %s \n' % out_name)


## Extract some TCP statistic (based on siftr/web10g output)
## The extracted files have an extension of .tcpstat_<num>, where <num> is the index
## of the statistic. The format is CSV with the columns:
## 1. Timestamp RTT measured (seconds.microseconds)
## 2. TCP statistic chosen 
#  @param test_id Test ID prefix of experiment to analyse
#  @param out_dir Output directory for results
#  @param replot_only Don't extract data again that is already extracted
#  @param source_filter Filter on specific sources
#  @param siftr_index Integer number of the column in siftr log files
#                     (note if you have sitfr and web10g logs, you must also
#                     specify web10g_index) (default = 9, CWND)
#  @param web10g_index Integer number of the column in web10g log files (note if
#                      you have web10g and siftr logs, you must also specify siftr_index)
#                      (default = 26, CWND)
#                      example: analyse_tcp_stat(siftr_index=17,web10_index=23,...)
#                      would plot smoothed RTT estimates.
#  @param ts_correct '0' use timestamps as they are (default)
#                    '1' correct timestamps based on clock offsets estimated
#                        from broadcast pings
#  @param io_filter  'i' only use statistics from incoming packets
#                    'o' only use statistics from outgoing packets
#                    'io' use statistics from incooming and outgoing packets
#                    (only effective for SIFTR files)
#  @return Test ID list, map of flow names to interim data file names and 
#          map of file names and group IDs
def _extract_tcp_stat(test_id='', out_dir='', replot_only='0', source_filter='',
                     siftr_index='9', web10g_index='26', ts_correct='1',
                     io_filter='o'):
    "Extract TCP Statistic"

    test_id_arr = test_id.split(';')
    if len(test_id_arr) == 0 or test_id_arr[0] == '':
        abort('Must specify test_id parameter')

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


## Extract some TCP statistic (based on siftr/web10g output)
## SEE _extract_tcp_stat
@task
def extract_tcp_stat(test_id='', out_dir='', replot_only='0', source_filter='',
                     siftr_index='9', web10g_index='26', ts_correct='1',
                     io_filter='o'):
    "Extract TCP Statistic"

    _extract_tcp_stat(test_id, out_dir, replot_only, source_filter,
                      siftr_index, web10g_index, ts_correct, io_filter)

    # done
    puts('\n[MAIN] COMPLETED extracting TCP Statistic %s \n' % test_id)


## Plot some TCP statistic (based on siftr/web10g output)
#  @param test_id Test ID prefix of experiment to analyse
#  @param out_dir Output directory for results
#  @param replot_only Don't extract data again, just redo the plot
#  @param source_filter Filter on specific sources
#  @param min_values Minimum number of data points in file, if fewer points
#                    the file is ignored
#  @param omit_const '0' don't omit anything,
#                    '1' omit any Series that are 100% constant
#                        (e.g. because there was no data flow)
#  @param siftr_index Integer number of the column in siftr log files
#                     (note if you have sitfr and web10g logs, you must also
#                     specify web10g_index) (default = 9, CWND)
#  @param web10g_index Integer number of the column in web10g log files (note if
#                      you have web10g and siftr logs, you must also specify siftr_index)
#                      (default = 26, CWND)
#		       example: analyse_tcp_stat(siftr_index=17,web10_index=23,...)
#                      would plot smoothed RTT estimates.
#  @param ylabel Label for y-axis in plot
#  @param yscaler Scaler for y-axis values (must be a floating point number)
#  @param ymin Minimum value on y-axis
#  @param ymax Maximum value on y-axis
#  @param lnames Semicolon-separated list of legend names
#  @param stime Start time of plot window in seconds (by default 0.0 = start of experiment)
#  @param etime End time of plot window in seconds (by default 0.0 = end of experiment)
#  @param out_name Name prefix for resulting pdf file
#  @param pdf_dir Output directory for pdf files (graphs), if not specified it is
#                 the same as out_dir
#  @param ts_correct '0' use timestamps as they are (default)
#                    '1' correct timestamps based on clock offsets estimated
#                        from broadcast pings
#  @param io_filter  'i' only use statistics from incoming packets
#                    'o' only use statistics from outgoing packets
#                    'io' use statistics from incooming and outgoing packets
#                    (only effective for SIFTR files)
#  @param plot_params Set env parameters for plotting
#  @param plot_script Specify the script used for plotting, must specify full path
@task
def analyse_tcp_stat(test_id='', out_dir='', replot_only='0', source_filter='',
                     min_values='3', omit_const='0', siftr_index='9', web10g_index='26',
                     ylabel='', yscaler='1.0', ymin='0', ymax='0', lnames='',
                     stime='0.0', etime='0.0', out_name='', pdf_dir='', ts_correct='1',
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
                         plot_script=plot_script, source_filter=source_filter)

    # done
    puts('\n[MAIN] COMPLETED plotting TCP Statistic %s \n' % out_name)


## Extract packet sizes. Plot function computes throughput based on the packet sizes.
## The extracted files have an extension of .psiz. The format is CSV with the
## columns:
## 1. Timestamp RTT measured (seconds.microseconds)
## 2. Packet size (bytes) 
#  @param test_id Test ID prefix of experiment to analyse
#  @param out_dir Output directory for results
#  @param replot_only Don't extract data again that is already extracted 
#  @param source_filter Filter on specific sources
#  @param link_len '0' throughput based on IP length (default),
#                  '1' throughput based on link-layer length
#  @param ts_correct '0' use timestamps as they are (default)
#                    '1' correct timestamps based on clock offsets estimated
#                        from broadcast pings
#  @return Test ID list, map of flow names to interim data file names and 
#          map of file names and group IDs
def _extract_pktsizes(test_id='', out_dir='', replot_only='0', source_filter='',
                       link_len='0', ts_correct='1', total_per_experiment='0'):
    "Extract throughput for generated traffic flows"

    ifile_ext = '.dmp.gz'
    ofile_ext = '.psiz'

    already_done = {}
    out_files = {}
    out_groups = {}

    test_id_arr = test_id.split(';')
    if len(test_id_arr) == 0 or test_id_arr[0] == '':
        abort('Must specify test_id parameter')

    # Initialise source filter data structure
    sfil = SourceFilter(source_filter)

    group = 1
    for test_id in test_id_arr:

        # first process tcpdump files (ignore router and ctl interface tcpdumps)
        tcpdump_files = get_testid_file_list('', test_id,
                                       ifile_ext,
                                       'grep -v "router.dmp.gz" | grep -v "ctl.dmp.gz"')

        for tcpdump_file in tcpdump_files:
            # get input directory name and create result directory if necessary
            out_dirname = get_out_dir(tcpdump_file, out_dir)
            dir_name = os.path.dirname(tcpdump_file)

            # unique flows
            flows = lookup_flow_cache(tcpdump_file)
            if flows == None:
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
             
                append_flow_cache(tcpdump_file, flows)

            # since client sends first packet to server, client-to-server flows
            # will always be first

            for flow in flows:

                src, src_port, dst, dst_port, proto = flow.split(',')

                # get external and internal addresses
                src, src_internal = get_address_pair_analysis(test_id, src, do_abort='0')
                dst, dst_internal = get_address_pair_analysis(test_id, dst, do_abort='0')

                if src == '' or dst == '':
                    continue

                # flow name
                name = src_internal + '_' + src_port + \
                    '_' + dst_internal + '_' + dst_port
                rev_name = dst_internal + '_' + dst_port + \
                    '_' + src_internal + '_' + src_port 
                # test id plus flow name
                if len(test_id_arr) > 1:
                    long_name = test_id + '_' + name
                    long_rev_name = test_id + '_' + rev_name
                else:
                    long_name = name
                    long_rev_name = rev_name

                # the two dump files
                dump1 = dir_name + '/' + test_id + '_' + src + ifile_ext 
                dump2 = dir_name + '/' + test_id + '_' + dst + ifile_ext 

                # tcpdump filters and output file names
                filter1 = 'src host ' + src_internal + ' && src port ' + src_port + \
                    ' && dst host ' + dst_internal + ' && dst port ' + dst_port
                filter2 = 'src host ' + dst_internal + ' && src port ' + dst_port + \
                    ' && dst host ' + src_internal + ' && dst port ' + src_port
                out_size1 = out_dirname + test_id + '_' + name + ofile_ext 
                out_size2 = out_dirname + test_id + '_' + rev_name + ofile_ext 

                if long_name not in already_done and long_rev_name not in already_done:
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
   
                    already_done[long_name] = 1
                    already_done[long_rev_name] = 1

                    if sfil.is_in(name):
                        if ts_correct == '1':
                            out_size1 = adjust_timestamps(test_id, out_size1, dst, ' ', out_dir)
                        out_files[long_name] = out_size1
                        out_groups[out_size1] = group

                    if sfil.is_in(rev_name):
                        if ts_correct == '1':
                            out_size2 = adjust_timestamps(test_id, out_size2, src, ' ', out_dir)
                        out_files[long_rev_name] = out_size2
                        out_groups[out_size2] = group

        # if desired compute aggregate packet kength data for each experiment
        if total_per_experiment == '1':

            files_list = ''
            for name in out_files:
                if out_groups[out_files[name]] == group:
                    files_list += out_files[name] + ' '

            out_size1 = out_dirname + test_id + '_total' + ofile_ext
            # cat everything together and sort by timestamp
            local('cat %s | sort -k 1,1 > %s' % (files_list, out_size1))

            # replace all files for separate flows with total
            delete_list = []
            for name in out_files:
                if out_groups[out_files[name]] == group:
                    delete_list.append(name)
  
            for d in delete_list:
                    del out_groups[out_files[d]]
                    del out_files[d]

            name = test_id 
            out_files[name] = out_size1
            out_groups[out_size1] = group

        group += 1

    return (test_id_arr, out_files, out_groups)


## Extract packet sizes. The plot function computes throughput based on the packet sizes.
## SEE _extract_pktsizes
@task
def extract_pktsizes(test_id='', out_dir='', replot_only='0', source_filter='',
                       link_len='0', ts_correct='1', total_per_experiment='0'):
    "Extract throughput for generated traffic flows"

    _extract_pktsizes(test_id, out_dir, replot_only, source_filter, link_len,
                        ts_correct, total_per_experiment)
    # done
    puts('\n[MAIN] COMPLETED extracting packet sizes %s \n' % test_id)


## Plot throughput
#  @param test_id Test ID prefix of experiment to analyse
#  @param out_dir Output directory for results
#  @param replot_only Don't extract data again, just redo the plot
#  @param source_filter Filter on specific sources
#  @param min_values Minimum number of data points in file, if fewer points
#                    the file is ignored
#  @param omit_const '0' don't omit anything,
#                    '1' omit any series that are 100% constant
#                        (e.g. because there was no data flow)
#  @param ymin Minimum value on y-axis
#  @param ymax Maximum value on y-axis
#  @param lnames Semicolon-separated list of legend names
#  @param link_len '0' throughput based on IP length (default),
#                  '1' throughput based on link-layer length
#  @param stime Start time of plot window in seconds
#               (by default 0.0 = start of experiment)
#  @param etime End time of plot window in seconds (by default 0.0 = end of experiment)
#  @param out_name Name prefix for resulting pdf file
#  @param pdf_dir Output directory for pdf files (graphs), if not specified it is
#                 the same as out_dir
#  @param ts_correct '0' use timestamps as they are (default)
#                    '1' correct timestamps based on clock offsets estimated
#                        from broadcast pings
#  @param plot_params: set env parameters for plotting
#  @param plot_script: specify the script used for plotting, must specify full path
#  @param total_per_experiment '0' plot per-flow throughput (default)
#                              '1' plot total throughput
@task
def analyse_throughput(test_id='', out_dir='', replot_only='0', source_filter='',
                       min_values='3', omit_const='0', ymin='0', ymax='0', lnames='',
                       link_len='0', stime='0.0', etime='0.0', out_name='',
                       pdf_dir='', ts_correct='1', plot_params='', plot_script='',
                       total_per_experiment='0'):
    "Plot throughput for generated traffic flows"

    (test_id_arr,
     out_files, 
     out_groups) =_extract_pktsizes(test_id, out_dir, replot_only, 
                              source_filter, link_len, ts_correct,
                              total_per_experiment)

    if total_per_experiment == '0':
        sort_flowkey='1'
    else:
        sort_flowkey='0'

    (out_files, out_groups) = filter_min_values(out_files, out_groups, min_values)
    out_name = get_out_name(test_id_arr, out_name)
    plot_time_series(out_name, out_files, 'Throughput (kbps)', 2, 0.008, 'pdf',
                     out_name + '_throughput', pdf_dir=pdf_dir, aggr='1',
                     omit_const=omit_const, ymin=float(ymin), ymax=float(ymax),
                     lnames=lnames, stime=stime, etime=etime, groups=out_groups,
                     sort_flowkey=sort_flowkey,
                     plot_params=plot_params, plot_script=plot_script,
                     source_filter=source_filter)

    # done
    puts('\n[MAIN] COMPLETED plotting throughput %s \n' % out_name)


## Get list of experiment IDs
#  @param exp_list List of all test IDs
#  @param test_id Test ID prefix of experiment to analyse 
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


## Do all extraction 
#  @param exp_list List of all test IDs
#  @param test_id Test ID prefix of experiment to analyse
#  @param out_dir Output directory for result files
#  @param replot_only Don't extract data again, just redo the plot
#  @param source_filter Filter on specific sources
#  @param resume_id Resume analysis with this test_id (ignore all test_ids before this),
#                   only effective if test_id is not specified
#  @param link_len '0' throughput based on IP length (default),
#                  '1' throughput based on link-layer length
#  @param ts_correct '0' use timestamps as they are (default)
#                    '1' correct timestamps based on clock offsets estimated
#                        from broadcast pings
#  @param io_filter 'i' only use statistics from incoming packets
#                   'o' only use statistics from outgoing packets
#                   'io' use statistics from incooming and outgoing packets
#                   (only effective for SIFTR files)
#  @param web10g_version web10g version string (default is 2.0.9)
@task
def extract_all(exp_list='experiments_completed.txt', test_id='', out_dir='',
                replot_only='0', source_filter='', resume_id='', 
                link_len='0', ts_correct='1', io_filter='o', web10g_version='2.0.9'):
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
            execute(extract_pktsizes, test_id, out_dir, replot_only, source_filter,
                    link_len=link_len, ts_correct=ts_correct)


## Do all analysis
#  @param exp_list List of all test IDs
#  @param test_id Test ID prefix of experiment to analyse
#  @param out_dir Output directory for result files
#  @param replot_only Don't extract data again, just redo the plot
#  @param source_filter Filter on specific sources
#  @param min_values Ignore flows with less output values 
#  @param omit_const '0' don't omit anything, ]
#                    '1' omit any series that are 100% constant
#                    (e.g. because there was no data flow)
#  @param smoothed '0' plot non-smooth RTT (enhanced RTT in case of FreeBSD),
#                  '1' plot smoothed RTT estimates (non enhanced RTT in case of FreeBSD)
#  @param resume_id Resume analysis with this test_id (ignore all test_ids before this),
#                   only effective if test_id is not specified
#  @param lnames Semicolon-separated list of legend names
#  @param link_len '0' throughput based on IP length (default),
#                  '1' throughput based on link-layer length
#  @param stime Start time of plot window in seconds
#               (by default 0.0 = start of experiment)
#  @param etime End time of plot window in seconds
#               (by default 0.0 = end of experiment)
#  @param out_name Name prefix for resulting pdf files
#  @param pdf_dir Output directory for pdf files (graphs), if not specified it is
#                 the same as out_dir
#  @param ts_correct '0' use timestamps as they are (default)
#                    '1' correct timestamps based on clock offsets estimated
#                        from broadcast pings
#  @param io_filter  'i' only use statistics from incoming packets
#                    'o' only use statistics from outgoing packets
#                    'io' use statistics from incooming and outgoing packets
#                    (only effective for SIFTR files)
#  @param web10g_version web10g version string (default is 2.0.9)
#  @param plot_params Parameters passed to plot function via environment variables
#  @param plot_script Specify the script used for plotting, must specify full path
@task
def analyse_all(exp_list='experiments_completed.txt', test_id='', out_dir='',
                replot_only='0', source_filter='', min_values='3', omit_const='0',
                smoothed='1', resume_id='', lnames='', link_len='0', stime='0.0',
                etime='0.0', out_name='', pdf_dir='', ts_correct='1',
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


## Read experiment IDs from file
#  @param exp_list List of all test IDs (allows to filter out certain experiments,
#                  i.e. specific value comnbinations)
#  @return List of experiment IDs
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

    # strip off right white space
    experiments = [e.rstrip() for e in experiments]

    return experiments


## Get path from first experiment in list
#  @param experiments List of experiment ids
#  @return Path name
def get_first_experiment_path(experiments):
    # get path based on first experiment id 
    dir_name = ''
    files = get_testid_file_list('', experiments[0],
                                 '', 'LC_ALL=C sort')
    if len(files) > 0:
        dir_name = os.path.dirname(files[0])
    else:
        abort('Cannot find experiment %s\n'
              'Remove outdated teacup_dir_cache.txt if files were moved.' % experiments[0])

    return dir_name


## Build match string to match test IDs based on specified variables, and a second
## string to extract the test id prefix. does not require access to the config, 
## instead it tries to get the sames from the file name and some specified prefix
#  @param test_id_prefix Regular expression
#  @param test_id Test ID of one experiment
#  @param variables Semicolon-separated list of <var>=<value> where <value> means
#                   we only want experiments where <var> had the specific value
#  @return match string to match test IDs, match string to extract test ID prefix
def build_match_strings(test_id='', variables='', 
                         test_id_prefix='[0-9]{8}\-[0-9]{6}_experiment_'): 

    match_str = ''
    var_dict = {}

    if variables != '':
        for var in variables.split(';'):
            name, val = var.split('=')
            var_dict[name] = val

    res = re.search(test_id_prefix, test_id)
    if res == None:
        abort('Cannot find test ID prefix in test ID %s' % test_id)

    # cut off the test_id_prefix part
    test_id = test_id[res.end():]
    # strip leading underscore (if any)
    if test_id[0] == '_':
        test_id = test_id[1:]

    # now we have a number of parameter names and values separated by '_'
    # split on '_' and then all the even elements are the names
    param_short_names = test_id.split('_')[::2]

    for name in param_short_names:
        val = var_dict.get(name, '')
        if val == '':
            # we specify only fixed so this is a wildcard then
            match_str += '(' + name + '_.*)' + '_'
        else:
            match_str += '(' + name + '_' + val + ')' + '_'

    match_str = match_str[:-1]  # chomp of last underscore
    match_str2 = '(.*)_' + match_str # test id prefix is before match_str
    match_str = test_id_prefix + match_str # add test id prefix

    #print(match_str)
    #print(match_str2)

    return (match_str, match_str2)


## Filter out experiments based on the variables and also return 
## test id prefix and list of labels to plot underneath x-axis
#  @param experiments Experiment list
#  @param match_str Match string to match experiment
#  @param match_str2 Match string for test ID prefix extraction
#  @return List of filtered experiments, test ID prefix, x-axis labels
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

    xlabs = [x.replace('_', ' ') for x in xlabs]

    # print(fil_experiments)
    # print(xlabs)

    return (fil_experiments, test_id_pfx, xlabs)


## Get plot parameters based on metric
#  @param metric Metric name
#  @param smoothed If '1' plot smoothed RTT, if '0' plot unsmoothed RTT
#  @param ts_correct If '1' use file with corrected timestamps, if '0' use uncorrected file
#  @param stat_index See analyse_tcp_stat 
#  @param dupacks See analyse_ackseq
#  @param cum_ackseq See analyse_ackseq
#  @param slowest_only See analyse_incast
#  @return File extension, y-axis label, index of metric in file, scaler, separator,
#          aggregation flag, difference flag
def get_metric_params(metric='', smoothed='0', ts_correct='1', stat_index='0', dupacks='0',
                     cum_ackseq='1', slowest_only='0'):

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
        ext = '.acks'
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
    elif metric == 'restime':
        # XXX cannot select the tcpdump times here at the moment
        ext = '.rtimes'
        ylab = 'Response time (s)'
        yindex = 3
        yscaler = 1.0
        sep = ' '
        aggr = '0'
        if slowest_only != '0':
            ext = 'rtimes.slowest'
            yindex = 2
    elif metric == 'iqtime':
        ext = '.iqtimes'
        ylab = 'Inter-query time (ms)'
        yindex = 5 # time gap to previous request
        yscaler = 1000.0
        sep = ' '
        aggr = '0'
    elif metric == 'pktloss':
        ext = '.loss'
        ylab = 'Packet loss (%)'
        yindex = 2
        yscaler = 1.0
        sep = ' '
        aggr = '2'
    # elif add more
    else:
        return None

    if ts_correct == '1' and metric != 'restime':
        ext += DATA_CORRECTED_FILE_EXT

    if metric == 'spprtt' or metric == 'ackseq':
        # select the all bursts file
        ext += '.0'
    elif metric == 'iqtime':
        # select the all responders file
        ext += '.all'

    return (ext, ylab, yindex, yscaler, sep, aggr, diff)


## Get extract function based on metric
#  @param metric Metric name
#  @param link_len See analyse_throughput
#  @param stat_index See analyse_tcp_stat
#  @param slowest_only See analyse_incast
#  @param sburst Start plotting with burst N (bursts are numbered from 1)
#  @param eburst End plotting with burst N (bursts are numbered from 1)
#  @param query_host See analyse_incast_iqtimes
#  @return extract function, keyword arguments to pass to extract function 
def get_extract_function(metric='', link_len='0', stat_index='0', slowest_only='0',
                         sburst='1', eburst='0', query_host=''):

    # define a map of metrics and corresponding extract functions
    extract_functions = {
        'throughput' : _extract_pktsizes,
        'spprtt'     : _extract_rtt,
        'tcprtt'     : _extract_tcp_rtt,
        'cwnd'       : _extract_cwnd,
        'tcpstat'    : _extract_tcp_stat,
        'ackseq'     : _extract_ackseq,
        'restime'    : _extract_incast,
        'iqtime'     : _extract_incast_iqtimes,
        'pktloss'    : _extract_pktloss,
    }

    # additonal arguments for extract functions
    extract_kwargs = {
        'throughput' : { 'link_len' : link_len },
        'spprtt'     : { },
        'tcprtt'     : { },
        'cwnd'       : { },
        'tcpstat'    : { 'siftr_index'  : stat_index, 
                         'web10g_index' : stat_index },
        'ackseq'     : { 'burst_sep'    : 0.0,
                         'sburst'       : sburst,
                         'eburst'       : eburst }, 
        'restime'    : { 'sburst'       : sburst, 
                         'eburst'       : eburst, 
                         'slowest_only' : slowest_only }, 
        'iqtime'     : { 'cumulative'   : '0', 
                         'by_responder' : '0',
                         'query_host'   : query_host }, 
        'pktloss'    : { },
    }

    return (extract_functions[metric], extract_kwargs[metric])


## Function that plots mean, median, boxplot of throughput, RTT and other metrics 
## for different parameter combinations
## XXX currently can't reorder the experiment parameters, order is the one given by
##     config.py (and in the file names)
#  @param exp_list List of all test IDs (allows to filter out certain experiments,
#                  i.e. specific value comnbinations)
#  @param res_dir Directory with result files from analyse_all
#  @param out_dir Output directory for result files
#  @param source_filter Filter on specific sources
#                       (number of filters must be smaller equal to 12)
#  @param min_values Ignore flows with less output values / packets
#  @param omit_const '0' don't omit anything,
#                    '1' omit any series that are 100% constant
#                        (e.g. because there was no data flow)
#  @param metric Metric can be 'throughput', 'spprtt' (spp rtt), 'tcprtt' (unsmoothed tcp rtt), 
#                'cwnd', 'tcpstat', with 'tcpstat' must specify siftr_index or web10g_index 
#                'restime', 'ackseq', 'iqtime'
#  @param ptype Plot type: 'mean', 'median', 'box' (boxplot)
#  @param variables Semicolon-separated list of <var>=<value> where <value> means
#                   we only want experiments where <var> had the specific value
#  @param out_name Name prefix for resulting pdf file
#  @param ymin Minimum value on y-axis
#  @param ymax Maximum value on y-axis
#  @param lnames Semicolon-separated list of legend names
#  @param group_by_prefix Group by prefix instead of group by traffic flow
#  @param omit_const_xlab_vars '0' show all variables in the x-axis labels,
#                              '1' omit constant variables in the x-axis labels
#  @param pdf_dir Output directory for pdf files (graphs), if not specified it
#                 is the same as out_dir
#  @param stime Start time of time window to analyse
#               (by default 0.0 = start of experiment)
#  @param etime End time of time window to analyse (by default 0.0 = end of
#               experiment)
#  @param ts_correct '0' use timestamps as they are (default)
#                    '1' correct timestamps based on clock offsets estimated
#                        from broadcast pings
#  @param smoothed '0' plot non-smooth RTT (enhanced RTT in case of FreeBSD),
#                  '1' plot smoothed RTT estimates (non enhanced RTT in case of FreeBSD)
#  @param link_len '0' throughput based on IP length (default),
#                  '1' throughput based on link-layer length
#  @param replot_only '0' extract data
#                     '1' don't extract data again, just redo the plot
#  @param plot_params Parameters passed to plot function via environment variables
#  @param plot_script Specify the script used for plotting, must specify full path
#                     (default is config.TPCONF_script_path/plot_cmp_experiments.R)
#  @param stat_index Integer number of the column in siftr/web10g log files
#                    need when metric is 'tcpstat'
#  @param dupacks '0' to plot ACKed bytes vs time
#                 '1' to plot dupACKs vs time
#  @param cum_ackseq '0' average per time window data 
#                    '1' cumulative counter data
#  @param merge_data '0' by default don't merge data
#                    '1' merge data for each experiment, i.e. merge statistics of all flows
#                    (merging does not make sense in every case, user need to decide)
#  @param sburst Start plotting with burst N (bursts are numbered from 1)
#  @param eburst End plotting with burst N (bursts are numbered from 1)
#  @param test_id_prefix Prefix used for the experiments (used to get variables 
#                        names from the file names
#  @param slowest_only '0' plot all response times (metric restime)
#                      '1' plot only the slowest response times for each burst
#                      '2' plot time between first request and last response finished
#  @param res_time_mode '0' normal plot (default)
#                       '1' plot nominal response times in addition box/median/mean of
#                           observed response times
#                       '2' plot ratio of median/mean (as per ptype) and nominal response
#                           time
#  @param query_host Name of querier (only for iqtime metric)
@task
def analyse_cmpexp(exp_list='experiments_completed.txt', res_dir='', out_dir='',
                   source_filter='', min_values='3', omit_const='0', metric='throughput',
                   ptype='box', variables='', out_name='', ymin='0', ymax='0', lnames='',
                   group_by_prefix='0', omit_const_xlab_vars='0', replot_only='0',
                   pdf_dir='', stime='0.0', etime='0.0', ts_correct='1', smoothed='1',
                   link_len='0', plot_params='', plot_script='', stat_index='',
                   dupacks='0', cum_ackseq='1', merge_data='0', sburst='1', 
                   eburst='0', test_id_prefix='[0-9]{8}\-[0-9]{6}_experiment_',
                   slowest_only='0', res_time_mode='0', query_host=''):
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

    # prevent wrong use of res_time_mode
    if metric != 'restime' and res_time_mode != '0':
        res_time_mode = '0'
    if ptype == 'box' and res_time_mode == '2':
        res_time_mode = '0'

    # XXX more param checking

    # Initialise source filter data structure
    sfil = SourceFilter(source_filter)

    # read test ids
    experiments = read_experiment_ids(exp_list)

    # get path based on first experiment id 
    dir_name = get_first_experiment_path(experiments)

    # if we haven' got the extracted data run extract method(s) first
    if res_dir == '':
        for experiment in experiments:
            
            (ex_function, kwargs) = get_extract_function(metric, link_len,
                                    stat_index, sburst=sburst, eburst=eburst,
                                    slowest_only=slowest_only, query_host=query_host)

            (dummy, out_files, out_groups) = ex_function(
                test_id=experiment, out_dir=out_dir,  
                source_filter=source_filter, 
                replot_only=replot_only, 
                ts_correct=ts_correct,
                **kwargs)

        if out_dir == '' or out_dir[0] != '/':
            res_dir = dir_name + '/' + out_dir 
        else:
            res_dir = out_dir
    else:
        if res_dir[0] != '/':
            res_dir = dir_name + '/' + res_dir

    # make sure we have trailing slash
    res_dir = valid_dir(res_dir)

    if pdf_dir == '':
        pdf_dir = res_dir
    else:
        if pdf_dir[0] != '/':
            pdf_dir = dir_name + '/' + pdf_dir
        pdf_dir = valid_dir(pdf_dir)
        # if pdf_dir specified create if it doesn't exist
        mkdir_p(pdf_dir)

    #
    # build match string from variables
    #

    (match_str, match_str2) = build_match_strings(experiments[0], variables,
                                  test_id_prefix)

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
                              cum_ackseq, slowest_only)

    res_time_env = ''
    if res_time_mode == '1':
        res_time_env = 'NOMINAL_RES_TIME="1"'
    if res_time_mode == '2':
        if ptype == 'median':
            ylab = 'Median resp time / nominal resp time'
        elif ptype == 'mean':
            ylab = 'Mean resp time / nominal resp time'
        res_time_env += ' RATIO_RES_TIME="1"'

    leg_names = source_filter.split(';')

    # if we merge responders make sure we only use the merged files
    if merge_data == '1':
        # set label to indicate merged data
        leg_names = ['Merged data']
        # reset source filter so we match the merged file
        sfil.clear()
        source_filter = 'S_0.0.0.0_0'
        sfil = SourceFilter(source_filter)

    file_names = []
    for experiment in fil_experiments:
        out_files = {}
        _ext = ext
 
        files = get_testid_file_list('', experiment, 
                                      '%s' % _ext,
                                      'LC_ALL=C sort', res_dir)
        if merge_data == '1':
            # change extension
            _ext += '.all'
            files = merge_data_files(files)

        #print(files)
        match_str = '.*_([0-9\.]*_[0-9]*_[0-9\.]*_[0-9]*)[0-9a-z_.]*' + _ext
        for f in files:
            # print(f)
            res = re.search(match_str, f)
            #print(res.group(1))
            if res and sfil.is_in(res.group(1)):
                # only add file if enough data points
                rows = int(
                    local('wc -l %s | awk \'{ print $1 }\'' %
                          f, capture=True))
                if rows > int(min_values):
                    out_files[res.group(1)] = f

        #print(out_files)
        #print(leg_names)
        if len(out_files) < len(leg_names):
            abort(
                'No data files for some of the source filters for experiment %s' %
                experiment)

        sorted_files = sort_by_flowkeys(out_files, source_filter)

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

        # second, sort files so that same parameter combinations for different
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
        xlabs = list(set(xlabs))

    if lnames != '':
        lnames_arr = lnames.split(';')
        if len(lnames_arr) != len(leg_names):
            abort(
                'Number of legend names must be qual to the number of source filters')
        leg_names = lnames_arr

    # filter out unchanged variables in the x labels (need at least 2 labels)
    if omit_const_xlab_vars == '1' and len(xlabs) > 1:

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
        plot_script = 'R CMD BATCH --vanilla %s/plot_cmp_experiments.R' % \
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

    #local('which R')
    local('TITLE="%s" FNAMES="%s" LNAMES="%s" XLABS="%s" YLAB="%s" YINDEX="%d" '
          'YSCALER="%f" SEP="%s" OTYPE="%s" OPREFIX="%s" ODIR="%s" AGGR="%s" DIFF="%s" '
          'OMIT_CONST="%s" PTYPE="%s" YMIN="%s" YMAX="%s" STIME="%s" ETIME="%s" %s '
          '%s '
          '%s %s%s_plot_cmp_experiments.Rout' %
          (title, ','.join(file_names), ','.join(leg_names), ','.join(xlabs), ylab,
           yindex, yscaler, sep, 'pdf', oprefix, pdf_dir, aggr, diff,
           omit_const, ptype, ymin, ymax, stime, etime, res_time_env, plot_params,
           plot_script, pdf_dir, oprefix))

    if config.TPCONF_debug_level == 0:
        local('rm -f %s%s_plot_cmp_experiments.Rout' % (pdf_dir, oprefix)) 

    # done
    puts('\n[MAIN] COMPLETED analyse_cmpexp %s \n' % test_id_pfx)


## Extract incast response times from httperf files 
## The extracted files have an extension of .rtimes. The format is CSV with the
## columns:
## 1. Request timestamp (seconds.microseconds)
## 2. Burst number
## 3. Response time (seconds)
#  @param test_id Test ID prefix of experiment to analyse
#  @param out_dir Output directory for results
#  @param replot_only Don't extract data again that is already extracted
#  @param source_filter Filter on specific sources
#  @param ts_correct '0' use timestamps as they are (default)
#                    '1' correct timestamps based on clock offsets estimated
#                        from broadcast pings
#  @param sburst Start plotting with burst N (bursts are numbered from 1)
#  @param eburst End plotting with burst N (bursts are numbered from 1)
#  @param slowest_only '0' plot response times for individual responders 
#                      '1' plot slowest response time across all responders
#                      '2' plot time between first request and last response finished
#  @return Experiment ID list, map of flow names to file names, map of file names
#          to group IDs
def _extract_incast(test_id='', out_dir='', replot_only='0', source_filter='',
                    ts_correct='1', sburst='1', eburst='0', slowest_only='0'):
    "Extract incast response times for generated traffic flows"

    ifile_ext = 'httperf_incast.log.gz'
    ofile_ext = '.rtimes'
  
    # abort in case of responder timeout
    abort_extract = False

    out_files = {}
    out_groups = {}

    sburst = int(sburst)
    eburst = int(eburst)

    test_id_arr = test_id.split(';')
    if len(test_id_arr) == 0 or test_id_arr[0] == '':
        abort('Must specify test_id parameter')

    # Initialise source filter data structure
    sfil = SourceFilter(source_filter)

    group = 1
    for test_id in test_id_arr:

        # first find httperf files (ignore router and ctl interface tcpdumps)
        log_files = get_testid_file_list('', test_id,
                                         ifile_ext, '')

        for log_file in log_files:
            # get input directory name and create result directory if necessary
            out_dirname = get_out_dir(log_file, out_dir)

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
                src, src_internal = get_address_pair_analysis(test_id, src, do_abort='0')
                dst, dst_internal = get_address_pair_analysis(test_id, dst, do_abort='0')

                #print(src, src_port, dst, dst_port)

                if src == '' or dst == '':
                    continue

                # flow name
                name = src_internal + '_' + src_port + \
                    '_' + dst_internal + '_' + dst_port
                # test id plus flow name
                if len(test_id_arr) > 1:
                    long_name = test_id + '_' + name
                else:
                    long_name = name

                if not sfil.is_in(name):
                    continue

                out_fname = out_dirname + test_id + '_' + name + ofile_ext 

                out_files[long_name] = out_fname
                out_groups[out_fname] = group

                if replot_only == '0' or not os.path.isfile(out_fname) :
                    f = open(out_fname, 'w')

                    responses = _list(local('zcat %s | grep "incast_files"' %
                        log_file, capture=True))

                    time = 0.0
                    bursts = {} 
                    for response in responses:
                        request_ts = float(response.split()[0])
                        responder_id = int(response.split()[2])
                        response_time = response.split()[9]
                        interval = float(response.split()[11])
                        timed_out = response.split()[12]

                        if responder_id == cnt:

                            if not responder_id in bursts:
                                bursts[responder_id] = 0                            
                            bursts[responder_id] += 1

                            # do only write the times for burst >= sburst and burst <= eburst
                            # but sburst=0/eburst=0 means no lower/upper limit 
                            if bursts[responder_id] >= sburst and \
                               (eburst == 0 or bursts[responder_id] <= eburst):
                                if timed_out == 'no':
                                    f.write('%f %i %s\n' % (request_ts, bursts[responder_id],
                                                            response_time))
                                else:
                                    f.write('%f NA NA\n' % time)
                                    abort_extract = True

                            time += interval

                    f.close()

                cnt += 1

        # abort but only after we fully processed the problematic experiment
        if abort_extract:
            abort('Responder timed out in experiment %s' % test_id)

        group += 1

    if slowest_only != '0':
        (out_files, out_groups) = get_slowest_response_time(out_files, out_groups,
                                  int(slowest_only) - 1)

    return (test_id_arr, out_files, out_groups)


## Extract incast 
## SEE _extract_incast
@task
def extract_incast(test_id='', out_dir='', replot_only='0', source_filter='',
                   ts_correct='1', sburst='1', eburst='0'):
    "Extract incast response times for generated traffic flows"

    _extract_incast(test_id, out_dir, replot_only, source_filter, ts_correct,
                    sburst, eburst)

    # done
    puts('\n[MAIN] COMPLETED extracting incast response times %s\n' % test_id)


## Get slowest response time per burst
#  @param out_files List of data files
#  @param out_groups Map of files to groups
#  @param mode '0' slowest response time
#              '1' time between first request and last response finished
#  @return Map of flow names to file names, map of file names to group IDs
def get_slowest_response_time(out_files, out_groups, mode=0):

    ofile_ext = '.rtimes'
    slowest = {}
    earliest = {}
    latest = {}
    burst_time = {}

    for group in set(out_groups.values()):
        fname = ''
        for name in out_files.keys():
            if out_groups[out_files[name]] == group:

                # read data file and adjust slowest
                f = open(out_files[name], 'r')
                for line in f.readlines():
                    _time = float(line.split()[0])
                    _burst = float(line.split()[1])
                    # response time is in last column, but column number differs
                    # for httperf vs tcpdump extracted data
                    _res_time = float(line.split()[-1])

                    _time_finished = _time + _res_time

                    # use the first time as time burst ocurred
                    if _burst not in burst_time:
                        burst_time[_burst] = _time

                    if _burst not in slowest:
                        slowest[_burst] = _res_time
                    else:
                        if _res_time > slowest[_burst]:
                            slowest[_burst] = _res_time

                    if _burst not in earliest:
                        earliest[_burst] = _time
                    else:
                        if _time < earliest[_burst]:
                            earliest[_burst] = _time

                    if _burst not in latest:
                        latest[_burst] = _time_finished
                    else:
                        if _time_finished > latest[_burst]:
                            latest[_burst] = _time_finished

                f.close()

                if fname == '':
                    fname = out_files[name]

                # delete entries for single responders
                del out_groups[out_files[name]]
                del out_files[name]

        fname = re.sub('_[0-9]*_[0-9]*\.[0-9]*\.[0-9]*\.[0-9]*_[0-9]*\.', '_0_0.0.0.0_0.', fname)
        fname += '.slowest'
        name = 'Experiment ' + str(group) + ' slowest'

        # write file for slowest response times
        f = open(fname, 'w')
        for _burst in sorted(slowest.keys()):
            if mode == 0:
                # slowest response time of all 
                f.write('%f %f\n' % (burst_time[_burst], slowest[_burst]))
            else:
                # time between first request and last response finished
                f.write('%f %f\n' % (burst_time[_burst], latest[_burst] - earliest[_burst]))

        f.close()

        out_files[name] = fname
        out_groups[fname] = group

    return (out_files, out_groups)


## Plot incast response times 
#  @param test_id Test ID prefix of experiment to analyse
#  @param out_dir Output directory for results
#  @param replot_only Don't extract data again, just redo the plot
#  @param source_filter Filter on specific sources
#  @param min_values Ignore flows with equal less output values / packets
#  @param omit_const '0' don't omit anything,
#                    '1' omit any series that are 100% constant
#                        (e.g. because there was no data flow)
#  @param ymin Minimum value on y-axis
#  @param ymax Maximum value on y-axis
#  @param lnames Semicolon-separated list of legend names
#  @param stime Start time of plot window in seconds
#               (by default 0.0 = start of experiment)
#  @param etime End time of plot window in seconds (by default 0.0 = end of experiment)
#  @param out_name Name prefix for resulting pdf file
#  @param tcpdump '0' by default use the response times reported by httperf
#                 '1' plot response times based on tcpdump data (time between GET packet
#                     and last packet of the response)
#  @param query_host If tcpdump=0 we don't need to set this parameter. however, tcpdump=1
#                    query_host needs to be set to the host name that was the querier.
#                    The name of the host as specified in the config file.
#  @param pdf_dir Output directory for pdf files (graphs), if not specified it is
#                 the same as out_dir
#  @param ts_correct '0' use timestamps as they are (default)
#                    '1' correct timestamps based on clock offsets estimated
#                        from broadcast pings
#  @param slowest_only '0' plot response times for individual responders 
#                      '1' plot slowest response time across all responders
#                      '2' plot time between first request and last response finished
#  @param boxplot '0' normal time series (default)
#                 '1' boxplot for each point in time
#  @param sburst Start plotting with burst N (bursts are numbered from 1)
#  @param eburst End plotting with burst N (bursts are numbered from 1)
#  @param plot_params Set env parameters for plotting
#  @param plot_script Specify the script used for plotting, must specify full path
@task
def analyse_incast(test_id='', out_dir='', replot_only='0', source_filter='',
                       min_values='3', omit_const='0', ymin='0', ymax='0', lnames='',
                       stime='0.0', etime='0.0', out_name='', tcpdump='0', query_host='',
                       pdf_dir='', ts_correct='1', slowest_only='0',
                       boxplot='0', sburst='1', eburst='0', plot_params='', plot_script=''):
    "Plot incast response times for generated traffic flows"

    pdf_name_part = '_restime'
    sort_flowkey = '1'

    if tcpdump == '1':
        # XXX no sburst and eburst for tcpdump yet
        if query_host == '':
            abort('Must specify query_host')
        (test_id_arr,
         out_files,
         out_groups) = _extract_incast_restimes(test_id, out_dir, replot_only, 
                             source_filter, ts_correct, query_host, slowest_only)
        yindex = 5
        ofile_ext = '.restimes'
    else:
        (test_id_arr,
         out_files,
         out_groups) = _extract_incast(test_id, out_dir, replot_only, source_filter, 
                                       ts_correct, sburst, eburst, slowest_only) 
        yindex = 3
        ofile_ext = '.rtimes'

    if slowest_only != '0':
        pdf_name_part = '_restime_slowest'
        sort_flowkey = '0'
        # the slowest code produces an output file with only two columns 
        # (time, response time)
        yindex = 2

    out_name = get_out_name(test_id_arr, out_name)
    plot_time_series(out_name, out_files, 'Response time (s)', yindex, 1.0, 'pdf',
                     out_name + pdf_name_part, pdf_dir=pdf_dir,
                     ymin=float(ymin), ymax=float(ymax),
                     lnames=lnames, stime=stime, etime=etime, 
                     groups=out_groups, sort_flowkey=sort_flowkey, 
                     boxplot=boxplot, plot_params=plot_params, plot_script=plot_script,
                     source_filter=source_filter) 

    # done
    puts('\n[MAIN] COMPLETED plotting incast response times %s\n' % out_name)


## Extract_dupACKs_bursts
#  @param acks_file Full path to a specific .acks file which is to be parsed
#                   for dupACKs and (optionally) extract sequence of ACK bursts
#  @param burst_sep =0, Just calculate running total of dupACKs and create acks_file+".0" output file
#                  < 0, extract bursts into acks_file+".N" outputfiles (for burst N),
#                     where burst starts @ t=0 and then burst_sep seconds after start of previous burst
#                  > 0, extract bursts into acks_file+".N" outputfiles (for burst N)
#                     where burst starts @ t=0 and then burst_sep seconds after end of previous burst
#  @return Vector of file names (one for each file generated)
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
# NOTE: This function relies on there being no re-ordering of ACK packets on
#       the return path.
#
def extract_dupACKs_bursts(acks_file='', burst_sep=0):

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
                out_f.write(ackdetails[0]+" "+str(bytes_gap)+" "+str(dupACKs)+"\n")

                # Store the seq number for next time around the loop
                prev_seqno = ackdetails[1]
                prev_ACKTS = ackdetails[0]

            # Close the last output file
            out_f.close()

    except IOError:
        print('extract_dupACKs_bursts(): File access problem while working on %s' % acks_file)

    return new_fnames



## Extract cumulative bytes ACKnowledged and cumulative dupACKs
## Intermediate files end in ".acks", ".acks.N", ".acks.tscorr" or ".acks.tscorr.N"
## XXX move sburst and eburst to the plotting task and here extract all?
#  @param test_id Semicolon-separated list of test ID prefixes of experiments to analyse
#  @param out_dir Output directory for results
#  @param replot_only '1' don't extract raw ACK vs time data per test_ID if already done,
#                     but still re-calculate dupACKs and bursts (if any) before plotting results
#                     '0' always extract raw data
#  @param source_filter Filter on specific flows to process
#  @param ts_correct '0' use timestamps as they are (default)
#                    '1' correct timestamps based on clock offsets estimated
#                        from broadcast pings
#  @param burst_sep '0' plot seq numbers as they come, relative to 1st seq number
#                   > '0' plot seq numbers relative to 1st seq number after gaps
#                        of more than burst_sep milliseconds (e.g. incast query/response bursts)
#                   < 0, plot seq numbers relative to 1st seq number after each abs(burst_sep)
#                        seconds since the first burst @ t = 0 (e.g. incast query/response bursts)
#  @param sburst Start plotting with burst N (bursts are numbered from 1)
#  @param eburst End plotting with burst N (bursts are numbered from 1)
#   @param total_per_experiment '0' per-flow data (default)
#                               '1' total data 
#  @return Experiment ID list, map of flow names to file names, map of file names to group IDs
def _extract_ackseq(test_id='', out_dir='', replot_only='0', source_filter='',
                    ts_correct='1', burst_sep='0.0',
                    sburst='1', eburst='0', total_per_experiment='0'):
    "Extract cumulative bytes ACKnowledged vs time / extract incast bursts"

    ifile_ext = '.dmp.gz'
    ofile_ext = '.acks'

    sburst = int(sburst)
    eburst = int(eburst)
    burst_sep = float(burst_sep)

    already_done = {}
    out_files = {}
    out_groups = {}

    test_id_arr = test_id.split(';')
    if len(test_id_arr) == 0 or test_id_arr[0] == '':
        abort('Must specify test_id parameter')

    # Initialise source filter data structure
    sfil = SourceFilter(source_filter)

    group = 1
    for test_id in test_id_arr:

        # first process tcpdump files (ignore router and ctl interface tcpdumps)
        tcpdump_files = get_testid_file_list('', test_id,
                                       ifile_ext,
                                       'grep -v "router.dmp.gz" | grep -v "ctl.dmp.gz"')

        for tcpdump_file in tcpdump_files:
            # get input directory name and create result directory if necessary
            dir_name = os.path.dirname(tcpdump_file)
            out_dirname = get_out_dir(tcpdump_file, out_dir)

            # unique flows
            flows = lookup_flow_cache(tcpdump_file)
            if flows == None:
                flows = _list(local('zcat %s | tcpdump -nr - "tcp" | '
                                'awk \'{ if ( $2 == "IP" ) { print $3 " " $5 " tcp" } }\' | '
                                'sed "s/://" | '
                                'sed "s/\.\([0-9]*\) /,\\1 /g" | sed "s/ /,/g" | '
                                'LC_ALL=C sort -u' %
                                tcpdump_file, capture=True))

                append_flow_cache(tcpdump_file, flows)

            # since client sends first packet to server, client-to-server flows
            # will always be first

            for flow in flows:
	
                src, src_port, dst, dst_port, proto = flow.split(',')

                # get external and internal addresses
                src, src_internal = get_address_pair_analysis(test_id, src, do_abort='0')
                dst, dst_internal = get_address_pair_analysis(test_id, dst, do_abort='0')

                if src == '' or dst == '':
                    continue

                # flow name
                name = src_internal + '_' + src_port + \
                    '_' + dst_internal + '_' + dst_port
                rev_name = dst_internal + '_' + dst_port + \
                    '_' + src_internal + '_' + src_port
                # test id plus flow name
                if len(test_id_arr) > 1:
                    long_name = test_id + '_' + name
                    long_rev_name = test_id + '_' + rev_name
                else:
                    long_name = name
                    long_rev_name = rev_name

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

                out_acks1 = out_dirname + test_id + '_' + name + ofile_ext 
                out_acks2 = out_dirname + test_id + '_' + rev_name + ofile_ext 

                if long_name not in already_done and long_rev_name not in already_done:
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

                    already_done[long_name] = 1
                    already_done[long_rev_name] = 1

                    if sfil.is_in(name):
                        if ts_correct == '1':
                            out_acks1 = adjust_timestamps(test_id, out_acks1, dst, ' ', out_dir)

                        # do the dupACK calculations and burst extraction here,
                        # return a new vector of one or more filenames, pointing to file(s) containing
                        # <time> <seq_no> <dupACKs>
                        #
                        out_acks1_dups_bursts = extract_dupACKs_bursts(acks_file = out_acks1, 
                                                          burst_sep = burst_sep)
                        # Incorporate the extracted .N files
                        # as a new, expanded set of filenames to be plotted.
                        # Update the out_files dictionary (key=interim legend name based on flow, value=file)
                        # and out_groups dictionary (key=file name, value=group)
                        if burst_sep == 0.0:
                            # Assume this is a single plot (not broken into bursts)
                            # The plot_time_series() function expects key to have a single string
                            # value rather than a vector. Take the first (and presumably only)
                            # entry in the vector returned by extract_dupACKs_bursts()
                            out_files[long_name] = out_acks1_dups_bursts[0]
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

                            out_files[long_name] = out_acks1_dups_bursts[sburst-1:eburst]
                            for tmp_f in out_acks1_dups_bursts[sburst-1:eburst] :
                                out_groups[tmp_f] = group

                    if sfil.is_in(rev_name):
                        if ts_correct == '1':
                            out_acks2 = adjust_timestamps(test_id, out_acks2, src, ' ', out_dir)

                        # do the dupACK calculations burst extraction here
                        # return a new vector of one or more filenames, pointing to file(s) containing
                        # <time> <seq_no> <dupACKs>
                        #
                        out_acks2_dups_bursts = extract_dupACKs_bursts(acks_file = out_acks2, 
                                                          burst_sep = burst_sep)

                        # Incorporate the extracted .N files
                        # as a new, expanded set of filenames to be plotted.
                        # Update the out_files dictionary (key=interim legend name based on flow, value=file)
                        # and out_groups dictionary (key=file name, value=group)
                        if burst_sep == 0.0:
                            # Assume this is a single plot (not broken into bursts)
                            # The plot_time_series() function expects key to have a single string
                            # value rather than a vector. Take the first (and presumably only)
                            # entry in the vector returned by extract_dupACKs_bursts()
                            out_files[long_rev_name] = out_acks2_dups_bursts[0]
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

                            out_files[long_rev_name] = out_acks2_dups_bursts[sburst-1:eburst]
                            for tmp_f in out_acks2_dups_bursts[sburst-1:eburst] :
                                out_groups[tmp_f] = group

        # if desired compute aggregate acked bytes for each experiment
        # XXX only do this for burst_sep=0 now
        if burst_sep == 0.0 and total_per_experiment == '1':

            aggregated = {}

            # first read everything in one dictionary indexed by time
            flow = 0
            for name in out_files:
                if out_groups[out_files[name]] == group:
                    with open(out_files[name], 'r') as f:
                        lines = f.readlines()
                        for line in lines:
                            fields = line.split()
                            curr_time = float(fields[0])
                            if curr_time not in aggregated:
                                aggregated[curr_time] = [] 
                            aggregated[curr_time].append((flow, int(fields[1]), int(fields[2])))

                    flow += 1

            total = {} # total cumulative values 
            last_flow_val = {} # last values per flow (ackbyte, dupack) tuples
            last_val = (0, 0)  # value from last time

            # second go through by time and total 
            for t in sorted(aggregated.keys()):

                # if there is no entry for time t, then create one
                if t not in total:
                    total[t] = last_val # start with the last value (cumulative total) 
 
                # get delta values for ackbytes and dupacks for each value and add
                for (flow, cum_byte, cum_ack) in aggregated[t]:

                    #print(t, flow, cum_byte, cum_ack)

                    if flow in last_flow_val:
                        byte = cum_byte - last_flow_val[flow][0]
                        ack = cum_ack - last_flow_val[flow][1]
                    else:
                        byte = cum_byte
                        ack = cum_ack

                    #if flow in last_flow_val:
                    #    print(cum_byte, last_flow_val[flow][0], byte)

                    # add delta values to value at current time t
                    total[t] = (total[t][0] + byte, total[t][1] + ack) 
 
                    # memorise last value
                    last_flow_val[flow] = (cum_byte, cum_ack)

                last_val = total[t]

            # write output file
            out_acks1 = out_dirname + test_id + '_total' + ofile_ext
            with open(out_acks1, 'w') as f:
                for t in sorted(total.keys()):
                    f.write('%f %i %i\n' % (t, total[t][0], total[t][1]))

            # replace all files for separate flows with total
            delete_list = []
            for name in out_files:
                if out_groups[out_files[name]] == group:
                    delete_list.append(name)

            #print(delete_list)
            #print(out_files)
            #print(out_groups)
            for d in delete_list:
                try:
                    del out_groups[out_files[d]]
                except KeyError:
                    # forward and backward name match to same data file 
                    # XXX investigate
                    pass
                del out_files[d]

            name = test_id
            out_files[name] = out_acks1
            out_groups[out_acks1] = group


        group += 1

    return (test_id_arr, out_files, out_groups)


## Extract cumulative bytes ACKnowledged and cumulative dupACKs
## SEE _extract_ackseq
@task
def extract_ackseq(test_id='', out_dir='', replot_only='0', source_filter='',
                    ts_correct='1', burst_sep='0.0',
                    sburst='1', eburst='0', total_per_experiment='0'):
    "Extract cumulative bytes ACKnowledged vs time / extract incast bursts"

    _extract_ackseq(test_id, out_dir, replot_only, source_filter, ts_correct,
                    burst_sep, sburst, eburst, total_per_experiment)

    # done
    puts('\n[MAIN] COMPLETED extracting ackseq %s \n' % test_id)


## Plot cumulative bytes ACKnowledged or cumulative dupACKs vs time
#  @param test_id Semicolon-separated list of test ID prefixes of experiments to analyse
#  @param out_dir Output directory for results
#  @param replot_only '1' don't extract raw ACK vs time data per test_ID if already done,
#                     but still re-calculate dupACKs and bursts (if any) before plotting results
#  @param source_filter Filter on specific flows to process
#  @param min_values Ignore flows with equal less output values / packets
#  @param omit_const '0' don't omit anything,
#                    '1' omit any series that are 100% constant
#                    (e.g. because there was no data flow)
#  @param ymin Minimum value on y-axis
#  @param ymax Maximum value on y-axis
#  @param lnames Semicolon-separated list of legend names per flow
#                (each name will have burst numbers appended if burst_sep is set)
#  @param stime Start time of plot window in seconds
#               (by default 0.0 = start of experiment)
#  @param etime End time of plot window in seconds (by default 0.0 = end of experiment)
#  @param out_name Prefix for filenames of resulting pdf files
#  @param pdf_dir Output directory for pdf files (graphs), if not specified it is
#                the same as out_dir
#  @param ts_correct '0' use timestamps as they are (default)
#                    '1' correct timestamps based on clock offsets estimated
#                        from broadcast pings
#  @param burst_sep '0' plot seq numbers as they come, relative to 1st seq number
#                   > '0' plot seq numbers relative to 1st seq number after gaps
#                   of more than burst_sep milliseconds (e.g. incast query/response bursts)
#                   < 0,  plot seq numbers relative to 1st seq number after each abs(burst_sep)
#                   seconds since the first burst @ t = 0 (e.g. incast query/response bursts)
#   @param sburst Start plotting with burst N (bursts are numbered from 1)
#   @param eburst End plotting with burst N (bursts are numbered from 1)
#   @param dupacks '0' to plot ACKed bytes vs time
#                  '1' to plot cumulative dupACKs vs time
#   @param plot_params Parameters passed to plot function via environment variables
#   @param plot_script Specify the script used for plotting, must specify full path
#
# Intermediate files end in ".acks", ".acks.N", ".acks.tscorr" or ".acks.tscorr.N"
# Output pdf files end in:
#   "_ackseqno_time_series.pdf",
#   "_ackseqno_bursts_time_series.pdf",
#   "_comparison_ackseqno_time_series.pdf"
#   "_comparison_ackseqno_bursts_time_series.pdf"
#   (if dupacks=1, then as above with "dupacks" instead of "ackseqno")
@task
def analyse_ackseq(test_id='', out_dir='', replot_only='0', source_filter='',
                       min_values='3', omit_const='0', ymin='0', ymax='0', lnames='',
                       stime='0.0', etime='0.0', out_name='',
                       pdf_dir='', ts_correct='1', burst_sep='0.0',
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
    if float(burst_sep) == 0.0:
        # Regular plots, each trial has one file containing data
        plot_time_series(out_name, out_files, yaxistitle, ycolumn, yaxisscale, 'pdf',
                        out_name + oname, pdf_dir=pdf_dir, aggr='',
                        omit_const=omit_const, ymin=float(ymin), ymax=float(ymax),
                        lnames=lnames, stime=stime, etime=etime, groups=out_groups,
                        plot_params=plot_params, plot_script=plot_script,
                        source_filter=source_filter)
    else:
        # Each trial has multiple files containing data from separate ACK bursts detected within the trial
        plot_incast_ACK_series(out_name, out_files, yaxistitle, ycolumn, yaxisscale, 'pdf',
                        out_name + oname, pdf_dir=pdf_dir, aggr='',
                        omit_const=omit_const, ymin=float(ymin), ymax=float(ymax),
                        lnames=lnames, stime=stime, etime=etime, groups=out_groups, burst_sep=burst_sep, 
                        sburst=int(sburst), plot_params=plot_params, plot_script=plot_script,
                        source_filter=source_filter)

    # done
    puts('\n[MAIN] COMPLETED plotting ackseq %s \n' % out_name)


## Plot goodput based on extracted ACKseq data
#  @param test_id Semicolon-separated list of test ID prefixes of experiments to analyse
#  @param out_dir Output directory for results
#  @param replot_only '1' don't extract raw ACK vs time data per test_ID if already done,
#                     but still re-calculate dupACKs and bursts (if any) before plotting results
#  @param source_filter Filter on specific flows to process
#  @param min_values Ignore flows with equal less output values / packets
#  @param omit_const '0' don't omit anything,
#                    '1' omit any series that are 100% constant
#                    (e.g. because there was no data flow)
#  @param ymin Minimum value on y-axis
#  @param ymax Maximum value on y-axis
#  @param lnames Semicolon-separated list of legend names per flow
#                (each name will have burst numbers appended if burst_sep is set)
#  @param stime Start time of plot window in seconds
#               (by default 0.0 = start of experiment)
#  @param etime End time of plot window in seconds (by default 0.0 = end of experiment)
#  @param out_name Prefix for filenames of resulting pdf files
#  @param pdf_dir Output directory for pdf files (graphs), if not specified it is
#                the same as out_dir
#  @param ts_correct '0' use timestamps as they are (default)
#                    '1' correct timestamps based on clock offsets estimated
#                        from broadcast pings
#   @param plot_params Parameters passed to plot function via environment variables
#   @param plot_script Specify the script used for plotting, must specify full path
#   @param total_per_experiment '0' plot per-flow goodput (default)
#                               '1' plot total goodput
@task
def analyse_goodput(test_id='', out_dir='', replot_only='0', source_filter='',
                       min_values='3', omit_const='0', ymin='0', ymax='0', lnames='',
                       stime='0.0', etime='0.0', out_name='',
                       pdf_dir='', ts_correct='1', 
                       plot_params='', plot_script='', total_per_experiment='0'):
    "Plot goodput vs time"

    (test_id_arr,
     out_files,
     out_groups) =  _extract_ackseq(test_id, out_dir, replot_only, source_filter,
                    ts_correct, 0, 0, 0, total_per_experiment)

    (out_files, out_groups) = filter_min_values(out_files, out_groups, min_values)
    out_name = get_out_name(test_id_arr, out_name)

    yaxistitle = 'Goodput [kbps]'
    ycolumn = 2
    yaxisscale = 0.008 
    oname = '_goodput'

    # ackseq always delivers cumulative values, instruct plot code to use the
    # differences
    plot_params = plot_params + 'DIFF=1'

    if total_per_experiment == '0':
        sort_flowkey='1'
    else:
        sort_flowkey='0'

    # Regular plots, each trial has one file containing data
    plot_time_series(out_name, out_files, yaxistitle, ycolumn, yaxisscale, 'pdf',
                     out_name + oname, pdf_dir=pdf_dir, aggr='1',
                     omit_const=omit_const, ymin=float(ymin), ymax=float(ymax),
                     lnames=lnames, stime=stime, etime=etime, groups=out_groups,
                     sort_flowkey=sort_flowkey,
                     plot_params=plot_params, plot_script=plot_script,
                     source_filter=source_filter)

    # done
    puts('\n[MAIN] COMPLETED plotting ackseq %s \n' % out_name)


## Generate a 2d density plot with one paramter on x, one one y and the third
## one expressed as different colours of the "blobs" 
#  @param exp_list List of all test IDs (allows to filter out certain experiments,
#                  i.e. specific value comnbinations)
#  @param res_dir Directory with result files from analyse_all
#  @param out_dir Output directory for result files
#  @param source_filter Filter on specific sources. typically one source. if multiple sources
#                       are specified they are all aggregated. unlike analyse_cmpexp here we
#                       can't have per-source categories.
#  @param min_values Ignore flows with less output values / packets
#  @param xmetric Can be 'throughput', 'spprtt' (spp rtt), 'tcprtt' (unsmoothed tcp rtt), 'cwnd',
#                 'tcpstat', with 'tcpstat' must specify siftr_index or web10g_index 
#  @param ymetric: Can be 'throughput', 'spprtt' (spp rtt), 'tcprtt' (unsmoothed tcp rtt), 'cwnd',
#                  'tcpstat', with 'tcpstat' must specify siftr_index or web10g_index 
#  @param variables Semicolon-separated list of <var>=<value> where <value> means
#                   we only want experiments where <var> had the specific value
#  @param out_name File name prefix
#  @param xmin Minimum value on x-axis
#  @param xmax Maximum value on x-axis
#  @param ymin Minimum value on y-axis
#  @param ymax Maximum value on y-axis
#  @param lnames Semicolon-separated list of legend names
#  @param group_by Semicolon-separated list of experiment variables defining the different categories 
#                  the variables are the variable names used in the file names
#  @param pdf_dir Output directory for pdf files (graphs), if not specified it
#                 is the same as out_dir
#  @param ts_correct '0' use timestamps as they are (default)
#                    '1' correct timestamps based on clock offsets estimated
#                        from broadcast pings
#  @param smoothed '0' plot non-smooth RTT (enhanced RTT in case of FreeBSD),
#                  '1' plot smoothed RTT estimates (non enhanced RTT in case of FreeBSD)
#  @param link_len '0' throughput based on IP length (default),
#                  '1' throughput based on link-layer length
#  @param replot_only '0' extract data
#                     '1' don't extract data again, just redo the plot
#  @param plot_params Parameters passed to plot function via environment variables
#  @param plot_script Specify the script used for plotting, must specify full path
#                     (default is config.TPCONF_script_path/plot_contour.R)
#  @param xstat_index Integer number of the column in siftr/web10g log files (for xmetric)
#  @param ystat_index Integer number of the column in siftr/web10g log files (for ymetric)
#  @param dupacks '0' to plot ACKed bytes vs time
#                 '1' to plot dupACKs vs time
#  @param cum_ackseq '0' average per time window data 
#                    '1' cumulative counter data
#  @param merge_data '0' by default don't merge data
#                    '1' merge data for each experiment 
#  @param sburst Start plotting with burst N (bursts are numbered from 1)
#  @param eburst End plotting with burst N (bursts are numbered from 1)
#  @param test_id_prefix Prefix used for the experiments (used to get variables 
#                        names from the file names
#  @param slowest_only '0' plot all response times (metric restime)
#                      '1' plot only the slowest response times for each burst
#  @param query_host Name of querier (only for iqtime metric)
# NOTE: that xmin, xmax, ymin and ymax don't just zoom, but govern the selection of data points
#       used for the density estimation. this is how ggplot2 works by default, although possibly
#       can be changed
@task
def analyse_2d_density(exp_list='experiments_completed.txt', res_dir='', out_dir='',
                   source_filter='', min_values='3', xmetric='throughput',
                   ymetric='tcprtt', variables='', out_name='', xmin='0', xmax='0',
                   ymin='0', ymax='0', lnames='', group_by='aqm', replot_only='0',
                   pdf_dir='', ts_correct='1', smoothed='1', link_len='0',
                   plot_params='', plot_script='', xstat_index='', ystat_index='',
                   dupacks='0', cum_ackseq='1', merge_data='0', 
                   sburst='1', eburst='0', test_id_prefix='[0-9]{8}\-[0-9]{6}_experiment_',
                   slowest_only='0', query_host=''):
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

    # Initialise source filter data structure
    sfil = SourceFilter(source_filter)

    # read test ids
    experiments = read_experiment_ids(exp_list)

    # get path based on first experiment id 
    dir_name = get_first_experiment_path(experiments)

    # if we haven' got the extracted data run extract method(s) first
    if res_dir == '':
        for experiment in experiments:

            (ex_function, kwargs) = get_extract_function(xmetric, link_len,
                                    xstat_index, sburst=sburst, eburst=eburst,
                                    slowest_only=slowest_only, query_host=query_host)
            
            (dummy, out_files, out_groups) = ex_function(
                test_id=experiment, out_dir=out_dir,
                source_filter=source_filter,
                replot_only=replot_only,
                ts_correct=ts_correct,
                **kwargs)

            (ex_function, kwargs) = get_extract_function(ymetric, link_len,
                                    ystat_index, sburst=sburst, eburst=eburst,
                                    slowest_only=slowest_only, query_host=query_host)
   
            (dummy, out_files, out_groups) = ex_function(
                test_id=experiment, out_dir=out_dir,
                source_filter=source_filter,
                replot_only=replot_only,
                ts_correct=ts_correct,
                **kwargs)

        if out_dir == '' or out_dir[0] != '/':
            res_dir = dir_name + '/' + out_dir
        else:
            res_dir = out_dir
    else:
        if res_dir[0] != '/':
            res_dir = dir_name + '/' + res_dir

    # make sure we have trailing slash
    res_dir = valid_dir(res_dir)

    if pdf_dir == '':
        pdf_dir = res_dir
    else:
        if pdf_dir[0] != '/':
            pdf_dir = dir_name + '/' + pdf_dir
        pdf_dir = valid_dir(pdf_dir)
        # if pdf_dir specified create if it doesn't exist
        mkdir_p(pdf_dir)

    #
    # build match string from variables
    #

    (match_str, match_str2) = build_match_strings(experiments[0], variables,
                                  test_id_prefix)

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

            if merge_data == '1':
                groups.append(levels[level])
            else:
                for i in range(len(source_filter.split(';'))):
                   groups.append(levels[level])

    fil_experiments = _experiments

    #
    # get metric parameters and list of data files
    #

    # get the metric parameter for both x and y
    x_axis_params = get_metric_params(xmetric, smoothed, ts_correct, xstat_index, 
                                      dupacks, cum_ackseq, slowest_only)
    y_axis_params = get_metric_params(ymetric, smoothed, ts_correct, ystat_index, 
                                      dupacks, cum_ackseq, slowest_only)

    x_ext = x_axis_params[0]
    y_ext = y_axis_params[0]
 
    # if we merge responders make sure we only use the merged files
    if merge_data == '1':
        # reset source filter so we match the merged file
        sfil.clear()
        sfil = SourceFilter('S_0.0.0.0_0')

    x_files = []
    y_files = []
    for experiment in fil_experiments:
        _x_files = []
        _y_files = []
        _x_ext = x_ext
        _y_ext = y_ext

        _files = get_testid_file_list('', experiment, _x_ext,
                                      'LC_ALL=C sort', res_dir)
        if merge_data == '1':
            _x_ext += '.all'
            _files = merge_data_files(_files)
        _x_files += _files

        _files = get_testid_file_list('', experiment, _y_ext,
                                      'LC_ALL=C sort', res_dir)
        if merge_data == '1':
            _y_ext += '.all'
            _files = merge_data_files(_files)
        _y_files += _files

        match_str = '.*_([0-9\.]*_[0-9]*_[0-9\.]*_[0-9]*)[0-9a-z_.]*' + _x_ext
        for f in _x_files:
            #print(f)
            res = re.search(match_str, f)
            #print(res.group(1))
            if res and sfil.is_in(res.group(1)):
                # only add file if enough data points
                rows = int(
                    local('wc -l %s | awk \'{ print $1 }\'' %
                          f, capture=True))
                if rows > int(min_values):
                    x_files.append(f)
   
        match_str = '.*_([0-9\.]*_[0-9]*_[0-9\.]*_[0-9]*)[0-9a-z_.]*' + _y_ext
        for f in _y_files:
            # print(f)
            res = re.search(match_str, f)
            if res and sfil.is_in(res.group(1)):
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
        plot_script = 'R CMD BATCH --vanilla %s/plot_contour.R' % config.TPCONF_script_path

    #local('which R')
    local('TITLE="%s" XFNAMES="%s" YFNAMES="%s", LNAMES="%s" XLAB="%s" YLAB="%s" YINDEXES="%s" '
          'YSCALERS="%s" XSEP="%s" YSEP="%s" OTYPE="%s" OPREFIX="%s" ODIR="%s" AGGRS="%s" '
          'DIFFS="%s" XMIN="%s" XMAX="%s" YMIN="%s" YMAX="%s" GROUPS="%s" %s '
          '%s %s%s_plot_contour.Rout' %
          (title, ','.join(x_files), ','.join(y_files), ','.join(leg_names),
           x_axis_params[1], y_axis_params[1], ','.join(yindexes), ','.join(yscalers),
           x_axis_params[4], y_axis_params[4], 'pdf', oprefix, pdf_dir, ','.join(aggr_flags),
           ','.join(diff_flags), xmin, xmax, ymin, ymax, ','.join([str(x) for x in groups]), 
           plot_params, plot_script, pdf_dir, oprefix))

    if config.TPCONF_debug_level == 0:
        local('rm -f %s%s_plot_contour.Rout' % (pdf_dir, oprefix))

    # done
    puts('\n[MAIN] COMPLETED analyse_2d_density %s \n' % test_id_pfx)


## Extract inter-query times for each query burst
#  @param test_id Semicolon-separated list of test ID prefixes of experiments to analyse
#  @param out_dir Output directory for results
#  @param replot_only '1' don't extract raw ACK vs time data per test_ID if already done,
#                     but still re-calculate dupACKs and bursts (if any) before plotting results
#                     '0' always extract raw data
#  @param source_filter Filter on specific flows to process
#  @param ts_correct '0' use timestamps as they are (default)
#                    '1' correct timestamps based on clock offsets estimated
#                        from broadcast pings
#  @param query_host Name of the host that sent the queries
#  @param by_responder '1' plot times for each responder separately
#                      Limitation: if by_responder=1, then this function only supports one test id
#                      '0' times for all responders
#  @param cummulative '0' raw inter-query time for each burst 
#                     '1' accumulated inter-query time over all bursts
#  @param burst_sep 'time between burst (default 1.0), must be > 0 
#  @return Experiment ID list, map of flow names and file names, map of file names to group IDs
#
# Intermediate files end in ".iqtime.all ".iqtime.<responder>", ".iqtime.<responder>.tscorr" 
# The files contain the following columns:
# 1. Timestamp
# 2. IP of responder
# 3. port number of responder
# 4. inter-query time, time between request and first request in burst 
# 5. inter-query time, time between request and previous request  
# Note 4,5 can be cumulative or non-cumulative
def _extract_incast_iqtimes(test_id='', out_dir='', replot_only='0', source_filter='',
                           ts_correct='1', query_host='', by_responder='1', cumulative='0',
                           burst_sep='1.0'):
    "Extract incast inter-query times"

    ifile_ext = '.dmp.gz'
    ofile_ext = '.iqtimes' # inter-query times

    already_done = {}
    out_files = {}
    out_groups = {}

    burst_sep = float(burst_sep)

    if query_host == '':
        abort('Must specify query_host parameter')

    test_id_arr = test_id.split(';')
    if len(test_id_arr) == 0 or test_id_arr[0] == '':
        abort('Must specify test_id parameter')

    # Initialise source filter data structure
    sfil = SourceFilter(source_filter)

    group = 1
    for test_id in test_id_arr:

        # first process tcpdump files (ignore router and ctl interface tcpdumps)
        tcpdump_files = get_testid_file_list('', test_id,
                                       ifile_ext,
                                       'grep -v "router.dmp.gz" | grep -v "ctl.dmp.gz"')

        for tcpdump_file in tcpdump_files:
            # get input directory name and create result directory if necessary
            out_dirname = get_out_dir(tcpdump_file, out_dir)

            if tcpdump_file.find(query_host) == -1:
                # ignore all dump files not taken at query host
                continue

            # tcpdump filters and output file names
            # 'tcp[tcpflags] & tcp-push != 0' rule to extract only packets with push flag set (eliminate SYN, FIN, or ACKs
            # without data)
            filter1 = 'tcp[tcpflags] & tcp-push != 0'

            (dummy, query_host_internal) = get_address_pair_analysis(test_id, query_host, do_abort='0') 
            flow_name = query_host_internal + '_0_0.0.0.0_0'
            name = test_id + '_' + flow_name 
            out1 = out_dirname + name + ofile_ext

            if name not in already_done:
                if replot_only == '0' or not (os.path.isfile(out1)):

                    # Use "-A" option to tcpdump so we get the payload bytes and can check for GET 
                    # XXX this command fails if default snap length is changed because of the magic -B 4
                    local(
                       'zcat %s | tcpdump -A -tt -nr - "%s" | grep -B 5 "GET" | egrep "IP" | '
                       'awk \'{ print $1 " " $5; }\' | sed \'s/\.\([0-9]*\):/ \\1/\'  > %s' %
                       (tcpdump_file, filter1, out1))

                already_done[name] = 1

                if sfil.is_in(flow_name):
                    if ts_correct == '1':
                        out1 = adjust_timestamps(test_id, out1, query_host, ' ', out_dir)

                    if by_responder == '0':
                        # all responders in in one output file
                        out_name = out1 + '.all'

                        if replot_only == '0' or not (os.path.isfile(out_name)):
                            last_time = 0.0
                            burst_start = 0.0
                            cum_time = 0.0 

                            out_f = open(out_name, 'w')

                            with open(out1) as f:
                                lines = f.readlines()
                                for line in lines:
                                    fields = line.split()
                                    time = float(fields[0])

                                    if burst_start == 0.0:
                                        burst_start = time
                                    if line != lines[:-1] and last_time != 0.0 and time - last_time >= burst_sep:
                                        cum_time += (last_time - burst_start)
                                        burst_start = time
                                        last_req_time = time
                                    else:
                                        last_req_time = last_time
                                        if last_req_time == 0.0:
                                            last_req_time = time

                                    if cumulative == '0':
                                        out_f.write('%s %f %f\n' % (' '.join(fields), (time - burst_start), (time - last_req_time)))
                                    else:
                                        out_f.write('%s %f %f\n' % (' '.join(fields), cum_time + (time - burst_start),
                                                    cum_time + (time - last_req_time)))
                                    last_time = float(time)

                            out_f.close()

                        out_files[name] = out_name
                        out_groups[out_name] = group

                    else:
                        # split inter-query times into multiple files by responder
                        # XXX ignore replot_only here, cause too difficult to check
                        last_time = 0.0
                        burst_start = 0.0
                        responders = {}
                        cum_time = {} 

		        with open(out1) as f:
                            lines = f.readlines()
                            for line in lines:
                                fields = line.split()
                                time = float(fields[0])
                                responder = fields[1] + '.' + fields[2]
                                if responder not in responders:
                                    out_name = out1 + '.' + responder 
                                    responders[responder] = open(out_name, 'w')
                                    out_files[responder] = out_name 
                                    cum_time[responder] = 0

                                out_f = responders[responder]

                                if burst_start == 0.0:
                                    burst_start = time
                                if line != lines[:-1] and last_time != 0.0 and time - last_time >= burst_sep:
                                    #cum_time[responder] += (last_time - burst_start)
                                    burst_start = time
                                    last_req_time = time
                                else:
                                    last_req_time = last_time
                                    if last_req_time == 0.0:
                                        last_req_time = time

                                if cumulative == '0':
                                    out_f.write('%s %f %f\n' % (' '.join(fields), (time - burst_start), (time - last_req_time)))
                                else:
                                    out_f.write('%s %f %f\n' % (' '.join(fields), cum_time[responder] + (time - burst_start),
                                                cum_time[responder] + (time - last_req_time)))

                                cum_time[responder] += time - burst_start
                                last_time = float(time)

                        for out_f in responders.values():
                            out_f.close()

                        # sort by responder name and set groups (ip+port)
                        for responder in sorted(responders.keys()):
                            out_name = out1 + '.' + responder
                            out_groups[out_name] = group
                            group += 1

        if by_responder == '0':
            group += 1
        else:
            group = 1


    return (test_id_arr, out_files, out_groups)


## Extract inter-query times for each query burst
## SEE _extract_incast_iqtimes()
@task
def extract_incast_iqtimes(test_id='', out_dir='', replot_only='0', source_filter='',
                           ts_correct='1', query_host='', by_responder='1', cumulative='0',
                           burst_sep='1.0'):
    "Extract incast inter-query times"
   
    _extract_incast_iqtimes(test_id, out_dir, replot_only, source_filter, ts_correct,
                            query_host, by_responder, cumulative, burst_sep)

    # done
    puts('\n[MAIN] COMPLETED extracting incast inter-query times %s \n' % test_id)


## Plot inter-query times
#  @param test_id Semicolon-separated list of test ID prefixes of experiments to analyse
#  @param out_dir Output directory for results
#  @param replot_only '1' don't extract raw data per test_ID if already done,
#                     '0' always extract raw data
#  @param source_filter Filter on specific flows to process
#  @param ts_correct '0' use timestamps as they are (default)
#                    '1' correct timestamps based on clock offsets estimated
#                        from broadcast pings
#  @param query_host Name of the host that sent the queries
#  @param by_responder '1' plot times for each responder separately
#                      '0' times for all responders
#  @param cumulative '0' raw inter-query time for each burst 
#                     '1' accumulated inter-query time over all bursts
#  @param burst_sep Time between burst (default 1.0), must be > 0 
#  @param min_values Ignore flows with equal less output values / packets
#  @param omit_const '0' don't omit anything,
#                    '1' omit any series that are 100% constant
#                       (e.g. because there was no data flow)
#  @param out_name File name prefix for resulting pdf file
#  @param diff_to_burst_start '0' print time diferences between requests, i.e.
#                       the times are the differences between request and previous
#                       request
#                       '1' print time differences between requests and first requests in
#                       burst (default) 
#   @param ymin Minimum value on y-axis
#   @param ymax Maximum value on y-axis
#   @param lnames Semicolon-separated list of legend names
#   @param stime Start time of plot window in seconds
#                (by default 0.0 = start of experiment)
#   @param etime End time of plot window in seconds (by default 0.0 = end of experiment)
#   @param pdf_dir Output directory for pdf files (graphs), if not specified it
#                  is the same as out_dir
#   @param ts_correct '0' use timestamps as they are (default)
#                     '1' correct timestamps based on clock offsets estimated
#                         from broadcast pings
#   @param plot_params Parameters passed to plot function via environment variables
#   @param plot_script Specify the script used for plotting, must specify full path
#                      (default is config.TPCONF_script_path/plot_contour.R)
#
# Note setting cumulative=1 and diff_to_burst_start=0 does produce a graph, but the
# graph does not make any sense. 
@task
def analyse_incast_iqtimes(test_id='', out_dir='', replot_only='0', source_filter='',
                    ts_correct='1', query_host='', by_responder='1', cumulative='0',
                    burst_sep='1.0', min_values='3', omit_const='0', ymin='0', ymax='0', lnames='',
                    stime='0.0', etime='0.0', out_name='', diff_to_burst_start='1',
                    pdf_dir='',  plot_params='', plot_script=''):
    "Plot incast inter-query times"

    if query_host == '':
        abort('Must specify query_host parameter')

    (test_id_arr,
     out_files,
     out_groups) = _extract_incast_iqtimes(test_id, out_dir, replot_only, source_filter, 
                            ts_correct, query_host, by_responder, cumulative, burst_sep) 

    (out_files, out_groups) = filter_min_values(out_files, out_groups, min_values)
    out_name = get_out_name(test_id_arr, out_name)

    if cumulative == '0':
        ylabel = 'Inter-query time (ms)'
    else:
        ylabel = 'Cumulative Inter-query time (ms)'

    if diff_to_burst_start == '1':
        ycolumn = 4
    else:
        ycolumn = 5

    if by_responder == '0' and cumulative == '0':
        out_name_add = '_iqtimes'
    elif by_responder == '0' and cumulative == '1':
        out_name_add = '_cum_iqtimes' 
    elif by_responder == '1' and cumulative == '0':
        out_name_add = '_iqtimes_responders'
    else:
        out_name_add = '_cum_iqtimes_responders'

    plot_time_series(out_name, out_files, ylabel, ycolumn, 1000, 'pdf',
                     out_name + out_name_add, pdf_dir=pdf_dir, aggr='', 
                     sort_flowkey='0', omit_const=omit_const, ymin=float(ymin), ymax=float(ymax), 
                     lnames=lnames, stime=stime, etime=etime, groups=out_groups,
                     plot_params=plot_params, plot_script=plot_script,
                     source_filter=source_filter)

    # done
    puts('\n[MAIN] COMPLETED plotting incast inter-query times %s\n' % out_name)


## Extract response times for each responder for incast experiments from tcpdump data 
#  @param test_id Semicolon-separated list of test ID prefixes of experiments to analyse
#  @param out_dir Output directory for results
#  @param replot_only '1' don't extract raw data per test_ID if already done,
#                     '0' always extract raw data 
#  @param source_filter Filter on specific flows to process
#  @param ts_correct '0' use timestamps as they are (default)
#                    '1' correct timestamps based on clock offsets estimated
#                        from broadcast pings
#  @param query_host Name of the host that sent the queries (s specified in config)
#  @param slowest_only '0' plot response times for individual responders 
#                      '1' plot slowest response time across all responders
#                      '2' plot time between first request and last response finished
#
# Intermediate files end in ".restimes", ".restimes.tscorr" 
# The files contain the following columns:
# 1. Timestamp the GET was sent
# 2. Burst number
# 3. Querier IP.port
# 4. Responder IP.port
# 5. Response time [seconds]
def _extract_incast_restimes(test_id='', out_dir='', replot_only='0', source_filter='',
                             ts_correct='1', query_host='', slowest_only='0'):
    "Extract incast response times"

    ifile_ext = '.dmp.gz'
    ofile_ext = '.restimes'

    abort_extract = False

    already_done = {}
    out_files = {}
    out_groups = {}

    if query_host == '':
        abort('Must specify query_host parameter')

    test_id_arr = test_id.split(';')
    if len(test_id_arr) == 0 or test_id_arr[0] == '':
        abort('Must specify test_id parameter')

    # Initialise source filter data structure
    sfil = SourceFilter(source_filter)

    group = 1
    for test_id in test_id_arr:

        # first process tcpdump files (ignore router and ctl interface tcpdumps)
        tcpdump_files = get_testid_file_list('', test_id,
                                       ifile_ext,
                                       'grep -v "router.dmp.gz" | grep -v "ctl.dmp.gz"')

        for tcpdump_file in tcpdump_files:
            # get input directory name and create result directory if necessary
            out_dirname = get_out_dir(tcpdump_file, out_dir)
            dir_name = os.path.dirname(tcpdump_file)

            if tcpdump_file.find(query_host) == -1:
                # ignore all dump files not taken at query host
                continue

            # unique flows
            flows = lookup_flow_cache(tcpdump_file)
            if flows == None:
                flows = _list(local('zcat %s | tcpdump -nr - "tcp" | '
                                'awk \'{ if ( $2 == "IP" ) { print $3 " " $5 " tcp" } }\' | '
                                'sed "s/://" | '
                                'sed "s/\.\([0-9]*\) /,\\1 /g" | sed "s/ /,/g" | '
                                'LC_ALL=C sort -u' %
                                tcpdump_file, capture=True))

                append_flow_cache(tcpdump_file, flows)

            # since client sends first packet to server, client-to-server flows
            # will always be first

            for flow in flows:

                src, src_port, dst, dst_port, proto = flow.split(',')

                # get external and internal addresses
                src, src_internal = get_address_pair_analysis(test_id, src, do_abort='0')
                dst, dst_internal = get_address_pair_analysis(test_id, dst, do_abort='0')

                if src == '' or dst == '':
                    continue

                # ignore flows with querier as destination
                if dst == query_host:
                    continue

                # flow name
                name = src_internal + '_' + src_port + \
                    '_' + dst_internal + '_' + dst_port
                # test id plus flow name
                if len(test_id_arr) > 1:
                    long_name = test_id + '_' + name
                else:
                    long_name = name

                # the two dump files
                dump1 = dir_name + '/' + test_id + '_' + src + ifile_ext

                # tcpdump filters and output file names
                # 'tcp[tcpflags] & tcp-push != 0' rule to extract only packets with push flag set 
                # (eliminate SYN, FIN, or ACKs without data)
                filter1 = 'host ' + dst_internal + ' && port ' + dst_port + \
                    ' && tcp[tcpflags] & tcp-push != 0'

                out1_tmp = out_dirname + test_id + '_' + name + ofile_ext + '.tmp'
                out1 = out_dirname + test_id + '_' + name + ofile_ext
                
                if long_name not in already_done:
                    if replot_only == '0' or not ( os.path.isfile(out1) ):
 
                        # Use "-A" option to tcpdump so we get the payload bytes 
                        # XXX this falls apart if snap size is not the default because of the magic -B 8
                        local(
                            'zcat %s | tcpdump -A -tt -nr - "%s" | grep -B 10 "GET" | egrep "IP" | '
                            'awk \'{ print $1 " " $3 " " $5; }\' | sed \'s/://\' > %s' %
                            (dump1, filter1, out1_tmp))
                        # get the last line, assume this is last packet of last request
                        local('zcat %s | tcpdump -tt -nr - "%s" | tail -1 | '
                              'awk \'{ print $1 " " $3 " " $5; }\' | sed \'s/://\' >> %s' % 
                            (dump1, filter1, out1_tmp))

                        # compute response times from each GET packet and corresponding final data packet
                        out_f = open(out1, 'w')
                        with open(out1_tmp) as f:
                            lines = f.readlines()
                            cnt = 0
                            last_src = ''
                            for line in lines:
                                fields = line.split()
                                if cnt % 2 == 0:
                                    # request
			            req_time = float(line.split()[0])
                                elif fields[1] != last_src:
                                    # response, unless the source is the same as for the last packet
                                    # (then we possibly have no response)
                                    res_time = float(fields[0]) - req_time
                                    out_f.write('%f %i %s %s %s\n' %  (req_time, int(cnt/2) + 1, fields[2], 
                                                                       fields[1], res_time))

                                last_src = fields[1] 
                                cnt += 1

                        out_f.close()
                        os.remove(out1_tmp)

                    already_done[long_name] = 1

                    if sfil.is_in(name):
                        if ts_correct == '1':
                            out1 = adjust_timestamps(test_id, out1, dst, ' ', out_dir)

                        out_files[long_name] = out1 
                        out_groups[out1] = group

        # check for consistency and abort if we see less response times for one responder
        max_cnt = 0
        for name in out_files:
            if out_groups[out_files[name]] == group:
                cnt = int(local('wc -l %s | awk \'{ print $1 }\'' %
                                out_files[name], capture=True)) 
                if max_cnt > 0 and cnt < max_cnt:
                    abort('Responder timed out in experiment %s' % test_id)
                if cnt > max_cnt:
                    max_cnt = cnt

        group += 1

    if slowest_only != '0':
        (out_files, out_groups) = get_slowest_response_time(out_files, out_groups,
                                  int(slowest_only) - 1)


    return (test_id_arr, out_files, out_groups)


## Extract response times for each responder for incast experiments 
## SEE _extract_restimes()
@task
def extract_incast_restimes(test_id='', out_dir='', replot_only='0', source_filter='',
                             ts_correct='1', query_host=''):
    "Extract incast response times"

    _extract_incast_restimes(test_id, out_dir, replot_only, source_filter, ts_correct,
                             query_host)

    # done
    puts('\n[MAIN] COMPLETED extracting incast response times %s \n' % test_id)


## Extract packet loss for flows using custom tool 
## XXX tool uses packet hash based on UDP/TCP payload, so only works with traffic
## that has unique payload bytes
## The extracted files have an extension of .loss. The format is CSV with the
## columns:
## 1. Timestamp RTT measured (seconds.microseconds)
## 2. 0/1  (0=arrived, 1=lost)
#  @param test_id Test ID prefix of experiment to analyse
#  @param out_dir Output directory for results
#  @param replot_only Don't extract data again that is already extracted
#  @param source_filter Filter on specific sources
#  @param ts_correct '0' use timestamps as they are (default)
#                    '1' correct timestamps based on clock offsets estimated
#                        from broadcast pings
#  @return Test ID list, map of flow names to interim data file names and 
#          map of file names and group IDs
def _extract_pktloss(test_id='', out_dir='', replot_only='0', source_filter='',
                     ts_correct='1'):
    "Extract packet loss of flows"

    ifile_ext = '.dmp.gz'
    ofile_ext = '.loss'

    already_done = {}
    out_files = {}
    out_groups = {}

    test_id_arr = test_id.split(';')
    if len(test_id_arr) == 0 or test_id_arr[0] == '':
        abort('Must specify test_id parameter')

    # Initialise source filter data structure
    sfil = SourceFilter(source_filter)

    #local('which pktloss.py')

    group = 1
    for test_id in test_id_arr:

        # first process tcpdump files (ignore router and ctl interface tcpdumps)
        tcpdump_files = get_testid_file_list('', test_id,
                                ifile_ext,
                                'grep -v "router.dmp.gz" | grep -v "ctl.dmp.gz"')

        for tcpdump_file in tcpdump_files:
            # get input directory name and create result directory if necessary
            out_dirname = get_out_dir(tcpdump_file, out_dir)
            dir_name = os.path.dirname(tcpdump_file)

            # get unique flows
            flows = lookup_flow_cache(tcpdump_file)
            if flows == None:
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

                append_flow_cache(tcpdump_file, flows)

            # since client sends first packet to server, client-to-server flows
            # will always be first

            for flow in flows:

                src, src_port, dst, dst_port, proto = flow.split(',')

                # get external and internal addresses
                src, src_internal = get_address_pair_analysis(test_id, src, do_abort='0')
                dst, dst_internal = get_address_pair_analysis(test_id, dst, do_abort='0')

                if src == '' or dst == '':
                    continue

                # flow name
                name = src_internal + '_' + src_port + \
                    '_' + dst_internal + '_' + dst_port
                rev_name = dst_internal + '_' + dst_port + \
                    '_' + src_internal + '_' + src_port
                # test id plus flow name
                if len(test_id_arr) > 1:
                    long_name = test_id + '_' + name
                    long_rev_name = test_id + '_' + rev_name
                else:
                    long_name = name
                    long_rev_name = rev_name

                if long_name not in already_done and long_rev_name not in already_done:

                    # the two dump files
                    dump1 = dir_name + '/' + test_id + '_' + src + ifile_ext
                    dump2 = dir_name + '/' + test_id + '_' + dst + ifile_ext

                    # filters for pktloss.py    
		    filter1 = src_internal + ':' + src_port + ':' + dst_internal + ':' + dst_port 
		    filter2 = dst_internal + ':' + dst_port + ':' + src_internal + ':' + src_port 
	
                    # output file names
                    out_loss = out_dirname + test_id + '_' + name + ofile_ext
                    rev_out_loss = out_dirname + test_id + '_' + rev_name + ofile_ext

                    if replot_only == '0' or not ( os.path.isfile(out_loss) and \
                                                   os.path.isfile(rev_out_loss) ):
                        # compute loss 
                        local(
                            'pktloss.py -t %s -T %s -f %s > %s' %
                            (dump1, dump2, filter1, out_loss))
                        local(
                            'pktloss.py -t %s -T %s -f %s > %s' %
                            (dump2, dump1, filter2, rev_out_loss))

                    already_done[long_name] = 1
                    already_done[long_rev_name] = 1

                    if sfil.is_in(name):
                        if ts_correct == '1':
                            out_loss = adjust_timestamps(test_id, out_loss, src, ' ', out_dir)
                        out_files[long_name] = out_loss
                        out_groups[out_loss] = group

                    if sfil.is_in(rev_name):
                        if ts_correct == '1':
                            rev_out_loss = adjust_timestamps(test_id, rev_out_loss, dst, ' ',
                                          out_dir)
                        out_files[long_rev_name] = rev_out_loss
                        out_groups[rev_out_loss] = group

        group += 1

    return (test_id_arr, out_files, out_groups)


## Extract packet loss for flows
## SEE _extract_pktloss()
@task
def extract_pktloss(test_id='', out_dir='', replot_only='0', source_filter='',
                    ts_correct='1'):
    "Extract packet loss of flows"

    _extract_pktloss(test_id, out_dir, replot_only, source_filter,
                     ts_correct)

    # done
    puts('\n[MAIN] COMPLETED extracting packet loss %s \n' % test_id)


## Plot packet loss rate for flows
#  @param test_id Test ID prefix of experiment to analyse
#  @param out_dir Output directory for results
#  @param replot_only Don't extract data again, just redo the plot
#  @param source_filter Filter on specific sources
#  @param min_values Minimum number of data points in file, if fewer points
#                    the file is ignored
#  @param omit_const '0' don't omit anything,
#                    '1' omit any series that are 100% constant
#                       (e.g. because there was no data flow)
#  @param ymin Minimum value on y-axis
#  @param ymax Maximum value on y-axis
#  @param lnames Semicolon-separated list of legend names
#  @param stime Start time of plot window in seconds
#               (by default 0.0 = start of experiment)
#  @param etime End time of plot window in seconds
#               (by default 0.0 = end of experiment)
#  @param out_name Name prefix for resulting pdf file
#  @param pdf_dir Output directory for pdf files (graphs), if not specified it is
#                 the same as out_dir
#  @param ts_correct '0' use timestamps as they are (default)
#                    '1' correct timestamps based on clock offsets estimated
#                        from broadcast pings
#  @param plot_params Set env parameters for plotting
#  @param plot_script Specify the script used for plotting, must specify full path
@task
def analyse_pktloss(test_id='', out_dir='', replot_only='0', source_filter='',
                min_values='3', omit_const='0', ymin='0', ymax='0',
                lnames='', stime='0.0', etime='0.0', out_name='', pdf_dir='',
                ts_correct='1', plot_params='', plot_script=''):
    "Plot packet loss rate of flows"

    (test_id_arr,
     out_files,
     out_groups) = _extract_pktloss(test_id, out_dir, replot_only,
                                    source_filter, ts_correct)

    (out_files, out_groups) = filter_min_values(out_files, out_groups, min_values)
    out_name = get_out_name(test_id_arr, out_name)

    plot_time_series(out_name, out_files, 'Packet loss (%)', 2, 1.0, 'pdf',
                     out_name + '_pktloss', pdf_dir=pdf_dir, omit_const=omit_const,
                     ymin=float(ymin), ymax=float(ymax), lnames=lnames, aggr='2',
                     stime=stime, etime=etime, groups=out_groups, plot_params=plot_params,
                     plot_script=plot_script, source_filter=source_filter)

    # done
    puts('\n[MAIN] COMPLETED plotting packet loss rate %s \n' % out_name)

