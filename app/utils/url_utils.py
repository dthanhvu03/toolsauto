def canonical_fb_url(url: str) -> str:
    if not url: return url
    url = url.replace("web.facebook.com", "www.facebook.com")
    url = url.replace("/reels/", "/reel/")
    url = url.rstrip("/")
    return url.lower().strip()
