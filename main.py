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

# --- GEMINI AI KURULUMU (DİNAMİK METİN VE YORUM ÜRETİMİ İÇİN) ---
# Environment variable veya doğrudan API anahtarı
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

def generate_dynamic_text(prompt_type, topic):
    """Hazır metin kullanmak yerine Gemini API ile anlık dinamik metin üretir."""
    model = genai.GenerativeModel('gemini-pro')
    
    if prompt_type == "script":
        prompt = f"Write a catchy 1-sentence viral YouTube Short script about the trend '{topic}'. Do not include emojis or hashtags."
    elif prompt_type == "comment":
        prompt = f"Write a short, engaging, natural YouTube comment asking viewers a question about '{topic}' to drive engagement. Do not sound like a bot."
    
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Dinamik metin üretme hatası: {e}")
        return f"Check out the latest updates on {topic}!"

# --- 1. GERÇEK ZAMANLI TREND TESPİTİ ---
def get_trending_topic():
    print("[1/5] Güncel viral trend çekiliyor...")
    try:
        url = "https://trends.google.com/trends/trendingsearches/daily/rss?geo=US"
        response = requests.get(url, timeout=10)
        root = ET.fromstring(response.content)
        items = root.findall('.//item/title')
        if items:
            topic = items[0].text
            print(f"Yakalanan Trend Topic: {topic}")
            return topic
    except Exception as e:
        print(f"RSS Trend hatası: {e}")
    return "Global News"

# --- 2. SIFIRDAN AI VİDEO ÜRETİMİ ---
def generate_100pct_ai_video(prompt_text):
    print("[2/5] %100 AI Video sıfırdan piksellerle oluşturuluyor...")
    try:
        client = Client("damo-vilab/ModelScopeT2V")
        result = client.predict(
            prompt_text,
            api_name="/predict"
        )
        print(f"AI Video üretildi: {result}")
        return result
    except Exception as e:
        print(f"AI Video üretme hatası: {e}")
        return None

# --- 3. 9:16 DİKEY KADRAJ VE DİNAMİK SES MONTAJI ---
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
    print("[3/5] Yapay zeka ile dinamik senaryo üretiliyor ve seslendiriliyor...")
    audio_file = "voice.mp3"
    output_filename = "final_shorts.mp4"
    
    # %100 Dinamik AI Senaryosu Üretimi
    script_text = generate_dynamic_text("script", topic)
    print(f"Üretilen Dinamik Senaryo: '{script_text}'")
    
    tts = gTTS(text=script_text, lang='en', slow=False)
    tts.save(audio_file)
    
    video_clip = VideoFileClip(video_path)
    audio_clip = AudioFileClip(audio_file)
    
    # 9:16 Kadraj düzeltmesi
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

# --- 4. YOUTUBE OTO-YÜKLEME VE DİNAMİK YORUM ---
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
    print("[4/5] YouTube Shorts yükleniyor...")
    youtube = get_youtube_client()
    
    body = {
        'snippet': {
            'title': f"{topic} #Shorts #Viral #Trending",
            'description': f"Dynamic AI coverage on {topic}.",
            'tags': [topic, 'Shorts', 'Viral'],
            'categoryId': '24'
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
    print(f"Video Yüklendi! Video ID: {video_id}")
    
    print("[5/5] Beğeni ve Dinamik Yorum Atılıyor...")
    
    # 1. Beğeni
    try:
        youtube.videos().rate(id=video_id, rating='like').execute()
        print("Otomatik LIKE atıldı.")
    except Exception as e:
        print(f"Beğeni hatası: {e}")
        
    # 2. %100 Dinamik AI Yorumu
    dynamic_comment = generate_dynamic_text("comment", topic)
    print(f"Atılacak Dinamik Yorum: '{dynamic_comment}'")
    
    try:
        youtube.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {
                            "textOriginal": dynamic_comment
                        }
                    }
                }
            }
        ).execute()
        print("Dinamik yorum başarıyla atıldı.")
    except Exception as e:
        print(f"Yorum hatası: {e}")

# --- ÇALIŞTIRMA ---
if __name__ == "__main__":
    trend = get_trending_topic()
    prompt = f"cinematic viral vertical footage of {trend}, highly detailed, 4k render, trending on social media"
    
    generated_video = generate_100pct_ai_video(prompt)
    
    if generated_video:
        final_file = process_media(generated_video, trend)
        upload_and_interact(final_file, trend)
    else:
        print("AI Video üretimi başarısız oldu, işlem sonlandırıldı.")
