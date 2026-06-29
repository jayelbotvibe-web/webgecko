"""HTML parser — CSS selectors, XPath, text search."""
from __future__ import annotations

import re
from typing import Any

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


class Page:
    __slots__ = ("_root", "url", "encoding")

    def __init__(self, content: str | bytes, url: str = "", encoding: str = "utf-8"):
        self.url = url
        self.encoding = encoding
        if isinstance(content, bytes):
            content = content.decode(encoding, errors="replace")
        self._root = document_fromstring(content, parser=HTMLParser(encoding=encoding))

    def css(self, selector: str) -> Elements:
        m = _PSEUDO.search(selector)
        if not m:
            return self.xpath(_translator.css_to_xpath(selector))

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

    @property
    def text(self) -> str:
        return "".join(self._root.itertext()).strip()

    @property
    def html(self) -> str:
        return (self._root.text or "") + "".join(tostring(c, encoding="unicode") for c in self._root)

    @property
    def tag(self) -> str:
        return self._root.tag

    def attr(self, name: str, default: str | None = None) -> str | None:
        return self._root.attrib.get(name, default)

    def __repr__(self) -> str:
        return f"Page({self.tag}{f' url={self.url!r}' if self.url else ''})"


class Element(Page):
    __slots__ = ()

    def __init__(self, el: HtmlElement):
        self.url = ""
        self.encoding = "utf-8"
        self._root = el

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
                val = item.css(selector).get()
                row[key] = val
            results.append(row)

        if first:
            return results[0] if results else None
        return results

    def __repr__(self) -> str:
        return f"Elements({len(self._items)} items)"
