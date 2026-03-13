import requests

def test_cobalt_tiktok():
    url = "https://vt.tiktok.com/ZSurL13nb/"
    api_url = "https://api.cobalt.tools/api/json"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    payload = {
        "url": url
    }
    print(f"Testing Cobalt with: {url}")
    try:
        resp = requests.post(api_url, json=payload, headers=headers, timeout=15)
        print(f"Status Code: {resp.status_code}")
        if resp.status_code == 200:
            print("Response:", resp.json())
        else:
            print("Error Response:", resp.text)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_cobalt_tiktok()
