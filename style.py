"""Dóra's house style as hard checks, run on every draft so style isn't left to the prompt alone.

enforce() silently fixes what is safe to fix (hashtags, emojis, spacing).
check() lists anything else that is off-style, shown to her before she schedules.
"""

from __future__ import annotations

import re

EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF️‍]")
HASHTAG = re.compile(r"(?<![\w&])#[\wÀ-ž]+")
BANNED = ["in today's world", "here's why", "let's dive", "game-changer", "game changer", "unlock the power",
          "excited to share", "thrilled to", "delve", "in conclusion"]


def enforce(text: str) -> tuple[str, list[str]]:
    fixes = []
    if HASHTAG.search(text):
        text = HASHTAG.sub("", text)
        fixes.append("Removed hashtags (you don't use them).")
    if EMOJI.search(text):
        text = EMOJI.sub("", text)
        fixes.append("Removed emojis (you don't use them).")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text, fixes


def check(text: str, url: str = "") -> list[str]:
    issues = []
    body = text.replace(url, "") if url else text
    words = len(body.split())
    if words > 220:
        issues.append(f"{words} words; your posts are usually under 200.")
    first = text.strip().split("\n", 1)[0]
    if len(first) > 120:
        issues.append("The first line is long; your hooks are one short line.")
    if "!" in body:
        issues.append("Contains an exclamation mark; your posts don't use them.")
    low = body.lower()
    for b in BANNED:
        if b in low:
            issues.append(f"Uses “{b}”, which doesn't sound like you.")
    bullets = [l for l in text.split("\n") if l.strip().startswith(("•", "-", "*"))]
    if not bullets:
        issues.append("No • bullets; you usually list the key points.")
    elif any(not l.strip().startswith("•") for l in bullets):
        issues.append("Use • for bullets, as in your posts.")
    tail = text.strip().split("\n")[-2:]
    if url and url not in text:
        issues.append("The link is missing.")
    if not any(t.strip().lower().startswith(("source", "forrás")) for t in tail) and not any(
            "forrás" in t.lower() or "source" in t.lower() for t in tail):
        issues.append("End with the source (“Source: …” / “Forrás: …”) and the link.")
    if HASHTAG.search(text):
        issues.append("Contains hashtags.")
    if EMOJI.search(text):
        issues.append("Contains emojis.")
    return issues
