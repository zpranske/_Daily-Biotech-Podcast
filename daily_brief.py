import feedparser
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
import os
import datetime
import re

import config

# --- CONFIGURATION ---
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

RSS_URL = "https://www.fiercebiotech.com/rss/biotech/xml"

# Prompts live in plain-text files under prompts/ so they can be edited
# without touching this script.
PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")

# Permanent, git-committed archive of every generated episode. The workflow
# checks the repo out fresh each run, so this doubles as the "context window":
# past transcripts are already on disk before we generate a new one.
ARCHIVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "archive")

client = OpenAI(api_key=OPENAI_API_KEY)


def load_prompt(filename):
    """Loads a prompt's text from the prompts/ directory."""
    with open(os.path.join(PROMPTS_DIR, filename), "r", encoding="utf-8") as f:
        return f.read()


def load_recent_archive(n=config.CONTEXT_WINDOW_EPISODES):
    """Reads the most recent n archived episodes for context.

    Returns a list of dicts (oldest first): {"date", "sources", "transcript"}.
    A missing/empty archive just yields an empty list, so the very first run
    works fine.
    """
    if n <= 0 or not os.path.isdir(ARCHIVE_DIR):
        return []

    files = sorted(f for f in os.listdir(ARCHIVE_DIR) if f.endswith(".md"))
    episodes = []
    for filename in files[-n:]:
        with open(os.path.join(ARCHIVE_DIR, filename), "r", encoding="utf-8") as f:
            content = f.read()

        # Format written by save_archive(): a "## Sources" block of
        # "- Title | URL" lines, then a "## Transcript" block.
        if "## Transcript" in content:
            header, transcript = content.split("## Transcript", 1)
        else:
            header, transcript = content, ""

        sources = []
        for line in header.splitlines():
            line = line.strip()
            if line.startswith("- ") and " | " in line:
                _, url = line[2:].rsplit(" | ", 1)
                sources.append(url.strip())

        episodes.append({
            "date": filename[:-3],  # strip ".md"
            "sources": sources,
            "transcript": transcript.strip(),
        })

    return episodes


def recent_source_urls(episodes):
    """Flat set of every source URL covered across the given episodes."""
    return {url for ep in episodes for url in ep["sources"]}


def build_recent_context(episodes):
    """Builds the 'recent coverage' block injected into the script prompt."""
    if not episodes:
        return ""
    return "\n\n".join(
        f"--- EPISODE {ep['date']} ---\n{ep['transcript']}" for ep in episodes
    )


def save_archive(date, sources, transcript):
    """Writes a permanent, git-committable record of one episode.

    `sources` is a list of (title, url) tuples for the articles actually used.
    """
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    lines = [f"# Daily Biotech Brief — {date}", "", "## Sources", ""]
    lines += [f"- {title} | {url}" for title, url in sources]
    lines += ["", "## Transcript", "", transcript, ""]

    path = os.path.join(ARCHIVE_DIR, f"{date}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Archived episode to {path}")
    return path

def get_latest_articles_from_rss():
    """Fetches the latest articles directly from the RSS feed."""
    print(f"Fetching news from {RSS_URL}...")
    feed = feedparser.parse(RSS_URL)
    
    if not feed.entries:
        print("Error: No entries found in RSS feed.")
        return []
    
    articles = []
    print(f"Found {len(feed.entries)} entries. Grabbing top 20...")

    for entry in feed.entries[:20]:
        print(f" - Found: {entry.title}")
        articles.append({"title": entry.title, "url": entry.link})

    return articles

def scrape_article_text(url):
    """Visits the link and scrapes the body text."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, "html.parser")
        
        paragraphs = soup.find_all('p')
        text = " ".join([p.get_text() for p in paragraphs])
        
        if len(text) < 200: 
            return ""
            
        return text[:3000] 
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return ""

def generate_clean_script(raw_text, recent_context=""):
    """Generates the readable text script for the user.

    `recent_context` is the transcripts of the last few episodes (see
    build_recent_context). When present, it's handed to the model so it can
    avoid repeating stories and connect today's news to running themes.
    """
    if not raw_text.strip():
        return "No news found today."

    neuro_prompt = load_prompt("neuro_prompt.txt")

    messages = [{"role": "system", "content": neuro_prompt}]

    if recent_context:
        messages.append({
            "role": "system",
            "content": (
                "RECENT COVERAGE CONTEXT — below are the transcripts of the last "
                "few episodes, oldest first. The listener has already heard these.\n"
                "Use them to:\n"
                "1. Avoid repeating stories. If today's articles overlap with something "
                "already covered, only bring it up if there's a genuinely new "
                "development, and make clear what's changed.\n"
                "2. Surface running threads. Connect today's headlines to ongoing "
                "storylines so recent news lands in the context of what else has been "
                "happening recently.\n"
                "Do NOT recap these prior episodes — reference them only where it adds "
                "context to today's news.\n\n"
                + recent_context
            ),
        })

    messages.append({
        "role": "user",
        "content": f"Here is the raw text from today's top articles:\n\n{raw_text}",
    })

    response = client.chat.completions.create(
        model=config.SCRIPT_MODEL,
        messages=messages,
    )
    return response.choices[0].message.content

def optimize_script_for_audio(script_text):
    """Rewrites acronyms phonetically so TTS pronounces them correctly."""
    
    print("Optimizing script for TTS pronunciation...")

    system_prompt = load_prompt("abbreviation_prompt.txt")

    response = client.chat.completions.create(
        model=config.ABBREVIATION_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": script_text}
        ]
    )
    return response.choices[0].message.content

def text_to_speech(script):
    """Generates MP3 using OpenAI TTS (Handles long scripts)."""
    max_length = 4096
    chunks = []
    
    if len(script) > max_length:
        print(f"Script is long ({len(script)} chars). Splitting into chunks...")
        current_chunk = ""
        for paragraph in script.split("\n"):
            if len(current_chunk) + len(paragraph) + 1 < max_length:
                current_chunk += paragraph + "\n"
            else:
                chunks.append(current_chunk)
                current_chunk = paragraph + "\n"
        if current_chunk:
            chunks.append(current_chunk)
    else:
        chunks = [script]

    output_filename = "daily_update.mp3"
    
    with open(output_filename, "wb") as f:
        for i, chunk in enumerate(chunks):
            if not chunk.strip(): continue
            
            print(f"Synthesizing audio part {i+1}/{len(chunks)}...")
            try:
                response = client.audio.speech.create(
                    model=config.TTS_MODEL,
                    voice=config.TTS_VOICE,
                    input=chunk,
                    instructions=load_prompt("tts_instructions.txt")
                )
                for audio_data in response.iter_bytes():
                    f.write(audio_data)
            except Exception as e:
                print(f"Error on chunk {i+1}: {e}")

    return output_filename

def send_via_telegram(audio_file, text_file):
    """Pushes the audio file AND the transcript to your phone."""
    url_audio = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendAudio"
    url_doc = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    
    print(f"Attempting to send to Chat ID: {TELEGRAM_CHAT_ID}")
    
    # 1. Send Audio
    try:
        with open(audio_file, 'rb') as audio:
            payload = {'chat_id': TELEGRAM_CHAT_ID, 'title': f"Biotech Update {datetime.date.today()}"}
            files = {'audio': audio}
            r = requests.post(url_audio, data=payload, files=files, timeout=30)
            if r.status_code == 200:
                print("✅ Audio sent successfully.")
            else:
                print(f"❌ Audio failed: {r.text}")
    except Exception as e:
        print(f"❌ Error sending audio: {e}")

    # 2. Send Transcript
    try:
        with open(text_file, 'rb') as doc:
            payload = {'chat_id': TELEGRAM_CHAT_ID, 'caption': f"Transcript {datetime.date.today()}"}
            files = {'document': doc}
            r = requests.post(url_doc, data=payload, files=files, timeout=30)
            if r.status_code == 200:
                print("✅ Transcript sent successfully.")
            else:
                print(f"❌ Transcript failed: {r.text}")
    except Exception as e:
        print(f"❌ Error sending transcript: {e}")

def main():
    # 1. Get articles (title + url)
    articles = get_latest_articles_from_rss()
    if not articles:
        print("No articles found. Exiting.")
        return

    # 1b. Load recent episodes — used both as generation context and to skip
    #     articles we've already covered.
    recent_episodes = load_recent_archive()
    seen_urls = recent_source_urls(recent_episodes)
    if seen_urls:
        before = len(articles)
        articles = [a for a in articles if a["url"] not in seen_urls]
        print(f"Skipped {before - len(articles)} article(s) already covered in the "
              f"last {len(recent_episodes)} episode(s).")

    # 2. Scrape Text (tracking which sources actually made it in)
    full_content = ""
    scraped_sources = []
    print(f"Scraping {len(articles)} articles...")
    for article in articles:
        url = article["url"]
        print(f"Processing: {url}")
        text = scrape_article_text(url)
        if text:
            scraped_sources.append((article["title"], url))
            full_content += f"\n\n--- ARTICLE SOURCE: {url} ---\n{text}"

    if not full_content.strip():
        print("Scraped content is empty. Stopping.")
        return

    # 3. Generate CLEAN Script (For Humans), grounded in recent coverage
    print("Generating clean script...")
    recent_context = build_recent_context(recent_episodes)
    clean_script = generate_clean_script(full_content, recent_context)

    # Save Readable Transcript
    transcript_filename = "daily_brief.txt"
    with open(transcript_filename, "w", encoding="utf-8") as f:
        f.write(clean_script)
    print("Clean transcript saved.")

    # 3b. Write the permanent archive record (committed by the workflow).
    today = datetime.date.today().isoformat()
    save_archive(today, scraped_sources, clean_script)

    # 4. Generate PHONETIC Script (For Robots)
    audio_script = optimize_script_for_audio(clean_script)
    
    # 5. Generate Audio from Phonetic Script
    print("Synthesizing audio...")
    audio_path = text_to_speech(audio_script)
    
    # 6. Send clean text and phonetic audio
    print("Sending to Telegram...")
    send_via_telegram(audio_path, transcript_filename)
    print("Done!")

if __name__ == "__main__":
    main()












