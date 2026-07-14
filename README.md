# 🎵 Echo Music Bot + Web Dashboard

A powerful Discord Music Bot with a beautiful and modern Web Dashboard built for easy server management, playlist management, and high-quality music playback.

---

# ✨ Features

## 🎵 Music Features

- High Quality Music Playback
- Slash Commands
- Autoplay
- Queue System
- Skip, Pause, Resume
- Loop & Shuffle
- Volume Control
- Lyrics Support
- 24/7 Mode
- Spotify Support
- SoundCloud Support
- Playlist Support
- Fast & Stable Playback

---

# 🌐 Dashboard Features

- 🏠 Modern Home Page
- 📊 Dashboard Statistics
- 🎵 Create Unlimited Playlists
- ✏️ Edit & Delete Playlists
- 🏆 Playlist Leaderboard
- 📈 Top Trending Playlists
- 🔍 Search Public Playlists
- 👤 Discord OAuth2 Login
- ⚡ Fast & Responsive Dashboard
- 🌙 Beautiful UI Design
- 📱 Mobile Friendly
- 🎧 Easy Music Management

---

# 📸 Dashboard Preview

> Add your dashboard screenshots here.

---

# ⚙️ Setup Guide

## 1️⃣ Clone Repository

```bash
git clone YOUR_GITHUB_REPOSITORY
cd YOUR_REPOSITORY
```

---

## 2️⃣ Install Packages

```bash
pip install -r requirements.txt
```

---

## 3️⃣ Configure Bot

Open the `.env` file and replace:

```env
BOT_TOKEN=YOUR_BOT_TOKEN
```

with your actual Discord Bot Token.

---

## 4️⃣ Change Owner ID

Open:

```
config.py
```

Replace the Owner ID with your Discord User ID.

Example:

```python
OWNER_ID = YOUR_DISCORD_ID
```

---

## 5️⃣ Configure Dashboard

Fill these values inside your `.env` file.

```env
DISCORD_CLIENT_ID=
DISCORD_CLIENT_SECRET=
DASHBOARD_REDIRECT_URI=
DASHBOARD_SESSION_SECRET=
DASHBOARD_PORT=2076
DASHBOARD_ENABLED=true
```

---

# 🔑 Discord OAuth2 Setup

Open:

https://discord.com/developers/applications

Select your application.

Go to:

```
OAuth2
```

Copy your

- Client ID
- Client Secret

Paste them into your `.env` file.

---

# 🚨 Redirect URI (IMPORTANT)

For Dashboard Login, you MUST add the same Redirect URI inside the Discord Developer Portal.

Example:

```
http://localhost:2076/auth/callback
```

or

```
https://yourdomain.com/auth/callback
```

⚠️ The Redirect URI inside your `.env` file and Discord Developer Portal MUST be exactly the same.

Otherwise Dashboard Login will NOT work.

---

# 📂 Required Files

Before starting the bot, edit these files.

```
.env
config.py
```

---

# 🚀 Start Bot

```bash
python main.py
```

or

```bash
python bot.py
```

(depending on your main file)

---

# ⚠️ Important

❌ Never share your Bot Token.

❌ Never share your Client Secret.

❌ Never upload your configured `.env` file to GitHub.

Keep all credentials private.

---

# ❤️ Support

If you like this project,

⭐ Star this Repository

🍴 Fork this Repository

💖 Share it with your friends.

---

# 👨‍💻 Made with ❤️ by Echo Music
