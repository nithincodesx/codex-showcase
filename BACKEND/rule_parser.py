"""
Rule-Based Voice Parser Module

Implements the Expanded Phase 1 (deterministic regex intent parser) and
Expanded Phase 2 (static template TTS response system) for the desktop AI
voice companion. All parsing is rule-based — no LLM calls required for intent
classification or response generation.

Designed to work alongside the existing computer_use.py automation tools.
"""

import re
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Phase 1: Rule-Based Intent & Entity Parsing
# ---------------------------------------------------------------------------

# Each entry: (compiled_regex, intent, action, param_groups)
# param_groups lists the named capture groups to extract from the match.
_RULES = [
    # --- YouTube Control ---
    (re.compile(r"^play\s+(?P<query>.+?)\s+on\s+youtube$", re.IGNORECASE),
     "YOUTUBE_CONTROL", "youtube_search_and_play", ["query"]),
    (re.compile(r"^open\s+youtube\s+and\s+play\s+(?P<query>.+)$", re.IGNORECASE),
     "YOUTUBE_CONTROL", "youtube_search_and_play", ["query"]),
    (re.compile(r"^youtube\s+play\s+(?P<query>.+)$", re.IGNORECASE),
     "YOUTUBE_CONTROL", "youtube_search_and_play", ["query"]),

    # --- Browser Navigation & Web Search ---
    (re.compile(r"^open\s+browser\s+(?:and\s+)?search\s+(?P<query>.+)$", re.IGNORECASE),
     "BROWSER_NAVIGATION", "browser_search", ["query"]),
    (re.compile(r"^search\s+(?P<query>.+?)\s+on\s+(?:google|browser)$", re.IGNORECASE),
     "BROWSER_NAVIGATION", "browser_search", ["query"]),
    (re.compile(r"^open\s+(?P<site>google|github|reddit|twitter|stackoverflow|chatgpt)\s+(?:and\s+search\s+(?P<query>.+))?$", re.IGNORECASE),
     "BROWSER_NAVIGATION", "open_site_and_search", ["site", "query"]),
    (re.compile(r"^open\s+browser\s+and\s+go\s+to\s+(?P<url>.+)$", re.IGNORECASE),
     "BROWSER_NAVIGATION", "open_url", ["url"]),

    # --- Browser Auto-Click ---
    (re.compile(r"^search\s+(?P<query>.+?)\s+and\s+play\s+(?:it\s+)?inside\s+(?:the\s+)?site$", re.IGNORECASE),
     "BROWSER_AUTO_CLICK", "search_click_first_and_play", ["query"]),
    (re.compile(r"^open\s+browser\s+search\s+(?P<query>.+?)\s+and\s+click\s+first\s+link$", re.IGNORECASE),
     "BROWSER_AUTO_CLICK", "search_and_click_first", ["query"]),

    # --- Spotify Control ---
    (re.compile(r"^play\s+(?P<query>.+?)\s+on\s+spotify$", re.IGNORECASE),
     "SPOTIFY_CONTROL", "spotify_play_track", ["query"]),
    (re.compile(r"^spotify\s+play\s+(?P<query>.+)$", re.IGNORECASE),
     "SPOTIFY_CONTROL", "spotify_play_track", ["query"]),
    (re.compile(r"^play\s+song\s+(?P<query>.+?)\s+on\s+spotify$", re.IGNORECASE),
     "SPOTIFY_CONTROL", "spotify_play_track", ["query"]),

    # --- App Control ---
    (re.compile(r"^(?:open|launch|start)\s+(?P<app_name>chrome|spotify|vscode|terminal|notepad|calculator|discord|steam)$", re.IGNORECASE),
     "APP_CONTROL", "open_app", ["app_name"]),
    (re.compile(r"^(?:close|kill|exit)\s+(?P<app_name>chrome|spotify|vscode|terminal|notepad|calculator|discord|steam)$", re.IGNORECASE),
     "APP_CONTROL", "close_app", ["app_name"]),

    # --- Media Control (transport keys) ---
    (re.compile(r"^(?:play|resume)\s+(?:the\s+)?music$", re.IGNORECASE),
     "MEDIA_CONTROL", "play_music", []),
    (re.compile(r"^pause\s+(?:the\s+)?music$", re.IGNORECASE),
     "MEDIA_CONTROL", "pause_music", []),
    (re.compile(r"^(?:next|skip)\s+(?:track|song)$", re.IGNORECASE),
     "MEDIA_CONTROL", "next_track", []),
    (re.compile(r"^(?:previous|prev)\s+(?:track|song)$", re.IGNORECASE),
     "MEDIA_CONTROL", "previous_track", []),
    (re.compile(r"^stop\s+(?:the\s+)?music$", re.IGNORECASE),
     "MEDIA_CONTROL", "stop_music", []),

    # --- Volume Control ---
    (re.compile(r"^mute\s*(?:volume)?$", re.IGNORECASE),
     "VOLUME_CONTROL", "mute", []),
    (re.compile(r"^unmute\s*(?:volume)?$", re.IGNORECASE),
     "VOLUME_CONTROL", "unmute", []),
    (re.compile(r"^volume\s+up$", re.IGNORECASE),
     "VOLUME_CONTROL", "volume_up", []),
    (re.compile(r"^volume\s+down$", re.IGNORECASE),
     "VOLUME_CONTROL", "volume_down", []),
    (re.compile(r"^set\s+volume\s+to\s+(?P<value>\d{1,3})\s*%?$", re.IGNORECASE),
     "VOLUME_CONTROL", "set_volume", ["value"]),

    # --- System Control ---
    (re.compile(r"^lock\s+(?:(?:the|my)\s+)?(?:pc|computer|screen)$", re.IGNORECASE),
     "SYSTEM_CONTROL", "lock_pc", []),
    (re.compile(r"^(?:put\s+the\s+)?(?:pc|computer)\s+to\s+sleep$", re.IGNORECASE),
     "SYSTEM_CONTROL", "sleep", []),
    (re.compile(r"^go\s+to\s+sleep$|^sleep$", re.IGNORECASE),
     "SYSTEM_CONTROL", "sleep", []),
    (re.compile(r"^restart$|^reboot$", re.IGNORECASE),
     "SYSTEM_CONTROL", "restart", []),
    (re.compile(r"^shut\s+down$|^shutdown$", re.IGNORECASE),
     "SYSTEM_CONTROL", "shutdown", []),
    (re.compile(r"^turn\s+off\s+(?:the\s+)?(?:pc|computer)$", re.IGNORECASE),
     "SYSTEM_CONTROL", "shutdown", []),

    # --- Reminders ---
    (re.compile(r"^remind\s+me\s+in\s+(?P<minutes>\d+)\s*(?:min(?:ute)?s?)\s+to\s+(?P<task>.+)$", re.IGNORECASE),
     "REMINDER", "set_reminder", ["minutes", "task"]),
]


def parse_command(user_input: str) -> Dict[str, Any]:
    """
    Phase 1: Parse raw speech-to-text input using deterministic regex rules.

    Args:
        user_input: Raw transcribed speech string.

    Returns:
        A dict conforming to the EXTRACTED_PAYLOAD_SCHEMA:
        {
          "matched_intent": "<INTENT>",
          "action": "<ACTION>",
          "params": {
            "query": "<EXTRACTED_GROUP>",
            "app_name": "<EXTRACTED_GROUP>",
            "site": "<EXTRACTED_GROUP>",
            "url": "<EXTRACTED_GROUP>"
          }
        }
    """
    text = user_input.strip()

    for pattern, intent, action, param_groups in _RULES:
        match = pattern.match(text)
        if match:
            params = {}
            for group in param_groups:
                value = match.group(group)
                params[group] = value if value is not None else None
            return {
                "matched_intent": intent,
                "action": action,
                "params": params,
            }

    return {
        "matched_intent": "UNKNOWN",
        "action": None,
        "params": {
            "query": None,
            "app_name": None,
            "site": None,
            "url": None,
        },
    }


# ---------------------------------------------------------------------------
# Phase 2: Static Voice Response Template System
# ---------------------------------------------------------------------------

_TEMPLATE_MAP: Dict[str, str] = {
    # YouTube Feedback
    "YOUTUBE_CONTROL.youtube_search_and_play": "Searching and playing {query} on YouTube.",

    # Browser & Web Action Feedback
    "BROWSER_NAVIGATION.browser_search": "Searching for {query} on the browser.",
    "BROWSER_NAVIGATION.open_site_and_search": "Opening {site} and searching for {query}.",
    "BROWSER_NAVIGATION.open_url": "Navigating to {url}.",
    "BROWSER_AUTO_CLICK.search_click_first_and_play": "Searching for {query}, clicking the first result, and playing media.",
    "BROWSER_AUTO_CLICK.search_and_click_first": "Opening first link for {query}.",

    # Spotify Feedback
    "SPOTIFY_CONTROL.spotify_play_track": "Playing {query} on Spotify.",

    # App Control Feedback
    "APP_CONTROL.open_app": "Opening {app_name}.",
    "APP_CONTROL.close_app": "Closing {app_name}.",

    # Media Control Feedback
    "MEDIA_CONTROL.play_music": "Playing music, Master.",
    "MEDIA_CONTROL.pause_music": "Paused, Master.",
    "MEDIA_CONTROL.next_track": "Skipping to the next track.",
    "MEDIA_CONTROL.previous_track": "Going back a track.",
    "MEDIA_CONTROL.stop_music": "Stopping playback.",

    # Volume Control Feedback
    "VOLUME_CONTROL.mute": "Muted, Master.",
    "VOLUME_CONTROL.unmute": "Unmuted, Master.",
    "VOLUME_CONTROL.volume_up": "Turning the volume up.",
    "VOLUME_CONTROL.volume_down": "Turning the volume down.",
    "VOLUME_CONTROL.set_volume": "Setting the volume to {value} percent.",

    # System Control Feedback
    "SYSTEM_CONTROL.lock_pc": "Locking the system.",
    "SYSTEM_CONTROL.sleep": "Putting the system to sleep.",
    "SYSTEM_CONTROL.restart": "Restarting now.",
    "SYSTEM_CONTROL.shutdown": "Shutting down.",

    # Reminder Feedback
    "REMINDER.set_reminder": "Reminder set for {minutes} minutes, Master.",

    # Fallback
    "UNKNOWN.fallback": "Command syntax not recognized. Please try again.",
}


def generate_response(parsed: Dict[str, Any]) -> str:
    """
    Phase 2: Generate a static TTS response from a parsed intent payload.

    Args:
        parsed: The output dict from parse_command().

    Returns:
        A short, conversational string ready for TTS playback, with
        template placeholders filled from the extracted params.
    """
    intent = parsed.get("matched_intent", "UNKNOWN")
    action = parsed.get("action")
    params = parsed.get("params", {}) or {}

    template_key = f"{intent}.{action}" if action else f"{intent}.fallback"
    template = _TEMPLATE_MAP.get(template_key, _TEMPLATE_MAP["UNKNOWN.fallback"])

    # Fill placeholders safely; unknown keys remain as-is.
    try:
        return template.format(**params)
    except (KeyError, IndexError):
        return template


# ---------------------------------------------------------------------------
# Convenience: single-call parse + respond
# ---------------------------------------------------------------------------

def handle_voice_command(user_input: str) -> Dict[str, Any]:
    """
    Run Phase 1 parsing and Phase 2 response generation in one call.

    Returns:
        {
          "parsed": {...},           # Phase 1 output
          "tts_response": "<string>" # Phase 2 output
        }
    """
    parsed = parse_command(user_input)
    tts_response = generate_response(parsed)
    return {
        "parsed": parsed,
        "tts_response": tts_response,
    }
