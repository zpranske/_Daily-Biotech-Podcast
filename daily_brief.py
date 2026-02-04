import imaplib
import email
from email.header import decode_header
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
import os
import datetime
import re

# --- CONFIGURATION ---
EMAIL_USER = os.environ["EMAIL_USER"]
EMAIL_PASS = os.environ["EMAIL_PASS"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

client = OpenAI(api_key=OPENAI_API_KEY)

def get_latest_email():
    """Connects to Gmail and fetches the latest Fierce Biotech email (Direct or Forwarded)."""
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(EMAIL_USER, EMAIL_PASS)
    mail.select("inbox")

    # Look back 3 days
    date = (datetime.date.today() - datetime.timedelta(days=3)).strftime("%d-%b-%Y")
    
    # Search for 'Fierce' in Subject (catches 'Fwd: Fierce...')
    status, messages = mail.search(None, f'(SUBJECT "Fierce" SINCE "{date}")')
    
    email_ids = messages[0].split()
    if not email_ids:
        print(f"No emails found with subject 'Fierce' since {date}.")
        return None

    # Fetch the latest one
    status, msg_data = mail.fetch(email_ids[-1], "(RFC822)")
    for response_part in msg_data:
        if isinstance(response_part, tuple):
            msg = email.message_from_bytes(response_part[1])
            print(f"Found Email Subject: {msg['subject']}")
            
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/html":
                        return part.get_payload(decode=True).decode()
            else:
                return msg.get_payload(decode=True).decode()
    return None

def extract_article_links(html_content):
    """Parses email HTML to find article links (Robust for Forwards)."""
    soup = BeautifulSoup(html_content, "html.parser")
    links = []
    
    # Keyword list to identify real articles vs ads/nav
    # We look for these words in the URL OR the link text
    keywords = ["fiercebiotech.com", "story", "article"]
    
    for a in soup.find_all('a', href=True):
        href = a['href']
        text = a.get_text().lower()
        
        # skip unsubscribe/social links
        if any(x in href.lower() for x in ["unsubscribe", "preferences", "twitter", "facebook", "linkedin"]):
            continue
            
        # If it's a fiercebiotech link (even if wrapped in a redirect)
        if "fiercebiotech.com" in href:
            links.append(href)
            
    # Remove duplicates and limit to 5
    unique_links = list(set(links))
    
    # Debug print to help us see what is happening
    print(f"DEBUG: Found {len(unique_links)} raw links. First 3: {unique_links[:3]}")
    
    return unique_links[:5]

def scrape_article_text(url):
    """Visits the link and scrapes the body text."""
    try:
        # User-Agent header tricks the website into thinking we are a real browser
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, "html.parser")
        
        paragraphs = soup.find_all('p')
        text = " ".join([p.get_text() for p in paragraphs])
        
        # If text is too short, scraping probably failed (paywall or bad layout)
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
    You are an expert biotech analyst briefing a Neurobiologist. 
    The user understands deep science (MOAs, pathways, receptors) but is unfamiliar with 'industry' terms (IPOs, Series B, PBMs, commercialization cliffs).
    
    Your Goal: Summarize these news items into a 5-minute spoken-word podcast script.
    
    Guidelines:
    1. Tone: Professional, slightly conversational, high-level intellectual.
    2. Translation: If a story is about a 'Series B raise', explain *what specific mechanism* or *target* that money will fund.
    3. Relevance: Highlight anything related to CNS, neurology, or interesting novel modalities.
    4. Structure: Start with "Good morning. Here is your Fierce Biotech update." End with "That's the roundup."
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

def send_via_telegram(audio_file):
    """Pushes the audio file to your phone."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendAudio"
    with open(audio_file, 'rb') as audio:
        payload = {'chat_id': TELEGRAM_CHAT_ID, 'title': f"Daily Biotech Update {datetime.date.today()}"}
        files = {'audio': audio}
        requests.post(url, data=payload, files=files)

def main():
    print("Checking email...")
    html = get_latest_email()
    if not html:
        print("No newsletter found today.")
        return

    print("Found newsletter. Extracting links...")
    links = extract_article_links(html)
    
    if not links:
        print("No articles found in the email. Stopping here.")
        return # STOP HERE to avoid crashing later

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

    print("Generating script with AI...")
    script = generate_script(full_content)
    
    print("Synthesizing audio...")
    audio_path = text_to_speech(script)
    
    print("Sending to Telegram...")
    send_via_telegram(audio_path)
    print("Done!")

if __name__ == "__main__":
    main()
