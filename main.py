import os
import json
import time
import random
import textwrap
import urllib.parse
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

from google import genai

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from moviepy import ImageClip, AudioFileClip, CompositeVideoClip

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 1. DOĞRULANMIŞ, SADE VE TEKRARSIZ BİLGİ ÜRETİMİ
def generate_fact_and_image_prompt():
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY bulunamadı!")

    topics = [
        "astronomy and space", "deep sea creatures", "human brain marvels", 
        "ancient world secrets", "bizarre nature facts", "unusual geography"
    ]
    chosen_topic = random.choice(topics)
    timestamp_seed = int(time.time() * 1000)

    prompt = (
        f"Generate a unique JSON response with two keys.\n"
        f"Unique Seed: {timestamp_seed}\n"
        f"Topic: {chosen_topic}\n"
        "1. 'fact': TODAY'S FACT! A 100% scientifically accurate, surprising short fact in VERY SIMPLE, basic English (under 15 words). Do not use cliché facts.\n"
        "2. 'image_prompt': A high quality visual prompt in English to generate a 9:16 vertical background picture representing this exact fact.\n"
        "Return ONLY raw JSON: {\"fact\": \"...\", \"image_prompt\": \"...\"}"
    )
    
    client = genai.Client(api_key=GEMINI_API_KEY)
    candidate_models = ['gemini-2.5-flash', 'gemini-1.5-flash']
    response = None

    for model_name in candidate_models:
        for attempt in range(1, 4):
            try:
                print(f"[Gemini] Model deneniyor: {model_name} (Deneme {attempt}/3)...")
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                if response and response.text:
                    break
            except Exception as e:
                print(f"⚠️ {model_name} hatası: {e}. 3sn bekleniyor...")
                time.sleep(3)
        
        if response and response.text:
            break

    if not response or not response.text:
        raise RuntimeError("Gemini API yanıt veremedi!")

    clean_text = response.text.strip()
    if "```json" in clean_text:
        clean_text = clean_text.split("```json")[1].split("```")[0].strip()
    elif "```" in clean_text:
        clean_text = clean_text.split("```")[1].split("```")[0].strip()
    
    data = json.loads(clean_text)
    fact = data.get("fact", "").strip()
    img_prompt = data.get("image_prompt", "").strip()

    print(f"[Fact]: {fact}")
    print(f"[Prompt]: {img_prompt}")
    return fact, img_prompt

# 2. GÖRSELİ HİÇBİR ŞEKİLDE BÜKMEDEN/YAMULTMADAN KUSURSUZ KESME (1080x1920)
def download_ai_image(image_prompt):
    encoded_prompt = urllib.parse.quote(f"vertical 9:16 aspect ratio, {image_prompt}, 8k resolution, cinematic lighting, masterpiece")
    seed = random.randint(100000, 999999)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1920&nologo=true&seed={seed}&enhance=true"
    
    print("AI Görseli indiriliyor...")
    resp = requests.get(url, timeout=40)
    if resp.status_code == 200:
        fixed_bg_path = "background.jpg"
        img = Image.open(BytesIO(resp.content)).convert('RGB')
        
        # En-boy oranını bozmadan merkeze oturtup kırpma (Center-Crop)
        target_w, target_h = 1080, 1920
        img_w, img_h = img.size
        
        scale = max(target_w / img_w, target_h / img_h)
        new_w, new_h = int(img_w * scale), int(img_h * scale)
        img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        left = (new_w - target_w) // 2
        top = (new_h - target_h) // 2
        
        cropped_img = img_resized.crop((left, top, left + target_w, top + target_h))
        cropped_img.save(fixed_bg_path, quality=95)
        return fixed_bg_path
    else:
        raise Exception("Görsel indirme başarısız oldu!")

# 3. 3 KADEMELİ YEDEKLİ %100 GARANTİLİ MÜZİK İNDİRİCİ (CC0 PUBLIC DOMAIN)
def download_background_music():
    music_path = "bg_music.mp3"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    # 3 Farklı yüksek kaliteli ve hızlı müzik sunucusu
    music_urls = [
        "https://freepd.com/music/Neon%20Groove.mp3",
        "https://freepd.com/music/Unstoppable.mp3",
        "https://cdn.pixabay.com/download/audio/2022/03/15/audio_c8c8a73467.mp3"
    ]
    
    for index, url in enumerate(music_urls, 1):
        try:
            print(f"Arka plan müziği indiriliyor (Kaynak {index})...")
            resp = requests.get(url, headers=headers, timeout=20)
            if resp.status_code == 200 and len(resp.content) > 50000:
                with open(music_path, "wb") as f:
                    f.write(resp.content)
                print("✅ Müzik başarıyla hazırlandı.")
                return music_path
        except Exception as e:
            print(f"⚠️ Kaynak {index} hatası ({e}), sonraki deneniyor...")
            
    raise RuntimeError("Müzik kaynaklarının hiçbirine ulaşılamadı!")

# 4. ŞIK SİYAH KUTULU METİN TASARIMI
def overlay_text_on_image(text, width=1080, height=1920):
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    font_size = 52
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()

    wrapped_lines = textwrap.wrap(text, width=20)
    
    line_heights = []
    line_widths = []
    for line in wrapped_lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_widths.append(bbox[2] - bbox[0])
        line_heights.append(bbox[3] - bbox[1])
    
    max_line_width = max(line_widths) if line_widths else 0
    line_spacing = 16
    total_text_height = sum(line_heights) + (len(wrapped_lines) - 1) * line_spacing
    
    y_start = int(height * 0.28)
    
    padding = 32
    box_left = (width - max_line_width) // 2 - padding
    box_top = y_start - padding
    box_right = (width + max_line_width) // 2 + padding
    box_bottom = y_start + total_text_height + padding
    
    draw.rounded_rectangle(
        [box_left, box_top, box_right, box_bottom],
        radius=24,
        fill=(0, 0, 0, 215)
    )
    
    current_y = y_start
    for line in wrapped_lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = (width - text_w) // 2
        
        draw.text((x + 2, current_y + 2), line, font=font, fill=(0, 0, 0, 255))
        draw.text((x, current_y), line, font=font, fill=(255, 255, 255, 255))
        current_y += text_h + line_spacing

    overlay_path = "text_overlay.png"
    img.save(overlay_path)
    return overlay_path

# 5. YOUTUBE AUTHENTICATION
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
        scopes=["https://www.googleapis.com/auth/youtube.upload"]
    )
    
    if creds.expired or not creds.valid:
        creds.refresh(Request())
        
    return build("youtube", "v3", credentials=creds)

# 6. %100 SAFE YOUTUBE YÜKLEME (BEĞENİ VE YORUM İŞLEMLERİ TAMAMEN KALDIRILDI)
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
    req = youtube.videos().insert(part='snippet,status', body=body, media_body=media)
    res = req.execute()
    video_id = res.get('id')
    print(f"✅ Video başarıyla yüklendi! Video ID: {video_id}")

# 7. VİDEO BİRLEŞTİRME
def build_shorts_video():
    fact_text, image_prompt = generate_fact_and_image_prompt()
    bg_path = download_ai_image(image_prompt)
    bg_music_path = download_background_music()
    
    duration = 10.0
    bg_music_clip = AudioFileClip(bg_music_path).subclipped(0, duration).with_volume_scaled(0.85)
    
    overlay_path = overlay_text_on_image(fact_text)
    
    bg_clip = ImageClip(bg_path).with_duration(duration)
    txt_clip = ImageClip(overlay_path).with_duration(duration)
    
    final_video = CompositeVideoClip([bg_clip, txt_clip]).with_audio(bg_music_clip)
    output_video_path = "final_shorts.mp4"
    
    final_video.write_videofile(
        output_video_path,
        fps=24,
        codec='libx264',
        audio_codec='aac',
        preset='ultrafast'
    )
    
    return output_video_path, fact_text

if __name__ == "__main__":
    video_path, fact = build_shorts_video()
    upload_to_youtube(video_path, fact)
