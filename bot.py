import discord
import os
import subprocess
import asyncio

from discord.ext import commands,tasks
from dotenv import load_dotenv
import youtube_dl

load_dotenv()

DISCORD_TOKEN = os.getenv("discord_token")

intents = discord.Intents().all()
client = discord.Client(intents=intents)
bot = commands.Bot(command_prefix='|', intents=intents)

youtube_dl.utils.bug_reports_message = lambda: ''

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
    'source_address': '0.0.0.0' # bind to ipv4 since ipv6 addresses cause issues sometimes
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

    async def download_info(self):
        self.data = await self.loop.run_in_executor(None, lambda: ytdl.extract_info(self.url, download=0))

    async def get_data(self):
        if not self.data:
            await self.download_info()
        return self.data

    async def get_songs_data(self):
        data = await self.get_data()
        if data['entries']:
            return data['entries']
        else:
            return [data]

    async def get_first_song_title(self):
        return await self.get_data()[0]['title']

    async def download_song(self, index):
        data = await self.loop.run_in_executor(None, lambda: ytdl.extract_info(self.get_songs_data()[index]['webpage-url'], download=1))
        if 'entries' in data:
            data = data['entries']
        return ytdl.prepare_filename(data)


async def query_youtube_info(search, loop):
    song = YoutubeQuery(search, loop)
    return await song.get_songs_data()

@bot.command(name='getinfo', help='Gets a bit of info about a song')
async def get_song_info(ctx, *search):
    data = await query_youtube_info(' '.join(search), bot.loop)
    await ctx.send("Filename: " + data[0]['title'])

async def download_youtube(url, loop):
    loop = loop if loop else asyncio.get_event_loop()
    data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=1))
    if 'entries' in data:
        data = data['entries'][0]
    if 'duration' in data:
        duration = data['duration']
    filename = ytdl.prepare_filename(data)
    return filename

@bot.command(name='join', help='Tells bot to join')
async def join(ctx):
    if not ctx.message.author.voice:
        await ctx.send("{} is not connected to a voice channel".format(ctx.mesage.author.name))
        return
    else:
        channel = ctx.message.author.voice.channel
    await channel.connect()

@bot.command(name='p_url', help='To play song')
async def play(ctx, url):
    await play_url(ctx, url)

async def play_url(ctx, url):
    try :
        server = ctx.message.guild
        voice_channel = server.voice_client

        async with ctx.typing():
            songs = await query_youtube_info(url, bot.loop)
            filename = songs[0]['title']
            voice_channel.play(discord.FFmpegPCMAudio(executable="ffmpeg.exe", source=filename), after=lambda: delete_file(filename))
        await ctx.send('Now playing: {}'.format(filename))
    except:
        await ctx.send("The bot ain't in a voice channel")

def delete_file(filename):
    os.remove(filename)

@bot.command(name='p_search', help='To play song (but you gotta search)')
async def play_search(ctx, *searches):
    await play_url(ctx, "ytsearch1:" + ' '.join(searches))

@bot.command(name='pause', help='This command pauses the song')
async def pause(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_playing():
        voice_client.pause()
    else:
        await ctx.send("The bot is not playing anything at the moment.")
    
@bot.command(name='resume', help='Resumes the song')
async def resume(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_paused():
        voice_client.resume()
    else:
        await ctx.send("The bot was not playing anything before this. Use play_song command")

@bot.command(name='stop', help='Stops the song')
async def stop(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_playing():
        await voice_client.stop()
    else:
        await ctx.send("The bot is not playing anything at the moment.")

@bot.command(name='leave', help='To make the bot leave the voice channel')
async def leave(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client.is_connected():
        await voice_client.disconnect()
    else:
        await ctx.send("The bot is not connected to a voice channel.")

@client.event
async def on_ready():
    print('Sup {0.user}'.format(client))

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.startswith('$hello'):
        await message.channel.send('Hello!')

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)