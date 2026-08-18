import os
import urllib.parse
import requests
import random
import time
from datetime import datetime, timedelta
from gtts import gTTS

from moviepy import ImageClip, CompositeVideoClip, concatenate_videoclips, AudioFileClip
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
    print(f"Global trend fetch failed: {e}")
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

# --- 4. GÜVENİLİR VE HIZLI ANİMASYON SİSTEMİ (10 KARE FLIPACLIP STYLE) ---
NUM_FRAMES = 10
frame_duration = total_duration / NUM_FRAMES

print(f"🎬 Generating {NUM_FRAMES} animation frames...")

base_prompt = "futuristic anime character investigating digital mysteries, cinematic lighting, 9:16 vertical portrait, 4k"
prompts = [
    f"{base_prompt}, standing in dark rain city looking at hologram screen",
    f"{base_prompt}, turning head quickly with shocked face expression",
    f"{base_prompt}, touching glowing holographic data about {trend_topic}",
    f"{base_prompt}, close up on glowing blue eyes reflecting code",
    f"{base_prompt}, running dramatically through cyber street",
    f"{base_prompt}, jumping over building roof, low angle camera",
    f"{base_prompt}, pointing finger towards camera, serious look",
    f"{base_prompt}, pulling down cyber goggles, glowing aura",
    f"{base_prompt}, looking up at sky light projection",
    f"{base_prompt}, turning back to camera, mysterious shadow pose"
]

image_clips = []
last_successful_clip = None

for i in range(NUM_FRAMES):
    img_filename = f"ai_frame_{i}.jpg"
    p = prompts[i]
    encoded_p = urllib.parse.quote(p)
    
    success = False
    for attempt in range(3):
        seed = random.randint(10000, 99999)
        # En stabil ve hızlı Turbo model kullanılıyor
        img_url = f"https://image.pollinations.ai/prompt/{encoded_p}?model=turbo&width=1080&height=1920&nologo=true&seed={seed}"
        
        try:
            res = requests.get(img_url, timeout=20)
            if res.status_code == 200 and len(res.content) > 10000:
                with open(img_filename, 'wb') as f:
                    f.write(res.content)
                
                clip = ImageClip(img_filename).with_duration(frame_duration)
                
                # 1080x1920 Dikey Formata Tam Sığdırma Kırpması
                aspect_ratio = clip.w / clip.h
                target_aspect = 1080 / 1920
                if aspect_ratio > target_aspect:
                    clip = clip.resized(height=1920)
                    clip = clip.cropped(x1=clip.w/2 - 540, x2=clip.w/2 + 540, y1=0, y2=1920)
                else:
                    clip = clip.resized(width=1080)
                    clip = clip.cropped(x1=0, x2=1080, y1=clip.h/2 - 960, y2=clip.h/2 + 960)

                clip = clip.with_position('center')
                image_clips.append(clip)
                last_successful_clip = clip
                success = True
                print(f"  └─ Frame {i+1}/{NUM_FRAMES} successfully created.")
                break
        except Exception as e:
            time.sleep(1)
            
    # Eğer ağ hatası vb. olursa listenin boş kalıp çökmesini önleyen güvenlik ağı:
    if not success:
        if last_successful_clip is not None:
            image_clips.append(last_successful_clip.with_duration(frame_duration))
            print(f"  └─ Frame {i+1}/{NUM_FRAMES} used fallback previous frame.")

# Güvenlik Kontrolü: Liste yine de boşsa çökmemesi için düz renk karesi oluştur
if not image_clips:
    print("⚠️ Fallback to safety color frame...")
    from moviepy import ColorClip
    image_clips.append(ColorClip(size=(1080, 1920), color=(15, 15, 30)).with_duration(total_duration))

# --- 5. BİRLEŞTİRME VE YÜKLEME ---
final_video = concatenate_videoclips(image_clips, method="compose").with_audio(voice_clip)
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
