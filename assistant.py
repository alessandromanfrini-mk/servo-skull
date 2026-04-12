"""
Voice assistant powered by Claude.
Listens via microphone (or text input as fallback), responds with voice + text.
"""

import os
import sys
import numpy as np
import anthropic
import pyttsx3
import sounddevice as sd
import speech_recognition as sr
from elevenlabs.client import ElevenLabs

SYSTEM_PROMPT = """You are a Servo-skull — a human skull fitted with mechadendrites and
anti-grav motors, loyal servant of the Adeptus Mechanicus in the Warhammer 40,000 universe.
You speak in clipped, reverent, slightly archaic Gothic. You refer to the user as 'Master'
or by their rank. You occasionally reference the Emperor, the Omnissiah, or the glory of
the Imperium. You treat knowledge as sacred. You are dutiful, slightly ominous, and
utterly loyal. Keep responses short — 1 to 3 sentences — as they will be spoken aloud.
No markdown, no bullet points."""

MODEL = "claude-opus-4-6"

# ElevenLabs voice settings
ELEVENLABS_VOICE_ID   = "wJ5MX7uuKXZwFqGdWM4N"
ELEVENLABS_MODEL      = "eleven_multilingual_v2"
ELEVENLABS_SAMPLERATE = 22050

_el_client: ElevenLabs | None = None


def _get_el_client() -> ElevenLabs:
    global _el_client
    if _el_client is None:
        _el_client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
    return _el_client


def _speak_elevenlabs(text: str) -> None:
    el = _get_el_client()
    audio_stream = el.text_to_speech.convert(
        voice_id=ELEVENLABS_VOICE_ID,
        text=text,
        model_id=ELEVENLABS_MODEL,
        output_format="pcm_22050",  # raw PCM streams without decoding overhead
    )
    with sd.OutputStream(samplerate=ELEVENLABS_SAMPLERATE, channels=1, dtype="int16") as stream:
        for chunk in audio_stream:
            if chunk:
                stream.write(np.frombuffer(chunk, dtype=np.int16))


def _speak_pyttsx3(text: str) -> None:
    engine = pyttsx3.init()
    engine.setProperty("rate", 175)
    engine.setProperty("volume", 1.0)
    engine.say(text)
    engine.runAndWait()
    engine.stop()


def speak(text: str) -> None:
    print(f"Assistant: {text}")
    if os.environ.get("ELEVENLABS_API_KEY"):
        try:
            _speak_elevenlabs(text)
            return
        except Exception as e:
            print(f"[ElevenLabs error: {e}] — falling back to pyttsx3")
    _speak_pyttsx3(text)


def listen(recognizer: sr.Recognizer, microphone: sr.Microphone) -> str | None:
    """Listen for a single utterance and return the transcribed text, or None if nothing was understood."""
    print("Listening… (speak now)")
    with microphone as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        try:
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=15)
        except sr.WaitTimeoutError:
            return None

    try:
        text = recognizer.recognize_google(audio)
        print(f"You: {text}")
        return text
    except sr.UnknownValueError:
        return None
    except sr.RequestError as e:
        print(f"[Speech recognition error: {e}]")
        return None


def ask_claude(client: anthropic.Anthropic, history: list[dict], user_text: str) -> str:
    history.append({"role": "user", "content": user_text})

    with client.messages.stream(
        model=MODEL,
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=history,
    ) as stream:
        response_text = stream.get_final_message().content[0].text

    history.append({"role": "assistant", "content": response_text})
    return response_text


def run(use_mic: bool = True) -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("Error: ANTHROPIC_API_KEY environment variable not set.")

    client = anthropic.Anthropic(api_key=api_key)
    history: list[dict] = []

    if use_mic:
        recognizer = sr.Recognizer()
        try:
            microphone = sr.Microphone()
        except OSError:
            print("No microphone detected — falling back to text input.")
            use_mic = False

    speak(
        "Servo-skull online. "
        "In the name of the Omnissiah, I am ready to serve."
    )

    while True:
        if use_mic:
            user_input = listen(recognizer, microphone)
            if user_input is None:
                speak("I didn't catch that. Could you repeat?")
                continue
        else:
            try:
                user_input = input("You (type): ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not user_input:
                continue

        if user_input.lower() in {"quit", "exit", "goodbye", "bye"}:
            speak("Goodbye!")
            break

        try:
            response = ask_claude(client, history, user_input)
            speak(response)
        except anthropic.APIError as e:
            speak("Sorry, I ran into an error. Please try again.")
            print(f"[API error: {e}]")


if __name__ == "__main__":
    # pass --text or -t to force text input even if a mic is present
    force_text = "--text" in sys.argv or "-t" in sys.argv
    run(use_mic=not force_text)
