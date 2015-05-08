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
## @package filefinder
# Functions to find files (used by analysis functions) 
#
# $Id: filefinder.py 1287 2015-04-29 05:27:00Z szander $

import os
import config
from fabric.api import task, warn, local, run, execute, abort, hosts, env
from internalutil import _list

# 
# Directory cache functions
#

## Cache file name
CACHE_FILE_NAME = 'teacup_dir_cache.txt'
## Cache
dir_cache = {}

## Read cachfile if exists
def read_dir_cache():

    if not os.path.isfile(CACHE_FILE_NAME):
        return

    with open(CACHE_FILE_NAME, 'r') as f:
        lines = f.readlines()
        for line in lines:
            fields = line.split()
            dir_cache[fields[0]] = fields[1]


## Append to cache if entry not in there yet 
#  @param test_id Test ID
#  @param directory Directory which has files of the experiment with ID = test ID
def append_dir_cache(test_id, directory):

    if test_id not in dir_cache:
        with open(CACHE_FILE_NAME, 'a') as f:
            f.write('%s %s\n' % (test_id, directory))


## Perform cache lookup, if we have entry for test id return directory. Otherwise
# return '.'
#  @param test_id Test ID
def lookup_dir_cache(test_id):

    # load cache first if cache is empty
    if len(dir_cache) == 0:
        read_dir_cache()

    if test_id in dir_cache:
        return dir_cache[test_id]
    else:
        return '.'


## Filter out duplicates (if we accidentally have copies lying around in 
#  different subdirectories)
#  @param file_list List of file names
def filter_duplicates(file_list):

    file_names = {}
    filtered_file_list = []

    for f in file_list:
        base_name = os.path.basename(f)
        if base_name not in file_names:
            file_names[base_name] = 1
            filtered_file_list.append(f)

    return filtered_file_list


## Return list of files that match search criteria
#  @param file_list_fname Name of file containing a list of full log file names 
#  @param test_id Semicolon separated list of test ids
#  @param file_ext Characteristic rightmost part of file (file extension) we are
#                  searching for
#  @param pipe_cmd One or more shell command that are executed in pipe with the
#                  find command
#  @param search_dir Directory from where we start the search
#  @param no_abort Set to false means abort if no matching files are found (default)
#                  Set to true means don't abort if no matching files are found.
#  @return List of files found 
def get_testid_file_list(file_list_fname='', test_id='', file_ext='', pipe_cmd='',
                         search_dir='.', no_abort=False):

    file_list = []

    # if search dir is not specified try to find it in cache
    if search_dir == '.':
        search_dir = lookup_dir_cache(test_id)

    if file_list_fname == '':
        # read from test_id list specified, this always overrules list in file if
        # also specified

        test_id_arr = test_id.split(';')

        if len(test_id_arr) == 0 or test_id_arr[0] == '':
            abort('Must specify test_id parameter')

        if pipe_cmd != '':
            pipe_cmd = ' | ' + pipe_cmd

        for test_id in test_id_arr:
            _files = _list(
                local(
                    'find -L %s -name "%s*%s" -print | sed -e "s/^\.\///"%s' %
                    (search_dir, test_id, file_ext, pipe_cmd),
                    capture=True))

            _files = filter_duplicates(_files)
 
            if search_dir == '.' and len(_files) > 0:
                append_dir_cache(test_id, os.path.dirname(_files[0]))

            file_list += _files
    else:
        # read list of test ids from file 

        try:
            lines = []
            with open(file_list_fname) as f:
                lines = f.readlines()
            for fname in lines:
                fname = fname.rstrip()
                _files = _list(
                    local(
                        'find -L %s -name "%s" -print | sed -e "s/^\.\///"' %
                        (search_dir, fname),
                        capture=True))

                _files = filter_duplicates(_files)

                if search_dir == '.' and len(_files) > 0:
                    append_dir_cache(test_id, os.path.dirname(_files[0]))

                file_list += _files

        except IOError:
            abort('Cannot open experiment list file %s' % file_list_fname)

    if not no_abort and len(file_list) == 0:
        abort('Cannot find any matching data files.\n'
              'Remove outdated teacup_dir_cache.txt if files were moved.') 

    return file_list

