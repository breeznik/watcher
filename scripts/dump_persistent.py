
from pathlib import Path
import re

html_path = Path("data/artifacts_debug/debug_content.html")
if not html_path.exists():
    print("File not found")
    exit(1)

content = html_path.read_text(encoding="utf-8")

matches = re.finditer(r"Deluxe Quadruple", content, re.IGNORECASE)

output = []
for i, match in enumerate(matches):
    start = max(0, match.start() - 1000)
    end = min(len(content), match.end() + 1000)
    chunk = content[start:end]
    output.append(f"<!-- PERSISTENT MATCH {i+1} -->\n{chunk}\n<!-- END PERSISTENT MATCH {i+1} -->\n")

Path("data/persistent_matches.html").write_text("\n".join(output), encoding="utf-8")
print(f"Dumped {len(output)} persistent matches to data/persistent_matches.html")
