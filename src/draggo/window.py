from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango

from . import dnd
from .i18n import _, n_items
from .shelf import KIND_FILE, KIND_LINK


def attach_drag_source(widget, app, get_items, icon_widget):
    """Make `widget` draggable, offering the items returned by `get_items()`."""
    source = Gtk.DragSource(actions=Gdk.DragAction.COPY)
    state = {"ids": [], "cancelled": False}

    def on_prepare(_source, _x, _y):
        items = get_items()
        state["ids"] = [i.id for i in items]
        state["cancelled"] = False
        return dnd.content_for_items(items)

    def on_begin(source, _drag):
        paintable = Gtk.WidgetPaintable.new(icon_widget)
        source.set_icon(paintable, icon_widget.get_width() // 2, icon_widget.get_height() // 2)

    def on_cancel(_source, _drag, _reason):
        state["cancelled"] = True
        return False

    def on_end(_source, _drag, _delete_data):
        if not state["cancelled"] and app.settings["remove-after-drag"]:
            ids = state["ids"]
            GLib.idle_add(lambda: app.shelf.remove(*ids) and False)
        state["ids"] = []

    source.connect("prepare", on_prepare)
    source.connect("drag-begin", on_begin)
    source.connect("drag-cancel", on_cancel)
    source.connect("drag-end", on_end)
    widget.add_controller(source)
    return source


class ItemRow(Gtk.ListBoxRow):
    def __init__(self, app, item):
        super().__init__(activatable=True)
        self.item = item
        self.add_css_class("draggo-item")
        self.set_tooltip_text(dnd.plain_text_for(item))

        box = Gtk.Box(spacing=10, margin_top=6, margin_bottom=6, margin_start=6, margin_end=4)
        self.icon = Gtk.Image(pixel_size=32, valign=Gtk.Align.CENTER)
        self.icon.add_css_class("draggo-icon")

        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, hexpand=True)
        self.title = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.MIDDLE, label=item.name)
        self.subtitle = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        self.subtitle.add_css_class("dim-label")
        self.subtitle.add_css_class("caption")
        labels.append(self.title)
        labels.append(self.subtitle)

        remove = Gtk.Button(icon_name="window-close-symbolic", valign=Gtk.Align.CENTER,
                            tooltip_text=_("Remove"))
        remove.add_css_class("flat")
        remove.add_css_class("circular")
        remove.connect("clicked", lambda *_a: app.shelf.remove(item.id))

        box.append(self.icon)
        box.append(labels)
        box.append(remove)
        self.set_child(box)

        self._describe()
        attach_drag_source(self, app, lambda: [i for i in [app.shelf.get(item.id)] if i], self.icon)

    def _describe(self):
        item = self.item
        if item.kind == KIND_LINK:
            self.icon.set_from_icon_name("web-browser-symbolic")
            self.subtitle.set_label(item.value)
        elif item.kind == KIND_FILE:
            self.icon.set_from_icon_name("text-x-generic")
            self.subtitle.set_label(dnd.plain_text_for(item))
            gfile = Gio.File.new_for_uri(item.value)
            gfile.query_info_async(
                "standard::display-name,standard::icon,standard::content-type,"
                "standard::size,standard::type,thumbnail::path",
                Gio.FileQueryInfoFlags.NONE, GLib.PRIORITY_DEFAULT, None, self._on_file_info)
        else:
            self.icon.set_from_icon_name("text-x-generic-symbolic")
            text = item.value.strip()
            self.subtitle.set_label(_("Text") + " · " + _("{n} characters").format(n=len(text)))

    def _on_file_info(self, gfile, result):
        try:
            info = gfile.query_info_finish(result)
        except GLib.Error:
            self.icon.set_from_icon_name("dialog-warning-symbolic")
            self.subtitle.set_label(_("File not found"))
            return
        self.title.set_label(info.get_display_name() or self.item.name)
        thumbnail = info.get_attribute_byte_string("thumbnail::path")
        if thumbnail:
            self.icon.set_from_file(thumbnail)
        elif info.get_icon():
            self.icon.set_from_gicon(info.get_icon())
        if info.get_file_type() == Gio.FileType.DIRECTORY:
            self.subtitle.set_label(_("Folder"))
        else:
            ctype = info.get_content_type()
            description = Gio.content_type_get_description(ctype) if ctype else ""
            size = GLib.format_size(info.get_size())
            self.subtitle.set_label(f"{description} · {size}" if description else size)


class ShelfWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Draggo", default_width=300, default_height=380)
        self.app = app
        self.set_hide_on_close(True)
        self.set_size_request(240, 220)

        header = Adw.HeaderBar()
        self.window_title = Adw.WindowTitle(title="Draggo")
        header.set_title_widget(self.window_title)

        self.drag_all = Gtk.Box(valign=Gtk.Align.CENTER, tooltip_text=_("Drag all items"))
        self.drag_all.add_css_class("draggo-handle")
        self.drag_all_icon = Gtk.Image(icon_name="edit-copy-symbolic")
        self.drag_all.append(self.drag_all_icon)
        self.drag_all.set_cursor(Gdk.Cursor.new_from_name("grab"))
        attach_drag_source(self.drag_all, app, lambda: list(app.shelf.items), self.drag_all_icon)
        header.pack_start(self.drag_all)

        menu = Gio.Menu()
        section = Gio.Menu()
        section.append(_("Paste"), "app.paste")
        section.append(_("Clear Shelf"), "app.clear")
        menu.append_section(None, section)
        section = Gio.Menu()
        section.append(_("Remove Items After Dragging Out"), "app.remove-after-drag")
        section.append(_("Keep Items Across Restarts"), "app.persist")
        menu.append_section(None, section)
        section = Gio.Menu()
        section.append(_("About Draggo"), "app.about")
        section.append(_("Quit"), "app.quit")
        menu.append_section(None, section)
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu,
                                       tooltip_text=_("Main Menu")))

        empty = Adw.StatusPage(icon_name="document-send-symbolic", title=_("Drop here"),
                               description=_("Files, links and text wait here until you drag them out again."))
        empty.add_css_class("compact")
        empty.add_css_class("draggo-empty")

        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.list.add_css_class("navigation-sidebar")
        self.list.connect("row-activated", self._on_row_activated)
        scrolled = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        scrolled.set_child(self.list)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.stack.add_named(empty, "empty")
        self.stack.add_named(scrolled, "items")

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(self.stack)
        toolbar.add_css_class("draggo-drop-target")
        self.set_content(toolbar)
        self.drop_area = toolbar
        self._setup_drop_target(toolbar)

        app.shelf.connect(lambda _shelf: self.refresh())
        self.refresh()

    # -- drop target ------------------------------------------------------

    def _setup_drop_target(self, widget):
        target = Gtk.DropTargetAsync.new(dnd.accepted_formats(), Gdk.DragAction.COPY)

        def on_accept(_target, drop):
            # Ignore drags that start from the shelf itself.
            return drop.get_drag() is None

        def on_enter(_target, _drop, _x, _y):
            widget.add_css_class("drop-hover")
            return Gdk.DragAction.COPY

        def on_motion(_target, _drop, _x, _y):
            return Gdk.DragAction.COPY

        def on_leave(_target, _drop):
            widget.remove_css_class("drop-hover")

        def on_drop(_target, drop, _x, _y):
            widget.remove_css_class("drop-hover")
            self.app.begin_drop()

            def done(ok):
                drop.finish(Gdk.DragAction.COPY if ok else 0)
                self.app.end_drop()

            dnd.read_offer(drop, self.app.shelf, done)
            return True

        target.connect("accept", on_accept)
        target.connect("drag-enter", on_enter)
        target.connect("drag-motion", on_motion)
        target.connect("drag-leave", on_leave)
        target.connect("drop", on_drop)
        widget.add_controller(target)

    # -- view -------------------------------------------------------------

    def refresh(self):
        child = self.list.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.list.remove(child)
            child = nxt
        for item in self.app.shelf.items:
            self.list.append(ItemRow(self.app, item))
        count = len(self.app.shelf)
        self.stack.set_visible_child_name("items" if count else "empty")
        self.window_title.set_subtitle(n_items(count))
        self.drag_all.set_visible(count > 1)

    def _on_row_activated(self, _list, row):
        uri = row.item.value if row.item.kind != "text" else None
        if uri:
            Gtk.UriLauncher.new(uri).launch(self, None, None, None)
