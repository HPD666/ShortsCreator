import os
import json
import urllib.parse
import requests
import random
import time
from datetime import datetime, timedelta
from gtts import gTTS

# MoviePy v2 importları
from moviepy import ColorClip, TextClip, ImageClip, CompositeVideoClip, concatenate_videoclips, AudioFileClip

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# --- 1. GİZLİ ANAHTARLARI DOSYAYA YAZ ---
if 'TOKEN_JSON' in os.environ:
    with open('token.json', 'w') as f:
        f.write(os.environ['TOKEN_JSON'])

if 'CLIENT_SECRET_JSON' in os.environ:
    with open('client_secret.json', 'w') as f:
        f.write(os.environ['CLIENT_SECRET_JSON'])

# --- 2. DÜNYA GENELİ TREND KONUYU ÇEK ---
print("🔍 Fetching global trends...")
try:
    yesterday = datetime.utcnow() - timedelta(days=1)
    date_str = yesterday.strftime("%Y/%m/%d")
    
    url = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia/all-access/{date_str}"
    headers = {'User-Agent': 'ShortsCreatorBot/1.0'}
    response = requests.get(url, headers=headers).json()
    articles = response['items'][0]['articles']
    
    ignore_list = ['Main_Page', 'Special:Search', 'Deaths_in_2026', 'Wikipedia:Featured_pictures', 'Special:CreateAccount']
    filtered_articles = [a['article'].replace('_', ' ') for a in articles if a['article'] not in ignore_list]
    
    trend_topic = filtered_articles[0]
except Exception as e:
    print(f"Global trend fetch failed, using default: {e}")
    trend_topic = "Global News Today"

print(f"🔥 Global Trend Topic: {trend_topic}")

# --- 3. İNGİLİZCE SES DOSYASINI OLUŞTUR ---
text_to_speech = f"Check this out! Today's top global trend is {trend_topic}. What do you think about this?"
tts = gTTS(text=text_to_speech, lang='en')
audio_path = "voice.mp3"
tts.save(audio_path)

voice_clip = AudioFileClip(audio_path)
total_duration = voice_clip.duration

# --- 4. KESİNTİSİZ AKICI AI FRAMELERİ İNDİR (SİYAH KARE ENGELLEYİCİ) ---
frame_duration = 0.25  # Her kare 0.25 saniye (Saniyede 4 AI görseli ile ultra akıcı animasyon)
num_frames = int(total_duration / frame_duration) + 1

print(f"🤖 Generating {num_frames} fluid AI frames...")

prompt_styles = [
    "hyperrealistic 8k cinematic shot, vertical 9:16 portrait, vivid colors, intense action scene",
    "dramatic lighting, 8k high detail photorealistic frame, vertical wallpaper style",
    "close up focus, cinematic lighting, sharp details, vertical masterpiece",
    "dynamic angle, action movie style, vibrant atmosphere, vertical 9:16 layout"
]

image_clips = []
last_valid_clip = None

for i in range(num_frames):
    img_name = f"ai_frame_{i}.jpg"
    success = False
    
    # Görsel tam inene kadar en fazla 3 kere dene
    for attempt in range(3):
        seed = random.randint(10000, 999999)
        style = random.choice(prompt_styles)
        full_prompt = f"{trend_topic}, {style}, frame {i}"
        encoded_prompt = urllib.parse.quote(full_prompt)
        ai_img_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1920&nologo=true&seed={seed}"
        
        try:
            res = requests.get(ai_img_url, timeout=12)
            if res.status_code == 200 and len(res.content) > 5000:  # Boş/Bozuk resim kontrolü
                with open(img_name, 'wb') as f:
                    f.write(res.content)
                
                # ImageClip ve Kırpma (Tam Sığdırma)
                clip = ImageClip(img_name).with_duration(frame_duration)
                
                # Aspect ratio düzeltme ve ortalama
                aspect_ratio = clip.w / clip.h
                target_aspect = 1080 / 1920
                
                if aspect_ratio > target_aspect:
                    clip = clip.resized(height=1920)
                    x_center = clip.w / 2
                    clip = clip.cropped(x1=x_center - 540, x2=x_center + 540, y1=0, y2=1920)
                else:
                    clip = clip.resized(width=1080)
                    y_center = clip.h / 2
                    clip = clip.cropped(x1=0, x2=1080, y1=y_center - 960, y2=y_center + 960)

                clip = clip.with_position('center')
                image_clips.append(clip)
                last_valid_clip = clip
                success = True
                print(f"  └─ Frame {i+1}/{num_frames} downloaded cleanly.")
                break
        except Exception as e:
            time.sleep(1)
            
    # Eğer API yanıt vermezse ASLA siyah ekran koyma, bir önceki başarılı kareyi uzat
    if not success:
        print(f"  └─ Frame {i+1} download missed, reusing previous AI frame.")
        if last_valid_clip is not None:
            image_clips.append(last_valid_clip.with_duration(frame_duration))
        else:
            fallback = ColorClip(size=(1080, 1920), color=(20, 20, 30), duration=frame_duration)
            image_clips.append(fallback)

# Tüm kareleri sıralı birleştir
animated_sequence = concatenate_videoclips(image_clips, method="compose").subclipped(0, total_duration)

# Karartma filtresi (Okunabilirlik için hafif)
dark_overlay = ColorClip(size=(1080, 1920), color=(0, 0, 0), duration=total_duration).with_opacity(0.25)

# Şık Altyazı
txt_clip = TextClip(
    text=f"🔥 TRENDING NOW\n\n{trend_topic.upper()}",
    font_size=60,
    color='yellow',
    size=(900, 600),
    method='caption'
)
txt_clip = txt_clip.with_position('center').with_duration(total_duration)

# Videoyu Birleştir
final_video = CompositeVideoClip([animated_sequence, dark_overlay, txt_clip], size=(1080, 1920)).with_audio(voice_clip)
output_path = "short_video.mp4"
final_video.write_videofile(output_path, fps=24, codec='libx264', audio_codec='aac')

# --- 5. YOUTUBE SHORTS OLARAK YÜKLE ---
print("🚀 Uploading to YouTube...")

creds = Credentials.from_authorized_user_file('token.json')
youtube = build('youtube', 'v3', credentials=creds)

request_body = {
    'snippet': {
        'title': f"Global Trend: {trend_topic} #shorts #viral",
        'description': f"Worldwide trending topic: {trend_topic} #shorts #viral #trending",
        'tags': [trend_topic, 'shorts', 'viral', 'trend'],
        'categoryId': '22'
    },
    'status': {
        'privacyStatus': 'public',
        'selfDeclaredMadeForKids': False,
    }
}

from googleapiclient.http import MediaFileUpload
media = MediaFileUpload(output_path, chunksize=-1, resumable=True, mimetype='video/mp4')

response = youtube.videos().insert(
    part='snippet,status',
    body=request_body,
    media_body=media
).execute()

print(f"🎉 VIDEO SUCCESSFULLY UPLOADED! Video ID: {response.get('id')}")
