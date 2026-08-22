# -*- coding: utf-8 -*-
"""ウォーシュFRB議長の発言コーパスを federalreserve.gov から収集する。

議長就任後の公開文書は2026年7月の議会証言1本しかない(2026-08時点)。
考え方を推定する材料はほぼ理事時代(2006-2010)の講演に限られるため、
両方を集めたうえで「いつの発言か」を必ず残す。時期を混ぜると、
在野で書いていた頃の見解と議長としての行動を取り違える。

使い方:
    python research/fetch_warsh.py          # 差分だけ取得
    python research/fetch_warsh.py --force  # 全部取り直す
"""

import argparse
import html
import io
import json
import os
import re
import time
import urllib.error
import urllib.request

BASE = "https://www.federalreserve.gov"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "warsh")
UA = "Mozilla/5.0 (compatible; nk225-option-site research collector)"

# 理事時代の講演一覧はこの年次インデックスに載っている
SPEECH_YEARS = range(2006, 2012)

# 議長就任後の文書。フィードに出ないものもあるのでURLを直接持つ。
CHAIR_DOCS = [
    ("2026-07-14", "Semiannual Monetary Policy Report to the Congress",
     "/newsevents/testimony/warsh20260714a.htm"),
]


def get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def to_text(raw: str) -> str:
    """本文だけを平文にする。ナビゲーションや脚注番号は落とす。"""
    raw = re.sub(r"(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", raw)
    body = re.search(r'(?is)<div[^>]*id="article"[^>]*>(.*?)</div>\s*</div>', raw)
    raw = body.group(1) if body else raw
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?i)</p>", "\n\n", raw)
    txt = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    txt = re.sub(r"[ \t\xa0]+", " ", txt)
    txt = re.sub(r"\n\s*\n+", "\n\n", txt)
    return txt.strip()


def discover_speeches() -> list:
    """年次インデックスから理事時代のウォーシュ講演を拾う。"""
    found = []
    for year in SPEECH_YEARS:
        try:
            idx = get(f"{BASE}/newsevents/speech/{year}speech.htm")
        except urllib.error.HTTPError as e:
            print(f"  {year}: 取得失敗 {e}")
            continue
        for path, label in re.findall(
                r'href="(/newsevents/speech/warsh[^"]+)"[^>]*>(.*?)</a>', idx, re.I | re.S):
            title = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", label))).strip()
            m = re.search(r"warsh(\d{4})(\d{2})(\d{2})", path)
            date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else str(year)
            found.append((date, title, path))
        time.sleep(0.5)
    return found


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    print("理事時代の講演を探しています...")
    items = [(d, t, p, "governor") for d, t, p in discover_speeches()]
    items += [(d, t, p, "chair") for d, t, p in CHAIR_DOCS]
    items.sort()

    index = []
    for date, title, path, role in items:
        name = f"{date}_{re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:60]}.txt"
        dest = os.path.join(OUT, name)
        if os.path.exists(dest) and not args.force:
            print(f"  skip  {date} {title[:52]}")
        else:
            try:
                text = to_text(get(BASE + path))
            except Exception as e:
                print(f"  FAIL  {date} {title[:40]} ({e})")
                continue
            header = (f"# {title}\n"
                      f"date: {date}\n"
                      f"role: {role}\n"
                      f"source: {BASE + path}\n\n")
            io.open(dest, "w", encoding="utf-8", newline="\n").write(header + text)
            print(f"  saved {date} {title[:52]} ({len(text):,}字)")
            time.sleep(0.5)
        index.append({"date": date, "title": title, "role": role,
                      "file": name, "source": BASE + path})

    io.open(os.path.join(OUT, "index.json"), "w", encoding="utf-8", newline="\n").write(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n")
    n_gov = sum(1 for i in index if i["role"] == "governor")
    n_chair = sum(1 for i in index if i["role"] == "chair")
    print(f"\n完了: 理事時代 {n_gov}本 / 議長就任後 {n_chair}本 → {OUT}")


if __name__ == "__main__":
    main()
