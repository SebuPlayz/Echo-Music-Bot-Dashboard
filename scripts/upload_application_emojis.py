"""
Syncs emoji sources to the bot's Discord Application emojis.
Reads emojis.json for the source list, uploads anything new, and
records the results in emojis.uploaded.json.

Each entry in emojis.json can provide EITHER (or both, "source" wins):
  "source": "<:name:1234567890>"   an existing Discord emoji literal —
                                    downloaded straight from Discord's CDN,
                                    no local file needed (same method XEON
                                    uses).
  "file":   "assets/emojis/x.png"  a local image file to upload instead.

If neither is set, the key just keeps using its unicode "fallback".

Usage:
    python3 scripts/upload_application_emojis.py
    python3 scripts/upload_application_emojis.py --force
    python3 scripts/upload_application_emojis.py --dry-run
"""
import argparse
import asyncio
import base64
import json
import mimetypes
import os
import re
import sys
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parent.parent
SOURCE_FILE = ROOT / "emojis.json"
UPLOADED_FILE = ROOT / "emojis.uploaded.json"
API_BASE = "https://discord.com/api/v10"

MIME_OVERRIDES = {".gif": "image/gif", ".png": "image/png", ".jpg": "image/jpeg",
                  ".jpeg": "image/jpeg", ".webp": "image/webp"}

_EMOJI_LITERAL_RE = re.compile(r"^<(a)?:([A-Za-z0-9_]+):(\d+)>$")


def parse_emoji_literal(literal: str) -> dict | None:
    """Parse '<a:name:id>' / '<:name:id>' into {'animated','name','id'}."""
    if not isinstance(literal, str):
        return None
    m = _EMOJI_LITERAL_RE.match(literal.strip())
    if not m:
        return None
    return {"animated": bool(m.group(1)), "name": m.group(2), "id": m.group(3)}


def load_token() -> str:
    token = os.environ.get("BOT_TOKEN") or os.environ.get("DISCORD_TOKEN")
    if token:
        return token
    # Fall back to reading .env directly (mirrors how config.py loads it)
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("BOT_TOKEN=") or line.startswith("DISCORD_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    print("ERROR: no BOT_TOKEN found in the environment or .env", file=sys.stderr)
    sys.exit(1)


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        print(f"WARNING: {path.name} is not valid JSON, treating as empty", file=sys.stderr)
        return {}


def save_json(path: Path, data: dict):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def to_data_uri(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    mime = MIME_OVERRIDES.get(ext) or mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    b64 = base64.b64encode(file_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


async def get_application_id(session: aiohttp.ClientSession) -> str:
    async with session.get(f"{API_BASE}/oauth2/applications/@me") as resp:
        if resp.status != 200:
            body = await resp.text()
            print(f"ERROR: could not resolve application id ({resp.status}): {body}", file=sys.stderr)
            sys.exit(1)
        data = await resp.json()
        return data["id"]


async def get_existing_emojis(session: aiohttp.ClientSession, app_id: str) -> dict:
    """Get all existing application emojis."""
    try:
        async with session.get(f"{API_BASE}/applications/{app_id}/emojis") as resp:
            if resp.status == 200:
                data = await resp.json()
                items = data.get("items", data) if isinstance(data, dict) else data
                return {e["name"].lower(): e for e in items if "name" in e and "id" in e}
    except Exception:
        pass
    return {}


async def download_from_cdn(session: aiohttp.ClientSession, emoji_id: str, animated: bool) -> str | None:
    """Download an existing Discord emoji straight from the CDN and return
    it as a data: URI, ready to hand to the application-emoji upload
    endpoint. This is what lets a key sync with no local file at all —
    same trick XEON's uploader uses."""
    exts = ["gif", "png", "webp"] if animated else ["png", "gif", "webp"]
    for ext in exts:
        url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}"
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    raw = await resp.read()
                    mime = "image/gif" if ext == "gif" else f"image/{ext}"
                    b64 = base64.b64encode(raw).decode("ascii")
                    return f"data:{mime};base64,{b64}"
        except Exception:
            pass
    print(f"  ✖ CDN download failed for {emoji_id} in all formats (gif, png, webp)")
    return None


async def upload_one(session: aiohttp.ClientSession, app_id: str, key: str,
                      name: str, animated: bool, data_uri: str) -> dict | None:
    async with session.post(
        f"{API_BASE}/applications/{app_id}/emojis",
        json={"name": name, "image": data_uri},
    ) as resp:
        if resp.status not in (200, 201):
            body = await resp.text()
            print(f"  ✖ {key}: upload failed ({resp.status}): {body}")
            return None
        data = await resp.json()
        print(f"  ✔ {key}: uploaded as {data['id']} ({'animated' if animated else 'static'})")
        return {"id": data["id"], "name": data["name"], "animated": animated}


async def run_sync(token: str | None = None, force: bool = False, dry_run: bool = False,
                    quiet: bool = False, timeout: float = 15.0) -> dict:
    """Core sync logic, used by the CLI and by main.py's startup hook."""
    def log(*a):
        if not quiet:
            print(*a)

    source = load_json(SOURCE_FILE)
    uploaded = load_json(UPLOADED_FILE)

    to_upload = {}
    skipped_existing = 0
    skipped_missing_asset = 0
    skipped_no_source = 0

    for key, entry in source.items():
        if key.startswith("_") or not isinstance(entry, dict):
            continue
        if not force and key in uploaded:
            skipped_existing += 1
            continue

        # 1. Prefer an existing Discord emoji literal (CDN source) — no
        #    local file needed, mirrors XEON's approach.
        parsed = parse_emoji_literal(entry.get("source"))
        if parsed:
            to_upload[key] = {**entry, "_kind": "cdn", "_parsed": parsed}
            continue

        # 2. Fall back to a local asset file.
        file_field = entry.get("file")
        if file_field:
            file_path = (ROOT / file_field).resolve()
            if file_path.exists():
                to_upload[key] = {**entry, "_kind": "file", "_resolved_file": str(file_path)}
                continue
            skipped_missing_asset += 1
            continue

        # 3. Neither — nothing to upload, key just keeps its fallback.
        skipped_no_source += 1

    summary = {
        "total_source": len(source),
        "skipped_existing": skipped_existing,
        "skipped_missing_asset": skipped_missing_asset,
        "skipped_no_source": skipped_no_source,
        "uploaded": 0,
        "failed": 0,
    }

    if not to_upload:
        log("[emoji-sync] Up to date — nothing new to upload.")
        return summary

    log(f"[emoji-sync] {len(to_upload)} new emoji(s) found, uploading...")

    if dry_run:
        for key, entry in to_upload.items():
            if entry["_kind"] == "cdn":
                log(f"[emoji-sync]  (dry-run) would upload {key} <- CDN source {entry['_parsed']['id']}")
            else:
                log(f"[emoji-sync]  (dry-run) would upload {key} <- {entry['_resolved_file']}")
        return summary

    token = token or load_token()
    headers = {"Authorization": f"Bot {token}"}
    client_timeout = aiohttp.ClientTimeout(total=timeout)
    async with aiohttp.ClientSession(headers=headers, timeout=client_timeout) as session:
        app_id = await get_application_id(session)
        existing_emojis = await get_existing_emojis(session, app_id)
        
        for key, entry in to_upload.items():
            if entry["_kind"] == "cdn":
                parsed = entry["_parsed"]
                name, animated = parsed["name"], parsed["animated"]
            else:
                name, animated = entry["name"], bool(entry.get("animated"))
            
            if name.lower() in existing_emojis:
                existing = existing_emojis[name.lower()]
                log(f"  ✔ {key}: using existing emoji from application with name '{name}'")
                uploaded[key] = {
                    "id": existing["id"],
                    "name": existing["name"],
                    "animated": existing.get("animated", False)
                }
                save_json(UPLOADED_FILE, uploaded)
                summary["uploaded"] += 1
                continue

            if entry["_kind"] == "cdn":
                data_uri = await download_from_cdn(session, parsed["id"], parsed["animated"])
            else:
                data_uri = to_data_uri(Path(entry["_resolved_file"]))

            result = await upload_one(session, app_id, key, name, animated, data_uri) if data_uri else None
            if result:
                uploaded[key] = result
                save_json(UPLOADED_FILE, uploaded)
                summary["uploaded"] += 1
            else:
                summary["failed"] += 1
            await asyncio.sleep(0.5)

    log(f"[emoji-sync] Done — {summary['uploaded']} uploaded, {summary['failed']} failed.")
    return summary


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Re-upload even if already cached")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be uploaded without uploading")
    args = parser.parse_args()

    summary = await run_sync(force=args.force, dry_run=args.dry_run, quiet=False, timeout=120.0)
    print(f"Source entries: {summary['total_source']}")
    print(f"Already uploaded (skipped, no duplicates): {summary['skipped_existing']}")
    print(f"Local asset missing on disk: {summary['skipped_missing_asset']}")
    print(f"No source/file set yet (using unicode fallback): {summary['skipped_no_source']}")


if __name__ == "__main__":
    asyncio.run(main())
