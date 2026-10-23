// Draggo GNOME Shell extension.
//
// On Wayland only the compositor knows when a drag and drop operation starts
// in another application. This extension listens for drags and tells the
// Draggo app (over D-Bus, through its exported GActions) to show its shelf.
// It also keeps the shelf window above other windows, on every workspace and
// next to the screen edge.

import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const APP_ID = 'io.github.albertosusco.Draggo';
const APP_PATH = '/io/github/albertosusco/Draggo';

export default class DraggoExtension extends Extension {
    enable() {
        this._settings = this.getSettings();
        this._dragging = false;
        this._notified = false;
        this._showTimeoutId = 0;
        this._focusNextShelf = false;
        this._trackedWindows = new Map();
        this._idleIds = new Set();

        Main.wm.addKeybinding('toggle-shelf', this._settings, Meta.KeyBindingFlags.NONE,
            Shell.ActionMode.NORMAL | Shell.ActionMode.OVERVIEW,
            () => this._onToggleShortcut());

        this._xdndIds = [
            Main.xdndHandler.connect('drag-begin', () => this._onDragBegin()),
            Main.xdndHandler.connect('drag-end', () => this._onDragEnd()),
        ];
        this._windowCreatedId = global.display.connect('window-created',
            (_display, window) => this._onWindowCreated(window));

        for (const actor of global.get_window_actors())
            this._onWindowCreated(actor.meta_window, true);
    }

    disable() {
        Main.wm.removeKeybinding('toggle-shelf');

        for (const id of this._xdndIds)
            Main.xdndHandler.disconnect(id);
        this._xdndIds = null;

        global.display.disconnect(this._windowCreatedId);
        this._windowCreatedId = 0;

        for (const [window, ids] of this._trackedWindows) {
            for (const id of ids)
                window.disconnect(id);
        }
        this._trackedWindows = null;
        for (const window of this._findShelves()) {
            window.unmake_above();
            window.unstick();
        }

        for (const id of this._idleIds)
            GLib.source_remove(id);
        this._idleIds = null;

        if (this._showTimeoutId) {
            GLib.source_remove(this._showTimeoutId);
            this._showTimeoutId = 0;
        }
        this._settings = null;
    }

    _onDragBegin() {
        this._dragging = true;
        if (this._showTimeoutId)
            GLib.source_remove(this._showTimeoutId);

        // A short delay avoids flashing the shelf for tiny accidental drags.
        const delay = Math.max(0, this._settings.get_int('show-delay'));
        this._showTimeoutId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, delay, () => {
            this._showTimeoutId = 0;
            if (this._dragging) {
                this._notified = true;
                this._activateAction('drag-begin');
            }
            return GLib.SOURCE_REMOVE;
        });
    }

    _onDragEnd() {
        this._dragging = false;
        if (this._showTimeoutId) {
            GLib.source_remove(this._showTimeoutId);
            this._showTimeoutId = 0;
        }
        if (this._notified) {
            this._notified = false;
            this._activateAction('drag-end');
        }
    }

    _onToggleShortcut() {
        console.debug('Draggo: toggle shortcut');
        const [shelf] = this._findShelves();
        if (shelf && !shelf.has_focus()) {
            // Visible but not focused: bring it to the user instead of hiding it.
            Main.activateWindow(shelf);
            return;
        }
        // Give the shelf keyboard focus when it appears, so Ctrl+V works.
        this._focusNextShelf = !shelf;
        this._activateAction('toggle');
    }

    _activateAction(name) {
        // Calling the app by its bus name starts it through D-Bus activation
        // if it is not running yet.
        Gio.DBus.session.call(
            APP_ID, APP_PATH, 'org.gtk.Actions', 'Activate',
            new GLib.Variant('(sava{sv})', [name, [], {}]),
            null, Gio.DBusCallFlags.NONE, -1, null,
            (connection, result) => {
                try {
                    connection.call_finish(result);
                } catch (e) {
                    console.warn(`Draggo: cannot reach the Draggo app: ${e.message}`);
                }
            });
    }

    _findShelves() {
        return global.display.list_all_windows().filter(w => this._isDraggoWindow(w));
    }

    _isDraggoWindow(window) {
        return window.get_gtk_application_id?.() === APP_ID ||
            window.get_wm_class() === APP_ID;
    }

    _onWindowCreated(window, alreadyShown = false) {
        if (!window || this._trackedWindows.has(window))
            return;

        if (alreadyShown) {
            if (this._isDraggoWindow(window))
                this._setupWindow(window, false);
            return;
        }

        // A Wayland window does not know its application id yet when it is
        // created; wait until it is shown to find out whether it is ours.
        const ids = [];
        this._trackedWindows.set(window, ids);
        const untrack = () => {
            for (const id of ids)
                window.disconnect(id);
            this._trackedWindows?.delete(window);
        };
        ids.push(window.connect('unmanaged', untrack));
        ids.push(window.connect('shown', () => {
            untrack();
            if (!this._isDraggoWindow(window))
                return;
            // Never restack, move or focus a window from inside a mutter
            // signal handler: doing it while a frame is being painted makes
            // mutter abort, taking the whole session down with it.
            let unmanagedId = 0;
            const sourceId = GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
                this._idleIds.delete(sourceId);
                window.disconnect(unmanagedId);
                this._setupWindow(window, true);
                return GLib.SOURCE_REMOVE;
            });
            this._idleIds.add(sourceId);
            unmanagedId = window.connect('unmanaged', () => {
                window.disconnect(unmanagedId);
                if (this._idleIds?.delete(sourceId))
                    GLib.source_remove(sourceId);
            });
        }));
    }

    _setupWindow(window, place) {
        window.make_above();
        if (this._settings.get_boolean('all-workspaces'))
            window.stick();
        if (place)
            this._placeWindow(window);
        if (place && this._focusNextShelf) {
            this._focusNextShelf = false;
            Main.activateWindow(window);
        }
        // Mapping a window without focus makes GNOME show a
        // "Draggo is ready" notification; the shelf does not need one.
        window.unset_demands_attention?.();
    }

    _placeWindow(window) {
        const monitor = global.display.get_current_monitor();
        const workArea = Main.layoutManager.getWorkAreaForMonitor(monitor);
        const rect = window.get_frame_rect();
        const margin = this._settings.get_int('margin');
        const position = this._settings.get_string('position');

        let x;
        if (position === 'left')
            x = workArea.x + margin;
        else if (position === 'center')
            x = workArea.x + Math.round((workArea.width - rect.width) / 2);
        else
            x = workArea.x + workArea.width - rect.width - margin;
        const y = workArea.y + Math.round((workArea.height - rect.height) / 2);

        window.move_frame(true, x, y);
    }
}
