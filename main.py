import os
import json
import io
import urllib.parse
import requests
import random
import time
from datetime import datetime, timedelta
from gtts import gTTS
from PIL import Image

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

HF_TOKEN = os.environ.get('HF_TOKEN', None)

# --- 2. ORANTI BOZMAYAN CENTER-CROP (1080x1920) ---
def process_center_crop(image_bytes, target_w=1080, target_h=1920):
    """Görseli sündürmeden orantılı şekilde merkezden 9:16 kırpar."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    target_ratio = target_w / target_h
    img_ratio = img.width / img.height

    if img_ratio > target_ratio:
        new_h = target_h
        new_w = int(img.width * (target_h / img.height))
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        left = (new_w - target_w) // 2
        img = img.crop((left, 0, left + target_w, target_h))
    else:
        new_w = target_w
        new_h = int(img.height * (target_w / img.width))
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        top = (new_h - target_h) // 2
        img = img.crop((0, top, target_w, top + target_h))

    return img

# --- 3. TREND İÇERİK VE DETAYLI SPESİFİK METİN ÇEKME ---
print("🔍 Fetching global trend and summary details...")
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
    
    summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(trend_topic)}"
    sum_res = requests.get(summary_url, headers=headers).json()
    extract_text = sum_res.get('extract', '')
    
    if extract_text and len(extract_text) > 30:
        first_sentences = '. '.join(extract_text.split('. ')[:2])
        voice_script = f"Here is what happened with {trend_topic}. {first_sentences}. What do you think?"
    else:
        voice_script = f"Breakdown on {trend_topic}. Major updates are unfolding right now. Did you see this coming?"
except Exception as e:
    print(f"Trend fetch failed: {e}")
    trend_topic = "mysterious breaking news"
    voice_script = "Major updates are unfolding worldwide right now. Stay tuned."

print(f"🔥 Trend Topic: {trend_topic}")

# --- 4. SESLENDİRME ---
tts = gTTS(text=voice_script, lang='en')
audio_path = "voice.mp3"
tts.save(audio_path)

voice_clip = AudioFileClip(audio_path)
total_duration = voice_clip.duration

# --- 5. HUGGING FACE İLE GÖRSEL ÜRETİMİ ---
NUM_FRAMES = 10
frame_duration = total_duration / NUM_FRAMES

print(f"🤖 Generating {NUM_FRAMES} frames via Hugging Face Inference API...")

base_prompt = f"original cyberpunk detective protagonist reacting to {trend_topic}, anime style, 8k vertical portrait, dynamic shadows"
frame_prompts = [
    f"{base_prompt}, looking shocked at glowing news screen",
    f"{base_prompt}, turning head quickly in dark alley",
    f"{base_prompt}, touching digital hologram interface",
    f"{base_prompt}, close up on glowing blue eyes reflecting digital text",
    f"{base_prompt}, running fast across cyber street",
    f"{base_prompt}, jumping over edge, cinematic angle",
    f"{base_prompt}, pointing finger dramatically at camera",
    f"{base_prompt}, pulling down cyber goggles, intense aura",
    f"{base_prompt}, looking up at sky hologram projection",
    f"{base_prompt}, mysterious silhouette ending pose"
]

def fetch_hf_image(prompt):
    model_id = "black-forest-labs/FLUX.1-schnell"
    api_url = f"https://api-inference.huggingface.co/models/{model_id}"
    
    headers = {}
    if HF_TOKEN:
        headers["Authorization"] = f"Bearer {HF_TOKEN}"
        
    payload = {"inputs": prompt}
    
    for attempt in range(3):
        try:
            res = requests.post(api_url, headers=headers, json=payload, timeout=25)
            if res.status_code == 200 and len(res.content) > 10000:
                return res.content
            elif res.status_code == 503:
                time.sleep(8)
            else:
                time.sleep(2)
        except Exception:
            time.sleep(2)
            
    try:
        encoded = urllib.parse.quote(prompt)
        fallback_url = f"https://image.pollinations.ai/prompt/{encoded}?model=turbo&width=1080&height=1920&nologo=true"
        f_res = requests.get(fallback_url, timeout=15)
        if f_res.status_code == 200:
            return f_res.content
    except Exception:
        pass
    return None

image_clips = []
last_valid_clip = None

for i in range(NUM_FRAMES):
    img_filename = f"ai_frame_{i}.jpg"
    p = frame_prompts[i]
    
    raw_bytes = fetch_hf_image(p)
    
    if raw_bytes:
        processed_img = process_center_crop(raw_bytes, 1080, 1920)
        processed_img.save(img_filename)
        
        clip = ImageClip(img_filename).with_duration(frame_duration)
        image_clips.append(clip)
        last_valid_clip = clip
        print(f"  └─ Frame {i+1}/{NUM_FRAMES} processed cleanly.")
    else:
        if last_valid_clip is not None:
            image_clips.append(last_valid_clip.with_duration(frame_duration))
            print(f"  └─ Frame {i+1}/{NUM_FRAMES} reused previous valid frame.")

if not image_clips:
    from moviepy import ColorClip
    image_clips.append(ColorClip(size=(1080, 1920), color=(10, 15, 30)).with_duration(total_duration))

# --- 6. VİDEO BİRLEŞTİRME VE YÜKLEME ---
animated_sequence = concatenate_videoclips(image_clips, method="compose").subclipped(0, total_duration)
final_video = CompositeVideoClip([animated_sequence], size=(1080, 1920)).with_audio(voice_clip)

output_path = "short_video.mp4"
final_video.write_videofile(output_path, fps=24, codec='libx264', audio_codec='aac')

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

print(f"🎉 SUCCESS! YouTube Video ID: {response.get('id')}")
