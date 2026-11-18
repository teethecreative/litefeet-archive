"""Classify public-site traffic without discarding automated requests.

This is best-effort user-agent classification, not proof of a human identity.
Old analytics records remain 'unclassified' because their agents weren't saved.
"""

BOT_AGENTS = (
    ("meta-externalagent", "Meta ExternalAgent"),
    ("meta-webindexer", "Meta WebIndexer"),
    ("meta-externalfetcher", "Meta ExternalFetcher"),
    ("meta-externalads", "Meta ExternalAds"),
    ("facebookexternalhit", "Meta link preview"),
    ("googlebot", "Googlebot"),
    ("bingbot", "Bingbot"),
    ("duckduckbot", "DuckDuckBot"),
    ("gptbot", "OpenAI GPTBot"),
    ("chatgpt-user", "ChatGPT-User"),
    ("oai-searchbot", "OpenAI SearchBot"),
    ("claudebot", "ClaudeBot"),
    ("claude-user", "Claude-User"),
    ("claude-searchbot", "Claude SearchBot"),
    ("perplexitybot", "PerplexityBot"),
    ("bytespider", "Bytespider"),
    ("ahrefsbot", "AhrefsBot"),
    ("semrushbot", "SemrushBot"),
    ("applebot", "Applebot"),
    ("ccbot", "Common Crawl"),
    ("yandexbot", "YandexBot"),
    ("slurp", "Yahoo crawler"),
    ("linkedinbot", "LinkedInBot"),
    ("pinterestbot", "Pinterestbot"),
    ("twitterbot", "Twitterbot"),
    ("discordbot", "Discordbot"),
    ("telegrambot", "Telegrambot"),
)

OTHER_AUTOMATION = (
    "bot/", "crawler", "spider", "scraper", "fetcher",
    "headless", "python-requests", "python-urllib",
    "curl/", "wget/", "go-http-client", "node-fetch",
    "axios/", "postmanruntime", "selenium", "playwright",
    "puppeteer", "httpclient", "httpx/", "libwww",
)


def classify_traffic(user_agent, *, is_admin=False):
    """Return (kind, source): human, bot, internal or unclassified.

    'human' means likely browser traffic, never verified human identity.
    User-Agent can be spoofed, so reported human traffic is an estimate.
    """
    if is_admin:
        return "internal", "Authenticated admin"

    agent = (user_agent or "").casefold().strip()
    if not agent:
        return "unclassified", "Missing user agent"

    for token, label in BOT_AGENTS:
        if token in agent:
            return "bot", label

    if any(token in agent for token in OTHER_AUTOMATION):
        return "bot", "Other automated"

    return "human", "Likely human browser"
