import discord
import os
import subprocess
import asyncio
import datetime

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
        Downloads youtube video from given url. download_full determines whether the file is downloaded alongside
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
        Returns array of all songs returned from search (or array with single element if only one song returned)
        """
        return [YoutubeQuery.entry_into_song(entry) for entry in YoutubeQuery.get_formatted_data(data)]

    @staticmethod
    def get_formatted_data(data):
        if 'entries' in data:
            return data['entries']
        else:
            return [data]

    @staticmethod
    def entry_into_song(entry):
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
        Fully downloads a song of the given index from the searched list, and returns its filename
        """
        data = await self.get_data()
        song = YoutubeQuery.get_songs_from_data(data)[index]
        download_data = await self.download(song.url, self.loop, download_full=True)
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

async def download_existing_song(song: Song):
    download_data = await YoutubeQuery.download(Song.url, bot.loop, download_full=True)
    song.set_downloaded_file(ytdl.prepare_filename(download_data))

song_queue = []

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

@bot.command()
async def queue(ctx, url):
    '''Adds a song to the queue'''
    if not len(song_queue):
        # Queue empty
        return YoutubeQuery(url, loop=bot.loop)
    
    # Queue has songs in it -> Add to queue and play top
    song_queue.append(YoutubeQuery(url, loop=bot.loop))
    await ctx.send(f"{ctx.author} has added to the queue!")
    return song_queue.pop(0)
        

async def query_youtube_info(search, loop):
    song = YoutubeQuery(search, loop)
    return await song.get_songs_from_data()

@bot.command(name='getinfo', help='Gets a bit of info about a song')
async def get_song_info(ctx, *, search):
    '''Send song information to chat'''
    async with ctx.typing:
        songs = YoutubeQuery("ytsearch10: " + search)
        str = await songs.format_songs()
    await ctx.send(str)

"""
async def download_youtube(url, loop):
    '''Download YouTube video from url'''
    loop = loop if loop else asyncio.get_event_loop()
    # Download
    data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=1))
    if 'entries' in data:
        data = data['entries'][0]
    if 'duration' in data:
        # TODO: Do something with duration 
        duration = data['duration']
    # Get file path
    filename = ytdl.prepare_filename(data)
    return filename
"""

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

@bot.command(help="Play a song")
async def play(ctx, *, search):
    '''Play a song with the given name'''
    server = ctx.message.guild
    if server.voice_client is None:
        # Bot needs to join a voice channel
        await join(ctx)
    voice_channel = server.voice_client
    # try :
    if search[:3] != "http":
        # User is searching via words
        url = "ytsearch1: " + search
    else:
        url = search
    # Make the bot look like it's typing
    async with ctx.typing():
        # Get Song instance from queue

        # song_to_play = await queue(ctx, url)
        # filename = await download_youtube(song_to_play.url, loop=bot.loop)

        query = YoutubeQuery(url, bot.loop)
        song = await query.download_from_list(0)
        # Play the song in the voice channel
        voice_channel.play(discord.FFmpegPCMAudio(executable="./ffmpeg.exe", 
                                                    source=song.filename), 
                                                    after=lambda: song.delete_downloaded_file())
    await ctx.send(f"Now playing: {song.title}")
    # except Exception as e:
    #     # TODO: Make this more detailed!
    #     # Some Error
    #     print(e)
    #     await ctx.send("Something went wrong!")

def delete_files(filename):
    '''Delete the file at given filepath'''
    os.remove(filename)

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