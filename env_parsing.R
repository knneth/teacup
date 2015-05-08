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
# Environment variable parsing used by the different plot scripts 
# (common variables only, variables used only by a particular script
#  should be defined in that script)
#
# $Id: env_parsing.R 958 2015-02-12 04:52:49Z szander $


# y-axis label
ylab = Sys.getenv("YLAB")
# separator in data file
sep = Sys.getenv("SEP")
if (sep == "") {
        sep = " "
}
# output file prefix
oprefix = Sys.getenv("OPREFIX")
# output type (e.g. pdf)
otype = Sys.getenv("OTYPE")
if (otype == "") {
        otype = "svg"
}
# output directory
odir = Sys.getenv("ODIR")
if (odir != "") {
        oprefix = paste(odir, oprefix, sep="")
}
# input data
tmp = Sys.getenv("FNAMES")
if (tmp != "") {
        fnames = strsplit(tmp, ",", fixed=T)[[1]]
} else {
        fnames = c()
}
print(fnames)
# legend names
tmp = Sys.getenv("LNAMES")
if (tmp != "") {
        lnames = strsplit(tmp, ",", fixed=T)[[1]]
} else {
        lnames = c()
}
print(lnames)
# plot title 
title = Sys.getenv("TITLE")
# min y value
ymin_user = Sys.getenv("YMIN")
if (ymin_user == "") {
        ymin_user = 0
} else {
        ymin_user = as.numeric(ymin_user)
} 
# max y value
ymax_user = Sys.getenv("YMAX")
if (ymax_user == "") {
        ymax_user = 0
} else {
        ymax_user = as.numeric(ymax_user)
} 
# yaxis max increase for legend space
ymax_inc = Sys.getenv("YMAX_INC")
if (ymax_inc == "") {
        ymax_inc = 0.09
} else {
        ymax_inc = as.numeric(ymax_inc)
}
# start/end time of plot
tmp = Sys.getenv("STIME")
stime = 0
if (tmp != "") {
        stime = as.numeric(tmp)
}
tmp = Sys.getenv("ETIME")
etime = 0
if (tmp != "") {
        etime = as.numeric(tmp)
}
# size of points in plot
tmp = Sys.getenv("POINT_SIZE")
plot_point_size = 0.5
if (tmp != "") { 
        plot_point_size = as.numeric(tmp)
}

