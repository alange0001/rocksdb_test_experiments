#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat May 16 08:54:54 2020

@author: Adriano Lange <alange0001@gmail.com>

Copyright (c) 2020-present, Adriano Lange.  All rights reserved.
This source code is licensed under both the GPLv2 (found in the
LICENSE.GPLv2 file in the root directory) and Apache 2.0 License
(found in the LICENSE.Apache file in the root directory).
"""

import os
import math
import collections
import re
import json
import copy
import sqlite3
import numpy
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.ticker import (AutoMinorLocator, MultipleLocator)
from mpl_toolkits.axes_grid1 import host_subplot
import pandas as pd
import seaborn as sns
sns.set()
sns.set_style('white')

class Options:
	formats = ['png', 'pdf']
	print_params = False
	file_description = None
	save = False
	savePlotData = False
	graphTickMajor = 5
	graphTickMinor = 5
	args_global = {'title': 'default+filename'}
	plot_db = True
	args_db = dict()
	db_xlim = None
	db_ylim = [0,  None]
	file_start_time = None
	plot_ycsb = True
	plot_io = True
	plot_cpu = True
	plot_at3 = True
	plot_at3_script = True
	plot_io_norm = False
	plot_at3_write_ratio = False
	plot_pressure = False
	args_pressure = dict()
	plot_containers_io = True
	plot_ycsb_lsm_stats = True
	plot_ycsb_lsm_size = True
	plot_ycsb_lsm_details = True
	plot_ycsb_lsm_summary = True
	plot_smart_utilization = True
	plot_pairgrid = False
	args_pairgrid = dict()
	plot_pairgrid_kv = False
	args_pairgrid_kv = dict()
	use_at3_counters = True
	at3_ticks = True
	fio_folder = None
	plot_all_dbmean = True
	plot_all_pressure = True
	all_pressure_label = None

	def __init__(self, **kargs):
		if self.file_start_time is None:
			self.file_start_time = {}
		self._process_args(kargs)

	def __call__(self, **kargs):
		cp = copy.copy(self)
		cp._process_args(kargs)
		return cp

	def _process_args(self, args: dict) -> None:
		deprecated = {
			'db_mean_interval': 'use args_db["mean_interval"] instead',
			'pressure_decreased': 'use args_pressure["mark_decreased"] instead',
			'print_pressure_values': 'use args_pressure["print_values"] instead',
		}
		for k, v in args.items():
			if k == 'plot_nothing':
				if v:
					for i in dir(self):
						if 'plot_' in i:
							self.__setattr__(i, False)
			elif k in dir(self):
				if k in deprecated.keys():
					raise Exception(f'Option {k} is DEPRECATED: {deprecated[k]}')
				self.__setattr__(k, v)
			else:
				raise Exception('Invalid option name: {}'.format(k))


class DBClass:
	conn = sqlite3.connect(':memory:')
	file_id = 0

	def __init__(self):
		cur = self.conn.cursor()
		cur.execute('''CREATE TABLE files (
			  file_id INT PRIMARY KEY, name TEXT,
			  number INT)''')
		cur.execute('''CREATE TABLE data (
			file_id INT, number INT, time INT,
			block_size INT, random_ratio DOUBLE, write_ratio DOUBLE,
			mbps DOUBLE, mbps_read DOUBLE, mbps_write DOUBLE, blocks_ps DOUBLE,
			PRIMARY KEY(file_id, number, time))''')
		self.conn.commit()

	def getFileId(self):
		ret = self.file_id
		self.file_id += 1
		return ret

	def getCursor(self):
		return self.conn.cursor()

	def query(self, sql, printsql=False):
		if printsql:
			print('SQL: ' + sql)
		return self.conn.cursor().execute(sql)

	def commit(self):
		self.conn.commit()


DB = DBClass()


class AllFiles:
	_options = None
	_filename = None
	_file_list = None
	_file_objs = None

	def __init__(self, filename, options=None, file_list=None):
		self._options = options
		self._filename = filename
		self._file_list = []
		self._file_objs = []
		for i in file_list if isinstance(file_list, list) else []:
			self.add_file(i)

	def add_file(self, filename):
		f = File(filename, self._options, allfiles=self)
		self._file_list.append(filename)
		self._file_objs.append(f)
		return f

	def __len__(self):
		return len(self._file_list)

	def __getitem__(self, item):
		if isinstance(item, int):
			return self._file_objs[item]
		else:
			raise Exception(f'Invalid index for the class {self.__class__.__name__}: {item}')

	@property
	def file_names(self):
		return self._file_list

	def check_options(self, options):
		if self._options is None:
			self._options = options

	def graph_all(self):
		for i in range(0, len(self._file_list)):
			self._file_objs[i].graph_all()

		print('AllFiles Graphs:')
		if self._options.plot_all_dbmean:
			self.graph_dbmean()
		if self._options.plot_all_pressure:
			self.graph_pressure()

	def graph_dbmean(self):
		pressures = self.file_pressures
		if len(pressures) == 0: return

		fig, ax = plt.subplots()
		fig.set_figheight(3)
		fig.set_figwidth(8)

		for i in range(len(self._file_objs)):
			f = self._file_objs[i]
			fp = self.file_pressures[i]

			sns.lineplot(ax=ax, x='w_name', y='ycsb[0].ops_per_s', data=f.pd_data,
			             label=fp['file_label'] if fp is not None else 'None')

		if self._options.db_xlim is not None:
			ax.set_xlim( self._options.db_xlim )
		if self._options.db_ylim is not None:
			ax.set_ylim( self._options.db_ylim )

		ax.grid(which='major', color='#CCCCCC', linestyle='--')
		ax.set(xlabel="time (min)", ylabel="tx/s")
		ax.legend(loc='best', ncol=1, frameon=True)

		if self._options.save:
			for f in self._options.formats:
				save_name = f'{self._filename}_graph_db.{f}'
				fig.savefig(save_name, bbox_inches="tight")
		plt.show()

	_file_pressures = None
	@property
	def file_pressures(self):
		if self._file_pressures is not None:
			return self._file_pressures

		self._file_pressures = []
		for f in self._file_objs:
			self._file_pressures.append(f.pressure_data)
		return self._file_pressures

	def graph_pressure(self) -> None:
		pressures = self.file_pressures
		if len(pressures) == 0:
			return

		colors = plt.get_cmap('tab10').colors
		n_data = len(pressures)

		fig, ax = plt.subplots()
		fig.set_figheight(0.7 * n_data)
		fig.set_figwidth(10)

		Y_labels = []
		Y_ticks = []
		i_ax = 0
		for data in pressures:
			if data is None: continue

			line_label = data['file_label']
			X = data['W_normalized']
			X_labels = data['W_names']
			Y_labels.append(line_label)

			for i in range(len(X)):
				ax.annotate(f'{X_labels[i]}', xy=(X[i], i_ax), xytext=(X[i] - 0.007, i_ax + 0.2), rotation=90)

			ax.plot(X, [i_ax for x in X], 'o', color=colors[0])
			Y_ticks.append(i_ax)
			i_ax -= 1

		ax.set_xlim([min(0, min(X))-0.05, 1.05])
		ax.set_ylim([i_ax + 0.8, 0.7])
		ax.yaxis.set_ticks(Y_ticks)
		ax.yaxis.set_ticklabels(Y_labels)

		ax.xaxis.set_major_locator(MultipleLocator(0.1))
		ax.xaxis.set_minor_locator(AutoMinorLocator(4))
		ax.grid(which='major', color='#888888', linestyle='--')
		ax.grid(which='minor', color='#CCCCCC', linestyle=':')

		ax.set(xlabel="normalized pressure: $(\\rho(w_0)-\\rho(w_i)) / \\rho(w_0)$")

		if self._options.save:
			for f in self._options.formats:
				save_name = f'{self._filename}-pressure.{f}'
				fig.savefig(save_name, bbox_inches="tight")
		plt.show()


class File:
	_filename    = None
	@property
	def filename(self): return self._filename
	_options     = None
	_allfiles    = None
	_params      = None

	_stats_interval = None
	_data           = None
	@property
	def data(self): return self._data
	_dbbench        = None

	_plotdata = None  # get data from generated graphs

	_file_id      = None
	_num_at       = None
	_num_dbs      = None
	_num_ydbs     = None
	_at_direct_io = None

	def __init__(self, filename, options, allfiles=None):
		self._filename = filename
		self._options = options
		self._allfiles = allfiles
		if allfiles is not None:
			allfiles.check_options(options)
		self._params = collections.OrderedDict()
		self._data = dict()
		self._dbbench = list()
		self._plotdata = collections.OrderedDict()
		self.get_dbbench_params()
		self.load_data()

	@classmethod
	def decompose_filename(cls, filename: str) -> list:
		r = re.findall(r'(.*)(\.out)(\.gz|\.lzma|\.xz)?$', filename)
		if len(r) > 0:
			return list(r[0])
		return []

	@classmethod
	def accept_file(cls, filename: str) -> bool:
		return len(cls.decompose_filename(filename)) > 0

	def open_file(self):
		d = self.__class__.decompose_filename(self._filename)
		if len(d) > 2 and d[2] == '.gz':
			import gzip
			return gzip.open(self._filename, 'rt')
		if len(d) > 2 and d[2] in ['.lzma', '.xz']:
			import lzma
			return lzma.open(self._filename, 'rt')
		return open(self._filename, 'rt')

	_filename_without_ext_cache = None

	@property
	def _filename_without_ext(self) -> str:
		if self._filename_without_ext_cache is None:
			d = self.__class__.decompose_filename(self._filename)
			self._filename_without_ext_cache = d[0] if len(d) > 0 else self._filename
		return self._filename_without_ext_cache

	def load_data(self):
		with self.open_file() as file:
			for line in file.readlines():
				parsed_line = re.findall(r'Args\.([^:]+): *(.+)', line)
				if len(parsed_line) > 0:
					self._params[parsed_line[0][0]] = try_convert(parsed_line[0][1], int, float)

				parsed_line = re.findall(r'Task ([^,]+), STATS: (.+)', line)
				if len(parsed_line) > 0:
					task = parsed_line[0][0]
					try:
						data = json.loads(parsed_line[0][1])
					except:
						print("json exception (task {}): {}".format(task, parsed_line[0][1]))
					# print("Task {}, data: {}".format(task, data))
					if self._data.get(task) is None:
						self._data[task] = []
					data_dict = collections.OrderedDict()
					self._data[task].append(data_dict)
					for k, v in data.items():
						data_dict[k] = try_convert(v, int, float, decimal_suffix)
			for e in self._data.keys(): # delete the 1st data of each task
				del self._data[e][0]

		self._num_at = self._params['num_at']
		self._num_dbs = self._params['num_dbs']
		self._num_ydbs = self._params['num_ydbs']
		self._stats_interval = self._params['stats_interval']
		if self._num_at > 0:
			self._at_direct_io = (self._params['at_params[0]'].find('--direct_io') >= 0)

	def get_dbbench_params(self):
		num_dbs = 0
		cur_db = -1
		with self.open_file() as file:
			for line in file.readlines():
				if num_dbs == 0:
					parsed_line = re.findall(r'Args\.num_dbs: *([0-9]+)', line)  # number of DBs
					if len(parsed_line) > 0:
						num_dbs = int(parsed_line[0][0])
						for i in range(0, num_dbs):
							self._dbbench.append(collections.OrderedDict())
					continue
				parsed_line = re.findall(r'Executing *db_bench\[([0-9]+)\]. *Command:', line)  # command of DB [i]
				if len(parsed_line) > 0:
					cur_db = int(parsed_line[0][0])
					continue
				parsed_line = re.findall(r'^\[.*', line) # end of the command
				if len(parsed_line) > 0:
					if cur_db == num_dbs -1: break
					else: continue
				for l2 in line.split("--"): # parameters
					parsed_line = re.findall(r'\s*([^=]+)="([^"]+)"', l2)
					if len(parsed_line) > 0:
						self._dbbench[cur_db][parsed_line[0][0]] = try_convert(parsed_line[0][1], int, float)
						continue
					parsed_line = re.findall(r'\s*([^=]+)=([^ ]+)', l2)
					if len(parsed_line) > 0:
						self._dbbench[cur_db][parsed_line[0][0]] = try_convert(parsed_line[0][1], int, float)
						continue

	def print_params(self):
		print('Params:')
		for k, v in self._params.items():
			if k.find('at_script') >= 0 : continue
			print('{:<20s}: {}'.format(k, v))
		print()

	def load_at3(self):
		file_id = DB.getFileId()
		self._file_id = file_id
		num_at = self._num_at

		DB.query("insert into files values ({}, '{}', {})".format(file_id, self._filename, num_at))
		for i in range(0, num_at):
			for j in self._data['access_time3[{}]'.format(i)]:
				values = collections.OrderedDict()
				values['file_id']      = file_id
				values['number']       = i
				values['time']         = j['time']
				values['block_size']   = j['block_size']
				values['random_ratio'] = j['random_ratio']
				values['write_ratio']  = j['write_ratio']
				values['mbps']         = j['total_MiB/s']
				values['mbps_read']    = j['read_MiB/s']
				values['mbps_write']   = j['write_MiB/s']
				values['blocks_ps']    = j['blocks/s'] if j.get('blocks/s') is not None else 'NULL'
				query = "insert into data (" + ', '.join(values.keys()) + ") values ({" + '}, {'.join(values.keys()) + "})"
				DB.query(query.format(**values))
		DB.commit()

	def save_plot_data(self, name, data):
		if self._options.savePlotData:
			self._plotdata[name] = data

	def count_dbs(self):
		return (self._num_dbs, self._num_ydbs)

	_at3_changes = None
	@property
	def at3_changes(self):
		if self._at3_changes is None:
			self._at3_changes = []
			count_at3 = self._num_at
			for i in range(0, count_at3):
				i_at = collections.OrderedDict()
				self._at3_changes.append(i_at)
				last_conf = None
				for j_at in self._data.get(f'access_time3[{i}]'):
					j_at_v = (j_at['wait'], j_at['random_ratio'], j_at['write_ratio'])
					if j_at_v != last_conf:
						last_conf = j_at_v
						i_at[j_at['time']] = j_at_v
			# print('\nDEBUG: at3_changes:')
			# for i in self._at3_changes:
			# 	print(i)
		return self._at3_changes

	_w_list = None
	@property
	def w_list(self):
		if self._w_list is None and self._num_at > 0:
			fuzzy = 15
			ret = collections.OrderedDict()

			aux_times = dict()
			for i in range(0, len(self.at3_changes)):
				for time, conf in self.at3_changes[i].items():
					if aux_times.get(time) is None:
						aux_times[time] = []
					aux_times[time].append((i, conf))
			times = list(aux_times.keys())
			times.sort()

			i = 0
			wc = 0
			while i < len(times):
				i_time = times[i]
				ret_wc = collections.OrderedDict()
				if i_time > fuzzy:
					ret_wc['time'] = i_time
				else:
					ret_wc['time'] = 0
				ret_wc['name'] = f'w{wc}'
				ret_wc['number'] = wc
				ret_wc['latex_name'] = f'$w_{{{wc}}}$'
				for i_at in aux_times[i_time]:
					ret_wc[i_at[0]] = i_at[1]
				ret[f'w{wc}'] = ret_wc
				for j in range(i+1, len(times)):
					if times[j] > i_time + fuzzy:
						break
					i += 1
					for i_at in aux_times[times[j]]:
						ret_wc[i_at[0]] = i_at[1]
				i += 1
				wc += 1

			self._w_list = ret
			#print('\nDEBUG: w_list:')
			#for k, v in self._w_list.items():
			#	print(k, ":", v)
		return self._w_list

	def last_at3(self, time):
		if self._num_at <= 0 or self.w_list is None:
			return None
		w_list = list(self.w_list.values())
		last_w = w_list[0]
		for w in w_list:
			if w['time'] > time:
				break
			last_w = w
		return last_w

	def get_at3_ticks(self, Xmin, Xmax):
		# print(f'\nDEBUG: get_at3_ticks{Xmin, Xmax}')
		ticks, labels = [], []
		if self.w_list is not None:
			for w in self.w_list.values():
				w_time = int(w['time']/60)
				if w_time < Xmin:
					continue
				if w_time > Xmax:
					break
				ticks.append(w_time)
				labels.append(w['latex_name'])
		return ticks, labels

	def add_at3_ticks(self, ax, Xmin, Xmax):
		if self._options.at3_ticks and self._num_at > 0:
			X2_ticks, X2_labels = self.get_at3_ticks(Xmin, Xmax)
			if 'twin' in dir(ax):
				ax2 = ax.twin()
				ax2.axis["right"].major_ticklabels.set_visible(False)
				ax2.axis["top"].major_ticklabels.set_visible(True)
			else:
				ax2 = ax.twiny()

			ax2.set_xticks(X2_ticks)
			ax2.set_xticklabels(X2_labels, rotation=90)
			ax2.set_xlim(ax.get_xlim()) # ax.set_xlim() must be set before
			return ax2
		return None

	def get_mean(self, X, Y, interval):
		pd1 = pd.DataFrame({
			'X': [(int(x/interval)*interval)+(interval/2) for x in X],
			'Y': Y,
			})
		pd2 = pd1.groupby(['X']).agg({'Y':'mean'}).sort_values('X')
		return list(pd2.index), list(pd2['Y'])

	def overlap_args(self, *args_list):
		args = copy.copy(self._options.args_global)
		for args_i in args_list:
			for k, v in args_i.items():
				args[k] = v
		return args

	_pd_data = None

	@property
	def pd_data(self):
		if self._pd_data is not None:
			return self._pd_data

		pkey = None
		for i in ['ycsb[0]', 'db_bench[0]', 'access_time3[0]', 'performancemonitor']:
			if i in self._data.keys():
				pkey = i
				break
		if pkey is None: return None
		if len(self._data[pkey]) < 2: return None

		buckets_data = collections.OrderedDict()
		for d in self._data[pkey]:
			t = d['time']
			bd = collections.OrderedDict()
			bd['time'] = t
			flat_dict(d, prefix=pkey, ret=bd)
			buckets_data[t] = bd

		interval = int(self._data[pkey][1]['time'] - self._data[pkey][0]['time'])
		buckets = collections.OrderedDict()
		for i in range(max(buckets_data.keys())+interval+1):
			for j in range(1,100):
				bd = buckets_data.get(i - j)
				if bd is not None:
					buckets[i] = bd
					break
				bd = buckets_data.get(i + j)
				if bd is not None:
					buckets[i] = bd
					break
			if buckets.get(i) is None:
				print(f'WARN: bucket {i} does not exist')

		for k, d in self._data.items():
			if k != pkey:
				for di in d:
					bucket_i = buckets.get(di['time'])
					if bucket_i is not None:
						flat_dict(di, prefix=k, ret=bucket_i)
					elif di['time'] < max(buckets.keys()):
						print(f'WARN: time {di["time"]} of key {k} not found in buckets')

		# Prepare data for the DataFrame
		transpose = collections.OrderedDict()
		for list_i in buckets_data.values():
			for k, v in list_i.items():
				if transpose.get(k) is None:
					transpose[k] = []
				if k != 'time':
					while len(transpose[k]) < len(transpose['time'])-1:
						transpose[k].append(None) # Missing data inside the time series
				transpose[k].append(self._pd_data_convert(k, v))
		# Add missing data at the end of each column
		len_time = len(transpose['time'])
		for v in transpose.values():
			len_v = len(v)
			for _ in range(0, len_time - len_v):
				v.append(None)

		ret = pd.DataFrame(transpose)
		ret['time_min'] = ret['time'] / 60.0

		if self._num_at > 0:
			w_name = []
			w_num = []
			for _, d in ret.iterrows():
				last_name = None
				last_num  = None
				for w in self.w_list.values():
					if w['time'] > d['time']:
						break
					last_name = w['name']
					last_num  = w['number']

				w_name.append(last_name)
				w_num.append(last_num)

			ret['w']      = w_num
			ret['w_name'] = w_name
		else:
			ret['w']      = [None for _ in range(len(ret))]
			ret['w_name'] = [None for _ in range(len(ret))]

		self._pd_data = ret
		return ret

	def _pd_data_convert(self, key, value):
		if key.find('rocksdb.cfstats.compaction') > 0:
			#if key.find('SizeBytes') > 0:
			#	return try_convert(value, float)
			return try_convert(value, float)
		return value

	def cut_begin(self, X, Y, start):
		retX, retY = [], []
		for i in range(len(X)):
			if X[i] >= start:
				retX.append(X[i] - start)
				retY.append(Y[i])
		return (retX, retY)

	def get_graph_title(self, args, graph_default):
		if args.get('title') is None:
			return None
		if callable(args.get('title')):
			return args['title'](self, graph_default)
		if args.get('title') == 'default':
			return graph_default
		if args.get('title') == 'filename':
			return self.filename
		if args.get('title') == 'filename+default':
			return f'{self.filename}\n{graph_default}'
		if args.get('title') == 'default+filename':
			return f'{graph_default}\n{self.filename}'
		return args.get('title') if isinstance(args.get('title'), str) else '(unknown type)'

	def graph_db(self, **kargs):
		num_dbbench, num_ycsb = self.count_dbs()
		if num_dbbench == 0 and num_ycsb == 0:
			return

		args = self.overlap_args(self._options.args_db, kargs)

		fig, ax = plt.subplots()
		fig.set_figheight(3)
		fig.set_figwidth(9)

		Ymax = -1
		Xmin, Xmax = 10**10, -10**10
		allfiles_d = None
		for i in range(0, num_dbbench):
			X = [i['time']/60.0 for i in self._data[f'db_bench[{i}]']]
			Y = [i['ops_per_s'] for i in self._data[f'db_bench[{i}]']]

			if self._options.file_start_time is not None and self._options.file_start_time.get(self._filename) is not None:
				Xplot, Yplot = self.cut_begin(X, Y, self._options.file_start_time.get(self._filename))
			else:
				Xplot, Yplot = X, Y
			Xmin = min([Xmin, min(Xplot)])
			Xmax = max([Xmax, max(Xplot)])
			Ymax = max([Ymax, max(Yplot)])
			ax.plot(Xplot, Yplot, '-', lw=1, label=f'db_bench')

			if self._dbbench[i].get("sine_d") is not None:
				sine_a = coalesce(self._dbbench[i]['sine_a'], 0)
				sine_b = coalesce(self._dbbench[i]['sine_b'], 0)
				sine_c = coalesce(self._dbbench[i]['sine_c'], 0)
				sine_d = coalesce(self._dbbench[i]['sine_d'], 0)
				Y = [ sine_a * math.sin(sine_b * x + sine_c) + sine_d for x in X]
				if self._options.file_start_time is not None and self._options.file_start_time.get(self._filename) is not None:
					Xplot, Yplot = self.cut_begin(X, Y, self._options.file_start_time.get(self._filename))
				else:
					Xplot, Yplot = X, Y
				ax.plot(Xplot, Yplot, '-', lw=1, label=f'db_bench (expected)')

			if args.get('mean_interval') is not None:
				X, Y = self.get_mean(Xplot, Yplot, args.get('mean_interval'))
				ax.plot(X, Y, '-', lw=1, label=f'db_bench mean')
			elif self._num_at > 0:
				df = self.pd_data.groupby(['w_name']).agg(
					{'time_min': 'mean', 'db_bench[0].ops_per_s': 'mean'}
					).sort_values('time_min')
				sns.lineplot(ax=ax, x='time_min', y='db_bench[0].ops_per_s', data=df)

		for i in range(0, num_ycsb):
			try:
				workload = self._params[f'ydb_workload[{i}]'].split('/')[-1]
				i_label = {'workloada': 'A', 'workloadb':'B'}[workload]
			except:
				i_label = i
			X = [i['time']/60.0 for i in self._data[f'ycsb[{i}]']]
			Y = [i['ops_per_s'] for i in self._data[f'ycsb[{i}]']]
			if self._options.file_start_time is not None and self._options.file_start_time.get(self._filename) is not None:
				Xplot, Yplot = self.cut_begin(X, Y, self._options.file_start_time.get(self._filename))
			else:
				Xplot, Yplot = X, Y
			Xmin = min([Xmin, min(Xplot)])
			Xmax = max([Xmax, max(Xplot)])
			Ymax = max([Ymax, max(Yplot)])
			ax.plot(Xplot, Yplot, '-', lw=1, label=f'ycsb {i_label}')

			if args.get('mean_interval') is not None:
				X, Y = self.get_mean(Xplot, Yplot, args.get('mean_interval'))
				ax.plot(X, Y, '-', lw=1, label=f'ycsb {i_label} mean')
			elif self._num_at > 0:
				df = self.pd_data.groupby(['w_name']).agg(
					{'time_min': 'mean', 'ycsb[0].ops_per_s': 'mean'}
					).sort_values('time_min')
				sns.lineplot(ax=ax, x='time_min', y='ycsb[0].ops_per_s', data=df)

		if self._options.db_xlim is not None:
			ax.set_xlim( self._options.db_xlim )
		else:
			aux = (Xmax - Xmin) * 0.01
			ax.set_xlim([Xmin-aux, Xmax+aux])
		if self._options.db_ylim is not None:
			ax.set_ylim( self._options.db_ylim )

		self.set_x_ticks(ax)

		if not(self._options.file_start_time is not None and self._options.file_start_time.get(self._filename) is not None):
			self.add_at3_ticks(ax, int(Xmin), int(Xmax))
			if allfiles_d is not None:
				X2_ticks, X2_labels = self.get_at3_ticks(int(Xmin), int(Xmax))
				allfiles_d['W_ticks'] = X2_ticks
				allfiles_d['W_labels'] = X2_labels

		ax.set(xlabel="time (min)", ylabel="tx/s")
		ax.set(title=self.get_graph_title(args, "Key-Value Store's Performance"))

		#chartBox = ax.get_position()
		#ax.set_position([chartBox.x0, chartBox.y0, chartBox.width*0.65, chartBox.height])
		#ax.legend(loc='upper center', bbox_to_anchor=(1.35, 0.9), title='threads', ncol=1, frameon=True)
		ax.legend(loc='best', ncol=1, frameon=True)

		if self._options.save:
			for f in self._options.formats:
				save_name = f'{self._filename_without_ext}_graph_db.{f}'
				fig.savefig(save_name, bbox_inches="tight")
		plt.show()

	def graph_io(self):
		self.graph_io_new()
		self.graph_io_old()

	def graph_io_new(self):
		if self._data.get('performancemonitor') is None:
			return

		X = [x['time']/60.0 for x in self._data['performancemonitor']]

		fig, axs = plt.subplots(3, 1)
		fig.set_figheight(5)
		fig.set_figwidth(8)

		for ax_i in range(0,3):
			ax = axs[ax_i]
			if ax_i == 0:
				Yr, Yw = None, None
				try: # due to a iostat bug when exporting kB/s in the JSON format. Using /proc/diskstats:
					Yr = numpy.array([i['disk']['diskstats']['rkB/s']/1024  for i in self._data['performancemonitor']])
					Yw = numpy.array([i['disk']['diskstats']['wkB/s']/1024  for i in self._data['performancemonitor']])
					#print('using /proc/diskstats')
				except: pass
				if Yr is None or Yw is None:
					Yr = numpy.array([i['disk']['iostat']['rkB/s']/1024  for i in self._data['performancemonitor']])
					Yw = numpy.array([i['disk']['iostat']['wkB/s']/1024  for i in self._data['performancemonitor']])
				Yt = Yr + Yw
				ax.plot(X, Yr, '-', lw=1, label='read', color='green')
				ax.plot(X, Yw, '-', lw=1, label='write', color='orange')
				ax.plot(X, Yt, '-', lw=1, label='total', color='blue')
				ax.set(title="iostat", ylabel="MB/s")
				ax.legend(loc='upper right', ncol=3, frameon=True)
			elif ax_i == 1:
				Y = [i['disk']['iostat']['r/s']     for i in self._data['performancemonitor']]
				ax.plot(X, Y, '-', lw=1, label='read', color='green')
				Y = [i['disk']['iostat']['w/s']     for i in self._data['performancemonitor']]
				ax.plot(X, Y, '-', lw=1, label='write', color='orange')
				ax.set(ylabel="IO/s")
				ax.legend(loc='upper right', ncol=2, frameon=True)
			elif ax_i == 2:
				Y = [i['disk']['iostat']['util']     for i in self._data['performancemonitor']]
				ax.plot(X, Y, '-', lw=1, label='%util')
				ax.set(xlabel="time (min)", ylabel="percent")
				ax.set_ylim([-5, 105])
				ax.legend(loc='upper right', ncol=1, frameon=True)

			#chartBox = ax.get_position()
			#ax.set_position([chartBox.x0, chartBox.y0, chartBox.width*0.65, chartBox.height])
			#ax.legend(loc='upper center', bbox_to_anchor=(1.35, 0.9), title='threads', ncol=1, frameon=True)

			aux = (X[-1] - X[0]) * 0.01
			ax.set_xlim([X[0]-aux,X[-1]+aux])
			if ax_i == 0:
				self.add_at3_ticks(ax, int(X[0]), int(X[-1]))

			self.set_x_ticks(ax)

		fig.tight_layout()

		if self._options.save:
			for f in self._options.formats:
				save_name = f'{self._filename_without_ext}_graph_io.{f}'
				fig.savefig(save_name, bbox_inches="tight")
		plt.show()

	def graph_io_old(self):
		if self._data.get('iostat') is None:
			return
		fig, axs = plt.subplots(3, 1)
		fig.set_figheight(5)
		fig.set_figwidth(8)

		for ax_i in range(0,3):
			ax = axs[ax_i]
			if ax_i == 0:
				X = [i['time']/60.0 for i in self._data['iostat']]
				Yr = numpy.array([i['rMB/s']     for i in self._data['iostat']])
				Yw = numpy.array([i['wMB/s']     for i in self._data['iostat']])
				Yt = Yr + Yw
				ax.plot(X, Yr, '-', lw=1, label='read', color='green')
				ax.plot(X, Yw, '-', lw=1, label='write', color='orange')
				ax.plot(X, Yt, '-', lw=1, label='total', color='blue')
				ax.set(title="iostat", ylabel="MB/s")
				ax.legend(loc='upper right', ncol=3, frameon=True)
			elif ax_i == 1:
				Y = [i['r/s']     for i in self._data['iostat']]
				ax.plot(X, Y, '-', lw=1, label='read', color='green')
				Y = [i['w/s']     for i in self._data['iostat']]
				ax.plot(X, Y, '-', lw=1, label='write', color='orange')
				ax.set(ylabel="IO/s")
				ax.legend(loc='upper right', ncol=2, frameon=True)
			elif ax_i == 2:
				Y = [i['%util']     for i in self._data['iostat']]
				ax.plot(X, Y, '-', lw=1, label='%util')
				ax.set(xlabel="time (min)", ylabel="percent")
				ax.set_ylim([-5, 105])
				ax.legend(loc='upper right', ncol=1, frameon=True)

			#chartBox = ax.get_position()
			#ax.set_position([chartBox.x0, chartBox.y0, chartBox.width*0.65, chartBox.height])
			#ax.legend(loc='upper center', bbox_to_anchor=(1.35, 0.9), title='threads', ncol=1, frameon=True)

			aux = (X[-1] - X[0]) * 0.01
			ax.set_xlim([X[0]-aux,X[-1]+aux])

			self.set_x_ticks(ax)

		fig.tight_layout()

		if self._options.save:
			for f in self._options.formats:
				save_name = f'{self._filename_without_ext}_graph_io.{f}'
				fig.savefig(save_name, bbox_inches="tight")
		plt.show()

	def graph_io_norm(self):
		if self._data.get('iostat') is None:
			return
		if self._num_at == 0 or self._num_at is None:
			return

		fig, ax = plt.subplots()
		fig.set_figheight(5)
		fig.set_figwidth(8)

		ax.grid()
		ax.set(ylabel="normalized performance")

		X = [i['time']/60.0 for i in self._data['iostat']]
		self.save_plot_data('io_norm_total_X', X)
		Yr = numpy.array([i['rMB/s']     for i in self._data['iostat']])
		Yw = numpy.array([i['wMB/s']     for i in self._data['iostat']])
		Yt = Yr + Yw
		self.save_plot_data('io_norm_total_Y_raw', Yt)
		Yt = Yt / Yt[0]
		self.save_plot_data('io_norm_total_Y', Yt)
		ax.plot(X, Yt, '-', lw=1, label='device', color='blue')

		cur_at = self._data['access_time3[0]']
		X = [j['time']/60.0 for j in cur_at]
		Y = numpy.array([j['total_MiB/s'] if j['wait'] == 'false' else None for j in cur_at])
		Yfirst = None
		for i in Y:
			if i is not None:
				Yfirst = i
				break
		if Yfirst is not None and Yfirst != 0:
			Y = Y/Yfirst
			ax.plot(X, Y, '-', lw=1, label='job0', color='green')

		self.save_plot_data('io_norm_job0_X', X)
		self.save_plot_data('io_norm_job0_Y', Y)

		aux = (X[-1] - X[0]) * 0.01
		ax.set_xlim([X[0]-aux,X[-1]+aux])

		self.set_x_ticks(ax)

		ax.legend(loc='upper right', ncol=3, frameon=True)

		#chartBox = ax.get_position()
		#ax.set_position([chartBox.x0, chartBox.y0, chartBox.width*0.65, chartBox.height])
		#ax.legend(loc='upper center', bbox_to_anchor=(1.35, 0.9), title='threads', ncol=1, frameon=True)

		fig.tight_layout()

		if self._options.save:
			for f in self._options.formats:
				save_name = f'{self._filename_without_ext}_graph_io_norm.{f}'
				fig.savefig(save_name, bbox_inches="tight")
		plt.show()

	def graph_cpu(self):
		self.graph_cpu_new()
		self.graph_cpu_old()

	def graph_cpu_new(self):
		if 'performancemonitor' not in self._data.keys(): return

		def sum_active(percents):
			s = 0.
			for k, v in percents.items():
				if k not in ('idle', 'iowait', 'steal'):
					s += v
			return s

		fig, axs = plt.subplots(2, 1)
		fig.set_figheight(4)
		fig.set_figwidth(9)
		axs[0].grid()
		axs[1].grid()

		X = [x['time']/60.0 for x in self._data['performancemonitor']]
		Y = [ sum_active(x['cpu']['percent_total']) for x in self._data['performancemonitor'] ]
		#print(Y)
		axs[0].plot(X, Y, '-', lw=1, label='usage (all)')

		Y = [i['cpu']['percent_total']['iowait'] for i in self._data['performancemonitor']]
		axs[0].plot(X, Y, '-', lw=1, label='iowait')

		for i in range(0, int(self._data['performancemonitor'][0]['cpu']['count'])):
			Y = [ sum_active(x['cpu']['percent'][i]) for x in self._data['performancemonitor'] ]
			axs[1].plot(X, Y, '-', lw=1, label='cpu{}'.format(i))

		aux = (X[-1] - X[0]) * 0.01
		for ax in axs:
			ax.set_xlim([X[0]-aux,X[-1]+aux])
			self.set_x_ticks(ax)

		axs[0].set_ylim([-5, None])
		axs[1].set_ylim([-5, 105])
		axs[0].set(title="CPU", ylabel="all CPUs\npercent")
		axs[1].set(xlabel="time (min)", ylabel="per CPU\npercent")

		axs[0].legend(loc='upper right', ncol=2, frameon=True)

		self.add_at3_ticks(axs[0], int(X[0]), int(X[-1]))

		if self._options.save:
			for f in self._options.formats:
				save_name = f'{self._filename_without_ext}_graph_cpu.{f}'
				fig.savefig(save_name, bbox_inches="tight")
		plt.show()

	def graph_cpu_old(self):
		if 'systemstats' not in self._data.keys() or self._data['systemstats'][0].get('cpus.active') is None:
			return

		fig, axs = plt.subplots(2, 1)
		fig.set_figheight(5)
		fig.set_figwidth(8)
		axs[0].grid()
		axs[1].grid()

		X = [i['time']/60.0   for i in self._data['systemstats']]
		Y = [i['cpus.active'] for i in self._data['systemstats']]
		axs[0].plot(X, Y, '-', lw=1, label='usage (all)')

		Y = [i['cpus.iowait'] for i in self._data['systemstats']]
		axs[0].plot(X, Y, '-', lw=1, label='iowait')

		for i in range(0,1024):
			if self._data['systemstats'][0].get('cpu[{}].active'.format(i)) is None:
				break
			Y = [j['cpu[{}].active'.format(i)] for j in self._data['systemstats']]
			axs[1].plot(X, Y, '-', lw=1, label='cpu{}'.format(i))

		aux = (X[-1] - X[0]) * 0.01
		for ax in axs:
			ax.set_xlim([X[0]-aux,X[-1]+aux])
			self.set_x_ticks(ax)

		axs[0].set_ylim([-5, None])
		axs[1].set_ylim([-5, 105])
		axs[0].set(title="cpu", ylabel="all CPUs (%)")
		axs[1].set(xlabel="time (min)", ylabel="per CPU (%)")

		#chartBox = ax.get_position()
		#ax.set_position([chartBox.x0, chartBox.y0, chartBox.width*0.65, chartBox.height])
		#ax.legend(loc='upper center', bbox_to_anchor=(1.35, 0.9), title='threads', ncol=1, frameon=True)

		axs[0].legend(loc='upper right', ncol=2, frameon=True)

		if self._options.save:
			for f in self._options.formats:
				save_name = f'{self._filename_without_ext}_graph_cpu.{f}'
				fig.savefig(save_name, bbox_inches="tight")
		plt.show()

	def graph_at3(self):
		if self._num_at == 0 or self._num_at is None:
			return
		#print(f'graph_at3() filename: {self._filename}')

		fig, axs = plt.subplots(self._num_at, 1)
		fig.set_figheight(5)
		fig.set_figwidth(8)

		ax2 = None
		for i in range(0,self._num_at):
			ax = axs[i] if self._num_at > 1 else axs
			ax.grid()
			cur_at = self._data['access_time3[{}]'.format(i)]
			X = [j['time']/60.0 for j in cur_at]
			Y = [j['total_MiB/s'] if j['wait'] == 'false' else None for j in cur_at]
			ax.plot(X, Y, '-', lw=1, label='total', color='blue')
			Y = [j['read_MiB/s'] if j['wait'] == 'false' else None for j in cur_at]
			ax.plot(X, Y, '-', lw=1, label='read', color='green')
			Y = [j['write_MiB/s'] if j['wait'] == 'false' else None for j in cur_at]
			ax.plot(X, Y, '-', lw=1, label='write', color='orange')

			ax_set = dict()
			ax_set['ylabel'] = f"at3[{i}]\nMB/s"

			if i == 0:
				ax_set['title'] = "access_time3 (at3): performance"
			if i == self._num_at -1:
				ax_set['xlabel'] = "time (min)"
				ax.legend(bbox_to_anchor=(0., -.8, 1., .102), loc='lower left',
					ncol=3, mode="expand", borderaxespad=0.)
			if i>=0 and i < self._num_at -1:
				ax.xaxis.set_ticklabels([])

			aux = (X[-1] - X[0]) * 0.01
			ax.set_xlim([X[0]-aux, X[-1]+aux])
			if i == 0:
				self.add_at3_ticks(ax, int(X[0]), int(X[-1]))

			self.set_x_ticks(ax)

			ax.set(**ax_set)
			#ax.set_yscale('log')

			#chartBox = ax.get_position()
			#ax.set_position([chartBox.x0, chartBox.y0, chartBox.width*0.75, chartBox.height])
			#ax.legend(loc='upper center', bbox_to_anchor=(1.25, 1.0), ncol=2, frameon=True)

		plt.subplots_adjust(hspace=0.1)

		if self._options.save:
			for f in self._options.formats:
				save_name = f'{self._filename_without_ext}_graph_at3.{f}'
				fig.savefig(save_name, bbox_inches="tight")
		plt.show()

	def graph_at3_script(self):
		if self._num_at == 0 or self._num_at is None:
			return

		fig, axs = plt.subplots(self._num_at, 1)
		fig.set_figheight(5)
		fig.set_figwidth(8)

		for i in range(0,self._num_at):
			ax = axs[i] if self._num_at > 1 else axs
			if i == 0:
				ax0 = ax

			ax.grid()
			cur_at = self._data['access_time3[{}]'.format(i)]
			X = [j['time']/60.0 for j in cur_at]
			Y = [j['write_ratio'] if j['wait'] == 'false' else None for j in cur_at]
			ax.plot(X, Y, '-', lw=1.5, label='write_ratio (wr)', color='orange')
			Y = [j['random_ratio'] if j['wait'] == 'false' else None for j in cur_at]
			ax.plot(X, Y, '-.', lw=1.5, label='random_ratio (rr)', color='blue')

			ax_set = dict()

			ax_set['ylabel'] = f'at3[{i}]\nratio'
			if i == 0:
				ax_set['title'] = 'Concurrent Workloads'
			if i == self._num_at -1:
				ax_set['xlabel'] = "time (min)"
				ax.legend(bbox_to_anchor=(0., -.8, 1., .102), loc='lower left',
					ncol=2, mode="expand", borderaxespad=0.)
			if i < self._num_at - 1:
				ax.xaxis.set_ticklabels([])

			aux = (X[-1] - X[0]) * 0.01
			ax.set_xlim([X[0]-aux,X[-1]+aux])
			ax.set_ylim([-0.05,1.08])

			self.set_x_ticks(ax)
			ax.set(**ax_set)

		self.add_at3_ticks(ax0, int(X[0]), int(X[-1]))

		plt.subplots_adjust(hspace=0.1)

		if self._options.save:
			for f in self._options.formats:
				save_name = f'{self._filename_without_ext}_graph_at3_script.{f}'
				fig.savefig(save_name, bbox_inches="tight")
		plt.show()

	def graph_at3_write_ratio(self):
		if self._num_at == 0 or self._num_at is None:
			return
		if self._file_id is None:
			self.load_at3()

		colors = plt.get_cmap('tab10').colors

		block_sizes = DB.query("select distinct block_size from data where file_id = {} order by block_size".format(self._file_id)).fetchall()
		random_ratios = DB.query("select distinct random_ratio from data where file_id = {} order by random_ratio".format(self._file_id)).fetchall()

		for i_bs in block_sizes:
			bs = i_bs[0]
			ci = 0
			fig, ax = plt.subplots()
			fig.set_figheight(5)
			fig.set_figwidth(8)
			ax.grid()
			for i_rr in random_ratios:
				rr = i_rr[0]
				sql1 = '''SELECT write_ratio*100, AVG(mbps) * {}
					FROM data
					WHERE file_id = {} AND block_size = {} AND random_ratio = {}
					GROUP BY write_ratio ORDER BY write_ratio'''
				q1 = DB.query(sql1.format(self._num_at, self._file_id, bs, rr))
				sql2 = '''SELECT write_ratio*100, AVG(mbps)
					FROM data
					WHERE file_id = {} AND block_size = {} AND random_ratio = {} AND number = 0
					GROUP BY write_ratio ORDER BY write_ratio'''
				q2 = DB.query(sql2.format(self._file_id, bs, rr))

				A = numpy.array(q1.fetchall()).T
				B = numpy.array(q2.fetchall()).T

				ax.plot(A[0], A[1], '-', color=colors[ci], lw=1, label='rand {}%, total'.format(int(rr*100)))
				ax.plot(B[0], B[1], '.-', color=colors[ci], lw=1, label='rand {}%, job0'.format(int(rr*100)))
				ci += 1

			ax.set(title='jobs={}, bs={}, {}'.format(self._num_at, bs, 'O_DIRECT+O_DSYNC' if self._at_direct_io else 'cache'),
				xlabel='(writes/reads)*100', ylabel='MB/s')

			chartBox = ax.get_position()
			ax.set_position([chartBox.x0, chartBox.y0, chartBox.width*0.65, chartBox.height])
			ax.legend(loc='upper center', bbox_to_anchor=(1.25, 0.9), ncol=1, frameon=True)
			#ax.legend(loc='best', ncol=1, frameon=True)

			if self._options.save:
				for f in self._options.formats:
					save_name = f'{self._filename_without_ext}-at3_bs{bs}.{f}'
					fig.savefig(save_name, bbox_inches="tight")
			plt.show()

	_pressure_data = None
	@property
	def pressure_data(self):
		if self._pressure_data is None:
			ret = dict()

			num_dbbench, num_ycsb = self.count_dbs()
			num_at3 = self._num_at
			if num_dbbench == 0 and num_ycsb == 0: return None
			if num_at3 == 0: return None

			target_attribute = 'ops_per_s'
			if num_ycsb > 0:
				target_db = self._data['ycsb[0]']
			else:
				target_db = self._data['db_bench[0]']

			target_data = collections.OrderedDict()
			for i in target_db:
				target_data[i['time']] = collections.OrderedDict()
				target_data[i['time']]['db'] = i

				w = self.last_at3(i['time'])
				target_data[i['time']]['at3'] = w['name']
				target_data[i['time']]['at3_counter'] = w['number']

			timelist = list(target_data.keys()); timelist.sort()

			pd1 = pd.DataFrame({
				'time'      : timelist,
				'ops_per_s' : [ target_data[t]['db'][target_attribute] for t in timelist ],
				'w'         : [ target_data[t]['at3'] for t in timelist ],
				'w_counter' : [ target_data[t]['at3_counter'] for t in timelist ],
				})
			ret['pd1'] = pd1

			if self._options.use_at3_counters:
				pd2 = pd1.groupby(['w', 'w_counter']).agg({'ops_per_s':'mean'}).sort_values('w_counter')
			else:
				pd2 = pd1.groupby(['w', 'w_counter']).agg({'ops_per_s':'mean'}).sort_values('ops_per_s', ascending=False)

			ret['pd2'] = pd2

			ret['W_names'] = [x[0] for x in pd2.index]
			w0 = pd2.loc['w0', 0][0]
			ret['w0'] = w0
			ret['W_pressure'] = [i[0] for i in pd2.values]
			ret['W_normalized'] = [(w0 - i) / w0 for i in ret['W_pressure']]

			ret['time'] = []
			ret['time_min'] = []
			for n in ret['W_names']:
				t = self.w_list[n]['time']
				ret['time'].append(t)
				ret['time_min'].append(t/60.0)

			if callable(self._options.all_pressure_label):
				file_label = self._options.all_pressure_label(self)
			else:
				file_label = f'bs = {self._params["at_block_size[0]"]}'
			ret['file_label'] = file_label

			self._pressure_data = ret

		return self._pressure_data

	def graph_pressure(self, **kargs):
		data = self.pressure_data
		if data is None: return
		pd2 = data['pd2']

		args = copy.copy(self._options.args_pressure)
		for k, v in kargs.items():
			args[k] = v

		fig = plt.figure()
		fig.set_figheight(2.8)
		fig.set_figwidth(9)

		ax = fig.add_axes([0,1,1,1])

		X_labels = data['W_names']
		X = range(len(X_labels))
		Y = data['W_pressure']
		ax.bar(X, Y, label='throughput')
		ax.set_xticks(X)
		ax.set_xticklabels(X_labels, rotation=90)

		ax.set(xlabel="$w_i$", ylabel="$\\rho(w_i)$")
		ax.legend(loc='upper center', ncol=1, frameon=False)

		ax2 = ax.twinx()
		ax2.set_yticks([ 0, 0.25, 0.5, 0.75, 1])
		ax2.grid()
		ax2.yaxis.set_visible(True)
		ax2.xaxis.set_visible(False)

		w0 = data['w0']
		Y2 = data['W_normalized']
		ax2.plot(X, Y2, '-', label='normalized pressure', color='red')

		X3, Y3 = [], []
		min_p = Y2[0]
		for i in range(1, len(Y2)):
			if Y2[i] < min_p:
				X3.append(X[i])
				Y3.append(Y2[i])
			else:
				min_p = Y2[i]
		if args.get('mark_decreased'):
			ax2.plot(X3, Y3, '*', label='decreased', color='red')
		ax2.legend(loc='upper right', ncol=2, frameon=False)
		ax2.set(ylabel="normalized pressure")

		ax.set_ylim([0, 1.1*w0])
		ax2.set_ylim([min(0, min(Y2)), 1.1])

		######################################################
		ax = fig.add_axes([0, 0.62, 1, 0.16])

		X = data['W_normalized']
		Y = [0 for i in X]
		ax.plot(X, Y, 'o', label='pressure')

		if args.get('print_values'):
			print(f'Pressure values: {", ".join([f"w{i}={X[i]:.3f}" for i in range(0,len(X))])}\n')

		ax.set_xlim([min(0, min(X))-0.05, 1.05])
		ax.set_ylim([-0.02, 0.1])
		ax.yaxis.set_ticklabels([])

		for i in range(len(X)):
			ax.annotate(f'{X_labels[i]}', xy=(X[i], 0), xytext=(X[i]-0.006,0.035), rotation=90)

		ax.xaxis.set_major_locator(MultipleLocator(0.1))
		ax.xaxis.set_minor_locator(AutoMinorLocator(4))
		ax.grid(which='major', color='#888888', linestyle='--')
		ax.grid(which='minor', color='#CCCCCC', linestyle=':')

		ax.set(xlabel="normalized pressure: $(\\rho(w_0)-\\rho(w_i)) / \\rho(w_0)$")

		if self._options.save:
			for f in self._options.formats:
				save_name = f'{self._filename_without_ext}-pressure.{f}'
				fig.savefig(save_name, bbox_inches="tight")
		plt.show()

	def get_container_names(self):
		perfmon_data = self._data.get('performancemonitor')
		if perfmon_data is None: return

		container_names = []
		for d in perfmon_data:
			containers_data = d.get('containers')
			if containers_data is None: continue
			for k in containers_data.keys():
				if k not in container_names:
					container_names.append(k)
		return container_names

	def map_container_names(self):
		names = self.get_container_names()
		stats_keys = self._data.keys()
		#print(f'stats_keys: {stats_keys}')

		ret = {'container_names':names, 'stats2container':{}, 'container2stats':{}}
		for n in names:
			r = re.findall(r'^([^_]+)_([0-9]+)$', n)
			if len(r) > 0:
				if r[0][0] == 'at3':
					name_stats = f'access_time3[{r[0][1]}]'
				else:
					name_stats = f'{r[0][0]}[{r[0][1]}]'
				if name_stats in stats_keys:
					ret['stats2container'][name_stats] = n
					ret['container2stats'][n] = name_stats
				else:
					print(f'WARNING: container name "{n}" without corresponding stats')
			else:
				print(f'WARNING: container name "{n}" without pattern')
		return ret

	def graph_containers_io(self):
		perfmon_data = self._data.get('performancemonitor')
		if perfmon_data is None: return

		containers_map = self.map_container_names()
		#print(f'containers_map: {containers_map}')
		if len(containers_map['container_names']) == 0: return
		containers_map['container_names'].sort()

		colors = plt.get_cmap('tab10').colors

		fig, axs = plt.subplots(len(containers_map['container_names'])+1, 1)
		fig.set_figheight(10)
		fig.set_figwidth(9)

		X = [x['time']/60.0 for x in self._data['performancemonitor']]
		sum_Y1r = numpy.array([0. for x in X])
		sum_Y1w, sum_Y2r, sum_Y2w = sum_Y1r.copy(), sum_Y1r.copy(), sum_Y1r.copy()

		for i in range(len(axs)):
			ax = axs[i]
			ax.grid()

			if i == (len(axs)-1):
				c_name = 'ALL'
				Y1r, Y1w = sum_Y1r, sum_Y1w
			else:
				c_name = containers_map['container_names'][i]
				Y1r = [scale(get_recursive(x, 'containers', c_name, 'blkio.service_bytes/s', 'Read'), 1024 ** 2) for x in self._data['performancemonitor']]
				sum_Y1r += [coalesce(y,0.) for y in Y1r]
				Y1w = [scale(get_recursive(x, 'containers', c_name, 'blkio.service_bytes/s', 'Write'), 1024 ** 2) for x in self._data['performancemonitor']]
				sum_Y1w += [coalesce(y,0.) for y in Y1w]
			ax.plot(X, Y1r, '-', lw=1, label=f'MiB read', color=colors[0])
			ax.plot(X, Y1w, '-.', lw=1, label=f'MiB write', color=colors[1])

			ax.set(ylabel=f"{c_name}\nMiB/s")

			ax2 = ax.twinx()

			if i == (len(axs)-1):
				Y2r, Y2w = sum_Y2r, sum_Y2w
			else:
				Y2r = [get_recursive(x, 'containers', c_name, 'blkio.serviced/s', 'Read') for x in self._data['performancemonitor']]
				sum_Y2r += [coalesce(y,0.) for y in Y2r]
				Y2w = [get_recursive(x, 'containers', c_name, 'blkio.serviced/s', 'Write') for x in self._data['performancemonitor']]
				sum_Y2w += [coalesce(y,0.) for y in Y2w]
			ax2.plot(X, Y2r, ':', lw=1, label=f'IO read', color=colors[2])
			ax2.plot(X, Y2w, ':', lw=1, label=f'IO write', color=colors[3])

			ax2.set(ylabel="IOPS")

			if i == (len(axs)-1):
				ax.legend(bbox_to_anchor=(0., -.8, .48, .102), loc='lower left',
					ncol=2, mode="expand", borderaxespad=0.)
				ax2.legend(bbox_to_anchor=(.52, -.8, .48, .102), loc='lower right',
					ncol=2, mode="expand", borderaxespad=0.)

		aux = (X[-1] - X[0]) * 0.01
		for ax in axs:
			ax.set_xlim([X[0]-aux,X[-1]+aux])
			self.set_x_ticks(ax)

		axs[0].set(title="Containers I/O")
		axs[-1].set(xlabel="time (min)")

		self.add_at3_ticks(axs[0], int(X[0]), int(X[-1]))

		if self._options.save:
			for f in self._options.formats:
				save_name = f'{self._filename_without_ext}_graph_containers_io.{f}'
				fig.savefig(save_name, bbox_inches="tight")
		plt.show()

	def get_lsm_levels(self, container='ycsb[0]'):
		base_str = f'{container}.socket_report.rocksdb.cfstats.compaction'
		ret = []
		df = self.pd_data
		for i in df.keys():
			if i.find(base_str) >= 0:
				r = re.findall(r'\.L([0-9]+)\.SizeBytes', i)
				if len(r) > 0:
					ret.append(int(r[0]))
		ret.sort()
		return ret

	def graph_ycsb_lsm_stats(self, **kargs):
		level_list = self.get_lsm_levels()
		l_max = level_list[-1] if len(level_list) > 0 else -1
		if l_max < 0:
			return

		args = self.overlap_args(kargs)
		df = self.pd_data

		x_min, x_max = df['time_min'].min(), df['time_min'].max()
		aux = (x_max - x_min) * 0.01

		ax_space = 2
		fig = plt.figure()
		gs = fig.add_gridspec((l_max + 1) * 2 + ax_space, 2, hspace=0.0, wspace=0.2)
		axs = gs.subplots()
		fig.suptitle(self.get_graph_title(args, "LSM-tree stats"), y=1.0)
		fig.set_figheight(9)
		fig.set_figwidth(14)

		graphs = [
			{'stat_name': 'SizeBytes',
			 'axs': [axs[i, 0] for i in range(0, l_max + 1)],
			 'scale': 1024.0 ** 3,
			 'title': 'Size (GiB)'},
			{'stat_name': 'Score',
			 'axs': [axs[i, 0] for i in range(l_max+1+ax_space, (l_max + 1) * 2 + ax_space)],
			 'scale': 1},
			{'stat_name': 'NumFiles',
			 'axs': [axs[i, 1] for i in range(0, l_max + 1)],
			 'scale': 1},
			{'stat_name': 'CompactedFiles',
			 'axs': [axs[i, 1] for i in range(l_max+1+ax_space, (l_max + 1) * 2 + ax_space)],
			 'scale': 1},
		]
		for i in range(1, ax_space+1):
			fig.delaxes(axs[l_max + i, 0])
			fig.delaxes(axs[l_max + i, 1])

		df_keys = df.keys()

		for l in range(0, l_max + 1):
			for g in graphs:
				ax = g['axs'][l]
				y_key = f'ycsb[0].socket_report.rocksdb.cfstats.compaction.L{l}.{g["stat_name"]}'
				if y_key in df_keys:
					Y = [v / g['scale'] for v in df[y_key]]
					ax.plot(df['time_min'], Y, '-', lw=1.4)

				if l == 0:
					ax.set(title=g['stat_name'] if g.get('title') is None else g['title'])
				elif l < l_max:
					ax.sharex(g['axs'][l_max])
				elif l == l_max:
					ax.set_xlim([x_min - aux, x_max + aux])
					self.set_x_ticks(ax)
					ax.tick_params(axis='x', which='both', bottom=True)
					ax.set_xlabel('time (min)', labelpad=1.0)
				ax.set_ylabel(f'L{l}', labelpad=4.5)
				ax.set_ylim([-0.1, None])

		for g in graphs:
			for l in range(0,l_max):
				ax = g['axs'][l]
				ax.tick_params(axis='x', labelbottom=False)
				ax.grid(which='major', color='#CCCCCC', linestyle='--')
				ax.grid(which='minor', color='#CCCCCC', linestyle=':')

			self.add_at3_ticks(g['axs'][0], int(x_min), int(x_max))

		if self._options.save:
			for f in self._options.formats:
				save_name = f'{self._filename_without_ext}_graph_lsm.{f}'
				fig.savefig(save_name, bbox_inches="tight")
		plt.show()

	def graph_ycsb_lsm_generic(self, stats_name: str, y_label: str, y_f, **kargs) -> None:
		level_list = self.get_lsm_levels()
		l_max = level_list[-1] if len(level_list) > 0 else -1
		if l_max < 0:
			return

		args = self.overlap_args(kargs)
		df = self.pd_data

		x_min, x_max = df['time_min'].min(), df['time_min'].max()
		aux = (x_max - x_min) * 0.01

		fig, axs = plt.subplots(l_max +1, 1)
		fig.set_figheight(5)
		fig.set_figwidth(9)

		df_keys = df.keys()

		for l in range(0, l_max + 1):
			ax = axs[l]
			y_key = f'ycsb[0].socket_report.rocksdb.cfstats.compaction.L{l}.{stats_name}'
			y_max = 0
			if y_key in df_keys:
				Y = [y_f(v) for v in df[y_key]]
				ax.plot(df['time_min'], Y, '-', lw=1.4, label=f'L{l}')
				y_max = max(Y)

			ax.set(ylabel=y_label.format(**locals()))
			if ax != axs[-1]:
				ax.set(xticklabels=[])

			ax.set_xlim([x_min - aux, x_max + aux])
			try:
				ax.set_ylim([-.01, y_max * 1.05])
			except:
				print(f'ylim exception: y_max={y_max}')
				ax.set_ylim([-.01, None])

			if l == 0:
				self.add_at3_ticks(ax, int(x_min), int(x_max))
			self.set_x_ticks(ax)

		axs[0].set(title=self.get_graph_title(args, f"LVM-tree stats: {stats_name}"))
		axs[-1].set(xlabel="time (min)")

		if self._options.save:
			file_suffix = coalesce(args.get('file_suffix'), stats_name)
			for f in self._options.formats:
				save_name = f'{self._filename_without_ext}_graph_lsm_{file_suffix}.{f}'
				fig.savefig(save_name, bbox_inches="tight")
		plt.show()

	def graph_ycsb_lsm_size(self, **kargs) -> None:
		self.graph_ycsb_lsm_generic(
			stats_name='SizeBytes',
			y_label='L{l}\nGiB',
			y_f=lambda y: float(coalesce(y, 0)) / (1024 ** 3),
			**kargs)

	def graph_ycsb_lsm_details(self, **kargs) -> None:
		for i in ['CompactedFiles', 'NumFiles', 'ReadMBps', 'Score', 'WriteAmp', 'WriteMBps']:
			self.graph_ycsb_lsm_generic(
				stats_name=i,
				y_label=f'L{{l}}',
				y_f=lambda y: float(coalesce(y, 0)),
				**kargs)

	def graph_ycsb_lsm_summary(self, **kargs) -> None:
		ycsb_data = get_recursive(self._data, 'ycsb[0]')
		if ycsb_data == None or get_recursive(ycsb_data, 0, 'socket_report', 'rocksdb.cfstats') == None:
			return

		X = [x['time']/60.0 for x in self._data['ycsb[0]']]
		aux = (X[-1] - X[0]) * 0.01

		fig, axs = plt.subplots(2, 1)
		fig.set_figheight(6)
		fig.set_figwidth(9)

		ax = axs[0]
		Y1 = [float(coalesce(get_recursive(y, 'socket_report', 'rocksdb.cfstats', 'compaction.Sum.ReadMBps', 0))) for y in ycsb_data]
		ax.plot(X, Y1, '-', lw=1.4, label='read')
		Y2 = [float(coalesce(get_recursive(y, 'socket_report', 'rocksdb.cfstats', 'compaction.Sum.WriteMBps', 0))) for y in ycsb_data]
		ax.plot(X, Y2, '-', lw=1.4, label='write')
		ax.set(ylabel='compaction\nMiB/s')
		ax.set(xticklabels=[])
		ax.set_ylim([-.01, max([max(Y1), max(Y2)]) * 1.1])

		ax = axs[1]
		Y1 = [float(coalesce(get_recursive(y, 'socket_report', 'rocksdb.cfstats', 'io_stalls.total_slowdown', 0))) for y in ycsb_data]
		ax.plot(X, Y1, '-', lw=1.4, label='total slowdown')
		Y2 = [float(coalesce(get_recursive(y, 'socket_report', 'rocksdb.cfstats', 'io_stalls.total_stop', 0))) for y in ycsb_data]
		ax.plot(X, Y2, '-', lw=1.4, label='total stop')
		ax.set(ylabel='iostalls')
		#ax.set(xticklabels=[])
		ax.set_ylim([-.01, max([max(Y1), max(Y2)]) * 1.1])

		for ax in axs:
			ax.set_xlim([X[0]-aux,X[-1]+aux])
			self.set_x_ticks(ax)
			ax.legend(loc='best', ncol=1, frameon=False)

		axs[0].set(title='LSM-tree stats summary')
		axs[-1].set(xlabel="time (min)")

		self.add_at3_ticks(axs[0], int(X[0]), int(X[-1]))

		if self._options.save:
			for f in self._options.formats:
				save_name = f'{self._filename_without_ext}_graph_lsm_summary.{f}'
				fig.savefig(save_name, bbox_inches="tight")
		plt.show()

	def graph_smart_utilization(self):
		perfmon_data = get_recursive(self._data, 'performancemonitor')
		if perfmon_data == None:
			return
		if get_recursive(perfmon_data, 0, 'smart', 'capacity') == None or get_recursive(perfmon_data, 0, 'smart', 'utilization') == None:
			return

		fig, axs = plt.subplots(1, 1)
		fig.set_figheight(2)
		fig.set_figwidth(9)

		ax = axs

		capacity = float(get_recursive(perfmon_data, 0, 'smart', 'capacity'))
		X = [x['time']/60.0 for x in perfmon_data]
		Y = [100. * float(coalesce(get_recursive(y, 'smart', 'utilization'), 0)) / capacity for y in perfmon_data]
		ax.plot(X, Y, '-', lw=2)

		ax.set(title="Flash Pages Utilization")
		ax.set(xlabel="time (min)")
		ax.set(ylabel=f"percent")
		#ax.legend(loc='upper right', ncol=2, frameon=False)

		aux = (X[-1] - X[0]) * 0.01
		ax.set_xlim([X[0]-aux,X[-1]+aux])
		self.add_at3_ticks(ax, int(X[0]), int(X[-1]))

		self.set_x_ticks(ax)
		ax.set_ylim([-1, 105])

		if self._options.save:
			for f in self._options.formats:
				save_name = f'{self._filename_without_ext}_graph_smart_utilization.{f}'
				fig.savefig(save_name, bbox_inches="tight")
		plt.show()

	def graph_pairgrid(self, **kargs):
		if self._num_ydbs > 0:
			first_metrics = {
				"ycsb[0].ops_per_s": "kv:ops/s",
				'performancemonitor.containers.ycsb_0.blkio.serviced/s.Read': 'kv:r/s',
				'performancemonitor.containers.ycsb_0.blkio.serviced/s.Write': 'kv:w/s',
			}
			pairgrid_kargs = {'hue':'w'}
		elif self._num_at > 0:
			first_metrics = {"access_time3[0].iodepth": "iodepth"}
			pairgrid_kargs = {}
		else:
			return

		args = self.overlap_args(self._options.args_pairgrid, kargs)

		cols = {
			**first_metrics,
			"performancemonitor.disk.iostat.r/s": "disk:r/s", #IOPS
			"performancemonitor.disk.iostat.w/s": "disk:w/s",
			"performancemonitor.disk.iostat.rareq-sz": "disk:r_size", #block size
			"performancemonitor.disk.iostat.wareq-sz": "disk:w_size",
			"performancemonitor.disk.iostat.aqu-sz": "disk:queue", #iodepth
			"performancemonitor.disk.iostat.r_await": "disk:r_await",
			"performancemonitor.disk.iostat.w_await": "disk:w_await",
		}
		df = self.pd_data
		if args.get('w') is not None:
			if isinstance(args['w'], list):
				df = df.loc[df['w'].isin(args['w'])]
			else:
				df = df.loc[df['w'] == args['w']]

		if args.get('y_vars') is not None:
			pairgrid_kargs['x_vars'] = [i for i in cols.values()]
			pairgrid_kargs['y_vars'] = args.get('y_vars')
		else:
			pairgrid_kargs['vars'] = [i for i in cols.values()]

		df2 = df.rename(columns=cols)
		g = sns.PairGrid(df2, diag_sharey=False, palette='viridis', **pairgrid_kargs)
		m1 = g.map_upper(sns.scatterplot)
		m2 = g.map_lower(sns.scatterplot)
		g.map_diag(sns.ecdfplot)
		g.add_legend()
		for ax in [i for i in m1.axes.flat]+[i for i in m2.axes.flat]:
			ax.grid(which='major', color='#888888', linestyle='--')
			ax.grid(which='minor', color='#CCCCCC', linestyle=':')

		g.axes.flat[0].set_title(self.get_graph_title(args, "Performance Pair Grid"), loc='left')

		fig = g.fig
		if self._options.save:
			for f in self._options.formats:
				save_name = f'{self._filename_without_ext}_graph_pairgrid.{f}'
				fig.savefig(save_name, bbox_inches="tight")
		plt.show()

	def graph_pairgrid_kv(self, **kargs):
		cols = {
			"ycsb[0].ops_per_s": "ops/s",
			'performancemonitor.containers.ycsb_0.blkio.serviced/s.Read': 'r/s',
			'performancemonitor.containers.ycsb_0.blkio.serviced/s.Write': 'w/s',
		}

		args = self.overlap_args(self._options.args_pairgrid_kv, kargs)

		df = self.pd_data
		if args.get('w') is not None:
			if isinstance(args['w'], list):
				df = df.loc[df['w'].isin(args['w'])]
			else:
				df = df.loc[df['w'] == args['w']]

		df2 = df.rename(columns=cols)

		g = sns.PairGrid(df2, hue='w', vars=[v for v in cols.values()], diag_sharey=False, palette='viridis')
		m1 = g.map_upper(sns.scatterplot)
		m2 = g.map_lower(sns.kdeplot)
		g.map_diag(sns.ecdfplot)
		for ax in [i for i in m1.axes.flat] + [i for i in m2.axes.flat]:
			ax.grid(which='major', color='#888888', linestyle='--')
			ax.grid(which='minor', color='#CCCCCC', linestyle=':')
		g.add_legend()

		g.axes.flat[0].set_title(self.get_graph_title(args, "Performance KV Pair Grid"), loc='left')

		fig = g.fig
		if self._options.save:
			for f in self._options.formats:
				save_name = f'{self._filename_without_ext}_graph_pairgrid_kv.{f}'
				fig.savefig(save_name, bbox_inches="tight")
		plt.show()

	def set_x_ticks(self, ax):
		if self._options.graphTickMajor is not None:
			ax.xaxis.set_major_locator(MultipleLocator(self._options.graphTickMajor))
			ax.xaxis.set_minor_locator(AutoMinorLocator(self._options.graphTickMinor))
			ax.grid(which='major', color='#CCCCCC', linestyle='--')
			ax.grid(which='minor', color='#CCCCCC', linestyle=':')

	def graph_all(self):
		print(f'Graphs from file "{self._filename}":')
		description = self._filename
		if self._options.file_description is not None:
			if isinstance(self._options.file_description, str):
				description = self._options.file_description
			elif callable(self._options.file_description):
				description = self._options.file_description(self)
		if self._options.print_params:
			self.print_params()
			
		## Generic Graphs:
		if self._options.plot_db:
			print(f'Database Performance: {description}')
			self.graph_db()
		if self._options.plot_io:
			print(f'I/O Performance: {description}')
			self.graph_io()
		if self._options.plot_cpu:
			print(f'CPU Utilization: {description}')
			self.graph_cpu()
		if self._options.plot_at3:
			print(f'access_time3 Performance: {description}')
			self.graph_at3()
		if self._options.plot_at3_script:
			print(f'Concurrent Workloads (at3_script): {description}')
			self.graph_at3_script()
		if self._options.plot_pressure:
			print(f'Pressure: {description}')
			self.graph_pressure()
		if self._options.plot_containers_io:
			print(f'Containers I/O: {description}')
			self.graph_containers_io()
		if self._options.plot_ycsb_lsm_stats:
			print(f'LSM-tree stats: {description}')
			self.graph_ycsb_lsm_stats()
		if self._options.plot_ycsb_lsm_size:
			print(f'LSM-tree level sizes: {description}')
			self.graph_ycsb_lsm_size()
		if self._options.plot_ycsb_lsm_details:
			print(f'LSM-tree details: {description}')
			self.graph_ycsb_lsm_details()
		if self._options.plot_ycsb_lsm_summary:
			print(f'LSM-tree summary: {description}')
			self.graph_ycsb_lsm_summary()
		if self._options.plot_smart_utilization:
			print(f'Occupied flash pages: {description}')
			self.graph_smart_utilization()
		if self._options.plot_pairgrid:
			print(f'Pair grid: {description}')
			self.graph_pairgrid()
		if self._options.plot_pairgrid_kv:
			print(f'Pair grid KV: {description}')
			self.graph_pairgrid_kv()

		## Special case graphs:
		# exp_at3_rww:
		if self._options.plot_io_norm: self.graph_io_norm()
		# exp_at3:
		if self._options.plot_at3_write_ratio: self.graph_at3_write_ratio()


def graph_at3_script(filename, num_at3, max_w):
	fig = plt.gcf()
	#fig, axs = plt.subplots(self._num_at, 1)
	fig.set_figheight(5)
	fig.set_figwidth(9)

	X = [j for j in range(0,max_w+1)]
	X_labels = [f'$w_{{{j}}}$' for j in range(0,max_w+1)]

	write_ratios = [0., 0.1, 0.2, 0.3, 0.5, 0.7, 1.]

	for i in range(0, num_at3):
		#ax = axs[i] if self._num_at > 1 else axs
		ax = host_subplot((100 * num_at3) + 10+i+1, figure=fig)
		#if i == 0:
		#	ax0 = ax

		ax.grid()

		cur_wr = 0
		X2, Y = [], []
		j2 = 0
		for j in range(0,max_w+1):
			if j <= i:
				pass
				#Y.append(None)
			else:
				X2.append(j)
				Y.append(write_ratios[cur_wr])
				j2 += 1
				if j2 >= num_at3:
					cur_wr += 1
					j2 = 0
		ax.plot(X2, Y, '-', lw=1.5, label='write_ratio ($wr$)', color='orange')
		#ax.bar(X2, Y, label='write_ratio (wr)', color='orange')

		Y = [0.5 if j>i else None for j in range(0,max_w+1)]
		ax.plot(X, Y, '-.', lw=1.5, label='random_ratio ($rr$)', color='blue')

		ax_set = dict()

		ax.set_xticks(X)
		if i == 0:
			pass
			#ax_set['title'] = "access_time3: access pattern"
		if i == num_at3 -1:
			ax_set['xlabel'] = "concurrent workloads ($W$)"
			ax.legend(bbox_to_anchor=(0., -.9, 1., .102), loc='lower left',
				ncol=2, mode="expand", borderaxespad=0.)
			ax.set_xticklabels(X_labels)
		if i>=0 and i < num_at3 -1:
			ax.xaxis.set_ticklabels([])

		ax.set_xlim([-0.5,  max_w+0.5])
		ax.set_ylim([-0.05, 1.08])

		ax.set(**ax_set)

		#chartBox = ax.get_position()
		#ax.set_position([chartBox.x0, chartBox.y0, chartBox.width*0.75, chartBox.height])
		#ax.legend(loc='upper center', bbox_to_anchor=(1.25, 1.0), ncol=2, frameon=True)


	plt.subplots_adjust(hspace=0.1)

	save_name = filename
	fig.savefig(save_name, bbox_inches="tight")
	plt.show()


def coalesce(*values):
	for v in values:
		if v is not None:
			return v;
	return None


def get_recursive(value, *attributes):
	cur_v = value
	for i in attributes:
		try:
			cur_v = cur_v[i]
		except:
			return None
	return cur_v


def scale(value, divisor):
	if value is not None:
		return value / divisor
	return None


def scale_list(values, divisor):
	return [scale(x, divisor) for x in values]


def try_convert(value, *types):
	for t in types:
		try:
			ret = t(value)
			return ret
		except:
			pass
	return value


def decimal_suffix(value):
	r = re.findall(r' *([0-9.]+) *([TBMK]) *', value)
	if len(r) > 0:
		number = try_convert(r[0][0], int, float)
		suffix = r[0][1]
		if   suffix == "K": number = number * 1000
		elif suffix == "M": number = number * (1000**2)
		elif suffix == "B": number = number * (1000**3)
		elif suffix == "T": number = number * (1000**4)
		return number
	else:
		raise Exception("invalid number")


def binary_suffix(value):
	r = re.findall(r' *([0-9.]+) *([PTGMKptgmk])i{0,1}[Bb]{0,1} *', value)
	if len(r) > 0:
		number = try_convert(r[0][0], int, float)
		suffix = r[0][1]
		if   suffix.upper() == "K": number = number * 1024
		elif suffix.upper() == "M": number = number * (1024**2)
		elif suffix.upper() == "G": number = number * (1024**3)
		elif suffix.upper() == "T": number = number * (1024**4)
		elif suffix.upper() == "P": number = number * (1024**5)
		return number
	else:
		raise Exception("invalid number")


def flat_dict(source, prefix=None, ret=None):
	prefix_add = '' if prefix is None else f'{prefix}.'

	if ret is None:
		ret = collections.OrderedDict()

	if isinstance(source, dict):
		for k, v in source.items():
			flat_dict(v, prefix=f'{prefix_add}{k}', ret=ret)
	elif isinstance(source, list):
		for i in range(len(source)):
			flat_dict(source[i], prefix=f'{prefix_add}{i}', ret=ret)
	else:
		ret[prefix if prefix is not None else 'NONE'] = source

	return ret


def getFiles(dirname: str, str_filter: str = None, list_filter: list = None, lambda_filter=None) -> list:
	if not os.path.isdir(dirname):
		print(f'WARNING: "{dirname}" is not a directory')
		return []
	
	try:
		from natsort import natsorted
		sort_method = natsorted
	except:
		print('WARNING: natsort not installed, using sorted')
		sort_method = sorted
		
	files = []
	for fn in os.listdir(dirname):
		if File.accept_file(fn):
			found_str = str_filter is None
			found_list = list_filter is None
			found_lambda = lambda_filter is None
			
			if str_filter is not None and fn.find(str_filter) >= 0:
				found_str = True

			if list_filter is not None:
				found_list = True
				for list_i in list_filter:
					if fn.find(list_i) < 0:
						found_list = False
						break

			if lambda_filter is not None and lambda_filter(fn):
				found_lambda = True
				
			if (found_str, found_list, found_lambda) == (True, True, True):
				files.append(f'{dirname}/{fn}')

	return sort_method(files)


def plotFiles(filenames, options, allfiles=None):
	if isinstance(allfiles, str):
		allfiles = AllFiles(allfiles, options)
	if allfiles is None:
		for name in filenames:
			f = File(name, options)
			f.graph_all()
	else:
		for name in filenames:
			allfiles.add_file(name)
		allfiles.graph_all()


class FioFiles:
	_options = None
	_files = None
	_data = None
	_pd = None

	def __init__(self, files, options):
		self._options = options
		self._files = []
		self._data = []

		for f in files:
			self.parseFile(f)

		self._pd = pd.DataFrame({
			"rw":           [i['jobs'][0]['job options']['rw']                         for i in self._data],
			"iodepth":      [try_convert(i['jobs'][0]['job options']['iodepth'], int) for i in self._data],
			"bs":           [binary_suffix(i['jobs'][0]['job options']['bs']) for i in self._data],
			"error":        [try_convert(i['jobs'][0]['error'], bool) for i in self._data],
			"bw_min":       [i['jobs'][0]['mixed']['bw_min']                           for i in self._data],
			"bw_max":       [i['jobs'][0]['mixed']['bw_max']                           for i in self._data],
			"bw_agg":       [i['jobs'][0]['mixed']['bw_agg']                           for i in self._data],
			"bw_mean":      [i['jobs'][0]['mixed']['bw_mean']                          for i in self._data],
			"bw_dev":       [i['jobs'][0]['mixed']['bw_dev']                           for i in self._data],
			"iops_min":     [i['jobs'][0]['mixed']['iops_min']                         for i in self._data],
			"iops_max":     [i['jobs'][0]['mixed']['iops_max']                         for i in self._data],
			"iops_mean":    [i['jobs'][0]['mixed']['iops_mean']                        for i in self._data],
			"iops_stddev":  [i['jobs'][0]['mixed']['iops_stddev']                      for i in self._data],
			"iops_samples": [i['jobs'][0]['mixed']['iops_samples']                     for i in self._data],
			})

	def parseFile(self, filename):
		try:
			with open(filename, "r") as f:
				j = json.load(f)
				self._files.append(filename)
				self._data.append(j)
		except Exception as e:
			print("failed to read file {}: {}".format(filename, str(e)))

	def sortPatterns(self, patterns):
		ret = []
		desired_order = ['read', 'randread', 'write', 'randwrite']
		for p in desired_order:
			if p in patterns: ret.append(p)
		for p in patterns:
			if p not in desired_order: ret.append(p)
		return ret

	def graph_bw(self):
		pattern_list = self.sortPatterns(self._pd['rw'].value_counts().index)
		for pattern in pattern_list:
			pattern_pd = self._pd[self._pd['rw'] == pattern]
			iodepth_list = list(pattern_pd['iodepth'].value_counts().index)
			iodepth_list.sort()
			X_values = list(pattern_pd['bs'].value_counts().index)
			X_values.sort()
			#print(X_values)

			fig, ax = plt.subplots()
			fig.set_figheight(4)
			fig.set_figwidth(9.8)

			X_labels = [ str(int(x/1024)) for x in X_values]
			#print(X_labels)

			Y_max = 0
			width=0.07
			s_width=0.0-((width * len(iodepth_list))/2)
			for iodepth in iodepth_list:
				X = [ x+s_width for x in range(0,len(X_values)) ]
				#print(X)
				Y = [ float(pattern_pd[(pattern_pd['iodepth']==iodepth)&(pattern_pd['bs']==x)]['bw_mean']) for x in X_values ]
				Y_dev = [ float(pattern_pd[(pattern_pd['iodepth']==iodepth)&(pattern_pd['bs']==x)]['bw_dev']) for x in X_values ]
				#print(Y)
				label = f'iodepth {iodepth}' if iodepth == 1 else f'{iodepth}'
				ax.bar(X, Y, yerr=Y_dev, label=label, width=width)
				Y_max = max([ Y_max, max(numpy.array(Y) + numpy.array(Y_dev)) ])
				s_width += width

			ax.set_xticks([ x for x in range(0, len(X_labels))])
			ax.set_xticklabels(X_labels)

			ax.set_ylim([0, Y_max * 1.2])

			ax.set(title="fio {}".format(pattern), xlabel="block size (KiB)", ylabel="KiB/s")
			ax.legend(loc='upper left', ncol=8, frameon=False)

			if self._options.save:
				folder = f'{self._options.fio_folder}/' if self._options.fio_folder is not None else ''
				for f in self._options.formats:
					save_name = f'{folder}fio_bw_{pattern}.{f}'
					fig.savefig(save_name, bbox_inches="tight")
			plt.show()

	def graph_iops(self):
		pattern_list = self.sortPatterns(self._pd['rw'].value_counts().index)
		for pattern in pattern_list:
			pattern_pd = self._pd[self._pd['rw'] == pattern]
			iodepth_list = list(pattern_pd['iodepth'].value_counts().index)
			iodepth_list.sort()
			X_values = list(pattern_pd['bs'].value_counts().index)
			X_values.sort()
			#print(X_values)

			fig, ax = plt.subplots()
			fig.set_figheight(4)
			fig.set_figwidth(9.8)

			X_labels = [ str(int(x/1024)) for x in X_values ]
			#print(X_labels)

			Y_max = 0
			width=0.07
			s_width=0.0-((width * len(iodepth_list))/2)
			for iodepth in iodepth_list:
				X = [ x+s_width for x in range(0,len(X_values)) ]
				#print(X)
				Y = [ float(pattern_pd[(pattern_pd['iodepth']==iodepth)&(pattern_pd['bs']==x)]['iops_mean']) for x in X_values ]
				Y_dev = [ float(pattern_pd[(pattern_pd['iodepth']==iodepth)&(pattern_pd['bs']==x)]['iops_stddev']) for x in X_values ]
				#print(Y)
				label = f'iodepth {iodepth}' if iodepth == 1 else f'{iodepth}'
				ax.bar(X, Y, yerr=Y_dev, label=label, width=width)
				Y_max = max([ Y_max, max(numpy.array(Y) + numpy.array(Y_dev)) ])
				s_width += width

			ax.set_xticks([ x for x in range(0, len(X_labels))])
			ax.set_xticklabels(X_labels)

			ax.set_ylim([0, Y_max * 1.2])

			ax.set(title="fio {}".format(pattern), xlabel="block size (KiB)", ylabel="IOPS")
			ax.legend(loc='upper left', ncol=8, frameon=False)

			if self._options.save:
				folder = f'{self._options.fio_folder}/' if self._options.fio_folder is not None else ''
				for f in self._options.formats:
					save_name = f'{folder}fio_iops_{pattern}.{f}'
					fig.savefig(save_name, bbox_inches="tight")
			plt.show()


##############################################################################
if __name__ == '__main__':
	pass
	#mpl.use('Qt5Agg')
	#Options.save = True

	#graph_at3_script('at3_script25.pdf', 4, 25)
	#graph_at3_script('at3_script28.pdf', 4, 28)

