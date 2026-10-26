"""'Apri Spotify', 'apri youtube.com', 'open Notes': Aether opens apps and sites on this Mac right away.

Opening something changes no data, so it needs no confirmation (like asking Spotlight). Only installed apps are matched, only
http(s) addresses are opened, and the name never reaches a shell: `open -a <path>` / `open <url>` with an argument list.
"""
from __future__ import annotations

import difflib
import re
import shutil
import subprocess
import sys
from pathlib import Path

_APP_DIRS = ("/Applications", "/System/Applications", "/System/Applications/Utilities", "/Applications/Utilities", str(Path.home() / "Applications"))
_OPEN_RE = re.compile(r"^\s*(?:aether[,\s]+)?(?:per\s+favore\s+)?(?:apri(?:mi)?|lancia|avvia|fai\s+partire|open|launch|start)\s+(?:l'app\s+|l'applicazione\s+|app\s+|the\s+app\s+)?"
                      r"(?P<name>[\w .&+'-]{2,60}?)\s*(?:per\s+favore|please)?[\s.!?]*$", re.IGNORECASE)
_DOMAIN_RE = re.compile(r"^(?:https?://)?(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}(?:/\S*)?$", re.IGNORECASE)
# what people say for sites they do not type as a domain
_SITES = {"youtube": "https://www.youtube.com", "gmail": "https://mail.google.com", "google": "https://www.google.com",
          "google calendar": "https://calendar.google.com", "calendar google": "https://calendar.google.com", "github": "https://github.com",
          "netflix": "https://www.netflix.com", "instagram": "https://www.instagram.com", "linkedin": "https://www.linkedin.com",
          "chatgpt": "https://chatgpt.com", "drive": "https://drive.google.com", "google drive": "https://drive.google.com"}
# Italian names of built-in apps
_ALIASES = {"note": "Notes", "promemoria": "Reminders", "calendario": "Calendar", "mappe": "Maps", "foto": "Photos", "musica": "Music",
            "impostazioni": "System Settings", "impostazioni di sistema": "System Settings", "calcolatrice": "Calculator",
            "terminale": "Terminal", "messaggi": "Messages", "posta": "Mail", "contatti": "Contacts", "anteprima": "Preview",
            "app store": "App Store", "monitoraggio attività": "Activity Monitor", "registratore": "Voice Memos"}


def parse(prompt: str) -> str | None:
    """The thing to open, or None when the message is not a plain 'open X'."""
    m = _OPEN_RE.match(prompt or "")
    if not m:
        return None
    name = m["name"].strip(" .'")
    # "apri una issue", "apri la mail di Mario", "apri il calendario di domani" are other requests
    art = re.match(r"^(?:una?|la|il|lo|le|gli|i|un|a|an|the|my|mio|mia|l')\s*", name, re.IGNORECASE)
    if art and art.group(0).strip():
        rest = name[art.end():].strip()
        return rest if rest.lower() in _ALIASES else None
    return name


def _installed() -> dict[str, str]:
    apps: dict[str, str] = {}
    for d in _APP_DIRS:
        p = Path(d)
        if not p.is_dir():
            continue
        for app in p.glob("*.app"):
            apps.setdefault(app.stem.lower(), str(app))
    return apps


def resolve(name: str, apps: dict[str, str] | None = None) -> tuple[str, str] | None:
    """('app', path) | ('url', url) | None."""
    low = name.lower().strip()
    if low in _SITES:
        return "url", _SITES[low]
    if _DOMAIN_RE.match(low) and " " not in low:
        return "url", low if low.startswith("http") else f"https://{low}"
    apps = _installed() if apps is None else apps
    low = _ALIASES.get(low, low).lower()
    if low in apps:
        return "app", apps[low]
    starts = [k for k in apps if k.startswith(low)]
    if len(starts) == 1:
        return "app", apps[starts[0]]
    close = difflib.get_close_matches(low, list(apps), n=1, cutoff=0.8)
    return ("app", apps[close[0]]) if close else None


def open_target(kind: str, target: str) -> bool:
    opener = shutil.which("open")
    if sys.platform != "darwin" or not opener:
        return False
    if kind == "url" and not target.startswith(("https://", "http://")):
        return False
    cmd = [opener, "-a", target] if kind == "app" else [opener, target]
    try:
        return subprocess.run(cmd, capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def handle(prompt: str, english: bool = False) -> str | None:
    """Opens it and returns what to say, or None when the message is not an 'open X' Aether can do."""
    name = parse(prompt)
    if not name:
        return None
    found = resolve(name)
    if not found:
        return (f"I can't find an app called “{name}” on this Mac." if english else f"Non trovo un'app che si chiama «{name}» su questo Mac.")
    kind, target = found
    label = Path(target).stem if kind == "app" else re.sub(r"^https?://(www\.)?", "", target).rstrip("/")
    if not open_target(kind, target):
        return (f"I couldn't open {label}." if english else f"Non riesco ad aprire {label}.")
    return f"Opening **{label}**." if english else f"Apro **{label}**."
