import requests

def test_instances():
    url = "https://www.instagram.com/reel/DVbrsWRElmi/"
    
    # List of known public cobalt instances
    instances = [
        "https://co.wuk.sh/api/json",
        "https://cobalt.wuk.sh/api/json",
        "https://api.cobalt.tools/api/json",
        "https://cobalt.101010.top/api/json",
        "https://cobalt.twiwt.org/api/json",
        "https://cobalt.unblockit.tools/api/json"
    ]
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    }
    
    payload = {
        "url": url,
    }
    
    for api_url in instances:
        print(f"\nTesting instance: {api_url}")
        try:
            resp = requests.post(api_url, json=payload, headers=headers, timeout=5)
            print(f"Status Code: {resp.status_code}")
            if resp.status_code == 200:
                print("SUCCESS!", resp.json())
                break
            else:
                print("Response:", resp.text[:200])
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    test_instances()
