import subprocess, os, json

platform_dir = "/tmp"
mat_id = 999
output_template = os.path.join(platform_dir, f"viral_{mat_id}_%(id)s.%(ext)s")
cmd = [
    "yt-dlp",
    "--max-filesize", "10M",
    "--write-info-json",
    "-o", output_template,
    "https://www.tiktok.com/@vtcnow/video/7479427013876616466"
]
subprocess.run(cmd, capture_output=True, text=True)

import glob
json_files = glob.glob(os.path.join(platform_dir, f"viral_{mat_id}_*.info.json"))
if json_files:
    print(f"Found JSON: {json_files[0]}")
    with open(json_files[0]) as f:
        data = json.load(f)
        print(f"Views: {data.get('view_count')}")
        print(f"Title: {data.get('title')}")
else:
    print("No JSON found")
