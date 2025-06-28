import os
import json
import asyncio
import logging
from typing import cast, Mapping, Optional

import discord
from discord.ext import commands

import wavelink

import yt_dlp


class BotHelp(commands.HelpCommand):
    def __init__(self):
        super().__init__(show_hidden=False, command_attrs={"brief": "ヘルプを表示"})

    async def send_bot_help(self, mapping: Mapping[Optional[commands.Cog], list[commands.Command]]) -> None:
        """引数なしでヘルプコマンドを実行したときに表示されるヘルプメッセージ ($helpみたいな)

        Parameters
        ----------
        mapping : Mapping[Optional[commands.Cog], list[commands.Command]]
            ヘルプのためにユーザーから要求されたコマンドへのコグのマッピング。
            マッピングのキーはコマンドが属する Cog です。値がない場合は None になり、そのコグに属するコマンドのリストになります。
        """
        embed = discord.Embed(title="ヘルプ", description="コマンドの使い方")

        embed.set_author(name=bot.user.display_name, icon_url=bot.user.display_avatar)

        cmds = mapping[None] # コマンドのリストを取得 (Cogを使わないのでNoneを指定)

        for command in (await self.filter_commands(cmds)): # 隠しコマンドを除外
            aliases = command.aliases
            aliases.insert(0, command.name)
            embed.add_field(name=" / ".join(aliases), value=f'> {command.brief}', inline=False)

        await self.get_destination().send(embed=embed) # ヘルプメッセージを送信


class Bot(commands.Bot):
    def __init__(self) -> None:
        intents: discord.Intents = discord.Intents.default()
        intents.message_content = True

        discord.utils.setup_logging(level=logging.INFO)
        super().__init__(command_prefix="!", intents=intents, case_insensitive=True, help_command=BotHelp())

    async def setup_hook(self) -> None:
        nodes = [wavelink.Node(uri="http://lavalink:2333", password="youshallnotpass")]

        # cache_capacity is EXPERIMENTAL. Turn it off by passing None
        await wavelink.Pool.connect(nodes=nodes, client=self, cache_capacity=100)

    async def on_ready(self) -> None:
        logging.info("Logged in: %s | %s", self.user, self.user.id)

    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload) -> None:
        logging.info("Wavelink Node connected: %r | Resumed: %s", payload.node, payload.resumed)

    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload) -> None:
        player: wavelink.Player | None = payload.player
        if not player:
            # Handle edge cases...
            return

        original: wavelink.Playable | None = payload.original
        track: wavelink.Playable = payload.track

        embed: discord.Embed = discord.Embed(title="再生中…", color=0xff0000)
        embed.description = f"**{track.title}**"

        if track.artwork:
            embed.set_thumbnail(url=track.artwork)

        if track.album.name:
            embed.add_field(name="Album", value=track.album.name)

        embed.set_footer(text=f"{track.author}", icon_url=track.artist.artwork)

        await player.home.send(embed=embed)


bot: Bot = Bot()


@bot.command(aliases=["p"], brief="指定されたURLの内容、添付された動画や音声を再生します。")
async def play(ctx: commands.Context, *, query: str = None) -> None:
    if not ctx.guild:
        return

    player: wavelink.Player
    player = cast(wavelink.Player, ctx.voice_client)  # type: ignore

    await ctx.typing()

    # queryに何も渡されていなかった場合
    if query is not None:
        pass
    elif query is None and ctx.message.attachments:
        query: list = ctx.message.attachments
    else:
        await ctx.send("URLを入力するか、動画か音声を添付してください。")
        return

    if not player:
        try:
            player = await ctx.author.voice.channel.connect(cls=wavelink.Player)  # type: ignore
        except AttributeError:
            await ctx.send("ボイスチャンネルに参加してから実行してください。")
            return
        except discord.ClientException:
            await ctx.send("ボイスチャンネルに参加できませんでした。もう一度お試しください。")
            return

    # Turn on AutoPlay to enabled mode.
    # enabled = AutoPlay will play songs for us and fetch recommendations...
    # partial = AutoPlay will play songs for us, but WILL NOT fetch recommendations...
    # disabled = AutoPlay will do nothing...
    player.autoplay = wavelink.AutoPlayMode.partial

    # Lock the player to this channel...
    if not hasattr(player, "home"):
        player.home = ctx.channel
    elif player.home != ctx.channel:
        await ctx.send(f"別チャンネルでbotが動いているようです。コマンドは{player.home.mention}で実行してください。")
        return

    # This will handle fetching Tracks and Playlists...
    # Seed the doc strings for more information on this method...
    # If spotify is enabled via LavaSrc, this will automatically fetch Spotify tracks if you pass a URL...
    # Defaults to YouTube for non URL based queries...
    if isinstance(query, list):
        tracks: list = []
        for attachment in query:
            tracks.append(await wavelink.Playable.search(attachment.url))
    else:
        try:
            tracks: wavelink.Search = await wavelink.Playable.search(query)
        except wavelink.LavalinkLoadException:
            tracks = None

    if not tracks:
        ydl_opts = {
            "quiet":    True,
            "simulate": True,
            "forceurl": True,
            "format": "ba*",
            "outtmpl": "temp_audio.%(ext)s",
            "paths": {
                'home': "/tmp"
            }
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            if "entries" in info:
                query = info["entries"][0]["url"]
            else:
                query = info["url"]
            try:
                tracks: wavelink.Search = await wavelink.Playable.search(query)
            except:
                await ctx.send("曲が再生できませんでした。もう一度お試しください。")
                return

    if isinstance(query, list):
        added: int = 0
        for track in tracks:
            await player.queue.put_wait(track)
            added += 1
        await ctx.send(f"添付ファイル({added}個)をキューに追加しました。")
    elif isinstance(tracks, wavelink.Playlist):
        # tracks is a playlist...
        added: int = await player.queue.put_wait(tracks)
        await ctx.send(f"**{tracks.name}**({added}曲)をキューに追加しました。")
    else:
        track: wavelink.Playable = tracks[0]
        await player.queue.put_wait(track)
        await ctx.send(f"**{track}**をキューに追加しました。")

    if not player.playing:
        # Play now since we aren't playing anything...
        await player.play(player.queue.get(), volume=30)


@bot.command(brief="再生中の曲を無条件でスキップします。")
async def skip(ctx: commands.Context) -> None:
    player: wavelink.Player = cast(wavelink.Player, ctx.voice_client)
    if not player:
        return

    await player.skip(force=True)
    await ctx.message.add_reaction("\u2705")


@bot.command(name="toggle", aliases=["stop", "pause", "resume"], brief="現在の状態に応じて一時停止または再生します。")
async def pause_resume(ctx: commands.Context) -> None:
    player: wavelink.Player = cast(wavelink.Player, ctx.voice_client)
    if not player:
        return

    await player.pause(not player.paused)
    await ctx.message.add_reaction("\u2705")


@bot.command(brief="音量を変更します。")
async def volume(ctx: commands.Context, value: int) -> None:
    player: wavelink.Player = cast(wavelink.Player, ctx.voice_client)
    if not player:
        return

    await player.set_volume(value)
    await ctx.message.add_reaction("\u2705")


@bot.command(aliases=["dc", "exit", "quit"], brief="このbotをボイスチャンネルから退出させます。")
async def disconnect(ctx: commands.Context) -> None:
    player: wavelink.Player = cast(wavelink.Player, ctx.voice_client)
    if not player:
        return

    await player.disconnect()
    await ctx.message.add_reaction("\u2705")


@bot.command(brief="Ping値・応答速度を返します。")
async def ping(ctx: commands.Context) -> None:
    message = await ctx.send("Pong!")
    ping = round(bot.latency * 1000)
    await message.edit(content=f"Pong! (応答速度は**{ping}**msくらいでした。)")


@bot.command(aliases=["info"], brief="Botの情報を表示します。")
async def botinfo(ctx: commands.Context) -> None:
    embed: discord.Embed = discord.Embed(title="このBotについて", description="YouTube, Spotify, Apple Music, Twitch, Soundcloud, Bandcamp, Vimeoおよび添付ファイルが再生できる非公開の音楽Botです。\n自己ホストであるため、停止や不安定などが起こる可能性があります。\n\nこのBotは以下のプロジェクトおよびライブラリを使用しています。")
    embed.set_author(name=bot.user.name, icon_url=bot.user.display_avatar)
    embed.add_field(name="discord.py", value="https://discordpy.readthedocs.io/ja/latest/")
    embed.add_field(name="Lavalink", value="https://lavalink.dev/")
    embed.add_field(name="youtube-source", value="https://github.com/lavalink-devs/youtube-source")
    embed.add_field(name="LavaSrc", value="https://github.com/topi314/LavaSrc")
    embed.add_field(name="Wavelink", value="https://wavelink.dev/en/latest/")
    embed.add_field(name="yt-dlp", value="https://github.com/yt-dlp/yt-dlp")
    if os.getenv("OWNER_ID"):
        owner: discord.User = await bot.fetch_user(os.getenv("OWNER_ID"))
        embed.set_footer(text=f"hosted by {owner.name}", icon_url=owner.display_avatar)
    await ctx.send(embed=embed)


@bot.event
async def on_voice_state_update(member, before, after):
    # ユーザーが特定のギルドのボイスチャンネルに出入りした場合に反応
    if before.channel != after.channel:
        if before.channel is not None:  # ユーザーが退出した場合
            voice_channel = before.channel
            # チャンネルに残っているのがBotのみの場合
            if len(voice_channel.members) == 1 and voice_channel.members[0].id == bot.user.id:
                # Botを退出させる
                voice_client = discord.utils.get(bot.voice_clients, guild=voice_channel.guild)
                await voice_client.disconnect()


async def main() -> None:
    try:
        async with bot:
            await bot.start(os.getenv("API_KEY"))
    except KeyboardInterrupt:
        logging.info("終了しました。")


asyncio.run(main())
