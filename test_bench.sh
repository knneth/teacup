#!/bin/sh

TEST_OUTDIR=/home/szander/experiment/plot_test_0.8/testing
TEST_OUTNAME="TESTING"

exit_with_error()
{
	echo "ERROR ERROR ERROR ERROR ERROR ERROR"
        # exit with error
	exit 1
}

set -vx

#
# analyse_cmpexp
#
TASK=analyse_cmpexp
METRICS="spprtt tcprtt cwnd throughput ackseq iqtime"
PTYPES="box mean median"

# restime
M=restime
for P in $PTYPES ; do 
	NICER_XLABS=1 fab $TASK:exp_list=different_responders_explist.txt,out_dir=$TEST_OUTDIR,metric=$M,ptype=$P,source_filter=S_172.16.10.60_*,omit_const_xlab_vars=1,out_name=$TEST_OUTNAME,merge_data=1,slowest_only=0,res_time_mode=0 || exit_with_error 
	fab $TASK:exp_list=different_responders_explist.txt,out_dir=$TEST_OUTDIR,metric=$M,ptype=$P,source_filter=S_172.16.10.60_*,out_name=$TEST_OUTNAME,merge_data=0,slowest_only=0,res_time_mode=0,replot_only=1 || exit_with_error 
	fab $TASK:exp_list=different_responders_explist.txt,out_dir=$TEST_OUTDIR,metric=$M,ptype=$P,source_filter=S_172.16.10.60_*,out_name=$TEST_OUTNAME,merge_data=0,slowest_only=1,res_time_mode=0,replot_only=1 || exit_with_error 
	fab $TASK:exp_list=different_responders_explist.txt,out_dir=$TEST_OUTDIR,metric=$M,ptype=$P,source_filter=S_172.16.10.60_*,out_name=$TEST_OUTNAME,merge_data=0,slowest_only=0,res_time_mode=1,replot_only=1 || exit_with_error 
	fab $TASK:exp_list=different_responders_explist.txt,out_dir=$TEST_OUTDIR,metric=$M,ptype=$P,source_filter=S_172.16.10.60_*,out_name=$TEST_OUTNAME,merge_data=0,slowest_only=0,res_time_mode=2,replot_only=1 || exit_with_error 
        #restime based on tcpdump data is not implemented yet
	#fab $TASK:exp_list=different_responders_explist.txt,out_dir=$TEST_OUTDIR,metric=$M,ptype=$P,source_filter=S_172.16.10.60_*,out_name=$TEST_OUTNAME,merge_data=0,slowest_only=0,res_time_mode=2,tcpdump=1,query_host=newtcp20 || exit_with_error 
done

# other metrics
for M in $METRICS ; do
	for P in $PTYPES ; do
                if [ "$M" = "iqtime" ] ; then
                	QHOST=",query_host=newtcp20"
                else
			QHOST=""
		fi
		#fab $TASK:exp_list=different_responders_explist.txt,out_dir=$TEST_OUTDIR,metric=$M,ptype=$P,source_filter=S_172.16.10.60_*,out_name=$TEST_OUTNAME,replot_only=1,merge_data=0$QHOST || exit_with_error
		#NICER_XLABS=1 fab $TASK:exp_list=different_responders_explist.txt,out_dir=$TEST_OUTDIR,metric=$M,ptype=$P,source_filter=S_172.16.10.60_*,omit_const_xlab_vars=1,out_name=$TEST_OUTNAME,replot_only=1,merge_data=0$QHOST || exit_with_error
		#fab $TASK:exp_list=different_responders_explist.txt,out_dir=$TEST_OUTDIR,metric=$M,ptype=$P,source_filter=S_172.16.10.60_*,out_name=$TEST_OUTNAME,replot_only=1,merge_data=1$QHOST || exit_with_error
	done
done

#
# analyse_2d_density
#

#
TASK=analyse_2d_density
XMETRICS="spprtt tcprtt cwnd throughput ackseq iqtime"
YMETRIC="restime"
for M in $XMETRICS ; do
        # XXX add more tests here
        if [ "$M" = "iqtime" ] ; then
		fab $TASK:exp_list=different_responders_explist.txt,out_dir=$TEST_OUTDIR,xmetric=$M,ymetric=$YMETRIC,source_filter=S_172.16.10.60_*,out_name=$TEST_OUTNAME,replot_only=1,query_host=newtcp20 || exit_with_error
        else
		fab $TASK:exp_list=different_responders_explist.txt,out_dir=$TEST_OUTDIR,xmetric=$M,ymetric=$YMETRIC,source_filter=S_172.16.10.60_*,out_name=$TEST_OUTNAME,replot_only=1 || exit_with_error
	fi
done

#
# analyse_dash_goodput
#
TASK=analyse_dash_goodput

#fab $TASK:test_id="20131219-163730_experiment;20131219-163143_experiment",out_dir=$TEST_OUTDIR,replot_only=0,ts_correct=0,lnames="1;2" || exit_with_error
#fab $TASK:test_id="20131219-163730_experiment;20131219-163143_experiment",out_dir=$TEST_OUTDIR,replot_only=1,ts_correct=0,lnames="1;2" || exit_with_error
# XXX don't have experiment data with clock offset measurements
#fab $TASK:test_id="20131219-163730_experiment;20131219-163143_experiment",out_dir=$TEST_OUTDIR,replot_only=0,ts_correct=1,lnames="1;2" || exit_with_error

#
# basic functions / analyse_all
#
TASK=analyse_all

fab $TASK:test_id=20140808-131349_experiment_tcp_newreno_del_2_down_100mbit_up_100mbit_incPer_10_incSz_512_bs_1000_ecn_0_run_0,out_dir=$TEST_OUTDIR,ts_correct=1
fab $TASK:test_id=20140808-131349_experiment_tcp_newreno_del_2_down_100mbit_up_100mbit_incPer_10_incSz_512_bs_1000_ecn_0_run_0,out_dir=$TEST_OUTDIR,ts_correct=0

#
# analyse_incast
#
TASK=analyse_incast

fab $TASK:test_id=20150218-135735_experiment_tcp_cubic_del_1_aqm_pfifo_responders_4_down_50mbit_up_50mbit_incPer_5_incSz_512_bs_120_ecn_0_run_0,out_dir=$TEST_OUTDIR,tcpdump=0,slowest_only=0
fab $TASK:test_id=20150218-135735_experiment_tcp_cubic_del_1_aqm_pfifo_responders_4_down_50mbit_up_50mbit_incPer_5_incSz_512_bs_120_ecn_0_run_0,out_dir=$TEST_OUTDIR,tcpdump=0,slowest_only=1
fab $TASK:test_id=20150218-135735_experiment_tcp_cubic_del_1_aqm_pfifo_responders_4_down_50mbit_up_50mbit_incPer_5_incSz_512_bs_120_ecn_0_run_0,out_dir=$TEST_OUTDIR,tcpdump=0,slowest_only=2
fab $TASK:test_id=20150218-135735_experiment_tcp_cubic_del_1_aqm_pfifo_responders_4_down_50mbit_up_50mbit_incPer_5_incSz_512_bs_120_ecn_0_run_0,out_dir=$TEST_OUTDIR,query_host=newtcp20,tcpdump=1,slowest_only=0
fab $TASK:test_id=20150218-135735_experiment_tcp_cubic_del_1_aqm_pfifo_responders_4_down_50mbit_up_50mbit_incPer_5_incSz_512_bs_120_ecn_0_run_0,out_dir=$TEST_OUTDIR,query_host=newtcp20,tcpdump=1,slowest_only=1
fab $TASK:test_id=20150218-135735_experiment_tcp_cubic_del_1_aqm_pfifo_responders_4_down_50mbit_up_50mbit_incPer_5_incSz_512_bs_120_ecn_0_run_0,out_dir=$TEST_OUTDIR,query_host=newtcp20,tcpdump=1,slowest_only=2

#
# analyse_ackseq
#
TASK=analyse_ackseq

fab --set teacup_config=config_grenville_v1.py $TASK:test_id=20141015-065523_experiment_tcp_newreno_del_2_down_100mbit_up_100mbit_incPer_3_incSz_256_bs_80_ecn_0_run_0,out_dir=$TEST_OUTDIR,source_filter="D_172.16.11.2_80",burst_sep=0,dupacks=0,replot_only=1
fab --set teacup_config=config_grenville_v1.py $TASK:test_id=20141015-065523_experiment_tcp_newreno_del_2_down_100mbit_up_100mbit_incPer_3_incSz_256_bs_80_ecn_0_run_0,out_dir=$TEST_OUTDIR,source_filter="D_172.16.11.2_80",burst_sep=1,dupacks=0,replot_only=1
fab --set teacup_config=config_grenville_v1.py $TASK:test_id=20141015-065523_experiment_tcp_newreno_del_2_down_100mbit_up_100mbit_incPer_3_incSz_256_bs_80_ecn_0_run_0,out_dir=$TEST_OUTDIR,source_filter="D_172.16.11.2_80",burst_sep=0,dupacks=1,replot_only=1
fab --set teacup_config=config_grenville_v1.py $TASK:test_id=20141015-065523_experiment_tcp_newreno_del_2_down_100mbit_up_100mbit_incPer_3_incSz_256_bs_80_ecn_0_run_0,out_dir=$TEST_OUTDIR,source_filter="D_172.16.11.2_80",burst_sep=1,dupacks=1,replot_only=1
fab --set teacup_config=config_grenville_v1.py $TASK:test_id=20141015-065523_experiment_tcp_newreno_del_2_down_100mbit_up_100mbit_incPer_3_incSz_256_bs_80_ecn_0_run_0,out_dir=$TEST_OUTDIR,source_filter="D_172.16.11.2_80",burst_sep=1,sburst=2,eburst=11,dupacks=0,replot_only=1
fab --set teacup_config=config_grenville_v1.py $TASK:test_id=20141015-065523_experiment_tcp_newreno_del_2_down_100mbit_up_100mbit_incPer_3_incSz_256_bs_80_ecn_0_run_0,out_dir=$TEST_OUTDIR,source_filter="D_172.16.11.2_80",burst_sep=1,sburst=2,eburst=11,dupacks=1,replot_only=1

fab $TASK:burst_sep=0.0,test_id="20150218-135735_experiment_tcp_cubic_del_1_aqm_pfifo_responders_8_down_50mbit_up_50mbit_incPer_5_incSz_512_bs_120_ecn_0_run_0;20150218-135735_experiment_tcp_cubic_del_1_aqm_pfifo_responders_10_down_50mbit_up_50mbit_incPer_5_incSz_512_bs_120_ecn_0_run_0;20150218-135735_experiment_tcp_cubic_del_1_aqm_pfifo_responders_12_down_50mbit_up_50mbit_incPer_5_incSz_512_bs_120_ecn_0_run_0",out_name=$TEST_OUTNAME,out_dir=$TEST_OUTDIR,source_filter=D_172.16.11.61_80,replot_only=1,lnames="Base RTT:2ms resp:8 incSz:512 bs:120; Base RTT:2ms resp:10 incSz:512 bs:120; Base RTT:2ms resp:12 incSz:512 bs:120"
fab $TASK:burst_sep=1.0,sburst=0,eburst=0,test_id="20150218-135735_experiment_tcp_cubic_del_1_aqm_pfifo_responders_8_down_50mbit_up_50mbit_incPer_5_incSz_512_bs_120_ecn_0_run_0;20150218-135735_experiment_tcp_cubic_del_1_aqm_pfifo_responders_10_down_50mbit_up_50mbit_incPer_5_incSz_512_bs_120_ecn_0_run_0;20150218-135735_experiment_tcp_cubic_del_1_aqm_pfifo_responders_12_down_50mbit_up_50mbit_incPer_5_incSz_512_bs_120_ecn_0_run_0",out_name=$TEST_OUTNAME,out_dir=$TEST_OUTDIR,source_filter=D_172.16.11.61_80,replot_only=1,lnames="Base RTT:2ms resp:8 incSz:512 bs:120; Base RTT:2ms resp:10 incSz:512 bs:120; Base RTT:2ms resp:12 incSz:512 bs:120"
fab $TASK:burst_sep=1.0,sburst=2,eburst=0,test_id="20150218-135735_experiment_tcp_cubic_del_1_aqm_pfifo_responders_8_down_50mbit_up_50mbit_incPer_5_incSz_512_bs_120_ecn_0_run_0;20150218-135735_experiment_tcp_cubic_del_1_aqm_pfifo_responders_10_down_50mbit_up_50mbit_incPer_5_incSz_512_bs_120_ecn_0_run_0;20150218-135735_experiment_tcp_cubic_del_1_aqm_pfifo_responders_12_down_50mbit_up_50mbit_incPer_5_incSz_512_bs_120_ecn_0_run_0",out_name=$TEST_OUTNAME,out_dir=$TEST_OUTDIR,source_filter=D_172.16.11.61_80,replot_only=1,lnames="Base RTT:2ms resp:8 incSz:512 bs:120; Base RTT:2ms resp:10 incSz:512 bs:120; Base RTT:2ms resp:12 incSz:512 bs:120"

#
# analyse_incast_iqtimes
#
TASK=analyse_incast_iqtimes

fab --set teacup_config=config_grenville.py $TASK:test_id=20150218-135735_experiment_tcp_cubic_del_1_aqm_pfifo_responders_4_down_50mbit_up_50mbit_incPer_5_incSz_512_bs_120_ecn_0_run_0,out_dir=$TEST_OUTDIR,burst_sep=1,query_host=newtcp20,ts_correct=1,cumulative=0,by_responder=0,diff_to_burst_start=0
fab --set teacup_config=config_grenville.py $TASK:test_id=20150218-135735_experiment_tcp_cubic_del_1_aqm_pfifo_responders_4_down_50mbit_up_50mbit_incPer_5_incSz_512_bs_120_ecn_0_run_0,out_dir=$TEST_OUTDIR,burst_sep=1,query_host=newtcp20,ts_correct=1,cumulative=1,by_responder=0,diff_to_burst_start=0
fab --set teacup_config=config_grenville.py $TASK:test_id=20150218-135735_experiment_tcp_cubic_del_1_aqm_pfifo_responders_4_down_50mbit_up_50mbit_incPer_5_incSz_512_bs_120_ecn_0_run_0,out_dir=$TEST_OUTDIR,burst_sep=1,query_host=newtcp20,ts_correct=1,cumulative=0,by_responder=1,diff_to_burst_start=0
fab --set teacup_config=config_grenville.py $TASK:test_id=20150218-135735_experiment_tcp_cubic_del_1_aqm_pfifo_responders_4_down_50mbit_up_50mbit_incPer_5_incSz_512_bs_120_ecn_0_run_0,out_dir=$TEST_OUTDIR,burst_sep=1,query_host=newtcp20,ts_correct=1,cumulative=1,by_responder=1,diff_to_burst_start=0
fab --set teacup_config=config_grenville.py $TASK:test_id=20150218-135735_experiment_tcp_cubic_del_1_aqm_pfifo_responders_4_down_50mbit_up_50mbit_incPer_5_incSz_512_bs_120_ecn_0_run_0,out_dir=$TEST_OUTDIR,burst_sep=1,query_host=newtcp20,ts_correct=1,cumulative=1,by_responder=1,diff_to_burst_start=1

#
# analyse_rtt with bursts
#
TASK=analyse_rtt

fab $TASK:test_id="20150218-135735_experiment_tcp_cubic_del_1_aqm_pfifo_responders_8_down_50mbit_up_50mbit_incPer_5_incSz_512_bs_120_ecn_0_run_0;20150218-135735_experiment_tcp_cubic_del_1_aqm_pfifo_responders_10_down_50mbit_up_50mbit_incPer_5_incSz_512_bs_120_ecn_0_run_0;20150218-135735_experiment_tcp_cubic_del_1_aqm_pfifo_responders_12_down_50mbit_up_50mbit_incPer_5_incSz_512_bs_120_ecn_0_run_0",out_name=$TEST_OUTNAME,out_dir=$TEST_OUTDIR,source_filter=D_172.16.11.61_80,replot_only=1,burst_sep=1.0,lnames="Base RTT:2ms resp:8 incSz:512 bs:120; Base RTT:2ms resp:10 incSz:512 bs:120; Base RTT:2ms resp:12 incSz:512 bs:120"
