
from pathlib import Path
import re

html_path = Path("data/artifacts_debug/debug_content.html")
if not html_path.exists():
    print("File not found")
    exit(1)

content = html_path.read_text(encoding="utf-8")




# Find string "Superior Twin"
matches = re.finditer(r"Superior Twin", content, re.IGNORECASE)

print("Checking ALL 'Superior Twin' matches...")
for i, match in enumerate(matches):
    start = max(0, match.start() - 300)
    end = min(len(content), match.end() + 300)
    chunk = content[start:end]

    # Simple formatting
    chunk = chunk.replace("><", ">\n<")

    print(f"--- Match {i+1} ---")
    print(chunk)
    print("-------------------")
