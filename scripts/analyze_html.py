
from pathlib import Path
import re

html_path = Path("data/artifacts_debug/debug_content.html")
if not html_path.exists():
    print("File not found")
    exit(1)

content = html_path.read_text(encoding="utf-8")
print(f"File size: {len(content)} bytes")









# Find string "Just Palace boasts"
matches = re.finditer(r"Just Palace boasts", content, re.IGNORECASE)

print("Checking Description hierarchy...")
for i, match in enumerate(matches):
    start = max(0, match.start() - 3000)
    chunk = content[start:match.start()]
    
    tags = list(re.finditer(r"<(\w+)([^>]*)>", chunk))
    last_tags = tags[-10:]
    
    print(f"--- Description Match {i+1} Hierarchy ---")
    for t in last_tags:
        print(f"<{t.group(1)}{t.group(2)}>")
    print(f">> Just Palace boasts")
    print("-------------------")
