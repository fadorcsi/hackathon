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
3. **Draft in your voice.** Claude learns format and hooks from all three sample posts, and tone mainly from the ones you mark as **My post**. It writes 3 posts (contrarian, practical and story angles, a different figure each) plus a 400 to 600 word article.
4. **Catch extra numbers.** Any number in a draft that doesn't appear in the report (e.g. a calculated "97.6%") is flagged in red on that card.

Each card shows a LinkedIn-style preview with the "…see more" fold, a character count, the source quote, and a Copy button.

## Run it

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...   # without a key the app runs in demo mode
python app.py                          # open http://localhost:8000
```

Demo mode (`DEMO=1 python app.py`, or no key set) returns a canned result built from `samples/sample_report.md`, a **fictional** report, so you can rehearse the pitch offline.

## Files

- `drafter.py`: pipeline (extract → verify → draft → check numbers), Claude API calls with structured outputs
- `app.py`: Flask server
- `static/index.html`: the whole UI
- `samples/`: fictional sample report and demo output

Uses `claude-opus-5-5` with adaptive thinking, structured outputs and server-side refusal fallbacks.

## Not included (yet)

Posting to LinkedIn. Drafts are copy-and-paste. A scheduler connector such as Typefully or Taplio could push them as LinkedIn drafts later.
