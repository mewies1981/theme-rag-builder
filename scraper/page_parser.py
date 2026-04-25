
from bs4 import BeautifulSoup

def extract_sections(html):
    soup = BeautifulSoup(html, "lxml")

    candidates = [
        "div.mw-parser-output",
        "article",
        "div.content",
        "main"
    ]

    content = None

    for selector in candidates:
        content = soup.select_one(selector)
        if content:
            break

    # last fallback
    if not content:
        content = soup.body

    if not content:
        return []

    # extract structured text
    blocks = content.find_all(["p", "h1", "h2", "h3", "li"])

    sections = []
    current_section = []

    for b in blocks:
        text = b.get_text(strip=True)

        if not text:
            continue

        # treat headings as section separators
        if b.name in ["h1", "h2", "h3"]:
            if current_section:
                sections.append({
                    "section": "auto",
                    "text": "\n".join(current_section)
                })
                current_section = []
        else:
            current_section.append(text)

    if current_section:
        sections.append({
            "section": "auto",
            "text": "\n".join(current_section)
        })

    return sections