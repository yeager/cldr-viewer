# CLDR Locale Viewer

A GTK4/Adwaita application for visualizing Unicode CLDR locale data completeness.

Find missing or incomplete translations in date formats, currencies, units, time zones, and more.

## Features

- Browse CLDR data per locale: date formats, month names, weekdays, currencies, units, time zone names
- Compare two locales side by side (e.g. `sv` vs `en`)
- Highlight missing/empty translations
- Coverage percentage per category
- Language selector (defaults to system locale)
- Search and filter
- Local cache with 24h TTL

## Install

### From APT repository

```bash
echo "deb https://yeager.github.io/debian-repo stable main" | sudo tee /etc/apt/sources.list.d/yeager.list
sudo apt update && sudo apt install cldr-viewer
```

### From source

```bash
pip install .
cldr-viewer
```

## Data Source

CLDR JSON data from [unicode-org/cldr-json](https://github.com/unicode-org/cldr-json).

## License

GPL-3.0-or-later — see [LICENSE](LICENSE).
