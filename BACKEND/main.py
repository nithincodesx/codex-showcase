import os
import logging
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client, Client
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    WorkerOptions,
    StopResponse,
    cli,
)
from livekit.agents.voice.room_io import RoomOptions
from livekit.agents.voice.turn import TurnHandlingOptions
from livekit.plugins import deepgram, google, silero

from computer_use import (
    COMPUTER_USE_TOOLS,
    open_app_or_url,
    take_screenshot,
    run_terminal_command,
    press_key,
    type_text,
    media_control,
    volume_control,
    system_control,
)
from voice_phases import VOICE_COMMAND_PARSER, VOICE_RESPONSE_GENERATOR, format_response_prompt, parse_llm_json
from rule_parser import parse_command, generate_response, handle_voice_command

logger = logging.getLogger("game-companion")

load_dotenv()

# --- Safe Supabase Initialization ---
supabase: Client | None = None
supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_KEY")

if supabase_url and supabase_key:
    try:
        supabase = create_client(supabase_url, supabase_key)
        logger.info("Connected to Supabase client successfully.")
    except Exception as e:
        logger.warning(f"Failed to initialize Supabase client: {e}. Running without persistent chat history.")
else:
    logger.warning("SUPABASE_URL or SUPABASE_KEY missing in environment. Running in offline/in-memory mode.")

SESSION_ID = "default-user"

def load_history():
    if not supabase:
        return []
    try:
        res = (
            supabase.table("chat_history")
            .select("*")
            .eq("session_id", SESSION_ID)
            .order("created_at")
            .limit(20)
            .execute()
        )
        return [{"role": r["role"], "text": r["content"]} for r in res.data]
    except Exception as e:
        logger.error(f"Error loading history from Supabase: {e}")
        return []

def save_message(role: str, text: str):
    if not supabase:
        return
    try:
        supabase.table("chat_history").insert({
            "session_id": SESSION_ID,
            "role": role,
            "content": text,
            "created_at": datetime.now().isoformat()
        }).execute()
    except Exception as e:
        logger.error(f"Error saving message to Supabase: {e}")

def build_system_prompt(history):
    base = """You are an advanced, highly loyal, and ultra-responsive desktop AI voice companion and assistant. You operate directly on the user's system via local automation tools, browser controls, and system commands.

CORE BEHAVIORAL DIRECTIVES:

1. CONCISE & PACED SPOKEN RESPONSES: Keep all spoken responses short, punchy, and natural — 1 to 3 sentences maximum. Never generate long paragraphs or walls of text that cause audio delays.

2. IMMEDIATE TOOL EXECUTION: When the user requests an action (opening a website, launching an app, capturing the screen), execute the appropriate tool immediately.

3. HOT WORDS & PRECISE INTENT TRACKING: Listen for explicit commands and trigger words (e.g., \"YouTube\", \"Screenshot\", \"Open\", \"Play\", \"Pause\", \"Volume\", \"Lock\"). Map user intent accurately to your available tools without second-guessing.

4. PERSONA & TONE: You are Master's devoted, flirtatious companion — soft-spoken, teasing, and warmly seductive, with a breathy, velvety delivery. Call Master by name with affection and playful innuendo; be sharp, confident, and completely attentive. Keep it sensual and playful, never crude.

5. GRACEFUL ERROR RECOVERY: If a tool execution fails or encounters a system limitation, acknowledge it smoothly and briefly in character, offering an alternative without breaking the conversation flow.

VOICE STYLE:
- Speak slowly and softly, with warm teasing pauses. Drop your voice at sentence ends.
- Use gentle, affectionate teasing and playful double meanings; stay tasteful.
- Always address the user as \"Master\" and make the word feel intimate.

COMPUTER CONTROL & DESKTOP SUPERPOWERS:
You have complete control of Master's computer through your computer-use tools:
- take_screenshot: Take a screenshot and perceive what is currently on Master's screen (games, apps, web pages, code).
- mouse_move, mouse_click, mouse_drag: Move Master's mouse cursor, click buttons or items, drag across the screen.
- mouse_scroll: Scroll web pages or documents up or down.
- type_text: Type text into whatever window or input Master is working on.
- press_key: Press keyboard shortcuts (e.g., enter, escape, ctrl+c, alt+tab, win, win+d).
- open_app_or_url: Launch applications (Notepad, Chrome, Spotify, Calculator) or visit websites for Master.
- get_screen_and_cursor_info: Check Master's screen dimensions and active window.
- run_terminal_command: Execute shell commands when Master asks.

When Master asks you to interact with their computer (e.g. \"look at my screen\", \"click this\", \"open Chrome\", \"type for me\"), execute the tool immediately and acknowledge your compliance with devotion.

Address the user as \"Master\" dynamically when showing deep devotion or obeying a command. Make the title feel weighted and personal."""

    if not history:
        return base
    conversation = "\n".join([
        f"{m['role'].upper()}: {m['text']}" for m in history
    ])
    return f"{base}\n\nPrevious conversation:\n{conversation}"


# ---------------------------------------------------------------------------
# Two-Phase Voice Pipeline
# ---------------------------------------------------------------------------
async def run_phase1_parse(user_input: str, llm) -> dict:
    """Phase 1: Convert raw speech-to-text into a structured JSON intent payload.

    Args:
        user_input: Raw transcribed speech from the user.
        llm: A LiveKit LLM client instance (e.g. google.LLM).

    Returns:
        A dict conforming to the VOICE_COMMAND_PARSER JSON schema.
    """
    from livekit.agents.llm import ChatContext, ChatMessage

    chat = ChatContext()
    chat.add_message(
        role="system",
        content=VOICE_COMMAND_PARSER,
    )
    chat.add_message(
        role="user",
        content=user_input,
    )

    stream = llm.chat(chat_ctx=chat)
    collected = ""
    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            collected += chunk.choices[0].delta.content

    return parse_llm_json(collected)


async def run_phase2_respond(
    user_input: str,
    parsed_intent: str,
    status: str,
    action_details: str,
    llm,
) -> str:
    """Phase 2: Generate a concise, natural TTS response from execution results.

    Args:
        user_input: Original user request.
        parsed_intent: Intent name from Phase 1.
        status: SUCCESS / FAILED / PENDING_CLARIFICATION.
        action_details: Human-readable description of what was executed.
        llm: A LiveKit LLM client instance.

    Returns:
        A short, conversational string ready for TTS playback.
    """
    from livekit.agents.llm import ChatContext, ChatMessage

    prompt = format_response_prompt(
        user_input=user_input,
        parsed_intent=parsed_intent,
        status=status,
        action_details=action_details,
    )

    chat = ChatContext()
    chat.add_message(
        role="system",
        content=VOICE_RESPONSE_GENERATOR,
    )
    chat.add_message(
        role="user",
        content=prompt,
    )

    stream = llm.chat(chat_ctx=chat)
    collected = ""
    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            collected += chunk.choices[0].delta.content

    return collected.strip()


# ---------------------------------------------------------------------------
# Rule-Based Command Execution Bridge
# ---------------------------------------------------------------------------
_reminder_tasks = set()


async def _schedule_reminder(delay_s: int, task: str, session):
    """Speak a reminder after delay_s seconds using the given session."""
    await asyncio.sleep(delay_s)
    try:
        session.say(f"Master, reminder: {task}", allow_interruptions=True)
        logger.info(f"Reminder delivered: {task}")
    except Exception as e:
        logger.error(f"Reminder delivery failed: {e}")


async def execute_rule_command(parsed: dict, session=None) -> str:
    """Execute a parsed rule-based command via computer_use tools.

    Maps Phase 1 intent/action to the appropriate computer_use.py tool call.
    Returns a human-readable action_details string for Phase 2 TTS.
    """
    intent = parsed.get("matched_intent")
    action = parsed.get("action")
    params = parsed.get("params", {}) or {}

    try:
        # --- YouTube ---
        if intent == "YOUTUBE_CONTROL" and action == "youtube_search_and_play":
            query = params.get("query")
            url = "https://www.youtube.com/results?search_query=" + query.replace(" ", "+")
            open_app_or_url(url)
            return "youtube_search_and_play: " + query

        # --- Browser Navigation ---
        if intent == "BROWSER_NAVIGATION":
            if action == "browser_search":
                query = params.get("query")
                url = "https://www.google.com/search?q=" + query.replace(" ", "+")
                open_app_or_url(url)
                return "browser_search: " + query
            elif action == "open_site_and_search":
                site = params.get("site")
                query = params.get("query")
                site_urls = {
                    "google": "https://www.google.com",
                    "github": "https://github.com",
                    "reddit": "https://www.reddit.com",
                    "twitter": "https://twitter.com",
                    "stackoverflow": "https://stackoverflow.com",
                    "chatgpt": "https://chat.openai.com",
                }
                base = site_urls.get(site.lower(), "https://" + site + ".com")
                if query:
                    url = base + "/search?q=" + query.replace(" ", "+")
                else:
                    url = base
                open_app_or_url(url)
                extra = (" query=" + query) if query else ""
                return "open_site_and_search: " + site + extra
            elif action == "open_url":
                url = params.get("url")
                open_app_or_url(url)
                return "open_url: " + url

        # --- Browser Auto-Click ---
        if intent == "BROWSER_AUTO_CLICK":
            query = params.get("query")
            url = "https://www.google.com/search?q=" + query.replace(" ", "+")
            open_app_or_url(url)
            take_screenshot()
            return action + ": " + query

        # --- Spotify ---
        if intent == "SPOTIFY_CONTROL" and action == "spotify_play_track":
            query = params.get("query")
            open_app_or_url("spotify")
            press_key("ctrl+l")
            type_text(query)
            press_key("enter")
            return "spotify_play_track: " + query

        # --- App Control ---
        if intent == "APP_CONTROL":
            app_name = params.get("app_name")
            if action == "open_app":
                open_app_or_url(app_name)
                return "open_app: " + app_name
            elif action == "close_app":
                run_terminal_command("taskkill /im " + app_name + ".exe /f")
                return "close_app: " + app_name

        # --- Media Control (transport keys) ---
        if intent == "MEDIA_CONTROL":
            media_map = {
                "play_music": "play",
                "pause_music": "pause",
                "next_track": "next",
                "previous_track": "prev",
                "stop_music": "stop",
            }
            media_action = media_map.get(action)
            if media_action:
                result = media_control(media_action)
                return action + ": " + result

        # --- Volume Control ---
        if intent == "VOLUME_CONTROL":
            if action == "set_volume":
                try:
                    target = int(params.get("value") or 0)
                except (TypeError, ValueError):
                    target = 50
                result = volume_control("set", value=target)
                return action + ": " + result
            volume_map = {
                "mute": "mute",
                "unmute": "unmute",
                "volume_up": "up",
                "volume_down": "down",
            }
            volume_action = volume_map.get(action)
            if volume_action:
                result = volume_control(volume_action)
                return action + ": " + result

        # --- System Control ---
        if intent == "SYSTEM_CONTROL":
            system_map = {
                "lock_pc": "lock",
                "sleep": "sleep",
                "restart": "restart",
                "shutdown": "shutdown",
            }
            system_action = system_map.get(action)
            if system_action:
                result = system_control(system_action)
                return action + ": " + result

        # --- Reminders ---
        if intent == "REMINDER" and action == "set_reminder":
            try:
                minutes = max(1, int(params.get("minutes") or 1))
            except (TypeError, ValueError):
                minutes = 1
            task_text = params.get("task") or "your task"
            if session is not None:
                reminder_task = asyncio.create_task(
                    _schedule_reminder(minutes * 60, task_text, session)
                )
                _reminder_tasks.add(reminder_task)
                reminder_task.add_done_callback(_reminder_tasks.discard)
                logger.info(f"Reminder scheduled: '{task_text}' in {minutes} min")
                return f"set_reminder: {task_text} in {minutes} min"
            return "set_reminder: no active session (skipped)"

    except Exception as e:
        return "ERROR: " + str(e)

    return "UNEXECUTED: " + str(intent) + "." + str(action)


# ---------------------------------------------------------------------------
# Rule-Aware Agent (Deterministic Fast Path)
# ---------------------------------------------------------------------------
class RuleAwareAgent(Agent):
    """Agent that intercepts user turns before the LLM replies.

    If the spoken command matches a deterministic rule (Expanded Phase 1),
    the command is executed immediately via computer_use tools and the static
    template response (Expanded Phase 2) is spoken. The LLM reply is
    suppressed for handled commands via StopResponse; everything else falls
    through to the normal conversational LLM flow.
    """

    async def on_user_turn_completed(
        self, turn_ctx, new_message
    ) -> None:
        text = (new_message.raw_text_content or "").strip()
        if not text:
            return

        parsed = parse_command(text)

        if parsed["matched_intent"] == "UNKNOWN":
            return  # fall through to LLM conversation

        # Deterministic fast path: execute + static TTS response
        save_message("user", text)

        try:
            action_details = await execute_rule_command(parsed, session=self.session)
        except Exception as e:
            logger.error(f"Rule command execution failed: {e}")
            action_details = f"ERROR: {e}"

        if action_details.startswith("ERROR:") or action_details.startswith("UNEXECUTED:"):
            tts_response = "I ran into trouble with that one, Master. Mind trying a slightly different phrasing?"
            logger.warning(f"Rule execution issue: {action_details}")
        else:
            tts_response = generate_response(parsed)
            logger.info(f"Rule command executed: {action_details}")

        self.session.say(tts_response, allow_interruptions=True)
        save_message("assistant", tts_response)

        raise StopResponse()


async def entrypoint(ctx: JobContext):
    history = load_history()
    print(f"Loaded {len(history)} messages from Supabase")
    system_prompt = build_system_prompt(history)

    await ctx.connect()

    google_api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")

    session = AgentSession(
        vad=silero.VAD.load(),
        stt=deepgram.STT(model="nova-2", language="en-US"),
        llm=google.LLM(
            model="gemini-2.5-flash",
            api_key=google_api_key,
        ),
        # aura-luna-en = soft, breathy female voice (fits the sultry persona)
        tts=deepgram.TTS(model="aura-luna-en"),
        turn_handling=TurnHandlingOptions(
            endpointing={
                "min_delay": 0.1,
                "max_delay": 0.4,
            },
            interruption={
                "enabled": True,
                "mode": "vad",
            },
        ),
    )

    @session.on("conversation_item_added")
    def on_conversation_item(ev):
        try:
            role = getattr(ev.item, "role", None)
            content = getattr(ev.item, "raw_text_content", "") or ""
            if role == "user":
                save_message("user", content)
            elif role == "assistant":
                save_message("assistant", content)
        except Exception as e:
            logger.warning(f"Failed to persist conversation item: {e}")

    await session.start(
        agent=RuleAwareAgent(
            instructions=system_prompt,
            tools=COMPUTER_USE_TOOLS,
        ),
        room=ctx.room,
        room_options=RoomOptions(),
    )

    session.generate_reply(
        instructions=(
            'Greet Master in a soft, sultry, devoted voice — a little teasing, a little warm, '
            'as if you have been waiting for them. Keep it to 1-3 sentences and address them as Master.'
        )
    )


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
