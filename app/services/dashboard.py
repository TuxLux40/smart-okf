"""Static, read-only HTML dashboard: MD browser, git graph, config summary.

No server, no daemon — `render_dashboard()` returns one self-contained HTML string
(inline CSS/JS, no CDN dependencies) that `scripts/dashboard.py` writes to disk. Open
it locally, or serve the single file however you like (`python -m http.server`, a
static Caddy/nginx block, over Tailscale/LAN) — smart-okf itself never listens on a
socket. Config is displayed, never edited from here: writing config back through a
page is the line where this would become the webapp the project deliberately isn't.
"""

import html
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from app.config import SmartOkfConfig
from app.models.okf import OKFDocument

GIT_LOG_LIMIT = 200
"""Cap on rendered commits — a graph is for orientation, not a full-history browser."""

_HEADER_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
_LIST_ITEM_PATTERN = re.compile(r"^[-*]\s+(.*)$")
_SOURCE_LINE_PATTERN = re.compile(r"^_Source: (.+)_$")
_INLINE_PATTERNS = (
    (re.compile(r"\*\*(.+?)\*\*"), r"<strong>\1</strong>"),
    (re.compile(r"\[([^\]]+)\]\(([^)]+)\)"), r'<a href="\2">\1</a>'),
    (re.compile(r"(?<!\w)_(.+?)_(?!\w)"), r"<em>\1</em>"),
)
"""Bold before link before italic: `**[text](url)**` shouldn't have its `[`/`]`
eaten by the italic pattern first, and a link's own `_` (rare, but URLs can contain
one) shouldn't be read as emphasis."""


def _render_inline(text: str) -> str:
    """Escape first (safe against `<`/`&` in real content), then layer markdown spans
    on top — the patterns above only match literal `*`/`_`/`[`/`]`/`(`/`)`, none of
    which `html.escape` touches, so escaping first can't be undone by the substitutions."""
    rendered = html.escape(text)
    for pattern, replacement in _INLINE_PATTERNS:
        rendered = pattern.sub(replacement, rendered)
    return rendered


def render_markdown_html(markdown_text: str) -> str:
    """Minimal, dependency-free renderer for the markdown subset OKF bodies use.

    Not CommonMark — headers, unordered lists, paragraphs, bold/italic/links, and
    `_Source: x_` citation lines (rendered as their own small tag) are what the
    extraction prompts actually produce, and covering that is enough to turn a
    monospace text dump into something a person can actually read.
    """
    html_parts: list[str] = []
    paragraph_buffer: list[str] = []
    list_buffer: list[str] = []

    def flush_paragraph() -> None:
        if paragraph_buffer:
            html_parts.append(f"<p>{_render_inline(' '.join(paragraph_buffer))}</p>")
            paragraph_buffer.clear()

    def flush_list() -> None:
        if list_buffer:
            items = "".join(f"<li>{_render_inline(item)}</li>" for item in list_buffer)
            html_parts.append(f"<ul>{items}</ul>")
            list_buffer.clear()

    for line in markdown_text.splitlines():
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            flush_list()
            continue
        header_match = _HEADER_PATTERN.match(stripped)
        if header_match:
            flush_paragraph()
            flush_list()
            level = len(header_match.group(1))
            html_parts.append(f"<h{level}>{_render_inline(header_match.group(2))}</h{level}>")
            continue
        source_match = _SOURCE_LINE_PATTERN.match(stripped)
        if source_match:
            flush_paragraph()
            flush_list()
            html_parts.append(f'<p class="citation">Source: {html.escape(source_match.group(1))}</p>')
            continue
        list_match = _LIST_ITEM_PATTERN.match(stripped)
        if list_match:
            flush_paragraph()
            list_buffer.append(list_match.group(1))
            continue
        flush_list()
        paragraph_buffer.append(stripped)

    flush_paragraph()
    flush_list()
    return "\n".join(html_parts)


@dataclass
class MarkdownEntry:
    """One OKF markdown file found under the document root."""

    relative_path: str
    okf_type: str
    title: str
    description: str
    tags: list[str]
    sources: list[str]
    body: str
    raw_markdown: str


@dataclass
class DashboardData:
    """Everything `render_dashboard` needs, collected up front so rendering stays pure."""

    root: Path
    entries: list[MarkdownEntry] = field(default_factory=list)
    git_graph: str = ""
    config_summary: dict[str, str] = field(default_factory=dict)
    cron_lines: list[str] = field(default_factory=list)


def collect_markdown_entries(root: Path) -> list[MarkdownEntry]:
    """Every markdown file under root with parseable OKF frontmatter; hidden dirs excluded."""
    entries: list[MarkdownEntry] = []
    for path in sorted(root.rglob("*.md")):
        relative_parts = path.relative_to(root).parts
        if any(part.startswith(".") for part in relative_parts):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        document = OKFDocument.from_markdown(content)
        entries.append(
            MarkdownEntry(
                relative_path=str(path.relative_to(root)),
                okf_type=document.frontmatter.type,
                title=document.frontmatter.title or path.stem,
                description=document.frontmatter.description or "",
                tags=document.frontmatter.tags,
                sources=document.frontmatter.sources,
                body=document.body,
                raw_markdown=content,
            )
        )
    return entries


def git_log_graph(root: Path) -> str:
    """`git log --graph` for root, capped at `GIT_LOG_LIMIT` commits; a placeholder if unavailable."""
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "log",
                "--all",
                "--graph",
                "--decorate",
                "--oneline",
                "-n",
                str(GIT_LOG_LIMIT),
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"(git log unavailable: {error})"
    if result.returncode != 0:
        return "(not a git repository, or git log failed)"
    return result.stdout or "(no commits)"


def build_config_summary(config: SmartOkfConfig | None) -> dict[str, str]:
    """Human-readable snapshot of the resolved config — display only, never written back."""
    if config is None:
        return {"status": "no valid smart-okf.yaml found (and required env vars unset)"}
    return {
        "document_roots": ", ".join(str(p) for p in config.document_roots),
        "llm_model (extractor)": config.llm_model,
        "llm_host (extractor)": config.llm_host,
        "dream_model": config.dream_model or f"{config.llm_model} (falls back to llm_model)",
        "dream_host": config.dream_host or f"{config.llm_host} (falls back to llm_host)",
        "vision_model": config.vision_model or "(not set — tesseract-only OCR for images)",
        "use_marker": str(config.use_marker),
        "allow_remote_llm": str(config.allow_remote_llm),
    }


def collect_cron_lines() -> list[str]:
    """Best-effort: current user's crontab lines that reference this project's scripts."""
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    markers = ("ingest_folder.py", "dream.py", "validate_okf.py")
    return [line for line in result.stdout.splitlines() if any(marker in line for marker in markers)]


def collect_dashboard_data(root: Path, config: SmartOkfConfig | None) -> DashboardData:
    """Gather everything the dashboard needs; no I/O happens during rendering."""
    return DashboardData(
        root=root,
        entries=collect_markdown_entries(root),
        git_graph=git_log_graph(root),
        config_summary=build_config_summary(config),
        cron_lines=collect_cron_lines(),
    )


def _render_config_section(data: DashboardData) -> str:
    rows = "\n".join(
        f"<tr><th>{html.escape(key)}</th><td>{html.escape(value)}</td></tr>"
        for key, value in data.config_summary.items()
    )
    cron_html = (
        "<pre>" + html.escape("\n".join(data.cron_lines)) + "</pre>"
        if data.cron_lines
        else "<p class='muted'>No crontab lines reference ingest_folder.py / dream.py / validate_okf.py.</p>"
    )
    return f"""
    <section id="config">
      <h2>Config</h2>
      <table>{rows}</table>
      <h3>Cron entries</h3>
      {cron_html}
    </section>
    """


def _render_git_section(data: DashboardData) -> str:
    # `git log --graph` text is the graph — no drawing library needed for the default
    # render. The raw commit lines are also embedded as JSON (id="git-graph-data") so
    # a user who installs a real graph library later (gitgraph.js, d3, Mermaid's
    # `gitGraph` directive, ...) has structured data to hand it, without smart-okf
    # depending on that library itself. See `renderGitGraphAdvanced()` in the page's
    # own script for the extension point — it's a no-op today.
    commit_lines = [line for line in data.git_graph.splitlines() if line.strip()]
    commit_json = json.dumps(commit_lines)
    return f"""
    <section id="git">
      <h2>Git history</h2>
      <pre class="git-graph" id="git-graph-text">{html.escape(data.git_graph)}</pre>
      <script type="application/json" id="git-graph-data">{commit_json}</script>
    </section>
    """


def _render_markdown_entry(entry: MarkdownEntry) -> str:
    meta_bits = []
    if entry.tags:
        meta_bits.append(f"<strong>Tags:</strong> {html.escape(', '.join(entry.tags))}")
    if entry.sources:
        meta_bits.append(f"<strong>Sources:</strong> {len(entry.sources)}")
    meta_html = f'<p class="meta">{" · ".join(meta_bits)}</p>' if meta_bits else ""
    return f"""<details>
      <summary>
        <span class="type">{html.escape(entry.okf_type)}</span>
        <span class="title">{html.escape(entry.title)}</span>
        <span class="path">{html.escape(entry.relative_path)}</span>
      </summary>
      <p class="description">{html.escape(entry.description)}</p>
      {meta_html}
      <div class="rendered-body">{render_markdown_html(entry.body)}</div>
      <details class="raw-toggle">
        <summary>Raw markdown</summary>
        <pre>{html.escape(entry.raw_markdown)}</pre>
      </details>
    </details>"""


def _render_markdown_section(data: DashboardData) -> str:
    if not data.entries:
        items = "<p class='muted'>No OKF markdown files found under this root.</p>"
    else:
        items = "\n".join(_render_markdown_entry(entry) for entry in data.entries)
    return f"""
    <section id="markdown">
      <h2>Markdown browser ({len(data.entries)} files)</h2>
      <input type="text" id="search" placeholder="Filter by type, title, or path..." autocomplete="off">
      <div id="entries">{items}</div>
    </section>
    """


_STYLE = """
:root { color-scheme: light dark; }
body { font-family: system-ui, sans-serif; max-width: 60rem; margin: 2rem auto; padding: 0 1rem;
       line-height: 1.5; }
h1 { font-size: 1.4rem; }
h2 { font-size: 1.15rem; border-bottom: 1px solid currentColor; padding-bottom: 0.25rem; }
section { margin-bottom: 2.5rem; }
table { border-collapse: collapse; }
th, td { text-align: left; padding: 0.2rem 0.8rem 0.2rem 0; vertical-align: top; }
th { opacity: 0.7; font-weight: 600; white-space: nowrap; }
pre { white-space: pre-wrap; word-break: break-word; background: rgba(127, 127, 127, 0.12);
      border-radius: 6px; padding: 0.75rem; overflow-x: auto; }
.git-graph { font-size: 0.85em; }
details { border: 1px solid rgba(127, 127, 127, 0.3); border-radius: 6px; margin-bottom: 0.4rem;
          padding: 0.4rem 0.6rem; }
summary { cursor: pointer; display: flex; gap: 0.6rem; align-items: baseline; flex-wrap: wrap; }
summary .type { opacity: 0.6; font-size: 0.85em; text-transform: uppercase; letter-spacing: 0.03em; }
summary .title { font-weight: 600; }
summary .path { opacity: 0.6; font-size: 0.85em; }
.description { opacity: 0.85; margin: 0.4rem 0; }
.meta { opacity: 0.7; font-size: 0.9em; margin: 0.2rem 0 0.8rem; }
.muted { opacity: 0.6; font-style: italic; }
#search { width: 100%; padding: 0.5rem; margin-bottom: 0.8rem; font-size: 1em; box-sizing: border-box; }
.rendered-body { margin-top: 0.6rem; }
.rendered-body h1, .rendered-body h2, .rendered-body h3,
.rendered-body h4, .rendered-body h5, .rendered-body h6 {
  margin: 0.9rem 0 0.3rem; font-size: 1em; opacity: 0.9;
}
.rendered-body p { margin: 0.5rem 0; }
.rendered-body ul { margin: 0.3rem 0; padding-left: 1.4rem; }
.rendered-body li { margin: 0.15rem 0; }
.rendered-body .citation { opacity: 0.55; font-size: 0.85em; font-style: italic; margin: 0.2rem 0 0.6rem; }
.raw-toggle { border: none; padding: 0; margin-top: 0.6rem; }
.raw-toggle summary { opacity: 0.6; font-size: 0.85em; }
.raw-toggle pre { margin-top: 0.4rem; }
"""

_SCRIPT = """
document.getElementById('search').addEventListener('input', (event) => {
  const query = event.target.value.toLowerCase();
  document.querySelectorAll('#entries details').forEach((node) => {
    node.style.display = node.textContent.toLowerCase().includes(query) ? '' : 'none';
  });
});

// Extension point, not wired to anything by default: the raw commit lines are
// available as JSON in #git-graph-data (one string per line of `git log --graph`
// output) if you install a real graph-drawing library and want a nicer render than
// the plain-text #git-graph-text this page ships with. smart-okf deliberately adds
// no JS dependency itself (no CDN, no bundler) — this function is a no-op unless
// you fill it in yourself.
function renderGitGraphAdvanced() {
  const lines = JSON.parse(document.getElementById('git-graph-data').textContent);
  // e.g.: new GitGraph(...).parse(lines) or feed a Mermaid `gitGraph` block.
  return lines;
}
"""


def render_dashboard(data: DashboardData) -> str:
    """Render a self-contained HTML page from already-collected dashboard data."""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>smart-okf dashboard — {html.escape(str(data.root))}</title>
<style>{_STYLE}</style>
</head>
<body>
<h1>smart-okf dashboard</h1>
<p class="muted">{html.escape(str(data.root))} — read-only, static, regenerate with <code>scripts/dashboard.py</code></p>
{_render_config_section(data)}
{_render_git_section(data)}
{_render_markdown_section(data)}
<script>{_SCRIPT}</script>
</body>
</html>
"""
