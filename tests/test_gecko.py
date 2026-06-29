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
