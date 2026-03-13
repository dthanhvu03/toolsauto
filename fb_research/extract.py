import zipfile
import xml.etree.ElementTree as ET
import os

def extract_text_from_docx(docx_path):
    try:
        with zipfile.ZipFile(docx_path) as docx:
            xml_content = docx.read('word/document.xml')
            tree = ET.fromstring(xml_content)
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            paragraphs = []
            for p in tree.findall('.//w:p', ns):
                texts = [node.text for node in p.findall('.//w:t', ns) if node.text]
                if texts:
                    paragraphs.append(''.join(texts))
            return '\n'.join(paragraphs)
    except Exception as e:
        return str(e)

directory = '/home/vu/toolsauto/fb_research'
for filename in os.listdir(directory):
    if filename.endswith('.docx'):
        path = os.path.join(directory, filename)
        txt_path = path.replace('.docx', '.txt')
        text = extract_text_from_docx(path)
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f"Extracted {filename}")
