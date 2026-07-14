# ═══════════════════════════════════════════════════
#  Echo Bot Emojis — Replace with custom IDs later
#  Format for custom: "<:name:1234567890>"
# ═══════════════════════════════════════════════════

import json
from pathlib import Path

# ── Status ──
SUCCESS = "<:icon_tick:1526451653761564682>"
ERROR = "<:icon_cross:1526451801514053824>"
INFO = "<:icons_info:1526452071539150851>"
LOADING = "<a:emoji_1076046:1526452343376183336>"

# ── Music ──
MUSIC = "<:music:1526452523739906098>"
PLAYING = "<:music:1526452523739906098>"
HEART = "<:like:1522896545098367128>"

# ── NowPlaying Controller Buttons ──
BTN_PAUSE = "<:pause:1526453178512576592>"
BTN_RESUME = "<:icon_pause:1526453490686361741>"
BTN_SKIP = "<:icon_skip:1526453677353730169>"
BTN_STOP = "<:music_stop:1526453840310697985>"
BTN_LOOP = "<:Icon_Loop:1526453979582824448>"
BTN_AUTOPLAY = "<:auto:1526454110772269090>"

# ── Platform ──
SPOTIFY = "<:Spotify_Primary_Logo_RGB_Green:1526451428854599761>"
YOUTUBE = "<:33615youtube69:1526451219827265700>"
APPLE_MUSIC = "<:apple:1522896449258655785>"
SOUNDCLOUD = "<:volume:1522896520242790461>"

# ── UI ──
DOT = "<:7135graydot:1526450496297238689>"
ARROW = "<a:Arrow_White:1526450912493572267>"

# ── Categories ──
CAT_MUSIC = "<:music:1526452523739906098>"
CAT_CONFIG = "<:Icons_utility:1526454344797519872>"
CAT_INFO = "<:icons_info:1526452071539150851>"
CAT_UTILITY = "<:icon_ignore:1526454670225178634>"

# ── Branding ──
Echo = "<:echologo:1526448906098049064>"

# ── Stats ──
LATENCY = "<:icon_ignore:1526454670225178634>"
UPTIME = "<:music:1526452523739906098>"

# ── Voice Channel Status ──
MYMUSIC = "<a:my_music:1522899608445911141>"
WAITING = "<:icons_info:1526452071539150851>"

# ── NoPrefix / Owner (replace with custom IDs later) ──
CROWN = "<:echo_owner:1526455520603668480>"
DEV = "🛠️"
PLAN = "📋"
CLOCK = "🕒"
USER_ICO = "👤"
LIST_ICO = "📃"
ADD = "➕"
REMOVE = "➖"
CHECK_ICO = "✔️"
GIFT = "🎁"
LOCK = "🔒"
UNLOCK = "🔓"
RELOAD = "🔄"
SHUTDOWN = "⛔"
TERMINAL = "💻"
RAM = "🧠"
DB_ICO = "🗄️"
CAT_OWNER = "🛡️"


def reload():
    uploaded_file = Path(__file__).resolve().parent / "emojis.uploaded.json"
    if uploaded_file.exists():
        try:
            data = json.loads(uploaded_file.read_text())
            g = globals()
            for key, val in data.items():
                emoji_name = val.get("name")
                emoji_id = val.get("id")
                animated = val.get("animated")
                prefix = "a" if animated else ""
                g[key.upper()] = f"<{prefix}:{emoji_name}:{emoji_id}>"
        except Exception:
            pass


reload()