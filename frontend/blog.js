/* File-based blog. Reads posts/index.json (list of articles) and renders either
 * the list or a single article (posts/<slug>.md). To publish a new article: add
 * a markdown file in frontend/posts/ and an entry to posts/index.json. */

const el = document.getElementById("blog");

function esc(s) { return String(s ?? "").replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }

/* Tiny, safe Markdown renderer: headings, bold/italic, links, lists, paragraphs. */
function md2html(md) {
  const lines = md.replace(/\r/g, "").split("\n");
  let html = "", inList = false;
  const inline = (t) => esc(t)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/(?<!\*)\*(?!\*)(.+?)\*(?!\*)/g, "<em>$1</em>")
    .replace(/\[(.+?)\]\((https?:\/\/[^\s)]+)\)/g, '<a class="link" href="$2" target="_blank" rel="noopener">$1</a>');
  const closeList = () => { if (inList) { html += "</ul>"; inList = false; } };
  for (const raw of lines) {
    const line = raw.trimEnd();
    let m;
    if ((m = line.match(/^(#{1,4})\s+(.*)$/))) { closeList(); const lvl = m[1].length; html += `<h${lvl}>${inline(m[2])}</h${lvl}>`; }
    else if ((m = line.match(/^[-*]\s+(.*)$/))) { if (!inList) { html += "<ul>"; inList = true; } html += `<li>${inline(m[1])}</li>`; }
    else if (line.trim() === "") { closeList(); }
    else { closeList(); html += `<p>${inline(line)}</p>`; }
  }
  closeList();
  return html;
}

async function render() {
  const slug = new URLSearchParams(location.search).get("post");
  let index = [];
  try {
    index = await (await fetch("posts/index.json", { cache: "no-cache" })).json();
  } catch (e) { index = []; }

  if (slug) {
    const meta = index.find(p => p.slug === slug);
    let md = "";
    try { md = await (await fetch(`posts/${slug}.md`, { cache: "no-cache" })).text(); }
    catch (e) { md = "# Not found\n\nThat article could not be loaded."; }
    el.innerHTML = `
      <p><a class="link" href="blog.html">← All articles</a></p>
      <div class="card">
        ${meta ? `<p class="muted-note">${esc(meta.date || "")}</p>` : ""}
        <div class="md" style="max-height:none;border:none;background:transparent;padding:0;white-space:normal;">${md2html(md)}</div>
      </div>`;
    return;
  }

  const items = index.length ? index.map(p => `
    <a class="feature" href="blog.html?post=${encodeURIComponent(p.slug)}" style="display:block;">
      <div class="f-title">${esc(p.title)}</div>
      <div class="muted-note" style="margin-top:2px;">${esc(p.date || "")}</div>
      <div class="f-desc" style="margin-top:8px;">${esc(p.summary || "")}</div>
    </a>`).join("") : `<p class="sub">No articles yet — check back soon.</p>`;

  el.innerHTML = `
    <div class="card">
      <h1>Blog</h1>
      <p class="sub">Guides on statistics, research methods, and writing up results.</p>
    </div>
    <div class="feature-grid" style="grid-template-columns:1fr;">${items}</div>`;
}

render();
