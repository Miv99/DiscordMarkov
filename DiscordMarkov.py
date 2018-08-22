import discord
from discord import ChannelType
import os
import csv
import datetime
import numpy
import bisect
import random
import pickle
import configparser

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

# Config file
config = configparser.ConfigParser()
config.read('config.ini')

# user : Markov
markovs = {}

client = discord.Client()
	
@client.event
async def on_ready():
	print('Logged in as')
	print(client.user.name)
	print(client.user.id)
	print('-------------------')
	print('Type /help in discord for help page')
	
async def get_channel_metadata(channel_id):
	last_message_timestamp = '-1'
	try:
		with open('Channels/' + channel_id + '/channel' + channel_id + 'meta.txt', 'r') as file:
			last_message_timestamp = file.readline()
	except Exception:
		# Meta file does not exist
		print('Meta file for channel ' + channel_id + ' does not exist')
	return [last_message_timestamp]

async def write_to_channel_metadata(channel_id, newest_message_timestamp_processed):
	with open('Channels/' + channel_id + '/channel' + channel_id + 'meta.txt', 'w') as file:
		# Write timestamp of last processed message to meta file
		file.write(str(newest_message_timestamp_processed))
		
def save_obj(obj, name):
    with open(name + '.pkl', 'wb') as f:
        pickle.dump(obj, f, pickle.HIGHEST_PROTOCOL)

def load_obj(name):
    with open(name + '.pkl', 'rb') as f:
        return pickle.load(f)
		
async def update_logs(channel, max_messages_to_process):
	global markovs
	
	#TODO: reset all probabiltiies in all markovs to 0
	
	logs = client.logs_from(channel, max_messages_to_process)
	
	# Make directory for channel if it does not exist yet
	if not os.path.exists(str(channel.id)):
		os.makedirs(str(channel.id))
	
	newest_message_timestamp_processed = -1
	
	# Get last message saved
	metadata = await get_channel_metadata(channel.id)
	last_message_timestamp = metadata[0]
	
	print('Recording...')
	await client.send_message(channel, 'Recording logs... This may take a while depending on total number of messages.')
	
	async for message in logs:
		# Remove all trailing whitespace
		content = message.clean_content.rstrip()
		# Remove all nonunicode
		content = ''.join([x for x in content if ord(x) < 128])
		
		#TODO: skip log file, just insert into markov
		
		# Record until last message saved
		# Note: logs might not be sorted by timestamp
		# Csv format: [seconds since 1/1/1970],[timestamp],[name],[message]
		print(str(message.timestamp) + ' compared to ' + str(last_message_timestamp))
		if str(message.timestamp) == str(last_message_timestamp):
			print('Encountered start of last update. Stopping log recording.')
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
		print('Finishing up for', k)
		markovs[k].finish_adding_messages()
	print('Finished recording logs')
	
	await write_to_channel_metadata(channel.id, newest_message_timestamp_processed)
	save_obj(markovs, 'MarkovChainData')
	await client.send_message(channel, 'Finished updating logs.')
	
@client.event
async def on_message(message):
	global config

	# Ignore messages from self or from bots
	if client.user.id == message.author.id:
		return
	elif config['DEFAULT']['IgnoreBots'].lower() == 'true' and message.author.bot:
		return

	global markovs
	
	# Help page
	if message.content == "/help":
		msg = '/markov update - Updates logs\n'
		msg += '/markov random - Random message from random user\n'
		msg += '/markov @user - Random message from mentioned user\n'
		
		await client.send_message(message.channel, msg)
	# Update logs
	elif message.content == '/markov update':
		await client.send_message(message.channel, "Updating logs...")
		await update_logs(message.channel, 100000000)
		#await record_users(message.channel)
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
		
# Start client
client.run(config['DEFAULT']['APIKey'])
