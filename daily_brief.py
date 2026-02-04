import feedparser
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
import os
import datetime
import re

# --- CONFIGURATION ---
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

# Fierce Biotech RSS Feed URL
RSS_URL = "https://www.fiercebiotech.com/rss/biotech/xml"

client = OpenAI(api_key=OPENAI_API_KEY)

def get_latest_articles_from_rss():
    """Fetches the latest articles directly from the RSS feed."""
    print(f"Fetching news from {RSS_URL}...")
    feed = feedparser.parse(RSS_URL)
    
    if not feed.entries:
        print("Error: No entries found in RSS feed.")
        return []
    
    links = []
    print(f"Found {len(feed.entries)} entries. Grabbing top 5...")
    
    for entry in feed.entries[:5]:
        print(f" - Found: {entry.title}")
        links.append(entry.link)
        
    return links

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

def generate_script(raw_text):
    """Uses GPT-4o to synthesize the podcast script."""
    if not raw_text.strip():
        return "No news found today."

    neuro_prompt = """
    You are an expert biotech analyst briefing an imaging-focused Neurobiologist who specializes in synapse biology. 
    The user understands general biology (MOAs, pathways, receptors) but is unfamiliar with 'industry' terms (IPOs, Series B, PBMs, commercialization cliffs).
    
    Your Goal: Summarize these news items into a 10-minute spoken-word podcast script (~1000-1500 words).
    
    Guidelines:
    1. Tone: Conversational, high-level intellectual. Make it engaging, take opportunities to teach and explain "industry jargon" as appropriate.
    2. Translation: If a story is about a 'Series B raise', explain *what specific mechanism* or *target* that money will fund.
    3. Relevance: Emphasize in particular 1) anything related to CNS, neurology, or interesting novel modalities (top priority), 2) anything related to microscopy or imaging (if present) and 3) anything related to mRNA, XNA, glycans, or nucleic acid therapies.
    4. Structure: Start with "Good morning. Here is your Fierce Biotech update for (insert today's date)." End with "That's the roundup."
    5. Do not read lists. Weave the stories into a narrative.
    """

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": neuro_prompt},
            {"role": "user", "content": f"Here is the raw text from today's top articles:\n\n{raw_text}"}
        ]
    )
    return response.choices[0].message.content

def text_to_speech(script):
    """Generates MP3 using OpenAI TTS."""
    response = client.audio.speech.create(
        model="tts-1",
        voice="onyx", 
        input=script
    )
    response.stream_to_file("daily_update.mp3")
    return "daily_update.mp3"

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
    # 1. Get Links (RSS)
    links = get_latest_articles_from_rss()
    if not links:
        print("No articles found. Exiting.")
        return

    # 2. Scrape Text
    full_content = ""
    print(f"Scraping {len(links)} articles...")
    for link in links:
        print(f"Processing: {link}")
        text = scrape_article_text(link)
        if text:
            full_content += f"\n\n--- ARTICLE SOURCE: {link} ---\n{text}"

    if not full_content.strip():
        print("Scraped content is empty. Stopping.")
        return

    # 3. Generate Script
    print("Generating script with AI...")
    script = generate_script(full_content)
    
    # --- NEW: Save Script to File ---
    transcript_filename = "daily_brief.txt"
    with open(transcript_filename, "w", encoding="utf-8") as f:
        f.write(script)
    print("Transcript saved.")
    
    # 4. Generate Audio
    print("Synthesizing audio...")
    audio_path = text_to_speech(script)
    
    # 5. Send Both
    print("Sending to Telegram...")
    send_via_telegram(audio_path, transcript_filename)
    print("Done!")

if __name__ == "__main__":
    main()

