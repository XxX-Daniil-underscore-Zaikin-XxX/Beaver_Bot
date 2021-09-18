import discord
import os
import subprocess
import asyncio
import datetime
import random

from discord.ext import commands
from dotenv import load_dotenv
import youtube_dl

load_dotenv()

DISCORD_TOKEN = os.getenv("discord_token")

# Global var for whether the user is currently searching through a list of songs to play
is_searching = False

#intents = discord.Intents().all()
#bot = commands.Bot(command_prefix='|', intents=intents)

#youtube_dl.utils.bug_reports_message = lambda: ''
bot = commands.Bot(command_prefix='.')

ytdl_format_options = {
    'format': 'bestaudio/best',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'username': os.getenv("username"),
    'password': os.getenv("password"),
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0', # bind to ipv4 since ipv6 addresses cause issues sometimes
    'outtmpl': "./songs/%(title)s.%(ext)s"
}

ffmpeg_options = {
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YoutubeQuery:
    def __init__(self, url, loop=None):
        self.loop = loop if loop else asyncio.get_event_loop()
        self.url = url
        self.data = None

    @staticmethod
    async def download(url, loop, download_full=False):
        """
        Downloads youtube video from given url. 
        Download_full determines whether the file is downloaded alongside
        """
        return await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=download_full))

    async def get_data(self):
        """
        Returns data from search. If it doesn't exist, it queries for it
        """
        if not self.data:
            self.data = await YoutubeQuery.download(self.url, self.loop)
        return self.data

    @staticmethod
    def get_songs_from_data(data):
        """
        Returns array of all songs (Song) returned from search 
        (or array with single element if only one song returned)
        """
        return [YoutubeQuery.entry_to_song(entry) for entry in YoutubeQuery.get_formatted_data(data)]

    @staticmethod
    def get_formatted_data(data):
        """
        Get song data from dictionary
        """
        if 'entries' in data:
            return data['entries']
        else:
            return [data]

    @staticmethod
    def entry_to_song(entry):
        """
        Convert entry into a Song object
        """
        return Song(entry['title'], entry['duration'], entry['webpage_url'])

    async def format_songs(self):
        """
        Returns discord-formatted string of the searched songs
        """
        data = await self.get_data()
        songs_data = YoutubeQuery.get_songs_from_data(data)
        return '\n'.join(["```"] + [str(ind + 1) + '\t' + str(song) for ind, song in enumerate(songs_data)] + ["\n```"])

    async def download_from_list(self, index):
        """
        Fully downloads a song of the given index 
        from the searched list, and returns its filename
        """
        data = await self.get_data()
        song = YoutubeQuery.get_songs_from_data(data)[index]
        download_data = await self.download(song.url, self.loop, download_full=False)
        filename = ytdl.prepare_filename(YoutubeQuery.get_formatted_data(download_data)[0])
        song.set_downloaded_file(filename)
        return song

class Song:
    def __init__(self, title, duration, url, filename=None):
        self.title = title
        self.duration = duration
        self.is_downloaded = not(filename == None)
        self.filename = filename
        self.url = url

    def set_downloaded_file(self, filename):
        self.filename = filename
        self.is_downloaded = True

    def delete_downloaded_file(self):
        os.remove(self.filename)
        self.filename = None
        self.is_downloaded = False

    def __str__(self) -> str:
        return self.title + '\t' + str(datetime.timedelta(seconds=self.duration))

class SongQueue:
    def __init__(self, loop, ytdl, executable="./ffmpeg.exe"):
        self.loop = loop if loop else asyncio.get_event_loop()
        self.ytdl = ytdl
        self.voice_channel = None
        self.executable = executable
        self.ctx = None
        self.songs = []
        self.current_song = 0
        self.currently_playing = False

    def is_currently_playing(self):
        """
        Check if the bot is currently playing a song
        Return True if playing / False otherwise
        """
        if self.voice_channel == None: return False
        return self.voice_channel.is_playing()

    def set_channel(self, voice_channel):
        """
        Set the bot's voice channel
        """
        self.voice_channel = voice_channel

    def set_ctx(self, ctx):
        """
        Set the context of discord client
        """
        self.ctx = ctx

    def insert_song(self, song, index):
        """
        Inset a song into the queue at position index
        """
        self.songs[index:index] = [song]

    async def push_song(self, song):
        """
        Add a song to the end of the queue if less than the limit
        Return True if able to push / False otherwise 
        """
        limit = 1.5 # hour
        if song.duration >= limit*60*60:
            # Song is larger than 1 hour
            await self.ctx.send("Cannot queue song longer than 1 hour")
            return False
        
        self.songs.append(song)
        await self.ctx.send(f"{self.ctx.author} has queued {song.title}")
        return True

    def remove_song(self, index):
        """
        Remove a song at the given index
        """
        if index <= self.current_song:
            # The song has already been played
            # or is currently playing
            return
        
        if self.songs[index].is_downloaded:
            # Delete the file on disk
            self.songs[index].delete_downloaded_file()
        
        # Remove from the queue
        del self.songs[index]

    async def play_song_after_current(self):
        """
        Play the song after current index 
        """
        self.current_song = self.current_song + 1
        if self.current_song >= len(self.songs):
           self.songs[self.current_song - 1].delete_downloaded_file()
        if self.current_song < len(self.songs) :
            # We are in bounds
            if self.songs[self.current_song].filename != self.songs[self.current_song - 1].filename:
                self.songs[self.current_song - 1].delete_downloaded_file()
            await self.play_current_song()
            
    async def play_current_song(self, func=None):
        """
        Play song at current queue index
        Starts recurrent song playing.
        If func is None, play all songs in sequence
        """
        if func == None:
            # Play in sequence
            func = self.play_song_after_current
        await self.play_song_at(self.current_song, func)

    def clear_songs(self):
        self.songs = []
        self.current_song = 0

    async def play_song_at(self, index, func=None):
        """
        Play the song at given index
        """
        async with self.ctx.typing():
            song = self.songs[index]
            if not song.is_downloaded: await download_existing_song(song)
            if self.ctx != None and self.voice_channel == None: 
                await join(self.ctx)
                self.voice_channel = self.ctx.message.guild.voice_client
            self.voice_channel.play(discord.FFmpegPCMAudio(executable=self.executable,
                                                           source=song.filename))
            await self.ctx.send(f"Now Playing: {song.title}")
        # TODO: pause function breaks sleep function
        #       since the sleep can finish while song is still paused
        await asyncio.sleep(song.duration)
        await func()

    async def pause(self):
        if self.is_currently_playing(): await self.voice_channel.pause()
    
    async def resume(self):
        if self.current_song < len(self.songs) and not self.is_currently_playing(): await self.voice_channel.resume()

    def __str__(self):
        return '\n'.join([(f" {ind+1} " if ind != self.current_song else f"[{ind+1}]") + '\t' + str(song) for ind, song in enumerate(self.songs)])

song_queue = SongQueue(bot.loop, ytdl)

async def download_existing_song(song: Song):
    download_data = await YoutubeQuery.download(song.url, bot.loop, download_full=True)
    song.set_downloaded_file(ytdl.prepare_filename(download_data))

async def download_info(url, loop):
    '''Download the video from given url'''
    loop = loop if loop else asyncio.get_event_loop()
    data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=0))
    duration, filesize = 0, 0
    if 'entries' in data:
        data = data['entries'][0]
    if 'duration' in data:
        duration = data['duration']
    if 'filesize' in data:
        filesize = data['filesize']
    filename = data['title']
    return filename
        
async def query_youtube_info(search, loop):
    song = YoutubeQuery(search, loop)
    return await song.get_songs_from_data()

@bot.command(name='shuffle', help='Shuffles the queue')
async def shuffle(ctx):
    """
    Shuffle the queue. Shuffles songs that are 
    strictly greater than the currently selected song
    """
    # Get the first half of the queue including the current song
    first_half = song_queue.songs[:song_queue.current_song + 1]
    # Second hald of the queue excluding the current song
    second_half = song_queue.songs[song_queue.current_song + 1:]
    # Shuffle the songs
    random.shuffle(second_half)
    song_queue.songs = first_half + second_half
    await ctx.send(f"{ctx.author} has shuffled the queue!")

@bot.command(name='getinfo', help='Gets a bit of info about a song')
async def get_song_info(ctx, *, search):
    '''Send song information to chat'''
    async with ctx.typing:
        songs = YoutubeQuery("ytsearch10: " + search)
        str = await songs.format_songs()
    await ctx.send(str)

@bot.command(name='join', help='Tells bot to join')
async def join(ctx):
    '''Connect bot to voice channel'''
    if not ctx.message.author.voice:
        # Invoking user not in a voice chat 
        await ctx.send(f"{ctx.mesage.author.name} is not connected to a voice channel")
        return
    # Connect to channel with user
    channel = ctx.message.author.voice.channel
    await channel.connect()

@bot.command(name='queue', help='Displays Queue', aliases=["q"])
async def display_song_queue(ctx):
    '''Display queue'''
    async with ctx.typing():
        if len(song_queue.songs) == 0:
            # Queue is empty
            await ctx.send("The queue is empty :(")
            return 
        message = f"```\n{str(song_queue)}\n```"
    await ctx.send(message)

@bot.command(name='play', help="Play a song", aliases=["p"])
async def play(ctx, *, search):
    '''Play a song with the given name'''
    server = ctx.message.guild
    if server.voice_client is None:
        # Bot needs to join a voice channel
        await join(ctx)
    voice_channel = server.voice_client
    song_queue.set_channel(voice_channel)
    song_queue.set_ctx(ctx)
    # try :
    if search[:3] != "http":
        # User is searching via words
        url = "ytsearch1: " + search
    else:
        url = search
    query = YoutubeQuery(url, bot.loop)
    data = await query.get_data()
    song = YoutubeQuery.get_songs_from_data(data)[0]
    result = await song_queue.push_song(song)
    if result and not song_queue.is_currently_playing(): 
        await song_queue.play_current_song()

def delete_files(filename):
    '''Delete the file at given filepath'''
    os.remove(filename)

@bot.command(name='skip', help='Skip the current song')
async def skip(ctx):
    """
    Skip the song currently playing
    """
    if song_queue.current_song >= len(song_queue.songs):
        # We are out of bounds
        return
    
    # Skip the song
    ctx.message.guild.voice_client.stop()
    if song_queue.songs[song_queue.current_song].is_downloaded:
        # File is there to delete
        song_queue.songs[song_queue.current_song].delete_downloaded_file()
    song_queue.current_song += 1
    await song_queue.play_current_song()

@bot.command(name='pause', help='This command pauses the song')
async def pause(ctx):
    '''Pause the bot from playing'''
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_playing():
        # Pause
        voice_client.pause()
    else:
        # Bot is already paused
        await ctx.send("The bot is not playing anything at the moment.")
    
@bot.command(name='resume', help='Resumes the song')
async def resume(ctx):
    '''Resume the bot if a song was playing'''
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_paused():
        # Resume the song
        voice_client.resume()
    else:
        # No song was playing
        await ctx.send("The bot was not playing anything before this. Use play_song command")

@bot.command(name='stop', help='Stops the song')
async def stop(ctx):
    '''Stop the current song from playing'''
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_playing():
        # Stop
        await voice_client.stop()
    else:
        # No song was playing
        await ctx.send("The bot is not playing anything at the moment.")

@bot.command(name='leave', help='To make the bot leave the voice channel')
async def leave(ctx):
    '''Disconnect the bot from voice channel'''
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_connected():
        # Disconnect
        await voice_client.disconnect()
    else:
        # Not currently in voice channel
        await ctx.send("The bot is not connected to a voice channel.")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)