# -*- coding: utf-8 -*-
"""FRB(連邦準備制度理事会)の公式RSSから声明・講演・証言の一覧を取得する。

- 出典はすべてfederalreserve.gov公式フィード(米政府著作物=パブリックドメイン)
- 取得失敗時はキャッシュ(data/fed_feeds.json)にフォールバック
"""

import json
import os
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import requests

UA = {"User-Agent": "Mozilla/5.0 (compatible; nk225-options-site)"}
CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "data", "fed_feeds.json")

FEEDS = [
    {"key": "monetary", "ja": "金融政策リリース(FOMC声明・議事要旨など)",
     "en": "Monetary Policy Releases (FOMC statements, minutes)",
     "url": "https://www.federalreserve.gov/feeds/press_monetary.xml"},
    {"key": "speeches", "ja": "理事・議長の講演",
     "en": "Speeches (Board members)",
     "url": "https://www.federalreserve.gov/feeds/speeches.xml"},
    {"key": "testimony", "ja": "議会証言",
     "en": "Congressional Testimony",
     "url": "https://www.federalreserve.gov/feeds/testimony.xml"},
]


def fetch_feeds(limit: int = 12) -> dict:
    """全フィードの最新エントリを返す。{feed_key: [{title, link, date}...]}"""
    out = {}
    errors = 0
    for f in FEEDS:
        try:
            r = requests.get(f["url"], headers=UA, timeout=30)
            r.raise_for_status()
            root = ET.fromstring(r.content)
            items = []
            for it in root.findall(".//item")[:limit]:
                title = (it.findtext("title") or "").strip()
                link = (it.findtext("link") or "").strip()
                pub = (it.findtext("pubDate") or "").strip()
                try:
                    date = parsedate_to_datetime(pub).strftime("%Y-%m-%d")
                except Exception:
                    date = pub[:16]
                if title and link:
                    items.append({"title": title, "link": link, "date": date})
            out[f["key"]] = items
        except Exception as e:
            print(f"WARN: fed feed {f['key']} failed: {e}")
            errors += 1
    if errors == len(FEEDS):
        if os.path.exists(CACHE):
            print("INFO: using cached fed feeds")
            return json.load(open(CACHE, encoding="utf-8"))
        raise RuntimeError("all fed feeds failed and no cache")
    # 部分成功でもキャッシュを更新(失敗フィードは前回キャッシュで補完)
    if os.path.exists(CACHE):
        prev = json.load(open(CACHE, encoding="utf-8"))
        for f in FEEDS:
            if f["key"] not in out and f["key"] in prev:
                out[f["key"]] = prev[f["key"]]
    with open(CACHE, "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False)
    return out
