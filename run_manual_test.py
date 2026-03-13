import sys
import os

# To test headlessly with print output showing
import subprocess

process = subprocess.Popen(["xvfb-run", "-a", sys.executable, "test_switch_page.py"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
stdout, stderr = process.communicate()

print("STDOUT:")
print(stdout)
print("STDERR:")
print(stderr)

