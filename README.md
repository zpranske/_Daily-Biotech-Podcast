#  AI RSS Feed Podcast Generator

Automated pipeline that scrapes daily news from an RSS feed, uses AI to summarize the articles into a podcast, generates audio using text to speech, and delivers the final MP3 and text transcript directly to your phone via Telegram.

Currently configured for Fierce Biotech news, but easily customizable for any RSS feed and any industry.

## Setup Guide

Follow these steps to fork this project and set it up for your own personal use. It takes about 10 minutes and requires no server hosting.
Note: The cost per run is ~40 cents as of March 2026. This can possibly be reduced slightly by removing the TTS assistant call within the main script, or significantly by not using TTS and delivering a text-only script.

### 1. Prerequisites
You will need three things before you start. Instructions for getting these are below.
1. An OpenAI API Key (Make sure your account is funded with a few dollars, as the API requires prepaid credits)
2. A Telegram Bot Token
3. Your personal Telegram Chat ID

### 2a. Get your OpenAI API Key
0. Create an OpenAI account, if you don't have one yet
1. Go to platform.openai.com/api-keys
2. Create a new secret key, and call it whatever you want (e.g. "Podcast Bot"). This is your **OPENAI_API_KEY**

### 2b. Create Your Telegram Bot
0. Create a Telegram account, if you don't have one yet
1. Open Telegram and search for "BotFather" (the official bot creation tool)
2. Send the message '/newbot' and follow the prompts to give your bot a name and username. Call it whatever you want; e.g. "FierceSyncBot"
3. BotFather will give you an HTTP API Token (it looks like '123456789:ABCdefGHIjklmNoPQRstuvwxyz'). This is your **TELEGRAM_TOKEN**
4. **Important:** Search for your newly created bot's username in Telegram and click Start (or send it a message)

### 2c. Get Your Personal Telegram Chat ID
1. In Telegram, search for "@GetMyIDBot"
2. Click Start or send it a message
3. It will reply with your personal ID number (e.g., '123456789'). This is your **TELEGRAM_CHAT_ID**

### 3. Fork and Configure the Repository
1. Fork this repository to copy it to your GitHub
2. In your forked repository, go to Settings -> Secrets and variables -> Actions
3. Click "New repository secret" and add the following three secrets exactly as spelled:
  **OPENAI_API_KEY**: Paste your OpenAI API key here
  **TELEGRAM_TOKEN**: Paste your BotFather token here
  **TELEGRAM_CHAT_ID**: Paste your personal ID number here

### 4. Enable GitHub Actions
1. Go to the **Actions** tab in your repository
2. GitHub disables workflows on forked repos by default. Click **"I understand my workflows, go ahead and enable them"**
3. You can test the script immediately by selecting the workflow on the left and clicking **Run workflow**. Run it on the main branch.

---

## Customization

You can easily tweak this script for your specific needs by editing 'daily_brief.py':

* **Change the News Source:** Update the **RSS_URL** variable at the top of the script to any valid RSS feed.
* **Change the Podcast Persona:** Locate the **neuro_prompt** variable inside the 'generate_clean_script' function and rewrite the instructions to do what you want it to do.
* **Change the Voice:** Look for 'voice="onyx"' inside the 'text_to_speech' function. See available voices here: https://developers.openai.com/api/docs/guides/text-to-speech/. You can also custom prompt it to tweak pacing and tone –– this is best tested using openai.fm first.
* **Change the Schedule:** Edit the '.yml' file in the '.github/workflows/' directory. Modify the 'cron' string to change when the podcast runs (this is a standardized format and you can find many examples online).

## Dependencies
* 'requests'
* 'beautifulsoup4'
* 'feedparser'
* 'openai'

*(These are handled automatically by 'requirements.txt' via GitHub Actions).*
