import os
import urllib.parse
import requests
import random
import time
from datetime import datetime, timedelta
from gtts import gTTS

from moviepy import VideoFileClip, CompositeVideoClip, concatenate_videoclips, AudioFileClip
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# --- 1. SECRETS HAZIRLIĞI ---
if 'TOKEN_JSON' in os.environ:
    with open('token.json', 'w') as f:
        f.write(os.environ['TOKEN_JSON'])

if 'CLIENT_SECRET_JSON' in os.environ:
    with open('client_secret.json', 'w') as f:
        f.write(os.environ['CLIENT_SECRET_JSON'])

# --- 2. TREND İÇERİK ÇEKME ---
print("🔍 Fetching global trends...")
try:
    yesterday = datetime.utcnow() - timedelta(days=1)
    date_str = yesterday.strftime("%Y/%m/%d")
    url = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia/all-access/{date_str}"
    headers = {'User-Agent': 'ShortsCreatorBot/1.0'}
    response = requests.get(url, headers=headers).json()
    articles = response['items'][0]['articles']
    
    ignore_list = ['Main_Page', 'Special:Search', 'Deaths_in_2026', 'Wikipedia:Featured_pictures']
    filtered_articles = [a['article'].replace('_', ' ') for a in articles if a['article'] not in ignore_list]
    trend_topic = filtered_articles[0]
except Exception as e:
    trend_topic = "mysterious global trend"

print(f"🔥 Trend Topic: {trend_topic}")

# --- 3. SESLENDİRME VE SÜRE HESABI ---
voice_scripts = [
    "Everyone is looking into this topic today. What is happening behind the scenes?",
    "This became the top searched trend on earth. Is it real or a distraction?",
    "Pay attention to this trend right now. Did you notice what is unfolding?"
]
tts = gTTS(text=random.choice(voice_scripts), lang='en')
audio_path = "voice.mp3"
tts.save(audio_path)

voice_clip = AudioFileClip(audio_path)
total_duration = voice_clip.duration

# --- 4. ÜCRETSİZ AI VIDEO GENERATOR İLE SAHNELERİ ÜRETME ---
NUM_SCENES = 3
scene_duration = total_duration / NUM_SCENES

video_clips = []

base_prompt = "futuristic anime character investigating digital mysteries, cinematic lighting, 9:16 vertical video, 4k"
prompts = [
    f"{base_prompt}, looking deeply into holographic screen showing {trend_topic}",
    f"{base_prompt}, running dramatically through cyber city street at night",
    f"{base_prompt}, turning back to camera with intense glowing eyes"
]

print(f"🎬 Generating {NUM_SCENES} video scenes via free AI Video Generator...")

for i, p in enumerate(prompts):
    video_filename = f"ai_video_{i}.mp4"
    encoded_p = urllib.parse.quote(p)
    seed = random.randint(10000, 99999)
    
    # Bedava AI Video API URL (Pollinations Video Engine)
    video_url = f"https://image.pollinations.ai/prompt/{encoded_p}?model=flux-video&width=1080&height=1920&nologo=true&seed={seed}"
    
    success = False
    for attempt in range(3):
        try:
            res = requests.get(video_url, timeout=45)
            if res.status_code == 200 and len(res.content) > 50000:
                with open(video_filename, 'wb') as f:
                    f.write(res.content)
                
                clip = VideoFileClip(video_filename).with_duration(scene_duration)
                
                # 1080x1920 Kırpma ve Boyutlandırma
                aspect_ratio = clip.w / clip.h
                target_aspect = 1080 / 1920
                if aspect_ratio > target_aspect:
                    clip = clip.resized(height=1920)
                    clip = clip.cropped(x1=clip.w/2 - 540, x2=clip.w/2 + 540, y1=0, y2=1920)
                else:
                    clip = clip.resized(width=1080)
                    clip = clip.cropped(x1=0, x2=1080, y1=clip.h/2 - 960, y2=clip.h/2 + 960)

                video_clips.append(clip)
                success = True
                print(f"  └─ Video Scene {i+1} successfully generated.")
                break
        except Exception as e:
            time.sleep(2)

# --- 5. BİRLEŞTİRME VE YÜKLEME ---
final_video = concatenate_videoclips(video_clips, method="compose").with_audio(voice_clip)
output_path = "short_video.mp4"
final_video.write_videofile(output_path, fps=24, codec='libx264', audio_codec='aac')

print("🚀 Uploading video to YouTube...")
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

print(f"🎉 SUCCESS! YouTube Video ID: {response.get('id')}")
