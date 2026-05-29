from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import markdown


HTML_TEMPLATE = """<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <title>{title}</title>
  <style>
    body {{
      font-family: 'Segoe UI', Arial, sans-serif;
      margin: 28px 36px;
      color: #111827;
      line-height: 1.45;
      font-size: 12pt;
    }}
    h1, h2, h3 {{ color: #0f172a; margin-top: 18px; margin-bottom: 8px; }}
    h1 {{ font-size: 20pt; }}
    h2 {{ font-size: 15pt; }}
    h3 {{ font-size: 12.5pt; }}
    p, li {{ margin-top: 5px; margin-bottom: 5px; }}
    table {{
      border-collapse: collapse;
      width: 100%;
      margin: 10px 0 14px 0;
      font-size: 10.5pt;
      table-layout: auto;
    }}
    th, td {{
      border: 1px solid #d1d5db;
      padding: 6px 8px;
      text-align: left;
      vertical-align: top;
      word-wrap: break-word;
    }}
    th {{
      background: #f3f4f6;
      font-weight: 600;
    }}
    img {{
      max-width: 100%;
      height: auto;
      display: block;
      margin: 10px auto;
      border: 1px solid #e5e7eb;
    }}
    code {{
      background: #f3f4f6;
      padding: 1px 3px;
      border-radius: 3px;
    }}
    @page {{
      size: Letter;
      margin: 0.55in;
    }}
  </style>
</head>
<body>
{content}
</body>
</html>
"""


def find_edge() -> Path:
    candidates = [
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError("Microsoft Edge executable was not found.")


def md_to_html(md_path: Path, html_path: Path) -> None:
    import re
    md_text = md_path.read_text(encoding="utf-8", errors="ignore")
    rendered = markdown.markdown(md_text, extensions=["tables", "fenced_code", "sane_lists"])
    # Convert relative img src paths to absolute file:/// URIs so Edge headless can find them
    base_dir = md_path.resolve().parent
    def _abs_img(m: re.Match) -> str:
        src = m.group(1)
        if not src.startswith(("http://", "https://", "file:///")):
            abs_path = (base_dir / src).resolve()
            src = abs_path.as_uri()
        return f'src="{src}"'
    rendered = re.sub(r'src="([^"]+)"', _abs_img, rendered)
    html = HTML_TEMPLATE.format(title=md_path.stem, content=rendered)
    html_path.write_text(html, encoding="utf-8")


def html_to_pdf_with_edge(html_path: Path, pdf_path: Path) -> None:
    edge = find_edge()
    file_url = html_path.resolve().as_uri()
    cmd = [
        str(edge),
        "--headless",
        "--disable-gpu",
        "--print-to-pdf=" + str(pdf_path.resolve()),
        file_url,
    ]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Render markdown to styled PDF via Edge headless print")
    parser.add_argument("md_file", type=Path)
    parser.add_argument("pdf_file", type=Path)
    parser.add_argument("--keep-html", action="store_true", help="Keep intermediate HTML file")
    args = parser.parse_args()

    md_file = args.md_file.resolve()
    pdf_file = args.pdf_file.resolve()
    html_file = md_file.with_suffix(".rendered.html")

    md_to_html(md_file, html_file)
    html_to_pdf_with_edge(html_file, pdf_file)

    if not args.keep_html:
        html_file.unlink(missing_ok=True)

    print(f"Wrote PDF: {pdf_file}")
