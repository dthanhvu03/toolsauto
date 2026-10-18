from app.features.facebook.adapter import FacebookAdapter

def test_urls():
    adapter = FacebookAdapter()
    test_cases = [
        "https://www.facebook.com/reel/123456789012345",
        "https://www.facebook.com/share/r/abcDEfg123/",
        "https://www.facebook.com/share/v/abcDEfg123/",
        "https://www.facebook.com/profile.php?id=1000&sk=reels_tab",
        "https://www.facebook.com/123456/videos/987654321/",
        "https://www.facebook.com/page_name/videos/987654321/",
        "https://www.facebook.com/reel/",
        "/reel/123456",
        "/share/r/abcDEF/"
    ]
    
    print("Testing _normalize_post_url:\n")
    for url in test_cases:
        res = adapter._normalize_post_url(url)
        print(f"[{'PASS' if res else 'FAIL'}] {url} -> {res}")

test_urls()


