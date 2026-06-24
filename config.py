"""
Model and voice configuration.

Change the models or TTS voice here — no need to touch daily_brief.py.
"""

# Model used to write the clean, human-readable podcast script (generate_clean_script).
SCRIPT_MODEL = "gpt-5.5"

# Model used to rewrite acronyms/abbreviations phonetically for TTS (optimize_script_for_audio).
ABBREVIATION_MODEL = "gpt-5.4"

# Model used to synthesize the audio (text_to_speech).
TTS_MODEL = "gpt-4o-mini-tts"

# Voice used for the TTS audio.
TTS_VOICE = "alloy"
