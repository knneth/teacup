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
# Point thinning function 
#
# $Id: point_thinning.R 958 2015-02-12 04:52:49Z szander $

# distance for point thinning
tmp = Sys.getenv("PTHIN_DIST_FAC")
pthin_dist_fac = 0
if (tmp != "") {
        pthin_dist_fac = as.numeric(tmp)
}

# distance for point thinning
tmp = Sys.getenv("PTHIN_DIST")
pthin_dist = 0
if (tmp != "") {
        pthin_dist = as.numeric(tmp)
}

# point thinning
# XXX improve performance of this
pthin <- function(data, yindex)
{

        if (pthin_dist == 0 && pthin_dist_fac == 0) { # exit quickly
                return(data)
        }

	if (stime == 0) {
		stime_tmp = 0
	} else {
		stime_tmp = stime
	}
	if (etime == 0) {
		etime_tmp = max(data[,1]) - min(data[,1])
	} else {
		etime_tmp = etime
	}
        if (ymin_user == 0) {
                ymin_tmp = min(data[,yindex]) 
        } else {
                ymin_tmp = ymin_user 
        }
        if (ymax_user == 0) {
                ymax_tmp = max(data[,yindex])
        } else {
                ymax_tmp = ymax_user
        }
        xrange = etime_tmp - stime_tmp
        yrange = ymax_tmp - ymin_tmp 

        if (pthin_dist > 0) {
		pthin_dist_x = pthin_dist
		pthin_dist_y = pthin_dist
	} else {
        	pthin_dist_x = pthin_dist_fac * xrange
		pthin_dist_y = pthin_dist_fac * yrange
	}

	print(paste(pthin_dist_x, pthin_dist_y))

        mask = integer(length(data[,1]))
        mask[1] = 1
        last = data[1,]
        for (i in c(2:length(data[,1]))) {
                if ((abs(data[i,1] - last[1,1]) >= pthin_dist_x) ||
                    (abs(data[i,yindex] - last[1,yindex]) >= pthin_dist_y)) {
                        mask[i] = 1
                        last = data[i,]
                }
        }

        return(data[mask==1,])
}


