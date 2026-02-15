"""CLDR Locale Viewer — GTK4/Adwaita application."""

import gettext
import locale
import os
import sys
import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, GObject, Gio, Pango

from cldr_viewer.cldr_data import (
    get_available_locales,
    get_flat_category,
    compute_coverage,
    clear_cache,
    CLDR_PACKAGES,
)

# i18n
TEXTDOMAIN = "cldr-viewer"
localedir = os.path.join(os.path.dirname(__file__), "..", "..", "locale")
if not os.path.isdir(localedir):
    localedir = "/usr/share/locale"
gettext.bindtextdomain(TEXTDOMAIN, localedir)
gettext.textdomain(TEXTDOMAIN)
_ = gettext.gettext


CATEGORY_LABELS = {
    "dates": _("Date Formats"),
    "dateFields": _("Date Fields"),
    "currencies": _("Currencies"),
    "units": _("Units"),
    "timeZoneNames": _("Time Zone Names"),
    "languages": _("Language Names"),
    "territories": _("Territory Names"),
}


class CldrViewerWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(default_width=900, default_height=700, **kwargs)
        self.set_title(_("CLDR Locale Viewer"))
        self.set_default_size(1100, 750)

        self._locales = []
        self._current_locale = ""
        self._compare_locale = ""
        self._current_category = "dates"
        self._filter_text = ""

        # Main layout
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(vbox)

        # Header bar
        header = Adw.HeaderBar()
        vbox.append(header)

        # Clear cache button
        clear_btn = Gtk.Button(icon_name="edit-clear-all-symbolic")
        clear_btn.set_tooltip_text(_("Clear cache"))
        clear_btn.connect("clicked", self._on_clear_cache)
        header.pack_end(clear_btn)

        # Content
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        content.set_margin_start(12)
        content.set_margin_end(12)
        vbox.append(content)

        # Controls row
        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        content.append(controls)

        # Locale dropdown
        controls.append(Gtk.Label(label=_("Locale:")))
        self._locale_dropdown = Gtk.DropDown()
        self._locale_dropdown.set_hexpand(False)
        controls.append(self._locale_dropdown)

        # Compare dropdown
        controls.append(Gtk.Label(label=_("Compare with:")))
        self._compare_dropdown = Gtk.DropDown()
        self._compare_dropdown.set_hexpand(False)
        controls.append(self._compare_dropdown)

        # Category dropdown
        controls.append(Gtk.Label(label=_("Category:")))
        self._cat_model = Gtk.StringList()
        for cat in CLDR_PACKAGES:
            self._cat_model.append(CATEGORY_LABELS.get(cat, cat))
        self._cat_dropdown = Gtk.DropDown(model=self._cat_model)
        self._cat_dropdown.connect("notify::selected", self._on_category_changed)
        controls.append(self._cat_dropdown)

        # Search
        self._search_entry = Gtk.SearchEntry()
        self._search_entry.set_placeholder_text(_("Filter keys…"))
        self._search_entry.set_hexpand(True)
        self._search_entry.connect("search-changed", self._on_search_changed)
        controls.append(self._search_entry)

        # Coverage bar
        self._coverage_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        content.append(self._coverage_box)
        self._coverage_label = Gtk.Label(label="")
        self._coverage_label.add_css_class("heading")
        self._coverage_box.append(self._coverage_label)
        self._coverage_bar = Gtk.ProgressBar()
        self._coverage_bar.set_hexpand(True)
        self._coverage_bar.set_valign(Gtk.Align.CENTER)
        self._coverage_box.append(self._coverage_bar)

        # Overview (all categories)
        self._overview_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        content.append(self._overview_box)

        # Scrolled data view
        sw = Gtk.ScrolledWindow()
        sw.set_vexpand(True)
        content.append(sw)

        # ColumnView for data
        self._list_store = Gio.ListStore(item_type=KeyValueItem)
        self._filter_model = Gtk.FilterListModel(model=self._list_store)
        self._custom_filter = Gtk.CustomFilter.new(self._filter_func)
        self._filter_model.set_filter(self._custom_filter)
        sel = Gtk.NoSelection(model=self._filter_model)

        self._column_view = Gtk.ColumnView(model=sel)
        self._column_view.add_css_class("data-table")

        # Key column
        col_key = Gtk.ColumnViewColumn(title=_("Key"))
        factory_key = Gtk.SignalListItemFactory()
        factory_key.connect("setup", self._setup_label)
        factory_key.connect("bind", self._bind_key)
        col_key.set_factory(factory_key)
        col_key.set_expand(True)
        self._column_view.append_column(col_key)

        # Value column
        col_val = Gtk.ColumnViewColumn(title=_("Value"))
        factory_val = Gtk.SignalListItemFactory()
        factory_val.connect("setup", self._setup_label)
        factory_val.connect("bind", self._bind_value)
        col_val.set_factory(factory_val)
        col_val.set_expand(True)
        self._column_view.append_column(col_val)

        # Compare column
        self._col_compare = Gtk.ColumnViewColumn(title=_("Reference"))
        factory_cmp = Gtk.SignalListItemFactory()
        factory_cmp.connect("setup", self._setup_label)
        factory_cmp.connect("bind", self._bind_compare)
        self._col_compare.set_factory(factory_cmp)
        self._col_compare.set_expand(True)
        self._column_view.append_column(self._col_compare)

        # Status column
        col_status = Gtk.ColumnViewColumn(title=_("Status"))
        factory_status = Gtk.SignalListItemFactory()
        factory_status.connect("setup", self._setup_label)
        factory_status.connect("bind", self._bind_status)
        col_status.set_factory(factory_status)
        self._column_view.append_column(col_status)

        sw.set_child(self._column_view)

        # Spinner for loading
        self._spinner = Gtk.Spinner()
        self._spinner.set_halign(Gtk.Align.CENTER)
        self._spinner.set_valign(Gtk.Align.CENTER)

        # Load locales
        self._load_locales()

    def _load_locales(self):
        """Fetch locale list in background."""
        def do_fetch():
            locales = get_available_locales()
            GLib.idle_add(self._on_locales_loaded, locales)
        threading.Thread(target=do_fetch, daemon=True).start()

    def _on_locales_loaded(self, locales):
        self._locales = locales

        model = Gtk.StringList()
        for loc in locales:
            model.append(loc)

        self._locale_dropdown.set_model(model)
        self._compare_dropdown.set_model(model)

        # Default: system locale or sv
        sys_locale = locale.getdefaultlocale()[0] or "sv"
        sys_lang = sys_locale.split("_")[0]
        default_idx = 0
        en_idx = 0
        for i, loc in enumerate(locales):
            if loc == sys_lang:
                default_idx = i
            if loc == "en":
                en_idx = i

        self._locale_dropdown.set_selected(default_idx)
        self._compare_dropdown.set_selected(en_idx)

        self._locale_dropdown.connect("notify::selected", self._on_locale_changed)
        self._compare_dropdown.connect("notify::selected", self._on_locale_changed)

        self._refresh_data()

    def _on_locale_changed(self, dropdown, _pspec):
        self._refresh_data()

    def _on_category_changed(self, dropdown, _pspec):
        self._refresh_data()

    def _on_search_changed(self, entry):
        self._filter_text = entry.get_text().lower()
        self._custom_filter.changed(Gtk.FilterChange.DIFFERENT)

    def _filter_func(self, item):
        if not self._filter_text:
            return True
        text = self._filter_text
        return text in item.key.lower() or text in item.value.lower() or text in item.compare.lower()

    def _refresh_data(self):
        """Reload data for current selection."""
        idx = self._locale_dropdown.get_selected()
        cmp_idx = self._compare_dropdown.get_selected()
        cat_idx = self._cat_dropdown.get_selected()

        if idx == Gtk.INVALID_LIST_POSITION or not self._locales:
            return

        loc = self._locales[idx]
        cmp = self._locales[cmp_idx] if cmp_idx != Gtk.INVALID_LIST_POSITION else "en"
        cats = list(CLDR_PACKAGES.keys())
        cat = cats[cat_idx] if cat_idx < len(cats) else "dates"

        self._current_locale = loc
        self._compare_locale = cmp
        self._current_category = cat

        def do_load():
            loc_data = get_flat_category(loc, cat)
            cmp_data = get_flat_category(cmp, cat)
            coverage = compute_coverage(loc, cmp)
            GLib.idle_add(self._update_view, loc_data, cmp_data, coverage, cat)

        threading.Thread(target=do_load, daemon=True).start()

    def _update_view(self, loc_data, cmp_data, coverage, category):
        self._list_store.remove_all()

        all_keys = sorted(set(list(loc_data.keys()) + list(cmp_data.keys())))
        for key in all_keys:
            val = loc_data.get(key, "")
            cmp_val = cmp_data.get(key, "")
            missing = key in cmp_data and (key not in loc_data or not loc_data[key].strip())
            item = KeyValueItem(key=key, value=val, compare=cmp_val, missing=missing)
            self._list_store.append(item)

        # Update coverage
        cat_cov = coverage.get(category, {})
        pct = cat_cov.get("percent", 0)
        total = cat_cov.get("total", 0)
        present = cat_cov.get("present", 0)
        self._coverage_label.set_text(
            _("Coverage: {percent}% ({present}/{total})").format(
                percent=pct, present=present, total=total
            )
        )
        self._coverage_bar.set_fraction(pct / 100.0)

        # Overview chips
        while self._overview_box.get_first_child():
            self._overview_box.remove(self._overview_box.get_first_child())
        for cat, info in coverage.items():
            label = Gtk.Label(
                label=f"{CATEGORY_LABELS.get(cat, cat)}: {info['percent']}%"
            )
            if info["percent"] >= 95:
                label.add_css_class("success")
            elif info["percent"] >= 70:
                label.add_css_class("warning")
            else:
                label.add_css_class("error")
            frame = Gtk.Frame()
            frame.set_child(label)
            label.set_margin_start(6)
            label.set_margin_end(6)
            label.set_margin_top(2)
            label.set_margin_bottom(2)
            self._overview_box.append(frame)

    def _setup_label(self, factory, list_item):
        label = Gtk.Label(xalign=0)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_selectable(True)
        list_item.set_child(label)

    def _bind_key(self, factory, list_item):
        item = list_item.get_item()
        label = list_item.get_child()
        label.set_text(item.key)
        if item.missing:
            label.add_css_class("error")
        else:
            label.remove_css_class("error")

    def _bind_value(self, factory, list_item):
        item = list_item.get_item()
        label = list_item.get_child()
        label.set_text(item.value)
        if item.missing:
            label.set_text(_("⚠ MISSING"))
            label.add_css_class("error")
        else:
            label.remove_css_class("error")

    def _bind_compare(self, factory, list_item):
        item = list_item.get_item()
        label = list_item.get_child()
        label.set_text(item.compare)

    def _bind_status(self, factory, list_item):
        item = list_item.get_item()
        label = list_item.get_child()
        if item.missing:
            label.set_text("❌")
        elif item.value == item.compare and item.value:
            label.set_text("⚠️")  # Same as reference — possibly untranslated
        else:
            label.set_text("✅")

    def _on_clear_cache(self, btn):
        clear_cache()
        self._refresh_data()


class KeyValueItem(GObject.Object):
    """List item for the column view."""
    __gtype_name__ = "KeyValueItem"

    def __init__(self, key="", value="", compare="", missing=False):
        super().__init__()
        self.key = key
        self.value = value
        self.compare = compare
        self.missing = missing


class CldrViewerApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="se.danielnylander.cldr-viewer",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )

    def do_activate(self):
        win = CldrViewerWindow(application=self)
        win.present()


def main():
    app = CldrViewerApp()
    app.run(sys.argv)


if __name__ == "__main__":
    main()
