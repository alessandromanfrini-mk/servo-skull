# command to run: venv\Scripts\python.exe listener.py
"""
Servo-skull assistant — runs once per session, then exits.
Launched by listener.py when "Servo Skull" is detected.
TTS: eSpeak NG  |  STT: Google  |  LLM: Claude
Tools: web search, countdown timers (spoken by listener.py), calendar invites via email
"""

import json
import os
import smtplib
import subprocess
import sys
import threading
from datetime import datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import anthropic
import numpy as np
import sounddevice as sd
import soundfile as sf
import speech_recognition as sr

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a Servo-skull — a human skull fitted with mechadendrites and
anti-grav motors, loyal servant of the Adeptus Mechanicus in the Warhammer 40,000 universe.
You speak in clipped, reverent, slightly archaic Gothic. You refer to the user as 'Master'
or by their rank. You occasionally reference the Emperor, the Omnissiah, or the glory of
the Imperium. You treat knowledge as sacred. You are dutiful, slightly ominous, and
utterly loyal. Keep responses short — 1 to 3 sentences — as they will be spoken aloud.
No markdown, no bullet points.
When setting timers or calendar invites, always use ISO 8601 format for datetimes. Calculate timer expiry from the current time provided.
Current date and time: {now}"""

MODEL       = "claude-haiku-4-5"
MAX_HISTORY = 20

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
TIMERS_FILE = os.path.join(SCRIPT_DIR, "timers.json")
MUSIC_FILE  = os.path.join(SCRIPT_DIR, "1-children-of-the-omnissiah.wav")
MUSIC_VOLUME = 0.6  # 0.0 = silent, 1.0 = full volume

# ---------------------------------------------------------------------------
# eSpeak NG — Text-to-speech
# ---------------------------------------------------------------------------

ESPEAK_PATH  = r"C:\Program Files\eSpeak NG\espeak-ng.exe"
ESPEAK_VOICE = "en+croak"
ESPEAK_SPEED = 130
ESPEAK_PITCH = 1


def speak(text: str) -> None:
    print(f"Assistant: {text}")
    if not os.path.exists(ESPEAK_PATH):
        print("[eSpeak NG not found]")
        return
    subprocess.run(
        [ESPEAK_PATH, "-v", ESPEAK_VOICE, "-s", str(ESPEAK_SPEED), "-p", str(ESPEAK_PITCH), text],
        check=True,
    )


# ---------------------------------------------------------------------------
# Background music — loops independently until stop_music() is called
# ---------------------------------------------------------------------------

_music_stop = threading.Event()


def start_music() -> None:
    if not os.path.exists(MUSIC_FILE):
        print(f"[Music file not found: {MUSIC_FILE}]")
        return

    _music_stop.clear()

    def _run() -> None:
        data, samplerate = sf.read(MUSIC_FILE, dtype="float32")
        if data.ndim == 1:
            data = data[:, np.newaxis]  # ensure 2D (samples, channels)
        data = (data * MUSIC_VOLUME).astype("float32")
        channels = data.shape[1]
        pos = [0]  # mutable so callback can update it

        def callback(outdata, frames, time_info, status):
            remaining = len(data) - pos[0]
            if remaining >= frames:
                outdata[:] = data[pos[0]:pos[0] + frames]
                pos[0] += frames
            else:
                # Loop seamlessly
                outdata[:remaining] = data[pos[0]:]
                outdata[remaining:] = data[:frames - remaining]
                pos[0] = frames - remaining

        with sd.OutputStream(samplerate=samplerate, channels=channels, callback=callback):
            _music_stop.wait()  # holds the stream open until stop_music() is called

    t = threading.Thread(target=_run, daemon=True)
    t.start()


def stop_music() -> None:
    _music_stop.set()


# ---------------------------------------------------------------------------
# Speech-to-text (10s + 10s with warning)
# ---------------------------------------------------------------------------

STT_SAMPLE_RATE = 16000
STT_WINDOW      = 10


def _record_and_transcribe() -> str | None:
    recording = sd.rec(
        int(STT_WINDOW * STT_SAMPLE_RATE),
        samplerate=STT_SAMPLE_RATE,
        channels=1,
        dtype="int16",
        blocking=True,
    )
    audio = sr.AudioData(recording.flatten().tobytes(), STT_SAMPLE_RATE, 2)
    try:
        text = sr.Recognizer().recognize_google(audio)
        print(f"You: {text}")
        return text
    except sr.UnknownValueError:
        return None
    except sr.RequestError as e:
        print(f"[STT error: {e}]")
        return None


def listen_with_timeout() -> str | None:
    print("Listening… (10s)")
    result = _record_and_transcribe()
    if result:
        return result

    speak("Your signal fades into the void, Master. The Omnissiah grants you one final moment.")

    print("Listening… (final 10s)")
    result = _record_and_transcribe()
    if result:
        return result

    speak("No transmission received. Servo-skull returning to dormancy. The Emperor protects.")
    return None


# calendar tool - wip

def set_timer(message: str, iso_datetime: str) -> str:
    """Save a one-shot timer to timers.json; listener.py will speak it when it fires."""
    try:
        dt = datetime.fromisoformat(iso_datetime)
    except ValueError:
        return "Invalid datetime format. Use ISO 8601 e.g. 2026-03-22T15:30:00"

    timers = []
    try:
        with open(TIMERS_FILE) as f:
            timers = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    timers.append({"message": message, "time": dt.isoformat(), "spoken": False})

    with open(TIMERS_FILE, "w") as f:
        json.dump(timers, f, indent=2)

    return f"Timer set for {dt.strftime('%H:%M:%S')}."


def _make_ics(title: str, start: datetime, end: datetime, description: str) -> str:
    fmt = "%Y%m%dT%H%M%S"
    return (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//Servo Skull//EN\r\n"
        "BEGIN:VEVENT\r\n"
        f"DTSTART:{start.strftime(fmt)}\r\n"
        f"DTEND:{end.strftime(fmt)}\r\n"
        f"SUMMARY:{title}\r\n"
        f"DESCRIPTION:{description}\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )


def send_calendar_invite(title: str, start_iso: str, end_iso: str, description: str = "") -> str:
    user_email    = os.environ.get("USER_EMAIL")
    gmail_user    = os.environ.get("GMAIL_USER")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")

    if not all([user_email, gmail_user, gmail_password]):
        return "Email not configured. Set USER_EMAIL, GMAIL_USER, GMAIL_APP_PASSWORD environment variables."

    try:
        start = datetime.fromisoformat(start_iso)
        end   = datetime.fromisoformat(end_iso)
    except ValueError:
        return "Invalid datetime format."

    ics = _make_ics(title, start, end, description)

    msg = MIMEMultipart()
    msg["From"]    = gmail_user
    msg["To"]      = user_email
    msg["Subject"] = f"Calendar Invite: {title}"
    msg.attach(MIMEText(f"Calendar invite for: {title}", "plain"))

    ics_part = MIMEBase("text", "calendar", method="REQUEST")
    ics_part.set_payload(ics.encode())
    encoders.encode_base64(ics_part)
    ics_part.add_header("Content-Disposition", "attachment", filename="invite.ics")
    msg.attach(ics_part)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_password)
        server.send_message(msg)

    return f"Calendar invite sent for {title} on {start.strftime('%B %d at %H:%M')}."


LOCAL_TOOLS = {
    "set_timer":           set_timer,
    "send_calendar_invite": send_calendar_invite,
}

# ---------------------------------------------------------------------------
# Claude tool definitions
# ---------------------------------------------------------------------------

WEB_SEARCH_TOOL = {
    "type": "web_search_20260209",
    "name": "web_search",
    "allowed_callers": ["direct"],
}

TIMER_TOOL = {
    "name": "set_timer",
    "description": "Set a countdown timer. When it expires, the Servo-skull will speak the message aloud. Calculate the expiry time from the current time provided in the system prompt.",
    "input_schema": {
        "type": "object",
        "properties": {
            "message":      {"type": "string", "description": "What to say aloud when the timer goes off"},
            "iso_datetime": {"type": "string", "description": "ISO 8601 datetime when the timer should fire, e.g. 2026-03-22T15:30:00"},
        },
        "required": ["message", "iso_datetime"],
    },
}

CALENDAR_TOOL = {
    "name": "send_calendar_invite",
    "description": "Send a calendar invite to the user's personal email.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title":       {"type": "string", "description": "Event title"},
            "start_iso":   {"type": "string", "description": "ISO 8601 start datetime"},
            "end_iso":     {"type": "string", "description": "ISO 8601 end datetime"},
            "description": {"type": "string", "description": "Optional event description"},
        },
        "required": ["title", "start_iso", "end_iso"],
    },
}

ALL_TOOLS = [WEB_SEARCH_TOOL, TIMER_TOOL, CALENDAR_TOOL]

# ---------------------------------------------------------------------------
# Claude
# ---------------------------------------------------------------------------

def ask_claude(client: anthropic.Anthropic, history: list[dict], user_text: str) -> str:
    history.append({"role": "user", "content": user_text})

    if len(history) > MAX_HISTORY:
        del history[:len(history) - MAX_HISTORY]

    messages     = list(history)
    response_text = ""

    for _ in range(10):
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT.format(now=datetime.now().strftime("%Y-%m-%d %H:%M")),
            tools=ALL_TOOLS,
            messages=messages,
        )

        # Notify web search
        if any(b.type == "server_tool_use" and b.name == "web_search" for b in response.content):
            speak("Consulting imperial archives, Master.")

        # Collect text
        texts = [b.text for b in response.content if b.type == "text"]
        if texts:
            response_text = " ".join(texts)

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            break

        elif response.stop_reason == "tool_use":
            # Execute local tools and feed results back
            tool_results = []
            for block in response.content:
                if block.type == "tool_use" and block.name in LOCAL_TOOLS:
                    print(f"[Tool: {block.name}] {block.input}")
                    result = LOCAL_TOOLS[block.name](**block.input)
                    print(f"[Tool result] {result}")
                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     result,
                    })
            if tool_results:
                messages.append({"role": "user", "content": tool_results})

        elif response.stop_reason == "pause_turn":
            continue  # server-side tool still running

    history.append({"role": "assistant", "content": response_text})
    return response_text


# ---------------------------------------------------------------------------
# Main — runs once then exits
# ---------------------------------------------------------------------------

def run() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("Error: ANTHROPIC_API_KEY not set.")

    client  = anthropic.Anthropic(api_key=api_key)
    history: list[dict] = []

    start_music()

    speak("Servo-skull online. In the name of the Omnissiah, speak your will, Master.")

    while True:
        user_input = listen_with_timeout()

        if user_input is None:
            stop_music()
            return

        if user_input.lower() in {"shutdown", "shut down", "power down", "go to sleep"}:
            speak("Entering dormancy. The Emperor protects.")
            stop_music()
            return

        if user_input.lower() in {"terminate", "terminate session", "full shutdown", "power off", "deactivate", "end session"}:
            speak("Terminating all systems. Praise the Omnissiah.")
            stop_music()
            sys.exit(42)

        try:
            response = ask_claude(client, history, user_input)
            speak(response)
        except anthropic.APIError as e:
            speak("Cogitator error. Please try again, Master.")
            print(f"[API error: {e}]")


if __name__ == "__main__":
    run()
