"""Helpers to turn shelf items into drag data and dropped data into shelf items."""

from gi.repository import Gdk, Gio, GLib, GObject

from .shelf import KIND_FILE, KIND_LINK, KIND_TEXT, parse_uri_list

URI_LIST = "text/uri-list"

# Everything the shelf is willing to receive.
ACCEPTED_MIME_TYPES = [
    URI_LIST,
    "text/x-moz-url",
    "text/plain;charset=utf-8",
    "text/plain",
    "UTF8_STRING",
    "STRING",
    "TEXT",
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
    "image/bmp",
]


def accepted_formats():
    builder = Gdk.ContentFormatsBuilder.new()
    for mime in ACCEPTED_MIME_TYPES:
        builder.add_mime_type(mime)
    builder.add_gtype(Gdk.FileList)
    builder.add_gtype(Gdk.Texture)
    builder.add_gtype(GObject.TYPE_STRING)
    return builder.to_formats()


def _bytes_provider(mime, text):
    return Gdk.ContentProvider.new_for_bytes(mime, GLib.Bytes.new(text.encode("utf-8")))


def _value(gtype, obj):
    value = GObject.Value(gtype)
    if gtype == GObject.TYPE_STRING:
        value.set_string(obj)
    else:
        value.set_boxed(obj)
    return value


def plain_text_for(item):
    if item.kind == KIND_FILE:
        return Gio.File.new_for_uri(item.value).get_path() or item.value
    return item.value


def content_for_items(items):
    """Build a GdkContentProvider offering the given items to drop targets.

    Files are offered as a GdkFileList (which GTK exports as text/uri-list and,
    for sandboxed apps, through the file transfer portal); links as
    text/uri-list; everything also as plain text.
    """
    items = list(items)
    if not items:
        return None
    providers = []
    kinds = {i.kind for i in items}

    if kinds == {KIND_FILE}:
        files = [Gio.File.new_for_uri(i.value) for i in items]
        providers.append(Gdk.ContentProvider.new_for_value(
            _value(Gdk.FileList, Gdk.FileList.new_from_array(files))))
    else:
        uris = [i.value for i in items if i.kind in (KIND_FILE, KIND_LINK)]
        if uris:
            providers.append(_bytes_provider(URI_LIST, "\r\n".join(uris) + "\r\n"))
        if len(items) == 1 and items[0].kind == KIND_LINK:
            link = items[0]
            moz = f"{link.value}\n{link.name}".encode("utf-16-le")
            providers.append(Gdk.ContentProvider.new_for_bytes("text/x-moz-url", GLib.Bytes.new(moz)))

    text = "\n".join(plain_text_for(i) for i in items)
    providers.append(Gdk.ContentProvider.new_for_value(_value(GObject.TYPE_STRING, text)))
    return Gdk.ContentProvider.new_union(providers)


# -- receiving ------------------------------------------------------------

def _read_stream(stream, callback):
    """Read a whole GInputStream asynchronously and pass the bytes to callback."""
    out = Gio.MemoryOutputStream.new_resizable()

    def done(out, result):
        try:
            out.splice_finish(result)
            callback(out.steal_as_bytes().get_data())
        except GLib.Error:
            callback(None)

    out.splice_async(
        stream,
        Gio.OutputStreamSpliceFlags.CLOSE_SOURCE | Gio.OutputStreamSpliceFlags.CLOSE_TARGET,
        GLib.PRIORITY_DEFAULT, None, done)


def _decode(data, mime):
    if data is None:
        return None
    if mime == "text/x-moz-url":
        text = bytes(data).decode("utf-16-le", errors="replace")
        return text.split("\n", 1)[0]
    return bytes(data).decode("utf-8", errors="replace")


def read_offer(offer, shelf, done):
    """Read data from a GdkDrop or GdkClipboard into the shelf.

    `done(ok)` is called once the data has been read (or reading failed).
    """
    formats = offer.get_formats()

    def read_mime(mime, handle):
        def on_read(offer, result):
            try:
                stream, _mime = offer.read_finish(result)
            except GLib.Error:
                done(False)
                return
            _read_stream(stream, lambda data: handle(_decode(data, mime)))
        offer.read_async([mime], GLib.PRIORITY_DEFAULT, None, on_read)

    def read_value(gtype, handle):
        def on_read(offer, result):
            try:
                value = offer.read_value_finish(result)
            except GLib.Error:
                done(False)
                return
            handle(value)
        offer.read_value_async(gtype, GLib.PRIORITY_DEFAULT, None, on_read)

    def finish_with(added):
        done(bool(added))

    # Prefer the plain URI list: it carries the real paths of the files,
    # whereas the portal format would hand us temporary document-portal paths.
    if formats.contain_mime_type(URI_LIST):
        def on_uris(text):
            uris = parse_uri_list(text or "")
            finish_with(shelf.add_uris(uris) if uris else [])
        read_mime(URI_LIST, on_uris)
    elif formats.contain_gtype(Gdk.FileList):
        def on_files(file_list):
            files = file_list.get_files() if file_list else []
            finish_with(shelf.add_uris([f.get_uri() for f in files]))
        read_value(Gdk.FileList, on_files)
    elif formats.contain_mime_type("text/x-moz-url"):
        read_mime("text/x-moz-url", lambda url: finish_with(shelf.add_text(url) if url else []))
    elif formats.contain_gtype(Gdk.Texture):
        def on_texture(texture):
            if texture is None or not shelf.files_dir:
                done(False)
                return
            path = shelf.new_owned_path(".png")
            texture.save_to_png(path)
            finish_with(shelf.add_owned_file(path))
        read_value(Gdk.Texture, on_texture)
    elif formats.contain_gtype(GObject.TYPE_STRING):
        read_value(GObject.TYPE_STRING, lambda text: finish_with(shelf.add_text(text) if text else []))
    else:
        done(False)
