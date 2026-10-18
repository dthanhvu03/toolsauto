import requests

def test_cobalt():
    url = "https://www.instagram.com/reel/DVbrsWRElmi/"
    api_url = "https://api.cobalt.tools/"
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    
    payload = {
        "url": url,
        "videoQuality": "1080",
        "audioFormat": "mp3",
        "isAudioOnly": False,
        "isNoTTWatermark": True
    }
    
    print(f"Testing Cobalt API with: {url}")
    try:
        resp = requests.post(api_url, json=payload, headers=headers, timeout=15)
        print(f"Status Code: {resp.status_code}")
        print("Response:", resp.text)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_cobalt()
