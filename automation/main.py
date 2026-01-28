import os
import json
import requests
import feedparser
import time
import re
import random
import logging
import warnings 
from datetime import datetime
from slugify import slugify
from io import BytesIO
from PIL import Image, ImageEnhance
from groq import Groq

# --- 🟢 LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("automation.log"),
        logging.StreamHandler()
    ]
)

# --- SUPPRESS WARNINGS ---
warnings.filterwarnings("ignore", category=FutureWarning, module="google.api_core")

# --- 🟢 GOOGLE INDEXING LIB ---
try:
    from oauth2client.service_account import ServiceAccountCredentials
    from googleapiclient.discovery import build
    GOOGLE_LIB_INSTALLED = True
except ImportError:
    logging.warning("⚠️ Google API Library not found. Install with: pip install google-api-python-client oauth2client")
    GOOGLE_LIB_INSTALLED = False

# --- 🟢 CONFIGURATION ---
GROQ_KEYS_RAW = os.environ.get("GROQ_API_KEY", "") 
GROQ_API_KEYS = [k.strip() for k in GROQ_KEYS_RAW.split(",") if k.strip()]
GOOGLE_JSON_KEY = os.environ.get("GOOGLE_INDEXING_KEY", "") 

WEBSITE_URL = "https://glitz-daily-news.vercel.app" 
INDEXNOW_KEY = "5b3e50c6d7b845d3ba6768de22595f94" 

if not GROQ_API_KEYS:
    logging.critical("❌ FATAL ERROR: Groq API Key is missing!")
    exit(1)

# --- 🟢 CONSTANTS & SETTINGS ---
TARGET_PER_SOURCE = 2     
COOLDOWN_SECONDS = 25  # Ditambah biar lebih aman
AUTHOR_NAME = "Glitz Editorial Desk"

CONTENT_DIR = "content/articles"
IMAGE_DIR = "static/images"
DATA_DIR = "automation/data"
MEMORY_FILE = f"{DATA_DIR}/link_memory.json"
USED_IMAGES_FILE = f"{DATA_DIR}/used_images.json"

RSS_SOURCES = {
    "Viral Trends US": "https://trends.google.com/trending/rss?geo=US&category=4",
    "Entertainment Headlines": "https://news.google.com/rss/headlines/section/topic/ENTERTAINMENT?hl=en-US&gl=US&ceid=US:en",
    "TV & Movies": "https://news.google.com/rss/search?q=movies+tv+shows+streaming+news&hl=en-US&gl=US&ceid=US:en"
}

AUTHORITY_MAP = {
    "Variety": "https://variety.com",
    "The Hollywood Reporter": "https://www.hollywoodreporter.com",
    "Rolling Stone": "https://www.rollingstone.com",
    "Billboard": "https://www.billboard.com",
    "Deadline": "https://deadline.com",
    "TMZ": "https://www.tmz.com",
    "E! Online": "https://www.eonline.com",
    "People": "https://people.com"
}

# Update User Agent lebih modern
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"
]

# 🟢 DATABASE GAMBAR STABIL (Updated Fresh Links)
RAW_IMAGE_DB = {
    "General": [
        "https://images.unsplash.com/photo-1492684223066-81342ee5ff30?w=1200&q=95",
        "https://images.unsplash.com/photo-1516280440614-6697288d5d38?w=1200&q=95",
        "https://images.unsplash.com/photo-1478720568477-152d9b164e63?w=1200&q=95",
        "https://images.unsplash.com/photo-1598899134739-24c46f58b8c0?w=1200&q=95",
        "https://images.unsplash.com/photo-1505686994434-e3cc5abf1330?w=1200&q=95",
        "https://images.unsplash.com/photo-1514525253440-b393452e8d26?w=1200&q=95",
        "https://images.unsplash.com/photo-1499364615650-ec38552f4f34?w=1200&q=95",
        # Tambahan Baru:
        "https://images.unsplash.com/photo-1574375927938-d5a98e8ffe85?w=1200&q=95", 
        "https://images.unsplash.com/photo-1522869635100-1f4906a1f07d?w=1200&q=95",
        "https://images.unsplash.com/photo-1593784697956-14f46924c560?w=1200&q=95",
        "https://images.unsplash.com/photo-1542751371-adc38448a05e?w=1200&q=95",
        "https://images.unsplash.com/photo-1538481199705-c710c4e965fc?w=1200&q=95",
        "https://images.unsplash.com/photo-1515634928627-2a4e0dae3ddf?w=1200&q=95",
        "https://images.unsplash.com/photo-1496747611176-843222e1e57c?w=1200&q=95",
        "https://images.unsplash.com/photo-1533174072545-e8d4aa97edf9?w=1200&q=95"
    ]
}

# --- 🟢 MEMORY & UTILS ---
def load_json_file(filepath):
    if not os.path.exists(filepath): return {}
    try:
        with open(filepath, 'r') as f: return json.load(f)
    except: return {}

def save_json_file(filepath, data):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w') as f: json.dump(data, f, indent=2)

def save_link_to_memory(title, slug):
    memory = load_json_file(MEMORY_FILE)
    memory[title] = f"/{slug}/"
    if len(memory) > 100: memory = dict(list(memory.items())[-100:])
    save_json_file(MEMORY_FILE, memory)

def is_image_used(url):
    used = load_json_file(USED_IMAGES_FILE)
    return url in used.values()

def mark_image_as_used(url, slug):
    used = load_json_file(USED_IMAGES_FILE)
    used[slug] = url
    save_json_file(USED_IMAGES_FILE, used)

def clean_camel_case(text):
    if not text: return ""
    text = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()

def repair_json(json_str):
    try:
        json_str = re.sub(r'```json\s*', '', json_str)
        json_str = re.sub(r'\s*```', '', json_str)
        return json.loads(json_str)
    except: return None

def get_internal_links():
    memory = load_json_file(MEMORY_FILE)
    items = list(memory.items())
    if not items: return ""
    count = min(len(items), 3)
    items = random.sample(items, count)
    return "\n".join([f"- [{title}]({url})" for title, url in items])

def get_external_sources_formatted():
    keys = list(AUTHORITY_MAP.keys())
    selected_keys = random.sample(keys, 2)
    formatted_list = []
    for key in selected_keys:
        url = AUTHORITY_MAP[key]
        formatted_list.append(f"{key} ({url})")
    return ", ".join(formatted_list)

# --- 🟢 IMAGE ENGINE (STRICT FILTER) ---
def get_unique_stock_image():
    target_list = RAW_IMAGE_DB["General"]
    random.shuffle(target_list)
    for url in target_list:
        if not is_image_used(url): return url
    return random.choice(target_list)

def download_and_process_image(url, path, is_ai=False):
    try:
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        r = requests.get(url, headers=headers, timeout=30)
        
        # 🛡️ FILTER AGRESIF (UPDATED)
        # Kita naikkan batas minimum file jadi 80KB (80000 bytes).
        # Gambar error Pollinations pixel art biasanya < 60KB.
        # Foto asli HD > 100KB.
        # Khusus untuk AI, kita cek size dengan ketat. Untuk Stock, kita lebih longgar.
        
        if is_ai and len(r.content) < 80000:
            logging.warning(f"      ⚠️ AI Image too small ({len(r.content)} bytes). REJECTED.")
            return False
            
        # Untuk stock image, batas bawah lebih rendah karena kompresi Unsplash bagus
        if not is_ai and len(r.content) < 10000:
             logging.warning("      ⚠️ Stock Image corrupt. Skipping.")
             return False

        if r.status_code == 200:
            img = Image.open(BytesIO(r.content)).convert("RGB")
            # Resize ke standar Discover
            img = img.resize((1200, 675), Image.Resampling.LANCZOS)
            enhancer = ImageEnhance.Color(img)
            img = enhancer.enhance(1.1)
            img.save(path, "WEBP", quality=85)
            return True
    except Exception as e:
        logging.error(f"      ❌ Image Download Error: {e}")
    return False

def generate_image_hybrid(query, slug):
    filename = f"{slug}.webp"
    filepath = os.path.join(IMAGE_DIR, filename)
    public_path = f"/images/{filename}"
    
    if os.path.exists(filepath): return public_path

    logging.info(f"🎨 Processing Image for: {slug}...")

    # --- LANGKAH 1: COBA AI GENERATOR ---
    try:
        clean_query = re.sub(r'[^a-zA-Z0-9\s]', '', query)[:150]
        safe_prompt = requests.utils.quote(f"cinematic photo of {clean_query}, realistic, 4k, detailed news photography")
        seed = random.randint(1, 999999)
        
        ai_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=1280&height=720&nologo=true&model=flux-realism&seed={seed}"
        
        logging.info("      🤖 Attempting AI Generation (Strict Filter 80KB)...")
        if download_and_process_image(ai_url, filepath, is_ai=True):
            logging.info("      ✅ AI Image Created Successfully")
            return public_path
        else:
             logging.info("      ❌ AI Image Rejected (Rate Limit/Quality).")
            
    except Exception as e:
        logging.warning(f"      ⚠️ AI Gen Failed: {e}")

    # --- LANGKAH 2: FALLBACK KE STOCK (PASTI JALAN) ---
    logging.info("      🔄 Switching to High-Quality Stock Image...")
    stock_url = get_unique_stock_image()
    
    if download_and_process_image(stock_url, filepath, is_ai=False):
        mark_image_as_used(stock_url, slug)
        logging.info("      ✅ Stock Image Applied")
        return public_path

    return "/images/default-glitz.jpg"

# --- 🟢 INDEXING API ---
def submit_to_indexnow(url):
    try:
        endpoint = "https://api.indexnow.org/indexnow"
        host = WEBSITE_URL.replace("https://", "").replace("http://", "")
        data = {
            "host": host,
            "key": INDEXNOW_KEY,
            "keyLocation": f"https://{host}/{INDEXNOW_KEY}.txt",
            "urlList": [url]
        }
        requests.post(endpoint, json=data, timeout=10)
        logging.info("      🚀 IndexNow Submitted")
    except Exception as e:
        logging.warning(f"      ⚠️ IndexNow Failed: {e}")

def submit_to_google(url):
    if not GOOGLE_LIB_INSTALLED or not GOOGLE_JSON_KEY:
        return
    try:
        creds_dict = json.loads(GOOGLE_JSON_KEY)
        SCOPES = ["https://www.googleapis.com/auth/indexing"]
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPES)
        service = build("indexing", "v3", credentials=credentials)
        body = {"url": url, "type": "URL_UPDATED"}
        service.urlNotifications().publish(body=body).execute()
        logging.info("      🚀 Google Indexing Submitted")
    except Exception as e:
        logging.warning(f"      ⚠️ Google Indexing Failed: {e}")

# --- 🤖 AI WRITER ENGINE ---
def call_groq_api(messages, model="llama-3.3-70b-versatile", response_format=None):
    for attempt in range(3):
        try:
            api_key = random.choice(GROQ_API_KEYS)
            client = Groq(api_key=api_key)
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 6000
            }
            if response_format: kwargs["response_format"] = response_format
            chat = client.chat.completions.create(**kwargs)
            return chat.choices[0].message.content
        except Exception as e:
            logging.warning(f"      ⚠️ Groq API Error (Retry {attempt+1}): {e}")
            time.sleep(5)
    return None

def get_metadata(title, summary):
    prompt = f"""
    Analyze Trending Topic: "{title}"
    Context: "{summary[:300]}"
    
    Task: Create a Viral, Click-worthy Title for Google Discover.
    Style: "Explainer", "What Happened", or "Why it Matters". 
    NO Clickbait. NO CamelCase.

    Return JSON ONLY:
    {{
        "title": "Compelling Title Here",
        "category": "Entertainment",
        "description": "Engaging summary under 160 chars for SEO",
        "keywords": ["keyword1", "keyword2"]
    }}
    """
    res = call_groq_api([{"role": "user", "content": prompt}], response_format={"type": "json_object"})
    return repair_json(res) if res else None

def write_article(metadata, summary, internal_links, external_sources):
    prompt = f"""
    You are a Senior Entertainment Journalist. Write a 800-word article.
    
    TOPIC: {metadata['title']}
    CONTEXT: {summary}
    
    STRUCTURE RULES (Strict Markdown):
    1. **Introduction**: Hook the reader immediately. 5W1H (Who, What, Where, When, Why).
    2. **The Details** (H2): Deep dive into the story.
    3. **Why It Matters** (H2): Analysis of the impact.
    4. **More News** (H2): EXACTLY paste this list:\n{internal_links}
    5. **Industry Insight** (H2): Mention {external_sources} naturally in the text with hyperlinks.
    6. **Key Facts** (H2): Create a Markdown Table of key events/people.
    7. **FAQ** (H2): 3 common questions and answers.

    Tone: Professional, Engaging, Insightful.
    """
    return call_groq_api([{"role": "user", "content": prompt}])

def repair_markdown(text):
    if not text: return ""
    text = text.replace("###", "\n\n###").replace("##", "\n\n##")
    text = re.sub(r'(?<!\n)\s-\s\[', '\n\n- [', text) 
    return text

# --- MAIN AUTOMATION ---
def main():
    logging.info("🎬 Starting Glitz Automation (Strict Filter Edition)...")
    os.makedirs(CONTENT_DIR, exist_ok=True)
    os.makedirs(IMAGE_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)

    generated_count = 0

    for source_name, url in RSS_SOURCES.items():
        logging.info(f"\n📡 Scanning: {source_name}...")
        try:
            feed = feedparser.parse(url)
            if not feed.entries:
                logging.warning("      ⚠️ No entries found.")
                continue
        except Exception as e:
            logging.error(f"      ❌ Feed Error: {e}")
            continue

        source_count = 0
        for entry in feed.entries:
            if source_count >= TARGET_PER_SOURCE: break
            
            clean_title = clean_camel_case(entry.title.split(" - ")[0])
            logging.info(f"   🔥 Analyze: {clean_title[:40]}...")

            meta = get_metadata(clean_title, entry.summary)
            if not meta: continue

            slug = slugify(meta['title'])
            filepath = os.path.join(CONTENT_DIR, f"{slug}.md")

            if os.path.exists(filepath): continue

            int_links = get_internal_links()
            ext_sources = get_external_sources_formatted()
            
            raw_content = write_article(meta, entry.summary, int_links, ext_sources)
            if not raw_content: continue

            final_content = repair_markdown(raw_content)
            parts = final_content.split("\n\n")
            if len(parts) > 4: parts.insert(3, "\n{{< ad >}}\n")
            final_content = "\n\n".join(parts)

            img_query = meta['keywords'][0] if meta['keywords'] else meta['title']
            img_path = generate_image_hybrid(img_query, slug)

            date_now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+07:00")
            
            md_file = f"""---
title: "{meta['title'].replace('"', "'")}"
date: {date_now}
author: "{AUTHOR_NAME}"
categories: ["{meta['category']}"]
tags: {json.dumps(meta['keywords'])}
featured_image: "{img_path}"
featured_image_alt: "{meta['title']}"
description: "{meta['description'].replace('"', "'")}"
draft: false
slug: "{slug}"
url: "/{slug}/"
---

{final_content}

---
*Sources: Analysis based on trending reports.*
"""
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(md_file)
            
            save_link_to_memory(meta['title'], slug)
            logging.info(f"      ✅ Published: {slug}")
            
            # Indexing
            full_url = f"{WEBSITE_URL}/{slug}/"
            submit_to_indexnow(full_url)
            submit_to_google(full_url)
            
            source_count += 1
            generated_count += 1
            
            logging.info(f"      ⏳ Cooldown {COOLDOWN_SECONDS}s...")
            time.sleep(COOLDOWN_SECONDS)

    logging.info(f"\n🎉 DONE! Generated {generated_count} articles.")

if __name__ == "__main__":
    main()
