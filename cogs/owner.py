"""
cogs/owner.py — Owner-only bot management commands.
Hidden from the public help menu (see cogs/info.py filtering).
"""

import discord
from discord.ext import commands
from discord import ui
import time
import platform
import psutil
import lavalink

import emojis
from config import Config


def make_text_container(text: str) -> ui.LayoutView:
    view = ui.LayoutView()
    container = ui.Container(accent_colour=None)
    container.add_item(ui.TextDisplay(text))
    view.add_item(container)
    return view


class Owner(commands.Cog, name="Owner"):
    """Owner-only utilities. Hidden from the public help menu."""

    def __init__(self, bot):
        self.bot = bot

    # ── Cog / extension management ─────────────────────────────────

    @commands.command(name="reload", hidden=True)
    @commands.is_owner()
    async def reload_cog(self, ctx, cog: str):
        try:
            await self.bot.reload_extension(f"cogs.{cog}")
            view = make_text_container(f"{emojis.RELOAD} Reloaded `{cog}`.")
        except commands.ExtensionNotLoaded:
            view = make_text_container(f"{emojis.ERROR} `{cog}` isn't loaded.")
        except Exception as e:
            view = make_text_container(f"{emojis.ERROR} Failed to reload `{cog}`:\n```py\n{e}\n```")
        await ctx.reply(view=view)

    @commands.command(name="load", hidden=True)
    @commands.is_owner()
    async def load_cog(self, ctx, cog: str):
        try:
            await self.bot.load_extension(f"cogs.{cog}")
            view = make_text_container(f"{emojis.CHECK_ICO} Loaded `{cog}`.")
        except commands.ExtensionAlreadyLoaded:
            view = make_text_container(f"{emojis.ERROR} `{cog}` is already loaded.")
        except Exception as e:
            view = make_text_container(f"{emojis.ERROR} Failed to load `{cog}`:\n```py\n{e}\n```")
        await ctx.reply(view=view)

    @commands.command(name="unload", hidden=True)
    @commands.is_owner()
    async def unload_cog(self, ctx, cog: str):
        if cog == "owner":
            view = make_text_container(f"{emojis.ERROR} You can't unload the owner cog.")
            return await ctx.reply(view=view)
        try:
            await self.bot.unload_extension(f"cogs.{cog}")
            view = make_text_container(f"{emojis.CHECK_ICO} Unloaded `{cog}`.")
        except commands.ExtensionNotLoaded:
            view = make_text_container(f"{emojis.ERROR} `{cog}` isn't loaded.")
        await ctx.reply(view=view)

    @commands.command(name="sync", hidden=True)
    @commands.is_owner()
    async def sync_cmds(self, ctx, scope: str = "guild"):
        view = make_text_container(f"{emojis.LOADING} Syncing...")
        msg = await ctx.reply(view=view)
        try:
            if scope.lower() == "global":
                synced = await self.bot.tree.sync()
                view = make_text_container(f"{emojis.CHECK_ICO} Synced `{len(synced)}` command(s) globally. (Can take up to 1 hour to propagate across all servers).")
            else:
                self.bot.tree.copy_global_to(guild=ctx.guild)
                synced = await self.bot.tree.sync(guild=ctx.guild)
                view = make_text_container(f"{emojis.CHECK_ICO} Synced `{len(synced)}` command(s) to this server instantly!")
        except Exception as e:
            view = make_text_container(f"{emojis.ERROR} Sync failed:\n```py\n{e}\n```")
        await msg.edit(view=view)

    # ── Bot control ──────────────────────────────────────────────

    @commands.command(name="shutdown", aliases=["die", "poweroff"], hidden=True)
    @commands.is_owner()
    async def shutdown(self, ctx):
        view = make_text_container(f"{emojis.SHUTDOWN} Shutting down...")
        await ctx.reply(view=view)
        await self.bot.close()

    @commands.command(name="setstatus", hidden=True)
    @commands.is_owner()
    async def setstatus(self, ctx, status: str):
        status_map = {
            "online": discord.Status.online,
            "idle": discord.Status.idle,
            "dnd": discord.Status.dnd,
            "invisible": discord.Status.invisible,
        }
        s = status_map.get(status.lower())
        if not s:
            view = make_text_container(f"{emojis.ERROR} Invalid status. Use: online, idle, dnd, invisible.")
            return await ctx.reply(view=view)
        await self.bot.change_presence(status=s)
        view = make_text_container(f"{emojis.CHECK_ICO} Status set to `{status}`.")
        await ctx.reply(view=view)

    @commands.command(name="setactivity", hidden=True)
    @commands.is_owner()
    async def setactivity(self, ctx, *, text: str):
        await self.bot.change_presence(
            activity=discord.Activity(type=discord.ActivityType.listening, name=text)
        )
        view = make_text_container(f"{emojis.CHECK_ICO} Activity set to `{text}`.")
        await ctx.reply(view=view)

    # ── Diagnostics ──────────────────────────────────────────────

    @commands.command(name="eval", aliases=["ev"], hidden=True)
    @commands.is_owner()
    async def eval_cmd(self, ctx, *, code: str):
        code = code.strip("`")
        if code.startswith("py"):
            code = code[2:].strip()

        env = {
            "bot": self.bot,
            "ctx": ctx,
            "discord": discord,
            "lavalink": lavalink,  # <-- wavelink hatake lavalink paya
        }
        try:
            result = eval(code, env)
            if hasattr(result, "__await__"):
                result = await result
            view = make_text_container(f"{emojis.CHECK_ICO} ```py\n{result}\n```")
        except Exception as e:
            view = make_text_container(f"{emojis.ERROR} ```py\n{type(e).__name__}: {e}\n```")
        await ctx.reply(view=view)

    @commands.command(name="nodeinfo", hidden=True)
    @commands.is_owner()
    async def nodeinfo(self, ctx):
        # lavalink.py vich client through nodes mildiyan ne
        lavalink_client = self.bot.lavalink

        if not lavalink_client or not lavalink_client.node_manager.nodes:
            view = make_text_container(f"{emojis.ERROR} No Lavalink nodes configured.")
            return await ctx.reply(view=view)

        lines = []
        for node in lavalink_client.node_manager.nodes:
            # Node available hai ke nahi check karo
            status = "Connected" if node.available else "Disconnected"
            # Kitne players chalde ne os node te
            player_count = len(node.players) if hasattr(node, "players") else node.stats.playing_players if node.stats else "?"

            # Node da name/region
            name = node.name or node.host
            lines.append(
                f"{emojis.DOT} **{name}** — `{status}` "
                f"({player_count} player(s))"
            )

        text = f"### {emojis.INFO} Lavalink Nodes\n" + "\n".join(lines)
        await ctx.reply(view=make_text_container(text))

    @commands.command(name="sysinfo", hidden=True)
    @commands.is_owner()
    async def sysinfo(self, ctx):
        uptime = int(time.time() - self.bot.start_time)
        h, rem = divmod(uptime, 3600)
        m, s = divmod(rem, 60)

        process = psutil.Process()
        mem = process.memory_info().rss / 1024 / 1024

        text = (
            f"### {emojis.RAM} System Info\n"
            f"{emojis.DOT} **Python:** `{platform.python_version()}`\n"
            f"{emojis.DOT} **discord.py:** `{discord.__version__}`\n"
            f"{emojis.DOT} **Lavalink.py:** `{lavalink.__version__}`\n"  # <-- wavelink hatake lavalink
            f"{emojis.DOT} **CPU:** `{psutil.cpu_percent()}%`\n"
            f"{emojis.DOT} **Memory:** `{mem:.1f} MB`\n"
            f"{emojis.DOT} **Uptime:** `{h}h {m}m {s}s`\n"
            f"{emojis.DOT} **Guilds:** `{len(self.bot.guilds)}`\n"
            f"{emojis.DOT} **Users:** `{sum(g.member_count or 0 for g in self.bot.guilds)}`"
        )
        await ctx.reply(view=make_text_container(text))

    @commands.command(name="dm", hidden=True)
    @commands.is_owner()
    async def dm_user(self, ctx, user: discord.User, *, message: str):
        try:
            await user.send(view=make_text_container(message))
            view = make_text_container(f"{emojis.CHECK_ICO} Sent DM to {user.mention}.")
        except discord.Forbidden:
            view = make_text_container(f"{emojis.ERROR} Couldn't DM {user.mention} (DMs closed).")
        except Exception as e:
            view = make_text_container(f"{emojis.ERROR} Failed: `{e}`")
        await ctx.reply(view=view)

    @commands.command(name="guilds", aliases=["servers"], hidden=True)
    @commands.is_owner()
    async def guilds_list(self, ctx):
        lines = []
        for g in sorted(self.bot.guilds, key=lambda x: x.member_count or 0, reverse=True)[:25]:
            lines.append(f"{emojis.DOT} **{g.name}** — `{g.member_count}` members (`{g.id}`)")

        text = f"### {emojis.INFO} Guilds ({len(self.bot.guilds)})\n" + "\n".join(lines)
        await ctx.reply(view=make_text_container(text))

    @commands.command(name="leaveguild", hidden=True)
    @commands.is_owner()
    async def leave_guild(self, ctx, guild_id: int):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            view = make_text_container(f"{emojis.ERROR} I'm not in a guild with that ID.")
            return await ctx.reply(view=view)
        name = guild.name
        await guild.leave()
        view = make_text_container(f"{emojis.CHECK_ICO} Left `{name}`.")
        await ctx.reply(view=view)


async def setup(bot):
    await bot.add_cog(Owner(bot))