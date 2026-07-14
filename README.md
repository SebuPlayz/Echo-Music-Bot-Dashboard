# ❤️ Credits

> ## Original Project by **R3novadcl**

This project is based on the original Discord Music Bot created by **R3novadcl**.

I did **not** create this bot from scratch. I have customized and improved the project by adding new features, improving the web dashboard, fixing bugs, redesigning parts of the interface, and making various enhancements.

**All credit for the original source code belongs to R3novadcl.**

Thank you for creating this amazing project! ❤️

---

# 🎵 Echo Music Bot + Web Dashboard

A powerful and modern **Discord Music Bot** with a beautiful **Web Dashboard**. Easily manage your bot, playlists, and server with an easy-to-use interface.

---

# ✨ Features

## 🎵 Music Bot Features

- High Quality Audio Playback
- Slash Commands
- Spotify Support
- SoundCloud Support
- YouTube Playback
- Queue System
- Autoplay
- Loop Songs
- Shuffle Queue
- Pause / Resume
- Skip Songs
- Volume Control
- 24/7 Music Mode
- Playlist Support
- Fast & Stable Performance

---

# 🌐 Dashboard Features

- 🏠 Beautiful Home Page
- 📊 Dashboard Statistics
- 👤 Discord OAuth2 Login
- 🎵 Create Unlimited Playlists
- ✏️ Edit Playlists
- ❌ Delete Playlists
- 🏆 Playlist Leaderboard
- 📈 Top Ranked Playlists
- 🔍 Search Public Playlists
- 📱 Mobile Friendly
- ⚡ Fast & Responsive Dashboard
- 🌙 Modern UI Design

---

# 📂 Installation

## Clone Repository

```bash
git clone https://github.com/SebuPlayz/Echo-Music-Bot-Dashboard.git
cd Echo-Music-Bot-Dashboard
```

---

## Install Dependencies

```bash
pip install -r requirements.txt
```

---

# ⚙️ Configuration

## Step 1 — Edit `.env`

Open the `.env` file.

Replace

```env
BOT_TOKEN=YOUR_BOT_TOKEN
```

with your Discord Bot Token.

Then configure the remaining values.

```env
DISCORD_CLIENT_ID=
DISCORD_CLIENT_SECRET=
DASHBOARD_REDIRECT_URI=
DASHBOARD_SESSION_SECRET=
DASHBOARD_PORT=2076
DASHBOARD_ENABLED=true
```

---

## Step 2 — Edit `config.py`

Open

```python
config.py
```

Replace

```python
OWNER_ID = YOUR_DISCORD_ID
```

with your own Discord User ID.

---

# 🌐 Dashboard Login Setup

To enable Dashboard Login, open the Discord Developer Portal.

https://discord.com/developers/applications

Select your application.

Go to

```
OAuth2
```

Copy

- Client ID
- Client Secret

Paste them inside your `.env` file.

---

# 🔗 Redirect URI

Don't forget to add your Redirect URI inside the Discord Developer Portal.

Example

```
http://localhost:2076/auth/callback
```

or

```
https://yourdomain.com/auth/callback
```

⚠️ The Redirect URI inside your `.env` file **must exactly match** the Redirect URI added in the Discord Developer Portal.

Otherwise Dashboard Login will not work.

---

# 📁 Files You Must Edit

Before running the bot, edit these files.

```
.env
config.py
```

---

# 🚀 Start The Bot

```bash
python main.py
```

or

```bash
python bot.py
```

depending on your project.

---

# 📸 Screenshots

You can add screenshots of your Dashboard here.

```
images/home.png
images/dashboard.png
images/leaderboard.png
images/playlists.png
```

---

# ⭐ Support

If you like this project, please consider supporting it by:

⭐ Starring this repository

🍴 Forking this repository

💖 Sharing it with your friends

---

# 📜 License

Please respect the work of the original developer.

If you modify or redistribute this project, kindly keep the original credits to **R3novadcl**.

---

# 👨‍💻 Maintained & Customized By

## 🎵 Echo Music

GitHub Repository

https://github.com/SebuPlayz/Echo-Music-Bot-Dashboard

Made with ❤️ by **Echo Music**
