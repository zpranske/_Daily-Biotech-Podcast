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
    print(f"Found {len(feed.entries)} entries. Grabbing top 20...")
    
    for entry in feed.entries[:20]:
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

def generate_clean_script(raw_text):
    """Generates the readable text script for the user."""
    if not raw_text.strip():
        return "No news found today."

    neuro_prompt = """
    You are an expert biotech analyst briefing an imaging-focused Neurobiologist who specializes in synapse biology. 
    The user understands general biology (MOAs, pathways, receptors) but is unfamiliar with 'industry' and 'business' terms (Series B, PBMs, commercialization cliffs) except for basics (IPOs, mergers, layoffs).
    
    Your Goal: Summarize these news items into a 1000-1500 spoken-word podcast script. As necessary, dive into the science a bit or provide relevant context beyond what's in the article to ensure clear user understanding.
    
    Guidelines:
    1. Tone: Professional, slightly conversational, high-level intellectual. Take opportunities to teach and explain "industry jargon" as appropriate. 
    2. Translation: If a story is about a 'Series B raise', explain *what specific mechanism* or *target* that money will fund.
    3. Relevance: Emphasize in particular 1) anything related to CNS, neurology, or interesting novel modalities (top priority), 2) anything related to microscopy or bioimaging (if present) and 3) anything related to mRNA, XNA, glycans, or nucleic acid therapies.
    4. Structure: Start with "Good morning. Here is your Fierce Biotech update for (insert today's date)." Then begin with a ~250 word "TL;DR" version briefly touching on the most important headline of the day and quickly summarizing the major trends. End with "That's the roundup for today."
    5. Do not write lists or bullet points. Weave the stories into a narrative.
    6. You do not need to summarize every single story. Pick the 8-10 most relevant and/or impactful. 
    7. Length should be at least 1000 words.
    """

    response = client.chat.completions.create(
        model="gpt-5.1",
        messages=[
            {"role": "system", "content": neuro_prompt},
            {"role": "user", "content": f"Here is the raw text from today's top articles:\n\n{raw_text}"}
        ]
    )
    return response.choices[0].message.content

def optimize_script_for_audio(script_text):
    """Rewrites acronyms phonetically so TTS pronounces them correctly."""
    
    print("Optimizing script for TTS pronunciation...")
    
    system_prompt = """
    You are a Voice-Over Assistant. Your job is to format text for a Text-to-Speech engine.
    
    RULES: 1. Identify scientific acronyms and, if needed, rewrite them based on how they should be spoken.
    
    EXAMPLES:
    - "GABA" -> "GABA" (Pronounced as a word)
    - "CRISPR" -> "CRISPR" (Pronounced as a word)
    - "FAAH" -> "F-A-A-H" (Read as letters)
    - "scRNA" -> "s-c-RNA" (Read as letters)
    - "siRNA" -> "s-i-RNA"
    - "AAV" -> "A-A-V" (Read as letters)
    - "EGFR" -> "E-G-F-R" (Read as letters)
    - "NMDAR" -> "N-M-D-A-R" or "NMDA receptor"
    - "smFISH" -> "s-m-fish" (Combination of letters and words)
    - "GABAR" -> "Gaba-R" or "GABA receptor" (Combination of letters and words)
    - "CAR-T" -> "car-T" (Combination of letters and words)
    - "GCase" -> "G-C-ase"
    - "Aβ" -> "A-beta" or "amyloid beta" (do this with any greek characters)

    2. Also modify certain syntactical abbreviations as needed, using good judgment to determine what will read most naturally.

    EXAMPLES:
    - "$2-4 billion" -> "two to four billion dollars"
    - "LY388496324" (a drug candidate that's too early-stage to have a name) -> "LY3884 for short" (the first time it's read) or "LY3884" (subsequent times)
    - When you see something like "stiff person syndrome (SPS)", add a comma after "stiff person syndrome"
    
    Output the full script with these modifications. Do not change the sentence structure or content.
    """

    response = client.chat.completions.create(
        model="gpt-5.1",
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
                    model="gpt-4o-mini-tts",
                    voice="alloy", 
                    input=chunk
                    instructions="Speak conversationally and smoothly, as on an informative podcast or NPR-style news briefing."
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
    # 1. Get Links
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

    # 3. Generate CLEAN Script (For Humans)
    print("Generating clean script...")
    clean_script = generate_clean_script(full_content)
    
    # Save Readable Transcript
    transcript_filename = "daily_brief.txt"
    with open(transcript_filename, "w", encoding="utf-8") as f:
        f.write(clean_script)
    print("Clean transcript saved.")
    
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








