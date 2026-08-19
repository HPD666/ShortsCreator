import os
import time
import requests
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google import genai

# API ANAHTARLARI
YT_API_KEY = "YOUR_YOUTUBE_API_KEY"
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"

def get_viral_trend():
    """1. Adım: Trend Akımı ve Görsel Konsepti Bulur"""
    youtube = build('youtube', 'v3', developerKey=YT_API_KEY)
    search_res = youtube.search().list(
        q='shorts challenge meme', type='video', videoDuration='short', maxResults=5, part='snippet'
    ).execute()

    v_ids = [item['id']['videoId'] for item in search_res.get('items', [])]
    video_res = youtube.videos().list(id=','.join(v_ids), part='snippet,statistics').execute()
    
    top_video = max(video_res.get('items', []), key=lambda x: int(x['statistics'].get('viewCount', 0)))
    title = top_video['snippet']['title']
    
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = f"YouTube Shorts akımı: '{title}'. Bu akıma uygun 5 saniyelik görsel bir AI video üretmek için İngilizce kısa prompt yaz (sadece prompt metnini ver)."
    
    response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
    return title, response.text.strip()

def generate_video_ai(prompt_text):
    """2. Adım: API üzerinden MP4 Video Dosyası Üretir"""
    print("🤖 Yapay zeka videosu oluşturuluyor...")
    # Pollinations / Açık kaynak Video Generation API kullanımı
    clean_prompt = requests.utils.quote(prompt_text)
    video_url = f"https://image.pollinations.ai/prompt/{clean_prompt}?model=video&width=720&height=1280"
    
    res = requests.get(video_url)
    video_filename = "generated_trend.mp4"
    
    with open(video_filename, "wb") as f:
        f.write(res.content)
    
    return video_filename

def upload_to_youtube(video_path, trend_title):
    """3. Adım: Kanalına Otomatik Yükler"""
    print("🚀 Video YouTube'a yükleniyor...")
    creds = Credentials.from_authorized_user_file('token.json', ['https://www.googleapis.com/auth/youtube.upload'])
    youtube = build('youtube', 'v3', credentials=creds)

    request_body = {
        'snippet': {
            'title': f"{trend_title[:50]} #shorts",
            'description': '#trend',
            'tags': ['trend', 'shorts', 'viral'],
            'categoryId': '22'
        },
        'status': {
            'privacyStatus': 'public',
            'selfDeclaredMadeForKids': False
        }
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    response = youtube.videos().insert(
        part='snippet,status',
        body=request_body,
        media_body=media
    ).execute()

    print(f"✅ Otomatik Yükleme Tamamlandı! Video ID: {response['id']}")

def job():
    try:
        title, video_prompt = get_viral_trend()
        video_file = generate_video_ai(video_prompt)
        upload_to_youtube(video_file, title)
    except Exception as e:
        print(f"Hata oluştu: {e}")

if __name__ == "__main__":
    job()
