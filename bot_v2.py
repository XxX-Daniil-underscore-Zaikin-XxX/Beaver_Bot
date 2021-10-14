import discord
import asyncio
import os
import youtube_dl

import urllib.parse, urllib.request, re
# import requests
from dotenv import load_dotenv

from discord.ext import commands
from discord import Embed, FFmpegPCMAudio
from discord.utils import get

'''

INSTALLING YOUTUBE-DL

pip install -U git+https://github.com/l1ving/youtube-dl

'''

load_dotenv()

DISCORD_TOKEN = os.getenv("discord_token")
# QUEUE = []

youtube_dl.utils.bug_reports_message = lambda: ''

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': './songs/%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}

ffmpeg_options = {
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)

        self.data = data

        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True, play=False):
        """Prepare the song from given search or url"""
        if loop is None:
            loop = asyncio.get_event_loop()
        data = ytdl.extract_info(url, download=not stream or play)
        
        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queue = []
        self.paused = False
    
    @commands.command()
    async def join(self, ctx):
        """Join a discord voice channel"""
        if not ctx.message.author.voice:
            await ctx.send("You are not connected to a voice channel!")
            return
        else:
            channel = ctx.message.author.voice.channel
            await ctx.send(f'Connected to ``{channel}``')

        await channel.connect()

    @commands.command(name="play", aliases=["p"])
    async def play(self, ctx, *, url):
        """Play a song on with the given url/search terms"""
        try:
            async with ctx.typing():
                if url[:3] != "http":
                    # User is searching via words
                    url = "ytsearch1: " + url
                player = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True)
                await self.add_queue(ctx, player)
                await self.start_playing(ctx)
        except Exception as e:
            print(e)
            await ctx.send("Somenthing went wrong - please try again later!")

    @commands.command()
    async def pause(self, ctx):
        """Pause the bot"""
        voice = get(self.bot.voice_clients, guild=ctx.guild)

        voice.pause()
        self.paused = True

        user = ctx.message.author.mention
        await ctx.send(f"Bot was paused by {user}")

    @commands.command()
    async def resume(self, ctx):
        """Resume the bot"""
        voice = get(self.bot.voice_clients, guild=ctx.guild)

        voice.resume()
        self.paused = False

        user = ctx.message.author.mention
        await ctx.send(f"Bot was resumed by {user}")

    async def add_queue(self, ctx, player):
        """Add a song to the queue"""
        try:
            self.queue.append(player)
            user = ctx.message.author.mention
            await ctx.send(f'``{player.title}`` was added to the queue by {user}!')
        except:
            await ctx.send(f"Couldnt add {player.title} to the queue!")

    @commands.command(name="remove", aliases=["r"])
    async def remove(self, ctx, number):
        """Remove a song from the queue"""
        try:
            self.queue.remove(int(number) - 1)
            del(self.queue[int(number)])
            if len(self.queue) < 1:
                await ctx.send("Your queue is empty now!")
            else:
                await ctx.send(f'Your queue is now {self.view_queue(ctx)}')
        except:
            await ctx.send("Remove Failed! Number is out of bounds...")

    @commands.command(name="clear")
    async def clear(self, ctx):
        """Clear the entire queue"""
        self.queue.clear()
        user = ctx.message.author.mention
        await ctx.send(f"The queue was cleared by {user}")

    @commands.command(name="queue", aliases=["q"])
    async def view_queue(self, ctx):
        """Print out the queue to the text channel"""
        if len(self.queue) < 1:
            await ctx.send("The queue is empty - nothing to see here!")
        else:
            await ctx.send('\n'.join(["```"] + 
                                     [f"{i+1}\t" + 
                                      song.title for i, song in enumerate(self.queue)] + ["\n```"]))

    @commands.command()
    async def leave(self, ctx):
        """Disconnects the bot from the voice channel"""
        voice_client = ctx.message.guild.voice_client
        user = ctx.message.author.mention
        await voice_client.disconnect()
        await ctx.send(f'Disconnected from {user}')

    @commands.command()
    async def skip(self, ctx):
        voice = get(self.bot.voice_clients, guild=ctx.guild)
        voice.stop()
        await self.start_playing(ctx)
    
    async def start_playing(self, ctx):
        """Start playing the queue"""
        voice_client = ctx.message.guild.voice_client
        while len(self.queue) > 0:
            if not voice_client.is_playing() and not self.paused:
                # Bot currently playing a song
                player = self.queue.pop(0)
                await ctx.send("Now playing a song!")
                voice_client.play(player)
            await asyncio.sleep(1)
    
    @play.before_invoke
    async def ensure_voice(self, ctx):
        """Make sure the bot connected to a voice channel"""
        if ctx.voice_client is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("You are not connected to a voice channel.")
                raise commands.CommandError("Author not connected to a voice channel.")

def setup(client):
    client.add_cog(Music(client))
    
    
if __name__ == '__main__':
    bot = commands.Bot(command_prefix='.')
    setup(bot)
    bot.run(DISCORD_TOKEN)
