"""Saves the day's euro exchange rates for the dashboard's EUR button.

Reads the European Central Bank's published euro reference rates (a public file, no key)
and writes data/fx.json: how many US dollars, pounds, zloty and francs one euro buys.
Runs separately from every other script and uses only Python's standard library.

It fails soft: a file that cannot be fetched or read leaves the previous data/fx.json alone,
and the file is rewritten only when the ECB's rates changed, so the history stays quiet."""

import json
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).parent
FX_PATH = ROOT / "data" / "fx.json"
ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
USER_AGENT = "python:ps2-sentiment-tracker-fx:1.0 (+https://github.com/SirNovaTofuBlaster/ps2-sentiment-tracker)"
CURRENCIES = ("USD", "GBP", "PLN", "CHF")   # the ones the price pages use, now or soon
MAX_BYTES = 200_000                         # the real file is about 2 KB
SANE_RATE = (0.01, 1000.0)                  # a rate outside this is a broken file, not a market move


def say(text):
    print(text, flush=True)


def parse_rates(text):
    """{"date": "YYYY-MM-DD", "rates": {code: units per euro}} from the ECB's XML; ValueError if wrong."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f"not XML ({exc})") from None
    day, rates = None, {}
    for cube in root.iter():
        if cube.tag.rsplit("}", 1)[-1] != "Cube":
            continue
        if cube.get("time"):
            day = cube.get("time")
        code, rate = cube.get("currency"), cube.get("rate")
        if code in CURRENCIES and rate:
            try:
                value = float(rate)
            except ValueError:
                raise ValueError(f"{code} has a rate that is not a number") from None
            if not SANE_RATE[0] <= value <= SANE_RATE[1]:
                raise ValueError(f"{code}'s rate {value} is not believable")
            rates[code] = value
    if not day or len(day) != 10 or day[4] != "-" or day[7] != "-":
        raise ValueError("no date in the file")
    missing = [code for code in CURRENCIES if code not in rates]
    if missing:
        raise ValueError(f"no rate for {', '.join(missing)}")
    return {"date": day, "rates": {code: rates[code] for code in CURRENCIES}}


def file_text(parsed):
    data = {"base": "EUR", "source": "European Central Bank euro foreign exchange reference rates",
            "date": parsed["date"], "rates": parsed["rates"]}
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def fetch(url=ECB_URL):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read(MAX_BYTES).decode("utf-8", "replace")


def main(path=FX_PATH, fetcher=fetch):
    try:
        parsed = parse_rates(fetcher())
    except (OSError, ValueError) as exc:
        say(f"The rates were not updated: {exc}.")
        return 0   # an old rate is better than a failed run
    text = file_text(parsed)
    try:
        if path.read_text(encoding="utf-8") == text:
            say(f"The rates of {parsed['date']} are already saved.")
            return 0
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    say(f"Saved the rates of {parsed['date']}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
