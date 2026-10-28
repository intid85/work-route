"""site/ 를 Claude 미리보기 페이지(artifact/)로 바꿉니다.

미리보기 환경은 Google Fonts 외 외부 스타일시트를 막기 때문에 글꼴을 Noto Sans KR로 바꾸고,
첫 페이지는 문서 껍데기(<html>, <head>, <body>)를 벗겨 내용만 남깁니다.
"""
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC, DST = ROOT / "site", ROOT / "artifact"

FONT_OLD = re.compile(r'<link rel="stylesheet" href="https://cdn\.jsdelivr\.net/gh/orioncactus/pretendard[^"]*">')
FONT_NEW = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700;800&display=swap">')
SIDES = '<meta name="claude:viewport-fit-sides" content="cover">'

if DST.exists():
    shutil.rmtree(DST)
shutil.copytree(SRC, DST, ignore=shutil.ignore_patterns("CNAME", "sitemap.xml", "robots.txt", ".nojekyll", "404.html"))

for f in DST.rglob("*.html"):
    html = FONT_OLD.sub(FONT_NEW, f.read_text(encoding="utf-8"))
    html = html.replace('<meta name="viewport" content="width=device-width, initial-scale=1">',
                        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">' + SIDES)
    if f == DST / "index.html":
        title = re.search(r"<title>.*?</title>", html, re.S).group(0)
        head = re.search(r"<head>(.*?)</head>", html, re.S).group(1)
        head = re.sub(r"<meta charset[^>]*>|<meta name=\"viewport\"[^>]*>|<title>.*?</title>", "", head, flags=re.S)
        head = head.replace(SIDES, "")
        body = re.search(r"<body>(.*)</body>", html, re.S).group(1)
        html = "<title>Work Route</title>\n" + SIDES + "\n" + head.strip() + "\n" + body.strip() + "\n"
    f.write_text(html, encoding="utf-8")

files = sorted(str(p.relative_to(DST)) for p in DST.rglob("*") if p.is_file() and p.name != "index.html" or (p.is_file() and p.parent != DST))
print("\n".join(files))
