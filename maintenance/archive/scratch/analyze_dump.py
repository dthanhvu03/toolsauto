import json

with open('/home/vu/toolsauto/scratch/graphql_dump.json') as f:
    d = json.load(f)

# Tìm ComposerStoryCreateMutation
print("=" * 60)
print("MUTATION: ComposerStoryCreateMutation")
print("=" * 60)
for e in d['entries']:
    if e['operation'] == 'ComposerStoryCreateMutation':
        body = e['body']
        if isinstance(body, dict):
            data = body.get('data', {})
            sc = data.get('story_create', {}) or {}
            print("story_create keys:", list(sc.keys()) if sc else "null")
            print("story_id:", sc.get('story_id'))
            print("post_id:", sc.get('post_id'))
            story = sc.get('story') or {}
            if story:
                print("story keys:", list(story.keys()))
                print("  id:", story.get('id'))
                print("  url:", story.get('url'))
                print("  permalink_url:", story.get('permalink_url'))
            
            # Try to find reel URL in nested structures
            import json as j2
            full_str = j2.dumps(body, ensure_ascii=False)
            
            # Extract all URLs
            urls_in_body = set()
            def find_urls(obj):
                if isinstance(obj, str):
                    if 'facebook.com/reel/' in obj or 'facebook.com/posts/' in obj:
                        urls_in_body.add(obj)
                elif isinstance(obj, dict):
                    for v in obj.values(): find_urls(v)
                elif isinstance(obj, list):
                    for v in obj: find_urls(v)
            find_urls(body)
            
            print("\nURLs in body:", sorted(urls_in_body))
            print("\nvariables:")
            vars_ = e.get('variables', {})
            if isinstance(vars_, dict):
                for k, v in vars_.items():
                    sv = str(v)[:200]
                    print(f"  {k}: {sv}")
            
            print("\nfull body (truncated 2000 chars):")
            print(j2.dumps(body, ensure_ascii=False, indent=2)[:2000])

print()
print("=" * 60)
print("ALL OPERATIONS in order")
print("=" * 60)
for e in d['entries']:
    urls = e.get('post_urls', [])
    marker = "🎯" if urls else "  "
    print(f"{marker} {e['ts']} | {e['operation']} | doc_id={e['doc_id']}")
