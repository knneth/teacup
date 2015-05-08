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
# Plot metrics for different parameter combinations 
#
# $Id: plot_cmp_experiments.R 1302 2015-05-01 07:47:33Z szander $

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
# MERGE_GROUPS: '0' plot each different group separately
#               '1' collaspe all groups into one
# NOTE THAT MERGE_GROUPS IS DEPRECATED BUT STILL HERE FOR BACKWARDS COMPATIBILITY
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
# NICER_XLABS: '0' or unset means XLABS is printed as is
#              '1' means only the values in XLABS are printed underneath the ticks,
#              while the names are only printed once on the left side 
# NOMINAL_RES_TIME: '0' don't plot nominal response times
#                   '1' plot nominal response times
# RATIO_RES_TIME: '0' normal plot
#                 '1' plot ratio of median/mean response time and nominal
#                     response time
# NO_BARS: '0' by default median and mean are plotted as bars
#          '1' plot median and mean as points
# OTYPE:  type of output file (can be 'pdf', 'eps', 'png', 'fig')
# OPREFIX: the prefix (first part) of the graph file name
# ODIR:   directory where output files, e.g. pdf files are placed
# OMIT_CONST: '0' don't omit anything,
#             '1' omit any data series from plot that are 100% constant 
# OUTLIER_QUANT: omit any values in the quantiles less than OUTLIER_QUANT and
#                larger than 1 - OUTLIER_QUANT
# POINT_SIZE: controls the size of points. POINT_SIZE does not specify an
#             absolute point size, it is a scaling factor that is multiplied with
#             the actual default point size (default is 1.0). 
# PTYPE: type of plot, can be 'box', 'mean' or 'median'
# SEP:    column separator used in data file (default is single space)
# STIME:  start time on x-axis (for zooming in), default is 0.0 meaning the start 
#         of an experiment
# TITLE:  character string that is plotted over the graph
# XLABS:  comma-separated list of character strings that must have the same
#         length as the number of variable combinations plotted. Each string is
#         describes the combination and is placed underneath the x-axis tick mark.
#         The format of one string must be: <name1>_<value2>\n<name2>_<value2>\n ...
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
# x labels
tmp = Sys.getenv("XLABS")
if (tmp != "") {
        xlabs = strsplit(tmp, ",", fixed=T)[[1]]
} else {
        xlabs = c()
}
print(xlabs)
# aggregation function
aggr = Sys.getenv("AGGR")
# change to non-cummulative
diff = Sys.getenv("DIFF")
# omit any series with constant value
omit_const = Sys.getenv("OMIT_CONST")
if (omit_const == "" || omit_const == "0") {
	omit_const = FALSE
} else {
	omit_const = TRUE 
}
# type of plot
ptype = Sys.getenv("PTYPE")
# don't plot lowest/highest x quantiles
outlier_quant = Sys.getenv("OUTLIER_QUANT")
if (outlier_quant == "") {
	outlier_quant = 0
} else {
	outlier_quant = as.numeric(outlier_quant)
}
# plot nicer x-axis labels (paramter names on the left)
tmp = Sys.getenv("NICER_XLABS")
nicer_xlabs = FALSE
if (tmp != "" && tmp != "0") {
	nicer_xlabs = TRUE
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
# merge groups 
merge_groups = Sys.getenv("MERGE_GROUPS")
if (merge_groups == "" || merge_groups == "0") {
        merge_groups = FALSE
} else {
        merge_groups = TRUE
}
# nominal response time
tmp = Sys.getenv("NOMINAL_RES_TIME")
if (tmp == "" || tmp == "0") {
        nominal_res_time = FALSE
} else {
        nominal_res_time = TRUE
}
# response time ratio
tmp = Sys.getenv("RATIO_RES_TIME")
if (tmp == "" || tmp == "0") {
        ratio_res_time = FALSE
} else {
        ratio_res_time = TRUE
}
# use points instead of bars 
tmp = Sys.getenv("NO_BARS")
if (tmp == "" || tmp == "0") {
        no_bars = FALSE
} else {
        no_bars = TRUE
}


# source basic plot stuff
source(paste(base_dir, "plot_func.R", sep="/"), verbose=F)


# function to get parameter values for parameters encoded in file name
get_param_value <- function(fname, param)
{
	fields = strsplit(basename(fname), "_", fixed=T)[[1]]
        for (i in c(1:length(fields))) {
		if (fields[i] == param) {
			val = fields[i + 1]

                        # make sure we get number for bandwidth
                        val = gsub("kbit", "000", val)
                        val = gsub("mbit", "000000", val)
		
  			val = as.numeric(val)
                        #print(paste("VALUE",val))

			if (is.numeric(val)) {
                        	return(val)
			}
		}	
	}

	return(0) 
}

# function to compute the percentage
percentage <- function(x)
{
        return ( as.numeric(sum(x)) / as.numeric(length(x)) * 100.0 )
}

# main

curr_fnames = fnames

data = list()
i = 1
xmin = 1e99 
xmax = 0
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

	# filter max int values (e.g. tcp rtt estimate is set to max int 
        # on windows for non-smoothed)
	data[[i]] = data[[i]][data[[i]][,2] < 4294967295,]

	data[[i]][,2] = data[[i]][,2] * yscaler 

	if (max(data[[i]][,2]) > ymax) {
		ymax = max(data[[i]][,2])	
	}
	if (min(data[[i]][,2]) < ymin) {
                ymin = min(data[[i]][,2])
        }
	if (min(data[[i]][,1]) < xmin) {
                xmin = min(data[[i]][,1])
        }
	if (max(data[[i]][,1]) > xmax) {
                xmax = max(data[[i]][,1])
        }
	i = i + 1
}

# normalise time to start with zero
for (i in c(1:length(data))) {
	data[[i]][,1] = data[[i]][,1] - min(data[[i]][,1]) 
}
xmax = xmax - xmin

if (diff == "1") {
        for (i in c(1:length(data))) {
                diff_vals = diff(data[[i]][,2])
                data[[i]] = data[[i]][-1,]
                data[[i]][,2] = diff_vals
        }
}

if (aggr != "" && aggr != "0") {
	ymin = 1e99
        ymax = 0
        xmax = 0

        for (i in c(1:length(data))) {

		window_size = aggr_win_size # window in seconds
                interpolate_steps = aggr_int_factor # "oversampling" factor
                iseq = seq(0, window_size, by=window_size/interpolate_steps)
                iseq = iseq[-length(iseq)] # remove full window size 
                data_out = data.frame()
                for (x in iseq) {
                        tmp = data[[i]]
                        tmp[,1] = floor((tmp[,1] - x)*(1/window_size))

                        if (aggr == "1") {
                                # throughput
                                myfun=sum
                        } else if (aggr == "2") {
                                # packet loss
                                myfun=percentage
                        }

                        data_out = rbind(data_out, cbind(
                                         data.frame(as.numeric(levels(factor(tmp[,1])))/(1/window_size) + 
                                                    x + (1/interpolate_steps)/2 + window_size/2), 
                                         data.frame(tapply(tmp[,-1], tmp[,1], FUN=myfun))))
                }
                data[[i]] = data_out[order(data_out[,1]),]
                if (aggr == "1") {
                        # throughput
                        data[[i]][,2] = data[[i]][,2] * (1/window_size)
                } else if (aggr == "2") {
                        # packet loss
                        data[[i]][,2] = data[[i]][,2]
                }
                #print(data[[i]])

                if (max(data[[i]][,2]) > ymax) {
                        ymax = max(data[[i]][,2])
                }
                if (min(data[[i]][,2]) < ymin) {
                        ymin = min(data[[i]][,2])
                }
                if (max(data[[i]][,1]) > xmax) {
                        xmax = max(data[[i]][,1])
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

# filter data and adjust ymax accordingly
if (stime > 0.0 || etime < max(xmax)) {
        ymax = 0
        for (i in c(1:length(data))) {

		data[[i]] = data[[i]][data[[i]][,1] >= stime & data[[i]][,1] <= etime,]

                ymax_zoom = max(data[[i]][,2])
                if (ymax_zoom > ymax) {
                        ymax = ymax_zoom
                }
        }
}


# get a list of only the data vectors
for (i in c(1:length(data))) {
	data[[i]] = data[[i]][,2]
}

# optionally remove outliers
if (outlier_quant > 0) {
	ymin = 1e99
        ymax = 0

	for (i in c(1:length(data))) {
                ol = quantile(data[[i]], 0 + outlier_quant)
                oh = quantile(data[[i]], 1 - outlier_quant)
                print(paste("OUTLIER", ol, oh))
                data[[i]] = data[[i]][data[[i]]>=ol & data[[i]]<=oh]

		if (max(data[[i]]) > ymax) {
                        ymax = max(data[[i]])
                }
                if (min(data[[i]]) < ymin) {
                        ymin = min(data[[i]])
                }
	}
}



# adjust width based on number of x-axis labels
if (length(xlabs) > 8) {
	width = width * length(xlabs)/8
}

out_name = paste(oprefix,"_cmp_exp",sep="")
print(out_name)
create_file(out_name, otype)

if (ymax_user != 0) {
	ymax = ymax_user
}
ymin=0
# if user specified maximum, then take user value
if (ymin_user != 0) {
        ymin = ymin_user
}

par(mar=c(4.6, 5.1, 2.1, 3.6))
par(las=1) # always vertical labels
f = 1 + ceiling(length(lnames)/3) * ymax_inc 

# optionally collapse groups
if (merge_groups) {
	ndata = list()
	for (i in c(1:(length(data) / length(lnames)))) {
        	ndata[[i]] = vector() 
		for (j in c(1:length(lnames))) {
			ndata[[i]] = append(ndata[[i]], data[[length(lnames) * (i-1) + j]])
		}
	}	
	lnames = c("Merged groups")
	data = ndata
}

atvec = vector()
atvec_axis = vector()
atcols = vector()
atvec_xgrid = vector()
g = length(data) / length(lnames)
for (i in c(1:g)) {
	atvec_axis = append(atvec_axis, i * length(lnames))
}
atvec = c(1:length(data))
atcols = rep(cols[1:length(lnames)], g)
atvec_axis = atvec_axis - length(lnames)/2 + 0.5
for (x in atvec_axis) {
	atvec_xgrid = append(atvec_xgrid, x - length(lnames)/2) 
	atvec_xgrid = append(atvec_xgrid, x + length(lnames)/2) 
}

print(atvec)
print(atvec_axis)
print(atcols)

if (ratio_res_time || nominal_res_time) {
        # plot nominal response time
        nom_rtimes = vector()

        for (fname in fnames) {
                inc_size = get_param_value(fname, "incSz")
                bandwidth = get_param_value(fname, "down")
                responders = get_param_value(fname, "responders")

                nom_rtimes = append(nom_rtimes, inc_size * 1024 * responders / (bandwidth/8))
        }
}

if (ptype == "box") {
	boxplot(data, at=atvec, col=atcols, bg=atcols, cex=cexs[1], ylab=ylab, 
                ylim=c(0, ymax*f), main = title, cex.main=0.5, axes=FALSE)
	grid(nx=NA, ny=NULL)
	abline(v=atvec_xgrid, lty=3, col="lightgray")
	boxplot(data, at=atvec, col=atcols, bg=atcols, cex=cexs[1], axes=FALSE, 
                add=TRUE)
} else {
	yvals = matrix(0, g, length(lnames))
	xvals = matrix(0, g, length(lnames))

	for (j in c(1:length(lnames))) {
		ymax = 0 # XXX avoid doing this again
		for (i in c(1:g)) {
			xvals[i,j] = i * length(lnames) - length(lnames) + j 
			print(paste(i,j,xvals[i,j]))
			if (ptype == "mean") {
				yvals[i,j] = mean(data[[xvals[i,j]]])
			} else if (ptype == "median") {
				yvals[i,j] = median(data[[xvals[i,j]]])
			}

			if (yvals[i,j] > ymax) {
				ymax = yvals[i,j]
			}
		}	 
	}

	if (ymax_user != 0) {
		ymax = ymax_user
	}

        if (no_bars) {
      		plot_type="p"
                plot_lwd=1
	} else {
		plot_type="h"
                plot_lwd=4
	}

        if (ratio_res_time) {
		for (j in c(1:length(lnames))) {
			yvals[,j] = yvals[,j] / nom_rtimes
		}
                print(yvals)
	}

	plot(xvals[,1], yvals[,1], type=plot_type, lwd=plot_lwd, lend=1, pch=pchs[1], col=cols[1], 
             bg=cols[1], cex=cexs[1], xlab="", ylab=ylab, xlim=c(1, length(data)), 
             ylim=c(ymin, ymax*f), main = title, cex.main=0.5, axes=F)
	grid(nx=NA, ny=NULL)
	abline(v=atvec_xgrid, lty=3, col="lightgray")
	for (j in c(1:length(lnames))) {
		points(xvals[,j], yvals[,j], type=plot_type, lwd=plot_lwd, lend=1, pch=pchs[j], 
                       col=cols[j], bg=cols[j], cex=cexs[j])	
	}
}

if (nominal_res_time) {
	points(c(1:length(nom_rtimes)), nom_rtimes, pch=22, cex=plot_point_size ,
               col="red", bg="red")
}

# if we have fewer labels than xaxis points, but the points divided by the labels is
# an integer number than speculate that we want to have fewer xaxis points
# for example, we have this case if we filter on sender in incast scenarios with
# multiple responders
if (length(xlabs) < length(atvec_axis) && length(atvec_axis) %% length(xlabs) == 0) {
	new_vec = c(1:length(xlabs)) * (length(atvec_axis) / length(xlabs)) - 
                  (length(atvec_axis) / length(xlabs))/2
        atvec_axis = new_vec
}

# font size for x-axis text
# the font sizes are set with cex.axis and cex. we scale the fonts based on 
# xlab_vars_cnt and there is always a maximum size, so the code is
# min(<maximum>, 1/xlab_vars_cnt*<scaler>). to adjust the sizes modify the maximum or
# the scaling factor or set size to a constant value that works for a certain
# scenario. 

axis(1, at=atvec_axis, labels=FALSE)
xlab_vars_cnt = max(sapply(strsplit(as.character(xlabs), split= "\n"), length))
if (nicer_xlabs) {
	xlab_vars = strsplit(as.character(xlabs), split= "\n")
	var_names = unlist(strsplit(xlab_vars[[1]], split= " "))
	var_names = var_names[seq(1, length(var_names), by=2)]
	for (name in var_names) {
		xlabs = gsub(paste(name, " ", sep=""), "", xlabs) 
	}

        # plot parameters values under x-axis ticks
	axis(1, at=atvec_axis, labels= xlabs, cex.axis=min(0.8, 1/xlab_vars_cnt*2.4), 
             padj=0, line= xlab_vars_cnt/2 - 0.5, tick=FALSE)

        # plot names to the left of y-xis right-aligned to y-axis 
	mtext(paste(var_names, sep="", collapse="\n"), 1, line= xlab_vars_cnt/2 + 0.5, 
              at= par("usr")[1], adj=1, cex = min(0.8, 1/xlab_vars_cnt*2.4))
} else {
        # plot parameter names plus values under x-axis ticks
	axis(1, at=atvec_axis, labels= xlabs, cex.axis=min(0.4, 1/xlab_vars_cnt*2.4), 
             padj=0, line= xlab_vars_cnt/4 - 0.5, tick=FALSE)
}

axis(2, cex.axis=1)

# set number of columns in legend to a maximum of 3, but smaller if we have less 
# categories
if (length(lnames) <= 3) {
	ncol = length(lnames)
} else {
	ncol = 3
}

#legend("topleft", ncol=ncol, inset=linset, legend=lnames, pch=pchs, col=cols, pt.bg=cols, 
#       pt.cex=cexs, cex=0.52, border=NA, bty="o", bg="white", box.col="white")
if (nominal_res_time) {
	lnames = append(lnames, "Nominal response time")
        cols[length(lnames)] = "red"
        pchs[length(lnames)] = 22
        cexs[length(lnames)] = plot_point_size 
}
if (ptype != "box" && no_bars) {
	legend("topleft", ncol=ncol, inset=linset, legend=lnames, col=cols, pch=pchs, pt.bg=cols, 
                pt.cex=cexs, cex=0.52, border=NA, bty="o", bg="white", box.col="white")
} else {
        # XXX cheating here for nominal response times by just plotting a filled square and not 
        # a square point symbols. this means the legen square will havw wrong size unless 
        # POINT_SIZE=0.75
	legend("topleft", ncol=ncol, inset=linset, legend=lnames, fill=cols, cex=0.52, border=NA, 
       		bty="o", bg="white", box.col="white")
}

box()

dev.off()

