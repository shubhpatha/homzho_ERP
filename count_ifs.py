import re

with open("templates/base.html", "r", encoding="utf-8") as f:
    content = f.read()

# Find all instances of {% if ... %} and {% endif %}
ifs = [m.start() for m in re.finditer(r'\{%\s*if\b', content)]
endifs = [m.start() for m in re.finditer(r'\{%\s*endif\b', content)]

print(f"Number of ifs: {len(ifs)}")
print(f"Number of endifs: {len(endifs)}")

with open("scratch/count.txt", "w") as f:
    f.write(f"Ifs: {len(ifs)}, Endifs: {len(endifs)}\n")
