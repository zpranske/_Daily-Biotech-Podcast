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
        Remember, however, that the user will often be listening to the podcast while somewhat distracted. Do not hesitate to digress, add context, repeat key points, or review lower level biology concepts to ensure understanding.
     
        Your Goal: Summarize these news items into a 1250-1750 spoken-word podcast script. Where helpful, act as a tutor, providing scientific context from your own knowledge beyond what's in the article.
     
        VOICE (this is a podcast, not a memo — read it aloud in your head as you write):
            1. Write like a sharp, curious person talking to a smart friend, not like a report. Vary sentence length: let some sentences run long and discursive, then cut to something short. Monotone rhythm is the enemy; a script where every sentence is the same length and shape reads as "dry" even when the content is good.
            2. Concrete specifics are what make it lively — the actual number, the company name, the size of the deal, the effect size, the name of the target. Reach for the specific detail rather than the generic summary. "They missed the primary endpoint by a hair — p of 0.06" beats "the trial had mixed results."
            3. You can have a personality. A wry aside, a moment of genuine enthusiasm when something is actually cool, a flicker of doubt when a claim is thin. Don't perform it constantly, but don't suppress it into neutrality either.
            4. Surface the insider read. The user wants to converse with others in biotech, which means knowing not just the facts but how people in the industry will actually interpret the news — what the smart-money reaction is, what the quiet implication is. Give him that subtext explicitly.
               BUT: vary how you deliver it. Do NOT lean on the "the headline is X, but the real story is Y" construction — it is a crutch, and using it more than once (if at all) makes the whole episode feel formulaic. Find different ways in: a question, a comparison to a prior deal, a "watch for," an aside about who's quietly nervous, a plain statement of the implication. The skill is the insight, not the sentence template.
            5. Skepticism where warranted. If a Phase 2 readout is being spun harder than the effect size justifies, say it. If a deal structure is mostly biobucks with a tiny upfront, flag it. He wants a read, not a recap.
            6. Running threads across the roundup. If two stories rhyme — both GLP-1 adjacencies, both companies pivoting off amyloid, both Chinese-originated assets getting licensed west — connect them explicitly. A roundup is more than the sum of its items when the items talk to each other.
            7. Enjoy the jargon instead of apologizing for it. "A Series B, which in biotech-speak basically means 'we showed the drug does something in a dish or a mouse and now we need real money to find out if it works in people'" is better than a dry parenthetical definition.
     
        ANTI-PATTERNS (avoid these; they make the script feel generic):
            - The "headline is X, real story is Y" template (see VOICE point 4).
            - Filler runway phrases: "buckle up," "let's dive in," "without further ado," "the bottom line is," "at the end of the day."
            - Overusing "quietly" / "under the radar" to manufacture intrigue.
            - Hedging everything into mush. Commit to a read.
            - Ending every story on the same kind of beat. Vary your landings.
     
        PRIORITIES (in order):
            1. CNS, neurology, psychiatry, novel modalities — lead with these, go deeper on the science. The user is a synapse-focused neurobiologist; assume he wants the mechanism and plenty of context.
            2. Microscopy, bioimaging, biosensor platforms, especially advanced microscopy — flag anything relevant even if it's a small story.
            3. mRNA, XNA, glycan, ligand-receptor biology, and nucleic acid therapies.
            4. Everything else — cover only if it's genuinely interesting or strategically important (big M&A, a platform collapse, a regulatory shift that changes the landscape).
     
        STRUCTURE: Start with some variant of "Good morning. Here is your Fierce Biotech update for (insert today's date)." Then a ~150 word "TL;DR" touching on the single most important headline and quickly sketching the major trends. End with "And that's the roundup for today."
     
        OTHER RULES:
            1. Do not write lists or bullet points. Weave the stories into an engaging narrative.
            2. You do not need to summarize every story — only those worth covering. Pick the 6-8 most relevant and/or impactful.
            3. Length should be at least 1250 words.
        """

    response = client.chat.completions.create(
        model="gpt-5.5",
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
    - "siRNA" -> "s-i-RNA" (Read as letters)
    - "circRNA" -> "circ-RNA" (Combination of letters and words)
    - "AAV" -> "A-A-V" (Read as letters)
    - "EGFR" -> "E-G-F-R" (Read as letters)
    - "NMDAR" -> "N-M-D-A-R" or "NMDA receptor"
    - "smFISH" -> "s-m-fish" (Combination of letters and words)
    - "GABAR" -> "Gaba-R" or "GABA receptor" (Combination of letters and words)
    - "CAR-T" -> "car T" (Combination of letters and words)
    - "GCase" -> "G-C-ace"
    - "Aβ" -> "A-beta" or "amyloid beta" (do this with any greek characters)
    – "PET" -> "Pet" (pronounced as a word)
    – "COVID" -> "co-vid" (pronounced as a word)
    – "BBB" -> "blood brain barrier"
    - "HER2" -> "Her-two" (pronounced as a word)
    - "VEGF" -> "Vedge-eff" (pronounced as a word)
    - "GAD" -> "Gad" (pronounced as a word)
    - "Sanofi" -> "Sun-OH-fee" (not an acronym, TTS just often gets this wrong and I want to make sure it's pronounced correctly)

    2. Also modify certain syntactical abbreviations as needed, using good judgment to determine what will read most naturally.

    EXAMPLES:
    - "$2-4 billion" -> "two to four billion dollars"
    - "LY388496324" (a drug candidate that's too early-stage to have a name) -> "LY3884 for short" (the first time it's read) or "LY3884" (subsequent times)
    - When you see something like "stiff person syndrome (SPS)", add a comma after "stiff person syndrome"
    
    Output the full script with these modifications. Do not change the sentence structure or content.
    """

    response = client.chat.completions.create(
        model="gpt-5.4",
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
                    input=chunk,
                    instructions="""
                    You are a smart, engaged podcast host delivering a morning biotech briefing. Think of the energy of a good daily 
                    news podcast — warm, curious, slightly wry when the material calls 
                    for it — not the even-keeled neutrality of traditional radio news. 
                    
                    Vary your pacing. Move briskly through setup sentences and 
                    transitions; slow down on the interesting beat of each story — the 
                    surprising number, the company name, the punchline of a reframe. 
                    Don't land every sentence on the same note.
                    
                    When the script uses parentheticals or mid-sentence asides, treat 
                    them as asides: slightly quicker, slightly lower in pitch. Then return to full voice for the main thread.
                    
                    Let dry humor and mild skepticism come through when the writing 
                    invites it. Most of the time you're just delivering the news clearly and with genuine interest. 
                    
                    Speak slightly faster than you would normally (~1.3x). Importantly, save emphasis for important parts. Otherwise, don't over-emphasize or over-emote.
                    """
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












