# Servo Skull

> *"In the name of the Omnissiah, speak your will, Master."*

A Warhammer 40,000-themed voice assistant powered by the [Claude API](https://www.anthropic.com/api). Speak the wake phrase **"Servo Skull"** and converse with a loyal servant of the Adeptus Mechanicus. Fully hands-free, with background music, web search, countdown timers, and calendar invites.

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)
![Model](https://img.shields.io/badge/model-claude--haiku--4--5-blueviolet)

---

## Features

- **Always-on wake word**: Vosk offline speech recognition listens for "Servo Skull" with near-zero CPU overhead
- **Conversational AI**: multi-turn dialogue via Claude Haiku with a persistent in-session history
- **Text-to-speech**: eSpeak NG with a croaking, robotic voice profile
- **Speech-to-text**: Google Speech Recognition with a two-attempt fallback and spoken timeout warnings
- **Web search**: real-time answers via Claude's built-in `web_search` server tool
- **Countdown timers**: persisted to `timers.json`; the listener speaks them aloud when they fire, even between assistant sessions
- **Calendar invites**: sends `.ics` files via Gmail SMTP to your personal email
- **Atmospheric music**: looping background track that fades out on shutdown

---

## Architecture

```
┌─────────────────────────────────────────┐
│              listener.py                │   Always running
│  Vosk offline STT → wake word detection │
│  Timer checker thread (fires every 5s)  │
└───────────────┬─────────────────────────┘
                │  subprocess (on wake phrase)
                ▼
┌─────────────────────────────────────────┐
│              assistant.py               │   One session per wake
│  Google STT → Claude API (tool loop)    │
│  eSpeak TTS  ←  tool results fed back   │
└─────────────────────────────────────────┘
```

**Data flow per utterance:**

1. Microphone audio → Google Speech-to-Text (transcription)
2. Transcription → Claude Haiku (with conversation history + tools)
3. Claude may invoke `web_search`, `set_timer`, or `send_calendar_invite`
4. Tool results are fed back; Claude produces a final 1-3 sentence response
5. Response → eSpeak NG (spoken aloud)

---

## Prerequisites

| Dependency | Install |
|---|---|
| Python 3.11+ | [python.org](https://www.python.org/downloads/) |
| eSpeak NG | [github.com/espeak-ng/espeak-ng/releases](https://github.com/espeak-ng/espeak-ng/releases) (install to default path) |
| Vosk model | Downloaded automatically on first run via `vosk` package |
| Anthropic API key | [console.anthropic.com](https://console.anthropic.com) |

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/alessandromanfrini-mk/servo-skull.git
cd servo-skull

# 2. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS / Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
copy .env.example .env
# Edit .env with your credentials
```

---

## Configuration

Copy `.env.example` to `.env` and fill in your values:

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Your Anthropic API key |
| `USER_EMAIL` | Optional | Recipient address for calendar invites |
| `GMAIL_USER` | Optional | Gmail address used to send invites |
| `GMAIL_APP_PASSWORD` | Optional | [Gmail App Password](https://support.google.com/accounts/answer/185833) (not your regular password) |

Calendar invite functionality is disabled if the email variables are not set.

---

## Usage

```bash
# Start the always-on listener (keep this running)
venv\Scripts\python.exe listener.py
```

Then say **"Servo Skull"** to activate the assistant. The assistant stays active until:

- No speech is detected for ~20 seconds, returning to listening
- You say *"shutdown"* / *"go to sleep"*, returning to listening
- You say *"terminate"* / *"full shutdown"*, which exits completely

---

## Project Structure

```
servo-skull/
├── listener.py          # Wake word detection + timer checker
├── assistant.py         # Conversational AI loop (STT → Claude → TTS)
├── requirements.txt     # Pinned Python dependencies
├── .env.example         # Environment variable template
└── .gitignore
```

---

## Tools

| Tool | Description |
|---|---|
| `web_search` | Server-side tool; Claude queries the web and synthesises results |
| `set_timer` | Writes a timer entry to `timers.json`; `listener.py` speaks it on expiry |
| `send_calendar_invite` | Generates an `.ics` file and emails it via Gmail SMTP |

---

## License

Proprietary, all rights reserved. See [LICENSE](LICENSE).
