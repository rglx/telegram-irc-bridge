# telegram-irc-bridge
simulates an irc server to facilitate a single IRC user on telegram. good for old IRC bots.

## dependencies
- python-telegram-bot ( https://github.com/python-telegram-bot/python-telegram-bot )
- up-to-date python 3 install
- knowledge of how telegram groups work  
- an IRC bot, or client, ready and waiting to connect and function.
  

## setup
- talk to the @BotFather on telegram ( https://telegram.me/botfather ) and use `/mybots` to: 
	- add a bot
	- give it a profile picture, a user picture, a example command, and some descriptive information about it
	- **allow** it to be joined to groups
	- **disable group privacy** to receive *all* messages from your group (if you so choose. Keep in mind that not enabling this means your bot will only see stuff with `/`s in front of it)
- install your bot's dependencies and get your IRC bot up and ready to be connected to IRC
	- direct it to connect via plaintext to your host and port you've set, but don't start it yet.
	- the character encoding NEEDS to be UTF-8. Most, if not all, modern IRC clients/bots use this by default, except ... mIRC.
	- configure this script with your group's ID and your bot's telegram access token.
- start the script. when the script says it's awaiting connection, start and connect your bot to it.  
- if all goes well, your bot should connect to the bridge, then react to you (and others) talking to it via telegram.
  
## notes
- sending more than 20 messages per minute to the telegram API will get sanctions applied to your account so don't let your bot flood it.
- this is still very much a work in progress! expect bugs and breakage and problems. file issues into the issues section.

## [issues directed here](</issues>)
