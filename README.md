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

## 🌍 Contributing Translations

Help translate this app into your language! All translations are managed via Transifex.

**→ [Translate on Transifex](https://app.transifex.com/danielnylander/cldr-viewer/)**

### How to contribute:
1. Visit the [Transifex project page](https://app.transifex.com/danielnylander/cldr-viewer/)
2. Create a free account (or log in)
3. Select your language and start translating

### Currently supported languages:
Arabic, Czech, Danish, German, Spanish, Finnish, French, Italian, Japanese, Korean, Norwegian Bokmål, Dutch, Polish, Brazilian Portuguese, Russian, Swedish, Ukrainian, Chinese (Simplified)

### Notes:
- Please do **not** submit pull requests with .po file changes — they are synced automatically from Transifex
- Source strings are pushed to Transifex daily via GitHub Actions
- Translations are pulled back and included in releases

New language? Open an [issue](https://github.com/yeager/cldr-viewer/issues) and we'll add it!