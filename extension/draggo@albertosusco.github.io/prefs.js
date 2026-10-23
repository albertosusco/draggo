import Adw from 'gi://Adw';
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

        window.add(page);
    }
}
