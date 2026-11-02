# Tradi6: Apple / iPhone content research

This repo contains the **`/niche-outliers`** Claude Code skill (`.claude/skills/niche-outliers/`).
Each run scrapes Instagram Reels and TikTok through Apify, ranks videos by views, finds the
top 10 viral outliers in our niche (iPhone tips, tricks, hidden features, settings and apps),
saves them to Notion, and turns them into a topic board for our own videos.

## Setup (one time)
1. Get an Apify API token (free tier works) at https://console.apify.com/settings/integrations
2. Optional Notion setup: create an internal integration at https://www.notion.so/my-integrations,
   then share a page with it (••• → Connections).
3. Provide the secrets as environment variables, e.g. in `.claude/settings.local.json` (gitignored):
   ```json
   { "env": { "APIFY_TOKEN": "apify_api_...", "NOTION_TOKEN": "ntn_...", "NOTION_PARENT_PAGE_ID": "..." } }
   ```

## Use
In Claude Code, type:
```
/niche-outliers                 # Apple/iPhone preset
/niche-outliers iphone-apps     # other presets: iphone-tips, iphone-settings, ios, mac
/niche-outliers iphonetips,ios26,actionbutton
```
Results land in `outliers/` (`outliers-<date>.md` table + `topics-<date>.md` video ideas) and in Notion.

Script only, without Claude: `python3 .claude/skills/niche-outliers/scripts/outliers.py --niche apple --days 7`
