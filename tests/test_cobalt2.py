import requests
import json

def test_cobalt_v7():
    url = "https://vt.tiktok.com/ZSurL13nb/"
    api_url = "https://api.cobalt.tools/api/json"
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    
    payload = {
        "url": url,
        "vCodec": "h264",
        "vQuality": "1080",
        "aFormat": "mp3",
        "isAudioOnly": False,
        "isNoTTWatermark": True
    }
    
    print(f"Testing Cobalt v7/v8 with: {url}")
    try:
        # Some public instances use different endpoints or routes, let's try the main one with specific headers
        resp = requests.post("https://co.wuk.sh/api/json", json=payload, headers=headers, timeout=15)
        print(f"Status Code: {resp.status_code}")
        print("Response:", resp.text)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_cobalt_v7()
