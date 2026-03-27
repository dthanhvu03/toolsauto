import re
from html.parser import HTMLParser

class ButtonParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_button = False
        self.current_attrs = {}
        self.current_text = []

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        # Check if it's a button or role="button" or role="dialog"
        if tag == 'button' or attr_dict.get('role') in ['button', 'dialog']:
            self.in_button = True
            self.current_attrs = attr_dict
            self.current_text = []

    def handle_endtag(self, tag):
        if self.in_button and (tag == 'button' or tag == 'div' or tag == 'span'):
            text = "".join(self.current_text).strip()
            # If the text is interesting, print it
            if re.search(r'(?i)(Tiếp|Next|Đăng|Xong)', text) or self.current_attrs.get('aria-label'):
                label = self.current_attrs.get('aria-label', '')
                if re.search(r'(?i)(Tiếp|Next|Đăng|Xong)', text) or re.search(r'(?i)(Tiếp|Next|Đăng|Xong)', label):
                    print(f"Tag: {tag}, Role: {self.current_attrs.get('role', '')}, Text: '{text[:100]}', Label: '{label}'")
            self.in_button = False

    def handle_data(self, data):
        if self.in_button:
            self.current_text.append(data)

with open("/home/vu/toolsauto/logs/fb/job_456_navigate_next.html", "r", encoding="utf-8") as f:
    html = f.read()

parser = ButtonParser()
parser.feed(html)
