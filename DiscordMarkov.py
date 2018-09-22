import discord
from discord import ChannelType
import os
import bisect
import random
import pickle
import configparser
import asyncio
import sys
import math
import re
import datetime
from dateutil import tz
import numpy as np
from collections import OrderedDict

class MarkovContainer:
	def __init__(self):
		# user_id : Markov
		self.markovs = {}
		# channel_id : ChannelMetadata
		self.channels_metadata = {}
		
class ChannelMetadata:
	def __init__(self):
		# Channel's first ever message's timestamp
		self.first_message_timestamp = None
		# List of ranges (tuples) of datetime of messages that have already been processed. Datetime objects are in UTC
		# Always sorted from greatest to least (newest to oldest)
		# Guaranteed to contain no overlaps
		self.processed_timestamp_ranges = []
		# Last log update's first message processed's timestamp, as a datetime object
		self.last_update_timestamp = None
		
	def add_timestamp_range(self, min_date, max_date):
		self.processed_timestamp_ranges.append((min_date, max_date))
		n = len(self.processed_timestamp_ranges)
		self.processed_timestamp_ranges.sort()
		
		stack = []
		stack.append(self.processed_timestamp_ranges[0])
		for i in range(n - 1):
			if stack[len(stack) - 1][1] < self.processed_timestamp_ranges[i + 1][0]:
				stack.append(self.processed_timestamp_ranges[i + 1])
			elif stack[len(stack) - 1][1] < self.processed_timestamp_ranges[i + 1][1]:
				stack[len(stack) - 1] = (stack[len(stack) - 1][0], self.processed_timestamp_ranges[i + 1][1])
				
		self.processed_timestamp_ranges.clear()
		for interval in stack:
			self.processed_timestamp_ranges.append(stack.pop())
		
class Markov:
	def __init__(self):
		# Probability distribution of message lengths
		# message_length : [probability, count]
		self.message_lengths = OrderedDict()
		self.total_messages = 0
	
		# Probability distribution of starting words
		# word : [probability, count of that word]
		self.starters = OrderedDict()
		
		# Graph of words
		# Dictionary of OrderedDicts
		# word : {next_word : [probability, count of next_word after word]}
		self.words = {}
		
	def add_message(self, message):
		words_list = message.split()
		words_count = len(words_list)
		
		if words_count == 0:
			return
		
		# Update count of generated messages' lengths
		self.total_messages = self.total_messages + 1
		try:
			self.message_lengths[words_count][1] = self.message_lengths[words_count][1] + 1
		except KeyError:
			self.message_lengths[words_count] = [0, 1]
			
		# Update count of starters
		try:
			self.starters[words_list[0]][1] = self.starters[words_list[0]][1] + 1
		except KeyError:
			self.starters[words_list[0]] = [0, 1]
			
		# Update counts of all words in message
		prev = words_list[0]
		for word in words_list[1:]:
			if self.words.get(prev) is None:
				self.words[prev] = OrderedDict()
		
			if self.words[prev].get(word) is None:
				self.words[prev][word] = [0, 1]
			else:
				self.words[prev][word][1] = self.words[prev][word][1] + 1
			prev = word
		
	def generate_message(self):
		# Choose random length
		r = random.random()
		length = list(self.message_lengths.items())[bisect.bisect_left([x[0] for x in self.message_lengths.values()], r)][0]
		length = max(1, int(round(length * message_length_multiplier)))
		
		# Choose starting word
		r = random.random()
		starter = list(self.starters.items())[bisect.bisect_left([x[0] for x in self.starters.values()], r)][0]
		message = starter
		
		cur_length = 0
		cur_word = starter
		while cur_length < length and cur_word in self.words and len(self.words[cur_word]) > 0:
			r = random.random()
			next = list(self.words[cur_word].items())[bisect.bisect_left([x[0] for x in self.words[cur_word].values()], r)][0]
			message += ' ' + next
			cur_word = next
			cur_length = cur_length + 1
		
		return message
		
	def finish_adding_messages(self):
		# Probabilities must be sorted so that bisect works correctly when picking a weighted random for generating messages

		# Sort by count so that probability is always increasing
		self.message_lengths = OrderedDict(sorted(self.message_lengths.items(), key=lambda x: x[1][1]))
		self.starters = OrderedDict(sorted(self.starters.items(), key=lambda x: x[1][1]))

		# Calculate all probabilities of starters/lengths/all_nodes
		prev_probability = 0
		for k in self.message_lengths.keys():
			self.message_lengths[k][0] = prev_probability + self.message_lengths[k][1]/self.total_messages
			prev_probability = self.message_lengths[k][0]
		prev_probability = 0
		for k in self.starters.keys():
			self.starters[k][0] = prev_probability + self.starters[k][1]/self.total_messages
			prev_probability = self.starters[k][0]
						
		for k in self.words.keys():
			sum = 0
			for v in self.words[k].values():
				sum += v[1]
				
			self.words[k] = OrderedDict(sorted(self.words[k].items(), key=lambda x: x[1][1]))
			prev_probability = 0
			for k2 in self.words[k].keys():
				self.words[k][k2][0] = prev_probability + self.words[k][k2][1]/sum
				prev_probability = self.words[k][k2][0]

class UsernamesContainer:
	'''
	Usernames stored in lowercase only so that the get is not case-sensitive for user friendliness
	'''
	def __init__(self):
		self.usernames = {}
		
	def add(self, uid, username):
		self.usernames[username.lower()] = uid
		
	def get(self, username):
		return self.usernames.get(username.lower())

class BackInputException(Exception):
	pass
			
# List of strings to be ignored when processing messages
# Ignore is done if string starts with anything in the list
message_ignore_list = [
'/markov',
'/help'
]

markov_c = MarkovContainer()
usernames_container = UsernamesContainer()
			
# Config file
config = configparser.ConfigParser()
config.read('config.ini')
try:
	message_length_multiplier = float(config['DEFAULT']['MessageLengthMultiplier'])
except ValueError:
	print('MessageLengthMultiplier in config.ini must be a float')
	message_length_multiplier = 1.4

BACK_COMMAND = 'b'
DATA_FOLDER = 'Data'

client = discord.Client()
	
@client.event
async def on_ready():
	# Preparations in initial login
	
	print('Logged in as')
	print(client.user.name)
	print(client.user.id)
	line()
	
	print('Updating usernames...')
	await update_usernames()
	line()
			
	print('Bot is ready.')
	print('Type /help in discord for help page')
	print('Enter "' + BACK_COMMAND + '" at any prompt to go back')
	
	while True:
		await main_menu()
			
async def update_usernames():
	global usernames_container
	
	try:
		with open('usernames.pkl', 'rb') as f:
			usernames_container = pickle.load(f)
	except IOError:
		pass
	
	for member in client.get_all_members():
		usernames_container.add(member.id, member.name)
		
	with open('usernames.pkl', 'wb') as f:
		pickle.dump(usernames_container, f, pickle.HIGHEST_PROTOCOL)
		
async def save_obj(obj, name):
	print('Saving data...')
	with open(name, 'wb') as f:
		pickle.dump(obj, f, pickle.HIGHEST_PROTOCOL)
		print('Saved')
		
async def load_obj(name):
	print('Loading data...')
	with open(name, 'rb') as f:
		ret = pickle.load(f)
		print('Loaded')
		return ret
		
def is_ignored_message(message):
	for string in message_ignore_list:
		if message.clean_content.startswith(string):
			return True
	return False
	
async def asd():
	current_timestamp_marker_index
	
async def update_logs(channel, messages_param):
	try:
		metadata = markov_c.channels_metadata[channel.id]
	except KeyError:
		markov_c.channels_metadata[channel.id] = ChannelMetadata()
		metadata = markov_c.channels_metadata[channel.id]
	
	if isinstance(messages_param, int):		
		# messages_param is the max number of messages to be processed
		if messages_param == 0:
			max_messages = 99999999999999
			
			stop_on_start_of_last_update = True
			ignore_messages_in_date_ranges = False
			process_messages_in_range = False
		elif messages_param == -1:
			max_messages = 99999999999999
			
			stop_on_start_of_last_update = False
			ignore_messages_in_date_ranges = True
			process_messages_in_range = False
		else:
			max_messages = messages_param
			stop_on_start_of_last_update = False
			ignore_messages_in_date_ranges = True
			process_messages_in_range = False
	else:
		# Request is for a date range
		# message_param is a tuple containing 2 datetime objects
		max_messages = 99999999999999
		min_date = messages_param[0]
		max_date = messages_param[1]
		
		stop_on_start_of_last_update = False
		ignore_messages_in_date_ranges = False
		process_messages_in_range = True
		
	logs = client.logs_from(channel, max_messages)
	
	newest_message_timestamp_processed = datetime.datetime.now()
	processed_newest = False
	
	print('Recording messages from ' + channel.server.name + '/#' + channel.name + '...')
	
	messages_processed = 0
	last_message = None
	
	# Read messages until the end is reached or when the start of the last update is reached
	# Guaranteed not to read messages that have already been read
	if not process_messages_in_range and stop_on_start_of_last_update:
		async for message in logs:
			last_message = message
			
			if not processed_newest:
				processed_newest = True
				# Messages always processed from newest to oldest, so first message processed
				# is the newest
				newest_message_timestamp_processed = message.timestamp
				max_date = message.timestamp

			if is_ignored_message(message):
				continue
									
			# Remove all trailing whitespace
			content = message.clean_content.rstrip()
			# Remove all nonunicode
			content = ''.join([x for x in content if ord(x) < 128])
			if len(content) == 0:
				continue
			
			messages_processed = messages_processed + 1
					
			# Record until last message saved
			if str(message.timestamp) == str(metadata.last_update_timestamp):
				break
				
			try:
				markov_c.markovs[message.author.id].add_message(content)
			except KeyError:
				markov_c.markovs[message.author.id] = Markov()
				markov_c.markovs[message.author.id].add_message(content)
				
		min_date = last_message.timestamp
	# Read unread messages
	elif not process_messages_in_range and ignore_messages_in_date_ranges:
		timestamp_marker_max = len(metadata.processed_timestamp_ranges) - 1
		current_timestamp_marker_index = 0
		compare_date_ranges = timestamp_marker_max >= current_timestamp_marker_index
	
		async for message in logs:
			last_message = message
			
			if not processed_newest:
				processed_newest = True
				# Messages always processed from newest to oldest, so first message processed
				# is the newest
				newest_message_timestamp_processed = message.timestamp
				max_date = message.timestamp

			if is_ignored_message(message):
				continue
							
			if compare_date_ranges:				
				# Check if message is in current date range
				if message.timestamp >= metadata.processed_timestamp_ranges[current_timestamp_marker_index][0] and message.timestamp <= metadata.processed_timestamp_ranges[current_timestamp_marker_index][1]:
					continue
				else:
					# Iterate over date ranges until one where the start of the range is less than the message timestamp is reached
					while current_timestamp_marker_index < timestamp_marker_max and message.timestamp < metadata.processed_timestamp_ranges[current_timestamp_marker_index][1]:
						current_timestamp_marker_index = current_timestamp_marker_index + 1						
				
			# Remove all trailing whitespace
			content = message.clean_content.rstrip()
			# Remove all nonunicode
			content = ''.join([x for x in content if ord(x) < 128])
			if len(content) == 0:
				continue
						
			messages_processed = messages_processed + 1
					
			try:
				markov_c.markovs[message.author.id].add_message(content)
			except KeyError:
				markov_c.markovs[message.author.id] = Markov()
				markov_c.markovs[message.author.id].add_message(content)
				
		min_date = last_message.timestamp
	# Read unread messages in a certain range
	elif process_messages_in_range:
		timestamp_marker_max = len(metadata.processed_timestamp_ranges) - 1
		current_timestamp_marker_index = 0
		compare_date_ranges = timestamp_marker_max >= current_timestamp_marker_index
		
		async for message in logs:
			last_message = message
			
			if not processed_newest:
				processed_newest = True
				# Messages always processed from newest to oldest, so first message processed
				# is the newest
				newest_message_timestamp_processed = message.timestamp

			if is_ignored_message(message):
				continue
				
			# Convert message timestamp to be offset-aware to be able to compare to user-set aware ranges
			message.timestamp = message.timestamp.replace(tzinfo=tz.tzutc())
			
			if message.timestamp > max_date:
				continue
			# Stop when message's timestamp is past the min_date because messages are traversed from newest to oldest,
			# so any message timestamp after the min_date will always be < min_date
			elif message.timestamp < min_date:
				break
							
			if compare_date_ranges:				
				# Check if message is in current date range
				if message.timestamp >= metadata.processed_timestamp_ranges[current_timestamp_marker_index][0] and message.timestamp <= metadata.processed_timestamp_ranges[current_timestamp_marker_index][1]:
					continue
				else:
					# Iterate over date ranges until one where the start of the range is less than the message timestamp is reached
					while current_timestamp_marker_index < timestamp_marker_max and message.timestamp < metadata.processed_timestamp_ranges[current_timestamp_marker_index][1]:
						current_timestamp_marker_index = current_timestamp_marker_index + 1
				
			# Remove all trailing whitespace
			content = message.clean_content.rstrip()
			# Remove all nonunicode
			content = ''.join([x for x in content if ord(x) < 128])
			if len(content) == 0:
				continue
						
			messages_processed = messages_processed + 1
					
			try:
				markov_c.markovs[message.author.id].add_message(content)
			except KeyError:
				markov_c.markovs[message.author.id] = Markov()
				markov_c.markovs[message.author.id].add_message(content)
		
	# test
	print('Read in ' + str(messages_processed) + ' messages')
	
	# Update metadata
	
	# If number of processed messages was less than the requested, the last message processed must be the first message in the server
	if messages_processed < max_messages:
		metadata.first_message_timestamp = last_message.timestamp.replace(tzinfo=tz.tzutc())
	
	metadata.last_update_timestamp = newest_message_timestamp_processed.replace(tzinfo=tz.tzutc())
	
	metadata.add_timestamp_range(min_date, max_date)
	
@client.event
async def on_message(message):
	global markov_c
	global config

	# Ignore messages from self or from bots
	if client.user.id == message.author.id:
		return
	elif config['DEFAULT']['IgnoreBots'].lower() == 'true' and message.author.bot:
		return
	
	# Help page
	if message.content == "/help":
		msg = '"/markov random" - Random message from random user\n'
		msg += '"/markov @user" or "/markov username" - Random message from that user\n'
		
		await client.send_message(message.channel, msg)
	elif message.content == '/markov random':
		m = markov_c.markovs[random.choice(list(markov_c.markovs))].generate_message()
		await client.send_message(message.channel, m)
	elif message.content.startswith('/markov'):
		if len(message.mentions) > 0:
			try:
				m = markov_c.markovs[message.mentions[0].id].generate_message()
				await client.send_message(message.channel, m)
			except:
				await client.send_message(message.channel, 'No data on ' + message.mentions[0].name)
		else:
			# Check usernames list
			username = message.content.split('/markov ', 1)[1]
			uid = usernames_container.get(username)
			if uid != None:
				m = markov_c.markovs[uid].generate_message()
				await client.send_message(message.channel, m)
			else:
				await client.send_message(message.channel, 'No data on ' + username)

def line():
	print('------------------------------')
			
async def load_markovs(file_name):
	global markov_c
	markov_c = await load_obj(file_name)
	
async def input_with_back(prompt):
	print(prompt)
	ret = await client.loop.run_in_executor(None, sys.stdin.readline)
	# Remove trailing whitespace
	ret = ret.rstrip()
	if ret == BACK_COMMAND:
		raise BackInputException
	return ret
			
async def ask_save_file_name():
	if not os.path.exists(DATA_FOLDER):
		os.makedirs(DATA_FOLDER)
		
	line()
	try:
		name = await input_with_back('Save file name: ')
		if os.path.isfile(DATA_FOLDER + '\\' + name + '.pkl'):
			confirm = await input_with_back('Overwrite existing file? (y/n)')
			if confirm == 'y':
				return DATA_FOLDER + '\\' + name + '.pkl'
			else:
				return None
		return DATA_FOLDER + '\\' + name + '.pkl'
	except BackInputException:
		return None
		
async def ask_load_file_name():
	if not os.path.exists(DATA_FOLDER):
		os.makedirs(DATA_FOLDER)
		
	line()
	i = 1
	files = {}
	for file in os.listdir(DATA_FOLDER + '\\'):
		if file.endswith('.pkl'):
			files[str(i)] = file
			print(str(i) + '. ' + file)
			i = i + 1
			
	if len(files) == 0:
		print('No existing data to load')
		return None
		
	try:
		file_num = await prompt_int('Enter a file to load: ')
		return DATA_FOLDER + '\\' + files[str(file_num)]
	except BackInputException:
		return None

async def main_menu():
	line()
	try:
		mode = await input_with_back('1. Read messages from Discord\n2. Load existing data\n3. Save current data')
	except BackInputException:
		quit()

	if mode == '1':
		await read_mode_menu()
	elif mode == '2':
		# Load data
		file_name = await ask_load_file_name()
		if file_name is None:
			await main_menu()
			return
		await load_markovs(file_name)
	elif mode == '3':
		# Save data
		file_name = await ask_save_file_name()
		if file_name is None:
			await main_menu()
			return
		await save_obj(markov_c, file_name)
	else:
		print('Invalid input')
		await main_menu()

async def read_from_all_channels(messages_to_process):
	for server in client.servers:
		for channel in server.channels:
			if (channel.type == ChannelType.text or channel.type == ChannelType.group) and channel.permissions_for(server.me).read_messages:
				await update_logs(channel, messages_to_process)
	for k in markov_c.markovs.keys():
		markov_c.markovs[k].finish_adding_messages()
						
async def prompt_message_processing():
	prompt = ('Enter number of messages to be processed or enter a dash-separated range of times in which all messages are processed.\n'
	'\tTime range must be in format "MM/DD/YYYY HOUR:MIN", with HOUR:MIN in 24-hour clock\n'
	'\tAssumes local computer\'s time zone\n'
	'\tFor example, "09/12/1999 07:00 - 12/4/2018 13:00"\n'
	'Enter 0 to process all messages in the channel(s) up to the last processed message\n'
	'Enter -1 to process all messages in the channel(s), ignoring already read ones')
	try:
		str = await input_with_back(prompt)
		return int(str)
	except ValueError:
		try:
			strs = str.split('-')
			if len(strs) != 2:
				print('Invalid input')
				line()
				return await prompt_message_processing()
			d1 = datetime.datetime.strptime(strs[0].strip(), '%m/%d/%Y %H:%M')
			d2 = datetime.datetime.strptime(strs[1].strip(), '%m/%d/%Y %H:%M')
			
			if d1 > d2:
				# Swap
				d1, d2 = d2, d1
			
			# Convert to UTC because discordpy message timestamps are in UTC
			d1 = d1.replace(tzinfo=tz.tzlocal()).astimezone(tz.tzutc())
			d2 = d2.replace(tzinfo=tz.tzlocal()).astimezone(tz.tzutc())
			
			return (d1, d2)
		except ValueError:
			print('Invalid input')
			line()
			return await prompt_message_processing()
		except BackInputException:
			raise BackInputException
	except BackInputException:
		raise BackInputException
		
	return ret
		
async def read_mode_menu():
	line()
	try:
		mode = await input_with_back('1. Choose server(s)/channel(s) to read from\n2. Read from all channels the bot is in')
	except BackInputException:
		main_menu()
		return
		
	if mode == '1':
		await channel_choice_menu()
	elif mode == '2':
		line()
		try:
			messages_to_process = await prompt_message_processing()
		except BackInputException:
			await read_mode_menu()
			return
		line()
		await read_from_all_channels(messages_to_process)
	else:
		print('Invalid input')
		await read_mode_menu()
		
async def channel_choice_menu():
	line()
	s = 1
	choices = {}
	for server in client.servers:
		print(str(s) + '. ' + server.name)
		choices[str(s)] = server
		c = ord('a')
		m = 1
		for channel in server.channels:
			if (channel.type == ChannelType.text or channel.type == ChannelType.group) and channel.permissions_for(server.me).read_messages: 
				# a --> b --> ... --> z --> aa --> bb --> ...
				channel_identifier = chr(c) * m
				print('\t' + channel_identifier + '. ' + channel.name)
				choices[str(s) + channel_identifier] = channel
				c = c + 1
				if c - ord('a') >= 26:
					m = m + 1
					c = ord('a')
		s = s + 1
	
	try:
		choice = await input_with_back('Pick the server(s)/channel(s) to read from, space-separated\nExample: "1b 1e 2a 3" will pick channels 1b, 1e, 2a, and all channels in 3')
		line()
		read_from = set()
		for s in choice.split():
			# If no alphabet in string, then it is a server selection
			if re.search('[a-zA-Z]', s):
				read_from.add(choices[s])
			else:
				for channel in choices[s].channels:
					if (channel.type == ChannelType.text or channel.type == ChannelType.group) and channel.permissions_for(server.me).read_messages: 
						read_from.add(channel)
				
		messages_to_process = await prompt_message_processing()
		line()
		
		# Read in channels
		for channel in read_from:
			await update_logs(channel, messages_to_process)
		for k in markov_c.markovs.keys():
			markov_c.markovs[k].finish_adding_messages()
	except BackInputException:
		await read_mode_menu()
		return
	except KeyError:
		print('Invalid input')
		await channel_choice_menu()
	return None
	
async def prompt_int(prompt):
	'''
	Prompts user for an integer >= 0
	'''
	try:
		num = int(await input_with_back(prompt))
		return num
	except ValueError:
		print('Invalid input')
		line()
		return await prompt_int(prompt)
	except BackInputException:
		raise BackInputException

client.run(config['DEFAULT']['APIKey'])