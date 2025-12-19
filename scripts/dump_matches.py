
from pathlib import Path
import re

html_path = Path("data/artifacts_debug/debug_content.html")
content = html_path.read_text(encoding="utf-8")

matches = re.finditer(r"Deluxe Quadruple", content, re.IGNORECASE)

output = []
for i, match in enumerate(matches):
    start = max(0, match.start() - 2000)
    end = min(len(content), match.end() + 2000)
    chunk = content[start:end]
    output.append(f"<!-- MATCH {i+1} -->\n{chunk}\n<!-- END MATCH {i+1} -->\n")

Path("data/deluxe_context.html").write_text("\n".join(output), encoding="utf-8")
print("Dumped matches to data/deluxe_context.html")
