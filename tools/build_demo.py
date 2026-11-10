"""Build the self-contained browser demo (static/post.html + a fake in-browser backend).

    python tools/build_demo.py demo.html
"""
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import article, drafter, watcher  # noqa: E402

css = (ROOT / "static/style.css").read_text(encoding="utf-8")
dark_start = css.index("@media (prefers-color-scheme: dark){")
dark_block = css[dark_start: css.index("}\n}", dark_start) + 3]
dark_vars = dark_block[dark_block.index(":root{") + 6: dark_block.rindex("}", 0, len(dark_block) - 2)]
css = css.replace(dark_block, '@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){' + dark_vars
                  + ';color-scheme:dark}}\n:root[data-theme="dark"]{' + dark_vars + ";color-scheme:dark}")
page = (ROOT / "static/post.html").read_text(encoding="utf-8")
pstyle = page[page.index("<style>") + 7:page.index("</style>")]
body = page[page.index("<body>") + 6:page.index("<script>")]
script = page[page.index("<script>") + 8:page.rindex("</script>")]
body = body.replace('<details style="margin-top:8px"><summary>Paywalled or won\'t load? Paste the text instead</summary>',
                    '<details open style="margin-top:8px"><summary>Article text (needed in this demo: the browser can\'t open links)</summary>')
body = re.sub(r"<nav>.*?</nav>", '<div class="demo-bar"><b>Demo</b> · runs in your browser with sample data. '
              'Paste the article text and Claude writes a real draft in your style, using your Claude account. Nothing is posted. The full app (opens links itself, watches the news, posts to LinkedIn) runs on your computer.</div>', body, flags=re.S)

demo = article.demo_post("")
now = dt.datetime.now(dt.timezone.utc)
seed = [{"id": 1, "created_at": now.isoformat(), "text": demo["text"], "source_url": demo["source_url"],
         "source_title": demo["source_title"], "status": "scheduled",
         "scheduled_at": (now + dt.timedelta(days=1)).replace(hour=7, minute=30, second=0, microsecond=0).isoformat(),
         "posted_at": None, "post_urn": None, "test_mode": 0, "error": None, "note": "Example scheduled post."}]
# real suggestions from a live watcher run (last 3 days, already-posted stories removed)
items = json.loads((ROOT / "tools/demo_suggestions.json").read_text(encoding="utf-8"))
fields = {k: v.description for k, v in article.ArticlePost.model_fields.items()}
data = {"article_system": article.ARTICLE_SYSTEM, "fields": fields, "languages": drafter.LANGUAGES, "seed": seed, "cfg": watcher.load_config(), "items": items, "voice": drafter.default_voice(), "draft": demo}

shim = (ROOT / "tools/demo_shim.js").read_text(encoding="utf-8").replace("__DATA__", json.dumps(data, ensure_ascii=False))
html = f"""<title>Research to Posts</title>
<meta name="claude:viewport-fit-sides" content="cover">
<style>
{css}
{pstyle}
.demo-bar{{max-width:1240px;margin:12px auto 0;padding-block:8px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));font-size:13px;color:var(--muted)}}
code{{font-size:12px}}
</style>
{body}
<script>
{shim}
{script}
</script>
"""
Path(sys.argv[1]).write_text(html, encoding="utf-8")
print("wrote", sys.argv[1], len(html), "bytes")
