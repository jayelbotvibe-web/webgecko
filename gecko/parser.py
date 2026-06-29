"""HTML parser — CSS selectors, XPath, text search, markdown conversion."""
from __future__ import annotations

import json as _json
import re
from typing import Any
from urllib.parse import urljoin as _urljoin

from cssselect import GenericTranslator
from lxml.etree import XPath, tostring
from lxml.html import HtmlElement, HTMLParser, document_fromstring

_translator = GenericTranslator()
_PSEUDO = re.compile(r'::(text|attr\(([^)]+)\))\s*$')


def _escape_xpath_str(s: str) -> str:
    if '"' not in s:
        return f'"{s}"'
    if "'" not in s:
        return f"'{s}'"
    return "concat(" + ", ".join(f'"{part}"' for part in s.split('"')) + ")"


# ── markdown converter ──────────────────────────────────────────────

_BLOCK_TAGS = frozenset({"p", "div", "section", "article", "main", "aside", "header",
                          "footer", "nav", "form", "fieldset", "figure", "figcaption",
                          "details", "summary", "dialog", "address"})
_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_LIST_TAGS = frozenset({"ul", "ol", "li"})
_VOID_TAGS = frozenset({"br", "hr", "img", "input", "meta", "link"})
_SKIP_TAGS = frozenset({"script", "style", "noscript", "head", "title", "template"})


def _inline_text(el: HtmlElement, base_url: str) -> str:
    """Collect inline text from an element, including tail text."""
    tag = el.tag
    if tag in _SKIP_TAGS:
        return ""
    parts = []
    t = (el.text or "")
    if t.strip():
        parts.append(t)
    for child in el:
        parts.append(_inline_text(child, base_url))
        tail = (child.tail or "")
        if tail.strip():
            parts.append(tail)
    text = "".join(parts).strip()

    if not text:
        if tag == "br":
            return "\n"
        if tag == "img":
            alt = el.attrib.get("alt", "")
            src = _urljoin(base_url, el.attrib.get("src", ""))
            return f"![{alt}]({src})"
        return ""

    if tag in _HEADING_TAGS:
        level = int(tag[1])
        return f"{'#' * level} {text}\n\n"
    if tag == "li":
        return text
    if tag in ("strong", "b"):
        return f"**{text}**"
    if tag in ("em", "i"):
        return f"*{text}*"
    if tag == "code":
        return f"`{text}`"
    if tag in ("del", "s"):
        return f"~~{text}~~"
    if tag == "a":
        href = _urljoin(base_url, el.attrib.get("href", ""))
        return f"[{text}]({href})"
    return text


def _md(el: HtmlElement, base_url: str = "") -> str:
    tag = el.tag
    if tag in _SKIP_TAGS:
        return ""

    # void tags — no children, render immediately
    if tag == "br":
        return "\n"
    if tag == "hr":
        return "---\n\n"
    if tag == "img":
        alt = el.attrib.get("alt", "")
        src = _urljoin(base_url, el.attrib.get("src", ""))
        return f"![{alt}]({src})"

    children = list(el)

    # headings / list items / inline wrappers — use _inline_text for text content
    if tag in _HEADING_TAGS:
        return _inline_text(el, base_url)
    if tag in ("strong", "b", "em", "i", "code", "del", "s", "a"):
        return _inline_text(el, base_url)

    # lists
    if tag in ("ul", "ol"):
        items = []
        for li in children:
            if not isinstance(li, HtmlElement) or li.tag != "li":
                continue
            li_text = _inline_text(li, base_url)
            if not li_text:
                continue
            if tag == "ul":
                items.append(f"- {li_text}")
            else:
                items.append(f"1. {li_text}")
        return "\n".join(items) + "\n\n" if items else ""

    # li handled inline
    if tag == "li":
        return _inline_text(el, base_url)

    # pre > code blocks
    if tag == "pre":
        code_el = el.find("code")
        if code_el is not None:
            lang = code_el.attrib.get("class", "").replace("language-", "")
            inner = code_el.text or ""
            for c in code_el:
                inner += "".join(c.itertext())
                inner += c.tail or ""
        else:
            lang = ""
            inner = el.text or ""
        return f"```{lang}\n{inner.strip()}\n```\n\n"

    # blockquote
    if tag == "blockquote":
        inner = _block_children(el, base_url)
        return "\n".join(f"> {line}" for line in inner.split("\n")) + "\n\n" if inner.strip() else ""

    # block containers and fallback
    return _block_children(el, base_url)


def _block_children(el: HtmlElement, base_url: str) -> str:
    """Process children of a block element, capturing text and tails."""
    parts = []
    t = (el.text or "").strip()
    if t:
        parts.append(t + "\n\n")
    for child in el:
        parts.append(_md(child, base_url))
        tail = (child.tail or "").strip()
        if tail:
            parts.append(tail + "\n\n")
    joined = "".join(parts).strip()
    return joined + "\n\n" if joined else ""


def _html_to_md(html_el: HtmlElement, base_url: str = "") -> str:
    """Convert an lxml HtmlElement tree to markdown."""
    body = html_el.find("body") if html_el.tag == "html" else html_el
    if body is None:
        body = html_el
    return _block_children(body, base_url).strip()


# ── Page / Element / Elements ────────────────────────────────────────


class Page:
    __slots__ = ("_root", "url", "encoding")

    def __init__(self, content: str | bytes, url: str = "", encoding: str = "utf-8"):
        self.url = url
        self.encoding = encoding
        if content is None:
            content = "<html></html>"
        if isinstance(content, bytes):
            content = content.decode(encoding, errors="replace")
        if not content.strip():
            content = "<html></html>"
        self._root = document_fromstring(content, parser=HTMLParser(encoding=encoding))

    # ── query methods ────────────────────────────────────────────────

    def css(self, selector: str) -> Elements:
        m = _PSEUDO.search(selector)
        try:
            if not m:
                return self.xpath(_translator.css_to_xpath(selector))
        except Exception as e:
            raise ValueError(f"Bad selector: {selector}") from e

        kind = m.group(1)
        base_css = selector[:m.start()]
        base_xpath = _translator.css_to_xpath(base_css or "*")

        if kind == "text":
            xpath = base_xpath + "/text()"
        else:
            xpath = base_xpath + f"/@{m.group(2)}"

        try:
            compiled = XPath(xpath)
        except Exception:
            raise ValueError(f"Bad selector: {selector}")
        nodes = compiled(self._root)

        if kind == "text":
            return Elements([str(n).strip() for n in nodes if str(n).strip()])
        return Elements([str(n) for n in nodes])

    def xpath(self, expression: str) -> Elements:
        try:
            compiled = XPath(expression)
        except Exception:
            raise ValueError(f"Bad XPath: {expression}")
        nodes = compiled(self._root)
        return Elements([Element(n) for n in nodes if isinstance(n, HtmlElement)])

    def find(self, text: str, *, partial: bool = False) -> Elements:
        escaped = _escape_xpath_str(text)
        xpath = (f".//*[contains(text(), {escaped})]" if partial
                 else f".//*[normalize-space(text()) = {escaped}]")
        return self.xpath(xpath)

    def find_all(self, tag: str | None = None, **attrs) -> Elements:
        parts = [".//", tag if tag else "*"]
        conditions = [f"@{k.rstrip('_')}={_escape_xpath_str(str(v))}" for k, v in attrs.items()]
        if conditions:
            parts.append("[" + " and ".join(conditions) + "]")
        return self.xpath("".join(parts))

    # ── properties ───────────────────────────────────────────────────

    @property
    def text(self) -> str:
        return "".join(self._root.itertext()).strip()

    @property
    def html(self) -> str:
        return (self._root.text or "") + "".join(tostring(c, encoding="unicode") for c in self._root)

    @property
    def tag(self) -> str:
        return self._root.tag

    @property
    def title(self) -> str:
        t = self.css("title::text").get()
        return str(t) if t else ""

    @property
    def markdown(self) -> str:
        return _html_to_md(self._root, self.url)

    def attr(self, name: str, default: str | None = None) -> str | None:
        return self._root.attrib.get(name, default)

    # ── convenience methods ──────────────────────────────────────────

    def links(self, *, base_url: str | None = None) -> list[dict[str, str]]:
        """Return all links as [{"text": ..., "href": ...}]."""
        base = base_url or self.url
        results = []
        for a in self._root.iter("a"):
            href = a.attrib.get("href", "")
            if base and href and not href.startswith(("http://", "https://", "#", "javascript:", "mailto:")):
                href = _urljoin(base, href)
            text = re.sub(r"\s+", " ", "".join(a.itertext())).strip()
            if href or text:
                results.append({"text": text, "href": href})
        return results

    def jsonld(self) -> list[dict]:
        """Extract JSON-LD structured data from <script type='application/ld+json'>."""
        results = []
        for script in self._root.iter("script"):
            if script.attrib.get("type") == "application/ld+json":
                try:
                    data = _json.loads(script.text or "")
                except (_json.JSONDecodeError, TypeError):
                    continue
                if isinstance(data, list):
                    results.extend(data)
                elif isinstance(data, dict):
                    results.append(data)
        return results

    def __repr__(self) -> str:
        return f"Page({self.tag}{f' url={self.url!r}' if self.url else ''})"


class Element(Page):
    __slots__ = ()

    def __init__(self, el: HtmlElement):
        self.url = ""
        self.encoding = "utf-8"
        self._root = el

    @property
    def parent(self) -> Element | None:
        p = self._root.getparent()
        return Element(p) if p is not None else None

    @property
    def children(self) -> Elements:
        return Elements([Element(c) for c in self._root.getchildren()])

    @property
    def next_sibling(self) -> Element | None:
        n = self._root.getnext()
        return Element(n) if n is not None else None

    @property
    def prev_sibling(self) -> Element | None:
        p = self._root.getprevious()
        return Element(p) if p is not None else None

    def __repr__(self) -> str:
        cls = self._root.attrib.get("class", "")
        id_ = self._root.attrib.get("id", "")
        return f"<{self.tag}{f'.{cls.replace(chr(32), chr(46))}' if cls else ''}{f'#{id_}' if id_ else ''}>"


class Elements:
    __slots__ = ("_items",)

    def __init__(self, items: list):
        self._items = items

    def __iter__(self):
        return iter(self._items)

    def __getitem__(self, index: int | slice):
        if isinstance(index, slice):
            return Elements(self._items[index])
        return self._items[index]

    def __len__(self) -> int:
        return len(self._items)

    def __bool__(self) -> bool:
        return bool(self._items)

    def get(self, default: Any = None) -> Any:
        return self._items[0] if self._items else default

    def extract(self, fields: dict[str, str], *, first: bool = False) -> list[dict] | dict | None:
        """Extract named fields from each element using CSS selectors.

        fields: {"name": ".title::text", "url": "a::attr(href)"}
        Returns list of dicts. With first=True, returns single dict or None.
        """
        results = []
        for item in self._items:
            if not isinstance(item, (Element, Page)):
                continue
            row = {}
            for key, selector in fields.items():
                try:
                    val = item.css(selector).get()
                except ValueError:
                    val = None
                row[key] = val
            results.append(row)

        if first:
            return results[0] if results else None
        return results

    def __repr__(self) -> str:
        return f"Elements({len(self._items)} items)"
