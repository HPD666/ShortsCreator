import os
import xml.etree.ElementTree as ET
import requests
import google.generativeai as genai
from gradio_client import Client
from gtts import gTTS
from moviepy.editor import VideoFileClip, AudioFileClip
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

# --- GEMINI AI KURULUMU ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

def generate_dynamic_text(prompt_type, topic):
    model = genai.GenerativeModel('gemini-pro')
    if prompt_type == "script":
        prompt = f"Write a viral, engaging 1-sentence YouTube Shorts narration about the topic: '{topic}'. No emojis or hashtags."
    else:
        prompt = f"Write a short YouTube comment asking viewers their opinion on '{topic}'."
    
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Gemini Metin Üretim Hatası: {e}")
        raise e

# --- 1. CANLI TREND TESPİTİ ---
def get_trending_topic():
    print("[1/5] Canlı trend verileri sorgulanıyor...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        url = "https://trends.google.com/trends/trendingsearches/daily/rss?geo=US"
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            items = root.findall('.//item/title')
            if items and items[0].text:
                topic = items[0].text
                print(f"Google Trends: {topic}")
                return topic
    except Exception as e:
        print(f"Google Trends Hatası: {e}")

    try:
        wiki_url = "https://en.wikipedia.org/w/api.php?action=query&list=geosearch&gsradius=10000&gscoord=37.7749|-122.4194&format=json"
        res = requests.get(wiki_url, headers=headers, timeout=10).json()
        pages = res.get('query', {}).get('geosearch', [])
        if pages:
            topic = pages[0]['title']
            print(f"Wikipedia Canlı Akış: {topic}")
            return topic
    except Exception as e:
        print(f"Wikipedia Hatası: {e}")

    raise Exception("Canlı veri kaynağı bulunamadı.")

# --- 2. SIFIRDAN AI VİDEO ÜRETİMİ (GÜNCEL / AÇIK KULLANIMLI SPACE) ---
def generate_100pct_ai_video(prompt_text):
    print(f"[2/5] Trend Konu ('{prompt_text}') için sıfırdan AI Video üretiliyor...")
    
    # HF Token gerektirmeyen güncel açık kaynak T2V modeli
    spaces = [
        "fffilimonov/Text-to-Video",
        "multimodalart/modelscope-tv"
    ]
    
    for space in spaces:
        try:
            print(f"Denenen AI Model Space: {space}")
            client = Client(space)
            result = client.predict(prompt_text, api_name="/predict")
            
            if isinstance(result, dict):
                video_path = result.get('video') or result.get('name') or list(result.values())[0]
            elif isinstance(result, (list, tuple)):
                video_path = result[0]
            else:
                video_path = result

            if video_path and os.path.exists(video_path):
                print(f"Geçici Video Oluşturuldu: {video_path}")
                return video_path
        except Exception as e:
            print(f"{space} alanında hata: {e}")
            continue

    raise Exception("Aktif AI Video servisi yanıt vermedi.")

# --- 3. 9:16 DİKEY FORMAT VE SES MONTAJI ---
def format_to_916(clip, target_w=1080, target_h=1920):
    target_ratio = target_w / target_h
    w, h = clip.size
    current_ratio = w / h

    if current_ratio > target_ratio:
        new_w = int(h * target_ratio)
        clip = clip.crop(x_center=w/2, width=new_w)
    else:
        new_h = int(w / target_ratio)
        clip = clip.crop(y_center=h/2, height=new_h)

    return clip.resize((target_w, target_h))

def process_media(video_path, topic):
    print("[3/5] Dikey kadraj ve dinamik seslendirme işleniyor...")
    audio_file = "voice.mp3"
    output_filename = "final_shorts.mp4"
    
    script_text = generate_dynamic_text("script", topic)
    print(f"Üretilen Senaryo: '{script_text}'")
    
    tts = gTTS(text=script_text, lang='en', slow=False)
    tts.save(audio_file)
    
    video_clip = VideoFileClip(video_path)
    audio_clip = AudioFileClip(audio_file)
    
    video_clip = format_to_916(video_clip, 1080, 1920)
    
    if video_clip.duration < audio_clip.duration:
        final_clip = video_clip.loop(duration=audio_clip.duration).set_audio(audio_clip)
    else:
        final_clip = video_clip.set_duration(audio_clip.duration).set_audio(audio_clip)
        
    final_clip.write_videofile(
        output_filename, 
        codec='libx264', 
        audio_codec='aac',
        temp_audiofile='temp-audio.m4a',
        remove_temp=True,
        fps=30
    )
    
    video_clip.close()
    audio_clip.close()
    return output_filename

# --- 4. YOUTUBE OTO-YÜKLEME VE DİNAMİK ETKİLEŞİM ---
SCOPES = [
    'https://www.googleapis.com/auth/youtube.upload', 
    'https://www.googleapis.com/auth/youtube.force-ssl'
]

def get_youtube_client():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file('client_secret.json', SCOPES)
        creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('youtube', 'v3', credentials=creds)

def upload_and_interact(video_file, topic):
    print("[4/5] YouTube Shorts kanalına yükleniyor...")
    youtube = get_youtube_client()
    
    body = {
        'snippet': {
            'title': f"{topic} #Shorts #Viral #Trending",
            'description': f"Real-time AI video covering {topic}.",
            'tags': [topic, 'Shorts', 'Viral'],
            'categoryId': '25'
        },
        'status': {
            'privacyStatus': 'public',
            'selfDeclaredMadeForKids': False
        }
    }
    
    media = MediaFileUpload(video_file, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part=','.join(body.keys()), body=body, media_body=media)
    response = request.execute()
    video_id = response['id']
    print(f"BAŞARILI: Video Yüklendi! Video ID: {video_id}")
    
    print("[5/5] Beğeni ve Yorum Atılıyor...")
    try:
        youtube.videos().rate(id=video_id, rating='like').execute()
        print("LIKE Atıldı.")
    except Exception as e:
        print(f"Beğeni Hatası: {e}")
        
    try:
        dynamic_comment = generate_dynamic_text("comment", topic)
        youtube.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {"snippet": {"textOriginal": dynamic_comment}}
                }
            }
        ).execute()
        print(f"Yorum Atıldı: '{dynamic_comment}'")
    except Exception as e:
        print(f"Yorum Hatası: {e}")

# --- AKIŞ BAŞLATICI ---
if __name__ == "__main__":
    trend = get_trending_topic()
    prompt = f"cinematic vertical footage of {trend}, 8k render, photorealistic"
    
    generated_video = generate_100pct_ai_video(prompt)
    
    if generated_video and os.path.exists(generated_video):
        final_file = process_media(generated_video, trend)
        upload_and_interact(final_file, trend)
    else:
        raise Exception("Geçerli video üretilemedi.")
