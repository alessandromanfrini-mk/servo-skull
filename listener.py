"""
Lightweight always-on listener.
Waits for "Servo Skull" then launches assistant.py, waits for it to finish,
then goes back to listening.

Background thread checks timers.json every 5 seconds and speaks any expired
timers via eSpeak NG.
"""

import json
import os
import subprocess
import threading
import time
import sounddevice as sd
from datetime import datetime
from vosk import Model as VoskModel, KaldiRecognizer

WAKE_PHRASE  = "servo skull"
SAMPLE_RATE  = 16000
CHUNK_FRAMES = 4000

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
PYTHON      = os.path.join(SCRIPT_DIR, "venv", "Scripts", "python.exe")
ASSISTANT   = os.path.join(SCRIPT_DIR, "assistant.py")
TIMERS_FILE = os.path.join(SCRIPT_DIR, "timers.json")

ESPEAK_PATH  = r"C:\Program Files\eSpeak NG\espeak-ng.exe"
ESPEAK_VOICE = "en+croak"
ESPEAK_SPEED = 130
ESPEAK_PITCH = 1

# Set while assistant.py is running so the timer thread waits
assistant_running = threading.Event()


def speak(text: str) -> None:
    if not os.path.exists(ESPEAK_PATH):
        print(f"[eSpeak not found] {text}")
        return
    subprocess.run(
        [ESPEAK_PATH, "-v", ESPEAK_VOICE, "-s", str(ESPEAK_SPEED), "-p", str(ESPEAK_PITCH), text],
        check=True,
    )


def timer_checker() -> None:
    """Background thread: checks timers.json every 5s, speaks expired timers once."""
    while True:
        time.sleep(5)

        if assistant_running.is_set():
            continue  # wait until assistant finishes so voices don't overlap

        if not os.path.exists(TIMERS_FILE):
            continue

        try:
            with open(TIMERS_FILE) as f:
                timers = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        now = datetime.now()
        changed = False

        for timer in timers:
            if timer.get("spoken"):
                continue
            try:
                due = datetime.fromisoformat(timer["time"])
            except (KeyError, ValueError):
                continue
            if due <= now:
                print(f"[Timer] {timer['message']}")
                speak(f"Timer complete, Master: {timer['message']}")
                timer["spoken"] = True
                changed = True

        if changed:
            try:
                remaining = [t for t in timers if not t.get("spoken")]
                if remaining:
                    with open(TIMERS_FILE, "w") as f:
                        json.dump(remaining, f, indent=2)
                else:
                    os.remove(TIMERS_FILE)  # no pending timers — clean up
            except OSError:
                pass


def main() -> None:
    print("Loading wake word model…")
    vosk_model      = VoskModel(model_name="vosk-model-small-en-us-0.15")
    wake_recognizer = KaldiRecognizer(vosk_model, SAMPLE_RATE, f'["{WAKE_PHRASE}", "[unk]"]')

    # Start timer checker in background
    t = threading.Thread(target=timer_checker, daemon=True)
    t.start()

    print("Ready. Say 'Servo Skull' to start the assistant.")

    while True:
        # Wait silently for "Servo Skull"
        with sd.RawInputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=CHUNK_FRAMES) as stream:
            while True:
                chunk, _ = stream.read(CHUNK_FRAMES)
                if wake_recognizer.AcceptWaveform(bytes(chunk)):
                    result = json.loads(wake_recognizer.Result())
                    if WAKE_PHRASE in result.get("text", ""):
                        print("Wake word detected — launching assistant.")
                        break

        # Block timer thread while assistant is speaking
        assistant_running.set()
        try:
            result = subprocess.run([PYTHON, ASSISTANT])
        finally:
            assistant_running.clear()

        if result.returncode == 42:
            print("Full shutdown requested. Exiting.")
            break

        print("Assistant finished. Listening again.")


if __name__ == "__main__":
    main()
