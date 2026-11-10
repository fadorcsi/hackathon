"""Web app: drop a report, paste 3 posts you liked, get 3 LinkedIn posts + an article.

Run:  python app.py          (then open http://localhost:8000)
      DEMO=1 python app.py   (no API key needed; returns a canned example)
"""

import os
import traceback

import anthropic
from flask import Flask, jsonify, redirect, request, send_from_directory

import article
import drafter
import linkedin
import post_queue

app = Flask(__name__, static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # API request limit for PDFs


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/api/status")
def status():
    return jsonify({"demo": _demo_mode(), "voice": drafter.default_voice()})


def _demo_mode() -> bool:
    return os.environ.get("DEMO") == "1" or not drafter.has_credentials()


@app.post("/api/draft")
def draft():
    if _demo_mode() or request.form.get("demo") == "1":
        return jsonify(drafter.demo_result() | {"demo": True})

    f = request.files.get("report")
    pasted = request.form.get("report_text", "").strip()
    if f and f.filename:
        report = drafter.Report(f.filename, f.read())
    elif pasted:
        report = drafter.Report("report.txt", pasted.encode())
    else:
        return jsonify({"error": "Add a report (PDF/TXT/MD) or paste its text."}), 400

    samples = []
    for i in range(1, 4):
        text = request.form.get(f"post{i}", "")
        if text.strip():
            samples.append({"text": text, "whose": request.form.get(f"whose{i}", "unspecified")})
    if not samples:
        return jsonify({"error": "Paste at least one post you liked."}), 400

    try:
        result = drafter.run(report, samples, request.form.get("style_notes", ""),
                             request.form.get("language", "en"))
    except anthropic.AuthenticationError:
        return jsonify({"error": "Anthropic API key is missing or invalid."}), 401
    except anthropic.RateLimitError:
        return jsonify({"error": "Rate limited by the API, wait a minute and retry."}), 429
    except anthropic.APIStatusError as e:
        return jsonify({"error": f"API error {e.status_code}: {e.message}"}), 502
    except anthropic.APIConnectionError:
        return jsonify({"error": "Could not reach the Anthropic API."}), 502
    except Exception as e:  # surface the reason in the UI during the hackathon
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    return jsonify(result | {"demo": False})


# ---------- article -> post ----------

@app.get("/post")
def post_page():
    return send_from_directory("static", "post.html")


@app.post("/api/article")
def article_draft():
    data = request.get_json(force=True)
    url = (data.get("url") or "").strip()
    pasted = (data.get("text") or "").strip()
    if _demo_mode():
        return jsonify(article.demo_post(url))
    try:
        if pasted:
            title, text = data.get("title", ""), pasted
        elif url:
            title, text = article.fetch_article(url)
        else:
            return jsonify({"error": "Paste a link to an article (or its text)."}), 400
        return jsonify(article.draft_post(title, text, url, drafter.default_voice(), data.get("language", "en")))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except anthropic.APIError as e:
        return jsonify({"error": f"Claude API error: {e}"}), 502
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Couldn't open that link ({e}). Paste the article text instead."}), 400


# ---------- queue ----------

@app.get("/api/queue")
def queue_list():
    return jsonify({"posts": post_queue.list_posts(), "linkedin": linkedin.status()})


@app.post("/api/queue")
def queue_save():
    d = request.get_json(force=True)
    try:
        p = post_queue.save(d.get("text", ""), d.get("source_url", ""), d.get("source_title", ""),
                            d.get("scheduled_at") or None, d.get("id"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if d.get("post_now"):
        p = post_queue.publish_now(p["id"])
    return jsonify(p)


@app.post("/api/queue/<int:pid>/publish")
def queue_publish(pid):
    return jsonify(post_queue.publish_now(pid))


@app.delete("/api/queue/<int:pid>")
def queue_delete(pid):
    post_queue.delete(pid)
    return jsonify({"ok": True})


# ---------- LinkedIn login ----------

@app.get("/auth/linkedin")
def li_login():
    if not linkedin.configured():
        return ("LinkedIn app not set up yet. Set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET "
                "(see linkedin.py for the 10-minute setup), then restart."), 400
    return redirect(linkedin.login_url())


@app.get("/auth/linkedin/callback")
def li_callback():
    if request.args.get("error"):
        return f"LinkedIn login cancelled: {request.args.get('error_description', '')}", 400
    try:
        linkedin.finish_login(request.args["code"], request.args.get("state", ""))
    except Exception as e:
        return f"LinkedIn login failed: {e}", 400
    return redirect("/post")


@app.post("/api/linkedin/disconnect")
def li_disconnect():
    linkedin.disconnect()
    return jsonify(linkedin.status())


if __name__ == "__main__":
    post_queue.start_scheduler()
    port = int(os.environ.get("PORT", 8000))
    print(f"Research to Posts on http://localhost:{port}  (demo mode: {_demo_mode()})")
    app.run(host="0.0.0.0", port=port, debug=False)
