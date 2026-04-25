import os

def load_html_files(root_folder):
    html_files = []

    for file in os.listdir(root_folder):
        full_path = os.path.join(root_folder, file)

        # Ignore folders
        if not os.path.isfile(full_path):
            continue

        # Only HTML files
        if not file.endswith(".html"):
            continue

        with open(full_path, "r", encoding="utf-8") as f:
            html_files.append({
                "file": file,
                "path": full_path,
                "html": f.read()
            })

    return html_files