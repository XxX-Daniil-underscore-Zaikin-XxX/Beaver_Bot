import discord
import os
import subprocess
import asyncio

from discord.ext import commands
from dotenv import load_dotenv
import youtube_dl

load_dotenv()

DISCORD_TOKEN = os.getenv("discord_token")

bot = commands.Bot(command_prefix='|')

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

class Song:
    def __init__(self, url, loop=None):
        self.loop = loop if loop else asyncio.get_event_loop()
        self.url = url
        self.data = None

    async def download_info(self):
        self.data = await self.loop.run_in_executor(None, lambda: ytdl.extract_info(self.url, download=0))

    async def get_data(self):
        if not self.data:
            await self.download_info()
        return self.data

    async def download_song(self):
        data = await self.loop.run_in_executor(None, lambda: ytdl.extract_info(self.url, download=1))

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
        return Song(url, loop=bot.loop)
    
    # Queue has songs in it -> Add to queue and play top
    song_queue.append(Song(url, loop=bot.loop))
    await ctx.send(f"{ctx.author} has added to the queue!")
    return song_queue.pop(0)
        

async def query_youtube_info(search, loop):
    '''Get information about a song'''
    song = Song(search, loop)
    await song.download_info()
    return song.data

@bot.command(name='getinfo', help='Gets a bit of info about a song')
async def get_song_info(ctx, *, search):
    '''Send song information to chat'''
    data = await query_youtube_info(search, bot.loop)
    await ctx.send("Filename: " + data['entries'][0]['title'])

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
    voice_channel = server.voice_client
    if voice_channel is None:
        # Bot needs to join a voice channel
        await join(ctx)
    try :
        if search[:3] != "http":
            # User is searching via words
            url = "ytsearch1:" + search
        else:
            url = search
        # Make the bot look like it's typing
        async with ctx.typing():
            # Get Song instance from queue
            song_to_play = await queue(ctx, url)
            filename = await download_youtube(song_to_play.url, loop=bot.loop)
            # Play the song in the voice channel
            voice_channel.play(discord.FFmpegPCMAudio(executable="./ffmpeg.exe", 
                                                      source=filename), 
                                                      after=lambda: delete_files(filename))
        await ctx.send(f"Now playing: {filename}")
    except Exception as e:
        # TODO: Make this more detailed!
        # Some Error
        print(e)
        await ctx.send("Something went wrong!")

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