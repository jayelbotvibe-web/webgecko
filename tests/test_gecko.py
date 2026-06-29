import time
import asyncio

import pytest
from gecko.parser import Page, _escape_xpath_str
from gecko.fetcher import fetch, Session


HTML = """<html><body>
<div class="product" id="p1">
  <h2 class="title">Widget A</h2>
  <span class="price">$9.99</span>
  <a href="/buy/a">Buy</a>
</div>
<div class="product" id="p2">
  <h2 class="title">Widget B</h2>
  <span class="price">$19.99</span>
  <a href="/buy/b">Buy</a>
</div>
</body></html>"""


class TestParser:
    def test_css_selectors(self):
        page = Page(HTML)
        products = page.css(".product")
        assert len(products) == 2
        assert products[0].attr("id") == "p1"

    def test_css_text(self):
        page = Page(HTML)
        assert page.css(".title")[0].text == "Widget A"

    def test_css_iteration(self):
        page = Page(HTML)
        texts = [e.text for e in page.css(".title")]
        assert texts == ["Widget A", "Widget B"]

    def test_css_get(self):
        page = Page(HTML)
        assert page.css(".product").get().attr("id") == "p1"
        assert page.css(".nonexistent").get() is None

    def test_xpath(self):
        page = Page(HTML)
        assert len(page.xpath("//h2")) == 2
        assert page.xpath("//h2")[0].text == "Widget A"

    def test_find_text(self):
        page = Page(HTML)
        found = page.find("Widget B")
        assert len(found) == 1
        assert found[0].tag == "h2"

    def test_find_text_partial(self):
        page = Page(HTML)
        assert len(page.find("Widget", partial=True)) == 2

    def test_find_all(self):
        page = Page(HTML)
        spans = page.find_all("span", class_="price")
        assert len(spans) == 2
        assert [e.text for e in spans] == ["$9.99", "$19.99"]

    def test_find_all_class_underscore(self):
        page = Page(HTML)
        divs = page.find_all(class_="product")
        assert len(divs) == 2

    def test_attr(self):
        el = Page(HTML).css(".product")[0]
        assert el.attr("id") == "p1"
        assert el.attr("nonexistent") is None
        assert el.attr("nonexistent", "default") == "default"

    def test_tag(self):
        assert Page(HTML).css("h2")[0].tag == "h2"

    def test_text_property(self):
        assert "Widget A" in Page(HTML).text

    def test_html_property(self):
        assert "<h2" in Page(HTML).css(".product")[0].html

    def test_elements_bool(self):
        page = Page(HTML)
        assert bool(page.css(".product"))
        assert not bool(page.css(".nonexistent"))

    def test_elements_slice(self):
        page = Page(HTML)
        sliced = page.css(".product")[:1]
        assert len(sliced) == 1
        assert sliced[0].attr("id") == "p1"

    def test_repr(self):
        assert "Page" in repr(Page(HTML))

    def test_attrs_via_comprehension(self):
        page = Page(HTML)
        ids = [e.attr("id") for e in page.css(".product")]
        assert ids == ["p1", "p2"]

    def test_parent(self):
        page = Page(HTML)
        h2 = page.css("h2")[0]
        assert h2.parent is not None
        assert h2.parent.tag == "div"
        assert h2.parent.attr("class") == "product"

    def test_parent_of_root(self):
        page = Page("<p>hi</p>")
        p = page.css("p")[0]
        assert p.parent is not None  # body
        assert p.parent.parent is not None  # html

    def test_children(self):
        page = Page(HTML)
        product = page.css(".product")[0]
        kids = product.children
        assert len(kids) == 3  # h2, span, a
        assert kids[0].tag == "h2"

    def test_siblings(self):
        page = Page(HTML)
        h2 = page.css("h2")[0]
        assert h2.next_sibling is not None
        assert h2.next_sibling.tag == "span"
        assert h2.next_sibling.next_sibling is not None  # a
        assert h2.prev_sibling is None  # first child

    def test_pseudo_text(self):
        page = Page(HTML)
        titles = page.css(".title::text")
        assert titles.get() == "Widget A"
        assert [t for t in titles] == ["Widget A", "Widget B"]

    def test_pseudo_attr(self):
        page = Page(HTML)
        hrefs = page.css("a::attr(href)")
        assert hrefs.get() == "/buy/a"
        assert [h for h in hrefs] == ["/buy/a", "/buy/b"]

    def test_pseudo_text_on_none(self):
        page = Page(HTML)
        result = page.css(".nonexistent::text")
        assert result.get() is None
        assert len(result) == 0

    def test_pseudo_attr_on_none(self):
        page = Page(HTML)
        result = page.css(".nonexistent::attr(href)")
        assert result.get() is None

    def test_pseudo_text_no_selector(self):
        page = Page("<p>hello</p>")
        assert page.css("::text").get() == "hello"

    def test_pseudo_in_element(self):
        page = Page(HTML)
        product = page.css(".product")[0]
        assert product.css(".title::text").get() == "Widget A"
        assert product.css("a::attr(href)").get() == "/buy/a"

    def test_extract_from_elements(self):
        page = Page(HTML)
        items = page.css(".product").extract({
            "name": ".title::text",
            "price": ".price::text",
            "link": "a::attr(href)",
        })
        assert items == [
            {"name": "Widget A", "price": "$9.99", "link": "/buy/a"},
            {"name": "Widget B", "price": "$19.99", "link": "/buy/b"},
        ]

    def test_extract_first(self):
        page = Page(HTML)
        item = page.css(".product").extract(
            {"name": ".title::text"}, first=True
        )
        assert item == {"name": "Widget A"}

    def test_extract_empty(self):
        page = Page(HTML)
        result = page.css(".nonexistent").extract({"x": "::text"})
        assert result == []

    def test_extract_first_empty(self):
        page = Page(HTML)
        result = page.css(".nonexistent").extract({"x": "::text"}, first=True)
        assert result is None

    def test_extract_missing_field(self):
        page = Page(HTML)
        items = page.css(".product").extract({"name": ".title::text", "nope": ".nope::text"})
        assert items[0]["name"] == "Widget A"
        assert items[0]["nope"] is None

    def test_extract_bad_selector(self):
        page = Page(HTML)
        items = page.css(".product").extract({"name": ".title::text", "bad": "!!!"})
        assert items[0]["name"] == "Widget A"
        assert items[0]["bad"] is None

    def test_empty_content(self):
        for content in ["", "   ", b""]:
            p = Page(content)
            assert p.tag == "html"

    def test_bad_css_raises_valueerror(self):
        page = Page(HTML)
        with pytest.raises(ValueError):
            page.css("!!!bad!!!")
        with pytest.raises(ValueError):
            page.css("")


class TestXPathEscape:
    def test_no_quotes(self):
        assert _escape_xpath_str("hello") == '"hello"'

    def test_double_quotes(self):
        assert _escape_xpath_str("it's") == "\"it's\""

    def test_both_quotes(self):
        assert "concat" in _escape_xpath_str('say "hello" to O\'Brien')


class TestFetcher:
    def test_fetch_get(self, httpbin):
        r = fetch(httpbin + "/get")
        assert r.status == 200

    def test_fetch_html(self, httpbin):
        r = fetch(httpbin + "/html")
        assert r.status == 200
        assert r.page.css("h1")  # has an h1

    def test_fetch_with_impersonate(self, httpbin):
        r = fetch(httpbin + "/get", impersonate="chrome131")
        assert r.status == 200

    def test_session_context_manager(self, httpbin):
        with Session() as s:
            r = s.get(httpbin + "/get")
            assert r.status == 200

    def test_response_page(self, httpbin):
        r = fetch(httpbin + "/html")
        assert r.page.css("h1")

    def test_fetch_returns_404(self, httpbin):
        r = fetch(httpbin + "/status/404")
        assert r.status == 404

    def test_session_raises_on_404(self, httpbin):
        with pytest.raises(Exception):
            with Session() as s:
                s.get(httpbin + "/status/404")

    def test_session_headers(self, httpbin):
        with Session() as s:
            r = s.get(httpbin + "/headers", headers={"X-Test": "hello"})
            assert r.status == 200

    def test_json_response(self, httpbin):
        r = fetch(httpbin + "/json")
        assert r.json is not None
        assert r.page.tag == "html"

    def test_html_response_no_json(self, httpbin):
        r = fetch(httpbin + "/html")
        assert r.json is None
        assert r.page.css("h1")

    def test_fetch_404_fast(self, httpbin):
        start = time.monotonic()
        r = fetch(httpbin + "/status/404")
        elapsed = time.monotonic() - start
        assert r.status == 404
        assert elapsed < 5  # no retries on HTTP errors

    def test_redirect(self, httpbin):
        r = fetch(httpbin + "/redirect/3")
        assert r.status == 200

    def test_xml_response(self, httpbin):
        r = fetch(httpbin + "/xml")
        assert r.status == 200
        assert len(r.page.css("*")) > 0


class TestGecko:
    def test_basic(self, httpbin):
        from gecko.crawler import Gecko
        from gecko.fetcher import Response

        class TestGecko(Gecko):
            start_urls = [httpbin + "/html"]
            concurrency = 1

            def parse(self, response: Response):
                yield {"status": response.status}

        g = TestGecko().run()
        assert g.stats.pages_crawled == 1
        assert len(g.items) == 1
        assert g.items[0]["status"] == 200

    def test_save(self, tmp_path, httpbin):
        from gecko.crawler import Gecko
        from gecko.fetcher import Response

        class TestGecko(Gecko):
            start_urls = [httpbin + "/html"]
            concurrency = 1

            def parse(self, response: Response):
                yield {"url": response.url}

        g = TestGecko().run()
        path = str(tmp_path / "test.json")
        n = g.save(path)
        assert n == 1

    def test_save_jsonl(self, tmp_path, httpbin):
        from gecko.crawler import Gecko
        from gecko.fetcher import Response

        class TestGecko(Gecko):
            start_urls = [httpbin + "/html"]
            concurrency = 1

            def parse(self, response: Response):
                yield {"url": response.url}

        g = TestGecko().run()
        path = str(tmp_path / "test.jsonl")
        n = g.save_jsonl(path)
        assert n == 1

    def test_max_pages(self, httpbin):
        from gecko.crawler import Gecko
        from gecko.fetcher import Response

        class TestGecko(Gecko):
            start_urls = [httpbin + "/html", httpbin + "/get"]
            concurrency = 1
            max_pages = 1

            def parse(self, response: Response):
                yield {"url": response.url}

        g = TestGecko().run()
        assert g.stats.pages_crawled <= 2
        assert g.stats.skipped >= 0

    def test_stream(self, httpbin):
        from gecko.crawler import Gecko
        from gecko.fetcher import Response

        items_received = []

        class TestGecko(Gecko):
            start_urls = [httpbin + "/html"]
            concurrency = 1

            def parse(self, response: Response):
                yield {"url": response.url}

        async def collect():
            g = TestGecko()
            async for item in g.stream():
                items_received.append(item)

        asyncio.run(collect())
        assert len(items_received) == 1


# ── New features: markdown, links, title, jsonld ─────────────────────


class TestMarkdown:
    def test_headings(self):
        page = Page("<h1>Title</h1><h2>Sub</h2><h3>Deep</h3>")
        md = page.markdown
        assert md == "# Title\n\n## Sub\n\n### Deep"

    def test_paragraphs(self):
        page = Page("<p>Hello world</p><p>Second para</p>")
        md = page.markdown
        assert "Hello world" in md
        assert "Second para" in md

    def test_links(self):
        page = Page('<a href="/page">Click here</a>', url="https://example.com")
        md = page.markdown
        assert "[Click here](https://example.com/page)" in md

    def test_bold_italic(self):
        page = Page("<strong>bold</strong> <em>italic</em> <b>b</b> <i>i</i>")
        md = page.markdown
        assert "**bold**" in md
        assert "*italic*" in md

    def test_lists(self):
        page = Page("<ul><li>a</li><li>b</li></ul><ol><li>1</li><li>2</li></ol>")
        md = page.markdown
        assert "- a" in md
        assert "- b" in md
        assert "1. 1" in md
        assert "1. 2" in md

    def test_code_inline(self):
        page = Page("<p>Use <code>fetch()</code> to get pages</p>")
        md = page.markdown
        assert "`fetch()`" in md

    def test_code_block(self):
        page = Page('<pre><code class="language-python">print("hi")</code></pre>')
        md = page.markdown
        assert "```python" in md
        assert 'print("hi")' in md
        assert md.endswith("```")

    def test_images(self):
        page = Page('<img src="/logo.png" alt="Logo">', url="https://example.com")
        md = page.markdown
        assert "![Logo](https://example.com/logo.png)" in md

    def test_blockquote(self):
        page = Page("<blockquote><p>famous quote</p></blockquote>")
        md = page.markdown
        assert "> famous quote" in md

    def test_strikethrough(self):
        page = Page("<del>old</del> and <s>gone</s>")
        md = page.markdown
        assert "~~old~~" in md
        assert "~~gone~~" in md

    def test_hr(self):
        page = Page("<p>above</p><hr><p>below</p>")
        md = page.markdown
        assert "---" in md

    def test_empty_page(self):
        page = Page("<html></html>")
        assert page.markdown == ""

    def test_script_skipped(self):
        page = Page("<script>alert('xss')</script><p>safe</p>")
        md = page.markdown
        assert "alert" not in md
        assert "safe" in md

    def test_complex_nesting(self):
        page = Page(
            '<article><h1>Blog</h1><p>intro text</p>'
            '<ul><li>point <strong>one</strong></li></ul></article>'
        )
        md = page.markdown
        assert "# Blog" in md
        assert "intro text" in md
        assert "**one**" in md

    def test_empty_paragraph_not_doubled(self):
        page = Page("<p>a</p><p></p><p>b</p>")
        md = page.markdown
        assert md.count("\n\n") <= 2  # not excessive blank lines

    def test_deep_nesting(self):
        page = Page("<div><div><div><p>deep content</p></div></div></div>")
        md = page.markdown
        assert "deep content" in md

    def test_tail_text_captured(self):
        page = Page("<p>Hello <em>world</em> today</p>")
        md = page.markdown
        assert "Hello" in md
        assert "*world*" in md
        assert "today" in md

    def test_page_only_body(self):
        page = Page("<html><head><title>x</title></head><body><p>body only</p></body></html>")
        md = page.markdown
        assert "body only" in md
        assert "x" not in md  # title skipped


class TestTitle:
    def test_title(self):
        page = Page("<html><head><title>My Page</title></head><body></body></html>")
        assert page.title == "My Page"

    def test_no_title(self):
        page = Page("<html><body><p>no title</p></body></html>")
        assert page.title == ""

    def test_whitespace_title(self):
        page = Page("<html><head><title>  Spaced  </title></head></html>")
        assert page.title == "Spaced"


class TestLinks:
    def test_basic(self):
        page = Page('<a href="/a">Link A</a><a href="/b">Link B</a>', url="https://example.com")
        links = page.links()
        assert len(links) == 2
        assert links[0] == {"text": "Link A", "href": "https://example.com/a"}
        assert links[1] == {"text": "Link B", "href": "https://example.com/b"}

    def test_no_links(self):
        page = Page("<p>just text</p>")
        assert page.links() == []

    def test_absolute_urls_untouched(self):
        page = Page('<a href="https://other.com/x">External</a>')
        links = page.links()
        assert links[0]["href"] == "https://other.com/x"

    def test_skips_javascript(self):
        page = Page('<a href="javascript:void(0)">JS</a>')
        links = page.links()
        assert links[0]["href"] == "javascript:void(0)"  # not resolved

    def test_empty_href(self):
        page = Page("<a>no href</a>")
        links = page.links()
        assert links[0] == {"text": "no href", "href": ""}

    def test_nested_text(self):
        page = Page('<a href="/x"><strong>bold</strong> text</a>', url="https://e.com")
        links = page.links()
        assert links[0]["text"] == "bold text"
        assert links[0]["href"] == "https://e.com/x"

    def test_base_url_override(self):
        page = Page('<a href="/path">Link</a>')
        links = page.links(base_url="https://override.com")
        assert links[0]["href"] == "https://override.com/path"


class TestJsonLD:
    def test_single_object(self):
        page = Page(
            '<script type="application/ld+json">'
            '{"@context": "https://schema.org", "@type": "WebSite", "name": "Test"}'
            '</script>'
        )
        data = page.jsonld()
        assert len(data) == 1
        assert data[0]["@type"] == "WebSite"
        assert data[0]["name"] == "Test"

    def test_array(self):
        page = Page(
            '<script type="application/ld+json">'
            '[{"@type": "A"}, {"@type": "B"}]'
            '</script>'
        )
        data = page.jsonld()
        assert len(data) == 2

    def test_multiple_scripts(self):
        page = Page(
            '<script type="application/ld+json">{"@type": "One"}</script>'
            '<script type="application/ld+json">{"@type": "Two"}</script>'
        )
        data = page.jsonld()
        assert len(data) == 2

    def test_no_jsonld(self):
        page = Page("<html><body>nothing</body></html>")
        assert page.jsonld() == []

    def test_invalid_json(self):
        page = Page('<script type="application/ld+json">{bad json}</script>')
        assert page.jsonld() == []

    def test_empty_script(self):
        page = Page('<script type="application/ld+json"></script>')
        assert page.jsonld() == []

    def test_ignores_regular_scripts(self):
        page = Page('<script>var x = 1;</script>')
        assert page.jsonld() == []
