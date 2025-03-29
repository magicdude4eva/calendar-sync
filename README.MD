[paypal]: https://paypal.me/GerdNaschenweng

# 📅 calendar-sync

![GitHub stars](https://img.shields.io/github/stars/magicdude4eva/calendar-sync?style=social)
![Build](https://img.shields.io/badge/build-passing-brightgreen)
![Python](https://img.shields.io/badge/python-3.13-blue)
![GitHub forks](https://img.shields.io/github/forks/magicdude4eva/calendar-sync?style=social)
![GitHub issues](https://img.shields.io/github/issues/magicdude4eva/calendar-sync)
[![GitHub last commit](https://img.shields.io/github/last-commit/magicdude4eva/calendar-sync.svg)](https://github.com/magicdude4eva/calendar-sync/commits/master)
![License](https://img.shields.io/github/license/magicdude4eva/calendar-sync)

> Sync ICS (.ics) feeds (e.g. Müllabfuhr, Feiertage, F1) to your 📆 CalDAV calendar (e.g. mailbox.org) with emoji support, deduplication, Docker, yearly recurring events, and more.

<video src="https://github.com/user-attachments/assets/59d1b6f4-32ad-4133-8826-021ca2ea3030" autoplay muted loop></video>

---
![paypal](https://img.shields.io/badge/PayPal--ffffff.svg?style=social&logo=data%3Aimage%2Fpng%3Bbase64%2CiVBORw0KG...)

___
![paypal](https://img.shields.io/badge/PayPal--ffffff.svg?style=social&logo=data%3Aimage%2Fpng%3Bbase64%2CiVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8%2F9hAAAABHNCSVQICAgIfAhkiAAAAZZJREFUOI3Fkb1PFFEUxX%2F3zcAMswFCw0KQr1BZSKUQYijMFibGkhj9D4zYYAuU0NtZSIiNzRZGamqD%2BhdoJR%2FGhBCTHZ11Pt%2B1GIiEnY0hFNzkFu%2FmnHPPPQ%2Buu%2BTiYGjy0ZPa5N1t0SI5m6mITeP4%2B%2FGP%2Fbccvto8j3cuCsQTSy%2FCzLkdxqkXpoUXJoUXJrkfFTLMwHiDYLrFz897Z3jT6ckdBwsiYDMo0tNOIGuBqS%2Beh7sdAkU2g%2BkBFGkd%2FrtSgD8Z%2BrBxj68MAGG1A9efRhVsXrKMU7Y4cNyGOwtDU28OtrqdUMetldvzFKxCYSHJ4NsJ%2BnRJGexHba7VJ%2FTff4BaQFBjVcbqIEZ1bESYn4PRUcHx2N952awUkOHZedUcWm14%2FtjqjREHawUEsgx6Ajg5%2Bsi7jWqBwA%2BmIrXlo9YHUVTmEP%2F6hOO1Ofiyy3pjo%2BsvBDX%2FZpSakhz4BqvQDvdYvrXQEXZViI5rPpBEOwR2l16vtN7bd9SN3L1WXj%2BjGSnN38rq%2B7VL8xXQOdDF%2F0KvXn8BlbuY%2FvUAHysAAAAASUVORK5CYII%3D)
🍺 **Please support me**: Although all my software is free, it is always appreciated if you can support my efforts on Github with a [contribution via Paypal][paypal] - this allows me to write cool projects like this in my personal time and hopefully help you or your business. 

<video src="https://github.com/user-attachments/assets/59d1b6f4-32ad-4133-8826-021ca2ea3030" autoplay muted loop></video>


___
![paypal](https://img.shields.io/badge/PayPal--ffffff.svg?style=social&logo=data%3Aimage%2Fpng%3Bbase64%2CiVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8%2F9hAAAABHNCSVQICAgIfAhkiAAAAZZJREFUOI3Fkb1PFFEUxX%2F3zcAMswFCw0KQr1BZSKUQYijMFibGkhj9D4zYYAuU0NtZSIiNzRZGamqD%2BhdoJR%2FGhBCTHZ11Pt%2B1GIiEnY0hFNzkFu%2FmnHPPPQ%2Buu%2BTiYGjy0ZPa5N1t0SI5m6mITeP4%2B%2FGP%2Fbccvto8j3cuCsQTSy%2FCzLkdxqkXpoUXJoUXJrkfFTLMwHiDYLrFz897Z3jT6ckdBwsiYDMo0tNOIGuBqS%2Beh7sdAkU2g%2BkBFGkd%2FrtSgD8Z%2BrBxj68MAGG1A9efRhVsXrKMU7Y4cNyGOwtDU28OtrqdUMetldvzFKxCYSHJ4NsJ%2BnRJGexHba7VJ%2FTff4BaQFBjVcbqIEZ1bESYn4PRUcHx2N952awUkOHZedUcWm14%2FtjqjREHawUEsgx6Ajg5%2Bsi7jWqBwA%2BmIrXlo9YHUVTmEP%2F6hOO1Ofiyy3pjo%2BsvBDX%2FZpSakhz4BqvQDvdYvrXQEXZViI5rPpBEOwR2l16vtN7bd9SN3L1WXj%2BjGSnN38rq%2B7VL8xXQOdDF%2F0KvXn8BlbuY%2FvUAHysAAAAASUVORK5CYII%3D)
🍺 **Please support me**: Although all my software is free, it is always appreciated if you can support my efforts on Github with a [contribution via Paypal][paypal] - this allows me to write cool projects like this in my personal time and hopefully help you or your business. 

---

## ✨ Features

- 🔁 Sync multiple ICS feeds to any CalDAV calendar
- 🧠 Deterministic UID generation & deduplication
- 🔁 Automatic expansion of YEARLY recurring events
- 📍 Location-based filtering for region-specific holidays
- 🧹 Optional cleanup of old imported events
- 📅 Supports emoji mapping for event names
- 🛑 Dry run mode to test before writing
- 🐳 Docker support for simple deployment

---

## 🚀 Usage

### Manual

```bash
python src/calendar_sync.py --import
python src/calendar_sync.py --import --dry-run
python src/calendar_sync.py --cleanup
```

### With Docker Compose

First, build the container:

```bash
docker-compose build
```

Then run the sync:

```bash
docker-compose run --rm calendar-sync --import
docker-compose run --rm calendar-sync --import --dry-run
docker-compose run --rm calendar-sync --cleanup
```

---

## 🧰 Manual Installation

```bash
git clone https://github.com/magicdude4eva/calendar-sync.git
cd calendar-sync
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## ⚙️ config.json

```json
{
  "caldav_url": "https://dav-sso.mailbox.org/caldav/...",
  "username": "your@email.com",
  "password": "your-app-password",
  "timezone": "Europe/Vienna",
  "uid_prefix": "ICS-",
  "future_event_limit_days": 365,
  "ics_feeds": [
    {
      "url": "https://example.com/my.ics",
      "emoji_mapping": {
        "Papier": "♻️",
        "default": "📦"
      }
    }
  ]
}
```

---

## 🛠️ How It Works

- Fetches events from each configured ICS feed
- Normalizes dates and checks if the UID exists
- Skips, adds, or replaces events as needed
- Uses emoji mappings to prefix event names
- All-day events are handled properly (no time zone shift)
- Recurring `RRULE:FREQ=YEARLY` events are expanded into individual years
- Events can be filtered by `LOCATION` using `import_locations`

🗺️ For `import_locations`, configure it per feed. For example:

```json
{
  "url": "https://www.feiertage-oesterreich.at/kalender-download/ics/feiertage-oesterreich.ics",
  "import_locations": "K,St,V",
  "emoji_mapping": {
    "§": "🇦🇹",
    "default": "🗓️"
  }
}
```

To discover valid locations, run the sync once and check the logs. Example:
```
INFO: ⏭️ Skipping 'St. Florian' (2025-05-04) due to unmatched location: OÖ
```


---

## 🧪 Dry Run

Add `--dry-run` to see what would happen without making changes:

```bash
docker-compose run --rm calendar-sync --import --dry-run
```

---

## 🗂️ Project Structure

```
calendar-sync/
├── src/
│   ├── calendar_sync.py      # Entry script
│   └── utils.py              # Core sync logic
├── config.json               # Configuration
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## 📷 mailbox.org Setup Guide

### 1. 🔐 Create Application Password  
Go to `Settings → Security → Application Passwords`  
Select **Calendar and Addressbook Client (CalDAV/CardDAV)**  
![Create Application Password](docs/mailbox1_application_password.jpg)

---

### 2. 📅 Create a New Calendar  
Go to the **Calendar** section → click `+ Add new calendar`  
![Create a New Calendar](docs/mailbox2_application_new_calendar.jpg)

---

### 3. 🔗 Get the CalDAV URL  
Right-click your new calendar → `Properties` → Copy the URL  
![Get the CalDAV URL](docs/mailbox3_caldav_url.jpg)

Paste it into `config.json` under `"caldav_url"`

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

## ❤️ Contributing

PRs welcome! File issues or ideas via GitHub.

## Donations are always welcome
[paypal]: https://paypal.me/GerdNaschenweng
:beer: **Please support me**: Although all my software is free, it is always appreciated if you can support my efforts on Github with a [contribution via Paypal][paypal] - this allows me to write cool projects like this in my personal time and hopefully help you or your business. 
```
(CRO)    0xBAdB43af444055c4031B79a76F74895469BA0CD7 (Cronos)
(USDC)   0xBAdB43af444055c4031B79a76F74895469BA0CD7
(ETH)    0xfc316ba7d8dc325250f1adfafafc320ad75d87c0
(BTC)    1Mhq9SY6DzPhs7PNDx7idXFDWsGtyn7GWM
(BNB)    0xfc316ba7d8dc325250f1adfafafc320ad75d87c0
Crypto.com PayString: magicdude$paystring.crypto.com    
```

Go to [Curve.com to add your Crypto.com card to ApplePay](https://www.curve.com/join#DWPXKG6E) and signup to [Crypto.com for a staking and free Crypto debit card](https://crypto.com/app/ref6ayzqvp).

Use [Binance Exchange](https://accounts.binance.com/register?ref=13896895) to trade #altcoins. I also accept old-school **[PayPal](https://paypal.me/GerdNaschenweng)**.

