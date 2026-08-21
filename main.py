import os
import json
import requests
from gTTS import gTTS
import google.generativeai as genai
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from moviepy.editor import ImageClip, AudioFileClip, TextClip, CompositeVideoClip

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

def get_gemini_content():
    prompt = "YouTube Shorts için Türkçe, merak uyandırıcı, bilinmeyen tek cümlelik ilginç bir bilgi üret."
    models = ['gemini-1.5-flash', 'gemini-1.5-flash-latest', 'gemini-1.5-pro']
    for m in models:
        try:
            model = genai.GenerativeModel(m)
            res = model.generate_content(prompt)
            if res and res.text:
                return res.text.strip()
        except Exception:
            continue
    return "Dünyanın en derin noktası olan Mariana Çukuru yaklaşık 11 kilometre derinliktedir."

def get_youtube_client():
    token_raw = os.getenv("TOKEN_JSON")
    if not token_raw:
        raise ValueError("TOKEN_JSON secret bulunamadı!")
    
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

def upload_and_interact(video_path, fact_text):
    youtube = get_youtube_client()
    
    body = {
        'snippet': {
            'title': "Bunu Biliyor Muydunuz? #Shorts #Bilgi",
            'description': f"{fact_text}\n\n#shorts #bilgi #ilginç",
            'tags': ['shorts', 'bilgi', 'trend'],
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
        print("Otomatik beğenildi.")
    except Exception as e:
        print(f"Beğeni atılamadı: {e}")
        
    try:
        comment_body = {
            'snippet': {
                'videoId': video_id,
                'topLevelComment': {
                    'snippet': {
                        'textOriginal': "Daha fazla bilgi için kanala abone olmayı ve beğenmeyi unutmayın! 👇"
                    }
                }
            }
        }
        youtube.commentThreads().insert(part='snippet', body=comment_body).execute()
        print("Otomatik yorum eklendi.")
    except Exception as e:
        print(f"Yorum atılamadı: {e}")

def build_video():
    fact = get_gemini_content()
    
    tts = gTTS(text=fact, lang='tr')
    audio_path = "speech.mp3"
    tts.save(audio_path)
    audio = AudioFileClip(audio_path)
    
    img_resp = requests.get("https://picsum.photos/1080/1920")
    img_path = "background.jpg"
    with open(img_path, "wb") as f:
        f.write(img_resp.content)
        
    bg = ImageClip(img_path).set_duration(audio.duration)
    txt = TextClip(fact, fontsize=40, color='white', method='caption', size=(900, None)).set_position('center').set_duration(audio.duration)
    
    video = CompositeVideoClip([bg, txt]).set_audio(audio)
    out_path = "final_shorts.mp4"
    video.write_videofile(out_path, fps=24, codec='libx264', audio_codec='aac')
    return out_path, fact

if __name__ == "__main__":
    v_path, fact_text = build_video()
    upload_and_interact(v_path, fact_text)
