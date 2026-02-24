"""CLDR Locale Viewer — GTK4/Adwaita application."""

import csv
import gettext
import json
import locale
import os
import sys
import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
# Optional desktop notifications
try:
    gi.require_version("Notify", "0.7")
    from gi.repository import Notify as _Notify
    HAS_NOTIFY = True
except (ValueError, ImportError):
    HAS_NOTIFY = False
from gi.repository import Gtk, Adw, GLib, GObject, Gio, Pango, Gdk

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

def _setup_heatmap_css():
    css = b"""
    .heatmap-green { background-color: #26a269; color: white; border-radius: 8px; }
    .heatmap-yellow { background-color: #e5a50a; color: white; border-radius: 8px; }
    .heatmap-orange { background-color: #ff7800; color: white; border-radius: 8px; }
    .heatmap-red { background-color: #c01c28; color: white; border-radius: 8px; }
    .heatmap-gray { background-color: #77767b; color: white; border-radius: 8px; }
    """
    provider = Gtk.CssProvider()
    provider.load_from_data(css)
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

def _heatmap_css_class(pct):
    if pct >= 95: return "heatmap-green"
    elif pct >= 70: return "heatmap-yellow"
    elif pct >= 40: return "heatmap-orange"
    elif pct > 0: return "heatmap-red"
    return "heatmap-gray"

CATEGORY_LABELS = {
    "dates": _("Date Formats"),
    "dateFields": _("Date Fields"),
    "currencies": _("Currencies"),
    "units": _("Units"),
    "timeZoneNames": _("Time Zone Names"),
    "languages": _("Language Names"),
    "territories": _("Territory Names"),
}

import json as _json
import platform as _platform
from pathlib import Path as _Path

_NOTIFY_APP = "cldr-viewer"

def _notify_config_path():
    return _Path(GLib.get_user_config_dir()) / _NOTIFY_APP / "notifications.json"

def _load_notify_config():
    try:
        return _json.loads(_notify_config_path().read_text())
    except Exception:
        return {"enabled": False}

def _save_notify_config(config):
    p = _notify_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_json.dumps(config))

def _send_notification(summary, body="", icon="dialog-information"):
    if HAS_NOTIFY and _load_notify_config().get("enabled"):
        try:
            n = _Notify.Notification.new(summary, body, icon)
            n.show()
        except Exception:
            pass

def _get_system_info():
    return "\n".join([
        f"App: CLDR Locale Viewer",
        f"Version: {"0.1.2"}",
        f"GTK: {Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}",
        f"Adw: {Adw.get_major_version()}.{Adw.get_minor_version()}.{Adw.get_micro_version()}",
        f"Python: {_platform.python_version()}",
        f"OS: {_platform.system()} {_platform.release()} ({_platform.machine()})",
    ])

class CldrViewerWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(default_width=900, default_height=700, **kwargs)
        self.set_title(_("CLDR Locale Viewer"))
        self.set_default_size(1100, 750)

        _setup_heatmap_css()
        self._locales = []
        self._current_locale = ""
        self._compare_locale = ""
        self._current_category = "dates"
        self._filter_text = ""

        # Main layout
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        # Status bar
        self._status_bar = Gtk.Label(label="", halign=Gtk.Align.START,
                                     margin_start=12, margin_end=12, margin_bottom=4)
        self._status_bar.add_css_class("dim-label")
        self._status_bar.add_css_class("caption")
        vbox.append(self._status_bar)

        self.set_content(vbox)

        # Header bar
        header = Adw.HeaderBar()
        vbox.append(header)

        # Clear cache button
        # Menu
        menu = Gio.Menu()
        about_section = Gio.Menu()
        about_section.append(_("About"), "app.about")
        notif_section = Gio.Menu()
        notif_section.append(_("Toggle Notifications"), "app.toggle-notifications")
        menu.append_section(None, notif_section)
        menu.append_section(None, about_section)
        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu)
        header.pack_end(menu_btn)

        # Theme toggle
        self._theme_btn = Gtk.Button(icon_name="weather-clear-night-symbolic",
                                     tooltip_text="Toggle dark/light theme")
        self._theme_btn.connect("clicked", self._on_theme_toggle)
        header.pack_end(self._theme_btn)

        export_btn = Gtk.Button(icon_name="document-save-symbolic")
        export_btn.set_tooltip_text(_("Export data"))
        export_btn.connect("clicked", self._on_export_clicked)
        header.pack_end(export_btn)

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

        # Overview heatmap (all categories)
        self._overview_flow = Gtk.FlowBox()
        self._overview_flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self._overview_flow.set_homogeneous(True)
        self._overview_flow.set_min_children_per_line(3)
        self._overview_flow.set_max_children_per_line(7)
        self._overview_flow.set_column_spacing(6)
        self._overview_flow.set_row_spacing(6)
        content.append(self._overview_flow)

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

        # Send notification if coverage is low
        for cat_name, cat_info in coverage.items():
            if 0 < cat_info.get("percent", 100) < 50:
                _send_notification(
                    _("CLDR: Low coverage"),
                    _("{cat} coverage is {pct}%").format(cat=cat_name, pct=cat_info["percent"]),
                    "cldr-viewer")
                break

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

        # Overview heatmap cells
        while True:
            child = self._overview_flow.get_first_child()
            if child is None:
                break
            self._overview_flow.remove(child)
        for cat, info in coverage.items():
            pct_val = info["percent"]
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            box.set_size_request(140, 60)
            box.add_css_class(_heatmap_css_class(pct_val))
            box.set_margin_start(4)
            box.set_margin_end(4)
            box.set_margin_top(4)
            box.set_margin_bottom(4)
            cat_lbl = Gtk.Label(label=CATEGORY_LABELS.get(cat, cat))
            cat_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            cat_lbl.set_max_width_chars(18)
            cat_lbl.set_margin_top(6)
            cat_lbl.set_margin_start(6)
            cat_lbl.set_margin_end(6)
            box.append(cat_lbl)
            pct_lbl = Gtk.Label(label=f"{pct_val}%")
            pct_lbl.set_margin_bottom(6)
            box.append(pct_lbl)
            box.set_tooltip_text(f"{CATEGORY_LABELS.get(cat, cat)}: {info['present']}/{info['total']}")
            self._overview_flow.append(box)

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

    def _on_export_clicked(self, *_args):
        dialog = Adw.MessageDialog(transient_for=self,
                                   heading=_("Export Data"),
                                   body=_("Choose export format:"))
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("csv", "CSV")
        dialog.add_response("json", "JSON")
        dialog.set_response_appearance("csv", Adw.ResponseAppearance.SUGGESTED)
        dialog.connect("response", self._on_export_format_chosen)
        dialog.present()

    def _on_export_format_chosen(self, dialog, response):
        if response not in ("csv", "json"):
            return
        self._export_fmt = response
        fd = Gtk.FileDialog()
        fd.set_initial_name(f"cldr-export.{response}")
        fd.save(self, None, self._on_export_save)

    def _on_export_save(self, dialog, result):
        try:
            path = dialog.save_finish(result).get_path()
        except Exception:
            return
        data = []
        for i in range(self._list_store.get_n_items()):
            item = self._list_store.get_item(i)
            data.append({"key": item.key, "value": item.value,
                         "reference": item.compare, "missing": item.missing})
        if not data:
            return
        if self._export_fmt == "csv":
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=data[0].keys())
                w.writeheader()
                w.writerows(data)
        else:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    def _on_clear_cache(self, btn):
        clear_cache()
        self._refresh_data()

    def _on_theme_toggle(self, _btn):
        sm = Adw.StyleManager.get_default()
        if sm.get_color_scheme() == Adw.ColorScheme.FORCE_DARK:
            sm.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
            self._theme_btn.set_icon_name("weather-clear-night-symbolic")
        else:
            sm.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
            self._theme_btn.set_icon_name("weather-clear-symbolic")

    def _update_status_bar(self):
        self._status_bar.set_text("Last updated: " + _dt_now.now().strftime("%Y-%m-%d %H:%M"))

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
        GLib.set_application_name(_("CLDR Locale Viewer"))
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        if HAS_NOTIFY:
            _Notify.init("cldr-viewer")
        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self._on_about)
        self.add_action(about_action)

        export_action = Gio.SimpleAction.new("export", None)
        export_action.connect("activate", lambda *_: self.props.active_window and self.props.active_window._on_export_clicked())
        self.add_action(export_action)
        self.set_accels_for_action("app.export", ["<Control>e"])

        notif_action = Gio.SimpleAction.new("toggle-notifications", None)
        notif_action.connect("activate", lambda *_: _save_notify_config({"enabled": not _load_notify_config().get("enabled", False)}))
        self.add_action(notif_action)

    def do_startup(self):
        Adw.Application.do_startup(self)
        self.set_accels_for_action("app.quit", ["<Control>q"])
        self.set_accels_for_action("app.refresh", ["F5"])
        self.set_accels_for_action("app.shortcuts", ["<Control>slash"])
        for n, cb in [("quit", lambda *_: self.quit()),
                      ("refresh", lambda *_: self._do_refresh()),
                      ("shortcuts", self._show_shortcuts_window)]:
            a = Gio.SimpleAction.new(n, None); a.connect("activate", cb); self.add_action(a)

    def _do_refresh(self):
        w = self.get_active_window()
        if w and hasattr(w, '_trigger_status_update'): w._trigger_status_update()

    def _show_shortcuts_window(self, *_args):
        win = Gtk.ShortcutsWindow(transient_for=self.get_active_window(), modal=True)
        section = Gtk.ShortcutsSection(visible=True, max_height=10)
        group = Gtk.ShortcutsGroup(visible=True, title="General")
        for accel, title in [("<Control>q", "Quit"), ("F5", "Refresh"), ("<Control>slash", "Keyboard shortcuts")]:
            s = Gtk.ShortcutsShortcut(visible=True, accelerator=accel, title=title)
            group.append(s)
        section.append(group)
        win.add_child(section)
        win.present()

    def do_activate(self):
        win = CldrViewerWindow(application=self)
        win.present()

    def _on_about(self, *_args):
        about = Adw.AboutDialog(
            application_name=_("CLDR Locale Viewer"),
            application_icon="cldr-viewer",
            version="0.1.2",
            developer_name="Daniel Nylander",
            developers=["Daniel Nylander <daniel@danielnylander.se>"],
            copyright="© 2026 Daniel Nylander",
            license_type=Gtk.License.GPL_3_0,
            website="https://github.com/yeager/cldr-viewer",
            issue_url="https://github.com/yeager/cldr-viewer/issues",
            translator_credits=_("Translate this app: https://www.transifex.com/danielnylander/cldr-viewer/"),
            comments=_("Browse and compare Unicode CLDR locale data"),
        )
        about.set_debug_info(_get_system_info())
        about.set_debug_info_filename("cldr-viewer-debug.txt")
        about.add_link(_("Help translate"), "https://app.transifex.com/danielnylander/cldr-viewer/")

        about.present(self.props.active_window)

def main():
    app = CldrViewerApp()
    app.run(sys.argv)

if __name__ == "__main__":
    main()
