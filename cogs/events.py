import discord
from discord.ext import commands
from discord import ui
from config import Config
import emojis


def make_text_container(text: str) -> ui.LayoutView:
    view = ui.LayoutView()
    container = ui.Container(accent_colour=None)
    container.add_item(ui.TextDisplay(text))
    view.add_item(container)
    return view


class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        if self.bot.user.mentioned_in(message) and not message.mention_everyone:
            if message.content.strip() in (f"<@{self.bot.user.id}>", f"<@!{self.bot.user.id}>"):
                prefix = await self.bot.db.get_prefix(message.guild.id) or Config.DEFAULT_PREFIX
                text = (
                    f"### Hey {message.author.mention}!\n"
                    f"{emojis.DOT} My prefix is `{prefix}`\n"
                    f"{emojis.DOT} Type `{prefix}help` for commands."
                )
                view = make_text_container(text)
                await message.reply(view=view)

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingPermissions):
            perms = ", ".join(f"`{p}`" for p in error.missing_permissions)
            view = make_text_container(f"{emojis.ERROR} You need {perms} permission(s).")
            return await ctx.reply(view=view)
        if isinstance(error, commands.BotMissingPermissions):
            perms = ", ".join(f"`{p}`" for p in error.missing_permissions)
            view = make_text_container(f"{emojis.ERROR} I need {perms} permission(s).")
            return await ctx.reply(view=view)
        if isinstance(error, commands.MissingRequiredArgument):
            text = (
                f"{emojis.ERROR} Missing argument: `{error.param.name}`\n"
                f"Usage: `>{ctx.command.qualified_name} {ctx.command.signature}`"
            )
            view = make_text_container(text)
            return await ctx.reply(view=view)
        if isinstance(error, commands.CommandOnCooldown):
            view = make_text_container(f"Slow down! Try again in `{error.retry_after:.1f}s`.")
            return await ctx.reply(view=view)
        if isinstance(error, commands.NotOwner):
            view = make_text_container(f"{emojis.ERROR} Owner-only command.")
            return await ctx.reply(view=view)

        view = make_text_container(f"{emojis.ERROR} An error occurred:\n```py\n{str(error)[:500]}\n```")
        await ctx.reply(view=view)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        try:
            self.bot.tree.copy_global_to(guild=guild)
            await self.bot.tree.sync(guild=guild)
            print(f"[GuildJoin] Automatically synced commands to '{guild.name}' ({guild.id}) instantly.")
        except Exception as e:
            print(f"[GuildJoin] Failed to sync commands to '{guild.name}': {e}")


async def setup(bot):
    await bot.add_cog(Events(bot))