# FilmFeed Traffic Engine

Autonomous, production-ready traffic acquisition system for [FilmFeed](https://web-umber-six-e1un7z6257.vercel.app).

Drives Tier-1 US/UK/CA/AU traffic through four parallel channels:
viral Shorts, Reddit organic replies, programmatic SEO, and a Discord community bot — all automated via GitHub Actions with zero dedicated hardware.

---

## Directory Structure

```
traffic-engine/
├── config/
│   ├── settings.json          — Central configuration
│   └── proxies.txt            — Proxy list (optional)
├── modules/
│   ├── 1_shorts_automation/   — YouTube Shorts + TikTok pipeline
│   ├── 2_reddit_agent/        — Reddit organic traffic agent
│   ├── 3_programmatic_seo/    — TMDb fetcher, sitemap, Next.js pages
│   └── 4_discord_bot/         — Discord slash command bot
├── .github/workflows/         — GitHub Actions CI/CD pipelines
├── .env.example               — Environment variable template
└── requirements.txt
```

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/youruser/traffic-engine.git
cd traffic-engine
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your API keys
```

### 3. Install FFmpeg (required for video editing)

```bash
# Ubuntu/Debian
sudo apt-get install ffmpeg

# macOS
brew install ffmpeg

# Windows
# Download from https://ffmpeg.org/download.html and add to PATH
```

---

## Module 1 — Shorts Automation

Extracts trending movie trailers, reformats to 9:16, adds subtitles + CTA, uploads to YouTube Shorts and TikTok.

```bash
# Process a specific movie
python modules/1_shorts_automation/run_shorts.py --movie "Dune Part Two"

# Process top 5 trending movies
python modules/1_shorts_automation/run_shorts.py --trending --count 5

# Skip YouTube (TikTok only)
python modules/1_shorts_automation/run_shorts.py --trending --no-yt

# Skip TikTok (YouTube only)
python modules/1_shorts_automation/run_shorts.py --trending --no-tt
```

### YouTube Setup
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project → Enable YouTube Data API v3
3. Create OAuth 2.0 credentials → Download `client_secret.json`
4. Place at `config/youtube_client_secret.json`
5. Run once locally to authorize — token saved to `config/youtube_token.json`
6. For GitHub Actions: `cat config/youtube_token.json` → paste as `YOUTUBE_TOKEN_JSON` secret

### TikTok Setup
- **API method**: Apply for [TikTok Content Posting API](https://developers.tiktok.com/), set `TIKTOK_ACCESS_TOKEN`
- **Session method** (fallback): Log into TikTok in browser → DevTools → Copy `sessionid` cookie → set as `TIKTOK_SESSION_COOKIE`

### Ambient footage (optional split-screen)
Place `.mp4` ambient clips (satisfying gameplay, nature loops, etc.) in `assets/ambient/` to enable split-screen mode.

---

## Module 2 — Reddit Agent

Monitors subreddits for streaming requests and replies with organic links.

```bash
# Run background worker
python modules/2_reddit_agent/run_reddit.py
```

### Reddit Setup
1. Go to [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps)
2. Create a "script" app
3. Set `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USERNAME`, `REDDIT_PASSWORD` in `.env`

**Subreddits monitored** (configurable in `config/settings.json`):
- r/MovieSuggestions, r/FreeMoviesOnWatch, r/Piracy, r/cordcutters, r/animepiracy, r/movies, r/anime, r/streaming

---

## Module 3 — Programmatic SEO

Fetches 10,000 TMDb titles and generates sitemaps + Next.js static pages.

```bash
# Fetch TMDb data
python modules/3_programmatic_seo/tmdb_fetcher.py

# Generate sitemaps and ping search engines
python modules/3_programmatic_seo/generate_sitemap.py
```

### Next.js Integration

Copy these files into your Next.js project:

| Source | Destination in Next.js |
|--------|------------------------|
| `nextjs_pages/[slug]/page.tsx` | `app/movie/[slug]/page.tsx` |
| `nextjs_pages/sitemap.xml/route.ts` | `app/sitemap.xml/route.ts` |

Add to `next.config.js`:
```js
module.exports = {
  env: {
    TMDB_API_KEY: process.env.TMDB_API_KEY,
    NEXT_PUBLIC_SITE_URL: process.env.NEXT_PUBLIC_SITE_URL,
  },
}
```

---

## Module 4 — Discord Bot

Slash commands: `/watch`, `/trending`, `/request`

```bash
python modules/4_discord_bot/bot.py
```

### Discord Setup
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create an application → Bot → Copy token → set `DISCORD_BOT_TOKEN`
3. Enable `Message Content Intent` under Bot settings
4. Invite link: `https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=2147485696&scope=bot%20applications.commands`
5. Optionally set `DISCORD_GUILD_IDS` for instant command sync (vs global 1hr propagation)

---

## GitHub Actions Automation

Add these secrets to your GitHub repository (`Settings → Secrets → Actions`):

| Secret | Description |
|--------|-------------|
| `TMDB_API_KEY` | TMDb API key |
| `REDDIT_CLIENT_ID` | Reddit app client ID |
| `REDDIT_CLIENT_SECRET` | Reddit app client secret |
| `REDDIT_USERNAME` | Reddit account username |
| `REDDIT_PASSWORD` | Reddit account password |
| `YOUTUBE_TOKEN_JSON` | YouTube OAuth token JSON string |
| `TIKTOK_ACCESS_TOKEN` | TikTok API access token |
| `TIKTOK_SESSION_COOKIE` | TikTok session cookie (fallback) |
| `DISCORD_BOT_TOKEN` | Discord bot token |
| `GOOGLE_INDEXING_API_KEY` | Google Search Console API key |
| `BING_INDEXING_API_KEY` | Bing IndexNow API key |

### Workflow Schedule

| Workflow | Trigger | Action |
|----------|---------|--------|
| `daily_shorts.yml` | Every 6 hours | Generate + upload trending shorts |
| `reddit_crawler.yml` | Every 30 minutes | Scan Reddit and reply |
| `seo_indexer.yml` | Every Monday 4AM | Refresh sitemap, ping Google + Bing |

---

## Configuration

All settings are in `config/settings.json`. Key options:

- `reddit_subreddits` — list of subreddits to monitor
- `reddit_triggers` — phrases that trigger a reply
- `video_settings.split_screen` — enable/disable split-screen mode
- `video_settings.cta_text` — call-to-action overlay text
- `rate_limits` — anti-ban delays for Reddit and upload intervals
- `proxy.enabled` — enable proxy rotation (add proxies to `config/proxies.txt`)
