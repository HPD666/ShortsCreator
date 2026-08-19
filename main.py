import os
import sys
import logging
import urllib.request
import urllib.parse
import json
from pathlib import Path

from moviepy import (
    VideoFileClip,
    TextClip,
    CompositeVideoClip,
    concatenate_videoclips
)
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload

try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("shorts-creator")

if 'TOKEN_JSON' in os.environ and os.environ['TOKEN_JSON'].strip():
    try:
        with open('token.json', 'w') as f:
            f.write(os.environ['TOKEN_JSON'])
    except Exception as e:
        logger.warning(f"token.json writing failed: {e}")

YT_API_KEY = os.environ.get("YT_API_KEY", None)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", None)
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", None)

OUT_DIR = Path("outputs")
OUT_DIR.mkdir(exist_ok=True)
VID_DIR = Path("temp_videos")
VID_DIR.mkdir(exist_ok=True)

def extract_live_trends():
    """Doğrudan canlı YouTube trendlerinden konu ve İngilizce metin çıkarır."""
    if not YT_API_KEY or not GEMINI_API_KEY or not GENAI_AVAILABLE:
        logger.error("❌ YT_API_KEY veya GEMINI_API_KEY eksik! Dinamik trend analizi yapılamıyor.")
        sys.exit(1)

    logger.info("🔥 Live YouTube Shorts trends fetching...")
    youtube = build('youtube', 'v3', developerKey=YT_API_KEY)
    
    # En güncel viral Shorts videolarını çek
    res = youtube.search().list(
        q='viral shorts trending',
        type='video',
        videoDuration='short',
        order='viewCount',
        maxResults=10,
        part='snippet'
    ).execute()
    
    titles = [item['snippet']['title'] for item in res.get('items', [])]
    trend_context = " | ".join(titles)
    logger.info(f"📊 Analyzing trend topics: {trend_context[:100]}...")

    client = genai.Client(api_key=GEMINI_API_KEY)
    gemini_prompt = (
        f"Analyze these current viral YouTube Shorts titles: '{trend_context}'. "
        "Extract 3 exact visual search topics in English that represent what is trending RIGHT NOW. "
        "For each topic, provide a short english overlay text (max 4 words). "
        "Do NOT use fixed themes like cyberpunk unless it is explicitly trending. "
        "Format exactly as: SEARCH_TOPIC|OVERLAY_TEXT for each line, separated by '---'."
    )
    
    response = client.models.generate_content(model='gemini-3.6-flash', contents=gemini_prompt)

    if not response or not response.text:
        logger.error("❌ Gemini failed to analyze trend data.")
        sys.exit(1)

    raw_items = [s.strip() for s in response.text.split('---') if s.strip()]
    parsed_data = []
    for item in raw_items:
        if '|' in item:
            s, t = item.split('|', 1)
            parsed_data.append({"search": s.strip(), "text": t.strip()})
    
    if len(parsed_data) < 3:
        logger.error("❌ Could not extract enough dynamic trend topics.")
        sys.exit(1)

    hashtag = titles[0].split()[0].replace('#', '')
    return parsed_data[:3], f"Trending Now #{hashtag} #shorts #viral"

def fetch_trend_video(search_query: str, idx: int) -> str:
    """Gemini'nin canlı çıkardığı trend kelimesiyle HD video indirir."""
    if not PEXELS_API_KEY:
        logger.error("❌ PEXELS_API_KEY missing!")
        sys.exit(1)

    video_path = VID_DIR / f"trend_vid_{idx}.mp4"
    logger.info(f"🔎 Searching live video for trend: '{search_query}'")
    
    url = f"https://api.pexels.com/videos/search?query={urllib.parse.quote(search_query)}&orientation=portrait&per_page=5"
    req = urllib.request.Request(url, headers={"Authorization": PEXELS_API_KEY})
    
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            
        videos = data.get('videos', [])
        if not videos:
            # Trend çok özelse fallback yerine genel arama dene
            url = f"https://api.pexels.com/videos/search?query=trending&orientation=portrait&per_page=5"
            req = urllib.request.Request(url, headers={"Authorization": PEXELS_API_KEY})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                videos = data.get('videos', [])

        video_files = videos[0].get('video_files', [])
        mp4_url = next((f['link'] for f in video_files if f.get('file_type') == 'video/mp4'), video_files[0]['link'])
        
        urllib.request.urlretrieve(mp4_url, video_path)
        logger.info(f"✅ Downloaded video matching trend '{search_query}'")
        return str(video_path)
    except Exception as e:
        logger.error(f"Video download failed for search '{search_query}': {e}")
        return None

def main():
    # 1. Canlı Trendleri Çek
    trend_scenes, video_title = extract_live_trends()
    video_clips = []

    # 2. Trend Videoları Oluştur
    for idx, scene in enumerate(trend_scenes):
        video_file = fetch_trend_video(scene["search"], idx)
        if video_file and os.path.exists(video_file):
            clip = VideoFileClip(video_file).subclipped(0, 4.0).resized(height=1024)
            
            try:
                txt_clip = TextClip(
                    text=scene["text"],
                    font_size=40,
                    color='yellow',
                    stroke_color='black',
                    stroke_width=2,
                    method='caption',
                    size=(500, 200)
                ).with_duration(clip.duration).with_position(('center', 0.75), relative=True)

                video_clips.append(CompositeVideoClip([clip, txt_clip]))
            except Exception:
                video_clips.append(clip)

    if not video_clips:
        logger.error("❌ No clips could be assembled.")
        sys.exit(1)

    # 3. Kurgula ve YouTube Shorts'a Yükle
    final_video = concatenate_videoclips(video_clips, method="compose")
    output_path = OUT_DIR / "short_video.mp4"
    final_video.write_videofile(str(output_path), fps=24, codec="libx264", audio_codec="aac", logger=None)

    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json')
        youtube = build('youtube', 'v3', credentials=creds)
        body = {
            'snippet': {'title': video_title, 'description': f'{video_title} #shorts #trending', 'categoryId': '22'},
            'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': False}
        }
        media = MediaFileUpload(str(output_path), chunksize=-1, resumable=True, mimetype='video/mp4')
        youtube.videos().insert(part='snippet,status', body=body, media_body=media).execute()
        logger.info("🎉 Dynamic Trend Video successfully published to YouTube!")

if __name__ == "__main__":
    main()
