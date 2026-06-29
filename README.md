# Web Gecko

> Pluck what you need. Climb through the web.

```python
from gecko import fetch, Session, Gecko, Response

r = fetch("https://httpbin.org/html", impersonate="chrome131")
print(r.page.css("h1::text").get())

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

# List comprehensions for bulk extraction
[e.text for e in page.css(".title")]
[e.attr("id") for e in page.css(".product")]
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
class MyGecko(Gecko):
    start_urls = ["https://example.com"]
    concurrency = 4
    download_delay = 0.5
    max_pages = 100

    def parse(self, response: Response):
        yield from response.page.css("a").extract({
            "url": "::attr(href)",
            "text": "::text",
        })
        next_page = response.page.css(".next a::attr(href)").get()
        if next_page:
            yield response.follow(next_page, callback=self.parse)

gecko = MyGecko().run()
gecko.items          # list[dict]
gecko.save("out.json")
gecko.save_jsonl("out.jsonl")
```

## License

MIT
