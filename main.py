import os
import json
import urllib.parse
import requests
import random
import time
from datetime import datetime, timedelta
from gtts import gTTS

# MoviePy v2 importları
from moviepy import ImageClip, CompositeVideoClip, concatenate_videoclips, AudioFileClip

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
    trend_topic = "mysterious global event"

print(f"🔥 Global Trend Topic: {trend_topic}")

# --- 3. VIRAL MERAK UYANDIRICI VE SORGULAYICI SESLENDİRME ---
voice_scripts = [
    f"Everyone is talking about this today. But what is really happening behind the scenes? Watch carefully.",
    f"This just became the most searched topic on earth. Is it real, or are we being distracted?",
    f"Pay attention. Something big is unfolding right now around this topic. Did you notice it?"
]
selected_voice_text = random.choice(voice_scripts)

tts = gTTS(text=selected_voice_text, lang='en')
audio_path = "voice.mp3"
tts.save(audio_path)

voice_clip = AudioFileClip(audio_path)
total_duration = voice_clip.duration

# --- 4. 10 KARELİ ÖZGÜN AI KARAKTERİ & FLIPACLIP ANİMASYONU ---
NUM_IMAGES = 10
frame_duration = total_duration / NUM_IMAGES

print(f"🤖 Generating {NUM_IMAGES} original character animation frames...")

# Trendi başkası yerine kendi gözünden sorgulayan özgün AI karakterimiz
character_description = "an original futuristic anime cyberpunk investigator protagonist with glowing eyes and leather coat, cinematic stop-motion style, sharp lines"

image_clips = []
last_valid_clip = None

# FlipaClip tarzı 10 farklı hareket ve açı karesi
angles = [
    "close up face reaction, shock expression",
    "looking down at glowing hologram news",
    "fast camera turn, dynamic action pose",
    "extreme close up on eyes, dramatic shadows",
    "walking towards camera in dark rainy alley",
    "pointing finger at screen, questioning look",
    "turning head quickly, side profile",
    "low angle heroic shot, dramatic lighting",
    "zooming into face, intense aura",
    "looking up at sky, mysterious ending pose"
]

for i in range(NUM_IMAGES):
    img_name = f"ai_frame_{i}.jpg"
    angle_prompt = angles[i % len(angles)]
    
    # Özgün karakter ile trend atmosferini harmanlama
    full_prompt = f"{character_description}, {angle_prompt}, thematic background about {trend_topic}, high contrast, 8k vertical 9:16 portrait"
    encoded_prompt = urllib.parse.quote(full_prompt)
    
    success = False
    for attempt in range(3):
        seed = random.randint(1000, 99999)
        ai_img_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1920&nologo=true&seed={seed}"
        
        try:
            res = requests.get(ai_img_url, timeout=15)
            if res.status_code == 200 and len(res.content) > 5000:
                with open(img_name, 'wb') as f:
                    f.write(res.content)
                
                clip = ImageClip(img_name).with_duration(frame_duration)
                
                # Yamulmayı önleyen Orantısal Kırpma (1080x1920 dikey)
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
                print(f"  └─ Frame {i+1}/{NUM_IMAGES} generated successfully.")
                break
        except Exception as e:
            time.sleep(1)
            
    if not success:
        if last_valid_clip is not None:
            image_clips.append(last_valid_clip.with_duration(frame_duration))

# 10 Kareyi sıralı birleştir
animated_sequence = concatenate_videoclips(image_clips, method="compose").subclipped(0, total_duration)

# SIFIR YAZI / SIFIR OVERLAY - Sadece temiz tam ekran video ve ses
final_video = CompositeVideoClip([animated_sequence], size=(1080, 1920)).with_audio(voice_clip)
output_path = "short_video.mp4"
final_video.write_videofile(output_path, fps=24, codec='libx264', audio_codec='aac')

# --- 5. YOUTUBE SHORTS OLARAK YÜKLE (#trend #shorts #viral) ---
print("🚀 Uploading to YouTube...")

creds = Credentials.from_authorized_user_file('token.json')
youtube = build('youtube', 'v3', credentials=creds)

request_body = {
    'snippet': {
        'title': "#trend #shorts #viral",
        'description': "#trend #shorts #viral #trending",
        'tags': ['trend', 'shorts', 'viral'],
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

print(f"🎉 VIRAL SHORTS SUCCESSFULLY UPLOADED! Video ID: {response.get('id')}")
