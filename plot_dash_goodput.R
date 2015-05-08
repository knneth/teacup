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
# Plot DASH-like client goodput over time 
#
# $Id: plot_dash_goodput.R 958 2015-02-12 04:52:49Z szander $

# Evironment parameters that control the script (alphabetical order):
# ETIME:  end time on x-axis (for zooming in), default is 0.0 meaning the end of an
#         experiment a determined from the data
# FNAMES: comma-separated list of file names (each file contains one date series,
#         e.g. data for one flow). The format of each file is CSV-style, but the
#         separator does not have to be a comma (can be set with SEP). The first
#         column contains the timestamps. The second, third etc. columns contain
#         data, but only one of these columns will be plotted (which is set with 
#         YINDEX). 
# LNAMES: comma-separated list of legend names. this list has the same length
#         as FNAMES and each entry corresponds to data in file name with the
#         same index in FNAMES. legend names must be character strings that do
#         not contain commas.
# NO_NOMINAL: '0' or unset means a line for nominal throughput is plotted
#             '1' means line for nominal throughput is NOT plotted
# OTYPE:  type of output file (can be 'pdf', 'eps', 'png', 'fig')
# OPREFIX: the prefix (first part) of the graph file name
# ODIR:   directory where output files, e.g. pdf files are placed
# POINT_SIZE: controls the size of points. POINT_SIZE does not specify an
#             absolute point size, it is a scaling factor that is multiplied with
#             the actual default point size (default is 1.0). 
# SEP:    column separator used in data file (default is single space)
# STIME:  start time on x-axis (for zooming in), default is 0.0 meaning the start 
#         of an experiment
# TITLE:  character string that is plotted over the graph
# YMIN:   minimum value on y-axis (for zooming in), default is 0 
# YMAX:   maximum value on y-axis (for zooming in), default is 0 meaning the 
#         maximum value is determined from the data
# YMAX_INC: YMAX_INC controls the space for the legend. It assumes the legend is 
#           plotted at the top (default). The actual y-axis maximum for the plot 
#           will be y_max*(1+YMAX_INC), where y_max is the maximum based on the data
#           or the specified YMAX 
# YLAB:   y-axis label character string


# our current dir
argv = commandArgs(trailingOnly = F)
print(argv)
base_dir = dirname(argv[grep(".R", argv, fixed = T)])
print(base_dir)

# get common environment variables
source(paste(base_dir, "env_parsing.R", sep="/"), verbose=F)

# don't plot line with nominal/set throughput
tmp = Sys.getenv("NO_NOMINAL")
no_nominal = FALSE
if (tmp != "" && tmp != "0") {
	no_nominal = TRUE
}

# source basic plot stuff
source(paste(base_dir, "plot_func.R", sep="/"), verbose=F)

# main

data = list()
i = 1
xmin = 1e99 
xmax = 0
ymin = 1e99
ymax = 0
len = 1
nominal_idx = 1
for (fname in fnames) {
	data[[i]] = read.table(fname, header=F, sep=sep, na.strings="NA")

	data[[i]] = data[[i]][complete.cases(data[[i]]),]

	# sum up the actual downloaded
	data[[i]][,2] = cumsum(data[[i]][,2])
	# scale to MB
	data[[i]][,2] = data[[i]][,2] / 1e6

	# get nominal bytes
	data[[i]][,6] = data[[i]][,6] * data[[i]][,5] / 8
	# generate times for ideal
	data[[i]][,5] = cumsum(data[[i]][,5])
	# sum up the nominal
	data[[i]][,6] = cumsum(data[[i]][,6])
	# scale to MB
	data[[i]][,6] = data[[i]][,6] / 1e3

	i = i + 1
}

for (i in c(1:length(data))) {
	data[[i]][,1] = data[[i]][,1] - data[[i]][1,1] + data[[i]][,4] 

	# add zero point
        data[[i]] = rbind(rep(0, 7), data[[i]])

	if (max(data[[i]][,1]) > xmax) {
                xmax = max(data[[i]][,1])
        }
	if (max(data[[i]][,5]) > xmax) {
                xmax = max(data[[i]][,5])
        }

	if (max(data[[i]][,2]) > ymax) {
                ymax = max(data[[i]][,2])
        }
	if (max(data[[i]][,6]) > ymax) {
                ymax = max(data[[i]][,6])
        }
        if (min(data[[i]][,2]) < ymin) {
                ymin = min(data[[i]][,2])
        }
	# determine which data series is longest, from that we plot the 
        # nominal transferred
	if (length(data[[i]][,1]) > len) {
		len = length(data[[i]][,1])
		nominal_idx = i
	}

	print(data[[i]])
}

# plot only specific time window
if (stime < 0 || stime > max(xmax)) {
        stime = 0.0
}
if (etime <= 0 || etime > max(xmax)) {
        etime = max(xmax)
}

# if we zoom on x-axis adjust ymax accordingly
if (stime > 0.0 || etime < max(xmax)) {
        ymax = 0
        for (i in c(1:length(data))) {
                ymax_zoom = max(data[[i]][data[[i]][,1]>=stime & data[[i]][,1]<=etime, 2])
                if (ymax_zoom > ymax) {
                        ymax = ymax_zoom
                }
        }
}

# if user specified maximum, then take user value
if (ymax_user != 0) {
        ymax = ymax_user
}

ymin=0
# if user specified maximum, then take user value
if (ymin_user != 0) {
        ymin = ymin_user
}



print(paste(oprefix,"_accumulated",sep=""))
create_file(paste(oprefix,"_accumulated",sep=""), otype)

par(mar=c(4.6, 5.1, 2.1, 4.6))
par(las=1) # always vertical labels
f = 1 + ceiling(length(data)/2) * ymax_inc 
if (no_nominal == FALSE) {
	plot(data[[nominal_idx]][,5], data[[nominal_idx]][,6], type="b", pch=pchs[1], 
             col=cols[1], bg=cols[1], cex=cexs[1], xlab="Time (s)", ylab=ylab, 
             xlim=c(stime, etime), ylim=c(ymin, ymax*f), main = title, cex.main=0.5, 
             axes=T)
} else {
	plot(data[[1]][,1], data[[1]][,2], type="b", pch=pchs[1], col=cols[1], 
             bg=cols[1], cex=cexs[1], xlab="Time (s)", ylab=ylab, xlim=c(stime, etime), 
             ylim=c(ymin, ymax*f), main = title, cex.main=0.5, axes=T)
}

grid()

if (no_nominal == FALSE) {
	points(data[[nominal_idx]][,5], data[[nominal_idx]][,6], type="b", pch=pchs[1], 
               col=cols[1], bg=cols[1], cex=cexs[1])
}

for (i in c(1:length(data))) {
	if (no_nominal == FALSE) {
		idx = i+1
	} else {
		idx = i
	}
	points(data[[i]][,1], data[[i]][,2], type="b", pch=pchs[idx], col=cols[idx], 
               bg=cols[idx], cex=cexs[idx])
}

if (no_nominal == FALSE) {
	lnames = append("Nominal", lnames)
}
legend("topleft", ncol=1, inset=linset, legend=lnames, pch=pchs, col=cols, pt.bg=cols, 
       pt.cex=cexs, cex=0.6, border=NA, bty="o", bg="white", box.col="white")

box()

dev.off()

