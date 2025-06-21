# news_mcp.py

from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
import uvicorn
import feedparser
import random
import re

# --- User-Agent Configuration ---
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

# --- RSS Feed Configuration ---
# Please remember to add your custom feeds (like 'stand4muslim') back to this list!
RSS_FEEDS = {
    "presstv": "https://www.presstv.ir/rss/rss-101.xml",
    "stand4muslim" : "https://rss.app/feeds/OPQ5Kaawp7JE7wmC.xml",
}

# Create the MCP server instance
mcp = FastMCP(name="NewsFetcherService")

@mcp.tool()
def get_latest_news(source: str = "all", limit: int = 5) -> str:
    """
    Fetch latest headlines.

    `source` rules
    --------------
    • "presstv"            → presstv only  
    • "presstv,stand4muslim" or "presstv stand4muslim"
                           → those two only  
    • anything else ("all", "", unknown) → all feeds
    """
    # --- normalise user input -------------------------------------------
    wanted = [
        s.strip().lower() for s in re.split(r"[,\s]+", source) if s.strip()
    ]
    if not wanted or wanted == ["all"]:
        feeds_to_fetch = RSS_FEEDS
    else:
        feeds_to_fetch = {
            k: v for k, v in RSS_FEEDS.items() if k.lower() in wanted
        }
        if not feeds_to_fetch:   # no match -> fall back to all
            feeds_to_fetch = RSS_FEEDS

    all_headlines = []
    _LOG = print                         # or logging, if you prefer
    _LOG(f"Fetching news from: {', '.join(feeds_to_fetch.keys())}")

    for key, url in feeds_to_fetch.items():
        try:
            feed = feedparser.parse(url, agent=USER_AGENT)

            if feed.bozo:
                msg = str(feed.get("bozo_exception", "")).lower()
                if any(s in msg for s in ("mismatch", "encoding", "declared as")):
                    _LOG(f"Non-fatal encoding issue on {key}, continuing.")
                else:
                    _LOG(f"Skipping malformed feed {key}: {msg}")
                    continue

            for entry in feed.entries:
                if "title" in entry and "link" in entry:
                    all_headlines.append(
                        {"source": key.upper(), "title": entry.title, "link": entry.link}
                    )
        except Exception as e:
            _LOG(f"Could not fetch {key}: {e}")

    if not all_headlines:
        return (
            "Sorry, I couldn’t fetch any news for the requested source(s): "
            f"{', '.join(wanted) or 'all'}."
        )

    random.shuffle(all_headlines)
    limited = all_headlines[: limit]

    out = ["Here are the latest headlines:"]
    out += [f"- [{h['source']}] {h['title']}\n  Link: {h['link']}" for h in limited]
    return "\n".join(out)



# --- Server Setup ---
middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["Content-Type", "Accept"]
    )
]
app = mcp.http_app(middleware=middleware, path="/mcp/", stateless_http=True)


if __name__ == "__main__":
    print("Starting News Fetcher MCP on port 8003...")
    uvicorn.run(app, host="0.0.0.0", port=8003)