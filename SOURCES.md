# Sources

Every source the scraper reads lives in [`feeds.json`](feeds.json). This page is the ranked snapshot behind it: who each source is, how big it is and whether it starts switched on. Switch sources on or off, add new ones or change weights in the dashboard's **Sources & Weights** panel (step by step: the dashboard's **How to use** page, `guide.html`; how it works and why these choices were made: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)).

- Numbers were measured on **2026-09-30**, directly from YouTube (public subscriber count, which YouTube rounds, and exact total views) and Apple Podcasts (number of US ratings and the Video Games chart rank in the US and UK). They are a snapshot, not live numbers.
- *Last upload / Last episode* is the newest item in the source's own feed on that date. The live state of every feed (active, quiet, stale or failing) is shown in the dashboard from `data/feed_status.json`.
- *Default* is the `enabled` value in feeds.json. A recommended source that published nothing for 120+ days starts off, and the *Note* column says why anything else is off.

## At a glance

| Type | In feeds.json | On by default |
|---|---:|---:|
| News sites | 18 | 18 |
| Subreddits | 26 | 26 |
| YouTube channels | 159 | 114 |
| Podcasts | 91 | 64 |
| **Total** | **294** | **222** |

## YouTube

Each channel is read through its public feed `https://www.youtube.com/feeds/videos.xml?channel_id=<channel id>` (latest 15 uploads, Shorts included), so no API key is needed.

### Biggest gaming channels, by subscribers

Built from Playboard's all-time top-20 gaming channels, Wikipedia's most-subscribed list and other well-known gaming channels, then re-measured. Most of the biggest channels are non-English or Minecraft/Roblox/Fortnite-focused, which says little about PS2 games (and the keyword sentiment is English-only), so they are listed but start off.

| # | Channel | Subscribers | Total views | Last upload | Default | Note |
|---:|---|---:|---:|---|---|---|
| 1 | [PewDiePie](https://www.youtube.com/channel/UC-lHJZR3Gqxm24_Vd_AJ5Yw) | 109M | 29,539,115,521 | 2026-09-22 | off | Latest upload (2026-09-22) is titled 'Thank you and Goodbye.'; vlog content. |
| 2 | [PANDA BOI](https://www.youtube.com/channel/UC0Wju2yvRlfwqraLlz5152Q) | 62.4M | 27,523,106,815 | 2026-09-27 | off | Shorts-only channel. |
| 3 | [IShowSpeed](https://www.youtube.com/channel/UCWsDFcIhY2DBi3GB5uykGXA) | 61.5M | 10,999,344,361 | 2026-09-27 | off | IRL streaming, not game coverage. |
| 4 | [MrBeast Gaming](https://www.youtube.com/channel/UCIPPMRA040LQr5QPyJEbmXA) | 60.2M | 11,870,384,091 | 2026-09-26 | off | Mostly Minecraft/Roblox/Fortnite; rarely relevant to PS2. |
| 5 | [Mikecrack](https://www.youtube.com/channel/UCqJ5zFEED1hWs0KNQCQuYdQ) | 58.7M | 22,128,146,846 | 2026-08-31 | off | Non-English; keyword sentiment is English-only. |
| 6 | [JuegaGerman](https://www.youtube.com/channel/UCYiGq8XF7YQD00x7wAd62Zg) | 56.7M | 19,112,131,575 | 2026-09-29 | off | Non-English; keyword sentiment is English-only. |
| 7 | [Jess No Limit](https://www.youtube.com/channel/UCvh1at6xpV1ytYOAzxmqUsA) | 54.6M | 7,347,899,526 | 2026-09-25 | off | Non-English; keyword sentiment is English-only. |
| 8 | [Techno Gamerz](https://www.youtube.com/channel/UCX8pnu3DYUnx8qy8V_c6oHg) | 53.2M | 16,540,772,451 | 2026-09-16 | off | Non-English; keyword sentiment is English-only. |
| 9 | [BETER BÖCÜK](https://www.youtube.com/channel/UC6gVx_vALsYT-z_u1djJbBQ) | 51.9M | 16,499,633,308 | 2026-09-30 | off | Non-English; keyword sentiment is English-only. |
| 10 | [Fernanfloo](https://www.youtube.com/channel/UCV4xOVpbcV8SdueDCOxLXtQ) | 50.7M | 11,170,932,725 | 2026-09-27 | off | Non-English; keyword sentiment is English-only. |
| 11 | [AboFlah](https://www.youtube.com/channel/UCqq5n-Oe-r1EEHI3yvhVJcA) | 50.6M | 9,354,123,897 | 2026-09-28 | off | Non-English; keyword sentiment is English-only. |
| 12 | [Total Gaming](https://www.youtube.com/channel/UC5c9VlYTSvBSCaoMu_GI6gQ) | 45.9M | 5,245,756,396 | 2026-09-26 | off | Non-English; keyword sentiment is English-only. |
| 13 | [TheDonato](https://www.youtube.com/channel/UCaHEdZtk6k7SVP-umnzifmQ) | 43.7M | 8,626,463,986 | 2026-09-27 | off | Non-English; keyword sentiment is English-only. |
| 14 | [LankyBox](https://www.youtube.com/channel/UCSf0s2ogUVYpJPuzW1zpAOg) | 42M | 35,995,331,692 | 2026-02-20 | off | Mostly Minecraft/Roblox/Fortnite; rarely relevant to PS2. |
| 15 | [elrubiusOMG](https://www.youtube.com/channel/UCXazgXDIYyWH-yXLAkcrFxw) | 41M | 8,327,120,060 | 2026-08-27 | off | Non-English; keyword sentiment is English-only. |
| 16 | [Markiplier](https://www.youtube.com/channel/UC7_YxT-KID8kRbqZo7MyscQ) | 38.9M | 23,936,836,519 | 2026-09-24 | on |  |
| 17 | [Dream](https://www.youtube.com/channel/UCTkXRDQl0luXxVQrRQvWS6w) | 34.8M | 4,527,706,943 | 2026-09-19 | off | Mostly Minecraft/Roblox/Fortnite; rarely relevant to PS2. |
| 18 | [VEGETTA777](https://www.youtube.com/channel/UCam8T03EOFBsNdR0thrFHdQ) | 34.7M | 16,482,975,144 | 2026-09-29 | off | Non-English; keyword sentiment is English-only. |
| 19 | [Diosdado Juarez](https://www.youtube.com/channel/UC0gnpMXQFvO9YsRZ_2adXPA) | 32.4M | 27,711,993,635 | 2026-09-30 | off | Non-English; keyword sentiment is English-only. |
| 20 | [BigSchool](https://www.youtube.com/channel/UC-Diq5SjWZDol8C0_E_1Y7A) | 32.4M | 14,863,891,674 | 2026-09-26 | off | Mostly Minecraft/Roblox/Fortnite; rarely relevant to PS2. |
| 21 | [Soy Suco](https://www.youtube.com/channel/UCIpp0Pb8H3K-Htb-WOF9DBw) | 31.3M | 7,164,710,377 | 2026-09-29 | off | Non-English; keyword sentiment is English-only. |
| 22 | [jacksepticeye](https://www.youtube.com/channel/UCYzPXprvl5Y-Sf0g4vX-m6g) | 31.2M | 17,759,463,682 | 2026-09-28 | on |  |
| 23 | [invictor](https://www.youtube.com/channel/UChOQkbLHWi3zSCUjT7Kjd1g) | 30.3M | 11,218,189,286 | 2026-09-28 | off | Non-English; keyword sentiment is English-only. |
| 24 | [DanTDM](https://www.youtube.com/channel/UCS5Oz6CHmeoF7vSad0qqXfw) | 29.1M | 20,446,927,670 | 2026-09-29 | on |  |
| 25 | [VanossGaming](https://www.youtube.com/channel/UCKqH_9mk1waLgBiL2vT5b9g) | 26M | 17,120,358,446 | 2026-09-28 | on |  |
| 26 | [SSundee](https://www.youtube.com/channel/UCke6I9N4KfC968-yRcd5YRg) | 25.5M | 17,354,057,240 | 2026-09-29 | off | Mostly Minecraft/Roblox/Fortnite; rarely relevant to PS2. |
| 27 | [Aphmau](https://www.youtube.com/channel/UCzYfz8uibvnB7Yc1LjePi4g) | 25.3M | 30,410,438,873 | 2026-09-29 | off | Mostly Minecraft/Roblox/Fortnite; rarely relevant to PS2. |
| 28 | [CoryxKenshin](https://www.youtube.com/channel/UCiYcA0gJzg855iSKMrX3oHg) | 24.7M | 10,075,495,043 | 2026-03-07 | off | Inactive: last upload 2026-03-07. |
| 29 | [Ninja](https://www.youtube.com/channel/UCAW-NpUFkMyCNrvRSSGIvDQ) | 23.5M | 2,793,642,003 | 2026-09-29 | off | Mostly Minecraft/Roblox/Fortnite; rarely relevant to PS2. |
| 30 | [Jelly](https://www.youtube.com/channel/UC0DZmkupLYwc0yDsfocLh0A) | 23.3M | 15,370,730,642 | 2026-09-27 | off | Mostly Minecraft/Roblox/Fortnite; rarely relevant to PS2. |
| 31 | [LazarBeam](https://www.youtube.com/channel/UCw1SQ6QRRtfAhrN_cjkrOgA) | 23.3M | 10,247,537,517 | 2026-09-29 | off | Mostly Minecraft/Roblox/Fortnite; rarely relevant to PS2. |
| 32 | [AuthenticGames](https://www.youtube.com/channel/UCIPA6iWNaoetaa1T46RkzXw) | 20.2M | 9,022,834,640 | 2025-04-10 | off | Non-English; keyword sentiment is English-only. |
| 33 | [Unspeakable](https://www.youtube.com/channel/UCwIWAbIeu0xI0ReKWOcw3eg) | 20.1M | 12,557,599,103 | 2026-09-26 | off | Mostly Minecraft/Roblox/Fortnite; rarely relevant to PS2. |
| 34 | [The Game Theorists](https://www.youtube.com/channel/UCo_IB5145EVNcf8hw1Kku7w) | 19.6M | 4,753,749,650 | 2026-09-26 | on |  |
| 35 | [PrestonPlayz](https://www.youtube.com/channel/UCJZam2u1G0syq3kyqrCXrNw) | 17.9M | 8,716,957,408 | 2026-09-26 | off | Mostly Minecraft/Roblox/Fortnite; rarely relevant to PS2. |
| 36 | [Willyrex](https://www.youtube.com/channel/UC8rNKrqBxJqL9izOOMxBJtw) | 17.3M | 5,516,017,385 | 2026-09-29 | off | Non-English; keyword sentiment is English-only. |
| 37 | [Typical Gamer](https://www.youtube.com/channel/UC2wKfjlioOCLP4xQMOWNcgg) | 16.1M | 5,760,612,110 | 2026-09-30 | off | Mostly Minecraft/Roblox/Fortnite; rarely relevant to PS2. |
| 38 | [Kwebbelkop](https://www.youtube.com/channel/UCfLuMSIDmeWRYpuCQL0OJ6A) | 14.9M | 7,063,675,988 | 2026-09-28 | off | Mostly Minecraft/Roblox/Fortnite; rarely relevant to PS2. |
| 39 | [CaptainSparklez](https://www.youtube.com/channel/UCshoKvlZGZ20rVgazZp5vnQ) | 11.4M | 4,185,542,796 | 2026-09-17 | off | Mostly Minecraft/Roblox/Fortnite; rarely relevant to PS2. |
| 40 | [Smosh Games](https://www.youtube.com/channel/UCJ2ZDzMRgSrxmwphstrm8Ww) | 8.62M | 4,309,972,130 | 2026-09-28 | on |  |
| 41 | [videogamedunkey](https://www.youtube.com/channel/UCsvn_Po0SmunchJYOWpOxMg) | 7.57M | 4,354,974,157 | 2026-09-28 | on |  |
| 42 | [GameGrumps](https://www.youtube.com/channel/UC9CuvdOVfMPvKCiwdGKL3cQ) | 5.45M | 7,430,461,473 | 2026-09-29 | on |  |

Same channels, top 10 by **total views**:

| # | Channel | Total views | Subscribers |
|---:|---|---:|---:|
| 1 | [LankyBox](https://www.youtube.com/channel/UCSf0s2ogUVYpJPuzW1zpAOg) | 35,995,331,692 | 42M |
| 2 | [Aphmau](https://www.youtube.com/channel/UCzYfz8uibvnB7Yc1LjePi4g) | 30,410,438,873 | 25.3M |
| 3 | [PewDiePie](https://www.youtube.com/channel/UC-lHJZR3Gqxm24_Vd_AJ5Yw) | 29,539,115,521 | 109M |
| 4 | [Diosdado Juarez](https://www.youtube.com/channel/UC0gnpMXQFvO9YsRZ_2adXPA) | 27,711,993,635 | 32.4M |
| 5 | [PANDA BOI](https://www.youtube.com/channel/UC0Wju2yvRlfwqraLlz5152Q) | 27,523,106,815 | 62.4M |
| 6 | [Markiplier](https://www.youtube.com/channel/UC7_YxT-KID8kRbqZo7MyscQ) | 23,936,836,519 | 38.9M |
| 7 | [Mikecrack](https://www.youtube.com/channel/UCqJ5zFEED1hWs0KNQCQuYdQ) | 22,128,146,846 | 58.7M |
| 8 | [DanTDM](https://www.youtube.com/channel/UCS5Oz6CHmeoF7vSad0qqXfw) | 20,446,927,670 | 29.1M |
| 9 | [JuegaGerman](https://www.youtube.com/channel/UCYiGq8XF7YQD00x7wAd62Zg) | 19,112,131,575 | 56.7M |
| 10 | [jacksepticeye](https://www.youtube.com/channel/UCYzPXprvl5Y-Sf0g4vX-m6g) | 17,759,463,682 | 31.2M |

### Gaming news & media

| # | Channel | Subscribers | Total views | Last upload | Default | Note |
|---:|---|---:|---:|---|---|---|
| 1 | [IGN](https://www.youtube.com/channel/UCKy1dAqELo0zrOtPkf0eTMw) | 20M | 22,144,903,190 | 2026-09-30 | on |  |
| 2 | [gameranx](https://www.youtube.com/channel/UCNvzD7Z-g64bPXxGzaQaa4g) | 8.65M | 4,578,180,764 | 2026-09-29 | on |  |
| 3 | [GameSpot](https://www.youtube.com/channel/UCbu2SsF-Or3Rsn3NxqODImw) | 5.72M | 4,195,930,796 | 2026-09-29 | on |  |
| 4 | [Video Game News](https://www.youtube.com/channel/UCitsvZeConV2Im24BVFH8hg) | 3.52M | 2,757,782,165 | 2026-09-29 | on |  |
| 5 | [Digital Foundry](https://www.youtube.com/channel/UC9PBzalIcEQCsiIkq36PyUA) | 1.53M | 822,431,441 | 2026-09-29 | on |  |
| 6 | [Polygon](https://www.youtube.com/channel/UCuVxaQDraOja6xKidcmoufA) | 1.4M | 693,435,248 | 2026-09-26 | on |  |
| 7 | [ACG](https://www.youtube.com/channel/UCK9_x1DImhU-eolIay5rb2Q) | 1.21M | 220,681,290 | 2026-09-25 | on |  |
| 8 | [Skill Up](https://www.youtube.com/channel/UCZ7AeeVbyslLM_8-nVy2B8Q) | 1.1M | 349,644,337 | 2026-09-28 | on |  |
| 9 | [Nintendo Life](https://www.youtube.com/channel/UCl7ZXbZUCWI2Hz--OrO4bsA) | 852K | 331,111,654 | 2026-09-28 | on |  |
| 10 | [Spawn Wave](https://www.youtube.com/channel/UCoIXnB865l9Ex9zs4OIXTdQ) | 771K | 490,035,737 | 2026-09-29 | on |  |
| 11 | [Eurogamer](https://www.youtube.com/channel/UCciKycgzURdymx-GRSY2_dA) | 754K | 372,003,438 | 2026-08-30 | on |  |
| 12 | [Game Informer](https://www.youtube.com/channel/UCK-65DO2oOxxMwphl2tYtcw) | 748K | 284,884,376 | 2026-09-25 | on |  |
| 13 | [Bellular News](https://www.youtube.com/channel/UC3nPaf5MeeDTHA2JN7clidg) | 545K | 230,379,215 | 2026-09-29 | on |  |
| 14 | [Kotaku](https://www.youtube.com/channel/UCVS9tA3PI8Gard_LrTx0YsQ) | 354K | 222,554,711 | 2024-10-03 | off | Inactive: last upload 2024-10-03. |
| 15 | [PC Gamer](https://www.youtube.com/channel/UCgaPRP68bbyHnfkPhWWBrNw) | 333K | 203,481,178 | 2026-09-30 | on |  |
| 16 | [Kinda Funny Games](https://www.youtube.com/channel/UCT6QFE3peNry9PdO5uGj96g) | 311K | 215,282,410 | 2026-09-30 | on |  |
| 17 | [Juicy News Network](https://www.youtube.com/channel/UC4rD2NGH3LxRNeF6VCDLeiQ) | 268K | 89,687,306 | 2026-01-29 | off | Inactive: last upload 2026-01-29. |
| 18 | [Easy Allies](https://www.youtube.com/channel/UCZrxXp1reP8E353rZsB3jaA) | 262K | 159,559,191 | 2026-09-27 | on |  |
| 19 | [Giant Bomb](https://www.youtube.com/channel/UCmeds0MLhjfkjD_5acPnFlQ) | 248K | 222,312,767 | 2026-09-29 | on |  |
| 20 | [VG247.com](https://www.youtube.com/channel/UCRl0tzAFRKfNvAQnnfvIR9A) | 231K | 196,959,031 | 2026-08-30 | on |  |
| 21 | [Rock Paper Shotgun](https://www.youtube.com/channel/UC5bKSAZBvV9AKlBJPG0Py-A) | 199K | 49,413,493 | 2026-08-30 | on |  |
| 22 | [Push Square](https://www.youtube.com/channel/UCbI-X9F07inmxYvQKDBOU7Q) | 172K | 60,894,776 | 2026-09-25 | on |  |
| 23 | [Mithrie - Gaming News](https://www.youtube.com/channel/UCDbiEgV3Y7JQtaftgN7lyPw) | 121K | 12,510,815 | 2026-09-30 | on |  |

### Platforms & publishers

Official channels announce remasters, remakes and ports first.

| # | Channel | Subscribers | Total views | Last upload | Default | Note |
|---:|---|---:|---:|---|---|---|
| 1 | [PlayStation](https://www.youtube.com/channel/UC-2Y8dQb0S6DtpxNgAKoJKA) | 17.2M | 6,417,318,786 | 2026-09-30 | on |  |
| 2 | [Rockstar Games](https://www.youtube.com/channel/UC6VcWc1rAoWdBCM0JxrRQ3A) | 13.8M | 1,773,501,566 | 2026-08-28 | on |  |
| 3 | [thegameawards](https://www.youtube.com/channel/UCqDS7KWjAPKv-7ZSlro9OiQ) | 12.4M | 307,047,971 | 2026-09-13 | on |  |
| 4 | [Nintendo of America](https://www.youtube.com/channel/UCGIY_O-8vW4rfX98KlMkvRg) | 10.2M | 4,152,897,536 | 2026-09-29 | on |  |
| 5 | [XBOX](https://www.youtube.com/channel/UCjBp_7RuDBUYbd1LegWEJ8g) | 5.86M | 1,838,680,324 | 2026-09-29 | on |  |
| 6 | [Ubisoft](https://www.youtube.com/channel/UC0KU8F9jJqSLS11LRXvFWmg) | 3.99M | 1,482,957,224 | 2026-09-29 | on |  |
| 7 | [PlayStation Access](https://www.youtube.com/channel/UC6yzV_xgKn8r77FkcmZyMSg) | 2.18M | 803,308,409 | 2026-09-29 | on |  |
| 8 | [Bethesda Softworks](https://www.youtube.com/channel/UCvZHe-SP3xC7DdOk4Ri8QBw) | 2.1M | 738,549,559 | 2026-09-29 | on |  |
| 9 | [Bandai Namco Entertainment America](https://www.youtube.com/channel/UC_ntXHv-XdKCD7CPynVvnQw) | 1.53M | 673,197,835 | 2026-09-30 | on |  |
| 10 | [Electronic Arts](https://www.youtube.com/channel/UCIHBybdoneVVpaQK7xMz1ww) | 857K | 355,159,428 | 2026-03-03 | off | Inactive: last upload 2026-03-03. |
| 11 | [Capcom USA](https://www.youtube.com/channel/UCW7h-1mymnJ96akzjrmiIgA) | 381K | 132,187,201 | 2026-09-17 | on |  |
| 12 | [Square Enix](https://www.youtube.com/channel/UCA5SLTAVA6unn1M-6lbo1NA) | 372K | 158,511,914 | 2026-09-28 | on |  |
| 13 | [Official ATLUS West](https://www.youtube.com/channel/UC7hgDFSPvJVIUx_b8i1cILA) | 342K | 140,378,802 | 2026-09-29 | on |  |
| 14 | [SEGA](https://www.youtube.com/channel/UCVkqs_Q88BDmyaWwjYJ8_Ig) | 331K | 263,090,745 | 2026-09-30 | on |  |
| 15 | [Konami](https://www.youtube.com/channel/UCwkUBN7foWU9GcY5cFmso-Q) | 284K | 59,665,895 | 2026-09-25 | on |  |

### Retro gaming, by subscribers

Focus: *reviews & history*, *hardware & emulation*, or *collecting & reselling* (resellers use the lower-weighted `collector` role, see [weights](docs/ARCHITECTURE.md#weights)).

| # | Channel | Focus | Subscribers | Total views | Last upload | Default | Note |
|---:|---|---|---:|---:|---|---|---|
| 1 | [JonTronShow](https://www.youtube.com/channel/UCdJdEguB1F1CiYe7OEi3SBg) | reviews & history | 6.38M | 1,428,520,931 | 2025-01-11 | off | Inactive: last upload 2025-01-11. |
| 2 | [Cinemassacre](https://www.youtube.com/channel/UC0M0rxSz3IF0CsSour1iWmw) | reviews & history | 4.03M | 2,478,672,727 | 2026-09-26 | on |  |
| 3 | [Odd Tinkering](https://www.youtube.com/channel/UCf_suVrG2dA5BTjJhNLwthQ) | collecting & reselling | 2.83M | 442,200,816 | 2026-08-09 | on |  |
| 4 | [DidYouKnowGaming](https://www.youtube.com/channel/UCyS4xQE6DK4_p3qXQwJQAyA) | reviews & history | 2.37M | 649,164,840 | 2026-08-08 | on |  |
| 5 | [Summoning Salt](https://www.youtube.com/channel/UCtUbO6rBht0daVIOGML3c8w) | reviews & history | 2.15M | 288,605,856 | 2026-08-27 | on |  |
| 6 | [Scott The Woz](https://www.youtube.com/channel/UC4rqhyiTs7XyuODcECvuiiQ) | reviews & history | 2.04M | 816,802,195 | 2026-09-05 | on |  |
| 7 | [PeanutButterGamer](https://www.youtube.com/channel/UCRBkeMoYX02w-0qVIKNkruw) | reviews & history | 2.03M | 503,820,327 | 2026-08-18 | on |  |
| 8 | [Ahoy](https://www.youtube.com/channel/UCE1jXbVAGJQEORz9nZqb5bQ) | reviews & history | 1.86M | 266,278,673 | 2026-06-29 | on |  |
| 9 | [LGR](https://www.youtube.com/channel/UCLx053rWZxCiYWsBETgdKrQ) | reviews & history | 1.82M | 614,808,092 | 2026-09-24 | on |  |
| 10 | [TronicsFix](https://www.youtube.com/channel/UCfOrKQtC1tDfGf_fFVb8pYw) | collecting & reselling | 1.78M | 514,636,057 | 2026-09-25 | on |  |
| 11 | [The 8-Bit Guy](https://www.youtube.com/channel/UC8uT9cgJorJPWu7ITLGo9Ww) | hardware & emulation | 1.47M | 293,502,181 | 2026-06-20 | on |  |
| 12 | [ETA PRIME](https://www.youtube.com/channel/UC_0CVCfC_3iuHqmyClu59Uw) | hardware & emulation | 1.4M | 567,835,484 | 2026-09-29 | on |  |
| 13 | [The Completionist](https://www.youtube.com/channel/UCPYJR2EIu0_MJaDeSGwkIVw) | reviews & history | 1.38M | 349,406,073 | 2026-09-18 | on |  |
| 14 | [UpIsNotJump](https://www.youtube.com/channel/UCFLwN7vRu8M057qJF8TsBaA) | reviews & history | 1.16M | 171,171,754 | 2026-09-25 | on |  |
| 15 | [Gaming Historian](https://www.youtube.com/channel/UCnbvPS_rXp4PC21PG2k1UVg) | reviews & history | 1.1M | 151,596,658 | 2026-04-03 | off | Inactive: last upload 2026-04-03. |
| 16 | [Karl Jobst](https://www.youtube.com/channel/UC3ltptWa0xfrDweghW94Acg) | reviews & history | 1.05M | 268,923,927 | 2026-08-25 | on |  |
| 17 | [WULFF DEN](https://www.youtube.com/channel/UCr613nJgA50o8DUUT00qHvw) | hardware & emulation | 987K | 251,026,353 | 2026-09-24 | on |  |
| 18 | [MetalJesusRocks](https://www.youtube.com/channel/UCEFymXY4eFCo_AchSpxwyrg) | collecting & reselling | 948K | 286,715,293 | 2026-09-25 | on |  |
| 19 | [Modern Vintage Gamer](https://www.youtube.com/channel/UCjFaPUcJU1vwk193mnW_w1w) | hardware & emulation | 938K | 239,727,396 | 2026-09-28 | on |  |
| 20 | [/noclip](https://www.youtube.com/channel/UC0fDG3byEcMtbOqPMymDNbw) | reviews & history | 901K | 88,781,443 | 2026-09-28 | on |  |
| 21 | [Retro Game Corps](https://www.youtube.com/channel/UCoZQiN0o7f36H7PaW4fVhFw) | hardware & emulation | 863K | 200,009,515 | 2026-09-29 | on |  |
| 22 | [Blue Television Games](https://www.youtube.com/channel/UCw5YkWj0TfjZrQEgG8u9JjQ) | reviews & history | 841K | 739,095,430 | 2026-09-26 | on |  |
| 23 | [RetroGamingNow](https://www.youtube.com/channel/UCTWbP-2W-_6mzWLg2oZmT7Q) | reviews & history | 718K | 160,557,762 | 2026-09-28 | on |  |
| 24 | [The Retro Future](https://www.youtube.com/channel/UCefAbzsWZE4uXU-mqQMrr4Q) | collecting & reselling | 651K | 106,280,432 | 2026-09-18 | on |  |
| 25 | [Nostalgia Nerd](https://www.youtube.com/channel/UC7qPftDWPw9XuExpSgfkmJQ) | reviews & history | 593K | 111,865,247 | 2026-09-28 | on |  |
| 26 | [Phoenix Resale](https://www.youtube.com/channel/UCYWd5Q-C8M-OeDzKo86CAeg) | collecting & reselling | 573K | 170,555,582 | 2026-09-13 | on |  |
| 27 | [GVMERS](https://www.youtube.com/channel/UCSuhUzpdXg9jme6eN6HA_IA) | reviews & history | 541K | 72,409,127 | 2026-07-31 | on |  |
| 28 | [RGT 85](https://www.youtube.com/channel/UCA5RGaQc-a8tIX_AqTTmWdw) | hardware & emulation | 536K | 258,783,614 | 2026-09-29 | on |  |
| 29 | [Cinemassacre Clips](https://www.youtube.com/channel/UC25-_5i19rPlLosl_h7G9Ow) | reviews & history | 493K | 174,033,687 | 2026-09-22 | on |  |
| 30 | [Retro Jakes](https://www.youtube.com/channel/UCTdwY9mYjI9mbuLJ7Zx2How) | collecting & reselling | 493K | 333,682,571 | 2026-09-29 | on |  |
| 31 | [Classic Game Room](https://www.youtube.com/channel/UCh4syoTtvmYlDMeMnwS5dmA) | reviews & history | 445K | 450,595,286 | 2024-06-21 | off | Inactive: last upload 2024-06-21. |
| 32 | [Macho Nacho Productions](https://www.youtube.com/channel/UC4CsqctrGOn4NTz09sAhXwQ) | collecting & reselling | 444K | 64,744,057 | 2026-09-26 | on |  |
| 33 | [Larry Bundy Jr](https://www.youtube.com/channel/UCJVdNvvuvOnthuWVQjYff2w) | reviews & history | 435K | 106,239,010 | 2026-09-05 | on |  |
| 34 | [SomecallmeJohnny](https://www.youtube.com/channel/UCg83RGdRpwfvoFEuE2zWKZA) | reviews & history | 418K | 237,716,588 | 2026-09-23 | on |  |
| 35 | [Chase After The Right Price](https://www.youtube.com/channel/UCPke0SGE7FGIuhnGurf9qQA) | collecting & reselling | 418K | 277,846,026 | 2026-09-28 | on |  |
| 36 | [Retro Dodo](https://www.youtube.com/channel/UCRg2tBkpKYDxOKtX3GvLZcQ) | hardware & emulation | 346K | 75,910,105 | 2026-09-23 | on |  |
| 37 | [SNES drunk](https://www.youtube.com/channel/UCfBLXTwLoUpDAkHcHizW3Jg) | reviews & history | 340K | 121,128,428 | 2026-08-18 | on |  |
| 38 | [Stop Skeletons From Fighting](https://www.youtube.com/channel/UC5Xeb9-FhZXgvw340n7PsCQ) | reviews & history | 336K | 57,690,060 | 2026-09-28 | on |  |
| 39 | [Game Sack](https://www.youtube.com/channel/UCT6LaAC9VckZYJUzutUW3PQ) | reviews & history | 328K | 132,300,438 | 2026-09-27 | on |  |
| 40 | [Retro Rick](https://www.youtube.com/channel/UC1tyWJZ-mPWch81I2UW7cQg) | collecting & reselling | 319K | 72,970,680 | 2026-09-22 | on |  |
| 41 | [TechDweeb](https://www.youtube.com/channel/UCgRaK4A7yi4ZELCLUjdP_pg) | hardware & emulation | 309K | 46,613,028 | 2026-09-29 | on |  |
| 42 | [NeoGamer - The Video Game Archive](https://www.youtube.com/channel/UCDC7X5gNh2LxQ2PnN_OKD5g) | reviews & history | 281K | 156,497,276 | 2026-09-29 | on |  |
| 43 | [Nerrel](https://www.youtube.com/channel/UCZKyj7wDE51SMbkrRBT6SdA) | reviews & history | 265K | 47,316,648 | 2026-09-16 | on |  |
| 44 | [Retro Game Mechanics Explained](https://www.youtube.com/channel/UCwRqWnW5ZkVaP_lZF7caZ-g) | reviews & history | 254K | 25,216,750 | 2026-01-26 | off | Inactive: last upload 2026-01-26. |
| 45 | [Pat the NES Punk](https://www.youtube.com/channel/UC1wdop56K-ORxh37G6-fs7A) | reviews & history | 254K | 156,716,904 | 2026-09-26 | on |  |
| 46 | [Adrian's Digital Basement](https://www.youtube.com/channel/UCE5dIscvDxrb7CD5uiJJOiw) | hardware & emulation | 249K | 57,241,419 | 2026-09-27 | on |  |
| 47 | [My Life in Gaming](https://www.youtube.com/channel/UCpvtp7mH0Cdq8FQUxcjDq0Q) | reviews & history | 239K | 43,115,496 | 2026-09-28 | on |  |
| 48 | [I Finished A Video Game](https://www.youtube.com/channel/UCVdDUN69YsAXPxh2y71sMtQ) | reviews & history | 229K | 40,141,735 | 2026-06-10 | on |  |
| 49 | [Wicked Gamer & Collector](https://www.youtube.com/channel/UCW_sIU3MaWW5cXSjGqNIvbw) | collecting & reselling | 208K | 77,856,815 | 2026-09-29 | on |  |
| 50 | [The Retro Collective](https://www.youtube.com/channel/UCLEoyoOKZK0idGqSc6Pi23w) | reviews & history | 199K | 29,629,665 | 2026-09-24 | on |  |
| 51 | [The Game Chasers](https://www.youtube.com/channel/UC78PzEVn5zWK4No0dPQHVQw) | collecting & reselling | 171K | 45,626,976 | 2025-07-14 | off | Inactive: last upload 2025-07-14. |
| 52 | [Pixel Game Squad](https://www.youtube.com/channel/UCRwh3TVQszgmDK6UHzHNdQQ) | collecting & reselling | 155K | 44,091,179 | 2026-09-29 | on |  |
| 53 | [GameHut](https://www.youtube.com/channel/UCfVFSjHQ57zyxajhhRc7i0g) | reviews & history | 149K | 13,878,929 | 2025-08-01 | off | Inactive: last upload 2025-08-01. |
| 54 | [Classic Gaming Quarterly](https://www.youtube.com/channel/UC2i64jLboyVFZwwO6UCKZ6g) | reviews & history | 147K | 18,788,042 | 2023-12-23 | off | Inactive: last upload 2023-12-23. |
| 55 | [John Hancock](https://www.youtube.com/channel/UCkDwUy-wt1adtSyd227TNdA) | reviews & history | 141K | 28,091,047 | 2026-09-29 | on |  |
| 56 | [Retro Video Game Pickups](https://www.youtube.com/channel/UC6W4xz9_OdWf2kF_yL7UbEQ) | collecting & reselling | 139K | 124,752,219 | 2026-09-30 | on |  |
| 57 | [Adam Koralik](https://www.youtube.com/channel/UCFTfkdN3L4aLdryeADiSsIg) | collecting & reselling | 129K | 38,004,571 | 2026-09-26 | on |  |
| 58 | [Displaced Gamers](https://www.youtube.com/channel/UCWoSKWs8h6lFdiEDAjuIfpA) | reviews & history | 121K | 12,275,224 | 2026-08-11 | on |  |
| 59 | [PeteDorr](https://www.youtube.com/channel/UCeTvRtfRFyWXdO_ZbyArPjA) | collecting & reselling | 119K | 27,784,253 | 2026-09-28 | on |  |
| 60 | [JRPGLife](https://www.youtube.com/channel/UCXbE-Ljd1C9RFe-yEdjTgkQ) | collecting & reselling | 115K | 63,762,307 | 2026-09-27 | on |  |
| 61 | [Kim Justice](https://www.youtube.com/channel/UC9ZWVL1Elyt2cdiQYjxS_1w) | reviews & history | 98.5K | 21,872,104 | 2026-09-20 | on |  |
| 62 | [Retro Handhelds](https://www.youtube.com/channel/UC3IYhdamzjvEJ9CwkQa4RAw) | hardware & emulation | 96.6K | 21,089,343 | 2026-09-29 | on |  |
| 63 | [Joey's Retro Handhelds](https://www.youtube.com/channel/UCwUiHJUm1wpSaUXiQt_H12A) | hardware & emulation | 96.4K | 20,882,464 | 2026-09-29 | on |  |
| 64 | [RetroRGB](https://www.youtube.com/channel/UCLPIbBCKVH2uKGm5C4sOkew) | hardware & emulation | 84.4K | 14,512,658 | 2026-09-25 | on |  |
| 65 | [Video Game Esoterica](https://www.youtube.com/channel/UCn2pQB4jsCTLUtx2NIkCvUg) | reviews & history | 82.4K | 23,933,499 | 2026-09-29 | on |  |
| 66 | [Memory Card](https://www.youtube.com/channel/UCoxRkuujB7-AwV5DmImIDRg) | collecting & reselling | 66.7K | 2,650,963 | 2026-09-15 | on |  |
| 67 | [The Video Game History Foundation](https://www.youtube.com/channel/UCicVsS0zrUPrA3RaOJO5oBg) | reviews & history | 64.9K | 2,918,667 | 2026-09-16 | on |  |
| 68 | [Gary](https://www.youtube.com/channel/UC202eItEazdvnMRK09RTtaw) | reviews & history | 63.7K | 39,702,444 | 2026-09-29 | on |  |

Retro channels, top 10 by **total views**:

| # | Channel | Total views | Subscribers |
|---:|---|---:|---:|
| 1 | [Cinemassacre](https://www.youtube.com/channel/UC0M0rxSz3IF0CsSour1iWmw) | 2,478,672,727 | 4.03M |
| 2 | [JonTronShow](https://www.youtube.com/channel/UCdJdEguB1F1CiYe7OEi3SBg) | 1,428,520,931 | 6.38M |
| 3 | [Scott The Woz](https://www.youtube.com/channel/UC4rqhyiTs7XyuODcECvuiiQ) | 816,802,195 | 2.04M |
| 4 | [Blue Television Games](https://www.youtube.com/channel/UCw5YkWj0TfjZrQEgG8u9JjQ) | 739,095,430 | 841K |
| 5 | [DidYouKnowGaming](https://www.youtube.com/channel/UCyS4xQE6DK4_p3qXQwJQAyA) | 649,164,840 | 2.37M |
| 6 | [LGR](https://www.youtube.com/channel/UCLx053rWZxCiYWsBETgdKrQ) | 614,808,092 | 1.82M |
| 7 | [ETA PRIME](https://www.youtube.com/channel/UC_0CVCfC_3iuHqmyClu59Uw) | 567,835,484 | 1.4M |
| 8 | [TronicsFix](https://www.youtube.com/channel/UCfOrKQtC1tDfGf_fFVb8pYw) | 514,636,057 | 1.78M |
| 9 | [PeanutButterGamer](https://www.youtube.com/channel/UCRBkeMoYX02w-0qVIKNkruw) | 503,820,327 | 2.03M |
| 10 | [Classic Game Room](https://www.youtube.com/channel/UCh4syoTtvmYlDMeMnwS5dmA) | 450,595,286 | 445K |

### PS2-dedicated

Small channels, but every upload is about PS2 games, so they count as PS2 context for matching and weigh 1.5×.

| # | Channel | Subscribers | Total views | Last upload | Default | Note |
|---:|---|---:|---:|---|---|---|
| 1 | [John GodGames](https://www.youtube.com/channel/UCLC3kuN_2emyokGE4WStv6w) | 729K | 609,141,822 | 2026-09-29 | on |  |
| 2 | [xTimelessGaming](https://www.youtube.com/channel/UC7c5IWuVuiYVdKxcQ3Bpvbg) | 412K | 325,173,780 | 2026-09-29 | on |  |
| 3 | [Retrogamingtommy](https://www.youtube.com/channel/UCrapa0hAEAIfdZxtjODd0Lw) | 316K | 196,356,378 | 2026-09-29 | on |  |
| 4 | [ANGEL PS2](https://www.youtube.com/channel/UCgHPug_ZesHYlCA-Jc25VgQ) | 90.2K | 64,757,938 | 2026-09-29 | on |  |
| 5 | [PS2 or Die](https://www.youtube.com/channel/UC81naFdSS2bKzj51XDVltBQ) | 14.5K | 916,606 | 2026-09-29 | on |  |
| 6 | [Jimbo Gaming PlayStation 2 ](https://www.youtube.com/channel/UCXspo7eyvzUh2k9d4JGLNRg) | 9.75K | 7,119,556 | 2026-09-30 | on |  |
| 7 | [We Review Every PS2 Game Oh God](https://www.youtube.com/channel/UC519lz5DdH7tsIMpfU55FlA) | 9.27K | 417,370 | 2025-10-05 | off | Inactive: last upload 2025-10-05. |
| 8 | [Dan Gnadt - The PS2 Guy](https://www.youtube.com/channel/UChBb5-4ILVNPsL8xX6a4LpA) | 7.72K | 443,360 | 2026-09-29 | on |  |

### Added from the dashboard

Channels added later through **Sources & Weights**. They were not part of the 2026-09-30 measurement, so they have no subscriber or view figures here.

| Channel | Default |
|---|---|
| [GetTheGreg](https://www.youtube.com/@GetTheGreg) | on |
| [Colour Shed Productions](https://www.youtube.com/@ColourShedProductions) | on |
| [Legally Insane Gamer](https://www.youtube.com/@LegallyInsaneGamer) | on |

## Podcasts

Podcasts are RSS feeds already. They publish no listener or subscriber numbers, so popularity is measured by Apple Podcasts' Video Games chart (US and UK) and the number of US ratings. Feed URLs come from Apple's lookup API and were each fetched and parsed. Podcasts are fetched every 6 hours (`poll_every_hours`) because the enabled feeds add up to roughly 100 MB per fetch.

### Gaming news & discussion, by chart rank

On by default: shows in the US or UK top 30. Shows about a single game (World of Warcraft, Pokémon, Minecraft, EA FC...) and non-gaming shows were left out.

| # | Show | Chart US | Chart UK | Apple ratings | Last episode | Default | Note |
|---:|---|---:|---:|---:|---|---|---|
| 1 | [Get Played](https://podcasts.apple.com/us/podcast/get-played/id1466286684) · [RSS](https://rss.art19.com/get-played) | #1 | #11 | 2,218 (★4.6) | 2026-09-28 | on |  |
| 2 | [WhatCulture Gaming](https://podcasts.apple.com/us/podcast/whatculture-gaming/id1433583146) · [RSS](https://feeds.acast.com/public/shows/c78baeb1-14c1-497c-bbfb-350cecd87107) | #8 | #1 | 287 (★4.3) | 2026-09-28 | on |  |
| 3 | [Kinda Funny Games Daily: Video Games News Podcast](https://podcasts.apple.com/us/podcast/kinda-funny-games-daily-video-games-news-podcast/id1247343210) · [RSS](https://feeds.megaphone.fm/ROOSTER8838278962) | #2 | #5 | 4,009 (★4.5) | 2026-09-29 | on |  |
| 4 | [Button Boys](https://podcasts.apple.com/us/podcast/button-boys/id1827054353) · [RSS](https://feeds.megaphone.fm/buttonboys) | #126 | #2 | 5 (★5) | 2026-09-23 | on |  |
| 5 | [Kinda Funny Gamescast: Video Game Podcast](https://podcasts.apple.com/us/podcast/kinda-funny-gamescast-video-game-podcast/id957171516) · [RSS](https://feeds.megaphone.fm/ROOSTER3727935380) | #3 | #3 | 2,853 (★4.4) | 2026-09-29 | on |  |
| 6 | [Game Scoop!](https://podcasts.apple.com/us/podcast/game-scoop/id276268226) · [RSS](https://rss.pdrl.fm/817ebc/feeds.megaphone.fm/gamescoop) | #4 | #6 | 4,108 (★4.7) | 2026-09-25 | on |  |
| 7 | [Friends Per Second](https://podcasts.apple.com/us/podcast/friends-per-second/id1629844110) · [RSS](https://feeds.megaphone.fm/friendspersecond) | #9 | #4 | 398 (★4.8) | 2026-09-26 | on |  |
| 8 | [The Besties](https://podcasts.apple.com/us/podcast/the-besties/id505516789) · [RSS](https://feeds.simplecast.com/Urk3897_) | #5 | #22 | 4,855 (★4.9) | 2026-09-25 | on |  |
| 9 | [GOONS](https://podcasts.apple.com/us/podcast/goons/id1475597548) · [RSS](https://feeds.megaphone.fm/GOONSMEDIALLC6622958176) | #6 | #25 | 6,175 (★4.9) | 2026-09-29 | on |  |
| 10 | [Giant Bombcast](https://podcasts.apple.com/us/podcast/giant-bombcast/id274450056) · [RSS](https://www.spreaker.com/show/5928697/episodes/feed) | #7 | #14 | 5,686 (★4.7) | 2026-09-29 | on |  |
| 11 | [IGN UK Podcast](https://podcasts.apple.com/us/podcast/ign-uk-podcast/id337004125) · [RSS](https://rss.pdrl.fm/6213a6/feeds.megaphone.fm/ignukpod) | #154 | #7 | 270 (★4.8) | 2026-09-25 | on |  |
| 12 | [The Back Page: A Video Games Podcast](https://podcasts.apple.com/us/podcast/the-back-page-a-video-games-podcast/id1542406765) · [RSS](https://feeds.acast.com/public/shows/6249ec6c14fbed0013d3ce7e) | — | #9 | 48 (★4.9) | 2026-09-25 | on |  |
| 13 | [The Cane and Rinse videogame podcast](https://podcasts.apple.com/us/podcast/the-cane-and-rinse-videogame-podcast/id467041704) · [RSS](https://caneandrinse.com/feed/podcast/) | #93 | #10 | 388 (★4.8) | 2026-09-29 | on |  |
| 14 | [The Jeff Gerstmann Show - A Podcast About Video Games](https://podcasts.apple.com/us/podcast/the-jeff-gerstmann-show-a-podcast-about-video-games/id1628348754) · [RSS](https://feeds.megaphone.fm/QCD5913450294) | #11 | #12 | 1,036 (★4.8) | 2026-09-29 | on |  |
| 15 | [Fire Escape Cast](https://podcasts.apple.com/us/podcast/fire-escape-cast/id1562626230) · [RSS](https://www.spreaker.com/show/5008213/episodes/feed) | #13 | #17 | 511 (★4.6) | 2026-09-28 | on |  |
| 16 | [The MinnMax Show](https://podcasts.apple.com/us/podcast/the-minnmax-show/id1484599827) · [RSS](https://pinecast.com/feed/the-minnmax-show) | #14 | #59 | 2,272 (★4.9) | 2026-09-24 | on |  |
| 17 | [Castle Super Beast](https://podcasts.apple.com/us/podcast/castle-super-beast/id688649759) · [RSS](https://rss.libsyn.com/shows/46822/destinations/156361.xml) | #15 | #56 | 2,991 (★4.9) | 2026-09-22 | on |  |
| 18 | [Video Gamers Podcast](https://podcasts.apple.com/us/podcast/video-gamers-podcast/id1501880187) · [RSS](https://feeds.megaphone.fm/AMGAC9705074721) | #17 | #70 | 1,028 (★4.8) | 2026-09-29 | on |  |
| 19 | [Nintendo Voice Chat](https://podcasts.apple.com/us/podcast/nintendo-voice-chat/id276268457) · [RSS](https://rss.pdrl.fm/52ee62/feeds.megaphone.fm/nvc) | #33 | #19 | 3,433 (★4.6) | 2026-09-09 | on |  |
| 20 | [Gaming illuminaughty](https://podcasts.apple.com/us/podcast/gaming-illuminaughty/id690393853) · [RSS](http://feeds.feedburner.com/GamingIlluminaughtyPodcast) | #19 | — | 2,160 (★4.9) | 2026-09-28 | on |  |
| 21 | [The Game Informer Show](https://podcasts.apple.com/us/podcast/the-game-informer-show/id335246945) · [RSS](https://www.spreaker.com/show/6639255/episodes/feed) | #20 | #62 | 1,422 (★4.5) | 2026-09-25 | on |  |
| 22 | [Press X to Continue](https://podcasts.apple.com/us/podcast/press-x-to-continue/id1781229776) · [RSS](https://audioboom.com/channels/5144387.rss) | — | #20 | 2 (★5) | 2026-09-29 | on |  |
| 23 | [Unlocked](https://podcasts.apple.com/us/podcast/unlocked/id276268454) · [RSS](https://rss.pdrl.fm/6e460d/feeds.megaphone.fm/ignunlocked) | #22 | #21 | 2,798 (★4.4) | 2026-09-24 | on |  |
| 24 | [DLC](https://podcasts.apple.com/us/podcast/dlc/id794234509) · [RSS](https://audioboom.com/channels/5104635.rss) | #23 | #49 | 1,118 (★4.6) | 2026-09-28 | on |  |
| 25 | [SpawnCast](https://podcasts.apple.com/us/podcast/spawncast/id1211524662) · [RSS](http://feeds.feedburner.com/soundcloud/QbQD) | #24 | #85 | 332 (★4.5) | 2026-09-27 | on |  |
| 26 | [Post Games](https://podcasts.apple.com/us/podcast/post-games/id1815131711) · [RSS](https://rss.art19.com/post-games) | #25 | #95 | 572 (★4.9) | 2026-09-28 | on |  |
| 27 | [Remap Radio](https://podcasts.apple.com/us/podcast/remap-radio/id1690437343) · [RSS](https://rss.art19.com/remap-radio) | #26 | #26 | 889 (★4.9) | 2026-09-26 | on |  |
| 28 | [Game Mess Mornings](https://podcasts.apple.com/us/podcast/game-mess-mornings/id1614295454) · [RSS](https://www.spreaker.com/show/5928689/episodes/feed) | #27 | #57 | 141 (★4.4) | 2026-09-28 | on |  |
| 29 | [The Computer Game Show](https://podcasts.apple.com/us/podcast/the-computer-game-show/id1100170036) · [RSS](https://feed.podbean.com/thecomputergameshow/feed.xml) | — | #28 | 18 (★4.3) | 2026-09-30 | on |  |
| 30 | [VGC: The Video Game Podcast](https://podcasts.apple.com/us/podcast/vgc-the-video-game-podcast/id1672575206) · [RSS](https://feeds.acast.com/public/shows/vgc-a-video-games-podcast) | — | #29 | 32 (★4.7) | 2026-09-25 | on |  |
| 31 | [CORE - Core Gaming for Core Gamers](https://podcasts.apple.com/us/podcast/core-core-gaming-for-core-gamers/id1041859215) · [RSS](https://feeds.acast.com/public/shows/6500f421d570420011d0e34b) | #30 | #102 | 300 (★4.4) | 2026-09-26 | on |  |
| 32 | [The XB2 — An Xbox & Gaming Podcast](https://podcasts.apple.com/us/podcast/the-xb2-an-xbox-gaming-podcast/id1074822039) · [RSS](https://feeds.megaphone.fm/NSR2628308212) | #49 | #30 | 266 (★4.4) | 2026-09-26 | on |  |
| 33 | [Axe of the Blood God: An RPG Podcast](https://podcasts.apple.com/us/podcast/axe-of-the-blood-god-an-rpg-podcast/id969659784) · [RSS](https://feeds.megaphone.fm/LDSPO7715218750) | #31 | #135 | 662 (★4.5) | 2026-09-28 | off | Outside the Apple Video Games top 30 (US/UK); enable if wanted. |
| 34 | [Into the Aether - A Low Key Video Game Podcast](https://podcasts.apple.com/us/podcast/into-the-aether-a-low-key-video-game-podcast/id1415546090) · [RSS](https://feeds.transistor.fm/intotheaether) | #32 | #39 | 427 (★4.8) | 2026-09-30 | off | Outside the Apple Video Games top 30 (US/UK); enable if wanted. |
| 35 | [The Kit & Krysta Podcast](https://podcasts.apple.com/us/podcast/the-kit-krysta-podcast/id1609805414) · [RSS](https://audioboom.com/channels/5081035.rss) | #34 | #141 | 526 (★4.7) | 2026-09-24 | off | Outside the Apple Video Games top 30 (US/UK); enable if wanted. |
| 36 | [Defining Duke: An Xbox Podcast](https://podcasts.apple.com/us/podcast/defining-duke-an-xbox-podcast/id1545198843) · [RSS](https://feeds.megaphone.fm/definingduke) | #37 | #98 | 882 (★4.8) | 2026-09-27 | off | Outside the Apple Video Games top 30 (US/UK); enable if wanted. |
| 37 | [Nontendo Podcast](https://podcasts.apple.com/us/podcast/nontendo-podcast/id1624139141) · [RSS](https://anchor.fm/s/111880bdc/podcast/rss) | #39 | #153 | 690 (★4.6) | 2026-09-18 | off | Outside the Apple Video Games top 30 (US/UK); enable if wanted. |
| 38 | [Pew Pew Bang](https://podcasts.apple.com/us/podcast/pew-pew-bang/id1796213059) · [RSS](https://pinecast.com/feed/pew-pew-bang) | #40 | — | 308 (★5) | 2026-09-28 | off | Outside the Apple Video Games top 30 (US/UK); enable if wanted. |
| 39 | [The Nerd Nest - A Video Game Podcast](https://podcasts.apple.com/us/podcast/the-nerd-nest-a-video-game-podcast/id1168326641) · [RSS](https://anchor.fm/s/8eaf968/podcast/rss) | #51 | #44 | 374 (★4.4) | 2026-09-27 | off | Outside the Apple Video Games top 30 (US/UK); enable if wanted. |
| 40 | [Game Mess Decides](https://podcasts.apple.com/us/podcast/game-mess-decides/id1176366805) · [RSS](https://www.spreaker.com/show/5683651/episodes/feed) | #47 | #177 | 156 (★4.7) | 2026-09-25 | off | Outside the Apple Video Games top 30 (US/UK); enable if wanted. |
| 41 | [Summon Sign: A Gaming Conversation](https://podcasts.apple.com/us/podcast/summon-sign-a-gaming-conversation/id1723904363) · [RSS](https://feeds.megaphone.fm/summonsign) | #50 | #118 | 266 (★4.9) | 2026-09-25 | off | Outside the Apple Video Games top 30 (US/UK); enable if wanted. |
| 42 | [The All Things Nintendo Podcast](https://podcasts.apple.com/us/podcast/the-all-things-nintendo-podcast/id1589146741) · [RSS](https://feeds.megaphone.fm/allthingsnintendo) | #52 | #52 | 256 (★4.6) | 2026-09-25 | off | Outside the Apple Video Games top 30 (US/UK); enable if wanted. |
| 43 | [Dropped Frames](https://podcasts.apple.com/us/podcast/dropped-frames/id1324781499) · [RSS](https://www.omnycontent.com/d/playlist/2a719a76-7cdb-4059-a7a0-af33012f7563/94ffb699-c5c9-4525-bf39-af3801515155/31f23a60-ba51-46ce-98b6-af380151517b/podcast.rss) | #55 | #53 | 160 (★5) | 2026-09-27 | off | Outside the Apple Video Games top 30 (US/UK); enable if wanted. |
| 44 | [Jimquisition](https://podcasts.apple.com/us/podcast/jimquisition/id947398127) · [RSS](https://feed.podbean.com/jimquisition/feed.xml) | #196 | #55 | 622 (★4.6) | 2026-09-24 | off | Outside the Apple Video Games top 30 (US/UK); enable if wanted. |
| 45 | [Inside Games News and Podcasts](https://podcasts.apple.com/us/podcast/inside-games-news-and-podcasts/id1494388156) · [RSS](https://anchor.fm/s/12356c9c/podcast/rss) | #59 | #134 | 155 (★4.9) | 2026-09-28 | off | Outside the Apple Video Games top 30 (US/UK); enable if wanted. |
| 46 | [The Insert Credit Show](https://podcasts.apple.com/us/podcast/the-insert-credit-show/id1651429066) · [RSS](https://insertcredit.podcast.audio/@show/feed.xml) | #60 | #74 | 359 (★4.9) | 2026-09-28 | off | Outside the Apple Video Games top 30 (US/UK); enable if wanted. |
| 47 | [The Easy Allies Podcast](https://podcasts.apple.com/us/podcast/the-easy-allies-podcast/id1097284330) · [RSS](https://feeds.megaphone.fm/IMP2654482957) | #62 | #128 | 803 (★4.7) | 2026-09-27 | off | Outside the Apple Video Games top 30 (US/UK); enable if wanted. |
| 48 | [Vidjagame Apocalypse](https://podcasts.apple.com/us/podcast/vidjagame-apocalypse/id600353928) · [RSS](http://feeds.feedburner.com/VidjagameApocalypse) | #70 | #192 | 817 (★4.7) | 2026-09-26 | off | Outside the Apple Video Games top 30 (US/UK); enable if wanted. |
| 49 | [Video Game Outsiders](https://podcasts.apple.com/us/podcast/video-game-outsiders/id79430865) · [RSS](https://feeds.megaphone.fm/NSR4849377281) | #151 | — | 624 (★4.1) | 2026-09-30 | off | Outside the Apple Video Games top 30 (US/UK); enable if wanted. |

### PlayStation podcasts

| # | Show | Chart US | Chart UK | Apple ratings | Last episode | Default | Note |
|---:|---|---:|---:|---:|---|---|---|
| 1 | [Beyond](https://podcasts.apple.com/us/podcast/beyond/id276268070) · [RSS](https://rss.pdrl.fm/a9cb78/feeds.megaphone.fm/ignbeyond) | #48 | #158 | 3,925 (★4.4) | 2026-09-10 | on |  |
| 2 | [Sacred Symbols: A PlayStation Podcast](https://podcasts.apple.com/us/podcast/sacred-symbols-a-playstation-podcast/id1406231151) · [RSS](https://feeds.megaphone.fm/STU5682506591) | #10 | #8 | 3,383 (★4.8) | 2026-09-28 | on |  |
| 3 | [Official PlayStation Podcast](https://podcasts.apple.com/us/podcast/official-playstation-podcast/id483223024) · [RSS](https://playstation.libsyn.com/rss) | #124 | #197 | 972 (★4.6) | 2026-09-25 | on |  |
| 4 | [The Trophy Room - A PlayStation Podcast](https://podcasts.apple.com/us/podcast/the-trophy-room-a-playstation-podcast/id1260212127) · [RSS](https://feed.podbean.com/pstrophyroom/feed.xml) | — | — | 384 (★4.8) | 2026-09-23 | on |  |
| 5 | [PlayStation Access](https://podcasts.apple.com/us/podcast/playstation-access/id1615420937) · [RSS](https://feeds.acast.com/public/shows/62309929e9119100173fd370) | #123 | #16 | 141 (★4.9) | 2026-09-19 | on |  |
| 6 | [Triangle Squared: A Playstation Podcast](https://podcasts.apple.com/us/podcast/triangle-squared-a-playstation-podcast/id1220271057) · [RSS](https://www.podserve.fm/series/rss/826/triangle-squared-a-playstation-podcast.rss) | — | — | 48 (★4.4) | 2026-09-23 | off | Smaller show; enable if wanted. |

### Retro gaming podcasts, by Apple ratings

On by default: active shows with 25+ ratings that cover several platforms; single-platform shows (NES, N64, C64, ZX Spectrum, Dreamcast, SEGA, Amiga) are listed but start off.

| # | Show | Chart US | Chart UK | Apple ratings | Last episode | Default | Note |
|---:|---|---:|---:|---:|---|---|---|
| 1 | [Retronauts](https://podcasts.apple.com/us/podcast/retronauts/id672857593) · [RSS](https://audioboom.com/channels/5081747.rss) | #16 | #42 | 2,117 (★4.5) | 2026-09-28 | on |  |
| 2 | [KnockBack: The Retro and Nostalgia Podcast](https://podcasts.apple.com/us/podcast/knockback-the-retro-and-nostalgia-podcast/id1350157623) · [RSS](https://feeds.megaphone.fm/STU6505478744) | — | — | 1,502 (★4.9) | 2026-04-08 | off | Inactive: last episode 2026-04-08. |
| 3 | [Watch Out for Fireballs!](https://podcasts.apple.com/us/podcast/watch-out-for-fireballs/id464108542) · [RSS](https://www.patreon.com/public-rss/80117?show=800722) | #58 | #140 | 1,197 (★4.7) | 2026-09-24 | on |  |
| 4 | [Completely Unnecessary Podcast](https://podcasts.apple.com/us/podcast/completely-unnecessary-podcast/id705355841) · [RSS](https://anchor.fm/s/37360560/podcast/rss) | #133 | — | 1,066 (★4.5) | 2026-08-26 | on |  |
| 5 | [Remember The Game? Retro Gaming Podcast](https://podcasts.apple.com/us/podcast/remember-the-game-retro-gaming-podcast/id1407041447) · [RSS](https://rss.art19.com/remember-the-game) | #38 | #40 | 422 (★4.6) | 2026-09-24 | on |  |
| 6 | [New Game Plus - A Retro Gaming Podcast](https://podcasts.apple.com/us/podcast/new-game-plus-a-retro-gaming-podcast/id1042429619) · [RSS](https://anchor.fm/s/1059e8940/podcast/rss) | — | — | 215 (★4.7) | 2026-09-28 | on |  |
| 7 | [Codex History of Video Games with Mike Coletta and Tyler Ostby](https://podcasts.apple.com/us/podcast/codex-history-of-video-games-with-mike-coletta/id1388568002) · [RSS](https://rss.libsyn.com/shows/141866/destinations/892730.xml) | — | #194 | 203 (★4.8) | 2026-09-28 | on |  |
| 8 | [Retrograde Amnesia: Comprehensive JRPG Retrospective](https://podcasts.apple.com/us/podcast/retrograde-amnesia-comprehensive-jrpg-retrospective/id1480854950) · [RSS](https://rss.libsyn.com/shows/213656/destinations/1546262.xml) | #76 | — | 178 (★5) | 2026-09-28 | on |  |
| 9 | [The Retro Hour (Retro Gaming Podcast)](https://podcasts.apple.com/us/podcast/the-retro-hour-retro-gaming-podcast/id1073270208) · [RSS](https://audioboom.com/channels/4970769.rss) | — | #18 | 132 (★4.8) | 2026-09-25 | on |  |
| 10 | [Retro RPG Podcast](https://podcasts.apple.com/us/podcast/retro-rpg-podcast/id331945044) · [RSS](https://retrorpg.net/?feed=podcast) | — | — | 131 (★4.1) | 2026-08-26 | on |  |
| 11 | [Video Game History Hour](https://podcasts.apple.com/us/podcast/video-game-history-hour/id1536393630) · [RSS](https://anchor.fm/s/370d6ccc/podcast/rss) | #120 | — | 127 (★4.9) | 2026-09-23 | on |  |
| 12 | [Play Retro Show](https://podcasts.apple.com/us/podcast/play-retro-show/id1601321925) · [RSS](https://feeds.acast.com/public/shows/6500f7e38c35840011fa822f) | #100 | #185 | 115 (★4.8) | 2026-09-24 | on |  |
| 13 | [Retrovaniacs](https://podcasts.apple.com/us/podcast/retrovaniacs/id998408464) · [RSS](https://feed.podbean.com/retrovaniacs/feed.xml) | #148 | — | 109 (★4.8) | 2026-09-29 | on |  |
| 14 | [Retro Gaming RoundUp](https://podcasts.apple.com/us/podcast/retro-gaming-roundup/id302869307) · [RSS](https://rss.libsyn.com/shows/23257/destinations/32444.xml) | — | — | 87 (★4.3) | 2026-09-01 | on |  |
| 15 | [BoxTrick: A Retro Gaming Podcast](https://podcasts.apple.com/us/podcast/boxtrick-a-retro-gaming-podcast/id1286376614) · [RSS](https://feeds.redcircle.com/b66323ef-3233-41de-86fb-6eebae6cd656) | — | — | 85 (★4.5) | 2026-09-11 | on |  |
| 16 | [RPGFan's Retro Encounter](https://podcasts.apple.com/us/podcast/rpgfans-retro-encounter/id991828866) · [RSS](https://feeds.transistor.fm/rpgfan-retro-encounter) | — | — | 74 (★4.6) | 2026-09-24 | on |  |
| 17 | [My Perfect Console with Simon Parkin](https://podcasts.apple.com/us/podcast/my-perfect-console-with-simon-parkin/id1665581266) · [RSS](https://feeds.acast.com/public/shows/63b458521043e00011114396) | #109 | #13 | 69 (★4.9) | 2026-09-29 | on |  |
| 18 | [NEStalgia](https://podcasts.apple.com/us/podcast/nestalgia/id1342922798) · [RSS](https://anchor.fm/s/5808ab8/podcast/rss) | #189 | — | 67 (★4.9) | 2026-09-25 | off | Single non-PlayStation platform; listed for completeness. |
| 19 | [SEGA Talk Podcast](https://podcasts.apple.com/us/podcast/sega-talk-podcast/id1167614817) · [RSS](http://segabits.com/blog/category/podcast/sega-talk-podcast/feed/) | — | — | 57 (★4.7) | 2026-09-25 | off | Single non-PlayStation platform; listed for completeness. |
| 20 | [Arcade Attack Retro Gaming Podcast](https://podcasts.apple.com/us/podcast/arcade-attack-retro-gaming-podcast/id1174983594) · [RSS](https://feed.podbean.com/arcadeattackpodcast/feed.xml) | — | #64 | 56 (★4.7) | 2026-09-29 | on |  |
| 21 | [Amigos Retro Gaming Network - Amigos: Everything Amiga / ARG Presents / Sprite Castle / Pixel Gaiden](https://podcasts.apple.com/us/podcast/amigos-retro-gaming-network-amigos-everything-amiga/id1022434255) · [RSS](https://anchor.fm/s/ee9137c/podcast/rss) | — | #167 | 55 (★4.9) | 2026-09-27 | off | Single non-PlayStation platform; listed for completeness. |
| 22 | [Secret Levels: Retro Game Reviews](https://podcasts.apple.com/us/podcast/secret-levels-retro-game-reviews/id1365013942) · [RSS](https://rss.buzzsprout.com/166619.rss) | — | — | 53 (★4.8) | 2026-09-17 | on |  |
| 23 | [Retro Blast](https://podcasts.apple.com/us/podcast/retro-blast/id1483354168) · [RSS](https://rss.libsyn.com/shows/214193/destinations/1551167.xml) | #114 | #78 | 52 (★5) | 2026-09-27 | on |  |
| 24 | [Classic Gaming Today:  A Retro Gaming Podcast](https://podcasts.apple.com/us/podcast/classic-gaming-today-a-retro-gaming-podcast/id1646545691) · [RSS](https://feed.podbean.com/classicgamingtoday/feed.xml) | — | — | 51 (★4.9) | 2026-07-27 | on |  |
| 25 | [Retro Blissed](https://podcasts.apple.com/us/podcast/retro-blissed/id1125745991) · [RSS](http://bicbp-radio.com/retro-blissed?format=rss) | — | — | 47 (★4.8) | 2026-07-01 | on |  |
| 26 | [Flashback 64 \| A Nintendo 64 Podcast](https://podcasts.apple.com/us/podcast/flashback-64-a-nintendo-64-podcast/id1685594885) · [RSS](https://feed.podbean.com/flashback64pod/feed.xml) | #140 | #152 | 42 (★4.6) | 2026-09-28 | off | Single non-PlayStation platform; listed for completeness. |
| 27 | [Sprite Castle: A C64/Commodore Game Podcast](https://podcasts.apple.com/us/podcast/sprite-castle-a-c64-commodore-game-podcast/id827251255) · [RSS](https://podcast.robohara.com/category/spritecastle/feed/) | — | #196 | 42 (★4.9) | 2026-09-25 | off | Single non-PlayStation platform; listed for completeness. |
| 28 | [The Dreamcast Junkyard DreamPod](https://podcasts.apple.com/us/podcast/the-dreamcast-junkyard-dreampod/id984898837) · [RSS](https://rss.buzzsprout.com/42610.rss) | — | #142 | 39 (★4.9) | 2026-09-25 | off | Single non-PlayStation platform; listed for completeness. |
| 29 | [Retro Asylum -  The UK's No.1 Retro Gaming Podcast](https://podcasts.apple.com/us/podcast/retro-asylum-the-uks-no-1-retro-gaming-podcast/id474414834) · [RSS](https://rss.libsyn.com/shows/70391/destinations/295987.xml) | — | #149 | 33 (★4.5) | 2026-09-13 | on |  |
| 30 | [The Retro Gamers: A Video Game Podcast](https://podcasts.apple.com/us/podcast/the-retro-gamers-a-video-game-podcast/id955251603) · [RSS](https://anchor.fm/s/51a3c054/podcast/rss) | — | #126 | 30 (★4.8) | 2026-09-28 | on |  |
| 31 | [Retro Hangover](https://podcasts.apple.com/us/podcast/retro-hangover/id996608625) · [RSS](https://feeds.captivate.fm/retrohangover/) | — | — | 28 (★4.7) | 2026-09-27 | on |  |
| 32 | [Nerd Cave Retro](https://podcasts.apple.com/us/podcast/nerd-cave-retro/id1135304235) · [RSS](https://feeds.acast.com/public/shows/6519b599fc8c840012975a4c) | — | — | 25 (★4.5) | 2026-09-25 | on |  |
| 33 | [Retro Gaming Discussion Show](https://podcasts.apple.com/us/podcast/retro-gaming-discussion-show/id954142242) · [RSS](https://rss.libsyn.com/shows/61467/destinations/238917.xml) | — | #119 | 21 (★3.9) | 2026-09-18 | off | Smaller show; enable if wanted. |
| 34 | [Our Sinclair: A ZX Spectrum Podcast](https://podcasts.apple.com/us/podcast/our-sinclair-a-zx-spectrum-podcast/id1454120857) · [RSS](https://anchor.fm/s/e8635b8/podcast/rss) | — | #38 | 6 (★4.8) | 2026-09-16 | off | Single non-PlayStation platform; listed for completeness. |

### PS2 & PlayStation history

| # | Show | Chart US | Chart UK | Apple ratings | Last episode | Default | Note |
|---:|---|---:|---:|---:|---|---|---|
| 1 | [Millennium Edition \| Nintendo, SEGA, and Games of the 2000s](https://podcasts.apple.com/us/podcast/millennium-edition-nintendo-sega-and-games-of-the-2000s/id1894975602) · [RSS](https://feeds.acast.com/public/shows/69e6e95d0b4baf3bf24eb30f) | — | — | 4 (★5) | 2026-09-25 | on |  |
| 2 | [Retro PlayStation Podcast](https://podcasts.apple.com/us/podcast/retro-playstation-podcast/id1896860130) · [RSS](https://api.riverside.com/hosting/8HBKd4lL.rss) | — | — | 1 (★5) | 2026-09-23 | on |  |

## News sites and subreddits

These are the original sources, moved unchanged from `scraper.py` into feeds.json (same URLs, same subreddit groups, so the same Reddit requests). A test keeps every one of them in the file.

| Source | Group | Feed |
|---|---|---|
| Gematsu | Major Global Outlets & Magazines | https://www.gematsu.com/feed |
| Eurogamer | Major Global Outlets & Magazines | https://www.eurogamer.net/feed |
| Time Extension | Major Global Outlets & Magazines | https://www.timeextension.com/feed |
| Push Square | Major Global Outlets & Magazines | https://www.pushsquare.com/feeds/latest |
| GameSpot | Major Global Outlets & Magazines | https://www.gamespot.com/feeds/mashup/ |
| PC Gamer | Major Global Outlets & Magazines | https://www.pcgamer.com/rss/ |
| Nintendo Everything | Major Global Outlets & Magazines | https://nintendoeverything.com/feed |
| Kotaku | Major Global Outlets & Magazines | https://kotaku.com/rss |
| Polygon | Major Global Outlets & Magazines | https://www.polygon.com/rss/index.xml |
| VG247 | Major Global Outlets & Magazines | https://www.vg247.com/feed |
| Rock Paper Shotgun | Major Global Outlets & Magazines | https://www.rockpapershotgun.com/feed/ |
| Destructoid | Major Global Outlets & Magazines | https://www.destructoid.com/feed/ |
| Nintendo Life | Major Global Outlets & Magazines | https://www.nintendolife.com/feeds/latest |
| PlayStation.Blog | Official Platform Blogs | https://blog.playstation.com/feed/ |
| Xbox Wire | Official Platform Blogs | https://news.xbox.com/en-us/feed/ |
| IGN Latinoamérica | Spanish & Portuguese Feeds | https://latam.ign.com/feed.xml |
| Eurogamer.pt | Spanish & Portuguese Feeds | https://www.eurogamer.pt/feed |
| Vandal | Spanish & Portuguese Feeds | https://vandal.elespanol.com/xml.cgi |

- **Dedicated PS2 & Emulation Hubs**: r/ps2, r/ps2homebrew, r/PCSX2, r/playstation2
- **Collecting, Retro & Emulation**: r/gamecollecting, r/LimitedPrintGames, r/NSCollectors, r/Steelbook, r/gameverifying, r/retrogaming, r/classicgaming, r/emulation, r/psx
- **High-Traffic General Communities**: r/gaming, r/Games, r/pcgaming, r/truegaming, r/ShouldIbuythisgame, r/gamingsuggestions, r/pcmasterrace, r/NintendoSwitch, r/PlayStation, r/xboxone, r/SteamDeck, r/jrpg, r/patientgamers

Health on 2026-09-30:

- **VG247**: the feed loads but its newest article is from 2026-06-02, so it has added nothing since June.
- **Time Extension**: served behind a Cloudflare check that blocks some networks; it works from GitHub's runners, which is where the scraper runs.
- **r/Steelbook** and **r/xboxone**: their newest posts in the combined Reddit feed are from 2018 and 2024. They stay listed (switch them off in the dashboard if you like).

## How the lists were built

1. Candidates: Playboard's all-time gaming ranking, Wikipedia's most-subscribed channels, YouTube's own channel search for 24 gaming, retro and PS2 queries (477 channels), well-known retro channels, Apple Podcasts' Video Games charts (top 200, US and UK) and iTunes searches for retro, PlayStation and PS2 shows.
2. Every candidate was measured live: channel ID, subscribers, total views, videos, country and join date from the channel's About panel; the RSS feed fetched and parsed to get the newest upload. Podcasts: feed fetched and parsed (status, size, newest episode, whether episodes have links) plus Apple ratings.
3. Wrong matches were removed by hand (handles that belong to namesakes, spam "PS2 BIOS" podcasts, feeds that return 404).
4. Defaults: gaming news, platforms/publishers, retro and PS2 sources on; entertainment creators on only when they are English and cover console/PC games broadly; anything inactive for 120+ days off.
