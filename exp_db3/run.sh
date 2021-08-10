#!/bin/bash

set -e

output_prefix="00-"
args_file="/tmp/rocksdb_test_helper.args"

config_template=${config_template:-09}
config_modifiers=${config_modifiers:-}
config_file="/tmp/rocksdb_config.options"

device=${device:-s980pro250}
data_path=${data_path:-/media/auto/$device}

function main() {

	ROCKSDB_TEST_HELPER=$(get_executable_path rocksdb_test_helper)
	ROCKSDB_CONFIG_GEN=$(get_executable_path rocksdb_config_gen)
	
	exp_n=$config_template
	output_prefix="${exp_n}${exp_pref}_${device}-"
	"$ROCKSDB_CONFIG_GEN" --template="$config_template" --output="$config_file" $config_modifiers
	cp -f "$config_file" "`dirname ${BASH_SOURCE[0]}`/${output_prefix}rocksdb.options"

	if [ "$1" == 'create' ]; then
		duration=${duration:-70}        \
		warm_period=${warm_period:-10}  \
		ydb_workload_list=${ydb_workload_list:-workloada workloadb} \
		ydb_threads=4                   \
		save_args
		"$ROCKSDB_TEST_HELPER" --load_args="$args_file" create_ycsb --duration=20
		sleep 1m
		"$ROCKSDB_TEST_HELPER" --load_args="$args_file" ycsb
		shift 1
	fi
	
	if [ "$1" == 'backup' ]; then
		save_args
		cp "`dirname ${BASH_SOURCE[0]}`/${exp_n}_rocksdb.options" /media/auto/work2/rocksdb_6.15_tune/ycsb_db3tune_${exp_n}.options
		tar -cf /media/auto/work2/rocksdb_6.15_tune/ycsb_db3tune_${exp_n}.tar -C "$data_path/rocksdb_ycsb_0" .
		shift 1
	fi

	if [ "$1" == 'steady' ]; then
		duration=${duration:-70}        \
		warm_period=${warm_period:-10}  \
		ydb_workload_list=${ydb_workload_list:-workloada workloadb} \
		ydb_threads=4                   \
		save_args
		"$ROCKSDB_TEST_HELPER" --load_args="$args_file" ycsb
		shift 1
	fi

	if [ "$1" == 'pressure3' ]; then
		duration=${duration:--1}        \
		warm_period=${warm_period:-30}  \
		at_interval=${at_interval:-2}   \
		at_script_gen=3                 \
		save_args
		
		"$ROCKSDB_TEST_HELPER" --load_args="$args_file" ycsb_at3
		
		shift 1
	fi

	if [ "$1" == 'steady3b' ]; then
		duration=${duration:-90}        \
		warm_period=${warm_period:-30}  \
		ydb_threads=4                   \
		ydb_workload_list="workloada workloadb"     \
		save_args
		"$ROCKSDB_TEST_HELPER" --load_args="$args_file" ycsb
		shift 1
	fi

	if [ "$1" == 'pressure3b' ]; then
		duration=${duration:--1}        \
		warm_period=${warm_period:-30}  \
		ydb_threads=4                   \
		ydb_workload_list="workloada workloadb"     \
		at_interval=${at_interval:-10}  \
		at_script_gen=3                 \
		at_random_ratio=1               \
		at_block_size_list=4            \
		at_iodepth_list=4               \
		at_o_dsync=false                \
		save_args
		"$ROCKSDB_TEST_HELPER" --load_args="$args_file" ycsb_at3
		shift 1
	fi

	if [ "$1" == 'pressure0' ]; then
		duration=${duration:-80}        \
		warm_period=${warm_period:-20}  \
		ydb_threads=4                   \
		ydb_workload_list=${ydb_workload_list:-workloadb}   \
		at_interval=${at_interval:-10}  \
		at_script_gen=0                 \
		at_random_ratio=1               \
		at_block_size_list=4            \
		at_iodepth_list=4               \
		at_o_dsync=false                \
		save_args
		"$ROCKSDB_TEST_HELPER" --load_args="$args_file" ycsb_at3
		shift 1
	fi

	if [ "$1" == 'pressure4' ]; then
		duration=${duration:--1}        \
		warm_period=${warm_period:-10}  \
		ydb_threads=4                   \
		ydb_workload_list=${ydb_workload_list:-workloada workloadb}   \
		at_interval=${at_interval:-20}  \
		at_script_gen=4                 \
		at_random_ratio=1               \
		at_block_size_list=4            \
		at_iodepth_list=4               \
		at_o_dsync=false                \
		save_args
		"$ROCKSDB_TEST_HELPER" --load_args="$args_file" ycsb_at3
		shift 1
	fi

}

###########################################################################################
function save_args() {
duration=${duration:-90}
warm_period=${warm_period:-10}
stats_interval=${stats_interval:-5}
ydb_workload_list=${ydb_workload_list:-workloadb}
ydb_threads=${ydb_threads:-5}
num_at=${num_at:-4}
at_iodepth_list=${at_iodepth_list:-1}
at_io_engine=${at_io_engine:-libaio}
at_script_gen=${at_script_gen:-1}
at_interval=${at_interval:-2}
at_block_size_list=${at_block_size_list:-4 8 16 32 64 128 256 512}
at_o_dsync=${at_o_dsync:-true}
at_random_ratio=${at_random_ratio:-0.5}
[ "$change_rocksdb_jni" == 1 ] && param_rocksdb_jni="--ydb_rocksdb_jni=$(readlink -f $(dirname $ROCKSDB_TEST_HELPER)/3rd-party/rocksdb/java/target/rocksdbjni-*-linux64.jar)"

cat <<EOB >"$args_file"
{
	"output_path": "`dirname ${BASH_SOURCE[0]}`",
	"output_prefix": "$output_prefix",
	"output_suffix": "$output_suffix",
	"data_path": "$data_path",
	"before_run_cmd": "echo telegram-send 'Initiating experiment {output}'; sudo fstrim $data_path; sleep 30",
	"after_run_cmd": "telegram-send 'Experiment {output} returned exit code {exit_code}'",
	"rocksdb_config_file": "$config_file",
	"__backup_ycsb": "$backup_file",
	"duration": $duration,
	"warm_period": $warm_period,
	"stats_interval": $stats_interval,
	"ydb_workload_list": "$ydb_workload_list",
	"ydb_num_keys": 50000000,
	"ydb_threads": $ydb_threads,
	"num_at": $num_at,
	"at_iodepth_list": "$at_iodepth_list",
	"at_io_engine": "$at_io_engine",
	"at_o_dsync": "$at_o_dsync",
	"at_script_gen": $at_script_gen,
	"at_interval": $at_interval,
	"at_block_size_list": "$at_block_size_list",
	"at_random_ratio": "$at_random_ratio",
	"commands": "$(get_commands |paste -s -d'#')",
	"params": "--perfmon --ydb_socket=true --socket=/tmp/rocksdb_test.sock $param_rocksdb_jni"
}
EOB
}

###########################################################################################
function get_commands() {
if [ "$commands" == 'tr' ]; then
cat <<EOB
+30s # y* setoptions tag.a=tr1 column_family=usertable level0_file_num_compaction_trigger=1
15m  # y* setoptions tag.a=tr2 column_family=usertable level0_file_num_compaction_trigger=2
25m  # y* setoptions tag.a=tr3 column_family=usertable level0_file_num_compaction_trigger=3
35m  # y* setoptions tag.a=tr4 column_family=usertable level0_file_num_compaction_trigger=4
45m  # y* setoptions tag.a=tr6 column_family=usertable level0_file_num_compaction_trigger=6
EOB
elif [ "$commands" == 'level' ]; then
cat <<EOB
+30s # y* setoptions tag.a=lb512   column_family=usertable max_bytes_for_level_base=512M
15m  # y* setoptions tag.a=lb1024  column_family=usertable max_bytes_for_level_base=1G
30m  # y* setoptions tag.a=lb1536  column_family=usertable max_bytes_for_level_base=1536M
45m  # y* setoptions tag.a=lb2048  column_family=usertable max_bytes_for_level_base=2G
EOB
elif [ "$commands" == 'T' ]; then
cat <<EOB
+30s # y* test tag.a=T10a
10m # y* setoptions tag.a=T14  column_family=usertable max_bytes_for_level_multiplier=14
15m # y* setoptions tag.a=T20a column_family=usertable max_bytes_for_level_multiplier=20
20m # y* test tag.a=T20b
35m # y* setoptions tag.a=T10b column_family=usertable max_bytes_for_level_multiplier=10
45m # y* test tag.a=T10c
EOB
elif [ "$commands" == 'Tltr' ]; then
cat <<EOB
+30s # y* test tag.a=T10a
10m # y* setoptions tag.a=T20l2tr15 column_family=usertable max_bytes_for_level_multiplier=20 max_bytes_for_level_base=2G level0_file_num_compaction_trigger=15
15m # y* setoptions tag.a=l05tr4    column_family=usertable max_bytes_for_level_base=512M level0_file_num_compaction_trigger=4
25m # y* setoptions tag.a=T10b      column_family=usertable max_bytes_for_level_multiplier=10
35m # y* test tag.a=T10c
45m # a* stop
EOB
else
	echo "$commands"
fi
}

###########################################################################################
function get_executable_path() {
	local cur_path=${PROJECT_PATH:-.}
	while [ -d "$cur_path" ]; do
		#echo "DEBUG: cur_path = $cur_path" >&2
		if [ -e "$cur_path/$1" ]; then
			readlink -f "$cur_path/$1"
			return 0
		fi
		[ "$(readlink -f "$cur_path")" == '/' ] && break
		cur_path="$cur_path/.."
	done
	d="$(which $1)"
	if [ $? != 0 ]; then
		echo "ERROR: program named $1 not found" >&2
		exit 1
	fi
	echo "$d"
}

###########################################################################################
main "$@"
