import re

filepath = '/home/vu/toolsauto/app/templates/pages/syspanel.html'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update main container
content = content.replace(
    '<div class="max-w-5xl mx-auto">',
    '<div class="max-w-[1400px] mx-auto grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6 auto-rows-max">'
)

# 2. Update all card wrappers
# Current: class="bg-white rounded-2xl shadow-sm border border-gray-100 p-4 md:p-5 mb-6"
old_card = 'class="bg-white rounded-2xl shadow-sm border border-gray-100 p-4 md:p-5 mb-6"'
new_card = 'class="bg-white rounded-2xl shadow-sm border border-gray-100 p-4 md:p-5 flex flex-col h-full"'
content = content.replace(old_card, new_card)

# 3. Span full width for specific sections
# Terminal Output is Section 7
# Finding the block comment and modifying the div after it
term_pattern = r'(<!-- ─── 7\. Terminal Output ─────────────────────────────────────────── -->\s*)<div class="bg-white'
content = re.sub(term_pattern, r'\1<div class="md:col-span-2 xl:col-span-3 bg-white', content)

log_pattern = r'(<!-- ─── 6b\. Log Viewer ───────────────────────────────────────────── -->\s*)<div class="bg-white'
content = re.sub(log_pattern, r'\1<div class="md:col-span-2 xl:col-span-3 bg-white', content)

screenshot_pattern = r'(<!-- ─── 8\. Bot Screenshots ─────────────────────────────────────────── -->\s*)<div class="bg-white'
content = re.sub(screenshot_pattern, r'\1<div class="md:col-span-2 xl:col-span-3 bg-white', content)

db_pattern = r'(<!-- ─── 6\. DB Management ───────────────────────────────────────────── -->\s*)<div class="bg-white'
content = re.sub(db_pattern, r'\1<div class="md:col-span-2 xl:col-span-1 bg-white', content)

server_actions = r'(<!-- ─── 5\. Server Actions ──────────────────────────────────────────── -->\s*)<div class="bg-white'
content = re.sub(server_actions, r'\1<div class="md:col-span-2 xl:col-span-2 bg-white', content)


with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print("Applied bento grid layout to syspanel")
