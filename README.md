# CLDR Locale Viewer

A GTK4/Adwaita application for browsing and comparing Unicode CLDR locale data across locales.

![Screenshot](data/screenshots/screenshot-01.png)

## Features

- Browse CLDR data per locale: date formats, month names, weekdays, currencies, units, time zone names
- Compare two locales side by side (e.g. `sv` vs `en`)
- Highlight missing/empty translations
- Coverage percentage per category
- Language selector (defaults to system locale)
- Search and filter
- Local cache with 24h TTL

## Installation

### Debian/Ubuntu

```bash
# Add repository
curl -fsSL https://yeager.github.io/debian-repo/KEY.gpg | sudo gpg --dearmor -o /usr/share/keyrings/yeager-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/yeager-archive-keyring.gpg] https://yeager.github.io/debian-repo stable main" | sudo tee /etc/apt/sources.list.d/yeager.list
sudo apt update
sudo apt install cldr-viewer
```

### Fedora/RHEL

```bash
sudo dnf config-manager --add-repo https://yeager.github.io/rpm-repo/yeager.repo
sudo dnf install cldr-viewer
```

### From source

```bash
pip install .
cldr-viewer
```

## 🌍 Contributing Translations

This app is translated via Transifex. Help translate it into your language!

**[→ Translate on Transifex](https://app.transifex.com/danielnylander/cldr-viewer/)**

Currently supported: Swedish (sv). More languages welcome!

### For Translators
1. Create a free account at [Transifex](https://www.transifex.com)
2. Join the [danielnylander](https://app.transifex.com/danielnylander/) organization
3. Start translating!

Translations are automatically synced via GitHub Actions.

## License

GPL-3.0-or-later — Daniel Nylander <daniel@danielnylander.se>
