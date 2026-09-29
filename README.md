# ps2-sentiment-tracker
Retro gaming sentiment tracking.

`scraper.py` pulls gaming news and Reddit RSS feeds, fuzzy-matches headlines against the PS2 library,
flags remaster/remake chatter and scores sentiment. Results go to `data/sentiment_feed.json`, which
`index.html` renders as a dashboard. A GitHub Actions workflow reruns the scraper every 6 hours.

## Run locally

```sh
pip install -r requirements.txt
python scraper.py
python -m http.server  # then open http://localhost:8000
```
