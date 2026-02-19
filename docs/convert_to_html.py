import markdown2

with open('A2A_MASTER_PLAN.md', 'r', encoding='utf-8') as f:
    md_content = f.read()

html = markdown2.markdown(md_content, extras=['tables', 'fenced-code-blocks', 'header-ids', 'code-friendly'])

html_template = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>A2A Master Plan - Niv AI</title>
<style>
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; max-width: 900px; margin: 0 auto; padding: 40px; color: #333; }
h1 { color: #7c3aed; border-bottom: 3px solid #7c3aed; padding-bottom: 10px; }
h2 { color: #5b21b6; margin-top: 40px; border-bottom: 1px solid #ddd; padding-bottom: 8px; }
h3 { color: #6d28d9; }
code { background: #f3f4f6; padding: 2px 6px; border-radius: 4px; font-size: 0.9em; }
pre { background: #1e1e1e; color: #d4d4d4; padding: 16px; border-radius: 8px; overflow-x: auto; }
pre code { background: none; color: inherit; }
table { border-collapse: collapse; width: 100%; margin: 20px 0; }
th, td { border: 1px solid #ddd; padding: 12px; text-align: left; }
th { background: #f8f9fa; font-weight: 600; }
tr:nth-child(even) { background: #f8f9fa; }
blockquote { border-left: 4px solid #7c3aed; margin: 20px 0; padding: 10px 20px; background: #f5f3ff; }
a { color: #7c3aed; }
hr { border: none; border-top: 2px solid #e5e7eb; margin: 40px 0; }
@media print { body { max-width: 100%; padding: 20px; } pre { white-space: pre-wrap; } }
</style>
</head>
<body>
%CONTENT%
</body>
</html>"""

html_full = html_template.replace('%CONTENT%', html)

with open('A2A_MASTER_PLAN.html', 'w', encoding='utf-8') as f:
    f.write(html_full)

print('Done! Open A2A_MASTER_PLAN.html in browser, then Ctrl+P to print as PDF')
