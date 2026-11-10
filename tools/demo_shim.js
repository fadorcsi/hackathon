// ---------- demo backend: answers the app's API calls inside the browser ----------
const DEMO = __DATA__;
const S = {posts: DEMO.seed, nextId: 2, cfg: DEMO.cfg, items: DEMO.items, last: null};
window.confirm = () => true;  // the demo skips confirm dialogs
const J = (d, status = 200) => Promise.resolve(new Response(JSON.stringify(d), {status, headers: {"Content-Type": "application/json"}}));
const nowIso = () => new Date().toISOString();
function tick() { for (const p of S.posts) if (p.status === "scheduled" && p.scheduled_at <= nowIso()) Object.assign(p, {status: "posted", posted_at: nowIso(), test_mode: 1}); }
function order() { const r = {scheduled: 0, draft: 1, failed: 2}; return [...S.posts].sort((a, b) => (r[a.status] ?? 3) - (r[b.status] ?? 3) || (b.scheduled_at || b.posted_at || b.created_at).localeCompare(a.scheduled_at || a.posted_at || a.created_at)); }
function sugg() { return {items: S.items.filter(i => ["relevant", "drafted"].includes(i.verdict)), last_run: S.last}; }
// ---------- real drafting with the viewer's Claude (same prompt and layout as article.py) ----------
let samplePromise = null;
const getSample = () => (samplePromise ??= (window.claude?.use ? window.claude.use("sample") : Promise.resolve(null)));
function assemble(p, url) {   // her layout, as article.assemble()
  const t = x => (x || "").trim();
  const bullets = (p.key_messages || []).map(m => "• " + String(m).replace(/^[•\-– ]+/, "").trim()).filter(b => b.length > 2).join("\n");
  const opening = [p.hook, p.source_intro, bullets, p.interpretation].map(t).filter(Boolean).join("\n");
  const source = [t(p.source_label), t(url)].filter(Boolean).join("\n");
  return [opening, p.punchline, p.closing, source].map(t).filter(Boolean).join("\n\n");
}
function enforce(text) {      // as style.enforce()
  const fixes = [];
  if (/(^|[^\w&])#[\wÀ-ž]+/.test(text)) { text = text.replace(/(^|[^\w&])#[\wÀ-ž]+/g, "$1"); fixes.push("Removed hashtags (you don't use them)."); }
  if (/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(text)) { text = text.replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\uFE0F]/gu, ""); fixes.push("Removed emojis (you don't use them)."); }
  return [text.replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim(), fixes];
}
function unsupported(article, text) {   // numbers in the draft that never appear in the article
  const nums = s => s.match(/\d+(?:[.,]\d+)?/g) || [];
  const have = new Set(nums(article)), bad = [];
  for (const n of nums(text)) if (!have.has(n) && !bad.includes(n) && !/^(19|20)\d\d$/.test(n) && !(/^\d+$/.test(n) && +n <= 10)) bad.push(n);
  return bad;
}
async function realDraft(body) {
  const text = (body.text || "").trim(), url = (body.url || "").trim();
  if (text.length < 300) return J({error: url
    ? "This browser demo can't open links. Copy the article text from the page and paste it into the Article text box, then click Draft again. (The app on your computer opens links by itself.)"
    : "Paste a link and the article text."}, 400);
  const sample = await getSample();
  if (!sample) return J({error: "Claude isn't available in this view. Open the demo on claude.ai while signed in."}, 400);
  const samples = DEMO.voice.posts.map(p => `<sample>\n${p.text.trim()}\n</sample>`).join("\n\n");
  const prompt = `${DEMO.article_system}

Reply with ONLY a JSON object with exactly these string fields (key_messages is an array of strings):
${JSON.stringify(DEMO.fields, null, 1)}

<article url="${url}">
${text.slice(0, 60000)}
</article>

<author_samples>
${samples}
</author_samples>

<author_style_notes>
${DEMO.voice.style_notes}
</author_style_notes>

Output language: ${DEMO.languages[body.language] || "English"}.
Write the post.`;
  try {
    const p = await sample.json(prompt, {modelTier: "default"});
    if (!p || !p.hook || !Array.isArray(p.key_messages)) throw {code: "invalid_json"};
    const [full, fixes] = enforce(assemble(p, url));
    return J({post: p, text: full, source_url: url, source_title: p.source_title || "",
      unsupported: unsupported(text, url ? full.split(url).join("") : full), style: [...styleCheck(full, url), ...fixes]});
  } catch (e) {
    const msg = {not_granted: "You didn't allow this page to use Claude, so it can't write drafts in this view.",
      rate_limited: "Claude is busy or you've hit a usage limit. Try again in a minute.",
      sampling_disabled: "Claude isn't available for this account.", session_expired: "Sign in to claude.ai again, then retry.",
      invalid_json: "Claude's answer came back in the wrong shape. Click Draft again.",
      refused: "Claude declined this text. Try a different article."}[e && e.code] || "Couldn't draft this time. Click Draft again.";
    return J({error: msg}, 400);
  }
}
function demoDraft(url) { const d = JSON.parse(JSON.stringify(DEMO.draft)); if (url) { d.text = d.text.replace(d.source_url, url); d.source_url = url; } return d; }
function styleCheck(text, url) {   // same rules as style.py
  const out = [], body = url ? text.split(url).join("") : text;
  const words = body.split(/\s+/).filter(Boolean).length;
  if (words > 220) out.push(`${words} words; your posts are usually under 200.`);
  if ((text.trim().split("\n")[0] || "").length > 120) out.push("The first line is long; your hooks are one short line.");
  if (body.includes("!")) out.push("Contains an exclamation mark; your posts don't use them.");
  for (const b of ["in today's world", "here's why", "let's dive", "game-changer", "game changer", "unlock the power", "excited to share", "thrilled to", "delve", "in conclusion"])
    if (body.toLowerCase().includes(b)) out.push(`Uses “${b}”, which doesn't sound like you.`);
  const bullets = text.split("\n").filter(l => /^\s*[•\-*]/.test(l));
  if (!bullets.length) out.push("No • bullets; you usually list the key points.");
  else if (bullets.some(l => !l.trim().startsWith("•"))) out.push("Use • for bullets, as in your posts.");
  if (url && !text.includes(url)) out.push("The link is missing.");
  const tail = text.trim().split("\n").slice(-2).join(" ").toLowerCase();
  if (!tail.includes("source") && !tail.includes("forrás")) out.push("End with the source (“Source: …” / “Forrás: …”) and the link.");
  if (/(^|[^\w&])#[\wÀ-ž]+/.test(text)) out.push("Contains hashtags.");
  if (/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(text)) out.push("Contains emojis.");
  return out;
}
window.fetch = async (url, opt = {}) => {
  const m = (opt.method || "GET").toUpperCase(), body = opt.body ? JSON.parse(opt.body) : {};
  await new Promise(r => setTimeout(r, url.includes("watch/draft") ? 600 : 80));
  tick();
  if (url === "/api/status") return J({demo: true, voice: DEMO.voice});
  if (url === "/api/article") return realDraft(body);
  if (url === "/api/style") return J({issues: styleCheck(body.text || "", body.url || "")});
  if (url === "/api/queue" && m === "GET") return J({posts: order(), linkedin: {connected: false, configured: false, test_mode: true}});
  if (url === "/api/queue" && m === "POST") {
    if (!body.text || !body.text.trim()) return J({error: "The post is empty"}, 400);
    if (body.text.length > 3000) return J({error: `LinkedIn allows 3000 characters; this post has ${body.text.length}`}, 400);
    if (body.scheduled_at && body.scheduled_at < new Date(Date.now() - 60000).toISOString()) return J({error: "That time is in the past"}, 400);
    let p = S.posts.find(x => x.id === body.id);
    if (p && ["posted", "posting"].includes(p.status)) return J({error: "This post was already published and can't be edited"}, 400);
    if (!p) { p = {id: S.nextId++, created_at: nowIso(), post_urn: null, test_mode: 0, error: null, note: null, posted_at: null}; S.posts.push(p); }
    Object.assign(p, {text: body.text, source_url: body.source_url || "", source_title: body.source_title || "",
      status: body.scheduled_at ? "scheduled" : "draft", scheduled_at: body.scheduled_at || null});
    if (body.post_now) Object.assign(p, {status: "posted", posted_at: nowIso(), test_mode: 1});
    return J(p);
  }
  let mm;
  if ((mm = url.match(/^\/api\/queue\/(\d+)$/)) && m === "DELETE") { S.posts = S.posts.filter(p => p.id !== +mm[1] || p.status === "posted"); return J({ok: true}); }
  if (url === "/api/watch") return J({config: S.cfg, ...sugg()});
  if (url === "/api/watch/config") { Object.assign(S.cfg, body); for (const k of ["keywords_en", "keywords_hu", "trusted_sources", "feeds", "feed_terms"]) S.cfg[k] = (S.cfg[k] || []).map(s => s.trim()).filter(Boolean); return J(S.cfg); }
  if (url === "/api/watch/run") { S.last = {at: nowIso(), found: 0, relevant: 0, drafted: 0, note: "demo"}; return J({found: 0, relevant: 0, drafted: 0, note: "Demo: the live news check runs in the app on your computer."}); }
  if (url === "/api/watch/dismiss") { const it = S.items.find(i => i.url === body.url); if (it) it.verdict = "dismissed"; return J(sugg()); }
  if (url === "/api/watch/draft") {
    return J({error: "In this demo: open the article, copy its text, then use the boxes on the left."}, 400);
    const it = S.items.find(i => i.url === body.url); const d = demoDraft(body.url);
    const p = {id: S.nextId++, created_at: nowIso(), text: d.text, source_url: body.url, source_title: it?.title || "", status: "draft",
      scheduled_at: null, posted_at: null, post_urn: null, test_mode: 0, error: null, note: "Found by the watcher. Review before scheduling. (Demo: sample text, not this article.)"};
    S.posts.push(p); if (it) Object.assign(it, {verdict: "drafted", post_id: p.id}); return J({ok: true, ...sugg()});
  }
  return J({error: "Not available in the demo"}, 404);
};
document.addEventListener("click", e => {
  const a = e.target.closest && e.target.closest('a[href="/auth/linkedin"]');
  if (a) { e.preventDefault(); e.stopPropagation(); a.closest(".card").querySelector(".hint").textContent = "In the real app this opens LinkedIn's login page. The demo stays in test mode."; }
}, true);
