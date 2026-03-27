from bs4 import BeautifulSoup
with open("/home/vu/toolsauto/logs/fb/job_456_navigate_next.html", "r", encoding="utf-8") as f: # or job_456_post_clicked? No, navigate_next
    html = f.read()
soup = BeautifulSoup(html, 'html.parser')
buttons = soup.find_all(lambda tag: tag.has_attr('role') and tag['role'] in ['button', 'dialog'])
for b in buttons:
    try:
        text = b.get_text(separator=' ', strip=True)[:100]
        label = b.get('aria-label', '')
        print(f"Role: {b['role']}, Text: {text}, Label: {label}")
    except: pass
