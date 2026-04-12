# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] — 2026-03-29

### Added
- Wake word detection via Vosk offline STT (`listener.py`)
- Conversational AI loop with multi-turn history via Claude Haiku (`assistant.py`)
- Text-to-speech via eSpeak NG with a robotic voice profile
- Speech-to-text via Google Speech Recognition with two-attempt fallback
- Real-time web search via Claude's built-in `web_search` server tool
- Countdown timer tool — persists to `timers.json`, spoken by `listener.py` on expiry
- Calendar invite tool — generates `.ics` and emails via Gmail SMTP
- Looping background music during active sessions
- Graceful shutdown commands: `"shutdown"` (return to listen) and `"terminate"` (full exit)
