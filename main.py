import os
import time
import xml.etree.ElementTree as ET
import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import google.generativeai as genai
from moviepy.editor import AudioFileClip, VideoClip
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# --- GİTHUB SECRETS DOSYA DÖNÜŞTÜRÜCÜ ---
if os.getenv("YOUTUBE_CLIENT_SECRET") and not os.path.exists("client_secret.json"):
    with open("client_secret.json", "w") as f:
        f.write(os.getenv("YOUTUBE_CLIENT_SECRET"))

if os.getenv("TOKEN_JSON") and not os.path.exists("token.json"):
    with open("token.json", "w") as f:
        f.write(os.getenv("TOKEN_JSON"))

# --- GEMINI AI KURULUMU ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

def generate_dynamic_text(prompt_type, topic):
    model = genai.GenerativeModel('gemini-3.6-flash')
    
    if prompt_type == "onscreen":
        prompt = f"Write a catchy, viral 1-sentence hook for YouTube Shorts about: '{topic}'. Keep it under 15 words. No emojis."
    else:
        prompt = f"Write an engaging 1-line YouTube comment about '{topic}' to boost user interaction."
    
    try:
        response = model.generate_content(prompt)
        return response.text.strip().replace('"', '')
    except Exception as e:
        print(f"Gemini Hata: {e}")
        return f"What do you think about {topic}?"

# --- 1. CANLI TREND TESPİTİ ---
def get_trending_topic():
    print("[1/5] Canlı popüler trend sorgulanıyor...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        url = "https://trends.google.com/trends/trendingsearches/daily/rss?geo=US"
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            items = root.findall('.//item/title')
            if items and items[0].text:
                topic = items[0].text
                print(f"Trend Konu Bulundu: {topic}")
                return topic
    except Exception as e:
        print(f"Google Trends Hata: {e}")
        
    return "Future Technology Trend"

# --- 2. AI GÖRSEL ÜRETİMİ ---
def generate_100pct_ai_video(prompt_text):
    print(f"[2/5] Görsel üretiliyor: '{prompt_text}'...")
    encoded = requests.utils.quote(prompt_text)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1920&model=flux&seed={int(time.time())}"
    
    res = requests.get(url, timeout=30)
    if res.status_code == 200:
        path = "generated_image.jpg"
        with open(path, "wb") as f:
            f.write(res.content)
        return path
    raise Exception("Görsel üretilemedi.")

# --- OTOMATİK TREND ARKA PLAN MÜZİĞİ İNDİRİCİ ---
def get_background_music():
    print("Trend Arka Plan Müziği İndiriliyor...")
    music_url = "https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3" # Enerjik Trend Beats
    music_path = "bg_music.mp3"
    try:
        res = requests.get(music_url, timeout=15)
        if res.status_code == 200:
            with open(music_path, "wb") as f:
                f.write(res.content)
            return music_path
    except Exception as e:
        print(f"Müzik indirilemedi: {e}")
    return None

# --- EKRAN METNİ VE HAREKETLİ VİDEO İŞLEME ---
def add_subtitles_and_motion(image_path, text, duration=12):
    base_img = Image.open(image_path).convert("RGB").resize((1080, 1920))
    
    draw = ImageDraw.Draw(base_img)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 54)
    except:
        font = ImageFont.load_default()
        
    words = text.split()
    lines, current_line = [], []
    for w in words:
        current_line.append(w)
        if len(" ".join(current_line)) > 20:
            lines.append(" ".join(current_line[:-1]))
            current_line = [w]
    if current_line:
        lines.append(" ".join(current_line))
    
    y_start = 1350
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        x = (1080 - w) // 2
        y = y_start + (i * 70)
        
        draw.rectangle([x - 20, y - 5, x + w + 20, y + h + 10], fill=(0, 0, 0, 190))
        draw.text((x, y), line, font=font, fill=(255, 255, 0))

    img_np = np.array(base_img)

    def make_frame(t):
        zoom = 1.0 + 0.10 * (t / duration)
        h, w, _ = img_np.shape
        new_h, new_w = int(h / zoom), int(w / zoom)
        top = (h - new_h) // 2
        left = (w - new_w) // 2
        
        cropped = img_np[top:top+new_h, left:left+new_w]
        pil_crop = Image.fromarray(cropped).resize((1080, 1920), Image.Resampling.LANCZOS)
        return np.array(pil_crop)

    return VideoClip(make_frame, duration=duration)

# --- 3. MONTAJ (VİDEO + MÜZİK) ---
def process_media(image_path, topic):
    print("[3/5] Dikey dinamik video, altyazı ve müzik harmanlanıyor...")
    output_filename = "final_shorts.mp4"
    
    onscreen_text = generate_dynamic_text("onscreen", topic)
    print(f"Ekran Yazısı: '{onscreen_text}'")
    
    video_clip = add_subtitles_and_motion(image_path, onscreen_text, duration=12)
    
    bg_music_path = get_background_music()
    if bg_music_path and os.path.exists(bg_music_path):
        audio_clip = AudioFileClip(bg_music_path).subclip(0, 12)
        final_clip = video_clip.set_audio(audio_clip)
    else:
        final_clip = video_clip

    final_clip.write_videofile(
        output_filename, 
        codec='libx264',
        audio_codec='aac',
        fps=30
    )
    
    video_clip.close()
    return output_filename

# --- 4. YOUTUBE YÜKLEME VE ETKİLEŞİM ---
def get_youtube_client():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json')
    
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        raise Exception("Geçerli token.json bulunamadı.")

    return build('youtube', 'v3', credentials=creds)

def upload_and_interact(video_file, topic):
    print("[4/5] YouTube Shorts'a yükleniyor...")
    youtube = get_youtube_client()
    
    body = {
        'snippet': {
            'title': f"{topic} #Shorts #Viral #Trending",
            'description': f"Real-time AI Short about {topic}.",
            'tags': [topic, 'Shorts', 'Viral'],
            'categoryId': '28'
        },
        'status': {
            'privacyStatus': 'public',
            'selfDeclaredMadeForKids': False
        }
    }
    
    media = MediaFileUpload(video_file, chunksize=-1, resumable=True)
    response = youtube.videos().insert(part=','.join(body.keys()), body=body, media_body=media).execute()
    video_id = response['id']
    print(f"BAŞARILI: Video Yüklendi! Video ID: {video_id}")
    
    # Oto-Beğeni
    print("[5/5] Beğeni ve Yorum İşlemi...")
    try:
        youtube.videos().rate(id=video_id, rating='like').execute()
        print("Otomatik LIKE atıldı.")
    except Exception as e:
        print(f"Beğeni uyarısı (Önemsiz): {e}")

    # Oto-Yorum
    try:
        comment_text = generate_dynamic_text("comment", topic)
        youtube.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {
                            "textOriginal": comment_text
                        }
                    }
                }
            }
        ).execute()
        print(f"Otomatik YORUM atıldı: '{comment_text}'")
    except Exception as e:
        print(f"Yorum uyarısı (Önemsiz): {e}")

# --- AKIŞ BAŞLATICI ---
if __name__ == "__main__":
    trend = get_trending_topic()
    prompt = f"cinematic footage of {trend}, 8k render, hyperrealistic, trending topic"
    
    generated_media = generate_100pct_ai_video(prompt)
    if generated_media and os.path.exists(generated_media):
        final_file = process_media(generated_media, trend)
        upload_and_interact(final_file, trend)
    else:
        raise Exception("Görsel üretilemedi.")
