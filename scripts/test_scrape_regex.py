import sys
import os
import re

sys.path.insert(0, os.path.abspath('.'))

def test_regex():
    pattern = r'^([\d\.,]+)\s*(K|M|B|Tr|N|k|m|b|tr|n)?$'
    texts = [
        "1.5M",
        "120K",
        "5 Tr",
        "150 N",
        "999",
        "2,5M",
        "100k",
        "1 B",
        "111",
        "22K likes",  # Shouldn't match due to ^ and $
    ]
    
    print("--- Test Regex ---")
    for text in texts:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            num_str = match.group(1).replace(',', '.').strip()
            multiplier = match.group(2)
            
            try:
                base_val = float(num_str)
                if multiplier:
                    m = multiplier.upper()
                    if m in ['K', 'N']: # Ngàn / Kilo
                        base_val *= 1000
                    elif m in ['M', 'TR']: # Triệu / Mega
                        base_val *= 1000000
                    elif m == 'B': # Tỷ / Billion
                        base_val *= 1000000000
                        
                views = int(base_val)
                print(f"PASS: '{text}' -> {views} views")
            except Exception as e:
                print(f"FAIL Parsing: '{text}' -> {e}")
        else:
            print(f"FAIL No Match: '{text}'")

if __name__ == "__main__":
    test_regex()
