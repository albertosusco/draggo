import os

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from . import config, dnd
from .i18n import _
from .shelf import Shelf
from .window import ShelfWindow

CSS = """
.draggo-drop-target.drop-hover {
    background-color: alpha(@accent_bg_color, 0.12);
    box-shadow: inset 0 0 0 2px @accent_bg_color;
}
.draggo-empty {
    margin: 12px;
    border-radius: 12px;
    border: 2px dashed alpha(currentColor, 0.2);
}
.draggo-handle {
    padding: 6px 8px;
    border-radius: 6px;
}
.draggo-handle:hover {
    background-color: alpha(currentColor, 0.08);
}
"""

# How long to wait after a drag ends before hiding an empty shelf; a drop on
# the shelf may still be transferring its data at that point.
HIDE_DELAY_AFTER_DRAG = 700
HIDE_DELAY_WHEN_EMPTIED = 400


class DraggoApplication(Adw.Application):
    def __init__(self):
        super().__init__(application_id=config.APP_ID,
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        GLib.set_application_name("Draggo")
        self.add_main_option("background", ord("b"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             _("Start without showing the shelf"), None)
        self.add_main_option("show", ord("s"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             _("Show the shelf"), None)
        self.add_main_option("hide", 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             _("Hide the shelf"), None)
        self.add_main_option("quit", ord("q"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
                             _("Quit Draggo"), None)
        self.settings = None
        self.shelf = None
        self.window = None
        self._dragging = False
        self._pending_drops = 0
        self._hide_source = 0

    # -- lifecycle --------------------------------------------------------

    def do_startup(self):
        Adw.Application.do_startup(self)
        # Draggo lives in the background, waiting for drags.
        self.hold()

        self.settings = config.Settings()
        self.shelf = Shelf(config.SHELF_FILE if self.settings["persist"] else None, config.FILES_DIR)
        self.shelf.load()
        self.shelf.connect(self._on_shelf_changed)

        provider = Gtk.CssProvider()
        provider.load_from_string(CSS) if hasattr(provider, "load_from_string") else provider.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self._add_action("drag-begin", self._on_drag_begin)
        self._add_action("drag-end", self._on_drag_end)
        self._add_action("show", lambda *_: self.show_shelf())
        self._add_action("hide", lambda *_: self.hide_shelf())
        self._add_action("toggle", lambda *_: self.toggle_shelf())
        self._add_action("paste", lambda *_: self.paste(), ["<Control>v"])
        self._add_action("clear", lambda *_: self.shelf.clear(), ["<Control>Delete"])
        self._add_action("about", lambda *_: self._show_about())
        self._add_action("quit", lambda *_: self.quit(), ["<Control>q"])
        self._add_toggle("remove-after-drag")
        self._add_toggle("persist", self._on_persist_changed)
        self.set_accels_for_action("window.close", ["<Control>w", "Escape"])

        self.window = ShelfWindow(self)
        if self.shelf:
            self.show_shelf()

    def do_activate(self):
        self.show_shelf()

    def do_handle_local_options(self, options):
        if options.contains("quit"):
            # Ask a running instance to quit, without starting a new one.
            try:
                bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
                bus.call_sync(config.APP_ID, "/" + config.APP_ID.replace(".", "/"),
                              "org.gtk.Actions", "Activate",
                              GLib.Variant("(sava{sv})", ("quit", [], {})), None,
                              Gio.DBusCallFlags.NO_AUTO_START, -1, None)
            except GLib.Error:
                pass
            return 0
        return -1

    def do_command_line(self, command_line):
        options = command_line.get_options_dict().end().unpack()
        if options.get("background"):
            pass
        elif options.get("hide"):
            self.hide_shelf()
        elif options.get("show"):
            self.show_shelf()
        else:
            self.toggle_shelf()
        return 0

    # -- actions ----------------------------------------------------------

    def _add_action(self, name, callback, accels=None):
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)
        if accels:
            self.set_accels_for_action(f"app.{name}", accels)

    def _add_toggle(self, key, on_change=None):
        action = Gio.SimpleAction.new_stateful(key, None, GLib.Variant.new_boolean(self.settings[key]))

        def on_activate(action, _param):
            value = not action.get_state().get_boolean()
            action.set_state(GLib.Variant.new_boolean(value))
            self.settings[key] = value
            if on_change:
                on_change(value)

        action.connect("activate", on_activate)
        self.add_action(action)

    def _on_persist_changed(self, persist):
        if persist:
            self.shelf.storage_path = config.SHELF_FILE
            self.shelf.save()
        else:
            self.shelf.storage_path = None
            try:
                os.remove(config.SHELF_FILE)
            except OSError:
                pass

    def _show_about(self):
        kwargs = dict(application_name="Draggo", application_icon=config.APP_ID,
                      version=config.VERSION, developer_name="Alberto Susco",
                      comments=_("A temporary shelf for drag and drop"),
                      website=config.WEBSITE, issue_url=config.WEBSITE + "/issues",
                      license_type=Gtk.License.GPL_3_0)
        if hasattr(Adw, "AboutDialog"):
            Adw.AboutDialog(**kwargs).present(self.window)
        else:
            Adw.AboutWindow(transient_for=self.window, **kwargs).present()

    def paste(self):
        clipboard = Gdk.Display.get_default().get_clipboard()
        dnd.read_offer(clipboard, self.shelf, lambda ok: None)

    # -- visibility -------------------------------------------------------

    def show_shelf(self):
        self._cancel_hide()
        self.window.present()

    def hide_shelf(self):
        self._cancel_hide()
        self.window.set_visible(False)

    def toggle_shelf(self):
        if self.window.get_visible():
            self.hide_shelf()
        else:
            self.show_shelf()

    def _on_drag_begin(self, *_args):
        self._dragging = True
        self.show_shelf()

    def _on_drag_end(self, *_args):
        self._dragging = False
        self._schedule_hide(HIDE_DELAY_AFTER_DRAG)

    def begin_drop(self):
        self._pending_drops += 1
        self._cancel_hide()

    def end_drop(self):
        self._pending_drops = max(0, self._pending_drops - 1)
        self._schedule_hide(HIDE_DELAY_WHEN_EMPTIED)

    def _on_shelf_changed(self, shelf):
        if not shelf:
            self._schedule_hide(HIDE_DELAY_WHEN_EMPTIED)

    def _cancel_hide(self):
        if self._hide_source:
            GLib.source_remove(self._hide_source)
            self._hide_source = 0

    def _schedule_hide(self, delay):
        self._cancel_hide()
        self._hide_source = GLib.timeout_add(delay, self._hide_if_idle)

    def _hide_if_idle(self):
        self._hide_source = 0
        if not self.shelf and not self._dragging and not self._pending_drops:
            self.window.set_visible(False)
        return GLib.SOURCE_REMOVE
