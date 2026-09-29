import json
import os
import re
from datetime import datetime
import feedparser
from thefuzz import process

# Global list of worldwide gaming RSS feeds (Japanese, European, North American magazines & aggregators)
RSS_FEEDS = [
    "https://www.gematsu.com/feed",
    "https://www.eurogamer.net/feed",
    "https://nintendoeverything.com/feed",  # General, but good for retro
    "https://www.timeextension.com/feed",  # Retro gaming focus
    "https://www.reddit.com/r/ps2/.rss",
    "https://www.reddit.com/r/emulation/.rss",
]

REMASTER_KEYWORDS = [
    "remaster",
    "remake",
    "reboot",
    "collection",
    "port",
    "hd version",
    "revival",
    "return",
]


def load_ps2_database():
  db_path = "data/ps2_database.json"
  if os.path.exists(db_path):
    try:
      with open(db_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        if data:  # Make sure it's not empty
          return data
    except json.JSONDecodeError:
      print("Warning: ps2_database.json is empty or invalid. Using fallback list.")

  # Fallback starter list
  return [
      {"id": 1, "title": ".hack//Infection", "region": "Global"},
      {"id": 2, "title": ".hack//Mutation", "region": "Global"},
      {"id": 3, "title": ".hack//Outbreak", "region": "Global"},
      {"id": 4, "title": ".hack//Quarantine", "region": "Global"},
      {"id": 5, "title": "Silent Hill 2", "region": "Global"},
      {"id": 6, "title": "Metal Gear Solid 2: Sons of Liberty", "region": "Global"},
      {
          "id": 7,
          "title": "Grand Theft Auto: San Andreas",
          "region": "Global",
      },
      {"id": 8, "title": "Shadow of the Colossus", "region": "Global"},
      {"id": 9, "title": "Persona 4", "region": "Global"},
      {"id": 10, "title": "Okami", "region": "Global"},
  ]


def analyze_sentiment(text):
  text_lower = text.lower()
  positive_words = [
      "masterpiece",
      "amazing",
      "love",
      "best",
      "classic",
      "brilliant",
      "hype",
      "return",
      "remaster",
  ]
  negative_words = ["bug", "worst", "broken", "terrible", "flop", "disaster"]

  score = 50  # Neutral baseline
  for word in positive_words:
    if word in text_lower:
      score += 10
  for word in negative_words:
    if word in text_lower:
      score -= 15

  return max(10, min(100, score))


def run_scraper():
  ps2_db = load_ps2_database()
  game_titles = [game["title"] for game in ps2_db]

  collected_items = []

  print(f"Fetching feeds from {len(RSS_FEEDS)} sources...")
  for url in RSS_FEEDS:
    try:
      feed = feedparser.parse(url)
      for entry in feed.entries[:15]:  # Top 15 per feed
        title = entry.get("title", "")
        link = entry.get("link", "#")
        published = entry.get(
            "published", datetime.now().strftime("%Y-%m-%d %H:%M")
        )

        # Fuzzy match title against PS2 database
        match, score = process.extractOne(title, game_titles)

        # If confidence score is high enough, link it to a PS2 game
        matched_game = None
        if score > 75:
          matched_game = match

        # Check for remaster / revival flags
        is_remaster = any(kw in title.lower() for kw in REMASTER_KEYWORDS)

        sentiment = analyze_sentiment(title)

        collected_items.append({
            "headline": title,
            "source": feed.feed.get("title", "Global Feed"),
            "link": link,
            "matched_game": matched_game,
            "match_score": score if score > 75 else 0,
            "is_remaster_rumor": is_remaster,
            "sentiment": sentiment,
            "timestamp": published,
        })
    except Exception as e:
      print(f"Error parsing {url}: {e}")

  # Save results to output json for GitHub Pages dashboard
  output_data = {
      "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
      "total_tracked_feeds": len(RSS_FEEDS),
      "items": collected_items,
  }

  os.makedirs("data", exist_ok=True)
  with open("data/sentiment_feed.json", "w", encoding="utf-8") as f:
    json.dump(output_data, f, indent=2)
  print(
      f"Successfully scraped and saved {len(collected_items)} items to"
      " data/sentiment_feed.json"
  )


if __name__ == "__main__":
  run_scraper()
