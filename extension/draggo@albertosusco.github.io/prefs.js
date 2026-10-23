import Adw from 'gi://Adw';
import Gdk from 'gi://Gdk';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Gtk from 'gi://Gtk';

import {ExtensionPreferences} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

const IT = {
    'Shelf': 'Cassetto',
    'Position': 'Posizione',
    'Screen edge where the shelf appears': 'Bordo dello schermo in cui compare il cassetto',
    'Right': 'Destra',
    'Left': 'Sinistra',
    'Center': 'Centro',
    'Distance from the edge': 'Distanza dal bordo',
    'Delay before showing (ms)': 'Ritardo prima di mostrarlo (ms)',
    'Ignores very short drags': 'Ignora i trascinamenti molto brevi',
    'Show on all workspaces': 'Mostra su tutti gli spazi di lavoro',
    'Keyboard shortcut': 'Scorciatoia da tastiera',
    'Show or hide the shelf': 'Mostra o nasconde il cassetto',
    'Disabled': 'Disattivata',
    'Change': 'Modifica',
    'Reset': 'Ripristina',
    'Press the new shortcut': 'Premi la nuova scorciatoia',
    'Esc to cancel, Backspace to disable': 'Esc per annullare, Backspace per disattivarla',
};
const italian = GLib.get_language_names()[0].toLowerCase().startsWith('it');
const _ = s => (italian && IT[s]) || s;

const POSITIONS = ['right', 'left', 'center'];

export default class DraggoPreferences extends ExtensionPreferences {
    fillPreferencesWindow(window) {
        const settings = this.getSettings();
        const page = new Adw.PreferencesPage();
        const group = new Adw.PreferencesGroup({title: _('Shelf')});
        page.add(group);

        const position = new Adw.ComboRow({
            title: _('Position'),
            subtitle: _('Screen edge where the shelf appears'),
            model: Gtk.StringList.new([_('Right'), _('Left'), _('Center')]),
        });
        position.selected = Math.max(0, POSITIONS.indexOf(settings.get_string('position')));
        position.connect('notify::selected',
            () => settings.set_string('position', POSITIONS[position.selected]));
        group.add(position);

        const margin = Adw.SpinRow.new_with_range(0, 200, 1);
        margin.title = _('Distance from the edge');
        settings.bind('margin', margin, 'value', Gio.SettingsBindFlags.DEFAULT);
        group.add(margin);

        const delay = Adw.SpinRow.new_with_range(0, 2000, 50);
        delay.title = _('Delay before showing (ms)');
        delay.subtitle = _('Ignores very short drags');
        settings.bind('show-delay', delay, 'value', Gio.SettingsBindFlags.DEFAULT);
        group.add(delay);

        const sticky = new Adw.SwitchRow({title: _('Show on all workspaces')});
        settings.bind('all-workspaces', sticky, 'active', Gio.SettingsBindFlags.DEFAULT);
        group.add(sticky);

        const shortcuts = new Adw.PreferencesGroup({title: _('Keyboard shortcut')});
        page.add(shortcuts);
        shortcuts.add(this._shortcutRow(window, settings));

        window.add(page);
    }

    _shortcutRow(window, settings) {
        const row = new Adw.ActionRow({title: _('Show or hide the shelf')});
        const label = new Gtk.ShortcutLabel({
            disabled_text: _('Disabled'),
            valign: Gtk.Align.CENTER,
        });
        const update = () => {
            label.accelerator = settings.get_strv('toggle-shelf')[0] ?? '';
        };
        settings.connect('changed::toggle-shelf', update);
        update();

        const change = new Gtk.Button({label: _('Change'), valign: Gtk.Align.CENTER});
        change.connect('clicked', () => this._captureShortcut(window, settings));
        const reset = new Gtk.Button({
            icon_name: 'edit-undo-symbolic',
            tooltip_text: _('Reset'),
            valign: Gtk.Align.CENTER,
            css_classes: ['flat'],
        });
        reset.connect('clicked', () => settings.reset('toggle-shelf'));

        row.add_suffix(label);
        row.add_suffix(change);
        row.add_suffix(reset);
        return row;
    }

    _captureShortcut(window, settings) {
        const dialog = new Adw.Window({
            transient_for: window,
            modal: true,
            default_width: 360,
            default_height: 180,
            content: new Adw.StatusPage({
                title: _('Press the new shortcut'),
                description: _('Esc to cancel, Backspace to disable'),
                icon_name: 'preferences-desktop-keyboard-shortcuts-symbolic',
            }),
        });
        const controller = new Gtk.EventControllerKey();
        controller.connect('key-pressed', (_c, keyval, keycode, state) => {
            const mods = state & Gtk.accelerator_get_default_mod_mask();
            if (mods === 0 && keyval === Gdk.KEY_Escape) {
                dialog.close();
                return Gdk.EVENT_STOP;
            }
            if (mods === 0 && keyval === Gdk.KEY_BackSpace) {
                settings.set_strv('toggle-shelf', []);
                dialog.close();
                return Gdk.EVENT_STOP;
            }
            if (!Gtk.accelerator_valid(Gdk.keyval_to_lower(keyval), mods))
                return Gdk.EVENT_STOP;
            const accel = Gtk.accelerator_name_with_keycode(null, Gdk.keyval_to_lower(keyval), keycode, mods);
            settings.set_strv('toggle-shelf', [accel]);
            dialog.close();
            return Gdk.EVENT_STOP;
        });
        dialog.add_controller(controller);
        dialog.present();
    }
}
