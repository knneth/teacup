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
# Plot throughput RTT, CWN, TCP parameter over time 
#
# $Id: plot_time_series.R 1012 2015-02-20 07:21:57Z szander $

# Evironment parameters that control the script (alphabetical order):
# AGGR:   '0' means plot data as is, i.e. values over time
#         '1' means data is aggregated over time intervals, more specifically
#         the data (specified by YINDEX) is summed over the time intervals (used 
#         to determine throughput over time windows based on packet lengths)  
#         (in the future could use other values to signal different aggregations)
# AGGR_WIN_SIZE: size of the aggregation window in seconds (default is 1 second)
# AGGR_INT_FACTOR: factor for oversampling / overlapping windows (default is 4
#                  meaning we get 4 times the number of samples compared to non-
#                  overlapping windows) 
# BOXPL:  '0' plot each point on time axis (x-axis)
#         '1' plot a boxplot over all data points from all data seres for each 
#         distinct timestamp (instead of a point for each a data series) 
# ETIME:  end time on x-axis (for zooming in), default is 0.0 meaning the end of an
#         experiment a determined from the data
# FNAMES: comma-separated list of file names (each file contains one date series,
#         e.g. data for one flow). The format of each file is CSV-style, but the
#         separator does not have to be a comma (can be set with SEP). The first
#         column contains the timestamps. The second, third etc. columns contain
#         data, but only one of these columns will be plotted (which is set with 
#         YINDEX). 
# GROUPS: comma-separated list of group IDs (integer numbers). This list must  
#         have the same length as FNAMES. If data from different experiments is plotted,
#         each experiment will be assigned a different number and these are passed
#         via GROUPS. This allows the plotting function to determine which data
#         series are (or are not) from the same experiment, so that results 
#         from different experiments, that started at different times, can be 
#         plotted in the same graph.
# LNAMES: comma-separated list of legend names. this list has the same length
#         as FNAMES and each entry corresponds to data in file name with the
#         same index in FNAMES. legend names must be character strings that do
#         not contain commas.
# OTYPE:  type of output file (can be 'pdf', 'eps', 'png', 'fig')
# OPREFIX: the prefix (first part) of the graph file name
# ODIR:   directory where output files, e.g. pdf files are placed
# OMIT_CONST: '0' don't omit anything,
#             '1' omit any data series from plot that are 100% constant 
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
# YINDEX: index of data column in file to plot on y-axis (since file can have more 
#         than one data column)
# YSCALER: factor which is multiplied with each data value before plotting

# our current dir
argv = commandArgs(trailingOnly = F)
print(argv)
base_dir = dirname(argv[grep(".R", argv, fixed = T)])
print(base_dir)

# get common environment variables
source(paste(base_dir, "env_parsing.R", sep="/"), verbose=F)

# index of data to plot on y-axis
yindex = Sys.getenv("YINDEX")
if (yindex == "") {
        yindex = 2 
} else {
        yindex = as.numeric(yindex) 
} 
# scaler for y values
yscaler = Sys.getenv("YSCALER")
if (yscaler == "") {
	yscaler = 1.0
} else {
	yscaler = as.numeric(yscaler)
} 
# specify group # for each file
tmp = Sys.getenv("GROUPS")
if (tmp != "") {
        groups = as.numeric(as.character(strsplit(tmp, ",", fixed=T)[[1]]))
} else {
        groups = c(1)
}
# aggregation function
aggr = Sys.getenv("AGGR")
# boxplot per time point
boxpl = Sys.getenv("BOXPL")
# omit any series with constant value
omit_const = Sys.getenv("OMIT_CONST")
if (omit_const == "" || omit_const == "0") {
	omit_const = FALSE
} else {
	omit_const = TRUE 
}
# window size in seconds for aggregation
tmp = Sys.getenv("AGGR_WIN_SIZE")
aggr_win_size = 1.0 
if (tmp != "") {
	aggr_win_size = as.numeric(tmp)
}
# interpolation factor for aggregation
tmp = Sys.getenv("AGGR_INT_FACTOR")
aggr_int_factor = 4 
if (tmp != "") {
        aggr_int_factor = as.numeric(tmp)
}

# source basic plot stuff
source(paste(base_dir, "plot_func.R", sep="/"), verbose=F)

# source point thinning
source(paste(base_dir, "point_thinning.R", sep="/"), verbose=F)


# main

# we can only plot 12 series in one graph, if we have more than 12 create 
# multiple graphs
series_cnt = ceiling(length(fnames) / 12)

for (series_no in c(1:series_cnt)) {

start = (series_no - 1) * max_series + 1
if (series_no < series_cnt) {
        end = series_no * max_series
} else {
        end = length(fnames)
}

curr_fnames = fnames[start:end]
curr_lnames = lnames[start:end]

no_groups = length(levels(factor(groups)))

data = list()
i = 1
xmin = rep(1e99, no_groups) 
xmax = rep(0, no_groups)
ymin = 1e99
ymax = 0  
for (fname in curr_fnames) {
	data[[i]] = read.table(fname, header=F, sep=sep, na.strings="foobla")

        data[[i]] = data[[i]][,c(1,yindex)]

	if (omit_const) {
		if (sd(data[[i]][,2]) == 0) {
			curr_lnames = curr_lnames[-i]
			next	
		}
	}		

	# filter max int values (e.g. tcp rtt estimate is set to max int on 
        # windows for non-smoothed)
	data[[i]] = data[[i]][data[[i]][,2] < 4294967295,]

	data[[i]][,2] = data[[i]][,2] * yscaler 

	if (aggr == "") {
		# point thinning
		data[[i]] = pthin(data[[i]], 2)
	}

	if (max(data[[i]][,2]) > ymax) {
		ymax = max(data[[i]][,2])	
	}
	if (min(data[[i]][,2]) < ymin) {
                ymin = min(data[[i]][,2])
        }
	if (min(data[[i]][,1]) < xmin[groups[i]]) {
                xmin[groups[i]] = min(data[[i]][,1])
        }
	if (max(data[[i]][,1]) > xmax[groups[i]]) {
                xmax[groups[i]] = max(data[[i]][,1])
        }
	i = i + 1
}


# normalise time to start with zero
for (i in c(1:length(data))) {
        data[[i]][,1] = data[[i]][,1] - xmin[groups[i]]
}
for (i in c(1:no_groups)) {
	xmax[i] = xmax[i] - xmin[i]
}


if (aggr != "") {
	ymin = 1e99
	ymax = 0
	xmax = rep(0, no_groups)

	for (i in c(1:length(data))) {

		window_size = aggr_win_size # window in seconds
		interpolate_steps = aggr_int_factor # "oversampling" factor
		iseq = seq(0, window_size, by=window_size/interpolate_steps)
		iseq = iseq[-length(iseq)] # remove full window size 
		data_out = data.frame()
		for (x in iseq) {
			tmp = data[[i]]
			tmp[,1] = floor((tmp[,1] - x)*(1/window_size))
			data_out = rbind(data_out, cbind(
                                       data.frame(as.numeric(levels(factor(tmp[,1])))/(1/window_size) + 
                                                  x + (1/interpolate_steps)/2 + window_size/2), 
                                       data.frame(tapply(tmp[,-1], tmp[,1], FUN=sum))))
		}
		data[[i]] = data_out[order(data_out[,1]),]
		data[[i]][,2] = data[[i]][,2] * (1/window_size)
		#print(data[[i]])

		# point thinning
                data[[i]] = pthin(data[[i]], 2)

		if (max(data[[i]][,2]) > ymax) {
        	        ymax = max(data[[i]][,2])
	        }
        	if (min(data[[i]][,2]) < ymin) {
                	ymin = min(data[[i]][,2])
        	}
		if (max(data[[i]][,1]) > xmax[groups[i]]) {
                        xmax[groups[i]] = max(data[[i]][,1])
                }
	}
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

if (series_cnt > 1) {
	# append series index to name
	out_name = paste(oprefix,"_time_series_",series_no,sep="")
} else {
	out_name = paste(oprefix,"_time_series",sep="")
}
print(out_name)


if (boxpl == "1") {
	# adjust width based on number of x-axis labels
	print(paste('nogroups', no_groups))
        width = width * no_groups 
}


create_file(out_name, otype)

par(mar=c(4.6, 5.1, 2.1, 4.6))
par(las=1) # always vertical labels
f = 1 + ceiling(length(data) / 2) * ymax_inc 

if (boxpl == "" || boxpl == "0") {

plot(data[[1]][,1], data[[1]][,2], type="p", pch=pchs[1], col=cols[1], bg=cols[1], 
     cex=cexs[1], xlab="Time (s)", ylab=ylab, xlim=c(stime, etime), ylim=c(ymin, ymax*f), 
     main = title, cex.main=0.5, axes=T)

grid()

for (i in c(1:length(data))) {
	points(data[[i]][,1], data[[i]][,2], type="p", pch=pchs[i], col=cols[i], 
               bg=cols[i], cex=cexs[i])
}

legend("topleft", ncol=2, inset=linset, legend=curr_lnames, pch=pchs, col=cols, pt.bg=cols,
       pt.cex=cexs, cex=0.52, border=NA, bty="o", bg="white", box.col="white")

} else {

# get a no_groups lists for each point in time where each list is a vector of all the
# response times for all the responders for each group (experiment)
pdata = list()
for (i in c(1:length(data[[1]][,1]))) {
        for (g in c(1:no_groups)) {
		ind = no_groups * (i - 1) + g 
        	pdata[[ind]] = vector() 
           	for (j in c(1:length(data))) {
                        if (as.numeric(groups[j]) == g) {
	         		pdata[[ind]] = append(pdata[[ind]], data[[j]][i,2])
			}
	   	}
	}
}
print(pdata)

atvec  = vector()
atcols = vector()

g = length(pdata) / no_groups 
for (i in c(1:g)) {
        for (j in c(1:no_groups)) {
		atvec = append(atvec, data[[1]][i,1] - no_groups + 2*j-1)
	}
}
atcols = rep(cols[1:no_groups], g)

if (length(lnames) != no_groups) {
	lnames = vector()
	for (i in c(1:no_groups)) {
		lnames = append(lnames, paste("Experiment", i))
	}
}
print(atvec)
print(atcols)
print(lnames)

boxplot(pdata, col=atcols, bg=atcols, at=atvec, boxwex=1,
     cex=cexs[1], xlab="Time (s)", ylab=ylab, xlim=c(stime, etime), ylim=c(ymin, ymax*f), 
     main = title, cex.main=0.5, axes=F)

axis(1)
axis(2)

grid()
abline(v=data[[1]][,1], lty=3, col="lightgrey")

boxplot(pdata, col=atcols, bg=atcols, at=atvec, boxwex=1, 
     cex=cexs[1], xlab="Time (s)", ylab=ylab, xlim=c(stime, etime), ylim=c(ymin, ymax*f),
     main = title, cex.main=0.5, axes=F, add=T)

if (length(lnames) > 1) {
	legend("topleft", ncol=2, inset=linset, legend=lnames, fill=cols,
       		pt.cex=cexs, cex=0.52, border=NA, bty="o", bg="white", box.col="white")
}

}

box()

dev.off()

}
