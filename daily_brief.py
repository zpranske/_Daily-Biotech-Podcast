import feedparser
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
import anthropic
import os
import datetime
import re

import config

# --- CONFIGURATION ---
# Script generation runs on Claude (Anthropic); TTS + abbreviation still use OpenAI.
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

RSS_URL = "https://www.fiercebiotech.com/rss/biotech/xml"

# Prompts live in plain-text files under prompts/ so they can be edited
# without touching this script.
PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")

# Permanent, git-committed archive of every generated episode (full transcripts).
# Kept as a human-readable record; it is NO LONGER the context window.
ARCHIVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "archive")

# Git-committed folder of condensed ~100-word "context_summary" notes, one per
# episode. The workflow checks the repo out fresh each run, so these summaries
# are already on disk and act as the lightweight "context window" fed to the
# script model — far cheaper than re-feeding whole transcripts.
SUMMARIES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "summaries")

# Beta-testing mode: write and send the script only. Skips the phonetic rewrite,
# TTS, and archive, so test runs don't affect the context window or dedupe.
SCRIPT_ONLY = os.environ.get("SCRIPT_ONLY", "").lower() in ("1", "true", "yes")

client = OpenAI(api_key=OPENAI_API_KEY)
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def load_prompt(filename):
    """Loads a prompt's text from the prompts/ directory."""
    with open(os.path.join(PROMPTS_DIR, filename), "r", encoding="utf-8") as f:
        return f.read()


def load_recent_summaries(n=config.CONTEXT_WINDOW_EPISODES):
    """Reads the most recent n daily context summaries.

    Returns a list of dicts (oldest first): {"date", "sources", "summary"}.
    A missing/empty summaries folder just yields an empty list, so the first
    runs after switching over (before any summaries exist) work fine.
    """
    if n <= 0 or not os.path.isdir(SUMMARIES_DIR):
        return []

    files = sorted(f for f in os.listdir(SUMMARIES_DIR) if f.endswith(".md"))
    episodes = []
    for filename in files[-n:]:
        with open(os.path.join(SUMMARIES_DIR, filename), "r", encoding="utf-8") as f:
            content = f.read()

        # Format written by save_context_summary(): a "## Sources" block of
        # "- Title | URL" lines, then a "## Summary" block.
        if "## Summary" in content:
            header, summary = content.split("## Summary", 1)
        else:
            header, summary = content, ""

        sources = []
        for line in header.splitlines():
            line = line.strip()
            if line.startswith("- ") and " | " in line:
                _, url = line[2:].rsplit(" | ", 1)
                sources.append(url.strip())

        episodes.append({
            "date": filename[:-3],  # strip ".md"
            "sources": sources,
            "summary": summary.strip(),
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
        f"--- EPISODE {ep['date']} ---\n{ep['summary']}" for ep in episodes
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


def save_context_summary(date, sources, summary):
    """Writes the condensed context_summary record for one episode.

    Same shape as save_archive (a "## Sources" block, then a "## Summary"
    block), so load_recent_summaries can parse it and still dedupe by URL.
    """
    os.makedirs(SUMMARIES_DIR, exist_ok=True)
    lines = [f"# Context Summary — {date}", "", "## Sources", ""]
    lines += [f"- {title} | {url}" for title, url in sources]
    lines += ["", "## Summary", "", summary, ""]

    path = os.path.join(SUMMARIES_DIR, f"{date}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Saved context summary to {path}")
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

    # Claude takes instructions in a top-level `system` parameter (a list of
    # text blocks), not as "system" messages in the conversation. The persona
    # prompt goes first; the recent-coverage context (if any) follows it.
    system_blocks = [{"type": "text", "text": neuro_prompt}]

    if recent_context:
        system_blocks.append({
            "type": "text",
            "text": (
                "RECENT COVERAGE CONTEXT — below are condensed summaries of the last "
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

    response = anthropic_client.beta.messages.create(
        model=config.SCRIPT_MODEL,
        # Must cover reasoning tokens + the script — see config.SCRIPT_MAX_TOKENS.
        max_tokens=config.SCRIPT_MAX_TOKENS,
        output_config={"effort": config.SCRIPT_EFFORT},
        # If a safety classifier ever declines, transparently retry on another
        # Claude model instead of failing the run. Remove `betas`/`fallbacks`
        # (and switch to anthropic_client.messages.create) if you don't want it.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=system_blocks,
        messages=[
            {
                "role": "user",
                "content": f"Here is the raw text from today's top articles:\n\n{raw_text}",
            }
        ],
    )

    # Log usage + stop reason so cost and truncation are visible in the run log.
    usage = response.usage
    print(
        f"Claude usage — stop_reason={response.stop_reason}, "
        f"input={usage.input_tokens} tok, output={usage.output_tokens} tok"
    )

    if response.stop_reason == "refusal":
        detail = getattr(response.stop_details, "explanation", "") or ""
        print(f"⚠️  Claude declined to generate the script. {detail}")
        return "The script could not be generated today (model declined the request)."

    # The response is a list of content blocks; grab the text ones (adaptive
    # thinking may also emit empty `thinking` blocks, which we skip).
    script = "".join(block.text for block in response.content if block.type == "text")

    # Guard: if the response was truncated mid-reasoning (stop_reason "max_tokens")
    # there may be no visible script text. Don't silently write/send an empty file.
    if not script.strip():
        print(
            "⚠️  Claude returned no script text "
            f"(stop_reason={response.stop_reason}). "
            "Raise config.SCRIPT_MAX_TOKENS or lower config.SCRIPT_EFFORT."
        )
        return (
            "Script generation returned no text this run "
            f"(stop_reason={response.stop_reason}). "
            "This usually means max_tokens was exhausted by reasoning — "
            "raise SCRIPT_MAX_TOKENS or lower SCRIPT_EFFORT."
        )

    return script


def generate_context_summary(clean_script):
    """Condenses ONE day's script into a ~100-word topic summary.

    Saved to SUMMARIES_DIR and used as lightweight 'recent coverage' context on
    future runs, instead of re-feeding whole transcripts. Runs on a cheap Claude
    model with thinking off — it's a trivial extraction task.
    """
    if not clean_script.strip():
        return ""

    summary_prompt = load_prompt("summary_prompt.txt")

    response = anthropic_client.messages.create(
        model=config.SUMMARY_MODEL,
        max_tokens=512,
        thinking={"type": "disabled"},  # trivial task — keep it cheap + fast
        output_config={"effort": "low"},
        system=summary_prompt,
        messages=[{"role": "user", "content": clean_script}],
    )

    return "".join(block.text for block in response.content if block.type == "text").strip()

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
    
    # 1. Send Audio (skipped in SCRIPT_ONLY mode)
    if audio_file:
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
            caption = f"{'[BETA] ' if SCRIPT_ONLY else ''}Transcript {datetime.date.today()}"
            payload = {'chat_id': TELEGRAM_CHAT_ID, 'caption': caption}
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

    # 1b. Load recent summaries — used both as generation context and to skip
    #     articles we've already covered.
    recent_episodes = load_recent_summaries()
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

    if SCRIPT_ONLY:
        print("SCRIPT_ONLY mode: skipping archive, TTS, and audio.")
        send_via_telegram(None, transcript_filename)
        print("Done!")
        return

    # 3b. Write the permanent archive record (committed by the workflow).
    today = datetime.date.today().isoformat()
    save_archive(today, scraped_sources, clean_script)

    # 3c. Condense today's script into a context_summary for future runs.
    print("Generating context summary...")
    summary = generate_context_summary(clean_script)
    if summary:
        save_context_summary(today, scraped_sources, summary)
    else:
        print("⚠️  Empty context summary; skipping save.")

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












