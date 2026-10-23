import sys

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")


NO_DISPLAY_OPTIONS = {"-q", "--quit", "-h", "--help", "--help-all", "--help-gapplication"}


def main():
    from gi.repository import Gdk, Gtk  # noqa: F401  (importing Gtk opens the display)

    # Without a display the app would own its D-Bus name but could not
    # create its actions, blocking every later start.
    if Gdk.Display.get_default() is None and not NO_DISPLAY_OPTIONS & set(sys.argv[1:]):
        print("draggo: cannot open the display", file=sys.stderr)
        return 1

    from .application import DraggoApplication
    return DraggoApplication().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
