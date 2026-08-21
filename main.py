import os
import json
import time
import random
import textwrap
import urllib.parse
import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from gtts import gTTS
from google import genai

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from moviepy import ImageClip, AudioFileClip, CompositeVideoClip

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 1. GEMINI İLE BİLGİ VE GÖRSEL PROMPTU ÜRETİMİ (503 / RETRY DESTEKLİ)
def generate_fact_and_image_prompt():
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY eksik!")

    prompt = (
        "Generate a JSON response with two keys:\n"
        "1. 'fact': TODAY'S FACT! A mind-blowing, short scientific or historical fact in English (under 20 words). Direct and engaging.\n"
        "2. 'image_prompt': A highly detailed, realistic, vertical visual description in English to generate an AI image matching this exact fact.\n"
        "Return ONLY raw JSON in this format: {\"fact\": \"...\", \"image_prompt\": \"...\"}"
    )
    
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    # 503 Sunucu Yoğunluğu ve Zaman Aşımı için Alternatif Modeller ve Yeniden Deneme
    candidate_models = ['gemini-3.6-flash', 'gemini-2.5-flash', 'gemini-1.5-flash']
    response = None

    for model_name in candidate_models:
        for attempt in range(1, 4):
            try:
                print(f"[Gemini Request] Model: {model_name} (Deneme {attempt}/3)...")
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                if response and response.text:
                    break
            except Exception as e:
                print(f"⚠️ {model_name} ile bağlantı hatası ({e}). 5 saniye bekleniyor...")
                time.sleep(5)
        
        if response and response.text:
            break

    if not response or not response.text:
        raise RuntimeError("Gemini API sunucu yoğunluğu nedeniyle tüm denemelere rağmen yanıt veremedi!")

    clean_text = response.text.strip()
    if "```json" in clean_text:
        clean_text = clean_text.split("```json")[1].split("```")[0].strip()
    elif "```" in clean_text:
        clean_text = clean_text.split("```")[1].split("```")[0].strip()
    
    data = json.loads(clean_text)
    fact = data.get("fact", "").strip()
    img_prompt = data.get("image_prompt", "").strip()

    if not fact or not img_prompt:
        raise ValueError("Gemini geçersiz JSON üretti!")

    print(f"[Today's Fact]: {fact}")
    print(f"[Image Prompt]: {img_prompt}")
    return fact, img_prompt

# 2. GÖRSEL ÜRETİMİ
def download_ai_image(image_prompt):
    encoded_prompt = urllib.parse.quote(f"vertical 9:16 aspect ratio, {image_prompt}, cinematic lighting, photorealistic, 8k, highly detailed")
    seed = random.randint(10000, 99999)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1920&nologo=true&seed={seed}&enhance=true"
    
    print("AI görseli indiriliyor...")
    resp = requests.get(url, timeout=40)
    if resp.status_code == 200:
        bg_path = "background.jpg"
        with open(bg_path, "wb") as f:
            f.write(resp.content)
        return bg_path
    else:
        raise Exception("Görsel indirme başarısız oldu!")

# 3. YAZI MASKESİ OLUŞTURMA (Pillow)
def overlay_text_on_image(text, width=1080, height=1920):
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
    except Exception:
        font = ImageFont.load_default()

    wrapped_lines = textwrap.wrap(text, width=22)
    
    line_heights = []
    for line in wrapped_lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_heights.append(bbox[3] - bbox[1])
    
    total_height = sum(line_heights) + (len(wrapped_lines) - 1) * 16
    y_start = (height - total_height) // 2
    
    current_y = y_start
    for line in wrapped_lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = (width - text_w) // 2
        
        pad = 18
        draw.rectangle(
            [x - pad, current_y - pad, x + text_w + pad, current_y + text_h + pad],
            fill=(0, 0, 0, 190)
        )
        draw.text((x, current_y), line, font=font, fill=(255, 255, 255, 255))
        current_y += text_h + 16

    overlay_path = "text_overlay.png"
    img.save(overlay_path)
    return overlay_path

# 4. YOUTUBE OAUTH İŞLEMLERİ
def get_youtube_client():
    token_raw = os.getenv("TOKEN_JSON")
    if not token_raw:
        raise ValueError("TOKEN_JSON eksik!")
    
    info = json.loads(token_raw)
    creds = Credentials(
        token=info.get("token"),
        refresh_token=info["refresh_token"],
        token_uri=info.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=info["client_id"],
        client_secret=info["client_secret"],
        scopes=[
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube.force-ssl"
        ]
    )
    
    if creds.expired or not creds.valid:
        creds.refresh(Request())
        
    return build("youtube", "v3", credentials=creds)

# 5. YOUTUBE YÜKLEME, BEĞENİ VE YORUM
def upload_to_youtube(video_path, fact_text):
    youtube = get_youtube_client()
    
    body = {
        'snippet': {
            'title': "TODAY'S FACT! Mind-Blowing Fact You Didn't Know #Shorts",
            'description': f"{fact_text}\n\n#shorts #todaysfact #facts #didyouknow #science",
            'tags': ['shorts', 'todaysfact', 'facts', 'didyouknow'],
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
    print(f"Video yüklendi! ID: {video_id}")
    
    try:
        youtube.videos().rate(id=video_id, rating='like').execute()
        print("Otomatik beğeni atıldı.")
    except Exception as e:
        print(f"Beğeni atılamadı: {e}")
        
    try:
        comment_body = {
            'snippet': {
                'videoId': video_id,
                'topLevelComment': {
                    'snippet': {
                        'textOriginal': "Did you know this before? Let me know in the comments! 👇"
                    }
                }
            }
        }
        youtube.commentThreads().insert(part='snippet', body=comment_body).execute()
        print("Otomatik yorum atıldı.")
    except Exception as e:
        print(f"Yorum atılamadı: {e}")

# 6. MÜZİK/SES VE VİDEO KURGUSU
def build_shorts_video():
    fact_text, image_prompt = generate_fact_and_image_prompt()
    bg_path = download_ai_image(image_prompt)
    
    tts = gTTS(text=fact_text, lang='en')
    audio_path = "voice.mp3"
    tts.save(audio_path)
    
    audio_clip = AudioFileClip(audio_path)
    duration = audio_clip.duration
    
    overlay_path = overlay_text_on_image(fact_text)
    
    bg_clip = ImageClip(bg_path).with_duration(duration)
    txt_clip = ImageClip(overlay_path).with_duration(duration)
    
    final_video = CompositeVideoClip([bg_clip, txt_clip]).with_audio(audio_clip)
    output_video_path = "final_shorts.mp4"
    final_video.write_videofile(output_video_path, fps=24, codec='libx264', audio_codec='aac')
    
    return output_video_path, fact_text

if __name__ == "__main__":
    video_path, fact = build_shorts_video()
    upload_to_youtube(video_path, fact)
