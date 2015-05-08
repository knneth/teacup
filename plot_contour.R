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
# Plot contour of distrbutions, looks like a bubble graph but technically
# a bubble graph is different 
#
# $Id: plot_time_series.R 958 2015-02-12 04:52:49Z szander $

# Evironment parameters that control the script (alphabetical order):
# ADD_RAND:  '0' default 
#            '1' add randomness unif(-0.5, 0.5) to values, looks better with
#                discrete values
# AGGR:   comma-separated list with two entries (first for x-axis, second for y-axis) 
#         '0' means plot data as is, i.e. values over time
#         '1' means data is aggregated over time intervals, more specifically
#         the data (specified by YINDEXES) is summed over the time intervals (used 
#         to determine throughput over time windows based on packet lengths)  
#         (in the future could use other values to signal different aggregations)
# AGGR_WIN_SIZE: size of the aggregation window in seconds (default is 1 second)
# AGGR_INT_FACTOR: factor for oversampling / overlapping windows (default is 4
#                  meaning we get 4 times the number of samples compared to non-
#                  overlapping windows) 
# BINS:    number of bins for density estimation
# DIFF:    convert cummulative data into non-cummulative data
# ELLIPSE: '0' by default will plot the actual 2d density distributions
#          '1' will plot data ellipses
# XFNAMES: comma-separated list of x-axis file names (each file contains one date series,
#         e.g. data for one flow). The format of each file is CSV-style, but the
#         separator does not have to be a comma (can be set with SEP[0]). The first
#         column contains the timestamps. The second, third etc. columns contain
#         data, but only one of these columns will be plotted (which is set with 
#         YINDEXES[0]). 
# YFNAMES: comma-separated list of y-axis file names (each file contains one date series,
#         e.g. data for one flow). The format of each file is CSV-style, but the
#         separator does not have to be a comma (can be set with SEP[1]). The first
#         column contains the timestamps. The second, third etc. columns contain
#         data, but only one of these columns will be plotted (which is set with 
#         YINDEXES[1]). YFNAMES must have the same length as XFNAMES. 
# GROUPS: comma-separated list of group IDs (integer numbers). This list must  
#         have the same length as XFNAMES and YFNAMES. The data is grouped using colour
#         as per the specified group numbers. 
# LNAMES: comma-separated list of legend names. this list has the same length
#         as XFNAMES, YFNAMES and GROUPS and each entry corresponds to data from 
#         a XFNAMES/YFNAMES pair. legend names must be character strings that do
#         not contain commas.
# MEDIAN: '0' by default don't plot median
#         '1' plot median for each group
# NO_LEGEND: '0' plot legend (default)
#            '1' don't plot legend
# OTYPE:  type of output file (can be 'pdf', 'eps', 'png', 'fig')
# OPREFIX: the prefix (first part) of the graph file name
# ODIR:   directory where output files, e.g. pdf files are placed
# OUTLIER_QUANT: omit any values in the quantiles less than OUTLIER_QUANT and
#                larger than 1 - OUTLIER_QUANT
# SCATTER: '0' by default points are not plotted
#          '1' plot points (scatter plot) as well as the density or ellipse
# XSEP:   column separators used in the x-axis data files for XFNAMES data. 
# YSEP:   column separators used in the y-axis data files for YFNAMES data. 
# TITLE:  character string that is plotted over the graph
# XMIN:   minimum value on x-axis (for zooming in), default is 0
# XMAX:   maximum value on y-axis (for zooming in), default is 0 meaning the 
#         maximum value is determined from the data
# YMIN:   minimum value on y-axis (for zooming in), default is 0 
# YMAX:   maximum value on y-axis (for zooming in), default is 0 meaning the 
#         maximum value is determined from the data
# YMAX_INC: YMAX_INC controls the space for the legend. It assumes the legend is 
#           plotted at the top (default). The actual y-axis maximum for the plot 
#           will be y_max*(1+YMAX_INC), where y_max is the maximum based on the data
#           or the specified YMAX 
# XLAB:   X-axis label character string
# YLAB:   y-axis label character string
# YINDEXES: comma-separated list of indexes of data column in data files. The list
#           must have exactly two entries, one index for x-axis data files and one
#           for y-axis data files  
# YSCALERS: comma-separated list of factors which are multiplied with each data value 
#           before plotting. Again, must have length two, first factor for x-axis and
#           second factor for y-axis.

library(MASS) # kde2d
library(ggplot2)

# our current dir
argv = commandArgs(trailingOnly = F)
print(argv)
base_dir = dirname(argv[grep(".R", argv, fixed = T)])
print(base_dir)

# get common environment variables
source(paste(base_dir, "env_parsing.R", sep="/"), verbose=F)

# x-axis label
xlab = Sys.getenv("XLAB")

# input data
tmp = Sys.getenv("XFNAMES")
if (tmp != "") {
        xfnames = strsplit(tmp, ",", fixed=T)[[1]]
} else {
        xfnames = c()
}
print(xfnames)

# input data
tmp = Sys.getenv("YFNAMES")
if (tmp != "") {
        yfnames = strsplit(tmp, ",", fixed=T)[[1]]
} else {
        yfnames = c()
}
print(yfnames)

# separators in data file
xsep = Sys.getenv("XSEP")
print(xsep)
ysep = Sys.getenv("YSEP")
print(ysep)

# min x value
xmin_user = Sys.getenv("XMIN")
if (xmin_user == "") {
        xmin_user = 0
} else {
        xmin_user = as.numeric(xmin_user)
}
# max y value
xmax_user = Sys.getenv("XMAX")
if (xmax_user == "") {
        xmax_user = 0
} else {
        xmax_user = as.numeric(xmax_user)
}

# bins
bins = Sys.getenv("BINS")
if (bins == "") {
        bins = 4 
} else {
        bins = as.numeric(bins)
}


# index of data to plot on y-axis
tmp = Sys.getenv("YINDEXES")
if (tmp != "") {
        yindexes = as.numeric(strsplit(tmp, ",", fixed=T)[[1]])
} else {
        yindexes = c(2,2)
}
print(yindexes)

# scaler for y values
tmp = Sys.getenv("YSCALERS")
if (tmp != "") {
        yscalers = as.numeric(strsplit(tmp, ",", fixed=T)[[1]])
} else {
        yscalers = c(1.0,1.0)
}
print(yscalers)

# specify group # for each file
tmp = Sys.getenv("GROUPS")
if (tmp != "") {
        groups = as.numeric(as.character(strsplit(tmp, ",", fixed=T)[[1]]))
} else {
        groups = c(1)
}
print(groups)

# aggregation function
tmp = Sys.getenv("AGGRS")
if (tmp != "") {
        aggrs = strsplit(tmp, ",", fixed=T)[[1]]
} else {
        aggrs = c("0", "0")
}
print(aggrs)

# non-cummulative conversion
tmp = Sys.getenv("DIFFS")
if (tmp != "") {
        diffs = strsplit(tmp, ",", fixed=T)[[1]]
} else {
        diffs = c("0", "0")
}
print(diffs)

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

# don't plot lowest/highest x quantiles
outlier_quant = Sys.getenv("OUTLIER_QUANT")
if (outlier_quant == "") {
        outlier_quant = 0
} else {
        outlier_quant = as.numeric(outlier_quant)
}

# add randomness
add_rand = Sys.getenv("ADD_RAND")

# ellipse plot
ellipse = Sys.getenv("ELLIPSE")

# plot median
plot_median = Sys.getenv("MEDIAN")

# plot points (scatter plot)
plot_scatter = Sys.getenv("SCATTER")

# control if legend is plotted
no_legend = Sys.getenv("NO_LEGEND")

# maxmimum number of points for one group
# (with too many points the point mapping takes forever)
MAX_DATA_POINTS = 10000


# source basic plot stuff
source(paste(base_dir, "plot_func.R", sep="/"), verbose=F)

icols = list()

# green
icols[[1]] = c("#ffffff", "#edf8fb", "#b2e2e2", "#66c2a4", "#2ca25f", "#006d2c")
# blue
icols[[2]] = c("#ffffff", "#f1eef6", "#bdc9e1", "#74a9cf", "#2b8cbe", "#045a8d")
# red
icols[[3]] = c("#ffffff", "#fef0d9", "#fdcc8a", "#fc8d59", "#e34a33", "#b30000")
# purple
icols[[4]] = c("#ffffff", "#edf8fb", "#b3cde3", "#8c96c6", "#8856a7", "#810f7c")
# pink
icols[[5]] = c("#ffffff", "#f1eef6", "#d7b5d8", "#df65b0", "#dd1c77", "#980043")
# grey
icols[[6]] = c("#ffffff", "#f7f7f7", "#cccccc", "#969696", "#636363", "#252525")

cols <- c("#006d2c", "#045a8d", "#b30000", "#810f7c", "#980043", "#252525")

# main

no_groups = length(levels(factor(groups)))

xdata = list()
ydata = list()
xmin = 1e99 
xmax = 0
ymin = 1e99
ymax = 0  

#
# read data and aggregate if needed
#

i = 1
for (fname in xfnames) {
	xdata[[i]] = read.table(fname, header=F, sep=xsep, na.strings="foobla")
  
        xdata[[i]] = xdata[[i]][,c(1,yindexes[1])]

	# filter max int values (e.g. tcp rtt estimate is set to max int on 
        # windows for non-smoothed)
	xdata[[i]] = xdata[[i]][xdata[[i]][,2] < 4294967295,]

	xdata[[i]][,2] = xdata[[i]][,2] * yscalers[1] 

        # down sample, as it takes forever with too many data points
        if (length(xdata[[i]][,1]) > MAX_DATA_POINTS) {
        	s = sample(c(1:length(xdata[[i]][,1])), MAX_DATA_POINTS)
		xdata[[i]] = xdata[[i]][s,]
	}

        i = i + 1
}

if (diffs[1] == "1") {
	for (i in c(1:length(xdata))) {
		diff_vals = diff(xdata[[i]][,2])
		xdata[[i]] = xdata[[i]][-1,]
        	xdata[[i]][,2] = diff_vals
	}
}

if (aggrs[1] == "1") {
        for (i in c(1:length(xdata))) {
                window_size = aggr_win_size # window in seconds
                interpolate_steps = aggr_int_factor # "oversampling" factor
                iseq = seq(0, window_size, by=window_size/interpolate_steps)
                iseq = iseq[-length(iseq)] # remove full window size 
                data_out = data.frame()
                for (x in iseq) {
                        tmp = xdata[[i]]
                        tmp[,1] = floor((tmp[,1] - x)*(1/window_size))
                        data_out = rbind(data_out, cbind(
                                       data.frame(as.numeric(levels(factor(tmp[,1])))/(1/window_size) +
                                                  x + (1/interpolate_steps)/2 + window_size/2),
                                       data.frame(tapply(tmp[,-1], tmp[,1], FUN=sum))))
                }
                xdata[[i]] = data_out[order(data_out[,1]),]
                xdata[[i]][,2] = xdata[[i]][,2] * (1/window_size)
                #print(xdata[[i]])
        }
}

i = 1
for (fname in yfnames) {
        ydata[[i]] = read.table(fname, header=F, sep=ysep, na.strings="foobla")

        ydata[[i]] = ydata[[i]][,c(1,yindexes[2])]

 	# filter max int values (e.g. tcp rtt estimate is set to max int on 
        # windows for non-smoothed)
        ydata[[i]] = ydata[[i]][ydata[[i]][,2] < 4294967295,]

        ydata[[i]][,2] = ydata[[i]][,2] * yscalers[2]

        # down sample, as it takes forever with too many data points
        if (length(ydata[[i]][,1]) > MAX_DATA_POINTS) {
		s = sample(c(1:length(ydata[[i]][,1])), MAX_DATA_POINTS)
        	ydata[[i]] = ydata[[i]][s,]
	}

 	i = i + 1
}

if (diffs[2] == "1") {
	for (i in c(1:length(ydata))) {
        	diff_vals = diff(ydata[[i]][,2])
        	ydata[[i]] = ydata[[i]][-1,]
        	ydata[[i]][,2] = diff_vals
	}
}

if (aggrs[2] == "1") {
        for (i in c(1:length(ydata))) {

                window_size = aggr_win_size # window in seconds
                interpolate_steps = aggr_int_factor # "oversampling" factor
                iseq = seq(0, window_size, by=window_size/interpolate_steps)
                iseq = iseq[-length(iseq)] # remove full window size 
                data_out = data.frame()
                for (x in iseq) {
                        tmp = ydata[[i]]
                        tmp[,1] = floor((tmp[,1] - x)*(1/window_size))
                        data_out = rbind(data_out, cbind(
                                       data.frame(as.numeric(levels(factor(tmp[,1])))/(1/window_size) +
                                                  x + (1/interpolate_steps)/2 + window_size/2),
                                       data.frame(tapply(tmp[,-1], tmp[,1], FUN=sum))))
                }
                ydata[[i]] = data_out[order(data_out[,1]),]
                ydata[[i]][,2] = ydata[[i]][,2] * (1/window_size)
                #print(ydata[[i]])
	}
}

#
# Remove outliers
#

# optionally remove outliers
if (outlier_quant > 0) {
        for (i in c(1:length(xdata))) {
                ol = quantile(xdata[[i]][,2], 0 + outlier_quant)
                oh = quantile(xdata[[i]][,2], 1 - outlier_quant)
                print(paste("OUTLIER", ol, oh))
                xdata[[i]] = xdata[[i]][xdata[[i]][,2]>=ol & xdata[[i]][,2]<=oh,]
        }
        for (i in c(1:length(ydata))) {
                ol = quantile(ydata[[i]][,2], 0 + outlier_quant)
                oh = quantile(ydata[[i]][,2], 1 - outlier_quant)
                print(paste("OUTLIER", ol, oh))
                ydata[[i]] = ydata[[i]][ydata[[i]][,2]>=ol & ydata[[i]][,2]<=oh,]
        }
}

#
# map x and y values
#

for (i in c(1:length(xdata))) {
	if (length(xdata[[i]][,1]) < length(ydata[[i]][,1])) {
		iter_data = xdata[[i]]
		other_data = ydata[[i]]
	} else {
		iter_data = ydata[[i]]
		other_data = xdata[[i]]
	}
	
	red_data = matrix(0, 0, length(other_data[1,]))
	for (j in (1:length(iter_data[,1]))) {
                timestamp = iter_data[j,1]
	        closest_idx = which.min(abs(other_data[,1] - timestamp))
		red_data = rbind(red_data, other_data[closest_idx,])
	}

	if (length(xdata[[i]][,1]) < length(ydata[[i]][,1])) {
                ydata[[i]] = red_data
        } else {
                xdata[[i]] = red_data
        }
        print(dim(xdata[[i]]))
        print(dim(ydata[[i]]))
}

#
# get minimum/maximum for the data
#

for (i in c(1:length(xdata))) {
        if (max(xdata[[i]][,2]) > xmax) {
                xmax = max(xdata[[i]][,2])
        }
        if (min(xdata[[i]][,2]) < xmin) {
                xmin = min(xdata[[i]][,2])
        }
}

for (i in c(1:length(ydata))) {
        if (max(ydata[[i]][,2]) > ymax) {
                ymax = max(ydata[[i]][,2])
        }
        if (min(ydata[[i]][,2]) < ymin) {
                ymin = min(ydata[[i]][,2])
        }
}

# if user specified maximum, then take user value
if (xmax_user != 0) {
        xmax = xmax_user
}

#xmin = 0
# if user specified maximum, then take user value
if (xmin_user != 0) {
        xmin = xmin_user
}


# if user specified maximum, then take user value
if (ymax_user != 0) {
	ymax = ymax_user
}

#ymin=0
# if user specified maximum, then take user value
if (ymin_user != 0) {
        ymin = ymin_user
}

if (ellipse == "1") {
	out_name = paste(oprefix,"_ellipse_plot",sep="")
} else {
	out_name = paste(oprefix,"_2d_density_plot",sep="")
}
print(out_name)


create_file(out_name, otype)

par(mar=c(4.6, 5.1, 2.1, 4.6))
par(las=1) # always vertical labels
f = 1 + ceiling(length(data) / 2) * ymax_inc 

#plot(0, 0, type="p", pch=pchs[1], col="white", bg="white", 
#     cex=cexs[1], xlab=xlab, ylab=ylab, xlim=c(xmin, xmax), ylim=c(ymin, ymax*f), 
#     main = title, cex.main=0.5, axes=T)

#grid()

#for (i in c(1:length(xdata))) {
#for (i in c(1:1)) {
 #       mydensity <- kde2d(xdata[[i]][,2],ydata[[i]][,2], 
                           #n=361, lims=c(xmin,xmax,ymin,ymax), h=c(10,10))
 #                          n=50, lims=c(xmin,xmax,ymin,ymax))
  #      print(summary(mydensity))
  #      mypalette = colorRampPalette(icols[[groups[i]]]) 
  # XXX with filled.contour we cannot plot multiple density plots on the same plot
        #filled.contour(mydensity, nlevels=5, color.palette = mypalette, 
  #      filled.contour(mydensity, nlevels=5, col=icols[[groups[i]]], add=TRUE) 
        #filled.contour(mydensity,  
        #       axes = FALSE, frame.plot = FALSE)
#}

#legend("topleft", ncol=2, inset=linset, legend=lnames, fill=cols, col=cols, 
#       pt.cex=cexs, cex=0.52, border=NA, bty="o", bg="white", box.col="white")

#box()

# get same number of samples for each group_by value, down sample if necessary
#min_samples = 1e99
#for (i in c(1:length(xdata))) {
#	if (length(xdata[[i]][,2]) < min_samples) {
#		min_samples = length(xdata[[i]][,2])
#	}
#}
#for (i in c(1:length(xdata))) {
#	s = sample(c(1:length(xdata[[i]][,2])), min_samples)
#	xdata[[i]] = xdata[[i]][s,]
#	ydata[[i]] = ydata[[i]][s,]
#}

xvals_vec = vector()
yvals_vec = vector()
group_vec = factor()
for (i in c(1:length(xdata))) {
	xvals_vec = append(xvals_vec, xdata[[i]][,2]) 
}
for (i in c(1:length(ydata))) {
        yvals_vec = append(yvals_vec, ydata[[i]][,2])
}
for (i in c(1:length(xdata))) {
	group_vec = append(group_vec, rep(lnames[groups[i]], length(xdata[[i]][,1])))
}

# add some randomness, since we have discrete values
# can make the distributions look better, but also makes them look different a bit
if (add_rand == "1") {
	xvals_vec = xvals_vec + runif(length(xvals_vec), -0.5, 0.5)
	yvals_vec = yvals_vec + runif(length(yvals_vec), -0.5, 0.5)
        xvals_vec[xvals_vec<0] = 0
        yvals_vec[yvals_vec<0] = 0
        xmin = max(xmin - 1, 0)
        ymin = max(ymin - 1, 0)
        xmax = xmax + 1
        ymax = ymax + 1
}

print(xvals_vec)
print(yvals_vec)
print(group_vec)
dat <- data.frame(xvals = xvals_vec, yvals = yvals_vec, group = factor(group_vec, levels=lnames)) 
print(dat)
print(summary(dat[,1]))
print(summary(dat[,2]))

# get a label list so we can place labels in the graph
# XXX problem is to get the positions right, this seems to be unsolvable in the general case
#lxvals_vec = vector()
#lyvals_vec = vector()
#for (f in levels(factor(dat$group))) {
#	lxvals_vec = append(lxvals_vec, quantile(dat[as.factor(dat$group)==f,1], 0.5))
#	lyvals_vec = append(lyvals_vec, quantile(dat[as.factor(dat$group)==f,2], 0.6) + runif(1, -3,3))
#}
#ldat <- data.frame(xvals = lxvals_vec, yvals = lyvals_vec, group = levels(factor(dat$group)))
#print(ldat)

# give a bit more space, otherwise ellipses start looking weird
xmin = xmin * 0.95
xmax = xmax * 1.05
ymin = ymin * 0.95
ymax = ymax * 1.05

print(xmin)
print(xmax)
print(ymin)
print(ymax)

p = ggplot()

if (ellipse == "1") {
	p = p +	stat_ellipse(data=dat, mapping= aes(x = xvals, y=yvals, colour = group, fill = group), 
                             geom="polygon", alpha=1/2, size = 0.25) +
                #geom_text(data=ldat, aes(label=group, x = xvals + 90), size=4) +
                ggplot2::xlab(xlab) + ggplot2::ylab(ylab) +
                ggplot2::xlim(xmin, xmax) + ggplot2::ylim(ymin, ymax) +
                labs(title=title) +
                theme_bw(base_size=9) +
                theme(plot.title = element_text(size = 6))
} else {
	p = p + stat_density2d(data=dat, mapping=aes(x = xvals, y=yvals, colour = group, fill = group, 
                               alpha = ..level..), bins=bins, geom="polygon", size = 0.25) +
        	#scale_alpha_continuous(limits=c(0,0.5),breaks=seq(0,0.5,by=0.1)) + 
        	ggplot2::xlab(xlab) + ggplot2::ylab(ylab) +
        	ggplot2::xlim(xmin, xmax) + ggplot2::ylim(ymin, ymax) +
        	labs(title=title) +
        	theme_bw(base_size=9) +
                theme(plot.title = element_text(size = 6))
}

if (plot_scatter == "1") {
        p = p + geom_point(data=dat, mapping=aes(x = xvals, y=yvals, colour = group, fill = group), size = 0.3)
}

if (plot_median == "1") {
	for (f in levels(factor(dat$group))) {
                # take the median in each dimension (not necessarily the best solution, but easy)
		x = median(dat[dat$group==f,1])
		y = median(dat[dat$group==f,2])

                mp = data.frame(x=x, y=y)
                print(mp)

                p = p + geom_point(data=mp, mapping=aes(x, y), colour = "black", shape = 21, size = 1.5)
	}
}

if (no_legend == "1") {
	p = p + guides(colour=FALSE, fill=FALSE, alpha=FALSE)
}

# execute plot command
p

dev.off()

