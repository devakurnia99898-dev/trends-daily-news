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

# --- 🟢 CONFIGURATION ---
GROQ_KEYS_RAW = os.environ.get("GROQ_API_KEY", "")
GROQ_API_KEYS = [k.strip() for k in GROQ_KEYS_RAW.split(",") if k.strip()]
GOOGLE_JSON_KEY = os.environ.get("GOOGLE_INDEXING_KEY", "") 

WEBSITE_URL = "https://trends-daily-news.netlify.app" 
INDEXNOW_KEY = "18753e66adf346f4bb2889ca1e3c7c51"

if not GROQ_API_KEYS:
    logging.critical("❌ FATAL ERROR: Groq API Key is missing!")
    exit(1)

# --- 🟢 CONSTANTS ---
TARGET_PER_SOURCE = 2 
MAX_RETRIES = 3

AUTHOR_PROFILES = [
    "Jessica Hart (Film Critic)", "Marcus Cole (Music Editor)",
    "Sarah Jenkins (Streaming Analyst)", "David Choi (K-Pop Insider)",
    "Amanda Lee (Celebrity News)", "Tom Baker (Gaming & Esports)",
    "The Pop Culture Desk"
]

VALID_CATEGORIES = [
    "Movies & Film", "TV Shows & Streaming", "Music & Concerts", 
    "Celebrity & Lifestyle", "Anime & Manga", "Gaming & Esports",
    "Pop Culture Trends"
]

RSS_SOURCES = {
    "Entertainment US": "https://news.google.com/rss/headlines/section/topic/ENTERTAINMENT?hl=en-US&gl=US&ceid=US:en",
    "Gaming News": "https://news.google.com/rss/search?q=gaming+news+esports&hl=en-US&gl=US&ceid=US:en",
    "Pop Culture": "https://news.google.com/rss/search?q=pop+culture+trends&hl=en-US&gl=US&ceid=US:en"
}

# 🟢 AUTHORITY SOURCES MAP (External Linking)
AUTHORITY_MAP = {
    "Variety": "https://variety.com",
    "The Hollywood Reporter": "https://www.hollywoodreporter.com",
    "Rolling Stone": "https://www.rollingstone.com",
    "Billboard": "https://www.billboard.com",
    "Deadline": "https://deadline.com",
    "IGN": "https://www.ign.com",
    "Rotten Tomatoes": "https://www.rottentomatoes.com",
    "Pitchfork": "https://pitchfork.com",
    "Vulture": "https://www.vulture.com",
    "Entertainment Weekly": "https://ew.com",
    "Polygon": "https://www.polygon.com",
    "Kotaku": "https://kotaku.com",
    "ScreenRant": "https://screenrant.com"
}

# 🟢 MASSIVE STOCK DATABASE (Unsplash HD) - Anti Error
# Saya perbanyak agar variatif karena kita matikan AI Generator
RAW_IMAGE_DB = {
    "Movies & Film": [
        "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=1200&q=90", 
        "https://images.unsplash.com/photo-1536440136628-849c177e76a1?w=1200&q=90",
        "https://images.unsplash.com/photo-1478720568477-152d9b164e63?w=1200&q=90",
        "https://images.unsplash.com/photo-1594909122845-11baa439b7bf?w=1200&q=90",
        "https://images.unsplash.com/photo-1517604931442-71053e683597?w=1200&q=90",
        "https://images.unsplash.com/photo-1440404653325-ab127d49abc1?w=1200&q=90",
        "https://images.unsplash.com/photo-1598899134739-24c46f58b8c0?w=1200&q=90",
        "https://images.unsplash.com/photo-1505686994434-e3cc5abf1330?w=1200&q=90"
    ],
    "TV Shows & Streaming": [
        "https://images.unsplash.com/photo-1574375927938-d5a98e8ffe85?w=1200&q=90",
        "https://images.unsplash.com/photo-1522869635100-1f4906a1f07d?w=1200&q=90", 
        "https://images.unsplash.com/photo-1593784697956-14f46924c560?w=1200&q=90",
        "https://images.unsplash.com/photo-1626814026160-2237a95fc5a0?w=1200&q=90",
        "https://images.unsplash.com/photo-1585776245991-cf89dd7fc171?w=1200&q=90",
        "https://images.unsplash.com/photo-1524712245354-2c4e5e7121c0?w=1200&q=90",
        "https://images.unsplash.com/photo-1611162617474-5b21e879e113?w=1200&q=90"
    ],
    "Music & Concerts": [
        "https://images.unsplash.com/photo-1493225255756-d9584f8606e9?w=1200&q=90",
        "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=1200&q=90",
        "https://images.unsplash.com/photo-1470225620780-dba8ba36b745?w=1200&q=90",
        "https://images.unsplash.com/photo-1501281668745-f7f57925c3b4?w=1200&q=90",
        "https://images.unsplash.com/photo-1514525253440-b393452e8d26?w=1200&q=90",
        "https://images.unsplash.com/photo-1459749411177-0473ef7161a8?w=1200&q=90"
    ],
    "Gaming & Esports": [
        "https://images.unsplash.com/photo-1542751371-adc38448a05e?w=1200&q=90",
        "https://images.unsplash.com/photo-1538481199705-c710c4e965fc?w=1200&q=90",
        "https://images.unsplash.com/photo-1592840496694-26d035b52b48?w=1200&q=90",
        "https://images.unsplash.com/photo-1616469829581-73993eb86b02?w=1200&q=90",
        "https://images.unsplash.com/photo-1511512578047-dfb367046420?w=1200&q=90",
        "https://images.unsplash.com/photo-1542831371-29b0f74f9713?w=1200&q=90",
        "https://images.unsplash.com/photo-1552820728-8b83bb6b773f?w=1200&q=90"
    ],
    "Celebrity & Lifestyle": [
        "https://images.unsplash.com/photo-1515634928627-2a4e0dae3ddf?w=1200&q=90",
        "https://images.unsplash.com/photo-1496747611176-843222e1e57c?w=1200&q=90",
        "https://images.unsplash.com/photo-1529626455594-4ff0802cfb7e?w=1200&q=90",
        "https://images.unsplash.com/photo-1583195764036-6dc248ac07d9?w=1200&q=90",
        "https://images.unsplash.com/photo-1504196606672-aef5c9cefc92?w=1200&q=90",
        "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=1200&q=90"
    ],
    "General": [
        "https://images.unsplash.com/photo-1492684223066-81342ee5ff30?w=1200&q=90",
        "https://images.unsplash.com/photo-1505373877841-8d25f7d46678?w=1200&q=90",
        "https://images.unsplash.com/photo-1516280440614-6697288d5d38?w=1200&q=90",
        "https://images.unsplash.com/photo-1550133730-695473e544be?w=1200&q=90",
        "https://images.unsplash.com/photo-1504711434969-e33886168f5c?w=1200&q=90"
    ]
}

# Directories
CONTENT_DIR = "content/articles"
IMAGE_DIR = "static/images"
DATA_DIR = "automation/data"
MEMORY_FILE = f"{DATA_DIR}/link_memory.json"
USED_IMAGES_FILE = f"{DATA_DIR}/used_images.json"

# --- 🟢 PERSISTENT DATA MANAGEMENT ---
def load_json_file(filepath):
    if not os.path.exists(filepath): return {}
    try:
        with open(filepath, 'r') as f: return json.load(f)
    except Exception as e:
        logging.error(f"Error loading {filepath}: {e}")
        return {}

def save_json_file(filepath, data):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w') as f: json.dump(data, f, indent=2)

def save_link_to_memory(title, slug):
    memory = load_json_file(MEMORY_FILE)
    memory[title] = f"/{slug}/"
    if len(memory) > 100:
        memory = dict(list(memory.items())[-100:])
    save_json_file(MEMORY_FILE, memory)

def is_image_used(url):
    used = load_json_file(USED_IMAGES_FILE)
    return url in used.values()

def mark_image_as_used(url, slug):
    used = load_json_file(USED_IMAGES_FILE)
    used[slug] = url
    save_json_file(USED_IMAGES_FILE, used)

# --- 🟢 HELPER FUNCTIONS ---
def clean_camel_case(text):
    if not text: return ""
    text = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', text)
    text = re.sub(r'(?<=[a-zA-Z])(?=\d)', ' ', text)
    text = re.sub(r'(?<=\d)(?=[a-zA-Z])', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()

def repair_json(json_str):
    try:
        json_str = re.sub(r'```json\s*', '', json_str)
        json_str = re.sub(r'\s*```', '', json_str)
        return json.loads(json_str) 
    except:
        json_str = re.sub(r'(\w+):', r'"\1":', json_str) 
        try: return json.loads(json_str)
        except: return None

def repair_markdown_formatting(text):
    if not text: return ""
    text = text.replace("| — |", "|---|").replace("|—|", "|---|")
    text = re.sub(r'\|\s*\|', '|\n|', text)
    text = re.sub(r'(?<!\n)\s-\s\[', '\n\n- [', text) 
    text = re.sub(r'(?<!\n)\s-\s\*\*', '\n\n- **', text)
    text = re.sub(r'(?<!\n)###', "\n\n###", text)
    text = re.sub(r'(?<!\n)##', "\n\n##", text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text

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

# --- 🟢 IMAGE ENGINE (PURE STOCK MODE) ---
def get_unique_stock_image(category):
    target_list = RAW_IMAGE_DB.get(category, RAW_IMAGE_DB["General"])
    # Fallback ke General jika kategori kosong
    if not target_list: target_list = RAW_IMAGE_DB["General"]
    
    random.shuffle(target_list)
    for url in target_list:
        if not is_image_used(url): return url
        
    # Jika semua sudah terpakai, ambil acak (terpaksa duplikat daripada error)
    return random.choice(target_list)

def download_image(url, path):
    try:
        # User Agent standar browser
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        r = requests.get(url, headers=headers, timeout=25)
        
        if r.status_code == 200:
            img = Image.open(BytesIO(r.content)).convert("RGB")
            img = img.resize((1200, 675), Image.Resampling.LANCZOS)
            enhancer = ImageEnhance.Color(img)
            img = enhancer.enhance(1.1)
            img.save(path, "WEBP", quality=85)
            return True
    except Exception as e:
        logging.error(f"Image download failed: {e}")
    return False

def process_image(query, category, slug):
    filename = f"{slug}.webp"
    filepath = os.path.join(IMAGE_DIR, filename)
    public_path = f"/images/{filename}"
    
    if os.path.exists(filepath): return public_path

    logging.info(f"🎨 Processing Image for: {slug}...")
    
    # 🔴 AI GENERATOR DISABLED
    # Karena API Pollinations sedang migrasi/error, kita force pakai Stock Photo
    # agar website tetap tampil profesional.
    
    logging.info("   📸 Fetching High-Quality Stock Image (Unsplash)...")
    stock_url = get_unique_stock_image(category)
    
    if download_image(stock_url, filepath):
        mark_image_as_used(stock_url, slug)
        logging.info("   ✅ Stock Image Applied")
        return public_path
        
    # Fallback absolut
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
        logging.info("   🚀 IndexNow Submitted")
    except Exception as e:
        logging.warning(f"IndexNow Failed: {e}")

def submit_to_google(url):
    if not GOOGLE_JSON_KEY: return
    try:
        from oauth2client.service_account import ServiceAccountCredentials
        from googleapiclient.discovery import build
        
        creds_dict = json.loads(GOOGLE_JSON_KEY)
        SCOPES = ["https://www.googleapis.com/auth/indexing"]
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPES)
        service = build("indexing", "v3", credentials=credentials)
        body = {"url": url, "type": "URL_UPDATED"}
        service.urlNotifications().publish(body=body).execute()
        logging.info("   🚀 Google Indexing Submitted")
    except Exception as e:
        logging.warning(f"Google Indexing Failed: {e}")

# --- 🤖 AI WRITER ---
def call_groq_api(messages, model="llama-3.3-70b-versatile", response_format=None):
    for attempt in range(MAX_RETRIES):
        try:
            api_key = random.choice(GROQ_API_KEYS)
            client = Groq(api_key=api_key)
            kwargs = {"model": model, "messages": messages, "temperature": 0.7}
            if response_format: kwargs["response_format"] = response_format
            chat = client.chat.completions.create(**kwargs)
            return chat.choices[0].message.content
        except Exception as e:
            logging.warning(f"Groq API Error (Attempt {attempt+1}): {e}")
            time.sleep(2 * (attempt + 1))
    return None

def get_metadata(title, summary):
    categories_str = ", ".join(VALID_CATEGORIES)
    prompt = f"""
    Analyze: "{title} - {summary[:200]}"
    Return JSON ONLY:
    {{
        "title": "Catchy Title (No CamelCase)",
        "category": "One of [{categories_str}]",
        "description": "SEO description 160 chars",
        "keywords": ["tag1", "tag2"]
    }}
    """
    response = call_groq_api([{"role": "user", "content": prompt}], response_format={"type": "json_object"})
    return repair_json(response) if response else None

def write_article(metadata, summary, internal_links, author, external_sources_str):
    prompt = f"""
    You are {author}, an expert journalist. Write a 800-1000 word article based on:
    Title: {metadata['title']}
    Summary: {summary}

    STRUCTURE & RULES:
    1. **Formatting**: Use clean Markdown. 
    2. **Headings**: Use H2 (##) for main sections.
    3. **Table**: Include ONE Markdown table summarizing key facts/dates. Ensure blank lines before/after.
    4. **Internal Links**: Include this list exactly in a section called "More News":
    {internal_links}
    5. **External Sources**: Mention {external_sources_str} naturally in the text.
    6. **Style**: engaging, professional, analytical.
    7. **FAQ**: Add 3 Q&A pairs at the end.

    Do NOT output the title again at the start. Just start with the introduction.
    """
    return call_groq_api([{"role": "user", "content": prompt}])

# --- MAIN LOOP ---
def main():
    logging.info("🎬 Starting Glitz Daily Automation (SAFE MODE)...")
    os.makedirs(CONTENT_DIR, exist_ok=True)
    os.makedirs(IMAGE_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    
    for source_name, url in RSS_SOURCES.items():
        logging.info(f"\n📡 Scanning: {source_name}...")
        try:
            feed = feedparser.parse(url)
        except Exception as e: continue

        processed_count = 0
        for entry in feed.entries:
            if processed_count >= TARGET_PER_SOURCE: break
            
            clean_title = clean_camel_case(entry.title.split(" - ")[0])
            logging.info(f"   ✨ Analyzing: {clean_title[:40]}...")

            meta = get_metadata(clean_title, entry.summary)
            if not meta: continue
            
            if meta['category'] not in VALID_CATEGORIES: meta['category'] = "Pop Culture Trends"
            slug = slugify(meta['title'])
            filepath = os.path.join(CONTENT_DIR, f"{slug}.md")
            
            if os.path.exists(filepath):
                logging.info(f"      ⏭️  Skipped (Exists)")
                continue

            # PREPARE CONTENT
            author = random.choice(AUTHOR_PROFILES)
            int_links = get_internal_links()
            ext_sources_str = get_external_sources_formatted()
            
            content_body = write_article(meta, entry.summary, int_links, author, ext_sources_str)
            if not content_body: continue
            
            img_keyword = meta['keywords'][0] if meta['keywords'] else meta['title']
            img_path = process_image(img_keyword, meta['category'], slug)
            
            final_content = repair_markdown_formatting(content_body)
            parts = final_content.split("\n\n")
            if len(parts) > 4: parts.insert(3, "\n{{< ad >}}\n")
            final_content = "\n\n".join(parts)

            date_now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+07:00")
            
            md_file = f"""---
title: "{meta['title'].replace('"', "'")}"
date: {date_now}
author: "{author}"
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
*Disclaimer: Content generated by AI Analyst {author}.*
"""
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(md_file)
            
            save_link_to_memory(meta['title'], slug)
            
            full_url = f"{WEBSITE_URL}/{slug}/"
            submit_to_indexnow(full_url)
            submit_to_google(full_url)
            
            logging.info(f"      ✅ Published: {slug}")
            processed_count += 1
            time.sleep(15) 

    logging.info("🎉 Automation Finished.")

if __name__ == "__main__":
    main()
