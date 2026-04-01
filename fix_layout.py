import re

filepath = '/home/vu/toolsauto/app/templates/pages/syspanel.html'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update Live Metrics to span 2 columns
content = re.sub(
    r'(<!-- ─── 1\. Live Metrics ─────────────────────────────────────────────── -->\s*)<div class="bg-white',
    r'\1<div class="md:col-span-2 xl:col-span-2 bg-white', 
    content
)

# 2. Update PM2 Processes to span 2 columns
content = re.sub(
    r'(<!-- ─── 2\. PM2 Processes ───────────────────────────────────────────── -->\s*)<div class="bg-white',
    r'\1<div class="md:col-span-2 xl:col-span-2 bg-white', 
    content
)

# 3. Job Stats can remain 1 column or 2 columns, but let's make it span what is left on row 1 (1 column)
# and PM2 processes will take row 2 (2 columns), Content & Storage (1 column). Wait, is there a specific span for Content & storage?
# Content & Storage is section 4.
# Let's check if it has spans.
pass

# 4. Add whitespace-nowrap and [&>svg]:shrink-0 to .action-btn
content = content.replace(
    '@apply flex items-center justify-center w-full sm:w-auto gap-2 px-4 py-2.5',
    '@apply flex items-center justify-center w-full sm:w-auto gap-2 px-4 py-2.5 whitespace-nowrap [&>svg]:shrink-0'
)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed layout in syspanel.html")
