import os
import json
import requests
from gtts import gTTS
from moviepy.video.VideoClip import ColorClip, TextClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
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

# --- 2. DÜNYA GENELİ TREND KONUYU ÇEK (İngilizce) ---
print("🔍 Fetching global trends...")
try:
    url = "https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia/all-access/2026/08/17"
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(url, headers=headers).json()
    articles = response['items'][0]['articles']
    
    ignore_list = ['Main_Page', 'Special:Search', 'Deaths_in_2026', 'Wikipedia:Featured_pictures']
    filtered_articles = [a['article'].replace('_', ' ') for a in articles if a['article'] not in ignore_list]
    
    trend_topic = filtered_articles[0]
except Exception as e:
    print(f"Global trend could not be fetched, using default: {e}")
    trend_topic = "Global News Today"

print(f"🔥 Global Trend Topic: {trend_topic}")

# --- 3. İNGİLİZCE SES VE VİDEO OLUŞTUR (Shorts 9:16 Formatı) ---
text_to_speech = f"Today's top trending topic worldwide is {trend_topic}. Stay tuned for more daily global updates!"
tts = gTTS(text=text_to_speech, lang='en')
audio_path = "voice.mp3"
tts.save(audio_path)

audio_clip = AudioFileClip(audio_path)
duration = audio_clip.duration

# Dikey Shorts Arka Planı
background = ColorClip(size=(1080, 1920), color=(15, 23, 42), duration=duration)

# Metin Görseli Oluşturma (MoviePy v2 Uyumlu)
txt_clip = TextClip(
    text=f"🔥 GLOBAL TREND\n\n{trend_topic}",
    font_size=60,
    color='white',
    size=(900, None),
    method='caption'
)
txt_clip = txt_clip.with_position('center').with_duration(duration)

final_video = CompositeVideoClip([background, txt_clip]).with_audio(audio_clip)
video_path = "short_video.mp4"
final_video.write_videofile(video_path, fps=24, codec='libx264', audio_codec='aac')

# --- 4. YOUTUBE SHORTS OLARAK YÜKLE ---
print("🚀 Uploading to YouTube...")

creds = Credentials.from_authorized_user_file('token.json')
youtube = build('youtube', 'v3', credentials=creds)

request_body = {
    'snippet': {
        'title': f"Global Trend: {trend_topic} #trend #shorts",
        'description': f"Worldwide trending topic: {trend_topic} #shorts #trend #viral #news",
        'tags': [trend_topic, 'shorts', 'trend', 'viral', 'news'],
        'categoryId': '22'
    },
    'status': {
        'privacyStatus': 'public',
        'selfDeclaredMadeForKids': False,
    }
}

from googleapiclient.http import MediaFileUpload
media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype='video/mp4')

response = youtube.videos().insert(
    part='snippet,status',
    body=request_body,
    media_body=media
).execute()

print(f"🎉 VIDEO SUCCESSFULLY UPLOADED! Video ID: {response.get('id')}")
