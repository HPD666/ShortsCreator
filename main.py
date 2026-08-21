import os
import json
import textwrap
import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from gTTS import gTTS
import google.generativeai as genai
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip

# 1. DİNAMİK YAPAY ZEKA / CANLI BİLGİ ÜRETİCİ (SIFIR MANUEL METİN)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

def get_dynamic_fact():
    prompt = (
        "Provide one mind-blowing, highly interesting, scientific or historical fact in English "
        "for a YouTube Short. Keep it under 22 words, direct, easy to understand, and extremely engaging. "
        "Do not include introductory words like 'Did you know'."
    )
    
    models_to_try = [
        'gemini-1.5-flash',
        'gemini-1.5-flash-latest',
        'gemini-1.5-pro',
        'gemini-2.0-flash',
        'gemini-pro'
    ]
    
    # 1. Aşama: Yapay Zeka (Gemini)
    for model_name in models_to_try:
        try:
            model = genai.GenerativeModel(model_name)
            res = model.generate_content(prompt)
            if res and res.text and len(res.text.strip()) > 10:
                fact = res.text.strip().replace('"', '').replace("Did you know that ", "").replace("Did you know ", "")
                print(f"[AI Fact Generated via {model_name}]: {fact}")
                return fact
        except Exception as e:
            print(f"Gemini model {model_name} attempt failed: {e}")
            continue

    # 2. Aşama: Canlı İngilizce Vikipedi API (Yapay zeka erişilemezse canlı ansiklopedi çeker)
    print("Fetching dynamic fact live from Wikipedia API...")
    try:
        wiki_res = requests.get("https://en.wikipedia.org/api/rest_v1/page/random/summary", timeout=10)
        if wiki_res.status_code == 200:
            data = wiki_res.json()
            extract = data.get('extract', '')
            first_sentence = extract.split('. ')[0] + '.'
            if len(first_sentence) > 15:
                print(f"[Wikipedia Fact Fetched]: {first_sentence}")
                return first_sentence
    except Exception as e:
        print(f"Wikipedia API error: {e}")

    raise RuntimeError("Critical Error: Unable to fetch dynamic content from AI or Wikipedia APIs!")

# 2. PIL İLE ALTYAZI ÇİZİMİ (ImageMagick Bağımlılığı Olmadan %100 Kararlı)
def overlay_text_on_image(text, width=1080, height=1920):
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 52)
    except Exception:
        font = ImageFont.load_default()

    wrapped_lines = textwrap.wrap(text, width=22)
    
    line_heights = []
    for line in wrapped_lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_heights.append(bbox[3] - bbox[1])
    
    total_height = sum(line_heights) + (len(wrapped_lines) - 1) * 18
    y_start = (height - total_height) // 2
    
    current_y = y_start
    for line in wrapped_lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = (width - text_w) // 2
        
        # Siyah yarı saydam arka plan kutusu
        pad = 16
        draw.rectangle(
            [x - pad, current_y - pad, x + text_w + pad, current_y + text_h + pad],
            fill=(0, 0, 0, 190)
        )
        
        # Beyaz Metin
        draw.text((x, current_y), line, font=font, fill=(255, 255, 255, 255))
        current_y += text_h + 18

    overlay_path = "text_overlay.png"
    img.save(overlay_path)
    return overlay_path

# 3. YOUTUBE OAUTH CLIENT
def get_youtube_client():
    token_raw = os.getenv("TOKEN_JSON")
    if not token_raw:
        raise ValueError("TOKEN_JSON secret environment variable is missing!")
    
    info = json.loads(token_raw)
    creds = Credentials(
        token=None,
        refresh_token=info["refresh_token"],
        token_uri=info.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=info["client_id"],
        client_secret=info["client_secret"],
        scopes=[
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube.force-ssl"
        ]
    )
    if not creds.valid:
        creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)

# 4. YOUTUBE YÜKLEME VE İETİLEŞİM (İNGİLİZCE)
def upload_to_youtube(video_path, fact_text):
    youtube = get_youtube_client()
    
    body = {
        'snippet': {
            'title': "Mind-Blowing Fact You Didn't Know! #Shorts #Facts",
            'description': f"{fact_text}\n\n#shorts #facts #didyouknow #science #education",
            'tags': ['shorts', 'facts', 'didyouknow', 'science'],
            'categoryId': '27'
        },
        'status': {
            'privacyStatus': 'public',
            'selfDeclaredMadeForKids': False
        }
    }
    
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    req = youtube.videos().insert(part=','.join(body.keys()), body=body, media_body=media)
    res = req.execute()
    video_id = res.get('id')
    print(f"Video successfully uploaded! Video ID: {video_id}")
    
    # Otomatik Beğeni
    try:
        youtube.videos().rate(id=video_id, rating='like').execute()
        print("Video automatically liked.")
    except Exception as e:
        print(f"Could not like video: {e}")
        
    # Otomatik Yorum
    try:
        comment_body = {
            'snippet': {
                'videoId': video_id,
                'topLevelComment': {
                    'snippet': {
                        'textOriginal': "What do you think about this? Share your thoughts below! 👇"
                    }
                }
            }
        }
        youtube.commentThreads().insert(part='snippet', body=comment_body).execute()
        print("Automatic comment posted.")
    except Exception as e:
        print(f"Could not post comment: {e}")

# 5. VİDEO BİRLEŞTİRME VE ÜRETİM SÜRECİ
def build_shorts_video():
    # Dynamic Fact Generation
    fact_text = get_dynamic_fact()
    
    # English Audio Generation (gTTS)
    tts = gTTS(text=fact_text, lang='en')
    audio_path = "voice.mp3"
    tts.save(audio_path)
    audio_clip = AudioFileClip(audio_path)
    
    # Background Image Download (Vertical 1080x1920)
    img_resp = requests.get("https://picsum.photos/1080/1920", timeout=15)
    bg_path = "background.jpg"
    with open(bg_path, "wb") as f:
        f.write(img_resp.content)
        
    # Overlay Text Image
    overlay_path = overlay_text_on_image(fact_text)
    
    # MoviePy Montaj
    bg_clip = ImageClip(bg_path).set_duration(audio_clip.duration)
    txt_clip = ImageClip(overlay_path).set_duration(audio_clip.duration)
    
    final_video = CompositeVideoClip([bg_clip, txt_clip]).set_audio(audio_clip)
    output_video_path = "final_shorts.mp4"
    final_video.write_videofile(output_video_path, fps=24, codec='libx264', audio_codec='aac')
    
    return output_video_path, fact_text

if __name__ == "__main__":
    video_path, fact = build_shorts_video()
    upload_to_youtube(video_path, fact)
