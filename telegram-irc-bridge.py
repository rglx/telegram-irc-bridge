#!/usr/bin/python3

# telegram-irc-bridge
bridgeVersion = "0.1.0" # don't comment this out
# by DJ_Arghlex (@dj_arghlex)
# simulates a simple IRC server for connecting an IRC bot to a telegram bot account, with some limited functionality and controls therein.

from datetime import datetime
def printLog(channel = "Debug", message = "empty"):
	# specialized log-printer that makes our logs ~fancy~
	now = datetime.now()
	unixtimestamp = datetime.timestamp(now)
	timestamp = now.strftime("%m/%d/%Y %H:%M:%S")
	print( "[" + str(timestamp) + "] [" + channel + "] " + message )

printLog("System","Importing dependencies...")
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from telegram import Bot, ParseMode
from time import sleep
import logging, sys, socket, json, threading, os.path, signal, configparser

printLog("System","telegram-irc-bridge v"+ bridgeVersion +" starting up...")

printLog("System","Defining functions...")

def bridge_alltext(update, context):
	toIrcText = None
	toIrcDestination = None
	sourceUserName = str(update.effective_user.username)
	sourceUserId = str(update.effective_user.id)
	sourceChatId = str(update.effective_chat.id)
	adminsList = None

	if sourceUserName == None: # ignore messages from @-less usernames
		printLog("Compat", "Ignoring a message from an @-less user")
		return None

	if sourceChatId == sourceUserId: # message coming from telegram to telegram-DM with that user
		toIrcDestination = sourceUserName # translate to their IRC handle
	elif int(sourceChatId) < 0: # groups are negative numbers
		toIrcDestination = "#" + str(update.effective_chat.id) # translate to the channel's "name"
		adminsList = update.effective_chat.get_administrators()
	else:
		# message going to a non-group location that ISN'T a DM with that exact user
		printLog("Compat", "Ignoring an invalid message to ... somewhere?")
		return None

	toIrcText = str(update.effective_message.text)

	# chop at symbol and following stuff off command
	if toIrcText.startswith("/"):
		temporary = toIrcText.split(" ")
		temporary[0] = temporary[0].split("@")[0]
		toIrcText = " ".join(temporary)
		del temporary

	# parse and IRC-ify /me as CTCP ACTIONs
	ctcpChar = '\x01'
	if toIrcText.startswith("/me "):
		actionText = toIrcText.split(" ")[1:]
		if actionText == None:
			return None
		toIrcText = ctcpChar + "ACTION " + actionText + ctcpChar
	
	# make sure it's not just some random empty variable/string
	if toIrcText == None:
		printLog("Compat","Warning: empty IRC-bound message! Suppressing")
		return None

	cacheGroup = None
	if int(sourceChatId) < 0: # only cache a group if it's actually a group
		cacheGroup = sourceChatId

	foundNewUserStatus, foundNewUserAdminStatus = saveUserToCache(sourceUserId,sourceUserName,cacheGroup,None,None)
	if adminsList != None:
		for chatMember in adminsList:
			if chatMember.user.username != None:
				foundNewListedUserStatus, foundNewListedAdminStatus = saveUserToCache(str(chatMember.user.id),str(chatMember.user.username),cacheGroup,True,None)
				if foundNewListedUserStatus == True and toIrcDestination.startswith("#"):
					sendToIrc(":"+prefixUsernames()+ chatMember.user.username +"!" +str(chatMember.user.id)+ "@telegram.irc.bridge" + " JOIN " + toIrcDestination)
				if foundNewListedAdminStatus == True:
					sendToIrc(":telegram.irc.bridge MODE " + toIrcDestination + " +o-v " + prefixUsernames() + chatMember.user.username + " " + prefixUsernames() + chatMember.user.username)
				elif foundNewListedAdminStatus == False:
					sendToIrc(":telegram.irc.bridge MODE " + toIrcDestination + " -o+v " + prefixUsernames() + chatMember.user.username + " " + prefixUsernames() + chatMember.user.username)
			
	# this is a new user talking, let's make sure the bot updates its userlist with the new information.
	if foundNewUserStatus == True and toIrcDestination.startswith("#"):
		sendToIrc(":"+prefixUsernames()+ sourceUserName +"!" +sourceUserId+ "@telegram.irc.bridge" + " JOIN " + toIrcDestination)

	# update the bot on our new operator status
	if foundNewUserAdminStatus == True:
		sendToIrc(":telegram.irc.bridge MODE " + toIrcDestination + " +o-v " + prefixUsernames() + sourceUserName + " " + prefixUsernames() + sourceUserName)
	elif foundNewUserAdminStatus == False:
		sendToIrc(":telegram.irc.bridge MODE " + toIrcDestination + " -o+v " + prefixUsernames() + sourceUserName + " " + prefixUsernames() + sourceUserName)

	# okay, send the message, and log it.
	printLog("Telegram " + toIrcDestination, prefixUsernames() + sourceUserName + "!" + sourceUserId + " " + toIrcText)
	sendToIrc(":"+prefixUsernames()+ sourceUserName +"!" +sourceUserId+ "@telegram.irc.bridge" + " PRIVMSG " + toIrcDestination + " :" + toIrcText)

def bridge_controlcommand(update, context):
	sourceUserName = str(update.effective_user.username)
	sourceUserId = str(update.effective_user.id)
	sourceChatId = str(update.effective_chat.id)
	sourceText = str(update.effective_message.text)
	if sourceUserName == None or sourceUserName == "None": # ignore messages from @-less usernames
		printLog("BridgeControl", "Ignoring a message from an @-less user")
		return None

	if sourceUserId != sourceChatId:
		printLog("BridgeControl","User attempted to control the bridge outside a DM. Ignoring.")
		return None
	
	printLog("Telegram DM U:"+sourceChatId, "<" + sourceUserName + "> "+ sourceText)
	if sourceText.startswith("/start"):
		# /start command issued, allowing the bridge to convey DMs between bot and user
		printLog("BridgeControl",sourceUserName + " enabled DMs with bridge client.")
		saveUserToCache(sourceUserId,sourceUserName,None,None,True)
		sendToTelegramChat( sourceChatId, "`[Bridge Notice]` PMs will now be conducted between you and the bot\n Use /stop, or block the bot to disable this", True )	
	if sourceText.startswith("/stop"):
		# /start command issued, allowing the bridge to convey DMs between bot and user
		saveUserToCache(sourceUserId,sourceUserName,None,None,False)
		printLog("BridgeControl",sourceUserName + " disabled DMs with bridge client.")
	if sourceText.startswith("/bridgecfg"):
		printLog("BridgeControl",sourceUserName + " attempted usage of bridge configuration command.")
		# /start command issued, allowing the bridge to convey DMs between bot and user
		printLog ("Debug","got a control command, but this isnt implemented yet. sorry.")
		printLog ("Debug","test")

def saveUserToCache(userId, storedName, groupId = None, adminOnSpecificGroup = None, directMessagesAllowed = None): 
	# correctly store these three as strings
	userId = str(userId)
	storedName = str(storedName)
	if groupId == "None" or groupId == None:
		groupId = None
	else:
		groupId = str(groupId)
	if storedName == None or userId == None: # sanity checks
		raise Exception("inputted userId or user/firstname was none.")
	cacheChanged = False # not returned, but used to determine if the cache should be written
	newUserInChannel = False # true = this user is new to this particular chat, false = user existed already
	adminStatusChanged = None # true = is now admin, false = no longer admin, None = unchanged

	# step one, check if we have seen this user before now
	if userId not in telegramCache["users"].keys():
		printLog("Cache","Created empty user entry for "+userId)
		telegramCache["users"][userId] = [None, None] # create empty entry for userid/name/PmsEnabled info
		cacheChanged = True
		# we don't need to check if this is a new user in the channel or mark it as such because that's done below.

	# stored name doesn't match what we already have.
	if storedName != telegramCache["users"][userId][0]:
		printLog("Cache","updated username user entry for "+userId)
		telegramCache["users"][userId][0] = storedName
		cacheChanged = True

	if directMessagesAllowed != None:
		# dmsAllowed possibly changing!
		if directMessagesAllowed != telegramCache["users"][userId][1]:
			printLog("Cache","updated dmAllowed state for "+userId)
			# incoming information differs, change it and make sure the cache is saved.
			telegramCache["users"][userId][1] = directMessagesAllowed
			cacheChanged = True

	if groupId != None:
		#printLog("Cache","group cache updating for TGG "+groupId)
		if groupId not in telegramCache["groups"].keys():
			printLog("Cache","added empty group entry for TGG "+groupId)
			# new channel! create dict for members and admin statuses therein
			telegramCache["groups"][groupId] = {}
			cacheChanged = True
		if userId not in telegramCache["groups"][groupId].keys():
			printLog("Cache","new user " + userId + " detected in "+groupId)
			# new user found in our channel. populate information
			telegramCache["groups"][groupId][userId] = None # default is None because we havent gathered that information yet
			# and pass that information back outwards to our calling code
			newUserInChannel = True
			cacheChanged = True

		# user is definitely either an admin or not an admin, not 'unknown'
		if adminOnSpecificGroup != None:
			if telegramCache["groups"][groupId][userId] == None or telegramCache["groups"][groupId][userId] == "None":
				telegramCache["groups"][groupId][userId] = adminOnSpecificGroup
				printLog("Cache","adminstate changed to " + str(adminOnSpecificGroup) + " on " + userId + " in "+groupId)
				adminStatusChanged = adminOnSpecificGroup
				cacheChanged = True
	else:
		printLog("Cache","skipping group cache actions as function was not called with groupId")

	# only write the cache if it's actually been changed. otherwise we're doing excessive disk writes for no reason
	if cacheChanged == True:
		saveCache(telegramCache)
	return newUserInChannel, adminStatusChanged


def sendToIrc(string):
	global conn
	try:
		conn.sendall( (string + '\r\n').encode('utf-8') )
	except:
		shutdownBridge(None,"IRC ERROR","Connection was lost or interrupted! Shutting bridge down!")

def sendToTelegramChat(destination, text, useMarkdown = False):
	if telegramConfig["stripAllAtSignsFromBotText"] == True:
		text=text.replace("@","")
	if telegramConfig["forceConvertUsernamesToAtUsernames"] == True:
		temporary = text.split(" ")
		for word in temporary:
			for cachedUserId,cachedUserInfo in telegramCache["users"].items():
				if cachedUserInfo[0] == word:
					word = "@" + word
					printLog("Compat","Forcibly converted a username to a mention")
		text = " ".join(temporary)
	if text == None:
		return False
	try:
		if useMarkdown:
			telegramBotInterface.send_message( chat_id=int(destination), text=str(text), parse_mode=ParseMode.MARKDOWN_V2 )
		else:
			telegramBotInterface.send_message( chat_id=int(destination), text=str(text) )
	except Unauthorized:
		printLog("TelegramLib WARNING", "Bridge cannot DM a user who has not enabled that function.")
	except:
		printLog("TelegramLib ERROR", "An error occured when attempting to send a message to Telegram. Ignoring! [fix this, arghlex]")

def prefixUsernames(): # probably a better way to handle this but whatever
	if telegramConfig["prefixTelegramUsernamesWithAtSign"] == True:
		return "@"
	else:
		return ""

def loadCache(file = "./usercache.json"):
	# load the cached telegram userdata

	# example of revision 2 cache file
	exampleCache = {
		"users": {
			# "exampleUserIdInteger": [ exampleUsernameString, directMessagesEnabledBoolean ]
		},
		"groups": {
			# exampleGroupIdInteger: {
			#	 "exampleUserIdInteger": isAdminBoolean
			# },
		}
	}

	if not os.path.exists(file):
		with open(file, "w") as filehandle:
			json.dump(exampleCache, filehandle, sort_keys = True, indent = 4)
			printLog("Cache","WARNING! Created new usercache!")
			return exampleCache
	else:
		with open(file, "r") as filehandle:
			cacheJson = json.load(filehandle)
			printLog("Cache","Loaded usercache.")
			return cacheJson
	
def saveCache(contents, file = "./usercache.json"):
	# save the telegram cache to disk
	if contents == None or contents == {}: # don't wipe our cache file whatsoever
		printLog("Cache","WARNING! Something just tried to wipe the cache!")
		return None
	with open(file, "w") as filehandle:
		json.dump(contents, filehandle, sort_keys = True, indent = 4)
		printLog("Cache","Saved cache.")

def loadConfig(file = "./configuration.json"):
	# load configuration
	if not os.path.exists(file):

		# example configuration which is changeable from telegram via the configuration command.
		exampleConfig = {
			"prefixTelegramUsernamesWithAtSign": False, # bot will see @usernames as actual @username rather than just username
			"stripAllAtSignsFromBotText": True, # remove any exact '@'s that come from the bot from the text to prevent pings
			"forceConvertUsernamesToAtUsernames": False # overrides stripAllAtSignsFromBotText, but only enables for usernames in that particular channel.
		}

		with open(file, "w") as filehandle:
			json.dump(exampleConfig, filehandle, sort_keys = True, indent = 4)
			printLog("Config","WARNING! Created new config!")
			return exampleConfig
	else:
		with open(file, "r") as filehandle:
			loadedcontents = json.load(filehandle)
			printLog("Config","Loaded config.")
			return loadedcontents
	
def saveConfig(contents, file = "./configuration.json"):
	# save the telegram config to disk
	if contents == None or contents == {}: # don't wipe our file whatsoever
		printLog("Config","WARNING! Something just tried to wipe the config!")
		return None
	with open(file, "w") as filehandle:
		json.dump(contents, filehandle, sort_keys = True, indent = 4)
		printLog("Config","Saved config.")

def loadOrCreateSecretConfig(file = "configuration_secrets.ini"):
	if not os.path.exists(file):
		# no secrets config? we can't function without it.
		# so let's generate one, then exit.
		exampleSecretConfig = configparser.ConfigParser()
		exampleSecretConfig["IRC Configuration"] = {}
		exampleSecretConfig["IRC Configuration"]["Listen Address"] = "127.0.0.1"
		exampleSecretConfig["IRC Configuration"]["Listen Port"] = "6667"
		exampleSecretConfig["IRC Configuration"]["Listen via SSL"] = "False"
		exampleSecretConfig["IRC Configuration"]["Connection Password"] = "exampleSecureConnectionPassword"
		exampleSecretConfig["Telegram Configuration"] = {}
		exampleSecretConfig["Telegram Configuration"]["Secret Token"] = "exampleTelegramSecretToken"
		with open(file + ".example", "w") as exampleSecretConfigFile:
			exampleSecretConfig.write(exampleSecretConfigFile)
		printLog("FATAL ERROR","Secrets Configuration was not present! Generating an example. Please rename it to " + file + " after you have filled it out.")
		return None
	else:
		# there's one here! excellent.
		secretConfigObject = configparser.ConfigParser()
		secretConfigObject.read(file)

		# and copy the values...
		returningSecretConfig = {}
		returningSecretConfig["telegramToken"] = secretConfigObject["Telegram Configuration"]["Secret Token"]
		returningSecretConfig["ircHost"] = secretConfigObject["IRC Configuration"]["Listen Address"]
		returningSecretConfig["ircPort"] = secretConfigObject["IRC Configuration"].getint("Listen Port")
		returningSecretConfig["ircSecure"] = secretConfigObject["IRC Configuration"].getboolean("Listen via SSL")
		returningSecretConfig["ircPass"] = secretConfigObject["IRC Configuration"]["Connection Password"]

		# and return it.
		return returningSecretConfig

def shutdownBridge (irc_socket = None, messageCategory = "FATAL ERROR", message = "Exiting!", exitcode = 1):
	printLog(messageCategory,message)
	if irc_socket is not None:
		irc_socket.close()
	#updater.stop()
	#sys.exit(exitcode)
	os.kill(os.getpid(), signal.SIGKILL)



printLog("System","Setting initial variables...")

telegramCache = loadCache()
telegramConfig = loadConfig()
telegramSecretConfig = loadOrCreateSecretConfig()
if telegramSecretConfig == None:
	sys.exit(255)

printLog("System","Initializing Telegram interface...")
conn = None
updater = Updater(token=telegramSecretConfig["telegramToken"], use_context=True)
dispatcher = updater.dispatcher
telegramBotInterface = Bot(token = telegramSecretConfig["telegramToken"])
logging.basicConfig(format="[%(asctime)s] [*%(name)s %(levelname)s] %(message)s", level=logging.INFO)

bridge_action_handler = CommandHandler("me", bridge_alltext) # for properly sending IRC-style ACTIONs
dispatcher.add_handler(bridge_action_handler)

bridge_start_handler = CommandHandler("start", bridge_controlcommand) # allows the bot to DM specific users
dispatcher.add_handler(bridge_start_handler)

bridge_stop_handler = CommandHandler("stop", bridge_controlcommand) # forbids the bot to DM specific users. this is the default.
dispatcher.add_handler(bridge_stop_handler)

bridge_bridgecfg_handler = CommandHandler("bridgecfg", bridge_controlcommand) # allows specific users to adjust the bridge options.
dispatcher.add_handler(bridge_bridgecfg_handler)

bridge_text_handler = MessageHandler(Filters.text, bridge_alltext) # all other text that's sent to the bot
dispatcher.add_handler(bridge_text_handler)

# needs to be absolutely the last handler registered.
bridge_allcmds_handler = MessageHandler(Filters.command, bridge_alltext) # all other slash-commands sent to the bot
dispatcher.add_handler(bridge_allcmds_handler)

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as irc_socket:
	printLog("IRC","Attempting to bind socket...")
	socketBound=False
	while not socketBound:
		try:
			irc_socket.bind((telegramSecretConfig["ircHost"], telegramSecretConfig["ircPort"]))
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
		"welcome": None,
		"channels": []
	}
	# and now, we wait.
	printLog("IRC (Blocked)","Now waiting for client connection...")
	conn, addr = irc_socket.accept()
	with conn:
		printLog("IRC","Connected to client!")
		while True:
			try:
				data=conn.recv(4096)
			except: # catch all errors and just exit
				shutdownBridge(irc_socket,"IRC","A socket error occured. Shutting down.",254)
			if not data:
				shutdownBridge(irc_socket,"IRC","A socket error occured. Shutting down.",253)
			# now we parse our received data. Hopefully.
			data=data.split(b'\r\n') # because some clients don't follow RFC, and send USER and NICK on the same line that's done to avoid the NICK/USER connection initialization deadlocking that does happen on big IRCds
			for rawline in data:
			
				# for each line we've recieved we need to preparse it.
				try:
					line=rawline.decode("utf-8") # decode
				except UnicodeDecodeError:
					printLog("IRC","ERROR: Could not decode a line from IRC.")
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
					if ircuser["nick"] != None and ircuser["welcome"] == None: # this is a fresh connection. treat it like one!
						ircuser["welcome"] = True
						printLog("IRC","Client connected and logged in successfully!")
						# initial informational components
						sendToIrc(":telegram.irc.bridge 001 "+ircuser["nick"]+" :Welcome to the telegram IRC bridge "+ircuser["nick"]+"!"+ircuser["user"]+"@"+ircuser["host"]) # welcome message
						sendToIrc(":telegram.irc.bridge 002 "+ircuser["nick"]+" :Your host is telegram.irc.bridge, running telegramircbridge-v" + bridgeVersion ) # more information
						sendToIrc(":telegram.irc.bridge 003 "+ircuser["nick"]+" :This server was created in the beginning of time. It only just now accepts connections.") # server creation date
						sendToIrc(":telegram.irc.bridge 004 "+ircuser["nick"]+" Telegram telegramircbridge-v" + bridgeVersion + " Biwxs Yqaohvrnmtsi") # server short-name, software version, usermodes, channelmodes, parametered channel modes. (channel modes here should not be parsed by clients apparently)

						# capabilities, server information and other pertinent details
						sendToIrc(":telegram.irc.bridge 005 "+ircuser["nick"]+" AWAYLEN=200 :are supported by this server") # not supported
						sendToIrc(":telegram.irc.bridge 005 "+ircuser["nick"]+" CASEMAPPING=rfc1459 :are supported by this server") # also not supported
						sendToIrc(":telegram.irc.bridge 005 "+ircuser["nick"]+" CHANMODES=,,,imnrst :are supported by this server") # updated to match our actual capabilities as a server
						sendToIrc(":telegram.irc.bridge 005 "+ircuser["nick"]+" CHANNELLEN=32 :are supported by this server") # not enforced
						sendToIrc(":telegram.irc.bridge 005 "+ircuser["nick"]+" CHANTYPES=# :are supported by this server") # 
						sendToIrc(":telegram.irc.bridge 005 "+ircuser["nick"]+" CHARSET=utf-8 :are supported by this server") # not enforced but required by clients
						sendToIrc(":telegram.irc.bridge 005 "+ircuser["nick"]+" KICKLEN=40 :are supported by this server") # kicks are not supported
						sendToIrc(":telegram.irc.bridge 005 "+ircuser["nick"]+" MAXBANS=1 :are supported by this server") # modes in general are not supported
						sendToIrc(":telegram.irc.bridge 005 "+ircuser["nick"]+" MAXCHANNELS=1 :are supported by this server") 
						sendToIrc(":telegram.irc.bridge 005 "+ircuser["nick"]+" MAXPARA=1 :are supported by this server")
						sendToIrc(":telegram.irc.bridge 005 "+ircuser["nick"]+" MAXTARGETS=1 :are supported by this server")
						sendToIrc(":telegram.irc.bridge 005 "+ircuser["nick"]+" MODES=1 :are supported by this server")
						sendToIrc(":telegram.irc.bridge 005 "+ircuser["nick"]+" NAMESX :are supported by this server")
						sendToIrc(":telegram.irc.bridge 005 "+ircuser["nick"]+" NETWORK=Telegram :are supported by this server")
						sendToIrc(":telegram.irc.bridge 005 "+ircuser["nick"]+" NICKLEN=32 :are supported by this server") # not enforced
						sendToIrc(":telegram.irc.bridge 005 "+ircuser["nick"]+" PREFIX=(Yqaohv)!~&@%+ :are supported by this server") # planned expanded support
						sendToIrc(":telegram.irc.bridge 005 "+ircuser["nick"]+" UHNAMES :are supported by this server") # implemented

						# and, since this IS technically IRC, let's send a big-ass ASCII art image, as is tradition.
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :telegram.irc.bridge message of the day") # motd start
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- TTTTTTTTTTTTTTTTTTTTTTTT0kxdoooooooddkTTTTTTTTTTTTTTTTTTTTTTTTTT ")
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- TTTTTTTTTTTTTTTTTTTko:'..              .';lx0TTTTTTTTTTTTTTTTTTT ")
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- TTTTTTTTTTTTTTTkl,.                         .'cxTTTTTTTTTTTTTTTT ")
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- TTTTTTTTTTTTTc'                                 .:kTTTTTTTTTTTTT ")
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- TTTTTTTTTTx;                                       'dTTTTTTTTTTT ")
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- TTTTTTTTk;                                           'xTTTTTTTTT ")
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- TTTTTTTl.                                              :0TTTTTTT ")
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- TTTTT0;                                                 'kTTTTTT ")
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- TTTTT'                                                   .xTTTTT ")
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- TTT0'                                    .,coo;           .xTTTT ")
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- TTT:                                .,cdkTTTTTd.           '0TTT ")
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- TTd.                          .;cldTTTTTTTTTTT:             cTTT ")
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- TT;                     .';ldTTTTTTTTkxkTTTTTT'             .TTT ")
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- TT.                .':ox0TTTTTTTTTxccd0TTTTTTl               lTT ")
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- To            .':okTTTTTTTTTT0d;'';dTTTTTTTTT,               cTT ")
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- Tl           ,TTTTTTTTTTTTTo;..,lxTTTTTTTTTTd.               :TT ")
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- Tx.          .';ldk0TTTTl,. .;kTTTTTTTTTTTTT;                cTT ")
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- T0,                ..'.   .:TTTTTTTTTTTTTTTk.               .dTT ")
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- TTc                      .kTTTTTTTTTTTTTTTTc                ,TTT ")
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- TTT.                     ;TTTTTTTTTTTTTTTT0'               .dTTT ")
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- TTTo.                    :TTTx::okTTTTTTTTl                :TTTT ")
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- TTTTl                    :0d,     'lTTTTTT;               ;TTTTT ")
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- TTTTTl                   ..         .;d0Tl.              ;TTTTTT ")
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- TTTTTTd.                               ..               cTTTTTTT ")
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- TTTTTTTT;                                             'xTTTTTTTT ")
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- TTTTTTTTTx,                                         .oTTTTTTTTTT ")
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- TTTTTTTTTTTk;.                                    ,oTTTTTTTTTTTT ")
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- TTTTTTTTTTTTT0o,.                              'ckTTTTTTTTTTTTTT ")
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- TTTTTTTTTTTTTTTT0dc,.                     .':oTTTTTTTTTTTTTTTTTT ")
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- TTTTTTTTTTTTTTTTTTTTTkdo:,''........',;ldk0TTTTTTTTTTTTTTTTTTTTT ")
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- TTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTT ")
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- TTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTTT ")
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- Telegram IRC Bridge v" + bridgeVersion )
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- Rules: Do not spam. Maximum 20 messages per minute.") # as per telegram API documentation.
						sendToIrc(":telegram.irc.bridge 375 "+ircuser["nick"]+" :- Other rules up to interpretation by Telegram itself.")
						sendToIrc(":telegram.irc.bridge 376 "+ircuser["nick"]+" :End of message of the day.") # end of MOTD
						sendToIrc(":telegram.irc.bridge 302 "+ircuser["nick"]+" :"+ircuser["nick"]+"=+"+ircuser["user"]+"@"+ircuser["host"]) # send hostname reported by IRC server, that way we're sure we've got it right

						# there. just like home.
						#updater.start_polling(poll_interval=0.2, clean=True)
						updater.start_polling(poll_interval=0.2, clean=False)
						printLog("Telegram","Telegram interface polling in separate thread. Link established!")

				elif line[0] == "NICK":  # nickname being changed
					ircuser["nick"] = line[1]
					printLog("IRC","Client changed nick to "+ircuser["nick"])

				elif line[0] == "JOIN":  # client joining channel
					attemptedChannels = line[1].split(",")
					for channel in attemptedChannels:
						convertedGroupId = str(channel.lstrip("#"))
						sendToIrc(":" + ircuser["nick"]+"!"+ircuser["user"]+"@"+"telegram.irc.bridge JOIN :"+ channel )
						ircuser["channels"].append(channel)
						printLog("IRC","Client joining pseudochannel #"+ str(convertedGroupId))
	
						if convertedGroupId in telegramCache["groups"].keys():
							allListedUsers = " " + ircuser["nick"]
							for cachedUserId,cachedUserIsAdmin in telegramCache["groups"][convertedGroupId].items():
								if cachedUserIsAdmin:
									allListedUsers = allListedUsers + " @" + prefixUsernames() + telegramCache["users"][cachedUserId][0]
								else:
									allListedUsers = allListedUsers + " " + prefixUsernames() + telegramCache["users"][cachedUserId][0]
							sendToIrc(":telegram.irc.bridge 353 " + ircuser["nick"] + " @ " + channel + allListedUsers)
						else:
							sendToIrc(":telegram.irc.bridge 353 " + ircuser["nick"] + " @ " + channel + " " + ircuser["nick"])
							printLog("IRC","WARNING! group cache for TGG "+str(convertedGroupId)+" nonexistent or empty, sending an empty channel NAMES reply")
						sendToIrc(":telegram.irc.bridge 366 " + ircuser["nick"] + " " + channel + " End of /NAMES list.")

				elif line[0] == "NAMES":  # client MANUALLY requesting NAMES. NAMES are also sent automatically on successful JOIN to a channel, but not what we're doing here.
					convertedGroupId = str(line[1].lstrip("#"))
					if convertedGroupId in telegramCache["groups"].keys():
						allListedUsers = " " + ircuser["nick"]
						for cachedUserId,cachedUserIsAdmin in telegramCache["groups"][convertedGroupId].items():
							if cachedUserIsAdmin:
								allListedUsers = allListedUsers + " @" + prefixUsernames() + telegramCache["users"][cachedUserId][0]
							else:
								allListedUsers = allListedUsers + " " + prefixUsernames() + telegramCache["users"][cachedUserId][0]
						sendToIrc(":telegram.irc.bridge 353 " + ircuser["nick"] + " @ " + line[1] + allListedUsers)
					else:
						sendToIrc(":telegram.irc.bridge 353 " + ircuser["nick"] + " @ " + line[1] + " " + ircuser["nick"])
						printLog("IRC","WARNING! group cache for TGG "+str(convertedGroupId)+" nonexistent or empty, sending an empty channel NAMES reply")
					sendToIrc(":telegram.irc.bridge 366 " + ircuser["nick"] + " " + line[1] + " End of /NAMES list.")


				elif line[0] == "WHO":  # client requesting WHO
					convertedGroupId = str(line[1].lstrip("#"))
					sendToIrc(":telegram.irc.bridge 352 " + ircuser["nick"] + " " + line[1] + " " + ircuser["user"] + " "+ircuser["host"]+" telegram.irc.bridge " + ircuser["nick"] + " H :0 "+ ircuser["real"])
					if convertedGroupId in telegramCache["groups"].keys():
						for cachedUserId,cachedUserIsAdmin in telegramCache["groups"][convertedGroupId].items():
							if telegramCache["users"][cachedUserId][1] == True:
								sendToIrc(":telegram.irc.bridge 352 " + ircuser["nick"] + " " + line[1] + " " + str(cachedUserId) + " telegram.irc.bridge telegram.irc.bridge " + prefixUsernames() + telegramCache["users"][cachedUserId][0] + " H@ :0 TelegramUser")
							else:
								sendToIrc(":telegram.irc.bridge 352 " + ircuser["nick"] + " " + line[1] + " " + str(cachedUserId) + " telegram.irc.bridge telegram.irc.bridge " + prefixUsernames() + telegramCache["users"][cachedUserId][0] + " H+ :0 TelegramUser")
					else: 
						printLog("IRC","WARNING! group cache for TGG "+str(convertedGroupId)+" nonexistent or empty")
					sendToIrc(":telegram.irc.bridge 315 " + ircuser["nick"] + " " + line[1] + " End of /WHO list.")
					printLog("IRC","Client requested memberlist (WHO) of pseudochannel #"+ str(convertedGroupId))

				elif line[0] =="PRIVMSG": # client messaging something
					destinationChatId = None
					if line[1].startswith("#"): # this is a channel/group/thing
						destinationChatId = str(line[1].lstrip("#"))
						if int(destinationChatId) > 0: # something odd happened and the client's trying to DM a user via a pseudochannel????
							continue
					else: # okay, so it's not a channel. it's a direct message to another user.
						for cachedUserId,cachedUserInfo in telegramCache["users"].items():
							if cachedUserInfo[0] == str(line[1]): # found it. this is where it goes.
								destinationChatId = cachedUserId
								if cachedUserInfo[1] == False or cachedUserInfo[1] == None:
									printLog("Compat","Client attempted to DM a user who has not accepted DMs from the bot.")
									continue

					if destinationChatId == None:
						continue
						# just ignore it.
					if line[2].startswith("\x01ACTION") or line[2].startswith(":\x01ACTION"):
						# ok so its an action, just yoink the "ACTION" bit and send it with stars around it
						newtext = "*"  + " ".join(line[3:]).strip("\x01") + "*" # remove the action and CTCP chars
						sendToTelegramChat( destinationChatId, newtext )
						printLog("IRC Msg " + str(destinationChatId), " * " + ircuser["nick"] + " " + " ".join(line[3:]) )

					else:
						newtext = " ".join(line[2:])[1:] # remove leading colon
						sendToTelegramChat( destinationChatId, newtext )
						printLog("IRC Msg " + str(destinationChatId), " <" + ircuser["nick"] + "> " + newtext )

				elif line[0] == "PART": # client leaving a channel
					ircuser["channels"] = list(filter((line[1]).__ne__, ircuser["channels"])) # taken from stackoverflow, it's arcane
					sendToIrc(":" + ircuser["nick"]+"!"+ircuser["user"]+"@telegram.irc.bridge PART :"+ " ".join(line[2:]) )

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

				#elif line[0] == "NOTICE":  # redirect ALL outgoing NOTICEs to the telegram chat, but make it fixed-width
				#	newtext = " ".join(line[2:]).lstrip(":") #.encode('utf-8')
				#	sendToTelegramChat( chat_id=int(line[1].lstrip("#")), text="NOTICE: `" + newtext + "`", parse_mode=ParseMode.MARKDOWN_V2)

				elif line[0] == "KICK":  # KICKs from client. Ignore them.
					printLog("IRC","Client tried to kick " + line[2] + " from " + line[1])
					sendToIrc(":telegram.irc.bridge 482 "+ircuser["nick"]+" "+line[1]+" :You must be a channel half-operator to kick users.")

				elif line[0] == "REMOVE":  # inspircd-style /REMOVE command. ignore it too. Normally failed attempts to remove are handled with a notice saying so, but i guess this is fine
					printLog("IRC","Client tried to remove " + line[2] + " from " + line[1])
					sendToIrc(":telegram.irc.bridge 482 "+ircuser["nick"]+" "+line[1]+" :You must be a channel half-operator to kick users.")

				elif line[0] == "QUIT":
					shutdownBridge(irc_socket,"IRC","Client disconnecting.",0)


				else: # other garbage info coming in. print here.
					printLog("IRC","GARBAGE: |"+ " ".join(line)+"|")
shutdownBridge(None,"CRITICAL ERROR","Socket was closed! Exiting bridge!",0)