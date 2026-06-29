# Web Gecko

> Pluck what you need. Climb through the web.

[![Tests](https://github.com/jayelbotvibe-web/webgecko/actions/workflows/test.yml/badge.svg)](https://github.com/jayelbotvibe-web/webgecko/actions/workflows/test.yml)
[![PyPI](https://img.shields.io/pypi/v/webgecko)](https://pypi.org/project/webgecko/)
[![Python](https://img.shields.io/pypi/pyversions/webgecko)](https://pypi.org/project/webgecko/)
[![License](https://img.shields.io/github/license/jayelbotvibe-web/webgecko)](https://github.com/jayelbotvibe-web/webgecko/blob/master/LICENSE)

**Web Gecko** is a point-solution library — stealthy HTTP + HTML parsing for when you need to scrape a site that blocks plain `curl` or `requests` but doesn't require JavaScript. Built for AI agents that want structured data without writing parsing loops.

**What it does:** TLS impersonation, CSS/XPath with pseudo-elements, markdown conversion, structured extraction, concurrent crawling.

**What it doesn't:** Browser automation, JavaScript rendering, proxy rotation, CAPTCHA solving. This is a library, not a scraping framework.

```python
from gecko import fetch

r = fetch("https://httpbin.org/html", impersonate="chrome131")
print(r.page.title)
print(r.page.markdown[:200])
```

## Install

```bash
pip install webgecko
```

Python 3.10+. Depends on `lxml`, `cssselect`, `curl_cffi`, `anyio`.

## API

### Fetch

```python
from gecko import fetch, Session, AsyncSession

r = fetch("https://example.com", impersonate="chrome131")
r.status          # 200
r.page            # parsed Page (HTML) or placeholder (JSON)
r.json            # parsed JSON body, or None
r.headers         # case-insensitive dict

with Session(impersonate="firefox124") as s:
    r = s.get("https://example.com")

async with AsyncSession() as s:
    r = await s.get("https://example.com")
```

### Parse

```python
from gecko import Page

page = Page("<html>...</html>")

# Queries return Elements (iterable, indexable, .get() for first)
page.css(".title")                 # Elements
page.xpath("//h2")                 # Elements
page.find("Hello")                 # exact text
page.find("Hel", partial=True)     # substring
page.find_all("div", class_="foo") # by tag + attrs

# Pseudo-elements — extract strings directly
page.css(".title::text").get()     # "Widget A"
page.css("a::attr(href)").get()    # "/buy/a"

# Element properties
el = page.css(".product")[0]
el.text            # text content
el.tag             # "div"
el.html            # inner HTML
el.attr("href")    # attribute value
```

### Agent-friendly shortcuts

```python
page.title         # "My Page" — <title> text
page.markdown      # full page as markdown
page.links()       # [{"text": "Link A", "href": "/a"}, ...]
page.jsonld()      # [{"@type": "WebSite", ...}] — JSON-LD data
```

### Extract (agent-friendly structured output)

```python
# Map CSS selectors → field names. One call per group of elements.
page.css(".product").extract({
    "name": ".title::text",
    "price": ".price::text",
    "link": "a::attr(href)",
})
# → [{"name": "Widget A", "price": "$9.99", "link": "/buy/a"}, ...]

# first=True returns a single dict or None
page.css("h1").extract({"title": "::text"}, first=True)
# → {"title": "Welcome"}
```

### Gecko

```python
class QuotesGecko(Gecko):
    start_urls = ["https://quotes.toscrape.com/"]
    concurrency = 4

    def parse(self, response: Response):
        yield from response.page.css(".quote").extract({
            "text": ".text::text",
            "author": ".author::text",
        })
        next_link = response.page.css(".next a::attr(href)").get()
        if next_link:
            yield response.follow(next_link, callback=self.parse)

result = QuotesGecko().run()  # 100 quotes, 10 pages, ~3s
result.save("quotes.json")
```

## License

MIT
