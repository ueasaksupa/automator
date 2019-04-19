#!/usr/bin/env python3
import threading
import re
import sys
import os
import time
import datetime
import argparse
####
import yaml
import pprint
import config
import curses
from sessionHandler import DeviceHandler, OptionHandler
###############################################

def isAllDevicesFinished(allDevices):
	for device_per_thread in allDevices:
		for device in device_per_thread:
			if device.isRunning:
				return False
	return True

def printWorker(allDevices):
	stdscr = curses.initscr()
	curses.noecho()
	curses.cbreak()
	while True:
		nodeIndex = 0
		time.sleep(0.5)
		if isAllDevicesFinished(allDevices):
			break
		for device_per_thread in allDevices:
			for device in device_per_thread:
				printline = "Connected to {0}. \tProgress |>{1}".format(device.hostname, device.runningCmd)
				stdscr.addstr(nodeIndex, 0, printline+" "*(device.globalConfig.termWidth - len(printline)))
				nodeIndex += 1
		stdscr.refresh()
	curses.echo()
	curses.nocbreak()
	curses.endwin()

def processWorker(devices):
	for device in devices:
		if device.globalConfig.test:
			print ("INFO: This is test_mode, the command below will NOT exec on devices.")
		device.run()

def stripNonAscii(string):
	''' Returns the string without non ASCII characters'''
	stripped = (c for c in string if 0 < ord(c) < 127)
	return ''.join(stripped)

def purifyParameter(params,option):
	# print (params)
	ip_match = re.search(r'ip=(\d+\.\d+\.\d+\.\d+)', params, re.IGNORECASE)
	user_match = re.search(r'user=([^ \t]+)', params, re.IGNORECASE)
	pass_match = re.search(r'password=([^ \t]+)', params, re.IGNORECASE)
	port_match = re.search(r'port=(\d+)', params, re.IGNORECASE)
	param_match = re.search(r'param=([^ \t]*)', params, re.IGNORECASE)
	workbook_match = re.search(r'workbook=([^ \t]*)', params, re.IGNORECASE)
	if ip_match:
		host = ip_match.group(1)
	else:
		host = ''
		print ("ERROR: host ip not found.")
	if user_match:
		user = user_match.group(1)
	else:
		user = config.DEFAULT_USER
	if pass_match:
		password = pass_match.group(1)
	else:
		password = config.DEFAULT_PASSWORD
	if port_match:
		port = port_match.group(1)
	else:
		port = option.port
	if workbook_match:
		workbook = workbook_match.group(1)
	else:
		workbook = option.workbook
	if param_match:
		param = param_match.group(1).split(',')
		params = list(map(str.strip , filter(None, param)))
	else:
		params = None
	if option.debug:
		print ('DEBUG: valus input parameters')
		print ('\tip=',host)
		print ('\tuser=',user)
		print ('\tpass=',password)
		print ('\tport=',port)
		print ('\tworkbook=',workbook)
		print ('\tparams=>',params)
		print ('################')
	return host,user,password,port,workbook,params

def createCommandList(workbook,option):
	# 1st priority : RAW command
	if option.rawCMD != '':
		cmd_line = [{'exec': {'cmd': option.rawCMD.strip().split(';') }}]
		return tuple(cmd_line)
	# 2nd priority : WORKBOOK from args
	elif option.workbook != '':
		with open('./'+option.workbook, 'r') as f:
			lines = f.read()
			return_list = yaml.load(lines)
		return tuple(return_list)
	# 3rh priority : WORKBOOK in hostfile
	elif workbook != '':
		with open('./'+workbook, 'r') as f:
			lines = f.read()
			return_list = yaml.load(lines)
		return tuple(return_list)

def createDeviceObject(option):
	ip_addr_list = []
	if option.hostIP != '':
		ip_addr_list.append('ip='+option.hostIP)
	if option.hostFILE != '':
		with open('./'+option.hostFILE, 'r') as f:
			for line in f:
				if not line.strip().startswith('#'):
					ip_addr_list.append(stripNonAscii(line.strip()))

	### in case IP ADDR more than THREAD
	### create THREAD array and mod IP into each THREAD
	if len(ip_addr_list) >= option.thread:
		all_devices = []
		for i in range(option.thread):
			all_devices.append([])
		for i in range(len(ip_addr_list)):
			host_ip,user,password,port,workbook,params = purifyParameter(ip_addr_list[i],option)
			cmdlist = createCommandList(workbook, option)
			if option.debug:
				print ("DEBUG: cmdlist variable")
				pprint.pprint(cmdlist)
			device = DeviceHandler(ip_addr=host_ip, username=user, password=password, globalConfig=option, cmd=cmdlist, params=params)
			all_devices[i % option.thread].append(device)

	### in case IP ADDR less than THREAD
	### Each IP ADDR has it own THREAD
	else:
		all_devices = []
		for i in range(len(ip_addr_list)):
			all_devices.append([])
		for i in range(len(ip_addr_list)):
			host_ip,user,password,port,workbook,params = purifyParameter(ip_addr_list[i],option)
			cmdlist = createCommandList(workbook, option)
			if option.debug:
				print ("DEBUG: cmdlist variable")
				pprint.pprint(cmdlist)
			device = DeviceHandler(ip_addr=host_ip, username=user, password=password, globalConfig=option, cmd=cmdlist, params=params)
			all_devices[i].append(device)

			# print (option)
		# pprint.pprint (all_devices[0][0].rawCMD)

	return all_devices

def makeOutput(devices, option):
	if option.outPerHost and option.outputPath:
		if option.debug:
			print ("DEBUG: executing makeOuput per host")
		for device_per_thread in devices:
			for device in device_per_thread:
				if not device.isError: 
					with open(device.globalConfig.outputPath.rstrip('/')+"/"+device.hostname.replace('/','_').replace(':','_')+'.txt' , 'w') as f:
						for line in device.output:
							f.write(line.strip() + '\n')
						f.close()
	elif option.outputPath:
		if option.debug:
			print ("DEBUG: executing makeOuput one file")
		with open(option.outputPath.rstrip('/')+"/"+"output.txt", 'w') as f:
			for device_per_thread in devices:
				for device in device_per_thread:
					if not device.isError: 
						for line in device.output:
							f.write(line.strip() + '\n')
			f.close()


def main(option):
	device_object_list = createDeviceObject(option)
	################################################################
	#															   #
	#                         Start task			 			   #
	#															   #
	################################################################
	threads = []
	threadCounter = 0
	for device_per_thread in device_object_list:
		t = threading.Thread(target=processWorker, args=(device_per_thread,))
		threads.append(t)
		t.start()
		threadCounter += 1

	### Real-time printer thread in case running more than 1 thread
	if option.thread > 1:
		t = threading.Thread(target=printWorker, args=(device_object_list,))
		threads.append(t)
		t.start()
		threadCounter += 1

	# wait for all threads complete
	for t in threads:
		t.join()
	if not option.test:
		makeOutput(device_object_list, option)


if __name__ == '__main__':
	### args parser
	parser = argparse.ArgumentParser()
	parser.add_argument('--host', action="store", dest='IP_HOST', default='', help='Ip address of target host. Have to set default user and password in config.py')
	parser.add_argument('--host-file', action="store", dest='IP_FILE', default='', help='Name of file in host directory containing set of ip address')
	parser.add_argument('-d','--debug', action="store_true", dest='DEBUG_MODE', default=False, help='Enable Debug mode: in this mode will show all debug output')
	parser.add_argument('-t','--test', action="store_true", dest='TEST_MODE', default=False, help='Enable test mode: in this mode automator will check the connection and show the command that will be pushed into device but does not do it')
	parser.add_argument('-T','--thread', action="store", dest='MAX_THREAD', default=1, type=int, help='Number of threads')
	parser.add_argument('-p','--port', action="store", dest='TELNET_CONN_PORT', default=23, type=int, help='Specific the Telnet port')
	parser.add_argument('--silent', action="store_true", dest='SILENT_MODE', default=False, help='In silent mode automator will not print output during running. Recommend to use when running in multithread.')
	parser.add_argument('--raw', action="store", dest='RAW_CMD', default='', help="Directly inject the command to device.")
	parser.add_argument('-w','--workbook', action="store", dest='WORKBOOK', default='', help='Specific Workbook filename to use')
	parser.add_argument('--version', action="store_true", dest='VERSION', default=False, help='Show version of script')
	parser.add_argument('-o','--output', action="store", dest='OUT_PATH', default=False, help='Output file path')
	parser.add_argument('--output-per-host', action="store_true", dest='OUT_PER_HOST', default=False, help='Output file path')
	args = parser.parse_args()
	# print args
	if args.VERSION:
		print("automator version 2.0.1")
		print("Written by Nuttawut Ueasaksupa")
		exit()
	###
	if args.MAX_THREAD > 1 and not args.SILENT_MODE :
		silent = True
	elif args.SILENT_MODE:
		silent = True
	else:
		silent = False
	option = {
        "HOST_IP"          : args.IP_HOST,
        "HOST_FILE"        : args.IP_FILE,
        "SILENT_MODE"      : silent,
        "DEBUG_MODE"       : args.DEBUG_MODE,
        "TEST_MODE"        : args.TEST_MODE,
        "MAX_THREAD"       : args.MAX_THREAD,
        "TELNET_CONN_PORT" : args.TELNET_CONN_PORT,
        "RAW_CMD"          : args.RAW_CMD,
        "WORKBOOK"         : args.WORKBOOK,
        "DATETIME"         : datetime.datetime.now().strftime('%Y%m%d_%H%M'),
		"OUTPUT"           : args.OUT_PATH,
		"OUT_PER_HOST"     : args.OUT_PER_HOST
	}
	
	globalConfig = OptionHandler(option)

	if option['DEBUG_MODE']:
		print ("DEBUG: option variable")
		pprint.pprint(option)
	main(globalConfig)
