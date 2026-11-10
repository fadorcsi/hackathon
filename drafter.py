"""Research to Posts: turn a report into 3 LinkedIn posts + a short article.

Pipeline
  1. extract_figures  - Claude reads the report and pulls out the strongest figures,
                        each with a verbatim quote and page number.
  2. verify_figures   - we check every quote/number against the report text ourselves,
                        so an invented statistic is flagged before it reaches LinkedIn.
  3. draft            - Claude writes 3 posts + 1 article, each anchored to a verified
                        figure, in a voice learned from the sample posts.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
from pathlib import Path
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"


# ---------- schemas ----------

class Figure(BaseModel):
    id: str = Field(description="Short id like F1, F2 ...")
    value: str = Field(description="The number exactly as written in the report, e.g. '37%' or '€2.4 bn'")
    what_it_measures: str = Field(description="One plain-English line: what this number is about")
    verbatim_quote: str = Field(description="The exact sentence from the report containing the number, copied character for character")
    page: int = Field(description="1-based page number where the quote appears (1 for plain-text reports)")
    why_it_matters: str = Field(description="Why a LinkedIn audience would care, in one line")


class FigureList(BaseModel):
    report_title: str
    report_publisher: str = Field(description="Who published the report, or 'unknown'")
    figures: list[Figure]


class Post(BaseModel):
    figure_id: str
    angle: Literal["contrarian", "practical", "story"] = Field(
        description="contrarian = challenges a belief; practical = what to do about it; story = human/industry narrative")
    hook: str = Field(description="The first 1-2 lines shown before '...see more'")
    body: str = Field(description="The rest of the post, LinkedIn formatting (short lines, blank lines between)")
    closing_question: str = Field(description="One question to invite comments, or empty string if it does not fit the voice")
    source_line: str = Field(description="Source credit as the author writes it, e.g. 'Source: <report title>' or 'Forrás: ...'")
    hashtags: list[str] = Field(description="Empty list if the sample posts use no hashtags")


class Article(BaseModel):
    title: str
    subtitle: str
    figure_ids: list[str]
    body_markdown: str = Field(description="400-600 words, markdown with ## subheadings")


class Drafts(BaseModel):
    voice_profile: list[str] = Field(description="5-7 concrete observations about the voice you are imitating")
    posts: list[Post] = Field(description="Exactly 3 posts, each on a different figure and a different angle")
    article: Article


# ---------- report loading ----------

class Report:
    """Holds the report both as something to send to Claude and as page text to verify against."""

    def __init__(self, name: str, data: bytes):
        self.name = name
        self.is_pdf = name.lower().endswith(".pdf") or data[:4] == b"%PDF"
        self.data = data
        if self.is_pdf:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            self.pages = [(p.extract_text() or "") for p in reader.pages]
        else:
            self.pages = [data.decode("utf-8", errors="replace")]

    @classmethod
    def from_path(cls, path: str | Path) -> "Report":
        p = Path(path)
        return cls(p.name, p.read_bytes())

    def content_block(self) -> dict:
        if self.is_pdf:
            return {
                "type": "document",
                "source": {"type": "base64", "media_type": "application/pdf",
                           "data": base64.standard_b64encode(self.data).decode()},
                "title": self.name,
            }
        return {
            "type": "document",
            "source": {"type": "text", "media_type": "text/plain", "data": self.pages[0]},
            "title": self.name,
        }


# ---------- Claude calls ----------

def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


def _call(content: list, schema: type[BaseModel], system: str, effort: str = "high"):
    resp = _client().beta.messages.parse(
        model=MODEL,
        max_tokens=16000,
        betas=[FALLBACK_BETA],
        fallbacks="default",
        output_config={"effort": effort},
        system=system,
        messages=[{"role": "user", "content": content}],
        output_format=schema,
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("Claude declined this request.")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("Output was cut off (max_tokens). Try a shorter report.")
    return resp.parsed_output


EXTRACT_SYSTEM = """You are a research analyst preparing a report for social media.
Pick the 6-8 most striking, specific, quotable figures in the report: numbers that
surprise, quantify a trend, or change a decision. Skip vague or methodology numbers.
For each, copy the sentence containing it EXACTLY as it appears (same words, same
number formatting) and give the page it is on. Never compute, round or combine numbers."""


def extract_figures(report: Report) -> FigureList:
    return _call(
        [report.content_block(),
         {"type": "text", "text": "Extract the key figures from this report."}],
        FigureList, EXTRACT_SYSTEM)


DRAFT_SYSTEM = """You ghostwrite LinkedIn content for a professional who works on water,
climate and the economics of adaptation. You will get verified figures from a report
and sample posts.

Voice: samples marked "mine" are the author's own posts; samples marked "admired" are
posts by others they like. Learn FORMAT and hooks from all samples; learn TONE,
vocabulary, sentence length, bullet style, emoji and hashtag habits primarily from the
author's own posts (if none are marked, blend all). Follow the author style notes when
given. Write in first person as the author. Match what the samples do, not generic
LinkedIn habits: if they use no hashtags or emojis, use none.

Rules:
- Each of the 3 posts is built on exactly one figure, a different one each, and uses a
  different angle (contrarian, practical, story). Supporting figures from the list may
  appear, but the anchor figure leads.
- Quote every number exactly as given. Never calculate, round, invert or combine numbers
  (no "97.6% is wasted" from "2.4% is reused"). Do not invent any statistic, name, place,
  or claim that is not in the figures list. Credit the source report in source_line.
- Posts: 100-220 words. The first line is the hook.
- The article: 400-600 words, can combine 2-3 figures, written for LinkedIn Articles,
  same voice, ## subheadings.
- Write everything in the requested output language."""


LANGUAGES = {"en": "English", "hu": "Hungarian (magyar)", "report": "the same language as the report"}


def draft(figures: FigureList, sample_posts: list[dict], style_notes: str = "",
          chosen_ids: list[str] | None = None, language: str = "en") -> Drafts:
    figs = [f for f in figures.figures if not chosen_ids or f.id in chosen_ids]
    samples = "\n\n".join(
        f"<sample whose=\"{s.get('whose', 'unspecified')}\">\n{s['text'].strip()}\n</sample>"
        for s in sample_posts if s.get("text", "").strip())
    payload = {
        "report": {"title": figures.report_title, "publisher": figures.report_publisher},
        "figures": [f.model_dump() for f in figs],
    }
    text = (f"<figures>\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n</figures>\n\n"
            f"<samples>\n{samples}\n</samples>\n\n"
            + (f"<author_style_notes>\n{style_notes.strip()}\n</author_style_notes>\n\n" if style_notes.strip() else "")
            + f"Output language: {LANGUAGES.get(language, LANGUAGES['en'])}. Translate figures' context "
            "if needed but keep each number exactly as written in the figures list.\n\n"
            + "Write the 3 posts and the article.")
    return _call([{"type": "text", "text": text}], Drafts, DRAFT_SYSTEM)


# ---------- verification ----------

def _norm(s: str) -> str:
    s = s.replace(" ", " ").replace("’", "'").replace("–", "-").replace("—", "-")
    s = re.sub(r"-\s*\n\s*", "", s)  # de-hyphenate line breaks
    return re.sub(r"\s+", " ", s).strip().lower()


def _digits(s: str) -> list[str]:
    return re.findall(r"\d+(?:[.,]\d+)?", s)


def verify_figures(report: Report, figures: FigureList) -> dict[str, dict]:
    """For each figure: is the quote in the report, on which page, and is the number in the quote?"""
    pages = [_norm(p) for p in report.pages]
    have_text = any(len(p) > 50 for p in pages)
    out = {}
    for f in figures.figures:
        q = _norm(f.verbatim_quote)
        found_page = next((i + 1 for i, p in enumerate(pages) if q and q in p), None)
        if found_page is None and q:
            # tolerate PDF extraction quirks: match on a long middle chunk of the quote
            chunk = q[len(q) // 4: len(q) // 4 + max(30, len(q) // 2)]
            found_page = next((i + 1 for i, p in enumerate(pages) if len(chunk) >= 25 and chunk in p), None)
        nums = _digits(f.value)
        num_in_quote = all(n in f.verbatim_quote for n in nums) if nums else True
        num_on_page = (found_page is not None and all(n in report.pages[found_page - 1] for n in nums)) if nums else True
        if not have_text:
            status = "unchecked"  # scanned PDF with no text layer
        elif found_page and num_in_quote and num_on_page:
            status = "verified"
        elif num_in_quote and any(all(n in p for n in nums) for p in report.pages):
            status = "partial"   # number exists but quote wording differs
        else:
            status = "not_found"
        out[f.id] = {"status": status, "page_found": found_page if status == "verified" else None,
                     "page_claimed": f.page}
    return out


_YEARS = re.compile(r"^(19|20)\d\d$")


def unsupported_numbers(report: Report, text: str) -> list[str]:
    """Numbers in a draft that never appear in the report (e.g. a derived '97.6%')."""
    corpus = " ".join(report.pages)
    corpus_nums = set(_digits(corpus))
    bad = []
    for n in _digits(text):
        if n in corpus_nums or n in bad or _YEARS.match(n):
            continue
        if n.isdigit() and int(n) <= 10:  # list numbering, "three questions", etc.
            continue
        bad.append(n)
    return bad


def check_drafts(report: Report, drafts: Drafts) -> dict:
    return {
        "posts": [unsupported_numbers(report, f"{p.hook}\n{p.body}\n{p.closing_question}\n{p.source_line}") for p in drafts.posts],
        "article": unsupported_numbers(report, f"{drafts.article.title}\n{drafts.article.subtitle}\n{drafts.article.body_markdown}"),
    }


# ---------- end to end ----------

def run(report: Report, sample_posts: list[dict], style_notes: str = "", language: str = "en") -> dict:
    figures = extract_figures(report)
    checks = verify_figures(report, figures)
    usable = [f.id for f in figures.figures if checks[f.id]["status"] in ("verified", "partial", "unchecked")]
    if len(usable) < 3:
        usable = [f.id for f in figures.figures]  # still draft, the UI shows the warnings
    drafts = draft(figures, sample_posts, style_notes, usable, language)
    return {"figures": figures.model_dump(), "checks": checks, "drafts": drafts.model_dump(),
            "unsupported": check_drafts(report, drafts)}


def demo_result() -> dict:
    return json.loads((Path(__file__).parent / "samples" / "demo_output.json").read_text(encoding="utf-8"))


def default_voice() -> dict:
    return json.loads((Path(__file__).parent / "samples" / "voice_posts.json").read_text(encoding="utf-8"))


def has_credentials() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
