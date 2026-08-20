import os
import xml.etree.ElementTree as ET
import requests
import google.generativeai as genai
from pytrends.request import TrendReq
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
    """Gemini API ile trend konuya özel %100 dinamik metin üretir."""
    model = genai.GenerativeModel('gemini-pro')
    if prompt_type == "script":
        prompt = f"Write a viral, engaging 1-sentence YouTube Shorts narration about the real-time breaking news/topic: '{topic}'. Do not use hashtags or emojis."
    else:
        prompt = f"Write an engaging short YouTube comment asking viewers their opinion on '{topic}'."
    
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Gemini Metin Üretim Hatası: {e}")
        raise e

# --- 1. %100 CANLI VİRAL TREND TESPİTİ (YEDEK HAZIR ŞABLONSUZ) ---
def get_trending_topic():
    print("[1/5] Canlı trend verileri sorgulanıyor...")
    
    # 1. Yöntem: Google Trends RSS
    try:
        url = "https://trends.google.com/trends/trendingsearches/daily/rss?geo=US"
        response = requests.get(url, timeout=10)
        root = ET.fromstring(response.content)
        items = root.findall('.//item/title')
        if items and items[0].text:
            topic = items[0].text
            print(f"RSS Üzerinden Yakalanan Trend: {topic}")
            return topic
    except Exception as e:
        print(f"RSS Trend Bağlantı Hatası: {e}")

    # 2. Yöntem: PyTrends Kütüphanesi
    try:
        pytrends = TrendReq(hl='en-US', tz=360)
        trending = pytrends.trending_searches(pn='united_states')
        topic = str(trending.iloc[0][0])
        if topic:
            print(f"PyTrends Üzerinden Yakalanan Trend: {topic}")
            return topic
    except Exception as e:
        print(f"PyTrends Bağlantı Hatası: {e}")

    # 3. Yöntem: Reddit Popular Topics (Kesin Canlı Akış)
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get('https://www.reddit.com/r/all/top.json?limit=1', headers=headers, timeout=10)
        topic = res.json()['data']['children'][0]['data']['title']
        print(f"Reddit Üzerinden Yakalanan Trend: {topic}")
        return topic
    except Exception as e:
        print(f"Reddit Trend Hatası: {e}")

    raise Exception("DİKKAT: Hiçbir canlı trend kaynağına ulaşılamadı. Sistem hazır varsayılan kelime kullanmamak üzere durduruldu.")

# --- 2. SIFIRDAN AI VİDEO ÜRETİMİ ---
def generate_100pct_ai_video(prompt_text):
    print(f"[2/5] Trend Konu ('{prompt_text}') için sıfırdan AI Video üretiliyor...")
    try:
        client = Client("damo-vilab/ModelScopeT2V")
        result = client.predict(prompt_text, api_name="/predict")
        
        if isinstance(result, dict):
            video_path = result.get('video') or result.get('name') or list(result.values())[0]
        elif isinstance(result, (list, tuple)):
            video_path = result[0]
        else:
            video_path = result

        print(f"Geçici Video Oluşturuldu: {video_path}")
        return video_path
    except Exception as e:
        print(f"AI Video Üretim Hatası: {e}")
        raise e

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
    print(f"Üretilen Canlı Senaryo: '{script_text}'")
    
    tts = gTTS(text=script_text, lang='en', slow=False)
    tts.save(audio_file)
    
    video_clip = VideoFileClip(video_path)
    audio_clip = AudioFileClip(audio_file)
    
    # Kadrajı tam 9:16 Shorts formatına oturtur (Ekran yamukluğunu önler)
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
    
    print("[5/5] Beğeni ve Dinamik Yorum Atılıyor...")
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
    prompt = f"cinematic viral vertical video of {trend}, 8k render, photorealistic, trending content"
    
    generated_video = generate_100pct_ai_video(prompt)
    
    if generated_video and os.path.exists(generated_video):
        final_file = process_media(generated_video, trend)
        upload_and_interact(final_file, trend)
    else:
        raise Exception("Geçerli video dosyası üretilemediği için süreç durduruldu.")
