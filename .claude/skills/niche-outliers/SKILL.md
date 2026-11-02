---
name: niche-outliers
description: Weekly content research for a short-form video niche. Scrapes Instagram Reels and TikTok with Apify, ranks videos by views, finds the top 10 viral outliers, saves them to Notion, and turns them into new video topics. Use when the user types /niche-outliers, asks for "viral outliers", "what's going viral in my niche", "find video topics", or "weekly content research". Default niche is Apple / iPhone tips, tricks, hidden features, settings and apps.
argument-hint: "[niche preset or hashtags, e.g. apple | iphone-apps | iphonetips,ios26]"
---

# Niche Outliers

Find the 10 short-form videos in a niche that are beating everything else right now, then turn them into topics for our own videos.

**Our channel niche:** Apple. iPhone tips, tricks, features, hidden features, iPhone apps, iPhone settings, iOS updates.
If the user gives no niche, use the `apple` preset.

## Step 0: Pick the niche

- `$ARGUMENTS` empty → `--niche apple`
- Matches a preset in `niches.json` (`apple`, `iphone-tips`, `iphone-settings`, `iphone-apps`, `ios`, `mac`) → `--niche <preset>`
- Otherwise treat it as hashtags or a topic → `--hashtags tag1,tag2 --niche "<label>"`. For a topic, pick 4 to 8 relevant hashtags yourself.

## Step 1: Collect data (Apify)

**If an Apify MCP connector is available** (tools named like `mcp__apify__*`), you can call the actors directly:
- `apify/instagram-hashtag-scraper` with `{"hashtags": [...], "resultsLimit": 30, "resultsType": "reels"}`
- `clockworks/tiktok-scraper` with `{"hashtags": [...], "resultsPerPage": 30}`

Save the merged results in the normalized shape used by the script (platform, creator, followers, views, likes, comments, caption, url, posted) to `outliers/raw-<date>.json`. Then run Step 2 with `--from-json`.

**Otherwise use the bundled script.** It needs `APIFY_TOKEN` in the environment:

```bash
python3 .claude/skills/niche-outliers/scripts/outliers.py --niche apple --top 10 --days 30
```

Useful flags: `--platforms instagram` or `--platforms tiktok`, `--per-tag 50`, `--days 7` for a weekly run, `--min-views 50000`.

If `APIFY_TOKEN` is missing, stop and tell the user to:
1. create a free account at apify.com,
2. copy the API token from Console → Settings → API & Integrations,
3. add it as `APIFY_TOKEN` (shell export, `.claude/settings.local.json` `env`, or cloud environment secret).

Do not invent data.

## Step 2: Rank by views and find the outliers

The script handles this:
- removes duplicates and keeps only recent videos (`--days`) with at least `--min-views`
- **outlier score** = views ÷ median views of the batch. TikTok videos also get a boost when views far exceed the creator's follower count, which marks a true breakout from a small account
- keeps the top N (default 10)

The output goes to `outliers/outliers-<date>.md` and `.json`.

## Step 3: Save to Notion

- **Notion MCP connector available**: create or append to a database called **"Viral Outliers"** with these columns: Caption (title), Platform, Creator, Views, Outlier Score, Engagement %, Rank, Niche, Week, Link, Status (Idea / Scripted / Posted).
- **Otherwise**: the script pushes rows automatically when `NOTION_TOKEN` is set, along with either `NOTION_DATABASE_ID` or `NOTION_PARENT_PAGE_ID`. With only a parent page ID, it creates the database on the first run and prints the ID to reuse. The integration must be shared with that page in Notion (••• → Connections).
- With neither, the Markdown table in `outliers/` is the deliverable.

## Step 4: Turn the outliers into our video topics

This step matters most. For each outlier, open its caption and work out **why it went viral**. Look at:
- **Hook type:** "Stop doing X", "Hidden setting", "You've been using X wrong", "iPhone feature nobody knows", "Turn this OFF now", list ("5 apps…")
- **Topic:** battery, camera, privacy, Control Center, Action Button, Shortcuts, keyboard, Photos, Messages, Focus, new iOS feature, app recommendation
- **Format:** screen recording, face plus phone, text-on-screen, comparison

Then write a **Topic Board** for our iPhone channel, with 10 ideas ranked by expected potential. Each idea gets:

| Field | Content |
|---|---|
| Title / on-screen hook | first 1 to 2 seconds, under 8 words |
| Inspired by | outlier # and link |
| Angle | what makes ours different or better (newer iOS, more steps, a combo trick) |
| Script beats | 3 to 5 bullets: hook → demo steps (exact Settings path, e.g. Settings → Accessibility → Touch → Back Tap) → payoff → CTA |
| Caption + hashtags | ready to paste |

Rules for ideas:
- Every tip must be real and work on the current iOS version. Check Settings paths. If you're unsure a feature exists, say so instead of guessing.
- Prefer patterns that appear in 2 or more outliers. A repeated pattern beats a one-off.
- Mix in evergreen topics (battery, camera, hidden settings) with timely ones (latest iOS release).

Save the board to `outliers/topics-<date>.md`. If Notion is connected, add the ideas there with Status = Idea.

## Step 5 (pro tip): Run it every Monday automatically

Offer to schedule it so the user never has to type the command:
- Claude Code cloud: a scheduled task with cron `CRON_TZ=<user tz> 37 8 * * 1` and the prompt `/niche-outliers apple --days 7`
- Local: `crontab -e` → `37 8 * * 1 cd <repo> && claude -p "/niche-outliers apple"`

Ask for the user's timezone before scheduling.
