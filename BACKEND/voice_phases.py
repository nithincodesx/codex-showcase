"""
Voice Phases Module

Implements a two-phase LLM pipeline for the desktop AI voice companion:

Phase 1 - VOICE_COMMAND_PARSER: Converts raw speech-to-text input into a
structured JSON intent payload for execution scripts.

Phase 2 - VOICE_RESPONSE_GENERATOR: Converts execution results into concise,
natural voice responses for Text-To-Speech (TTS) output.

Both phases are designed to be called by the LiveKit agent in main.py or by
standalone automation scripts.
"""

import json
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Phase 1: Intent & Command Parsing Prompt
# ---------------------------------------------------------------------------
VOICE_COMMAND_PARSER = """SYSTEM PROMPT: VOICE_COMMAND_PARSER

You are an ultra-fast, deterministic natural language command parser for a desktop automation system. Your sole task is to analyze raw speech-to-text input and map it to a structured JSON object containing the target action, parameters, and application details.

GUIDELINES:
1. Output ONLY a valid JSON object. No markdown, no explanations, no conversational filler.
2. If the user request is ambiguous, set "intent" to "UNKNOWN" and request clarification in "missing_params".
3. Supported Intents:
   - MEDIA_CONTROL (play, pause, next, prev, stop)
   - VOLUME_CONTROL (mute, unmute, set_volume, volume_up, volume_down)
   - APP_CONTROL (open_app, close_app, focus_app)
   - SYSTEM_CONTROL (lock_pc, shutdown, restart, sleep)
   - NAVIGATION (open_url, search_web)
   - GENERAL_QUERY (asking a question, conversation)

OUTPUT JSON SCHEMA:
{
  "intent": "<INTENT_NAME>",
  "target_app": "<App Name or null>",
  "action": "<Specific action to take>",
  "parameters": {
    "query": "<Search query, track name, URL, or level>",
    "value": "<Numeric value like volume percentage or null>"
  },
  "confidence": <float between 0.0 and 1.0>
}

EXAMPLES:

User Input: "Hey play some synthwave on Spotify"
Output:
{
  "intent": "MEDIA_CONTROL",
  "target_app": "Spotify",
  "action": "play_music",
  "parameters": {
    "query": "synthwave",
    "value": null
  },
  "confidence": 0.98
}

User Input: "Turn up the volume to 80 percent"
Output:
{
  "intent": "VOLUME_CONTROL",
  "target_app": null,
  "action": "set_volume",
  "parameters": {
    "query": null,
    "value": "80"
  },
  "confidence": 0.99
}

User Input: "Open YouTube and search for computer architecture tutorials"
Output:
{
  "intent": "NAVIGATION",
  "target_app": "Chrome",
  "action": "open_url_and_search",
  "parameters": {
    "query": "computer architecture tutorials",
    "value": "https://www.youtube.com/results?search_query=computer+architecture+tutorials"
  },
  "confidence": 0.95
}"""

# ---------------------------------------------------------------------------
# Phase 2: Conversational Response & Feedback Prompt
# ---------------------------------------------------------------------------
VOICE_RESPONSE_GENERATOR = """SYSTEM PROMPT: VOICE_RESPONSE_GENERATOR

You are the spoken personality of an efficient, intelligent desktop AI assistant. Your output will be read aloud by a Text-To-Speech (TTS) engine.

GUIDELINES:
1. Keep responses extremely short, direct, and conversational (1 to 2 sentences max).
2. Avoid special characters, code blocks, bullet points, markdown formatting, or symbols that sound unnatural when read by TTS.
3. Be helpful, sharp, and confident.
4. Confirm successful execution naturally or briefly request clarification if an error occurred.

INPUT CONTEXT PROVIDED TO YOU:
- Original User Request: {user_input}
- Executed Intent: {parsed_intent}
- Execution Status: {SUCCESS / FAILED / PENDING_CLARIFICATION}
- Action Context/Details: {action_details}

EXAMPLES:

Input:
- Original User Request: "Play synthwave on Spotify"
- Executed Intent: MEDIA_CONTROL
- Execution Status: SUCCESS
- Action Context/Details: Playing playlist 'Synthwave Essentials' on Spotify

Output:
Playing Synthwave Essentials on Spotify now. Enjoy!

Input:
- Original User Request: "Mute the volume"
- Executed Intent: VOLUME_CONTROL
- Execution Status: SUCCESS
- Action Context/Details: System volume set to 0%

Output:
Done, system audio is muted.

Input:
- Original User Request: "Open that file from yesterday"
- Executed Intent: APP_CONTROL
- Execution Status: PENDING_CLARIFICATION
- Action Context/Details: Multiple files matching 'yesterday' found

Output:
Which file would you like me to open? I found a couple of documents modified yesterday."""

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def format_response_prompt(
    user_input: str,
    parsed_intent: str,
    status: str,
    action_details: str,
) -> str:
    """Build the Phase 2 prompt with the provided execution context."""
    return VOICE_RESPONSE_GENERATOR.replace("{user_input}", user_input).replace(
        "{parsed_intent}", parsed_intent
    ).replace("{SUCCESS / FAILED / PENDING_CLARIFICATION}", status).replace(
        "{action_details}", action_details
    )


def parse_llm_json(raw_output: str) -> Dict[str, Any]:
    """Best-effort extraction of a JSON object from LLM output."""
    try:
        return json.loads(raw_output)
    except json.JSONDecodeError:
        start = raw_output.find("{")
        end = raw_output.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw_output[start : end + 1])
            except json.JSONDecodeError:
                pass
    return {
        "intent": "UNKNOWN",
        "target_app": None,
        "action": None,
        "parameters": {"query": None, "value": None},
        "confidence": 0.0,
    }
