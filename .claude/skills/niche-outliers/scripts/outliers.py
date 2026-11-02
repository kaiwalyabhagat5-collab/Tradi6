#!/usr/bin/env python3
"""Niche outliers: scrape Instagram Reels + TikTok for a niche via Apify,
rank by views, flag outliers, and save the top N to Notion (or Markdown/JSON).

Standard library only. Environment:
  APIFY_TOKEN            required for live scraping (https://console.apify.com/settings/integrations)
  NOTION_TOKEN           optional, Notion internal integration secret
  NOTION_DATABASE_ID     optional, existing "Viral Outliers" database to append to
  NOTION_PARENT_PAGE_ID  optional, page under which the database is created on first run

Usage:
  python3 outliers.py --niche apple                      # preset hashtags
  python3 outliers.py --hashtags iphonetips,iostips --top 10 --days 14
  python3 outliers.py --from-json raw.json               # re-rank saved data, no scraping
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
NICHES = json.loads((SKILL_DIR / "niches.json").read_text())

APIFY = "https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"
IG_ACTOR = "apify~instagram-hashtag-scraper"
TT_ACTOR = "clockworks~tiktok-scraper"
NOTION = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


# ---------------------------------------------------------------- HTTP helpers
def _request(url: str, payload: dict | None = None, headers: dict | None = None,
             method: str | None = None, timeout: int = 600):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"),
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:500]
        raise SystemExit(f"HTTP {e.code} from {url.split('?')[0]}: {body}") from None


def run_actor(actor: str, actor_input: dict, token: str) -> list[dict]:
    url = APIFY.format(actor=actor) + "?" + urllib.parse.urlencode({"token": token})
    return _request(url, actor_input) or []


# ---------------------------------------------------------------- scraping
def scrape_instagram(hashtags: list[str], per_tag: int, token: str) -> list[dict]:
    items = run_actor(IG_ACTOR, {"hashtags": hashtags, "resultsLimit": per_tag,
                                 "resultsType": "reels"}, token)
    out = []
    for it in items:
        views = it.get("videoPlayCount") or it.get("videoViewCount") or 0
        if not views:
            continue
        out.append({
            "platform": "Instagram",
            "creator": it.get("ownerUsername") or "",
            "followers": None,
            "views": int(views),
            "likes": it.get("likesCount") or 0,
            "comments": it.get("commentsCount") or 0,
            "caption": (it.get("caption") or "").strip(),
            "url": it.get("url") or "",
            "posted": it.get("timestamp"),
        })
    return out


def scrape_tiktok(hashtags: list[str], per_tag: int, token: str) -> list[dict]:
    items = run_actor(TT_ACTOR, {"hashtags": hashtags, "resultsPerPage": per_tag,
                                 "shouldDownloadVideos": False,
                                 "shouldDownloadCovers": False}, token)
    out = []
    for it in items:
        views = it.get("playCount") or 0
        if not views:
            continue
        author = it.get("authorMeta") or {}
        ts = it.get("createTimeISO") or (
            dt.datetime.fromtimestamp(it["createTime"], dt.timezone.utc).isoformat()
            if it.get("createTime") else None)
        out.append({
            "platform": "TikTok",
            "creator": author.get("name") or "",
            "followers": author.get("fans"),
            "views": int(views),
            "likes": it.get("diggCount") or 0,
            "comments": it.get("commentCount") or 0,
            "caption": (it.get("text") or "").strip(),
            "url": it.get("webVideoUrl") or "",
            "posted": ts,
        })
    return out


# ---------------------------------------------------------------- ranking
def _parse_ts(s):
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def rank(videos: list[dict], top: int, days: int | None, min_views: int) -> list[dict]:
    # de-duplicate by URL
    seen, uniq = set(), []
    for v in videos:
        key = v["url"] or (v["platform"], v["creator"], v["caption"][:60])
        if key not in seen:
            seen.add(key)
            uniq.append(v)

    if days:
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
        uniq = [v for v in uniq if (t := _parse_ts(v["posted"])) is None or t >= cutoff]
    uniq = [v for v in uniq if v["views"] >= min_views]
    if not uniq:
        return []

    # Outlier score = views relative to the median video in this niche batch,
    # boosted when a small account beats its follower count (true breakout).
    med = statistics.median(v["views"] for v in uniq) or 1
    for v in uniq:
        score = v["views"] / med
        f = v.get("followers")
        if f:
            v["views_per_follower"] = round(v["views"] / f, 2)
            if v["views"] > f:
                score *= min(1 + (v["views"] / f) / 10, 3)
        v["outlier_score"] = round(score, 1)
        v["engagement"] = round((v["likes"] + v["comments"]) / v["views"] * 100, 2)

    uniq.sort(key=lambda v: (v["outlier_score"], v["views"]), reverse=True)
    return uniq[:top]


# ---------------------------------------------------------------- output
def fmt_views(n: int) -> str:
    return f"{n/1e6:.1f}M" if n >= 1e6 else f"{n/1e3:.0f}K" if n >= 1e3 else str(n)


def to_markdown(rows: list[dict], niche: str) -> str:
    today = dt.date.today().isoformat()
    lines = [f"# Viral Outliers: {niche} ({today})", "",
             "| # | Platform | Creator | Views | Outlier | Eng % | Caption | Link |",
             "|---|---|---|---|---|---|---|---|"]
    for i, v in enumerate(rows, 1):
        cap = v["caption"].replace("\n", " ").replace("|", "/")[:90]
        lines.append(f"| {i} | {v['platform']} | @{v['creator']} | {fmt_views(v['views'])} | "
                     f"{v['outlier_score']}x | {v['engagement']} | {cap} | [Open]({v['url']}) |")
    return "\n".join(lines) + "\n"


def notion_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION}


def notion_create_db(token: str, parent_page: str) -> str:
    db = _request(f"{NOTION}/databases", {
        "parent": {"type": "page_id", "page_id": parent_page},
        "title": [{"type": "text", "text": {"content": "Viral Outliers"}}],
        "properties": {
            "Caption": {"title": {}},
            "Platform": {"select": {"options": [{"name": "Instagram", "color": "pink"},
                                                {"name": "TikTok", "color": "gray"}]}},
            "Creator": {"rich_text": {}},
            "Views": {"number": {"format": "number_with_commas"}},
            "Outlier Score": {"number": {}},
            "Engagement %": {"number": {}},
            "Rank": {"number": {}},
            "Niche": {"select": {}},
            "Week": {"date": {}},
            "Link": {"url": {}},
            "Status": {"select": {"options": [{"name": "Idea", "color": "blue"},
                                              {"name": "Scripted", "color": "yellow"},
                                              {"name": "Posted", "color": "green"}]}},
        },
    }, notion_headers(token))
    return db["id"]


def notion_push(rows: list[dict], niche: str, token: str, db_id: str) -> None:
    week = dt.date.today().isoformat()
    for i, v in enumerate(rows, 1):
        _request(f"{NOTION}/pages", {
            "parent": {"database_id": db_id},
            "properties": {
                "Caption": {"title": [{"text": {"content": (v["caption"] or "(no caption)")[:1900]}}]},
                "Platform": {"select": {"name": v["platform"]}},
                "Creator": {"rich_text": [{"text": {"content": "@" + v["creator"]}}]},
                "Views": {"number": v["views"]},
                "Outlier Score": {"number": v["outlier_score"]},
                "Engagement %": {"number": v["engagement"]},
                "Rank": {"number": i},
                "Niche": {"select": {"name": niche[:100]}},
                "Week": {"date": {"start": week}},
                "Link": {"url": v["url"] or None},
                "Status": {"select": {"name": "Idea"}},
            },
        }, notion_headers(token))


# ---------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--niche", default="apple", help=f"preset ({', '.join(NICHES)}) or free text label")
    ap.add_argument("--hashtags", help="comma-separated hashtags (overrides preset)")
    ap.add_argument("--platforms", default="instagram,tiktok")
    ap.add_argument("--per-tag", type=int, default=30, help="results per hashtag per platform")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--days", type=int, default=30, help="only videos from the last N days (0 = any)")
    ap.add_argument("--min-views", type=int, default=10_000)
    ap.add_argument("--from-json", help="skip scraping; rank a saved raw.json")
    ap.add_argument("--out", default="outliers", help="output directory")
    ap.add_argument("--no-notion", action="store_true")
    a = ap.parse_args()

    preset = NICHES.get(a.niche.lower())
    hashtags = ([h.strip().lstrip("#") for h in a.hashtags.split(",") if h.strip()] if a.hashtags
                else preset["hashtags"] if preset else [a.niche.replace(" ", "").lower()])
    label = preset["label"] if preset and not a.hashtags else a.niche

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = dt.date.today().isoformat()

    if a.from_json:
        raw = json.loads(Path(a.from_json).read_text())
    else:
        token = os.environ.get("APIFY_TOKEN")
        if not token:
            sys.exit("APIFY_TOKEN is not set. Get one at https://console.apify.com/settings/integrations")
        plats = {p.strip().lower() for p in a.platforms.split(",")}
        raw = []
        if "instagram" in plats:
            print(f"Scraping Instagram reels for #{', #'.join(hashtags)} ...", file=sys.stderr)
            raw += scrape_instagram(hashtags, a.per_tag, token)
        if "tiktok" in plats:
            print(f"Scraping TikTok for #{', #'.join(hashtags)} ...", file=sys.stderr)
            raw += scrape_tiktok(hashtags, a.per_tag, token)
        (out / f"raw-{stamp}.json").write_text(json.dumps(raw, indent=1, ensure_ascii=False))
        print(f"Collected {len(raw)} videos", file=sys.stderr)

    rows = rank(raw, a.top, a.days or None, a.min_views)
    if not rows:
        sys.exit("No videos matched. Try more hashtags, a larger --days window, or a lower --min-views.")

    md = to_markdown(rows, label)
    (out / f"outliers-{stamp}.md").write_text(md)
    (out / f"outliers-{stamp}.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    print(md)

    ntoken = os.environ.get("NOTION_TOKEN")
    if ntoken and not a.no_notion:
        db = os.environ.get("NOTION_DATABASE_ID")
        if not db and os.environ.get("NOTION_PARENT_PAGE_ID"):
            db = notion_create_db(ntoken, os.environ["NOTION_PARENT_PAGE_ID"])
            print(f"Created Notion database {db}. Set NOTION_DATABASE_ID={db} for next runs.",
                  file=sys.stderr)
        if db:
            notion_push(rows, label, ntoken, db)
            print(f"Saved {len(rows)} rows to Notion database {db}", file=sys.stderr)
        else:
            print("NOTION_TOKEN set but no NOTION_DATABASE_ID / NOTION_PARENT_PAGE_ID; skipped Notion.",
                  file=sys.stderr)


if __name__ == "__main__":
    main()
