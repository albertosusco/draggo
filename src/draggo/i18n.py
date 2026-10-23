"""Minimal translation support (English source strings, Italian translation)."""

import os

_IT = {
    "Drop here": "Rilascia qui",
    "Files, links and text wait here until you drag them out again.":
        "File, link e testi restano qui finché non li trascini di nuovo fuori.",
    "Drag all items": "Trascina tutti gli elementi",
    "Remove": "Rimuovi",
    "Open": "Apri",
    "Paste": "Incolla",
    "Clear Shelf": "Svuota cassetto",
    "Remove Items After Dragging Out": "Rimuovi gli elementi dopo averli trascinati",
    "Keep Items Across Restarts": "Conserva gli elementi al riavvio",
    "About Draggo": "Informazioni su Draggo",
    "Quit": "Esci",
    "Main Menu": "Menu principale",
    "Empty": "Vuoto",
    "1 item": "1 elemento",
    "{n} items": "{n} elementi",
    "Text": "Testo",
    "Link": "Link",
    "Image": "Immagine",
    "{n} characters": "{n} caratteri",
    "File not found": "File non trovato",
    "Folder": "Cartella",
    "A temporary shelf for drag and drop": "Un cassetto temporaneo per il drag and drop",
    "Start without showing the shelf": "Avvia senza mostrare il cassetto",
    "Show the shelf": "Mostra il cassetto",
    "Hide the shelf": "Nascondi il cassetto",
    "Quit Draggo": "Chiudi Draggo",
}


def _is_italian():
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var)
        if value:
            return value.split(":")[0].lower().startswith("it")
    return False


_TABLE = _IT if _is_italian() else {}


def _(text):
    return _TABLE.get(text, text)


def n_items(n):
    if n == 0:
        return _("Empty")
    if n == 1:
        return _("1 item")
    return _("{n} items").format(n=n)
