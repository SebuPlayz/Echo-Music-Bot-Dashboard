import aiosqlite
import time
import random
import string


class Database:
    def __init__(self):
        self.path = "Echo.db"

    async def init(self):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS guilds (
                    guild_id INTEGER PRIMARY KEY,
                    prefix TEXT DEFAULT '>',
                    twentyfourseven INTEGER DEFAULT 0
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS liked_songs (
                    user_id INTEGER,
                    track_title TEXT,
                    track_author TEXT,
                    track_uri TEXT,
                    added_at INTEGER
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS noprefix (
                    user_id    INTEGER PRIMARY KEY,
                    added_by   INTEGER NOT NULL,
                    added_at   INTEGER NOT NULL,
                    expires_at INTEGER
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS playlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    code TEXT UNIQUE,
                    is_public INTEGER DEFAULT 0
                )
            """)
            # Safe migration: check column existence via PRAGMA before adding
            cur = await db.execute("PRAGMA table_info(playlists)")
            existing_cols = {row[1] for row in await cur.fetchall()}
            if "code" not in existing_cols:
                await db.execute("ALTER TABLE playlists ADD COLUMN code TEXT")
                await db.commit()
            if "is_public" not in existing_cols:
                await db.execute("ALTER TABLE playlists ADD COLUMN is_public INTEGER DEFAULT 0")
                await db.commit()

            # Safe migration: check guilds columns
            cur = await db.execute("PRAGMA table_info(guilds)")
            existing_guild_cols = {row[1] for row in await cur.fetchall()}
            if "twentyfourseven_channel_id" not in existing_guild_cols:
                await db.execute("ALTER TABLE guilds ADD COLUMN twentyfourseven_channel_id INTEGER")
                await db.commit()

            await db.execute("""
                CREATE TABLE IF NOT EXISTS playlist_tracks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    playlist_id INTEGER NOT NULL,
                    track_title TEXT NOT NULL,
                    track_author TEXT NOT NULL,
                    track_uri TEXT NOT NULL,
                    track_identifier TEXT,
                    added_at INTEGER NOT NULL,
                    FOREIGN KEY (playlist_id) REFERENCES playlists (id) ON DELETE CASCADE
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS playlist_plays (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    playlist_id INTEGER NOT NULL,
                    played_at INTEGER NOT NULL,
                    FOREIGN KEY (playlist_id) REFERENCES playlists (id) ON DELETE CASCADE
                )
            """)
            await db.commit()

    # ── Prefix Methods ───────────────────────────────────────────

    async def get_prefix(self, guild_id):
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT prefix FROM guilds WHERE guild_id = ?", (guild_id,))
            row = await cur.fetchone()
            return row[0] if row else None

    async def set_prefix(self, guild_id, prefix):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO guilds (guild_id, prefix) VALUES (?, ?) "
                "ON CONFLICT(guild_id) DO UPDATE SET prefix = ?",
                (guild_id, prefix, prefix)
            )
            await db.commit()

    # ── 24/7 Methods ─────────────────────────────────────────────

    async def get_247(self, guild_id):
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT twentyfourseven FROM guilds WHERE guild_id = ?", (guild_id,))
            row = await cur.fetchone()
            return bool(row[0]) if row else False

    async def set_247(self, guild_id, value):
        async with aiosqlite.connect(self.path) as db:
            if not value:
                await db.execute(
                    "INSERT INTO guilds (guild_id, twentyfourseven, twentyfourseven_channel_id) VALUES (?, ?, NULL) "
                    "ON CONFLICT(guild_id) DO UPDATE SET twentyfourseven = ?, twentyfourseven_channel_id = NULL",
                    (guild_id, 0, 0)
                )
            else:
                await db.execute(
                    "INSERT INTO guilds (guild_id, twentyfourseven) VALUES (?, ?) "
                    "ON CONFLICT(guild_id) DO UPDATE SET twentyfourseven = ?",
                    (guild_id, 1, 1)
                )
            await db.commit()

    async def set_247_channel(self, guild_id, channel_id):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO guilds (guild_id, twentyfourseven_channel_id) VALUES (?, ?) "
                "ON CONFLICT(guild_id) DO UPDATE SET twentyfourseven_channel_id = ?",
                (guild_id, channel_id, channel_id)
            )
            await db.commit()

    async def get_247_channel(self, guild_id):
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT twentyfourseven_channel_id FROM guilds WHERE guild_id = ?", (guild_id,))
            row = await cur.fetchone()
            return row[0] if row else None

    async def get_all_247_guilds(self):
        """Get list of (guild_id, twentyfourseven_channel_id) for active 24/7 guilds."""
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT guild_id, twentyfourseven_channel_id FROM guilds WHERE twentyfourseven = 1 AND twentyfourseven_channel_id IS NOT NULL")
            return await cur.fetchall()

    # ── Liked Songs Methods ──────────────────────────────────────

    async def like_song(self, user_id, title, author, uri):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO liked_songs VALUES (?, ?, ?, ?, ?)",
                (user_id, title, author, uri, int(time.time()))
            )
            await db.commit()

    async def unlike_song(self, user_id, uri):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "DELETE FROM liked_songs WHERE user_id = ? AND track_uri = ?",
                (user_id, uri)
            )
            await db.commit()

    async def is_liked(self, user_id, uri):
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT 1 FROM liked_songs WHERE user_id = ? AND track_uri = ?",
                (user_id, uri)
            )
            return await cur.fetchone() is not None

    async def get_liked(self, user_id):
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT * FROM liked_songs WHERE user_id = ? ORDER BY added_at DESC",
                (user_id,)
            )
            return await cur.fetchall()

    # ── NoPrefix Methods ─────────────────────────────────────────

    async def add_noprefix(self, user_id: int, added_by: int, expires_at: int = None):
        """Grant noprefix to a user."""
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO noprefix (user_id, added_by, added_at, expires_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    added_by = excluded.added_by,
                    added_at = excluded.added_at,
                    expires_at = excluded.expires_at
                """,
                (user_id, added_by, int(time.time()), expires_at),
            )
            await db.commit()

    async def remove_noprefix(self, user_id: int) -> bool:
        """Remove noprefix from a user. Returns True if it existed."""
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "DELETE FROM noprefix WHERE user_id = ?", (user_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def is_noprefix(self, user_id: int) -> bool:
        """Check whether a user has active (non-expired) noprefix."""
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT expires_at FROM noprefix WHERE user_id = ?", (user_id,)
            )
            row = await cur.fetchone()
            if not row:
                return False
            expires_at = row[0]
            if expires_at is not None and expires_at < int(time.time()):
                # expired, clean it up
                await db.execute(
                    "DELETE FROM noprefix WHERE user_id = ?", (user_id,)
                )
                await db.commit()
                return False
            return True

    async def get_noprefix(self, user_id: int):
        """Return a user's noprefix info as a tuple, or None."""
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT user_id, added_by, added_at, expires_at FROM noprefix WHERE user_id = ?",
                (user_id,),
            )
            return await cur.fetchone()

    async def list_noprefix(self):
        """Return the list of all noprefix users."""
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT user_id, added_by, added_at, expires_at FROM noprefix"
            )
            return await cur.fetchall()

    # ── Playlist Methods ─────────────────────────────────────────

    def _generate_code(self) -> str:
        """Generate a random 8-character alphanumeric playlist code."""
        chars = string.ascii_uppercase + string.digits
        return ''.join(random.choices(chars, k=8))

    async def create_playlist(self, user_id: int, name: str) -> tuple:
        """Create a new playlist and return (id, code)."""
        async with aiosqlite.connect(self.path) as db:
            # Generate a unique code
            for _ in range(10):
                code = self._generate_code()
                cur = await db.execute("SELECT 1 FROM playlists WHERE code = ?", (code,))
                if not await cur.fetchone():
                    break
            cursor = await db.execute(
                "INSERT INTO playlists (user_id, name, created_at, code, is_public) VALUES (?, ?, ?, ?, 0)",
                (user_id, name, int(time.time()), code)
            )
            await db.commit()
            return cursor.lastrowid, code

    async def delete_playlist(self, user_id: int, playlist_id: int) -> bool:
        """Delete a playlist. Returns True if successful."""
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "DELETE FROM playlists WHERE id = ? AND user_id = ?",
                (playlist_id, user_id)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def rename_playlist(self, user_id: int, playlist_id: int, new_name: str) -> bool:
        """Rename a playlist. Returns True if successful."""
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "UPDATE playlists SET name = ? WHERE id = ? AND user_id = ?",
                (new_name, playlist_id, user_id)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def get_playlists(self, user_id: int):
        """Get all playlists for a user, sorted by creation date."""
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                """
                SELECT p.id, p.name, p.created_at, COUNT(t.id) as track_count, p.code, p.is_public
                FROM playlists p
                LEFT JOIN playlist_tracks t ON p.id = t.playlist_id
                WHERE p.user_id = ?
                GROUP BY p.id
                ORDER BY p.created_at DESC
                """,
                (user_id,)
            )
            return await cur.fetchall()

    async def get_playlist(self, user_id: int, playlist_id: int):
        """Get a single playlist entry."""
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT id, name, created_at, code, is_public FROM playlists WHERE id = ? AND user_id = ?",
                (playlist_id, user_id)
            )
            return await cur.fetchone()

    async def get_playlist_by_name(self, user_id: int, name: str):
        """Get a single playlist entry by name (case-insensitive)."""
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT id, name, created_at, code, is_public FROM playlists WHERE user_id = ? AND LOWER(name) = LOWER(?)",
                (user_id, name)
            )
            return await cur.fetchone()

    async def get_playlist_by_code(self, code: str):
        """Get a public playlist by its share code. Returns (id, name, user_id, track_count, is_public)."""
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                """
                SELECT p.id, p.name, p.user_id, COUNT(t.id) as track_count, p.is_public, p.code
                FROM playlists p
                LEFT JOIN playlist_tracks t ON p.id = t.playlist_id
                WHERE p.code = ?
                GROUP BY p.id
                """,
                (code.upper(),)
            )
            return await cur.fetchone()

    async def set_playlist_privacy(self, user_id: int, playlist_id: int, is_public: bool) -> bool:
        """Set playlist privacy. Returns True if updated."""
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "UPDATE playlists SET is_public = ? WHERE id = ? AND user_id = ?",
                (1 if is_public else 0, playlist_id, user_id)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def ensure_playlist_code(self, playlist_id: int) -> str:
        """Ensure a playlist has a code (for old playlists), return the code."""
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT code FROM playlists WHERE id = ?", (playlist_id,))
            row = await cur.fetchone()
            if row and row[0]:
                return row[0]
            # Generate new code
            for _ in range(10):
                code = self._generate_code()
                cur2 = await db.execute("SELECT 1 FROM playlists WHERE code = ?", (code,))
                if not await cur2.fetchone():
                    break
            await db.execute("UPDATE playlists SET code = ? WHERE id = ?", (code, playlist_id))
            await db.commit()
            return code

    async def get_playlist_tracks(self, playlist_id: int):
        """Get all tracks in a playlist, sorted by added date."""
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(
                "SELECT id, track_title, track_author, track_uri, track_identifier, added_at "
                "FROM playlist_tracks WHERE playlist_id = ? ORDER BY added_at ASC",
                (playlist_id,)
            )
            return await cur.fetchall()

    async def add_to_playlist(self, playlist_id: int, title: str, author: str, uri: str, identifier: str = None) -> int:
        """Add a track to a playlist. Returns the track ID."""
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "INSERT INTO playlist_tracks (playlist_id, track_title, track_author, track_uri, track_identifier, added_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (playlist_id, title, author, uri, identifier, int(time.time()))
            )
            await db.commit()
            return cursor.lastrowid

    async def remove_from_playlist(self, playlist_id: int, track_id: int) -> bool:
        """Remove a track from a playlist. Returns True if successful."""
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                "DELETE FROM playlist_tracks WHERE id = ? AND playlist_id = ?",
                (track_id, playlist_id)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def record_playlist_play(self, playlist_id: int):
        """Record a playlist play event with the current timestamp."""
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO playlist_plays (playlist_id, played_at) VALUES (?, ?)",
                (playlist_id, int(time.time()))
            )
            await db.commit()

    async def get_playlist_leaderboard(self, timeframe: str = "all", limit: int = 10):
        """
        Get the most played public playlists.
        timeframe can be 'day', 'week', 'month', or 'all'.
        Returns list of (playlist_id, name, user_id, code, play_count, track_count).
        """
        since = 0
        now = int(time.time())
        if timeframe == "day":
            since = now - (60 * 60 * 24)
        elif timeframe == "week":
            since = now - (60 * 60 * 24 * 7)
        elif timeframe == "month":
            since = now - (60 * 60 * 24 * 30)

        query = """
            SELECT p.id, p.name, p.user_id, p.code, COUNT(DISTINCT pp.id) as play_count, COUNT(DISTINCT pt.id) as track_count
            FROM playlists p
            JOIN playlist_plays pp ON p.id = pp.playlist_id
            LEFT JOIN playlist_tracks pt ON p.id = pt.playlist_id
            WHERE p.is_public = 1
        """
        
        params = []
        if since > 0:
            query += " AND pp.played_at >= ?"
            params.append(since)

        query += """
            GROUP BY p.id
            ORDER BY play_count DESC
            LIMIT ?
        """
        params.append(limit)

        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute(query, tuple(params))
            return await cur.fetchall()