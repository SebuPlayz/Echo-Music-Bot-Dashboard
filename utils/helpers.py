import emojis


def format_time(ms: int) -> str:
    seconds = ms // 1000
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def progress_bar(position: int, duration: int, length: int = 18) -> str:
    if duration <= 0:
        return "-" * length
    filled = int((position / duration) * length)
    filled = max(0, min(length, filled))
    return "-" * filled + "•" + "-" * (length - filled - 1)


def get_source_emoji(uri: str) -> str:
    if not uri:
        return emojis.MUSIC
    u = uri.lower()
    if "spotify" in u:
        return emojis.SPOTIFY
    elif "apple" in u:
        return emojis.APPLE_MUSIC
    elif "soundcloud" in u:
        return emojis.SOUNDCLOUD
    elif "youtube" in u or "youtu.be" in u:
        return emojis.YOUTUBE
    return emojis.MUSIC


def truncate(text: str, max_len: int = 40) -> str:
    if len(text) > max_len:
        return text[:max_len - 3] + "..."
    return text