# 🎵 Echo Music Bot + Web Dashboard

A modern, feature-rich Discord Music Bot with a powerful Web Dashboard. Manage your server, control music, create playlists, and customize everything from an elegant and easy-to-use interface.

> **Repository:** https://github.com/SebuPlayz/Echo-Music-Bot-Dashboard

---

# ❤️ Credits

## Original Project by **R3novadcl**

This project is based on the original work created by **R3novadcl**.

I did **not** create the original bot from scratch. I have customized, improved, and extended the project by redesigning the dashboard, adding new features, fixing bugs, improving the user experience, and making various enhancements.

**All credit for the original source code belongs to R3novadcl.**

Thank you for creating such an amazing project. ❤️

---

# ✨ Features

## 🎵 Music Features

- High Quality Music Playback
- Slash Commands
- Spotify Support
- SoundCloud Support
- YouTube Support
- Queue System
- Skip, Pause & Resume
- Loop & Shuffle
- Volume Control
- 24/7 Music Mode
- Playlist Support
- Fast & Stable Performance

---

# 🌐 Dashboard Features

The integrated Dashboard makes managing your music easier than ever.

### 🏠 Modern Dashboard

- Beautiful Home Page
- Clean & Responsive UI
- Mobile Friendly Design
- Dashboard Statistics
- Discord OAuth2 Login
- Easy Server Management

---

### 🎵 Advanced Playlist Manager

Manage everything directly from your browser without using Discord commands.

✅ Create Unlimited Playlists

✅ Edit Existing Playlists

✅ Delete Playlists

✅ Rename Playlists

✅ Add Songs to Playlists

✅ Remove Songs from Playlists

✅ View Complete Playlist Details

✅ Search Public Playlists

---

### 🔒 Playlist Privacy

Every playlist can be configured as:

- 🌍 Public Playlist
- 🔒 Private Playlist

Private playlists are only visible to the owner.

Public playlists can be discovered by everyone.

---

### 🔗 Playlist Sharing

One of the best features of Echo Music Dashboard.

Every playlist automatically receives a unique **Share Code**.

Simply share your Playlist Code with friends.

Anyone can import your playlist instantly without manually adding every song.

Sharing playlists has never been easier.

---

### 🏆 Playlist Leaderboard

The Dashboard includes a built-in Playlist Leaderboard where users can discover the most popular playlists.

Features include:

- Top Ranked Playlists
- Most Popular Playlists
- Trending Playlists
- Community Favorites
- Public Playlist Discovery

---

### 📊 Dashboard Statistics

View useful information directly from the Dashboard.

- Total Servers
- Total Users
- Total Playlists
- Public Playlists
- Private Playlists
- Top Playlists
- Dashboard Activity

---

# ⚙️ Installation

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

# 🔧 Configuration

## 1. Edit `.env`

Replace

```env
BOT_TOKEN=YOUR_BOT_TOKEN
```

Then configure

```env
DISCORD_CLIENT_ID=
DISCORD_CLIENT_SECRET=
DASHBOARD_REDIRECT_URI=
DASHBOARD_SESSION_SECRET=
DASHBOARD_PORT=2076
DASHBOARD_ENABLED=true
```

---

## 2. Edit `config.py`

Replace

```python
OWNER_ID = YOUR_DISCORD_ID
```

with your Discord User ID.

---

# 🌐 Dashboard Login Setup

Open

https://discord.com/developers/applications

Select your application.

Navigate to

```
OAuth2
```

Copy your

- Client ID
- Client Secret

Paste them inside your `.env`.

---

# 🔗 Redirect URI

Add the same Redirect URI inside your Discord Developer Portal.

Example

```
http://localhost:2076/auth/callback
```

or

```
https://yourdomain.com/auth/callback
```

⚠️ **The Redirect URI inside the Developer Portal and the `.env` file must be exactly the same.**

Otherwise Dashboard Login will not work.

---

# 📁 Files To Edit

Before running the bot, edit:

```
.env
config.py
```

---

# 🚀 Run

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

You can add screenshots here.

- Home Page
- Dashboard
- Playlist Manager
- Playlist Leaderboard
- Statistics Page
- Login Page

---

# ⭐ Support

If you enjoy this project, please consider:

⭐ Starring this repository

🍴 Forking this repository

💖 Sharing it with your friends

---

# 📜 License

Please respect the work of the original developer.

If you modify or redistribute this project, kindly keep the original credits to **R3novadcl**.

---

# 👨‍💻 Customized & Maintained by Echo Music

GitHub Repository

https://github.com/SebuPlayz/Echo-Music-Bot-Dashboard

Made with ❤️ by **Echo Music**
