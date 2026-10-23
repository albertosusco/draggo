import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from draggo.shelf import (  # noqa: E402
    KIND_FILE, KIND_LINK, KIND_TEXT, Shelf, classify_uri, looks_like_url, name_for, parse_uri_list,
)


class HelpersTest(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(classify_uri("file:///tmp/a.txt"), KIND_FILE)
        self.assertEqual(classify_uri("sftp://host/a.txt"), KIND_FILE)
        self.assertEqual(classify_uri("https://example.com"), KIND_LINK)
        self.assertEqual(classify_uri("mailto:a@b.c"), KIND_LINK)
        self.assertIsNone(classify_uri("just text"))

    def test_parse_uri_list(self):
        data = "# comment\r\nfile:///a\r\n\r\nhttps://b.org/x\r\n\0"
        self.assertEqual(parse_uri_list(data), ["file:///a", "https://b.org/x"])

    def test_looks_like_url(self):
        self.assertTrue(looks_like_url("https://gnome.org/"))
        self.assertTrue(looks_like_url("  mailto:me@example.com\n"))
        self.assertFalse(looks_like_url("see https://gnome.org"))
        self.assertFalse(looks_like_url("https:nothing"))

    def test_names(self):
        self.assertEqual(name_for(KIND_FILE, "file:///home/u/My%20File.pdf"), "My File.pdf")
        self.assertEqual(name_for(KIND_FILE, "file:///home/u/dir/"), "dir")
        self.assertEqual(name_for(KIND_LINK, "https://example.com/a/b/"), "example.com/a/b")
        self.assertEqual(name_for(KIND_TEXT, "\n\n  hello\nworld"), "hello")


class ShelfTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = os.path.join(self.tmp.name, "shelf.json")
        self.files = os.path.join(self.tmp.name, "files")
        self.shelf = Shelf(self.storage, self.files)
        self.changes = 0
        self.shelf.connect(lambda _s: setattr(self, "changes", self.changes + 1))

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_uris_mixed(self):
        added = self.shelf.add_uris(["file:///tmp/a", "https://x.org", "file:///tmp/a"])
        self.assertEqual([i.kind for i in added], [KIND_FILE, KIND_LINK])
        self.assertEqual(len(self.shelf), 2)
        self.assertEqual(self.changes, 1)

    def test_no_duplicates(self):
        self.shelf.add_text("hello")
        self.assertEqual(self.shelf.add_text("hello"), [])
        self.assertEqual(len(self.shelf), 1)

    def test_add_text_detects_kinds(self):
        self.assertEqual(self.shelf.add_text("https://fedoraproject.org\n")[0].kind, KIND_LINK)
        self.assertEqual(self.shelf.add_text("file:///a\nfile:///b")[0].kind, KIND_FILE)
        path = os.path.join(self.tmp.name, "real.txt")
        open(path, "w").close()
        self.assertEqual(self.shelf.add_text(path)[0].kind, KIND_FILE)
        self.assertEqual(self.shelf.add_text("some words")[0].kind, KIND_TEXT)
        self.assertEqual(self.shelf.add_text("   "), [])

    def test_remove_and_clear(self):
        a, b = self.shelf.add_uris(["https://a.org", "https://b.org"])
        self.shelf.remove(a.id)
        self.assertEqual([i.id for i in self.shelf.items], [b.id])
        self.shelf.clear()
        self.assertFalse(self.shelf)

    def test_owned_files_are_deleted(self):
        path = self.shelf.new_owned_path(".png")
        with open(path, "wb") as f:
            f.write(b"x")
        (item,) = self.shelf.add_owned_file(path)
        self.shelf.remove(item.id)
        self.assertFalse(os.path.exists(path))

    def test_foreign_files_are_never_deleted(self):
        path = os.path.join(self.tmp.name, "mine.txt")
        open(path, "w").close()
        (item,) = self.shelf.add_text(path)
        self.shelf.remove(item.id)
        self.assertTrue(os.path.exists(path))

    def test_persistence(self):
        path = os.path.join(self.tmp.name, "keep.txt")
        open(path, "w").close()
        self.shelf.add_text(path)
        self.shelf.add_text("note")
        self.shelf.add_uris(["file:///does/not/exist"])
        other = Shelf(self.storage, self.files)
        other.load()
        self.assertEqual([i.kind for i in other.items], [KIND_FILE, KIND_TEXT])


if __name__ == "__main__":
    unittest.main()
