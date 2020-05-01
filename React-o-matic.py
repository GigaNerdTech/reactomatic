import discord
import re
import mysql.connector
from mysql.connector import Error
import time
from discord.utils import get
import discord.utils
import random
from datetime import datetime
from nltk.corpus import webtext
import nltk
from nltk.corpus import reuters
from nltk.corpus import twitter_samples
from nltk.tag import pos_tag
from nltk.stem.wordnet import WordNetLemmatizer
from nltk.corpus import stopwords
from nltk import FreqDist
from nltk import classify
from nltk import NaiveBayesClassifier
import string
from nltk.tokenize import word_tokenize

client = discord.Client()
emoji_reaction = {}
# word_features = list(nltk.FreqDist(str(w).lower() for w in reuters.tokenized()[:4000]))
message_dict = {}
user_dict = {}
message_count_dict = {}
message_rand_freq_dict = {} 
bot_mood = { }
random_colors = { }
classifier = None
featuresets = None
user_color_roles = { }

async def log_message(log_entry):
    current_time_obj = datetime.now()
    current_time_string = current_time_obj.strftime("%b %d, %Y-%H:%M:%S.%f")
    print(current_time_string + " - " + log_entry, flush = True)
    
async def commit_sql(sql_query, params = None):
    try:
        connection = mysql.connector.connect(host='localhost', database='Reactomatic', user='REDACTED', password='REDACTED')    
        cursor = connection.cursor()
        result = cursor.execute(sql_query, params)
        connection.commit()
        return True
    except mysql.connector.Error as error:
        await log_message("Database error! " + str(error))
        return False
    finally:
        if(connection.is_connected()):
            cursor.close()
            connection.close()
            
def get_tweets_for_model(cleaned_tokens_list):
    for tweet_tokens in cleaned_tokens_list:
        yield dict([token, True] for token in tweet_tokens) 
        
def document_features(document):
    global word_features
    document_words = set(document)
    features = {}
    for word in word_features:
        features['contains({})'.format(word)] = (word in document_words)
    return features
    
def lemmatize_sentence(tokens):
    lemmatizer = WordNetLemmatizer()
    lemmatized_sentence = []
    for word, tag in pos_tag(tokens):
        if tag.startswith('NN'):
            pos = 'n'
        elif tag.startswith('VB'):
            pos = 'v'
        else:
            pos = 'a'
        lemmatized_sentence.append(lemmatizer.lemmatize(word, pos))
    return lemmatized_sentence    

def remove_noise(tweet_tokens, stop_words = ()):

    cleaned_tokens = []

    for token, tag in pos_tag(tweet_tokens):
        token = re.sub('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+#]|[!*\(\),]|'\
                       '(?:%[0-9a-fA-F][0-9a-fA-F]))+','', token)
        token = re.sub("(@[A-Za-z0-9_]+)","", token)

        if tag.startswith("NN"):
            pos = 'n'
        elif tag.startswith('VB'):
            pos = 'v'
        else:
            pos = 'a'

        lemmatizer = WordNetLemmatizer()
        token = lemmatizer.lemmatize(token, pos)

        if len(token) > 0 and token not in string.punctuation and token.lower() not in stop_words:
            cleaned_tokens.append(token.lower())
    return cleaned_tokens

def get_all_words(cleaned_tokens_list):
    for tokens in cleaned_tokens_list:
        for token in tokens:
            yield token
            
async def select_sql(sql_query, params = None):
    try:
        connection = mysql.connector.connect(host='localhost', database='Reactomatic', user='REDACTED', password='REDACTED')
        cursor = connection.cursor()
        result = cursor.execute(sql_query, params)
        records = cursor.fetchall()
        return records
    except mysql.connector.Error as error:
        await log_message("Database error! " + str(error))
        return None
    finally:
        if(connection.is_connected()):
            cursor.close()
            connection.close()

async def execute_sql(sql_query):
    try:
        connection = mysql.connector.connect(host='localhost', database='Reactomatic', user='REDACTED', password='REDACTED')
        cursor = connection.cursor()
        result = cursor.execute(sql_query)
        return True
    except mysql.connector.Error as error:
        await log_message("Database error! " + str(error))
        return False
    finally:
        if(connection.is_connected()):
            cursor.close()
            connection.close()
            
            
async def send_message(message, response):
    await log_message("Message sent back to server " + message.guild.name + " channel " + message.channel.name + " in response to user " + message.author.name + "\n\n" + response)
    message_chunks = [response[i:i+1900] for i in range(0, len(response), 1900)]
    for chunk in message_chunks:
        await message.channel.send(chunk)
        time.sleep(1)

@client.event
async def on_ready():
    global message_dict
    global user_dict
    global message_count_dict
    global message_rand_freq_dict
    global emoji_reaction
    global bot_mood
    global random_colors
    global user_color_roles
    
    print("Logged in!")
    for guild in client.guilds:
        message_count_dict[guild.id] = {}
        emoji_reaction[guild.id] = True
        message_dict[guild.id] = { }
        user_dict[guild.id] = { }
        message_rand_freq_dict[guild.id] = { }
        bot_mood[guild.id] = {} 
        user_color_roles[guild.id] = {} 
        random_colors[guild.id] = {} 
        for member in guild.members:
            bot_mood[guild.id][member.id] = ""
            random_colors[guild.id][member.id] = False

            if member.nick:
                message_count_dict[guild.id][member.nick] = 0
            else:
                message_count_dict[guild.id][member.name] = 0
            
    get_reactions = """SELECT EmojiString,ReactionPattern,MessageOrUser,ReactionType,Frequency,ServerId FROM Reactions;"""
    get_randomcolors = """SELECT ServerId,UserId,RandomColors,IFNULL(ColorRoles,'everyone') FROM RandomColors;"""
    records = await select_sql(get_reactions)
    for row in records:
        if "Message" in row[2]:
            try: message_dict[int(row[5])]
            except: message_dict[int(row[5])] = {} 
            message_dict[int(row[5])][row[1]] = { }
            message_dict[int(row[5])][row[1]]["Emoji"] = row[0]
            message_dict[int(row[5])][row[1]]["ReactionType"] = row[3]
            message_dict[int(row[5])][row[1]]["Frequency"] = int(row[4])
        elif "User" in row[2]:
            try: user_dict[int(row[5])]
            except: user_dict[int(row[5])] =  {} 
            user_dict[int(row[5])][row[1]] = { }
            user_dict[int(row[5])][row[1]]["Emoji"] = row[0]
            user_dict[int(row[5])][row[1]]["ReactionType"] = row[3]
            user_dict[int(row[5])][row[1]]["Frequency"] = int(row[4])
            try: message_rand_freq_dict[int(row[5])]
            except: message_rand_freq_dict[int(row[5])] = { } 
            if (user_dict[int(row[5])][row[1]]["Frequency"] == 0):
                message_rand_freq_dict[int(row[5])][row[1]] = random.randint(1,10)
        else:
            print("Nothing found.")
    records = await select_sql(get_randomcolors)
    for row in records:
        if row[2] == 'Yes':
            try: random_colors[int(row[0])]
            except: random_colors[int(row[0])] = {} 
            random_colors[int(row[0])][int(row[1])] = True
        try: user_color_roles[int(row[0])]
        except: user_color_roles[int(row[0])] = { }
        user_color_roles[int(row[0])][int(row[1])] = row[3]    
            
            
@client.event
async def on_guild_join(guild):
    global user_dict
    global message_dict
    global message_count_dict
    global message_rand_freq_count
    global emoji_reaction 
    global bot_mood
    global user_color_roles
    
    message_count_dict[guild.id] = {}
    emoji_reaction[guild.id] = True
    bot_mood[guild.id] = { }
    
    for member in guild.members:
        bot_mood[guild.id][member.id] = ""
        if member.nick:
            message_count_dict[guild.id][member.nick] = 0
            
        else:
            message_count_dict[guild.id][member.name] = 0
    user_dict[guild.id] = { }
    message_dict[guild.id] = { }
    message_rand_freq_count[guild.id] = { }
    user_color_roles[guild.id] = {} 
    
    
@client.event
async def on_guild_remove(guild):
    await log_message("Left guild " + guild.name)
    result = await commit_sql("""DELETE FROM Reactions WHERE ServerId = %s;""",(str(guild.id),))
    await log_message("removed all reactions from guild.")

@client.event
async def on_member_join(member):
    global user_dict
    global message_dict
    global message_count_dict
    global message_rand_freq_count
    global emoji_reaction 
    global bot_mood
    
    await log_message("Member " + member.name + " joined guild " + member.guild.name)
    bot_mood[member.guild.id][member.id] = ""
    message_count_dict[member.guild.id][member.display_name] = 0
    
@client.event
async def on_member_remove(member):
    await log_message("Member " + member.name + " left guild " + member.guild.name)
    
@client.event
async def on_message(message):
    global classifier
    global emoji_reaction
    global user_dict
    global message_dict
    global message_count_dict
    global message_rand_freq_dict
    global bot_mood
    global random_colors
    global featuresets
    global user_color_roles

    if message.author.bot:
        return
    if message.author.nick:
        username = message.author.nick
    else:
        username = message.author.name
    pattern = username
    

        
    message_count_dict[message.guild.id][username] = message_count_dict[message.guild.id][username] + 1
    if bot_mood[message.guild.id][message.author.id]:

        if (message_count_dict[message.guild.id][username] <= 1):
            message_rand_freq_dict[message.guild.id][message.author.id] = random.randint(1,10)
            frequency = message_rand_freq_dict[message.guild.id][message.author.id]
            await log_message("New Frequency: " + str(frequency))
        elif message_count_dict[message.guild.id][username] >=2:
            frequency = message_rand_freq_dict[message.guild.id][message.author.id]
        await log_message("Frequency: " + str(frequency))
        await log_message("Message count: " + str(message_count_dict[message.guild.id][username]))
        if message_count_dict[message.guild.id][username] == frequency:
            message_count_dict[message.guild.id][username] = 0
            await message.add_reaction(random.choice(bot_mood[message.guild.id][message.author.id]))      
        
    elif emoji_reaction[message.guild.id]:
        if message.author.nick:
            username = message.author.nick
        else:
            username = message.author.name

        await log_message("Message count for " + username + " = " + str(message_count_dict[message.guild.id][username]))
        for pattern in message_dict[message.guild.id]:
            if re.search(pattern, message.content, re.IGNORECASE | re.S):
                emoji_string = message_dict[message.guild.id][pattern]["Emoji"]
                if '/' in emoji_string:
                    emoji_choices = emoji_string.split('/')
                    emoji_string = str(random.choice(emoji_choices)).strip()
                reaction_type = message_dict[message.guild.id][pattern]["ReactionType"]
                frequency = int(message_dict[message.guild.id][pattern]["Frequency"])
                if (reaction_type == 'React'):
                    await message.add_reaction(emoji_string)
                elif (reaction_type == 'Reply'):
                    await send_message(message,emoji_string)
                else:
                    pass
        for pattern in user_dict[message.guild.id]:
            if re.search(pattern, username, re.IGNORECASE | re.S):
                emoji_string = user_dict[message.guild.id][pattern]["Emoji"]
                if '/' in emoji_string:
                    emoji_choices = emoji_string.split('/')
                    emoji_string = str(random.choice(emoji_choices)).strip()
                
                reaction_type = user_dict[message.guild.id][pattern]["ReactionType"]
                frequency = int(user_dict[message.guild.id][pattern]["Frequency"])
                await log_message("Frequency: " + str(frequency))
                if (frequency == 0 and message_count_dict[message.guild.id][username] <= 1):
                    message_rand_freq_dict[message.guild.id][pattern] = random.randint(1,10)
                    frequency = message_rand_freq_dict[message.guild.id][pattern]
                    await log_message("New Frequency: " + str(frequency))
                    
                elif (frequency == 0 and message_count_dict[message.guild.id][username] >=2):
                    frequency = message_rand_freq_dict[message.guild.id][pattern]
                
                if (reaction_type == 'React') and message_count_dict[message.guild.id][username] >= frequency:
                    message_count_dict[message.guild.id][username] = 0
                    await message.add_reaction(emoji_string)
                    color_roles = user_color_roles[message.guild.id][message.author.id].split(',')
                    await log_message("Color roles: " + str(color_roles))
                    if random_colors[message.guild.id][message.author.id]:
                        await log_message("You have random colors on.")
                        for rolec in color_roles:
                            await log_message("Color role: " + rolec)
                            for role in message.author.roles:
                                await log_message("Role name: " + str(role.name))
                                if rolec == role.name:
                                    color = random.choice(color_roles)
                                    await log_message("Your color is " + color)
                                    await message.author.remove_roles(get(message.guild.roles, name=rolec))
                                    await message.author.add_roles(get(message.guild.roles, name=color))

                elif (reaction_type == 'Reply') and message_count_dict[message.guild.id][username] >= frequency:
                    message_count_dict[message.guild.id][username] = 0
                    await send_message(message,emoji_string)
                else:
                    pass
    
      
   
    if message.content.startswith('+'):
        command_string = message.content.split(' ')
        command = command_string[0].replace('+','')
        parsed_string = message.content.replace(command,"").replace("+","")
        
        if message.author.nick:
            username = message.author.nick
        else:
            username = message.author.name
        if (command == 'emoji'):
            if (emoji_reaction[message.guild.id]):
                emoji_reaction[message.guild.id] = False
                await send_message(message,"Emoji reactions off.")
            else:
                emoji_reaction[message.guild.id] = True
                for member in message.guild.members:
                    message_count_dict[message.guild.id][member.nick] = 0
                await send_message(message,"Emoji reactions on.")
        elif command == 'setcolorroles':
            user_id = message.author.id
            color_roles = parsed_string.strip()
            user_color_roles[message.guild.id][message.author.id] = color_roles
            result = await commit_sql("""UPDATE RandomColors SET ColorRoles=%s WHERE ServerId=%s AND UserId=%s;""",(str(color_roles),str(message.guild.id),str(user_id)))
            if result:
                await send_message(message, "Random color roles set!")
            else:
                await send_message(message, "Database error!")                
        elif command == 'randomcolors':
            if not random_colors[message.guild.id][message.author.id]:
                random_colors[message.guild.id][message.author.id] = True
                result = await select_sql("""SELECT RandomColors FROM RandomColors WHERE ServerId=%s AND UserId=%s;""",(str(message.guild.id),str(message.author.id)))
                if not result:
                    insert_result = await commit_sql("""INSERT INTO RandomColors (ServerId,UserId,RandomColors) VALUES (%s,%s,%s);""",(str(message.guild.id),str(message.author.id),'Yes'))
                else:
                    insert_result = await commit_sql("""UPDATE RandomColors SET RandomColors=%s WHERE ServerId=%s AND UserId=%s);""",('Yes',str(message.guild.id),str(message.author.id)))
                        
                await send_message(message, "Random colors on for <@" + str(message.author.id) + "> .")
            else:
                result = await select_sql("""SELECT RandomColors FROM RandomColors WHERE ServerId=%s AND UserId=%s;""",(str(message.guild.id),str(message.author.id)))
                if not result:
                    insert_result = await commit_sql("""INSERT INTO RandomColors (ServerId,UserId,RandomColors) VALUES (%s,%s,%s);""",(str(message.guild.id),str(message.author.id),'No'))
                else:
                    insert_result = await commit_sql("""UPDATE RandomColors SET RandomColors=%s WHERE ServerId=%s AND UserId=%s);""",('No',str(message.guild.id),str(message.author.id)))            
                random_colors[message.guild.id][message.author.id] = False
                await send_message(message, "Random colors off for <@" + str(message.author.id) + "> .")
        elif command == 'analyze':
            custom_string = parsed_string
            custom_tokens = remove_noise(word_tokenize(custom_string))
            response = classifier.classify(document_features(custom_tokens))
            await send_message(message, "Sentiment analysis: " + str(response))
        elif (command == 'initialize'):
            await log_message("initialize called by " + username)
            if (message.author.id != 610335542780887050):
                await send_message(message,"Admin command only!")
                return
            await send_message(message,"Creating databases...")
                
            create_reaction_table = """CREATE TABLE Reactions (Id int NOT NULL, UserID varchar(40), EmojiString varchar(1000), ReactionPattern varchar(200), MessageOrUser varchar(10), ReactionType varchar(30), Frequency Int, ServerId varchar(40));"""
            

            result = await execute_sql(create_reaction_table)

            if result:
                await send_message(message,"Database created successfully.")
            else:
                await send_message(message,"Database error!")
                
        elif (command == 'resetall'):
            await log_message("resetall called by " + username)
            if (message.author.id != 610335542780887050):
                await send_message(message,"Admin command only!")
                return
            await send_message(message,"Deleting databases...")
           
            drop_reaction_table = """DROP TABLE Reactions;"""
            
            result = await execute_sql(drop_reaction_table)

            if result:    
                await send_message(message,"Database dropped successfully.")
            else:
                await send_message(message,"Database error!")

        elif command == 'randomaction':
            if message.author.nick:
                name = message.author.nick
            else:
                name = message.author.name        
            responses = ["flops on","rolls around","curls on","lurks by","farts near","falls asleep on","throws Skittles at","throws popcorn at","huggles","snugs","hugs","snuggles","tucks in","watches","stabs","slaps","sexes up","tickles","thwaps","pinches","smells","cries with","laughs at","fondles","stalks","leers at","creeps by","lays on","glomps","clings to","flirts with","makes fun of","nibbles on","noms","protects","stupefies","snickers at"]
            usernames = message.guild.members
            user = random.choice(usernames)
            if parsed_string:
                user_id = message.mentions[0].id
            else:
                user_id = user.id
            response = "*" + name + " " + random.choice(responses) + " <@" + str(user_id) + ">*"
            await send_message(message, response)
            await message.delete()
        elif command == 'me':
            if message.author.nick:
                name = message.author.nick
            else:
                name = message.author.name        
            await send_message(message, "*-" + name + " " + parsed_string + "-*")
            await message.delete()              
        elif command == 'lurk':
            if message.author.nick:
                name = message.author.nick
            else:
                name = message.author.name
            responses = ["*" + name + " lurks in the shadowy rafters with luminous orbs with parted tiers, trailing long digits through their platinum tresses.*", "**" +name + ":** ::lurk::", "*" + name + " flops on the lurker couch.*", "*double lurk*","*luuuuuurk*","*posts that they are lurking so someone notices they are lurking*"]
            await send_message(message, random.choice(responses))
            await message.delete()            
        elif command == 'mood':
            parsed_string = message.content.replace("+mood ","")
        
            if not parsed_string:
                await send_message(message, "No mood specified!")
                return
            if not message.mentions:
                await send_message(message, "No user specified!")
                return
            m = re.search(r"(?P<mood>.+?) ",parsed_string)
            if not m:
                await send_message(message, "No mood found!")
                return
            else:
                mood = str(m.group('mood'))
            if mood == 'none':
                bot_mood[message.guild.id][message.mentions[0].id] = ""
                await send_message(message, "Mood disabled for user " + message.mentions[0].name)
                return
            records = await select_sql("""SELECT Emojis FROM Moods WHERE MoodName=%s;""", (mood,))
            if not records:
                await send_message(message, "No mood found!")
                return
            for row in records:
                mood_list = row[0].split('|')
            for mood_item in mood_list:
                mood_item = mood_item.strip()
            await log_message("Emojis: " + str(mood_list))
            bot_mood[message.guild.id][message.mentions[0].id] = mood_list
            await log_message("Emoji list: " + str(bot_mood[message.guild.id][message.mentions[0].id]))
            message_rand_freq_dict[message.guild.id][message.author.id] = random.randint(1,10)
            for user in message.guild.members:
                if user.nick:
                    message_count_dict[message.guild.id][message.author.nick] = 0
                else:
                    message_count_dict[message.guild.id][message.author.name] = 0
            
            await send_message(message, "Bot mood set to " + mood + " for user " + message.mentions[0].name + "!") 
            
            
        elif (command == 'addreaction'):
            message_type = False
            user_type = False
            reaction_add = False
            reply_add = False
            emoji_string = " "
            pattern_string = " "
            frequency = "0"
            message_or_user = " "
            react_or_reply = " "
            await log_message("addreaction called by " + username)
            parsed_string = message.content
            emoji_re = re.compile(r"-emoji (.+?) -", re.MULTILINE | re.S)
            pattern_re = re.compile(r"-pattern (.+?) -", re.MULTILINE | re.S)
            frequency_re = re.compile(r"-frequency (\d+) -", re.MULTILINE | re.S)
            message_re = re.compile(r"-message", re.MULTILINE | re.S)
            user_re = re.compile(r"-user", re.MULTILINE | re.S)
            reaction_re = re.compile(r"-react", re.MULTILINE | re.S)
            reply_re = re.compile(r"-reply", re.MULTILINE | re.S)
            user_id = message.author.id
            id = 1
            m = emoji_re.search(parsed_string)
            if not m:
                await send_message(message,"No emoji specified!")
                return
            emoji_string = m.group()
            emoji_string = emoji_string.replace("-emoji ","")
            emoji_string = emoji_string.replace("-","")
            emoji_string = emoji_string.strip()
            
            m = pattern_re.search(parsed_string)
            if not m:
                await send_message(message,"No pattern specified!")
                return
            pattern_string = m.group()
            pattern_string = pattern_string.replace("-pattern ","")
            pattern_string = pattern_string.replace("-","")
            pattern_string = pattern_string.strip()
            
            m = frequency_re.search(parsed_string)
            if not m:
                await send_message(message,"No frequency specified, setting to every message!")
            else:
                frequency = m.group()
                frequency = frequency.replace("-frequency ","")
                frequency = frequency.replace("-","")
                frequency = frequency.strip()
                
            if message_re.search(parsed_string):
                message_type = True
                message_or_user = "Message"
            if user_re.search(parsed_string):
                user_type = True
                message_or_user = "User"
            
            if reply_re.search(parsed_string):
                reply_add = True
                react_or_reply = "Reply"
            if reaction_re.search(parsed_string):
                reaction_add = True
                react_or_reply = "React"
                
            if not message_type and not user_type:
                await send_message(message,"No user or message flag specified!")
                return
            if message_type and user_type:
                await send_message(message,"You cannot specifiy both the user and message flag!")
                return
            if not reaction_add and not reply_add:
                await send_message(message,"No reply or react action flag specified!")
                return
            if reaction_add and reply_add:
                await send_message(message,"You cannot add both a reply and react action!")
                return
                
            add_reaction_entry = """INSERT INTO Reactions (Id, UserID, EmojiString, ReactionPattern, MessageOrUser, ReactionType, Frequency, ServerId) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);"""
            post_to_save = (id, user_id, emoji_string, pattern_string, message_or_user, react_or_reply, frequency, str(message.guild.id))
            result = await commit_sql(add_reaction_entry, post_to_save)
            if result:
                await send_message(message,"Reaction saved successfully.")
            else:
                await send_message(message,"Database error!")

            get_reactions = """SELECT EmojiString,ReactionPattern,MessageOrUser,ReactionType,Frequency FROM Reactions WHERE ServerId=%s;"""
            records = await select_sql(get_reactions, (str(message.guild.id),))
            for row in records:
                if "Message" in row[2]:
                    message_dict[message.guild.id][row[1]] = {}
                    message_dict[message.guild.id][row[1]]["Emoji"] = row[0]
                    message_dict[message.guild.id][row[1]]["ReactionType"] = row[3]
                    message_dict[message.guild.id][row[1]]["Frequency"] = row[4]
                elif "User" in row[2]:
                    user_dict[message.guild.id][row[1]] = {} 
                    user_dict[message.guild.id][row[1]]["Emoji"] = row[0]
                    user_dict[message.guild.id][row[1]]["ReactionType"] = row[3]
                    user_dict[message.guild.id][row[1]]["Frequency"] = row[4]
                    if (user_dict[message.guild.id][row[1]]["Frequency"] == 0):
                        message_rand_freq_dict[message.guild.id][row[1]] = random.randint(1,10)                        
                else:
                    await log_message("Nothing found.")
        elif (command == 'changereaction'):
            message_type = False
            user_type = False
            reaction_add = False
            reply_add = False
            emoji_string = " "
            pattern_string = " "
            frequency = "0"
            message_or_user = " "
            react_or_reply = " "
            await log_message("changereaction called by " + username)
            parsed_string = message.content
            emoji_re = re.compile(r"-emoji (.+?) -", re.MULTILINE | re.S)
            pattern_re = re.compile(r"-pattern (.+?) -", re.MULTILINE | re.S)
            frequency_re = re.compile(r"-frequency (\d+) -", re.MULTILINE | re.S)
            message_re = re.compile(r"-message", re.MULTILINE | re.S)
            user_re = re.compile(r"-user", re.MULTILINE | re.S)
            reaction_re = re.compile(r"-react", re.MULTILINE | re.S)
            reply_re = re.compile(r"-reply", re.MULTILINE | re.S)
            user_id = message.author.id
            id = 1
            m = emoji_re.search(parsed_string)
            if not m:
                await send_message(message,"No emoji specified!")
                return
            emoji_string = m.group()
            emoji_string = emoji_string.replace("-emoji ","")
            emoji_string = emoji_string.replace("-","")
            emoji_string = emoji_string.strip()
            
            m = pattern_re.search(parsed_string)
            if not m:
                await send_message(message,"No pattern specified!")
                return
            pattern_string = m.group()
            pattern_string = pattern_string.replace("-pattern ","")
            pattern_string = pattern_string.replace("-","")
            pattern_string = pattern_string.strip()
            
            m = frequency_re.search(parsed_string)
            if not m:
                await send_message(message,"No frequency specified, setting to every message!")
            else:
                frequency = m.group()
                frequency = frequency.replace("-frequency ","")
                frequency = frequency.replace("-","")
                frequency = frequency.strip()
                
            if message_re.search(parsed_string):
                message_type = True
                message_or_user = "Message"
            if user_re.search(parsed_string):
                user_type = True
                message_or_user = "User"
            
            if reply_re.search(parsed_string):
                reply_add = True
                react_or_reply = "Reply"
            if reaction_re.search(parsed_string):
                reaction_add = True
                react_or_reply = "React"
                
            if not message_type and not user_type:
                await send_message(message,"No user or message flag specified!")
                return
            if message_type and user_type:
                await send_message(message,"You cannot specifiy both the user and message flag!")
                return
            if not reaction_add and not reply_add:
                await send_message(message,"No reply or react action flag specified!")
                return
            if reaction_add and reply_add:
                await send_message(message,"You cannot add both a reply and react action!")
                return
            change_reaction_entry = """UPDATE Reactions SET UserID=%s, EmojiString=%s, ReactionType=%s, Frequency=%s WHERE ReactionPattern=%s AND ServerId=%s ;"""            

            post_to_save = (user_id, emoji_string, react_or_reply, frequency,pattern_string, str(message.guild.id))
            result = await commit_sql(change_reaction_entry, post_to_save)
            if result:
                await send_message(message,"Reaction saved successfully.")
            else:
                await send_message(message,"Database error!")
            message_dict[message.guild.id].clear()
            user_dict[message.guild.id].clear()
            get_reactions = """SELECT EmojiString,ReactionPattern,MessageOrUser,ReactionType,Frequency FROM Reactions WHERE ServerId=%s;"""
            records = await select_sql(get_reactions, (str(message.guild.id),))
            for row in records:
                if "Message" in row[2]:
                    message_dict[message.guild.id][row[1]] = {}
                    message_dict[message.guild.id][row[1]]["Emoji"] = row[0]
                    message_dict[message.guild.id][row[1]]["ReactionType"] = row[3]
                    message_dict[message.guild.id][row[1]]["Frequency"] = row[4]
                elif "User" in row[2]:
                    user_dict[message.guild.id][row[1]] = {} 
                    user_dict[message.guild.id][row[1]]["Emoji"] = row[0]
                    user_dict[message.guild.id][row[1]]["ReactionType"] = row[3]
                    user_dict[message.guild.id][row[1]]["Frequency"] = row[4]            
                else:
                    await log_message("Nothing found.")
        elif (command == 'deletereaction'):
            message_type = False
            user_type = False
            reaction_add = False
            reply_add = False
            emoji_string = " "
            pattern_string = " "
            frequency = "0"
            message_or_user = " "
            react_or_reply = " "
            await log_message("deletereaction called by " + username)
            parsed_string = message.content
            emoji_re = re.compile(r"-emoji (.+?) -", re.MULTILINE | re.S)
            pattern_re = re.compile(r"-pattern (.+)", re.MULTILINE | re.S)
            frequency_re = re.compile(r"-frequency (\d+) -", re.MULTILINE | re.S)
            message_re = re.compile(r"-message", re.MULTILINE | re.S)
            user_re = re.compile(r"-user", re.MULTILINE | re.S)
            reaction_re = re.compile(r"-react", re.MULTILINE | re.S)
            reply_re = re.compile(r"-reply", re.MULTILINE | re.S)
            user_id = message.author.id
            id = 1
            
            m = pattern_re.search(parsed_string)
            if not m:
                await send_message(message,"No pattern specified!")
                return
            pattern_string = m.group()
            pattern_string = pattern_string.replace("-pattern ","")
            pattern_string = pattern_string.strip()
            await log_message("Pattern string: " + pattern_string)
            delete_reaction_entry = """DELETE FROM Reactions WHERE ReactionPattern = %s AND ServerId=%s;"""            
            result = await commit_sql(delete_reaction_entry, (pattern_string,str(message.guild.id)))
            await send_message(message,"Reaction deleted successfully.")
            message_dict[message.guild.id] = { }
            user_dict[message.guild.id] = {}                   
            get_reactions = """SELECT EmojiString,ReactionPattern,MessageOrUser,ReactionType,Frequency FROM Reactions WHERE ServerId=%s;"""

            records = await select_sql(get_reactions, (str(message.guild.id),))
            for row in records:
                if "Message" in row[2]:
                    message_dict[message.guild.id][row[1]] = {}
                    message_dict[message.guild.id][row[1]]["Emoji"] = row[0]
                    message_dict[message.guild.id][row[1]]["ReactionType"] = row[3]
                    message_dict[message.guild.id][row[1]]["Frequency"] = row[4]
                elif "User" in row[2]:
                    user_dict[message.guild.id][row[1]] = {} 
                    user_dict[message.guild.id][row[1]]["Emoji"] = row[0]
                    user_dict[message.guild.id][row[1]]["ReactionType"] = row[3]
                    user_dict[message.guild.id][row[1]]["Frequency"] = row[4]            
                else:
                    await log_message("Nothing found.")
      
        elif command == 'initializemood':
            result = await execute_sql("""CREATE TABLE Moods (Id int auto_increment, MoodName varchar(100), Emojis TEXT, PRIMARY KEY(Id));""")
            if result:
                await log_message("Mood database generated.")
            else:
                await log_message("Database error!")
            
            mood_dict = { 'happy': ':grinning:|:smiley:|:smile:|:grin:|:blush:|:relieved:|:thumbsup:|:raised_hands:',
                            'coy': ':wink:|:heart_eyes:|:relaxed:|:smiling_face_with_3_hearts:|:smirk:|:ohmy:|:jaw_drop:|:smiling_imp:|:bikini:|:eggplant:',
                            'pissy': ':f_bomb:|:unamused:|:triumph:|:angry:|:rage:|:middle_finger:|:face_with_symbols_over_mouth:|:imp:|:japanese_goblin:|:rolling_eyes:',
                         'silly':':sweat_smile:|:joy:|:rofl:|:laughing:|:zany_face:|:stuck_out_tongue_winking_eye:|:stuck_out_tongue_closed_eyes:|:stuck_out_tongue:|:upside_down:|:nerd:|:face_with_monocle:|:yagazuzi:',
                            'sad': ':dark_heart:|:pensive:|:disappointed:|:worried:|:frowning2:|:pleading_face:|:persevere:|:disappointed_relieved:|:cry:|:sob:'}
        elif command=='addmood':
            mood = command_string[1]
            emojis = message.content.replace("+addmood ","").replace(mood,"")
            

            result = await commit_sql("""INSERT INTO Moods (MoodName,Emojis) VALUES (%s,%s);""", (mood, emojis))
            await send_message(message, "Moods loaded!")
            
        elif command == 'mood':
            parsed_string = message.content.replace("+mood ","")
        
            if not parsed_string:
                await send_message(message, "No mood specified!")
                return
            if not message.mentions:
                await send_message(message, "No user specified!")
                return
            m = re.search(r"(?P<mood>.+?) ",parsed_string)
            if not m:
                await send_message(message, "No mood found!")
                return
            else:
                mood = str(m.group('mood'))
            if mood == 'none':
                bot_mood[message.guild.id][message.mentions[0].id] = ""
                await send_message(message, "Mood disabled for user " + message.mentions[0].name)
                return
            records = await select_sql("""SELECT Emojis FROM Moods WHERE MoodName=%s;""", (mood,))
            if not records:
                await send_message(message, "No mood found!")
                return
            for row in records:
                mood_list = row[0].split('|')
            for mood_item in mood_list:
                mood_item = mood_item.strip()
            await log_message("Emojis: " + str(mood_list))
            bot_mood[message.guild.id][message.mentions[0].id] = mood_list
            await log_message("Emoji list: " + str(bot_mood[message.guild.id][message.mentions[0].id]))
            message_rand_freq_dict[message.guild.id][message.author.id] = random.randint(1,10)
            for user in message.guild.members:
                if user.nick:
                    message_count_dict[message.guild.id][message.author.nick] = 0
                else:
                    message_count_dict[message.guild.id][message.author.name] = 0
            
            await send_message(message, "Bot mood set to " + mood + " for user " + message.mentions[0].name + "!")
                            
        elif (command == 'info' or command == 'help'):
            await send_message(message,"**This is React-o-matic, a Discord bot for reactions and auto-replies!**\n\n*Written by Ninja Nerd*\n\n>>> **AVAILABLE COMMANDS**\n\n**+info** or **+help** This help message.\n\n**+addreaction** -emoji *emoji string* -pattern *regular expression* -frequency *message number* -user -message -react -reply\n\nAdd a reaction.\n\n__**Required Flags**__\n*-emoji*: The Unicode character or Discord ID of the emoji. To see the Discord ID, type \\:emoji: in Discord and place that after this flag.\n*-pattern*: This uses regular expressions. Search 'python regular expression' on Google for syntax, but to simply match a word or phrase, type it as is.\n*-frequency*: This is the number of messages to wait until reacting or replying to a message by a user that matches the pattern.\n*-user*: Apply the pattern to usernames.\n-message: Apply the pattern to messages sent.\n*-react*: React to a message matching the pattern.\n*-reply*: Reply to a message matching the pattern.\n\n-user/-message cannot be combined, and neither can -react/-reply.\n\n**+emoji** Turn the reactions on or off. The bot starts up in off mode by default.\n\n**+listreactions** Show all reactions defined.\n\n**+changereaction** -emoji *emoji string* -pattern *regular expression* -frequency *message number* -user -message -react -reply Change an existing reaction with the specified pattern. See the required flags for definitions.\n\n**+deletereaction** -pattern *regular expression*  Delete this reaction with the specified pattern.")
        elif (command == 'listreactions'):
            response = "**Reaction list**\n\n**USER NAME REACTIONS\n__Pattern__ __Emoji__ __ReactionType__ __Frequency__\n\n"
            for pattern in user_dict[message.guild.id]:
                response = response + pattern + " " + user_dict[message.guild.id][pattern]["Emoji"] + " " + user_dict[message.guild.id][pattern]["ReactionType"] + " " + str(user_dict[message.guild.id][pattern]["Frequency"]) + "\n"
            response = response + "\nMESSAGE REACTIONS\n__Pattern__ __Emoji__ __ReactionType__ __Frequency__\n\n"
            for pattern in message_dict[message.guild.id]:
                response = response + pattern + " " + message_dict[message.guild.id][pattern]["Emoji"] + " " + message_dict[message.guild.id][pattern]["ReactionType"] + " " + str(message_dict[message.guild.id][pattern]["Frequency"]) + "\n"
            await send_message(message, response)
        else:
            await send_message(message,"Invalid command.")
            
          
            
client.run('')   