import discord
from discord.ext import commands
import asyncio
import time
from config import Config
from utils.database import Database


class EchoBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(
            command_prefix=self._get_prefix,
            intents=intents,
            help_command=None,
            owner_ids=set(Config.OWNER_IDS),
            case_insensitive=True,
            strip_after_prefix=True
        )
        self.db = Database()
        self.start_time = time.time()
        self.dashboard_broadcast = None  # gets set when dashboard boots
        self.dashboard_task = None

    async def _get_prefix(self, bot, message):
        if not message.guild:
            return commands.when_mentioned_or(Config.DEFAULT_PREFIX)(bot, message)
        prefix = await self.db.get_prefix(message.guild.id)
        base = prefix or Config.DEFAULT_PREFIX
        return commands.when_mentioned_or(base)(bot, message)

    async def setup_hook(self):
        await self.db.init()

        await self._autoload_emojis()
        await self._autoload_cogs()

        # dashboard shares the bot's event loop + db, no separate connection needed
        if Config.DASHBOARD_ENABLED:
            from dashboard.app import run_dashboard
            self.dashboard_task = self.loop.create_task(run_dashboard(self), name="dashboard")

            def _on_dashboard_done(task: asyncio.Task):
                if task.cancelled():
                    return
                exc = task.exception()
                if exc is not None:
                    print(f"  ⚠ Dashboard task ended with an error: {exc!r}")

            self.dashboard_task.add_done_callback(_on_dashboard_done)

    async def close(self):
        # cancel the dashboard task cleanly so uvicorn shuts down properly
        # instead of getting killed mid-request on restart
        if self.dashboard_task and not self.dashboard_task.done():
            self.dashboard_task.cancel()
            try:
                await self.dashboard_task
            except asyncio.CancelledError:
                pass
        await super().close()

    async def _autoload_emojis(self):
        # syncs emoji before cogs load since cogs need emojis.X at import time.
        # wrapped in a timeout so a slow network never blocks the bot from booting
        try:
            from scripts.upload_application_emojis import run_sync
            summary = await asyncio.wait_for(
                run_sync(token=Config.TOKEN, quiet=True, timeout=60.0),
                timeout=70.0,
            )
            if summary.get("uploaded"):
                import emojis
                emojis.reload()
                print(f"  [OK] Emoji sync: uploaded {summary['uploaded']} new emoji(s)")
            else:
                print(f"  [OK] Emoji sync: up to date ({summary.get('skipped_existing', 0)} cached)")
        except Exception as e:
            print(f"  [WARN] Emoji sync skipped ({e}) - using cached/fallback emojis")

    async def _autoload_cogs(self):
        # auto-discovers cogs so we don't need a hardcoded list here
        import pkgutil
        import cogs as cogs_pkg

        cog_names = sorted(
            name for _, name, is_pkg in pkgutil.iter_modules(cogs_pkg.__path__)
            if not is_pkg and not name.startswith("_")
        )

        for cog in cog_names:
            try:
                await self.load_extension(f"cogs.{cog}")
                print(f"  ✔ Loaded: {cog}")
            except Exception as e:
                print(f"  ✖ Failed: {cog} -> {e}")

    async def on_ready(self):
        print(f"\n{'='*50}")
        print(f"  🌹 {self.user.name} is online")
        print(f"  Servers: {len(self.guilds)}")
        print(f"  Users: {sum(g.member_count for g in self.guilds)}")
        print(f"{'='*50}\n")

        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name=f"{Config.DEFAULT_PREFIX}help"
            ),
            status=discord.Status.dnd
        )


async def main():
    bot = EchoBot()
    async with bot:
        await bot.start(Config.TOKEN)


if __name__ == "__main__":
    asyncio.run(main())