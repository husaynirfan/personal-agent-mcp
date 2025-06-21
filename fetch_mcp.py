"""FetcherService MCP

A FastMCP micro‑service that downloads a web page and returns the main
article content in **Markdown** by default, making it ready for display
in chat/LLM answers.  Pass `as_markdown=False` if you need the raw HTML
instead.

CLI flags let you pick host/port and a log level (default *info*).
Set `--log-level debug` to see detailed fetch/extraction steps.

Dependencies (install with pip):
    fastmcp[base] readability-lxml markdownify requests uvicorn

Run with defaults (0.0.0.0:8000):
    python fetch_mcp.py

Override host/port or debug:
    python fetch_mcp.py --host 127.0.0.1 --port 8010 --log-level debug
"""
from __future__ import annotations

import argparse
import logging
from typing import Optional

import requests
import uvicorn
from fastmcp import FastMCP
from markdownify import markdownify as md
from readability import Document
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from bs4 import BeautifulSoup          # NEW
import re       

_LOG = logging.getLogger("fetch_mcp")

mcp = FastMCP(name="FetcherService")

# top of file – keep BeautifulSoup + re imports
# …

# ── inside _extract_telegram_post (replace the first GET section) ──────────
def _extract_telegram_post(url: str, as_markdown: bool, timeout: int) -> str:
    _LOG.info("Fetching Telegram post %s", url)

    # Always hit the embed endpoint (works for public posts)
    if "?embed=" not in url:
        url = url.rstrip("/") + "?embed=1&mode=tme"

    try:
        r = requests.get(url, timeout=timeout, headers={
            "User-Agent": "FetcherService/1.1 (+https://github.com/example/fetcher-mcp)"
        })
        r.raise_for_status()
    except Exception as exc:
        return f"Failed to download Telegram page: {exc}"

    soup = BeautifulSoup(r.text, "html.parser")
    article = soup.select_one(".tgme_widget_message")
    if not article:
        return "Could not locate Telegram post content (maybe private?)."

    # ---- improved extraction ----
    text_node = (
        article.select_one(".tgme_widget_message_text") or          # normal
        article.select_one(".tgme_widget_message_caption") or       # media caption
        article.select_one(".tgme_widget_message_poll")             # polls
    )
    if not text_node:
        return "Post has no textual content."

    html = str(text_node)
    return md(html, heading_style="ATX") if as_markdown else html


@mcp.tool
def fetch(url: str, as_markdown: bool = True, timeout: int = 15) -> str:
    """Fetch **url** and return its main content.

    Args:
        url: Full URL to download.
        as_markdown: When *True* (default) the response is a Markdown string
            extracted from the primary article on the page.  When *False*
            the raw HTML of the page is returned verbatim.
        timeout: Seconds before the HTTP request aborts (default 15).

    Raises:
        requests.HTTPError: if the server returns 4xx/5xx.
        requests.RequestException: for network‑level failures.
    """
    _LOG.info("Fetching %s", url)
    # --- Telegram fast-path -------------------------------------------------
    if re.match(r"https?://(t\.me|telegram\.me)/", url):
        return _extract_telegram_post(url, as_markdown, timeout)
    
    r = requests.get(
        url,
        timeout=timeout,
        headers={
            "User-Agent": (
                "FetcherService/1.0 (+https://github.com/example/fetcher-mcp)"
            )
        },
    )
    _LOG.debug("Received %s %s in %d bytes", r.status_code, r.reason, len(r.content))
    r.raise_for_status()

    html = r.text
    if not as_markdown:
        _LOG.debug("Returning raw HTML (%d chars)", len(html))
        return html

    try:
        doc = Document(html)
        article_html = doc.summary(html_partial=True)
        markdown = md(article_html, heading_style="ATX")
        _LOG.debug("Extracted markdown length %d chars", len(markdown))
        return markdown.strip()
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("Failed to extract article; returning raw HTML: %s", exc)
        return html  # fallback


# ---------------------------- FastAPI wrapper -----------------------------

middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )
]

app = mcp.http_app(middleware=middleware, path="/mcp/", stateless_http=True)


# ----------------------------- CLI launcher ------------------------------

def _parse_args(argv: Optional[list[str]] = None):
    parser = argparse.ArgumentParser(description="Run the FetcherService MCP")
    parser.add_argument("--host", default="0.0.0.0", help="Binding host")
    parser.add_argument("--port", type=int, default=8000, help="TCP port")
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["critical", "error", "warning", "info", "debug"],
        help="Log level for both this module and Uvicorn",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None):
    args = _parse_args(argv)

    # Configure root logger before anything else.
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    _LOG.info(
        "Starting Fetch MCP on %s:%d with log‑level %s",
        args.host,
        args.port,
        args.log_level,
    )

    uvicorn.run(
        app, host=args.host, port=args.port, log_level=args.log_level, workers=1
    )


if __name__ == "__main__":  # pragma: no cover
    main()
