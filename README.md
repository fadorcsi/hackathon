# Research to Posts

**Problem:** "Help me create LinkedIn posts automatically" / "help me write articles and research posts."

**Build:** Give it a new report and it drafts **three LinkedIn posts and a short article in your voice**, each built on a figure from the report.

**Bring:** one recent report + three posts you liked.

## How it works

1. **Find the figures.** Claude reads the report (PDF/TXT/MD) and pulls out 6 to 8 striking numbers, each with the exact sentence it came from and its page.
2. **Fact-check them.** The app (not the model) searches the report text for every quote and number:
   - `✓ verified`: quote and number found on that page
   - `≈ partial`: number is in the report, wording differs
   - `✗ not found`: likely invented, so it isn't used for drafting
3. **Draft in your voice.** Claude learns format and hooks from all three sample posts, and tone mainly from the ones you mark as **My post**. You can choose English, Hungarian, or the same language as the report. It writes 3 posts (contrarian, practical and story angles, a different figure each) plus a 400 to 600 word article.
4. **Catch extra numbers.** Any number in a draft that doesn't appear in the report (e.g. a calculated "97.6%") is flagged in red on that card.

Each card shows a LinkedIn-style preview with the "…see more" fold, a character count, the source quote, and a Copy button.

## Article → post (with scheduling)

Open **http://localhost:8000**:

1. Paste a link to an article (or paste its text if it is paywalled).
2. Claude writes a post in your voice: hook, 3 to 4 • bullets with the key messages, a punch line, a question, then the source and link. Numbers not in the article are flagged.
3. Edit it, then **Save as draft**, **Schedule** (pick a date and time) or **Post now**.
4. A scheduler inside the app publishes posts when they are due. Keep the app running.

The report page can also add any of its three posts to the same queue.

### Watching topics

The **Watching for new articles** card checks your topics every few hours (Google News in English and Hungarian, plus any RSS feeds you add). Claude sorts the new articles into worth posting or not, with a one-line reason, and drafts the best ones into your queue as **drafts**. The watcher never publishes on its own: you review each draft and click Schedule. Your topics live in `samples/watch_config.json` (English and Hungarian Google News searches, trusted sources, and Telex/444/Átlátszó feeds filtered by topic words). Edit them under *Topics & settings*. Changes are saved to `watch.json`.

Some Google News links hide the publisher's address. If a draft can't be made automatically, click **Open in editor**, or paste the text.

### Connecting LinkedIn (one time, about 10 minutes)

Until you connect, the app runs in **test mode**: posts are written to `outbox.log`, nothing goes to LinkedIn.

1. Go to https://www.linkedin.com/developers/apps and create an app (link it to the AquaRE company page).
2. **Products** tab: add *Share on LinkedIn* and *Sign In with LinkedIn using OpenID Connect*.
3. **Auth** tab: add the redirect URL `http://localhost:8000/auth/linkedin/callback`.
4. Start the app with the app's keys:
   ```bash
   LINKEDIN_CLIENT_ID=... LINKEDIN_CLIENT_SECRET=... ANTHROPIC_API_KEY=... python app.py
   ```
5. Click **Connect LinkedIn** and log in. The login lasts about 60 days, then click Connect again.

Posts go out as you, to your personal profile, through LinkedIn's official API.

## Run it

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...   # without a key the app runs in demo mode
python app.py                          # open http://localhost:8000
```

Demo mode (`DEMO=1 python app.py`, or no key set) returns a canned result built from `samples/sample_report.md`, a **fictional** report, so you can rehearse the pitch offline.

## Files

- `drafter.py`: pipeline (extract → verify → draft → check numbers), Claude API calls with structured outputs
- `article.py`: fetch an article and draft one post from it
- `linkedin.py`: LinkedIn login and publishing (test mode without login)
- `post_queue.py`: SQLite queue and the scheduler
- `watcher.py`: topic watcher (feeds → Claude ranking → drafts)
- `style.py`: your house style as hard checks (hashtags and emojis removed; anything off-style flagged while you edit)
- `tools/build_demo.py`: builds the browser-only demo page
- `app.py`: Flask server
- `static/index.html`: the whole UI
- `samples/voice_posts.json`: your three voice posts + style notes, pre-filled in the form
- `samples/sample_report.md`, `samples/demo_output.json`: fictional sample report and demo output

Uses `claude-opus-5-5` with adaptive thinking, structured outputs and server-side refusal fallbacks.

