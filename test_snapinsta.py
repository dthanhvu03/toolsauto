import requests

def test_snapinsta():
    url = "https://www.instagram.com/reel/DVbrsWRElmi/"
    print(f"Testing public SnapInsta wrapper or similar with: {url}")
    # There are public generic APIs for social downloads
    # For example, let's try a common free one: socialdownload.io or similar
    # Another reliably free one is the pub.social api if available, let's test a generic request
    
    # We will just write a placeholder script to test some public endpoints
    endpoints = [
        "https://api.vkrdownloader.co/api/ajax.php?url=" + url,
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    
    for api_url in endpoints:
        print(f"Testing: {api_url}")
        try:
            resp = requests.post(api_url, headers=headers, timeout=10)
            print(resp.status_code)
            print(resp.text[:300])
        except Exception as e:
            print(e)

if __name__ == "__main__":
    test_snapinsta()
