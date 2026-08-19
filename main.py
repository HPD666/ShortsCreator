import os, sys, logging, tempfile, requests, subprocess, json
from pathlib import Path
from datetime import datetime
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload
from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_videoclips
from gradio_client import Client

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("shorts-autopilot")

# Secrets
YT_API_KEY = os.environ.get("YT_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
HF_TOKEN = os.environ.get("HF_TOKEN")
if "TOKEN_JSON" in os.environ and os.environ["TOKEN_JSON"].strip():
    with open("token.json", "w") as f:
        f.write(os.environ["TOKEN_JSON"])

OUT_DIR = Path("outputs"); OUT_DIR.mkdir(exist_ok=True)
TMP_DIR = Path(tempfile.mkdtemp(prefix="shorts-"))

# --- Trend Discovery ---
def fetch_shorts():
    youtube = build("youtube", "v3", developerKey=YT_API_KEY)
    res = youtube.search().list(
        part="snippet",
        type="video",
        videoDuration="short",
        order="date",
        maxResults=20
    ).execute()
    return res.get("items", [])

def cluster_by_title(videos):
    clusters = {}
    for v in videos:
        title = v["snippet"]["title"].lower()
        key = "".join(sorted(set(title.split())))
        clusters.setdefault(key, []).append(v)
    return clusters

def pioneer_video(clusters):
    for key, vids in clusters.items():
        vids.sort(key=lambda x: x["snippet"]["publishedAt"])
        return vids[0]  # ilk kümenin pioneer'ı

# --- Gemini API ---
def gemini_verify_and_prompt(thumbnail_url, title):
    headers = {"Authorization": f"Bearer {GEMINI_API_KEY}"}
    payload = {
        "contents": [{
            "parts": [
                {"text": f"Verify if this thumbnail represents a real Shorts trend: {title}"},
                {"inline_data": {"mime_type":"image/jpeg","data":requests.get(thumbnail_url).content}}
            ]
        }]
    }
    r = requests.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent",
                      headers=headers, json=payload)
    if r.status_code == 200:
        logger.info("Gemini doğrulama başarılı")
    # Prompt üret
    prompt_payload = {
        "contents": [{"parts":[{"text":f"Generate a detailed English video generation prompt for AI video tools based on trend: {title}"}]}]
    }
    r2 = requests.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent",
                       headers=headers, json=prompt_payload)
    return r2.json()["candidates"][0]["content"]["parts"][0]["text"]

# --- Video Generation ---
def generate_video(prompt, idx):
    spaces = ["Wan-AI/Wan2.1-T2V-1.3B","artificialguybr/CogVideoX-5B-Text2Video","fffiloni/ZeroScope-T2V"]
    out_path = TMP_DIR / f"clip_{idx}.mp4"
    for space in spaces:
        try:
            client = Client(space, hf_token=HF_TOKEN)
            job = client.submit(prompt=prompt, api_name="/predict")
            result = job.result(timeout=180)
            if result and os.path.exists(str(result)):
                with open(result,"rb") as src, open(out_path,"wb") as dst: dst.write(src.read())
                return str(out_path)
        except Exception as e:
            logger.warning(f"{space} failed: {e}")
    return None

# --- Audio ---
def download_audio():
    url = "https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3"
    path = TMP_DIR / "bg.mp3"
    r = requests.get(url); open(path,"wb").write(r.content)
    return str(path)

# --- Upload ---
def upload_to_youtube(video_path, title):
    creds = Credentials.from_authorized_user_file("token.json")
    youtube = build("youtube","v3",credentials=creds)
    body = {
        "snippet":{"title":f"{title} #shorts","description":"#trend","categoryId":"22"},
        "status":{"privacyStatus":"public","selfDeclaredMadeForKids":False,"containsSyntheticMedia":True}
    }
    media = MediaFileUpload(video_path,resumable=True,mimetype="video/mp4")
    youtube.videos().insert(part="snippet,status",body=body,media_body=media).execute()
    logger.info("Video YouTube'a yüklendi!")

# --- Main ---
def main():
    videos = fetch_shorts()
    clusters = cluster_by_title(videos)
    pioneer = pioneer_video(clusters)
    title = pioneer["snippet"]["title"]
    thumb = pioneer["snippet"]["thumbnails"]["high"]["url"]
    prompt = gemini_verify_and_prompt(thumb,title)
    clip_path = generate_video(prompt,0)
    if not clip_path: sys.exit("Video üretilemedi")
    audio_path = download_audio()
    final = OUT_DIR / "short_video.mp4"
    clip = VideoFileClip(clip_path)
    audio = AudioFileClip(audio_path).subclip(0,clip.duration)
    clip = clip.set_audio(audio)
    clip.write_videofile(str(final),fps=24,codec="libx264",audio_codec="aac",logger=None)
    upload_to_youtube(str(final),title)

if __name__=="__main__":
    main()
