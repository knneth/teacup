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
# Plot functions included by other scripts
#
# $Id: plot_func.R 958 2015-02-12 04:52:49Z szander $

#library(gplots)


inFromCm <- function(cm) {
        return(cm/2.54)
}


create_file <- function(fname, type)
{

        if (type == "svg") {
                #devSVGTips(paste(fname,".svg",sep=""), width=2*width+inFromCm(7), 
                #           height=2*height, toolTipFontSize=max(pointsize,8), 
                #           toolTipMode=1)
        } else if (type == "eps") {
                postscript(paste(fname,".eps",sep=""), width=width+1, 
                           height=height, pointsize=pointsize, 
                           horizontal=FALSE, onefile=FALSE)
        } else if (type == "png") {
                png(paste(fname,".png",sep=""), width=png_width, 
                    height=png_height, units="px", pointsize=pointsize)
        } else if (type == "wmf") {
                win.metafile(paste(fname,".wmf",sep=""), width=width+1, 
                             height=height, pointsize=pointsize)
        } else if (type == "fig") {
                xfig(paste(fname,".fig",sep=""), width=width+1, 
                     height=height, pointsize=pointsize, horizontal=FALSE, 
                     textspecial=T)
        } else {
                pdf(paste(fname,".pdf",sep=""), width=width+1, height=height, 
                    pointsize=pointsize)
        }
}

# set some defaults (can still be overriden in R file with plot commands)

width <- inFromCm(9.45)
height <- inFromCm(8)
pointsize <- 10
linset <- 0.0

# max number of series in one graph
max_series <- 12
ltys <- rep(1, max_series)
cols <- c("blue", "lightsteelblue2", "darkorange3", "orange", "deeppink", "violetred4",
          "red", "black", "yellow", "aquamarine2", "gray", "green")
pchs <- c(21,24,4,3,22,23,25,15,16,17,18,8)
cexs <- rep(plot_point_size, max_series)
cexs[12] = plot_point_size * 0.86 # make this a bit smaller

