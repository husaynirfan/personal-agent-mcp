from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
import uvicorn
import re

from playwright.async_api import async_playwright
import asyncio

mcp = FastMCP(name="XPostFetcher")

def extract_tweet_id(url: str) -> str:
    match = re.search(r"(?:twitter\.com|x\.com)/[^/]+/status/(\d+)", url)
    return match.group(1) if match else None

@mcp.tool()
async def get_x_post(url: str) -> str:
    tweet_id = extract_tweet_id(url)
    if not tweet_id:
        return "Invalid Twitter/X post URL."
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url)
        await page.wait_for_timeout(3000)

        try:
            text = await page.inner_text('article [data-testid="tweetText"]')
        except Exception:
            text = "Could not extract tweet content (DOM structure may have changed)."

        try:
            author = await page.inner_text('article a[role="link"][href*="/status/"] span')
        except Exception:
            author = "Unknown"

        try:
            created = await page.get_attribute('article time', 'datetime')
        except Exception:
            created = ""

        await browser.close()

    lines = [
        f"**{author}** at {created}:" if author else f"At {created}:",
        "",
        text.strip()
    ]
    return "\n".join([l for l in lines if l]).strip()

@mcp.tool()
async def search_user_tweets(username: str, query: str, max_results: int = 10) -> str:
    url = f"https://x.com/{username}"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url)
        await page.wait_for_timeout(5000)

        try:
            articles = await page.query_selector_all('article')
            tweets = []
            for art in articles[:max_results]:
                try:
                    text = await art.inner_text('[data-testid="tweetText"]')
                    time = await art.get_attribute('time', 'datetime')
                    if text:
                        tweets.append((text, time))
                except Exception:
                    continue
        except Exception:
            await browser.close()
            return f"Could not extract tweets for @{username} (DOM or structure error)."

        await browser.close()

    if not tweets:
        return f"No tweets found for @{username}."

    keywords = [q.strip().lower() for q in query.split(",") if q.strip()]
    relevant = [
        (text, time) for text, time in tweets
        if any(k in text.lower() for k in keywords)
    ]

    if not relevant:
        return f"No recent tweets from @{username} mentioning '{query}'."

    result = f"Recent tweets by @{username} about '{query}':\n\n"
    result += "\n\n".join(
        f"{time or ''}\n{text}" for text, time in relevant
    )
    return result

# --- FastAPI setup ---
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

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8004)
