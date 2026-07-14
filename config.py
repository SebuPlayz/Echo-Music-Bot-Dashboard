import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    TOKEN = os.getenv("BOT_TOKEN")
    DEFAULT_PREFIX = ">"
    OWNER_IDS = [1354490199140470784] 

    # ── Public Lavalink Nodes ──
    LAVALINK_NODES = [
        {
            "host": "de1.aspirehosting.in",
            "port": 3008,
            "password": "ansh4real",
            "region": "us",
            "name": "aspirehosting",
            "ssl": False,
        },
        {
            "host": "lavalink.devamop.in",
            "port": 443,
            "password": "DevamOP",
            "region": "us",
            "name": "devamop",
            "ssl": True,
        },
        {
            "host": "lavalink.clxud.dev",
            "port": 443,
            "password": "clxud",
            "region": "us",
            "name": "clxud",
            "ssl": True,
        },
        {
            "host": "lavalinkv4.serenetia.com",
            "port": 443,
            "password": "https://dsc.gg/ajidevserver",
            "region": "us",
            "name": "serenetia",
            "ssl": True,
        },
    ]

    # ── Accent Color: None (Components V2) ──
    ACCENT_COLOR = None

    # ── Bot Info ──
    BOT_NAME = "Echo"
    SUPPORT_SERVER = "https://discord.gg/yourserver"
    WEBSITE = None

    # ── Dashboard ──
    DASHBOARD_ENABLED = os.getenv("DASHBOARD_ENABLED", "true").lower() == "true"