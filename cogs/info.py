import discord
from discord.ext import commands
from discord import ui
import time
import platform
import psutil
from config import Config
import emojis


# helpers

def make_text_container(text: str) -> ui.LayoutView:
    view = ui.LayoutView()
    container = ui.Container(accent_colour=None)
    container.add_item(ui.TextDisplay(text))
    view.add_item(container)
    return view


# help menu layout

class HelpCategorySelect(ui.Select):
    def __init__(self, bot, ctx, layout):
        self.bot_ref = bot
        self.ctx = ctx
        self.layout = layout
        options = [
            discord.SelectOption(label="Home", value="home", emoji=emojis.Echo),
            discord.SelectOption(label="Music", value="Music", emoji=emojis.CAT_MUSIC),
            discord.SelectOption(label="Playlist", value="Playlist", emoji=emojis.MYMUSIC),
            discord.SelectOption(label="Config", value="Config", emoji=emojis.CAT_CONFIG),
            discord.SelectOption(label="Information", value="Information", emoji=emojis.CAT_INFO),
            discord.SelectOption(label="Utility", value="Utility", emoji=emojis.CAT_UTILITY),
        ]
        super().__init__(placeholder="Select a category...", options=options)

    async def callback(self, interaction):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Not for you.", ephemeral=True)
        self.layout.current = self.values[0]
        self.layout.rebuild()
        await interaction.response.edit_message(view=self.layout)


class HelpLayout(ui.LayoutView):
    def __init__(self, bot, ctx):
        super().__init__(timeout=120)
        self.bot_ref = bot
        self.ctx = ctx
        self.current = "home"
        self.message = None
        self.rebuild()

    def rebuild(self):
        self.clear_items()
        container = ui.Container(accent_colour=None)

        if self.current == "home":
            self._build_home(container)
        else:
            self._build_category(container, self.current)

        container.add_item(ui.Separator())
        row = ui.ActionRow()
        row.add_item(HelpCategorySelect(self.bot_ref, self.ctx, self))
        container.add_item(row)

        self.add_item(container)

    def _build_home(self, container):
        prefix = Config.DEFAULT_PREFIX
        non_hidden_cmds = [c for c in self.bot_ref.commands if not c.hidden]

        container.add_item(ui.TextDisplay(f"## {emojis.Echo} **{self.bot_ref.user.name} — Help Desk**"))
        container.add_item(ui.TextDisplay(
            f"*Your ultimate companion for high-fidelity music, custom playlists, and server utilities.*\n"
            f"Use the dropdown selector below to explore all commands."
        ))
        container.add_item(ui.Separator())

        stats_text = (
            f"**<:icons_pings:1526457255455621131> SYSTEM STATUS**\n"
            f"↳ **Prefix:** `{prefix}`\n"
            f"↳ **Commands:** `{len(non_hidden_cmds)}` (developer tools hidden)\n"
            f"↳ **Dashboard:** [Manage Server](http://127.0.0.1:2076)"
        )
        container.add_item(ui.TextDisplay(stats_text))
        container.add_item(ui.Separator())

        overview = (
            f"**<:icon_categories:1526459849263812691> MODULE OVERVIEW**\n\n"
            f"{emojis.CAT_MUSIC} **Music Module**\n"
            f"↳ `/play` • `/skip` • `/stop` • `/volume` • `/loop` • `/shuffle` • `/queue` • `/247` • `/join` • `/dc` • ...\n\n"
            f"{emojis.MYMUSIC} **Playlist Module**\n"
            f"↳ `/playlist create` • `/playlist play` • `/playlist list` • `/playlist public` • ...\n\n"
            f"{emojis.CAT_CONFIG} **Configuration**\n"
            f"↳ `/247` • `/setprefix`\n\n"
            f"{emojis.CAT_INFO} **Information**\n"
            f"↳ `/help` • `/ping` • `/stats` • `/invite` • `/support`\n\n"
            f"{emojis.CAT_UTILITY} **Utilities**\n"
            f"↳ `/avatar` • `/banner` • `/serverinfo` • `/userinfo`"
        )
        container.add_item(ui.TextDisplay(overview))

    def _build_category(self, container, category):
        cat_emojis = {
            "Music": emojis.CAT_MUSIC,
            "Playlist": emojis.MYMUSIC,
            "Config": emojis.CAT_CONFIG,
            "Information": emojis.CAT_INFO,
            "Utility": emojis.CAT_UTILITY,
        }
        ce = cat_emojis.get(category, emojis.DOT)
        container.add_item(ui.TextDisplay(f"### {ce} {category} Commands"))
        container.add_item(ui.Separator())

        cmds = [c for c in self.bot_ref.commands if (c.cog_name or "Other") == category and not c.hidden]
        if not cmds:
            container.add_item(ui.TextDisplay("No commands here."))
            return

        desc = ""
        for c in sorted(cmds, key=lambda x: x.name):
            aliases = f" *(aliases: {', '.join(f'`{a}`' for a in c.aliases)})*" if c.aliases else ""
            desc += f"🔹 **`/{c.name}`**{aliases}\n"
            desc += f"  *{c.help or 'No description'}*\n\n"
            
        container.add_item(ui.TextDisplay(desc))
        container.add_item(ui.TextDisplay(f"-# Total {len(cmds)} commands in {category}"))


# stats layout

class StatsSelect(ui.Select):
    def __init__(self, bot, ctx, layout):
        self.bot_ref = bot
        self.ctx = ctx
        self.layout = layout
        options = [
            discord.SelectOption(label="Overview", value="overview", emoji=emojis.Echo),
            discord.SelectOption(label="System", value="system", emoji=emojis.LATENCY),
            discord.SelectOption(label="Lavalink", value="lavalink", emoji=emojis.MUSIC),
        ]
        super().__init__(placeholder="Select stats view...", options=options)

    async def callback(self, interaction):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Not for you.", ephemeral=True)
        self.layout.current = self.values[0]
        self.layout.rebuild()
        await interaction.response.edit_message(view=self.layout)


class StatsLayout(ui.LayoutView):
    def __init__(self, bot, ctx):
        super().__init__(timeout=120)
        self.bot_ref = bot
        self.ctx = ctx
        self.current = "overview"
        self.message = None
        self.rebuild()

    def rebuild(self):
        self.clear_items()
        container = ui.Container(accent_colour=None)

        if self.current == "overview":
            self._overview(container)
        elif self.current == "system":
            self._system(container)
        else:
            self._lavalink(container)

        container.add_item(ui.Separator())
        row = ui.ActionRow()
        row.add_item(StatsSelect(self.bot_ref, self.ctx, self))
        container.add_item(row)

        self.add_item(container)

    def _overview(self, container):
        bot = self.bot_ref
        users = sum(g.member_count for g in bot.guilds)
        channels = sum(1 for _ in bot.get_all_channels())
        uptime = int(time.time() - bot.start_time)
        h, m, s = uptime // 3600, (uptime % 3600) // 60, uptime % 60

        # Safe VC count (works with both discord voice + custom LavalinkVoiceClient)
        vcs = 0
        for vc in bot.voice_clients:
            try:
                connected_attr = getattr(vc, 'is_connected', None)
                if callable(connected_attr):
                    if connected_attr():
                        vcs += 1
                else:
                    # Fallback: just count if voice client exists
                    vcs += 1
            except Exception:
                pass

        container.add_item(ui.TextDisplay(f"### {emojis.Echo} {bot.user.name} Statistics"))
        container.add_item(ui.Separator())

        text = (
            f"```yaml\n"
            f"Username     : {bot.user.name}\n"
            f"Bot ID       : {bot.user.id}\n"
            f"Servers      : {len(bot.guilds)}\n"
            f"Users        : {users}\n"
            f"Channels     : {channels}\n"
            f"Commands     : {len(bot.commands)}\n"
            f"Active VCs   : {vcs}\n"
            f"Shards       : {bot.shard_count or 1}\n"
            f"Uptime       : {h}h {m}m {s}s\n"
            f"Latency      : {round(bot.latency * 1000)}ms\n"
            f"```"
        )
        container.add_item(ui.TextDisplay(text))

    def _system(self, container):
        proc = psutil.Process()
        mem = proc.memory_info()
        cpu = psutil.cpu_percent()
        ram = mem.rss / 1024 / 1024
        total_ram = psutil.virtual_memory().total / 1024 / 1024 / 1024

        container.add_item(ui.TextDisplay(f"### {emojis.LATENCY} System Statistics"))
        container.add_item(ui.Separator())

        text = (
            f"```yaml\n"
            f"OS          : {platform.system()} {platform.release()}\n"
            f"Python      : {platform.python_version()}\n"
            f"discord.py  : {discord.__version__}\n"
            f"CPU Usage   : {cpu}%\n"
            f"RAM Usage   : {ram:.1f} MB\n"
            f"Total RAM   : {total_ram:.1f} GB\n"
            f"CPU Cores   : {psutil.cpu_count()}\n"
            f"Threads     : {proc.num_threads()}\n"
            f"```"
        )
        container.add_item(ui.TextDisplay(text))

    def _lavalink(self, container):
        container.add_item(ui.TextDisplay(f"### {emojis.MUSIC} Lavalink Nodes"))
        container.add_item(ui.Separator())

        # Get music cog's lavalink client
        music_cog = self.bot_ref.get_cog("Music")
        if not music_cog or not music_cog.lavalink:
            container.add_item(ui.TextDisplay("```No lavalink client initialized.```"))
            return

        nodes = music_cog.lavalink.node_manager.nodes
        if not nodes:
            container.add_item(ui.TextDisplay("```No nodes configured.```"))
            return

        text = "```yaml\n"
        for node in nodes:
            try:
                status = "Connected" if node.available else "Disconnected"
            except:
                status = "Unknown"

            players = 0
            try:
                players = len([
                    p for p in music_cog.lavalink.player_manager.players.values()
                    if p.node == node
                ])
            except:
                pass

            text += (
                f"Node        : {node.name}\n"
                f"Status      : {status}\n"
                f"Region      : {node.region}\n"
                f"Players     : {players}\n"
                f"---\n"
            )
        text += "```"
        container.add_item(ui.TextDisplay(text))



class Info(commands.Cog, name="Information"):
    """Information & stats commands."""

    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="help", aliases=["h"])
    async def help_cmd(self, ctx, *, command: str = None):
        """Show help menu or command details."""
        if command:
            cmd = self.bot.get_command(command)
            if not cmd:
                view = make_text_container(f"{emojis.ERROR} No command named `{command}`.")
                return await ctx.reply(view=view)
            aliases = ", ".join(f"`{a}`" for a in cmd.aliases) if cmd.aliases else "`None`"
            text = (
                f"### Command: {cmd.name}\n"
                f"{emojis.DOT} **Category:** `{cmd.cog_name or 'None'}`\n"
                f"{emojis.DOT} **Description:** {cmd.help or 'No description'}\n"
                f"{emojis.DOT} **Aliases:** {aliases}\n"
                f"{emojis.DOT} **Usage:** `>{cmd.qualified_name} {cmd.signature}`"
            )
            view = make_text_container(text)
            return await ctx.reply(view=view)

        layout = HelpLayout(self.bot, ctx)
        msg = await ctx.reply(view=layout)
        layout.message = msg

    @commands.command(name="ping")
    async def ping(self, ctx):
        """Check bot latency."""
        api = round(self.bot.latency * 1000)
        start = time.perf_counter()
        loading = make_text_container(f"{emojis.LOADING} Measuring...")
        msg = await ctx.reply(view=loading)
        end = time.perf_counter()
        mlat = round((end - start) * 1000)

        uptime = int(time.time() - self.bot.start_time)
        h, m, s = uptime // 3600, (uptime % 3600) // 60, uptime % 60

        text = (
            f"### {emojis.SUCCESS} Pong!\n"
            f"```yaml\n"
            f"Message Latency  : {mlat}ms\n"
            f"API Latency      : {api}ms\n"
            f"Uptime           : {h}h {m}m {s}s\n"
            f"Loaded Commands  : {len(self.bot.commands)}\n"
            f"```"
        )
        view = make_text_container(text)
        await msg.edit(view=view)

    @commands.command(name="stats", aliases=["botinfo", "bi"])
    async def stats(self, ctx):
        """Detailed bot statistics."""
        layout = StatsLayout(self.bot, ctx)
        msg = await ctx.reply(view=layout)
        layout.message = msg

    @commands.command(name="invite")
    async def invite(self, ctx):
        """Get bot invite link."""
        url = discord.utils.oauth_url(self.bot.user.id, permissions=discord.Permissions(8))
        layout = ui.LayoutView()
        container = ui.Container(accent_colour=None)
        container.add_item(ui.TextDisplay(f"### {emojis.INFO} Invite {self.bot.user.name} to your server"))
        container.add_item(ui.Separator())
        row = ui.ActionRow()
        row.add_item(ui.Button(label="Invite", url=url, style=discord.ButtonStyle.link))
        if Config.SUPPORT_SERVER:
            row.add_item(ui.Button(label="Support", url=Config.SUPPORT_SERVER, style=discord.ButtonStyle.link))
        container.add_item(row)
        layout.add_item(container)
        await ctx.reply(view=layout)

    @commands.command(name="support")
    async def support(self, ctx):
        """Get support server link."""
        layout = ui.LayoutView()
        container = ui.Container(accent_colour=None)
        container.add_item(ui.TextDisplay("### Need help? Join our support server."))
        container.add_item(ui.Separator())
        row = ui.ActionRow()
        row.add_item(ui.Button(label="Support Server", url=Config.SUPPORT_SERVER, style=discord.ButtonStyle.link))
        container.add_item(row)
        layout.add_item(container)
        await ctx.reply(view=layout)

    @commands.command(name="membercount", aliases=["mc"])
    async def membercount(self, ctx):
        """Show server member count."""
        g = ctx.guild
        bots = sum(1 for m in g.members if m.bot)
        humans = g.member_count - bots
        online = sum(1 for m in g.members if m.status != discord.Status.offline)

        text = (
            f"### Member Count\n"
            f"```yaml\n"
            f"Total Members : {g.member_count}\n"
            f"Humans        : {humans}\n"
            f"Bots          : {bots}\n"
            f"Online        : {online}\n"
            f"```"
        )
        view = make_text_container(text)
        await ctx.reply(view=view)


async def setup(bot):
    await bot.add_cog(Info(bot))