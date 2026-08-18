import os
import json
import urllib.parse
import requests
import random
from datetime import datetime, timedelta
from gtts import gTTS
from moviepy.video.VideoClip import ColorClip, TextClip, ImageClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
from moviepy.video.compositing.concatenate import concatenate_videoclips
from moviepy.audio.io.AudioFileClip import AudioFileClip

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
    trend_topic = "Global Trending Topic"

print(f"🔥 Global Trend Topic: {trend_topic}")

# --- 3. İNGİLİZCE SES DOSYASINI OLUŞTUR ---
text_to_speech = f"Did you know about this? Today's top trending topic worldwide is {trend_topic}. Stay tuned for daily global news!"
tts = gTTS(text=text_to_speech, lang='en')
audio_path = "voice.mp3"
tts.save(audio_path)

voice_clip = AudioFileClip(audio_path)
total_duration = voice_clip.duration

# --- 4. ARKA ARKAYA HIZLI HAREKET EDEN (LOW-FPS STOP-MOTION) AI GÖRSELLERİ ÜRET ---
# Her görsel 0.4 saniye ekranda kalacak (Saniyede 2.5 kare low-FPS animasyon)
frame_duration = 0.4
num_frames = int(total_duration / frame_duration) + 1

print(f"🤖 Generating {num_frames} copyright-free AI frames for low-FPS animation...")

prompts = [
    f"hyperrealistic cinematic shot of {trend_topic}, action angle, highly detailed, 8k vertical wallpaper",
    f"dramatic lighting scene of {trend_topic}, high quality cinematic frame, vivid colors",
    f"close up view of {trend_topic}, photorealistic 8k vertical image, intense mood",
    f"dynamic motion shot of {trend_topic}, professional photography, vertical 9:16",
    f"cinematic masterpiece featuring {trend_topic}, trending on artstation, masterpiece"
]

image_clips = []

for i in range(num_frames):
    img_name = f"ai_frame_{i}.jpg"
    current_prompt = random.choice(prompts) + f", seed {random.randint(1, 99999)}"
    encoded_prompt = urllib.parse.quote(current_prompt)
    ai_img_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1920&nologo=true"
    
    try:
        img_bytes = requests.get(ai_img_url, timeout=20).content
        with open(img_name, 'wb') as f:
            f.write(img_bytes)
        
        # Her kareyi kısa süreli clip yapıp listeye ekle
        clip = ImageClip(img_name).with_duration(frame_duration)
        clip = clip.resized(height=1920) if clip.h < 1920 else clip.resized(width=1080)
        clip = clip.with_position('center')
        image_clips.append(clip)
        print(f"  └─ Frame {i+1}/{num_frames} ready.")
    except Exception as e:
        print(f"  └─ Frame {i+1} failed: {e}")
        fallback = ColorClip(size=(1080, 1920), color=(15, 23, 42), duration=frame_duration)
        image_clips.append(fallback)

# Tüm kareleri sıralı olarak birleştir (Low-FPS Video Akışı)
animated_sequence = concatenate_videoclips(image_clips, method="compose").subclip(0, total_duration)

# Karartma filtresi (Okunabilirlik için)
dark_overlay = ColorClip(size=(1080, 1920), color=(0, 0, 0), duration=total_duration).with_opacity(0.3)

# Şık Altyazı
txt_clip = TextClip(
    text=f"🔥 TRENDING NOW\n\n{trend_topic.upper()}",
    font_size=65,
    color='yellow',
    size=(950, None),
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
