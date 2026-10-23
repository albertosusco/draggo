"""The shelf model: an ordered list of items waiting to be dragged somewhere.

This module has no GTK dependency so it can be unit-tested on its own.
"""

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from urllib.parse import unquote, urlsplit

KIND_FILE = "file"
KIND_LINK = "link"
KIND_TEXT = "text"

LINK_SCHEMES = {
    "http", "https", "ftp", "ftps", "mailto", "magnet", "irc", "ircs",
    "tel", "sms", "geo", "news", "gemini", "ssh", "git",
}

_NAME_MAX = 80


@dataclass
class ShelfItem:
    kind: str
    value: str  # a URI for files and links, the text itself for text
    name: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    added: float = field(default_factory=time.time)
    # True when Draggo created the file itself (e.g. an image dropped as raw
    # data) and must delete it once the item leaves the shelf.
    owned: bool = False

    @classmethod
    def from_dict(cls, data):
        return cls(
            kind=data["kind"],
            value=data["value"],
            name=data.get("name") or data["value"],
            id=data.get("id") or uuid.uuid4().hex,
            added=data.get("added", time.time()),
            owned=bool(data.get("owned", False)),
        )

    @property
    def local_path(self):
        if self.kind != KIND_FILE:
            return None
        parts = urlsplit(self.value)
        if parts.scheme != "file":
            return None
        return unquote(parts.path)


def _truncate(text, limit=_NAME_MAX):
    return text if len(text) <= limit else text[: limit - 1] + "…"


def uri_scheme(uri):
    return urlsplit(uri).scheme.lower()


def classify_uri(uri):
    """Return KIND_LINK or KIND_FILE for a URI, or None if it is not a URI."""
    scheme = uri_scheme(uri)
    if not scheme or len(scheme) == 1:  # "C:" style paths are not URIs
        return None
    return KIND_LINK if scheme in LINK_SCHEMES else KIND_FILE


def parse_uri_list(data):
    """Parse a text/uri-list payload (RFC 2483)."""
    uris = []
    for line in data.replace("\0", "").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            uris.append(line)
    return uris


def looks_like_url(text):
    text = text.strip()
    if not text or any(c.isspace() for c in text):
        return False
    parts = urlsplit(text)
    scheme = parts.scheme.lower()
    if scheme not in LINK_SCHEMES:
        return False
    return bool(parts.netloc) or scheme in {"mailto", "magnet", "tel", "sms", "geo", "news"}


def name_for(kind, value):
    if kind == KIND_FILE:
        parts = urlsplit(value)
        base = os.path.basename(unquote(parts.path).rstrip("/"))
        return base or unquote(value)
    if kind == KIND_LINK:
        parts = urlsplit(value)
        if parts.netloc:
            rest = unquote(parts.path).rstrip("/")
            return _truncate(parts.netloc + rest)
        return _truncate(unquote(value.split(":", 1)[-1]))
    for line in value.splitlines():
        if line.strip():
            return _truncate(line.strip())
    return _truncate(value.strip()) or "…"


def path_to_uri(path):
    from pathlib import Path
    return Path(path).absolute().as_uri()


class Shelf:
    """Ordered collection of ShelfItem with change notification and persistence."""

    def __init__(self, storage_path=None, files_dir=None):
        self.items = []
        self.storage_path = storage_path
        self.files_dir = files_dir
        self._listeners = []

    # -- notification -----------------------------------------------------

    def connect(self, callback):
        self._listeners.append(callback)

    def _changed(self):
        self.save()
        for callback in list(self._listeners):
            callback(self)

    # -- queries ----------------------------------------------------------

    def __len__(self):
        return len(self.items)

    def __bool__(self):
        return bool(self.items)

    def get(self, item_id):
        for item in self.items:
            if item.id == item_id:
                return item
        return None

    def _contains(self, kind, value):
        return any(i.kind == kind and i.value == value for i in self.items)

    # -- adding -----------------------------------------------------------

    def add(self, kind, value, owned=False):
        return self.add_many([(kind, value, owned)])

    def add_many(self, entries):
        added = []
        for kind, value, owned in entries:
            if not value or self._contains(kind, value):
                continue
            if any(a.kind == kind and a.value == value for a in added):
                continue
            added.append(ShelfItem(kind=kind, value=value, name=name_for(kind, value), owned=owned))
        if added:
            self.items.extend(added)
            self._changed()
        return added

    def add_uris(self, uris):
        entries = []
        for uri in uris:
            kind = classify_uri(uri)
            if kind:
                entries.append((kind, uri, False))
        return self.add_many(entries)

    def add_text(self, text):
        """Add dropped or pasted text, recognising URLs, URI lists and paths."""
        text = text.replace("\0", "")
        stripped = text.strip()
        if not stripped:
            return []
        if looks_like_url(stripped):
            return self.add(KIND_LINK, stripped)
        lines = parse_uri_list(stripped)
        if lines and all(uri_scheme(l) == "file" for l in lines):
            return self.add_uris(lines)
        if "\n" not in stripped and stripped.startswith("/") and os.path.exists(stripped):
            return self.add(KIND_FILE, path_to_uri(stripped))
        return self.add(KIND_TEXT, text)

    def add_owned_file(self, path):
        return self.add(KIND_FILE, path_to_uri(path), owned=True)

    def new_owned_path(self, suffix):
        os.makedirs(self.files_dir, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H-%M-%S")
        path = os.path.join(self.files_dir, f"Draggo {stamp}{suffix}")
        n = 1
        while os.path.exists(path):
            n += 1
            path = os.path.join(self.files_dir, f"Draggo {stamp} ({n}){suffix}")
        return path

    # -- removing ---------------------------------------------------------

    def remove(self, *item_ids):
        ids = set(item_ids)
        removed = [i for i in self.items if i.id in ids]
        if not removed:
            return []
        self.items = [i for i in self.items if i.id not in ids]
        for item in removed:
            self._discard(item)
        self._changed()
        return removed

    def clear(self):
        return self.remove(*[i.id for i in self.items])

    def _discard(self, item):
        path = item.local_path
        if not (item.owned and path and self.files_dir):
            return
        if os.path.dirname(os.path.abspath(path)) != os.path.abspath(self.files_dir):
            return
        try:
            os.remove(path)
        except OSError:
            pass

    def prune_missing(self):
        """Drop local file items whose file no longer exists."""
        missing = [i.id for i in self.items if i.local_path and not os.path.exists(i.local_path)]
        if missing:
            self.remove(*missing)
        return missing

    # -- persistence ------------------------------------------------------

    def load(self):
        if not self.storage_path or not os.path.exists(self.storage_path):
            return
        try:
            with open(self.storage_path, encoding="utf-8") as f:
                data = json.load(f)
            self.items = [ShelfItem.from_dict(d) for d in data.get("items", [])
                          if d.get("kind") in (KIND_FILE, KIND_LINK, KIND_TEXT)]
        except (OSError, ValueError, KeyError, TypeError):
            self.items = []
        self.prune_missing()

    def save(self):
        if not self.storage_path:
            return
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        tmp = self.storage_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "items": [asdict(i) for i in self.items]}, f, indent=1)
        os.replace(tmp, self.storage_path)
