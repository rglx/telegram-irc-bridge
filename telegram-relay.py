#!/usr/bin/python3

# telegram-irc-bridge v0.0.4-beta
# by DJ_Arghlex (@dj_arghlex)
# simulates a simple IRC server for connecting an IRC bot to a telegram bot account, and joining that bot to a telegram chat group.

'''
DEPENDENCIES
	- python-telegram-bot ( https://github.com/python-telegram-bot/python-telegram-bot )
	- up-to-date python 3.7 install
	- knowledge of how telegram groups work
	- an IRC bot, or client, ready and waiting to connect and function.

SETUP
	- talk to the @BotFather on telegram ( https://telegram.me/botfather )
	  - add a bot user for your account
	  - allow it to be joined to groups, and to receive *all* messages from your group
	    (if you so choose. Keep in mind that not enabling this means your bot will have to parse all commands as though they have a / preceding them rather than anything else.)
	- install dependencies and get your IRC bot up and running
	  - direct it to connect via plaintext to localhost:6667, but don't start it yet.
	  - the character encoding NEEDS to be UTF-8. Most, if not all, modern IRC clients/bots use this by default, except ... mIRC.
	- configure this script with your group ID, user ID, and your bot's telegram access token.
	- start the script. when the script says it's awaiting connection, start and connect your bot to it.
	- if all goes well, your bot should react to you talking to it via telegram.
	
NOTES & CAVEATS
	- /me (yes, an actual command) is parsed by the bridge and sent as a CTCP ACTION when going to IRC
	- conversely, ACTIONs by the bot are converted and encapsulated with asterisks
	- all formatting between the two sides of the bridge is removed (TG->IRC) or just broken (IRC->TG)
	- users that talk the first time (as determined by the bridge's persistence) will
	    seem (to the bot) to join, then talk immediately with their line. after this,
	    the user will appear as normal. some advanced bots (eggdrop) may see this as
	    a flood attack. adjust your chansets accordingly
	- due to the nature of IRC being that of impermanence, the telegram relay will NOT
	    automatically push any cached messages from telegram that were accrued while the bridge was offline.
	    this is INTENTIONAL. you can disable it in the code if you REALLY want but it will make your bot FREAK.
	- flooding from the bot to telegram will absolutely get your API calls blocked and your token locked down. 
	    at time of writing, the limit as noted in telegram's API documents is more than 20 messages in a minute 
	    will result in throttling. further offences in this period will result in likely some form of blockade.
	- the CAPAB (004 & 005 numerics) messages sent by the bridge to the client are not indicative of the bridge's abilities. These merely
	    were copied from a real, complete server to get bots to see it as a valid connection. These may be pared down to match
	    the actual capabilities of the bridge in the future.
	- no banlists/invitelists/exceptionlists
	- (currently) no +o/+h/+v or +m mode support
	- it's literally the galaxy's crudest single-connection single-thread IRC server stapled on to an asynchronous
	    telegram API. there's gonna be some wack-ass shit and some even wackier janky shit going on.

'''

# CONFIGURATION
telegramToken = "replace" # your bot's telegram presence's token. get from the @BotFather on telegram.
whitelistedTelegramGroupId = -219689000 # only allow messages to be sent to/from the bot via this group ID
prefixUsernamesWithAtSign = False # prefix telegram usernames with @ symbols? allows bot to ping people (bypasses telegram block feature, very annoying)
# END CONFIGURATION


from datetime import datetime
def printLog(channel = "Debug", message = "empty"):
	# specialized log-printer
	now = datetime.now()
	unixtimestamp = datetime.timestamp(now)
	timestamp = now.strftime("%m/%d/%Y %H:%M:%S")
	print( "[" + str(timestamp) + "] [" + channel + "] " + message )

printLog("System","Importing dependencies...")
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from telegram import Bot, ParseMode
from time import sleep
import logging, sys, socket, json, threading, os.path, signal


printLog("System","Starting up...")

printLog("System","Setting initial variables...")
conn = None
telegramCache = None # we'll import this later.
updater = Updater(token=telegramToken, use_context=True)
dispatcher = updater.dispatcher
telegramBotInterface = Bot(token = telegramToken)
HOST, PORT = "0.0.0.0", 65445
logging.basicConfig(format="[%(asctime)s] [*%(name)s %(levelname)s] %(message)s", level=logging.INFO)

printLog("System","Defining functions...")
def bridge_action(update, context): # /me commands being translated to CTCP ACTIONs and going to IRC
	if update.effective_chat.id != whitelistedTelegramGroupId:
		return None
	if "#"+str(update.effective_chat.id) not in telegramCache: # make the specific usercache for this channel exist
		telegramCache["#"+str(update.effective_chat.id)] = {}
	if str(update.effective_user.username) not in telegramCache["#"+str(update.effective_chat.id)]:
		telegramCache["#"+str(update.effective_chat.id)][str(update.effective_user.username)] = str(update.effective_user.id)
		saveCache(telegramCache)
		sendToIrc(":"+prefixUsernames() + update.effective_user.username +"!" +str(update.effective_user.id)+ "@telegram.irc.relay" + " JOIN #" + str(update.effective_chat.id))
		printLog("Telegram " + str(update.effective_chat.id), "Added " + prefixUsernames() + update.effective_user.username + "!" + str(update.effective_user.id) + " to channel usercache")
		sleep(0.1) # just in case
	newtext = " ".join((update.effective_message.text).split(" ")[1:])
	sendToIrc(":" + prefixUsernames() + update.effective_user.username +"!" +str(update.effective_user.id)+ "@telegram.irc.relay" + " PRIVMSG #" + str(update.effective_chat.id) + " :" + (b'\x01').decode("utf-8") + "ACTION " + newtext + (b'\x01').decode("utf-8"))
	printLog("Telegram " + str(update.effective_chat.id) , " * " + prefixUsernames() + update.effective_user.username + "!" + str(update.effective_user.id) + " " + newtext)

def bridge_text(update, context): # regular text going to IRC
	if update.effective_chat.id != whitelistedTelegramGroupId:
		return None
	if "#"+str(update.effective_chat.id) not in telegramCache: # make the specific usercache for this channel exist
		telegramCache["#"+str(update.effective_chat.id)] = {}
	if str(update.effective_user.username) not in telegramCache["#"+str(update.effective_chat.id)]:
		telegramCache["#"+str(update.effective_chat.id)][str(update.effective_user.username)] = str(update.effective_user.id)
		saveCache(telegramCache)
		sendToIrc(":"+prefixUsernames() + update.effective_user.username +"!" +str(update.effective_user.id)+ "@telegram.irc.relay" + " JOIN #" + str(update.effective_chat.id))
		printLog("Telegram " + str(update.effective_chat.id), "Added " + prefixUsernames() + update.effective_user.username + "!" + str(update.effective_user.id) + " to channel usercache")
		sleep(0.1) # just in case
	sendToIrc(":"+prefixUsernames()+ update.effective_user.username +"!" +str(update.effective_user.id)+ "@telegram.irc.relay" + " PRIVMSG #" + str(update.effective_chat.id) + " :" + update.effective_message.text)
	printLog("Telegram " + str(update.effective_chat.id) , "<"+prefixUsernames() + update.effective_user.username + "!" + str(update.effective_user.id) + "> " + update.effective_message.text)

def bridge_allcmds(update, context): # regular text going to IRC
	if update.effective_chat.id != whitelistedTelegramGroupId:
		return None
	if "#"+str(update.effective_chat.id) not in telegramCache: # make the specific usercache for this channel exist
		telegramCache["#"+str(update.effective_chat.id)] = {}
	if str(update.effective_user.username) not in telegramCache["#"+str(update.effective_chat.id)]:
		telegramCache["#"+str(update.effective_chat.id)][str(update.effective_user.username)] = str(update.effective_user.id)
		saveCache(telegramCache)
		sendToIrc(":"+prefixUsernames() + update.effective_user.username +"!" +str(update.effective_user.id)+ "@telegram.irc.relay" + " JOIN #" + str(update.effective_chat.id))
		printLog("Telegram " + str(update.effective_chat.id), "Added " + prefixUsernames() + update.effective_user.username + "!" + str(update.effective_user.id) + " to channel usercache")
		sleep(0.1) # just in case
	# because telegram likes to put @mentions after bot commands we have to strip them off so that the bot doesnt ignore them just because they have @s on them

	newtext = update.effective_message.text.split(" ")
	newtext[0] = newtext[0].split("@")[0] # split it and only take the first half
	newtext = " ".join(newtext)
	sendToIrc(":" + prefixUsernames() + update.effective_user.username +"!" +str(update.effective_user.id)+ "@telegram.irc.relay" + " PRIVMSG #" + str(update.effective_chat.id) + " :" + newtext)
	printLog("Telegram " + str(update.effective_chat.id) , "<"+prefixUsernames() + update.effective_user.username + "!" + str(update.effective_user.id) + "> " + newtext)
	printLog("Telegram " + str(update.effective_chat.id) , update.effective_user.username + "!" + str(update.effective_user.id) + " invoking command! " + newtext)

def sendToIrc(string):
	global conn
	try:
		conn.sendall( (string + '\r\n').encode('utf-8') )
	except:
		printLog("IRC ERROR","Connection was lost or interrupted! Shutting bridge down!")
		os.kill(os.getpid(), signal.SIGKILL)

def prefixUsernames(): # probably a better way to handle this but whatever
	if prefixUsernamesWithAtSign == True:
		return "@"
	else:
		return ""

printLog("System","Binding Telegram commands...")

bridge_action_handler = CommandHandler("me", bridge_action) # for properly sending IRC-style ACTIONs
dispatcher.add_handler(bridge_action_handler)

bridge_text_handler = MessageHandler(Filters.text, bridge_text) # all other text that's sent to the bot
dispatcher.add_handler(bridge_text_handler)

# needs to be absolutely the last handler registered.
bridge_allcmds_handler = MessageHandler(Filters.command, bridge_allcmds) # all other slash-commands sent to the bot
dispatcher.add_handler(bridge_allcmds_handler)

def loadCache(file = "./telegramCache.json"):
	# load the cached telegram userdata
	if not os.path.exists(file):
		with open(file, "w") as filehandle:
			json.dump({}, filehandle, sort_keys = True, indent = 4)
			printLog("Cache","WARNING! Created new usercache!")
			return {}
	else:
		with open(file, "r") as filehandle:
			cacheJson = json.load(filehandle)
			printLog("Cache","Loaded usercache.")
			return cacheJson
	
def saveCache(cachecontents, file = "./telegramCache.json"):
	# save the telegram cache to disk
	if cachecontents == None or cachecontents == {}: # don't wipe our cache file whatsoever
		printLog("Cache","WARNING! Something just tried to wipe the cache!")
		return None
	with open(file, "w") as filehandle:
		json.dump(cachecontents, filehandle, sort_keys = True, indent = 4)
		printLog("Cache","Saved usercache.")
		print("CACHE CONTENTS")
		print(repr(cachecontents))
		print("CACHE CONTENTS END")

if __name__ == "__main__":
	with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as irc_socket:
		printLog("IRC","Attempting to bind socket...")
		socketBound=False
		while not socketBound:
			try:
				irc_socket.bind((HOST, PORT))
				irc_socket.listen()
				socketBound=True
				printLog("IRC","Socket bound and listening.")
			except:
				printLog("IRC","Failed to bind socket... retrying!")
				sleep(0.5)
				pass
		ircuser = {
			"user": None,
			"nick": None,
			"real": None,
			"host": None,
			"welcome": None
		}
		telegramCache = loadCache()
		# and now, we wait.
		printLog("IRC (Blocked)","Now waiting for client connection...")
		conn, addr = irc_socket.accept()
		with conn:
			printLog("IRC","Connected to client!")
			while True:
				try:
					data=conn.recv(512)
				except:
					printLog("IRC ERROR","Socket error! Exiting!")
					irc_socket.close()
					os.kill(os.getpid(), signal.SIGKILL)
				if not data:
					printLog("IRC ERROR","Socket recieve failed! Shutting down!")
					irc_socket.close()
					os.kill(os.getpid(), signal.SIGKILL)
				# now we parse our received data. Hopefully.
				data=data.split(b'\r\n') # because some clients don't follow RFC, and send USER and NICK on the same line that's done to avoid the NICK/USER connection initialization deadlocking that does happen on big IRCds
				for rawline in data:
				
					# for each line we've recieved we need to preparse it.
					try:
						line=rawline.decode("utf-8") # decode
					except UnicodeDecodeError:
						printLog("IRC","ERROR! Could not decode a message from IRC.")
						continue
					if line == "" or line == None: # make sure it's not just garbage data
						continue # empty line. skip.
					#line = line.strip('\x01','\x03','\x02','\x1D','\x1F','\x1E','\x0F','\x16','\x04')
					line = line.split(" ") # ok NOW split it
					
					if line[0] == "PING": # ping responses, the bread and butter of any ircd
						sendToIrc(":telegram.irc.bridge PONG telegram.irc.bridge :" + " ".join(line[1:]))

					elif line[0] == "USER":  # initial username login procedure
						ircuser["user"] = line[1] # we really dont care as this is a single-connection IRCd
						ircuser["real"] = " ".join(line[4:]).lstrip(":")
						ircuser["host"] = line[3]
						printLog("IRC","Client attempting login...")
						if ircuser["nick"] is not None and ircuser["welcome"] is None: # this is a fresh connection. treat it like one!
							ircuser["welcome"] = True
							printLog("IRC","Client connected and logged in successfully!")
							# send our initial IRC protocol stuff
							sendToIrc(":telegram.irc.bridge 001 "+ircuser["nick"]+" :Welcome to the telegram IRC bridge "+ircuser["nick"]+"!"+ircuser["user"]+"@"+ircuser["host"]) # welcome message
							sendToIrc(":telegram.irc.bridge 002 "+ircuser["nick"]+" :Your host is telegram.irc.bridge, running telegramircbridge-v0.0.1") # welcome message
							sendToIrc(":telegram.irc.bridge 003 "+ircuser["nick"]+" :This server was created now") # welcome message

							# FAKE IT TIL YA MAKE IT YO
							# lines shamelessly stolen from stormbit's CAPABs sent on join and modified a little
							sendToIrc(":telegram.irc.bridge 004 "+ircuser["nick"]+" Telegram telegramircbridge-v0.0.3 BGHIRSWcdghikorswx ABCFGHIKLMNOPQRSTXYZabcefghijklmnopqrstvwz FHILXYZabefghjkloqvw") # welcome message
							sendToIrc(":telegram.irc.bridge 005 "+ircuser["nick"]+" AWAYLEN=200 CALLERID=g CASEMAPPING=rfc1459 CHANMODES=IXZbegw,k,FHLfjl,ABCGKMNOPQRSTcimnprstz CHANNELLEN=32 CHANTYPES=# CHARSET=ascii ELIST=MU ESILENCE EXCEPTS=e EXTBAN=,ABCNOQRSTUcjmrsz FNC INVEX=I :are supported by this server") # welcome message
							sendToIrc(":telegram.irc.bridge 005 "+ircuser["nick"]+" KICKLEN=40 MAXBANS=1 MAXCHANNELS=1 MAXPARA=1 MAXTARGETS=1 MODES=1 NAMESX NETWORK=Telegram NICKLEN=32 PREFIX=(v)+ UHNAMES :are supported by this server") # welcome message

							sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :telegram.irc.bridge message of the day") # motd start
							sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- Bridge to telegram. Do not spam.") # motd contents
							sendToIrc(":telegram.irc.bridge 376 "+ircuser["nick"]+" :End of message of the day.") # end of MOTD
							sendToIrc(":telegram.irc.bridge 302 "+ircuser["nick"]+" :"+ircuser["nick"]+"=+"+ircuser["user"]+"@"+ircuser["host"]) # send hostname reported by IRC server, that way we're sure we've got it right
							updater.start_polling(poll_interval=0.2, clean=True)
							printLog("Telegram","Telegram interface polling in separate thread. Link established!")

					elif line[0] == "NICK":  # nickname being changed
						ircuser["nick"] = line[1]
						printLog("IRC","Client changed nick to "+ircuser["nick"])

					elif line[0] == "JOIN":  # client trying to join channel
						sendToIrc(":" + ircuser["nick"]+"!"+ircuser["user"]+"@"+"telegram.irc.bridge JOIN :"+ line[1] )
						sendToIrc(":telegram.irc.bridge 353 " + ircuser["nick"] + " = " + line[1] + " " +ircuser["nick"]+"!"+ircuser["user"]+"@"+ircuser["host"])
						if line[1] in telegramCache:
							for bridgeUser,bridgeUserId in telegramCache[line[1]].items():
								sendToIrc(":telegram.irc.bridge 353 " + ircuser["nick"] + " = " + line[1] + " " + prefixUsernames() + bridgeUser + "!" + bridgeUserId + "@telegram.irc.bridge")
						else: 
							printLog("IRC","WARNING! group cache for TGG "+line[1]+" nonexistent or empty")
						sendToIrc(":telegram.irc.bridge 366 " + ircuser["nick"] + " " + line[1] + " End of /NAMES list.")
						printLog("IRC","Client joining pseudochannel "+ line[1])

					elif line[0] == "NAMES":  # client MANUALLY requesting NAMES. NAMES are sent automatically on successful JOIN to a channel.
						sendToIrc(":telegram.irc.bridge 353 " + ircuser["nick"] + " = " + line[1] + " " +ircuser["nick"]+"!"+ircuser["user"]+"@"+ircuser["host"])
						if line[1] in telegramCache:
							for bridgeUser,bridgeUserId in telegramCache[line[1]].items():
								sendToIrc(":telegram.irc.bridge 353 " + ircuser["nick"] + " = " + line[1] + " "+prefixUsernames() +bridgeUser+"!"+bridgeUserId+"@telegram.irc.bridge")
						else: 
							printLog("IRC","WARNING! group cache for TGG "+line[1]+" nonexistent or empty")
						sendToIrc(":telegram.irc.bridge 366 " + ircuser["nick"] + " " + line[1] + " End of /NAMES list.")
						printLog("IRC","Client finished joining pseudochannel (NAMES) "+ line[1])

					elif line[0] == "WHO":  # client requesting WHO
						sendToIrc(":telegram.irc.bridge 352 " + ircuser["nick"] + " " + line[1] + " " + ircuser["user"] + " "+ircuser["host"]+" telegram.irc.bridge " + ircuser["nick"] + " H :0 "+ ircuser["real"])
						if line[1] in telegramCache:
							for bridgeUser,bridgeUserId in telegramCache[line[1]].items():
								sendToIrc(":telegram.irc.bridge 352 " + ircuser["nick"] + " " + line[1] + " " + bridgeUserId + " telegram.irc.bridge telegram.irc.bridge " + prefixUsernames() + bridgeUser + " H :0 TelegramUser")
						else: 
							printLog("IRC","WARNING! group cache for TGG "+line[1]+" nonexistent or empty")
						sendToIrc(":telegram.irc.bridge 315 " + ircuser["nick"] + " " + line[1] + " End of /WHO list.")
						printLog("IRC","Client requested memberlist (WHO) of pseudochannel "+ line[1])

					elif line[0] == "MODE":  # client trying to change MODEs
						if line[1].startswith("#"): # ... on a channel
							if len(line) == 3:
								# just checking or setting a channel mode of some kind, no targets specified
								
								# various channel list checks
								if line[2] == "+b":
									sendToIrc(":telegram.irc.bridge 368 "+ircuser["nick"]+" "+line[1]+" :End of channel ban list")
									printLog("IRC","Sent empty ban list.")
								if line[2] == "+e":
									sendToIrc(":telegram.irc.bridge 349 "+ircuser["nick"]+" "+line[1]+" :End of channel exception list")
									printLog("IRC","Sent empty banexcept list.")
								if line[2] == "+I":
									sendToIrc(":telegram.irc.bridge 347 "+ircuser["nick"]+" "+line[1]+" :End of channel invite exception list")
									printLog("IRC","Sent empty invex list.")
								if line[2] == "+g":
									sendToIrc(":telegram.irc.bridge 940 "+ircuser["nick"]+" "+line[1]+" :End of channel spamfilter list")
									printLog("IRC","Sent empty spamfilter list.")
									
								else:  # looks like it might be an actual mode change. better tell them to fuck off.
									printLog("IRC","Denied mode change.")
									sendToIrc(":telegram.irc.bridge 482 "+ircuser["nick"]+" "+line[1]+" :You must have channel halfop access or above to set channel mode ")
									
							else:  # ok it LOOKS like they're trying to set some kind of mode on the channel or someone. better just tell them to fuck themselves.
								printLog("IRC","Denied mode change (length check fail)")
								sendToIrc(":telegram.irc.bridge 482 "+ircuser["nick"]+" "+line[1]+" :You must have channel halfop access or above to set channel mode ") # but be kinda vague. this might be a problem with really convoluted bots that check 482 responses.
							sendToIrc(":telegram.irc.bridge 324 "+ircuser["nick"]+" " + line[1] + " +nts") # standard "no outside messages, no topic changes without ops, secret" mode line used by lots of ircds
						elif line[1] == ircuser["nick"]: # setting modes on itself. just echo it back.
							sendToIrc(":" + ircuser["nick"] + "!" + ircuser["user"] + "@" + ircuser["host"] + " " + " ".join(line[0:]))
							printLog("IRC","Client set modes "+ " ".join(line[2:])+ " on themself")
						else:
							printLog("IRC","Client tried to set modes on another user. Ignoring. ("+ " ".join(line) +")")

					elif line[0] =="PRIVMSG": # client messaging something
						if line[1] == ("#" + str(whitelistedTelegramGroupId)): # only allow things to happen in THIS group ID
							if line[2].startswith("\x01ACTION") or line[2].startswith(":\x01ACTION"):
								# ok so its an action, just yoink the "ACTION" bit and send it with stars around it
								newtext = ( "*"  + " ".join(line[3:]).strip("\x01") + "*" ).replace("@","") #.encode('utf-8')
								telegramBotInterface.send_message( chat_id=whitelistedTelegramGroupId, text=newtext )
								printLog("IRC Msg " + line[1]," * " + ircuser["nick"] + " " + " ".join(line[3:]) )
							else:
								newtext = (" ".join(line[2:])[1:] ).replace("@","") # .encode('utf-8') # second set of array-selecting is removal of the leading colon
								telegramBotInterface.send_message( chat_id=whitelistedTelegramGroupId, text=newtext )
								printLog("IRC Msg " + line[1],"<" + ircuser["nick"] + "> " + newtext )
						else:
							printLog("IRC","Client sent a message to non-whitelisted channel " + line[1] + ": " + " ".join(line[2:]))
							
					elif line[0] == "NOTICE":  # redirect ALL outgoing NOTICEs to the telegram chat, but make it fixed-width
						newtext = " ".join(line[2:]).lstrip(":") #.encode('utf-8')
						telegramBotInterface.send_message( chat_id=whitelistedTelegramGroupId, text=newtext + " -- NOTICE to " + line[1])

					elif line[0] == "KICK":  # KICKs from client. Ignore them.
						printLog("IRC","Client tried to kick " + line[2] + " from " + line[1])
						sendToIrc(":telegram.irc.bridge 482 "+ircuser["nick"]+" "+line[1]+" :You must be a channel half-operator to kick users.")

					elif line[0] == "REMOVE":  # inspircd-style /REMOVE command. ignore it too. Normally failed attempts to remove are handled with a notice saying so, but i guess this is fine
						printLog("IRC","Client tried to remove " + line[2] + " from " + line[1])
						sendToIrc(":telegram.irc.bridge 482 "+ircuser["nick"]+" "+line[1]+" :You must be a channel half-operator to kick users.")

					else: # other garbage info coming in. print here.
						printLog("IRC","GARBAGE: |"+ " ".join(line)+"|")
						
	updater.idle() # needs to be here in case IRC loop somehow exits, and telegram doesnt exit as well.
else:
	printLog("ERROR","This program should NOT be imported to another!")
	sys.exit(255)
