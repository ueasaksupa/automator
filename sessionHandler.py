import sys
import telnetlib
import re
import time

import shutil
import pprint
import config
#from netmiko import ConnectHandler
#################################

class OptionHandler(object):
	def __init__(self, option):
		(width,height)    = shutil.get_terminal_size()
		self.termWidth    = width
		self.termHeight   = height
		self.debug        = option['DEBUG_MODE']
		self.silent       = option['SILENT_MODE']
		self.hostIP       = option['HOST_IP']      
		self.hostFILE     = option['HOST_FILE']      
		self.thread       = option['MAX_THREAD']
		self.test         = option['TEST_MODE']
		self.port         = option['TELNET_CONN_PORT']
		self.rawCMD       = option['RAW_CMD']
		self.workbook     = option['WORKBOOK']
		self.datetime     = option['DATETIME']    
		self.outputPath   = option['OUTPUT']    
		self.outPerHost   = option['OUT_PER_HOST']    

class DeviceHandler(object):
	"""docstring for DevicesHandler"""
	def __init__(self, ip_addr, username, password, globalConfig, cmd, params):
		self.ip_addr      = ip_addr
		self.username     = username
		self.password     = password
		self.platform     = "cisco"
		self.host_name    = ""
		self.prompt       = ""
		self.conn         = ""
		self.params       = params
		self.cmd          = cmd
		self.isConnect    = False
		self.isError      = False
		self.output       = []
		self.globalConfig = globalConfig

	def connect(self,port=23,timeout=20):
		try:
			connection_object = telnetlib.Telnet(self.ip_addr,port,timeout)
			#
			# Wait and send user, password
			connection_object.read_until(b"Username:",timeout)
			connection_object.write(self.username.encode('ascii') + b"\n")
			connection_object.read_until(b"Password:",timeout)
			connection_object.write(self.password.encode('ascii') + b"\n")
			connection_object.expect([config.PROMPT_RE.encode('ascii')],3)
			time.sleep(0.2)
			connection_object.write(b"\n")
			expect_ret = connection_object.expect([config.PROMPT_RE.encode('ascii')],timeout)
			prompt = str(expect_ret[1].group().strip(), 'ascii')
			nodename = str(expect_ret[1].group(1).strip(), 'ascii')
			connection_object.write(b"terminal length 0\n")
			connection_object.expect([config.PROMPT_RE.encode('ascii')],timeout)
			connection_object.write(b"terminal width 0\n")
			connection_object.expect([config.PROMPT_RE.encode('ascii')],timeout)

			self.host_name = nodename
			self.prompt = prompt
			self.isConnect = True
			self.conn = connection_object
			print ('\r\n'+'*'*(self.globalConfig.termWidth - 50 - len(self.host_name)),"Connected to",self.host_name,'*'*35)

			if not self.globalConfig.silent:
				print (self.prompt, end='')
			if self.globalConfig.debug:
				print ("Connection to",nodename,"established port:",port)
			
		except Exception as e:
			self.isError = True
			print ('\r\n'+'*'*(self.globalConfig.termWidth - 50 - len(self.ip_addr)),"ERROR Cannot Connect to ",self.ip_addr,'*'*23)
			print (e)

	def run(self):
		if not self.isConnect:
			self.connect()

		for instruction in self.cmd:
			if 'exec' in instruction:
				self.__exec_node(instruction['exec'])
			elif 'loop' in instruction:
				self.__loop_node(instruction['loop'])
			elif 'if' in instruction:
				self.__if_node(instruction['if'])

	def __outputPreprocess(self, text, pattern):
		if text.strip() != '':
			output_array = re.findall(pattern, text)
			if self.globalConfig.debug:
				print('DEBUG: RAW OUTPUT',[text])
			self.output.extend(list(filter(lambda a: a != '', output_array)))
			# if not self.globalConfig.silent:
			# 	for line in output_array[:-2]:
			# 		if line != '':
			# 			print (line.strip())
			# 	print (output_array[-2], end='')

	def __sendCommand(self, connection, command_string, promptRE='', realTimeRead=False):
		DEFAULT_TIMEOUT = 30 #second
		READ_WAIT_TIME  = 0.2 #second
		if self.globalConfig.test:
			print('---',command_string)
			return ""
		try:
			output = ''
			if promptRE == '':
				promptRE = r'\r\n\r?\n?('+ self.host_name +r'[^ ]*)[#>]'
			connection.write(command_string.encode('ascii') + b"\n")
			if realTimeRead:
				for i in range(int(DEFAULT_TIMEOUT/READ_WAIT_TIME)):
					time.sleep(READ_WAIT_TIME)
					out = str(connection.read_very_eager(), 'ascii').strip()
					if out != '':
						output += out
						if not self.globalConfig.silent:
							sys.stdout.write(out)
							sys.stdout.flush()
					if promptRE == '':
						if re.search(r'\r\n\r?\n?('+ self.host_name +r'[^ ]*)[#>]', out):
							break
					else:
						if re.search(promptRE, out):
							break
			else:
				output = str(connection.expect([promptRE.encode('ascii')],DEFAULT_TIMEOUT)[2], 'ascii')
				if not self.globalConfig.silent:
					print (output, end='')
			# for netmiko # future feature
			# elif config.CON_PROTO == 'ssh':
				# timeout is 8 sec.
				# text_output = connection.send_command(command_string, strip_prompt=False, strip_command=False, expect_string=promptRE)
			return output
		except Exception as e:
			print ("ERROR:",e)
			return ""

	def __inlineReplaceCommand(self, cmd, iterator=0):
		while re.search(r'\{(\d+)\}', cmd):
			param_match = re.search(r'\{(\d+)\}', cmd)
			position = param_match.group(1)
			try:
				cmd = cmd.replace('{'+str(position)+'}', str(self.params[int(position)]).strip())
			except:
				cmd = cmd.replace('{'+str(position)+'}', '')
		cmd = cmd.replace('{host_name}', self.host_name)
		cmd = cmd.replace('{iterator}', str(iterator))
		cmd = cmd.replace('{datetime}', self.globalConfig.datetime)
		cmd = cmd.replace('{enter}', "")

		return cmd

	def __exec_node(self, instruction, iterator=0):
		expect_string = r'\r\n\r?\n?('+ self.host_name +r'[^ ]*)[#>]'
		filter_word = r'.*'
		delay_value = 0
		realTimeRead = False
		if 'realTimeRead' in instruction:
			realTimeRead = instruction['realTimeRead']
		if 'expect' in instruction:
			expect_string = instruction['expect']
		if 'delay' in instruction:
			delay_value = instruction['delay']
		if 'filter word' in instruction:
			filter_word = instruction['filter word']
		for cmd in instruction['cmd']:
			if self.globalConfig.debug:
				print ("DEBUG: EXPECT STRING",expect_string)
			output = self.__sendCommand(connection=self.conn, command_string=self.__inlineReplaceCommand(cmd,iterator), promptRE=expect_string, realTimeRead=realTimeRead)
			self.__outputPreprocess(output, filter_word)
			if delay_value > 0:
				if not self.globalConfig.silent:
					print("\n*** Sleep",delay_value,"msec ***")
				if not self.globalConfig.test:
					time.sleep(delay_value/1000.0)


	def __loop_node(self, instruction):
		expect_string = config.PROMPT_RE
		loop_to = 1
		loop_from = 0
		step = 1
		delay_value = 0
		if 'to' in instruction:
			loop_to = instruction['to']
		if 'expect' in instruction:
			expect_string = instruction['expect']
		if 'step' in instruction:
			step = instruction['step']
		if 'from' in instruction:
			loop_from = instruction['from']
		if 'delay' in instruction:
			delay_value = instruction['delay']

		for iterator in range(loop_from, loop_to+1, step):
			for exec_node in instruction['loop-exec']:
				self.__exec_node(exec_node['exec'],iterator)
			if delay_value > 0:
				if not self.globalConfig.silent:
					print("\n*** Sleep",delay_value,"msec ***")
				if not self.globalConfig.test:
					time.sleep(delay_value/1000.0)

	def __if_node(self, instruction):
		expect_string = config.PROMPT_RE
		filter_word = r'.*'
		delay_value = 0
		contain = instruction['contain']
		_else = []
		if 'else' in instruction:
			_else = instruction['else']
		if 'expect' in instruction:
			expect_string = instruction['expect']
		if 'delay' in instruction:
			delay_value = instruction['delay']
		if 'filter word' in instruction:
			filter_word = instruction['filter word']

		output = self.__sendCommand(self.conn, self.__inlineReplaceCommand(instruction['cmd']), expect_string)
		print (output, end='')
		if delay_value > 0:
			time.sleep(delay_value/1000.0)
			if not self.globalConfig.silent:
				print("  *** Sleep",delay_value,"msec ***", end='    ')
		
		if contain in output:
			for cmd in instruction['then']:
				output = self.__sendCommand(self.conn, self.__inlineReplaceCommand(cmd), expect_string)
				print (output, end='')
				if delay_value > 0:
					time.sleep(delay_value/1000.0)
					if not self.globalConfig.silent:
						print("  *** Sleep",delay_value,"msec ***", end='    ')
		else:
			for cmd in _else:
				output = self.__sendCommand(self.conn, self.__inlineReplaceCommand(cmd), expect_string)
				print (output, end='')
				if delay_value > 0:
					time.sleep(delay_value/1000.0)
					if not self.globalConfig.silent:
						print("  *** Sleep",delay_value,"msec ***", end='    ')