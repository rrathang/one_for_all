import os

file_path = "w:/Projects/WebApps/OFA/BackEnd/templates/index.html"

with open(file_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Find the indices
start_modals = -1
end_modals = -1
head_end = -1
body_start = -1

for i, line in enumerate(lines):
    if "<!-- Edit Environment Variable Modal -->" in line:
        start_modals = i
    if '<script defer src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>' in line:
        end_modals = i
    if "</head>" in line:
        head_end = i
    if "<body>" in line:
        body_start = i

if start_modals != -1 and end_modals != -1 and body_start != -1:
    modals = lines[start_modals:end_modals+1]
    
    # Remove modals from their current location
    del lines[start_modals:end_modals+1]
    
    # Recalculate body_start
    for i, line in enumerate(lines):
        if "<body>" in line:
            body_start = i
            break
            
    # Insert modals after body
    lines = lines[:body_start+1] + ["\n"] + modals + ["\n"] + lines[body_start+1:]
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print("Modals moved to body successfully!")
else:
    print(f"Could not find indices: {start_modals}, {end_modals}, {body_start}")
