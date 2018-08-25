import discord
from discord import ChannelType
import os
import bisect
import random
import pickle
import configparser
import tkinter as tk
from tkinter import filedialog
import functools
import asyncio

class Markov:
	def __init__(self):
		# Probability distribution of message lengths
		# [(probability, len, total), ...]
		self.message_lengths = []
		self.total_messages = 0
	
		# Probability distribution of starting words
		# [(probability, word, total), ...]
		self.starters = []
		
		# Graph of words
		# {'a': [(0.1, 'b', 10), (1.0, 'c', 90)]]}
		self.words = {}
		
	def add_message(self, message):
		words_list = message.split()
		words_count = len(words_list)
		
		if words_count == 0:
			return
		
		# Update count of generated messages' lengths
		found = False
		self.total_messages = self.total_messages + 1
		for i in range(len(self.message_lengths)):
			if self.message_lengths[i][1] == words_count:
				self.message_lengths[i] = (self.message_lengths[i][0], self.message_lengths[i][1], self.message_lengths[i][2] + 1)
				found = True
				break
		if found == False:
			self.message_lengths.append((0, words_count, 1))
			
		# Update count of starters
		found = False
		for i in range(len(self.starters)):
			if self.starters[i][1] == words_list[0]:
				self.starters[i] = (self.starters[i][0], self.starters[i][1], self.starters[i][2] + 1)
				found = True
				break
		if found == False:
			self.starters.append((0, words_list[0], 1))
			# If first word not in starters, it must not be in words either
			self.words[words_list[0]] = []
			
		# Update counts of all words in message
		prev = words_list[0]
		for word in words_list[1:]:
			try:
				found = False
				for i in range(len(self.words[prev])):
					if word == self.words[prev][i][1]:
						# Increase count
						self.words[prev][i] = (self.words[prev][i][0], self.words[prev][i][1], self.words[prev][i][2] + 1)
						found = True
						break
				if found == False:
					self.words[prev].append((0, word, 1))
			except KeyError:
				self.words[prev] = []
			prev = word
		
	def generate_message(self):
		r = random.random()
		length = self.message_lengths[bisect.bisect_left(self.message_lengths, (r, '', 0))][1]
		r = random.random()
		starter = self.starters[bisect.bisect_left(self.starters, (r, '', 0))][1]
		
		message = starter
		
		cur_length = 0
		cur_word = starter
		while cur_length < length and cur_word in self.words and len(self.words[cur_word]) > 0:
			r = random.random()
			next = self.words[cur_word][bisect.bisect_left(self.words[cur_word], (r, '', 0))][1]
			message += ' ' + next
			cur_word = next
			cur_length = cur_length + 1
		
		return message
		
	def finish_adding_messages(self):
		# Probabilities must be sorted so that bisect works correctly when picking a weighted random for generating messages
	
		# Calculate all probabilities of starters/lengths/all_nodes
		for i in range(len(self.message_lengths)):
			if i != 0:
				self.message_lengths[i] = (self.message_lengths[i][2]/self.total_messages + self.message_lengths[i - 1][0], self.message_lengths[i][1], self.message_lengths[i][2])
			else:
				self.message_lengths[i] = (self.message_lengths[i][2]/self.total_messages, self.message_lengths[i][1], self.message_lengths[i][2])
		for i in range(len(self.starters)):
			if i != 0:
				self.starters[i] = (self.starters[i][2]/self.total_messages + self.starters[i - 1][0], self.starters[i][1], self.starters[i][2])
			else:
				self.starters[i] = (self.starters[i][2]/self.total_messages, self.starters[i][1], self.starters[i][2])
			
		self.message_lengths.sort()
		self.starters.sort()
			
		for k in self.words.keys():
			sum = 0
			for i in range(len(self.words[k])):
				sum += self.words[k][i][2]
			for i in range(len(self.words[k])):
				if i != 0:
					self.words[k][i] = (self.words[k][i][2]/sum + self.words[k][i - 1][0], self.words[k][i][1], self.words[k][i][2])
				else:
					self.words[k][i] = (self.words[k][i][2]/sum, self.words[k][i][1], self.words[k][i][2])
			self.words[k].sort()

class BackInputException(Exception):
    pass
			
# List of strings to be ignored when processing messages
# Ignore is done if string starts with anything in the list
global message_ignore_list
message_ignore_list = [
'/markov',
'/help'
]
			
# Config file
config = configparser.ConfigParser()
config.read('config.ini')

# user : Markov
markovs = {}

BACK_COMMAND = 'b'

global client
client = discord.Client()

global client_ready_queue
client_ready_queue = []
	
@client.event
async def on_ready():
	global client_ready_queue
	
	print('Logged in as')
	print(client.user.name)
	print(client.user.id)
	line()
	
	print('Executing commands queue...')
	for partial in client_ready_queue:
		if asyncio.iscoroutinefunction(partial.func):
			await partial()
		else:
			partial()
	line()
	print('Bot is ready.')
	print('Type /help in discord for help page')
	
async def get_channel_metadata(channel_id):
	last_message_timestamp = '-1'
	try:
		with open('Channels\\' + channel_id + '\\channel' + channel_id + 'meta.txt', 'r') as file:
			last_message_timestamp = file.readline()
	except Exception:
		# Meta file does not exist
		print('Meta file for channel ' + channel_id + ' does not exist')
	return [last_message_timestamp]

async def write_to_channel_metadata(channel_id, newest_message_timestamp_processed):
	# Make directory for channel if it does not exist yet
	if not os.path.exists('Channels'):
		os.makedirs('Channels')
	if not os.path.exists('Channels\\' + channel_id):
		os.makedirs('Channels\\' + channel_id)
		
	with open('Channels\\' + channel_id + '\\channel' + channel_id + 'meta.txt', 'w') as file:
		# Write timestamp of last processed message to meta file
		file.write(str(newest_message_timestamp_processed))
		
def save_obj(obj, name):
	print('Saving data...')
	with open(name, 'wb') as f:
		pickle.dump(obj, f, pickle.HIGHEST_PROTOCOL)
		print('Saved')
		
def load_obj(name):
	print('Loading data...')
	with open(name, 'rb') as f:
		ret = pickle.load(f)
		print('Loaded')
		return ret
		
def is_ignored_message(message):
	global message_ignore_list

	for string in message_ignore_list:
		if message.clean_content.startswith(string):
			return True
	return False
		
async def update_logs(channel, max_messages_to_process):
	global markovs
	
	if max_messages_to_process == 0:
		logs = client.logs_from(channel, 99999999999999)
	else:
		logs = client.logs_from(channel, max_messages_to_process)
	
	newest_message_timestamp_processed = -1
	
	# Get last message saved
	metadata = await get_channel_metadata(channel.id)
	last_message_timestamp = metadata[0]
	
	print('Recording messages from ' + channel.name + '...')
	
	async for message in logs:
		if is_ignored_message(message):
			continue
			
		#TODO: add oldest_message_timestamp_processed to allow for skipping messages that already have been processed --> re-request logs but with max_messages += (number of skipped messages) if max_messages != 0
	
		# Remove all trailing whitespace
		content = message.clean_content.rstrip()
		# Remove all nonunicode
		content = ''.join([x for x in content if ord(x) < 128])
				
		# Record until last message saved
		# Note: logs might not be sorted by timestamp
		#print(content)
		if str(message.timestamp) == str(last_message_timestamp):
			#print('Encountered start of last update. Stopping log recording.')
			break
		elif newest_message_timestamp_processed == -1:
			# Messages always processed from newest to oldest, so first message processed
			# is the newest
			newest_message_timestamp_processed = message.timestamp
			
		try:
			markovs[message.author.id].add_message(content)
		except KeyError:
			markovs[message.author.id] = Markov()
			markovs[message.author.id].add_message(content)
	
	for k in markovs.keys():
		markovs[k].finish_adding_messages()
	print('Finished recording messages')
	
	await write_to_channel_metadata(channel.id, newest_message_timestamp_processed)
	
@client.event
async def on_message(message):
	global markovs
	global config

	# Ignore messages from self or from bots
	if client.user.id == message.author.id:
		return
	elif config['DEFAULT']['IgnoreBots'].lower() == 'true' and message.author.bot:
		return
	
	# Help page
	if message.content == "/help":
		msg = '/markov random - Random message from random user\n'
		msg += '/markov @user - Random message from mentioned user\n'
		
		await client.send_message(message.channel, msg)
	elif message.content == '/markov random':
		m = markovs[random.choice(list(markovs))].generate_message()
		await client.send_message(message.channel, m)
	elif message.content == '/markov load':
		markovs = load_obj('MarkovChainData')
	elif message.content.startswith('/markov'):
		try:
			m = markovs[message.mentions[0].id].generate_message()
			await client.send_message(message.channel, m)
		except:
			await client.send_message(message.channel, 'No data on that user.')

def line():
	print('------------------------------')
			
def load_markovs(file_name):
	global markovs
	markovs = load_obj(file_name)
	
def input_with_back(prompt):
	ret = input(prompt)
	if ret == BACK_COMMAND:
		raise BackInputException
	return ret
		
def main_menu():
	global client
	global markovs
	global client_ready_queue
	
	client_ready_queue.clear()

	line()
	try:
		mode = input_with_back('1. Read messages from Discord\n2. Load existing data and run Markov bot\n')
	except BackInputException:
		quit()

	if mode == '1':
		channel_choice_menu()
		
		# Save data
		file = filedialog.asksaveasfile(mode='w', defaultextension='.pkl')
		if file is None:
			main_menu()
			return
		client_ready_queue.append(functools.partial(save_obj, markovs, file.name))
	elif mode == '2':
		# Load data
		file = filedialog.askopenfile()
		if file is None:
			main_menu()
			return
		client_ready_queue.append(functools.partial(load_markovs, file.name))
	else:
		print('Invalid input')
		line()
		main_menu()

async def read_from_all_channels(num_messages):
	for server in client.servers:
		for channel in server.channels:
			if (channel.type == ChannelType.text or channel.type == ChannelType.group) and channel.permissions_for(server.me).read_messages:
				await update_logs(channel, num_messages)
		
def channel_choice_menu():
	global client
	global client_ready_queue

	line()
	try:
		mode = input_with_back('1. Choose server/channel to read from\n2. Read from all channels the bot is in\n')
	except BackInputException:
		main_menu()
		return
		
	if mode == '1':
		print('asd')
	elif mode == '2':
		line()
		#TODO: be able to choose date range
		try:
			num_messages = prompt_int('Enter number of messages to be read\nEnter 0 to read all messages in the channel(s)')
		except BackInputException:
			channel_choice_menu()
			return
		line()
		client_ready_queue.append(functools.partial(read_from_all_channels, num_messages))
	else:
		print('Invalid input')
		line()
		channel_choice_menu()

def prompt_int(prompt):
	'''
	Prompts user for an integer >= 0
	'''
	try:
		num = int(input_with_back(prompt + '\n'))
		return num
	except ValueError:
		print('Invalid input')
		line()
		return prompt_int(prompt)
	except BackInputException:
		raise BackInputException
			
root = tk.Tk()
root.withdraw()

line()
print('Enter "' + BACK_COMMAND + '" at any prompt to go back')

main_menu()
line()
print('Logging in...')

client.run(config['DEFAULT']['APIKey'])