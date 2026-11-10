"""
Model and voice configuration.

Change the models or TTS voice here — no need to touch daily_brief.py.
"""

# Model used to write the clean, human-readable podcast script (generate_clean_script).
# This step runs on Anthropic's Claude API — use a Claude model id here.
SCRIPT_MODEL = "claude-sonnet-5-5"

# Reasoning effort for the script model: low | medium | high | xhigh | max.
# Higher effort = more thorough analysis (and more cost/latency). "medium" is a
# good balance for creative writing; bump to "high" if you want sharper takes.
SCRIPT_EFFORT = "high"

# Max tokens for the script response. IMPORTANT: on Claude this ceiling must
# cover BOTH the model's (billed, usually hidden) reasoning AND the visible
# script. A 1250-1750 word script is only ~2500 tokens, but higher SCRIPT_EFFORT
# spends more reasoning tokens — if this is too low, the response is truncated
# mid-reasoning and comes back with no script text at all. 16000 leaves ample
# headroom at any effort. Lower effort is the main lever to cut cost here.
SCRIPT_MAX_TOKENS = 16000

# Model used to rewrite acronyms/abbreviations phonetically for TTS (optimize_script_for_audio).
# Still on OpenAI for now — part of the TTS pipeline, which we haven't migrated yet.
ABBREVIATION_MODEL = "gpt-5.6-luna"

# Model used to synthesize the audio (text_to_speech).
TTS_MODEL = "gpt-4o-mini-tts"

# Voice used for the TTS audio.
TTS_VOICE = "alloy"

# How many recent episodes to load as "context" before writing a new script.
# These are fed to the script model so it can avoid repeating stories and
# connect today's news to running themes. Set to 0 to disable.
CONTEXT_WINDOW_EPISODES = 24
