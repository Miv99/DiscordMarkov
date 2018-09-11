# DiscordMarkov
Discord bot that reads in messages in server(s)/channel(s) and creates Markov chain data that can be saved, updated, and used by the bot to generate text.  
DiscordMarkov has several options for reading in messages: all channels the bot can access, certain channels as chosen by the user, all channels in certain servers as chosen by the user  
How much is read in is determined by the user. They can set a range of dates and times or a number of messages.

## Getting Started

# Prerequisites
1. Python 3.5 or higher  
2. discord.py - https://github.com/Rapptz/discord.py

# Setting up the bot
1. Create a Discord bot account  
2. Get its API key and put it in config.ini after "APIKey = "  
3. Add bot to your server and make sure it has permissions to read relevant text channels and can send messages  
4. Type /help to see the list of public commands  

Example config.ini  
```
[DEFAULT]
APIKey = Makfp3m9_24nola94hG9ANFjsIa0
IgnoreBots = true
MessageLengthMultiplier = 1.4
```

## Public commands
Public commands are commands that can be used by anyone in the server  
```
"/help" - Shows all public commands
"/markov random" - Generates a message from a random user and sends it to the channel the command was sent from
"/markov @user" or "/markov [username]" - Generates a message from the specified user and sends it to the channel the command was sent from
```

## Terminal help
Enter the number corresponding to a choice to execute that command  
Enter "b" at any prompt to go back  

### Main menu
"1. Read messages from Discord" - Opens the message reading menu  
"2. Load existing data" - Prompts user to load a .pkl containing saved data from read messages  
"3. Save current data" - Prompts user to save everything that has been read or loaded in this session into a .pkl  
### Message reading menu
"1. Choose server(s)/channel(s) to read from" - Opens the channel choice menu for reading in messages from specific servers or channels  
"2. Read from all channels the bot is in" - Read in messages from all channels the bot can access and has permissions to read from  
### Channel choice menu
The menu here differs based on what servers are visible by the bot.  
Here's an example:  
```
1. Random Server
  a. rules
  b. general-chat
  c. announcements
2. Another Random Server
  a. stuff
  b. random
  c. images
```
Each choice by the user is space-separated. Pick a specific channel by entering its server number and letter of the alphabet. Pick all channels in a server by entering only its server number.  
Here's an example of reading in #rules and #general-chat from Random Server and all channels in Another Random Server:  
```1a 1b 2```
The order does not matter.  
### Reading in messages
There are two main options for reading in messages: reading in a specific number, or reading in all messages in a certain date range  Messages that are markov commands are ignored and if IgnoreBots is true in config.ini, messages from bots are also ignored.  
To read in a certain number of messages, simply enter that number. This reads in x messages from when the command was given. Ignored messages count towards the number of read messages.  
To read in messages in a range of dates, enter two dates separated by a dash. The dates must be in format "MM/DD/YYYY HOUR:MIN" with HOUR:MIN being in 24-hour clock. The following example reads in all messages from September 12, 1999 7AM to December 4, 2018 1PM.  
```09/12/1999 07:00 - 12/4/2018 13:00```
Entering 0 reads in all messages up to the last read message  
Entering -1 reads in all messages up until the very beginning of the channel(s) while ignoring messages that have already been read  
