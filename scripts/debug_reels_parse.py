import re

def extract_urls():
    with open("/home/vu/toolsauto/reels_body.html", "r", encoding="utf-8") as f:
        content = f.read()

    # Look for both unescaped and escaped urls
    # e.g. https://www.facebook.com/reel/123456 or https:\/\/www.facebook.com\/reel\/123456
    pattern = r'(https:[\\/]+www\.facebook\.com[\\/]+reel[\\/]+\d+)'
    matches = set(re.findall(pattern, content))
    
    print(f"Found {len(matches)} reel URLs:")
    for m in list(matches)[:20]:
        print(m.replace('\\/', '/'))

if __name__ == "__main__":
    extract_urls()
