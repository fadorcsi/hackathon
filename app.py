"""Web app: drop a report, paste 3 posts you liked, get 3 LinkedIn posts + an article.

Run:  python app.py          (then open http://localhost:8000)
      DEMO=1 python app.py   (no API key needed; returns a canned example)
"""

import os
import traceback

import anthropic
from flask import Flask, jsonify, request, send_from_directory

import drafter

app = Flask(__name__, static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # API request limit for PDFs


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/api/status")
def status():
    return jsonify({"demo": _demo_mode()})


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
        result = drafter.run(report, samples, request.form.get("style_notes", ""))
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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"Research to Posts on http://localhost:{port}  (demo mode: {_demo_mode()})")
    app.run(host="0.0.0.0", port=port, debug=False)
