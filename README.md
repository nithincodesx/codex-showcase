# CODEX — Voice Assistant

> **Status: Actively in development.** This is a showcase repo for CODEX, a voice assistant I'm building from scratch. Core pipeline is working end-to-end; more capabilities are being added continuously. Full source lives in private working repos — this page documents the architecture, decisions, and progress.

A voice assistant that isn't a wrapper around an existing assistant SDK. CODEX listens, talks back, and actually *does* things — opens apps, plays music, checks your system, reads the news, remembers what you told it yesterday.

## Why this exists

Most "AI assistant" demos just chat. CODEX is built around real tool-calling — every capability below is a function the LLM can actually invoke and get a result back from, not a scripted response.

## Architecture

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│   Next.js   │◄────►│   LiveKit    │◄────►│  Python      │
│  Frontend   │      │   Cloud      │      │  Agent       │
└─────────────┘      └──────────────┘      └─────┬───────┘
                                                    │
                      ┌─────────────────────────────┼─────────────────┐
                      │                             │                 │
                ┌─────▼─────┐              ┌────────▼────────┐  ┌─────▼─────┐
                │ Deepgram  │              │  LLM (OpenRouter │  │ Supabase  │
                │ STT / TTS │              │  + Cerebras      │  │ (memory)  │
                └───────────┘              │  fallback chain) │  └───────────┘
                                            └──────────────────┘
```

**Stack:**
- **Transport:** LiveKit Cloud (free tier)
- **STT/TTS:** Deepgram Nova-2 / Aura-2-Thalia
- **VAD:** Silero
- **LLM:** OpenRouter (multi-model free fallback chain) with Cerebras as primary
- **Memory:** Supabase (Postgres) — persists conversation history and notes across sessions
- **Frontend:** Next.js, military/terminal aesthetic, canvas radar visualizer, JetBrains Mono

## What works today

| Category | Tools |
|---|---|
| **Music** | Play/pause/resume/stop — streams from YouTube via `yt-dlp` + `ffplay`, native Windows pause/resume |
| **System control** | Open/close apps, screenshots, volume, CPU/RAM/disk/battery status, kill top memory hog |
| **Info** | Weather (Open-Meteo), web search (DuckDuckGo), news (RSS), date/time |
| **Productivity** | Notes, clipboard read/save, timers |
| **Memory** | Remembers prior conversations, references them naturally in replies |

## In progress

- Structured test suite for mood detection, memory recall, and tool-call accuracy
- Reducing per-turn token overhead (prompt, docstrings, history window)
- Calendar/email integration (OAuth-gated, not yet built)

## Engineering highlights so far

- **Graceful degradation under rate limits** — when the primary LLM provider hits a hard quota wall mid-conversation, the agent falls through a chain of alternate models instead of crashing the session.
- **Zero paid APIs** — every component runs on a free tier by design.

---

*Built solo, from an open-source starting point, rebuilt into a fully custom agent. Still growing.*
