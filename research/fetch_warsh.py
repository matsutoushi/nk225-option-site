# -*- coding: utf-8 -*-
"""ウォーシュFRB議長まわりの一次資料を federalreserve.gov から収集する。

集めるもの:
  1. ウォーシュ本人の講演・議会証言(理事時代 2006-2010 / 議長就任後 2026-)
  2. 就任後のFOMC声明・議事要旨(彼が議長として主宰した会合の文書)

1と2は性格が違う。1は本人の言葉、2は委員会の合意文書で本人の見解とは限らない。
ファイル先頭の role: で区別できるようにし、保存先も分けている。

取得経路が2つあるのは、FRBのサイト構造がそうなっているため:
  - 古い年(〜2011)は年次インデックスページに一覧がある
  - 最近の年はインデックスページが無く(2026分は404)、RSSしか入口が無い
RSSは直近十数件しか載らないので、日次で回して取りこぼしを防ぐ前提。

使い方:
    python research/fetch_warsh.py          # 差分だけ取得
    python research/fetch_warsh.py --force  # 保存済みも取り直す
"""

import argparse
import email.utils
import html
import io
import json
import os
import re
import time
import urllib.error
import urllib.request

BASE = "https://www.federalreserve.gov"
ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_WARSH = os.path.join(ROOT, "warsh")
OUT_FOMC = os.path.join(ROOT, "fomc")
UA = "Mozilla/5.0 (compatible; nk225-option-site research collector)"

# 議長就任日。これ以降のFOMC文書が「彼が主宰した会合」のもの。
# 出典: https://www.federalreserve.gov/aboutthefed/bios/board/warsh.htm
# 「took office as chairman ... on May 22, 2026, for a four-year term ending on May 21, 2030」
CHAIR_SINCE = "2026-05-22"

# 年次インデックスが存在する範囲(理事時代)
ARCHIVE_YEARS = range(2006, 2012)

FEEDS = {
    "speech": f"{BASE}/feeds/speeches.xml",
    "testimony": f"{BASE}/feeds/testimony.xml",
    "monetary": f"{BASE}/feeds/press_monetary.xml",
}

# FOMC文書として拾うもの。討議内容が載るのはこの2種類。
FOMC_PATTERNS = (
    re.compile(r"^Minutes of the Federal Open Market Committee", re.I),
    re.compile(r"issues FOMC statement", re.I),
)


def get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def to_text(raw: str) -> str:
    """本文だけを平文にする。ナビゲーションやスクリプトは落とす。"""
    raw = re.sub(r"(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", raw)
    body = re.search(r'(?is)<div[^>]*id="article"[^>]*>(.*?)</div>\s*</div>', raw)
    raw = body.group(1) if body else raw
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?i)</p>", "\n\n", raw)
    txt = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    txt = re.sub(r"[ \t\xa0]+", " ", txt)
    txt = re.sub(r"\n\s*\n+", "\n\n", txt)
    return txt.strip()


def cdata(item: str, tag: str) -> str:
    m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", item, re.S)
    if not m:
        return ""
    v = m.group(1).strip()
    v = re.sub(r"^<!\[CDATA\[|\]\]>$", "", v).strip()
    return html.unescape(v)


def feed_items(url: str) -> list:
    """RSSから (日付, タイトル, URL) を返す。取得できなければ空。"""
    try:
        xml = get(url)
    except Exception as e:
        print(f"  フィード取得失敗 {url}: {e}")
        return []
    out = []
    for raw in re.findall(r"(?s)<item>(.*?)</item>", xml):
        link = cdata(raw, "link")
        title = cdata(raw, "title")
        pub = cdata(raw, "pubDate")
        if not (link and title):
            continue
        try:
            date = email.utils.parsedate_to_datetime(pub).strftime("%Y-%m-%d")
        except Exception:
            m = re.search(r"(\d{4})(\d{2})(\d{2})", link)
            date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""
        out.append((date, title, link))
    return out


def archive_speeches() -> list:
    """年次インデックスから理事時代のウォーシュ講演を拾う。"""
    found = []
    for year in ARCHIVE_YEARS:
        try:
            idx = get(f"{BASE}/newsevents/speech/{year}speech.htm")
        except urllib.error.HTTPError as e:
            print(f"  {year}年インデックス: {e}")
            continue
        for path, label in re.findall(
                r'href="(/newsevents/speech/warsh[^"]+)"[^>]*>(.*?)</a>', idx, re.I | re.S):
            title = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", label))).strip()
            m = re.search(r"warsh(\d{4})(\d{2})(\d{2})", path)
            date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else str(year)
            found.append((date, title, BASE + path))
        time.sleep(0.4)
    return found


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60]


def presser_text(date: str) -> tuple:
    """FOMC記者会見の逐語録(PDF)を取ってテキストにする。

    URLは会合最終日で決まる: FOMCpresconf{YYYYMMDD}.pdf
    見つからなければ (None, None) を返す。会見が無い会合もあるため。
    """
    url = f"{BASE}/mediacenter/files/FOMCpresconf{date.replace('-', '')}.pdf"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            blob = r.read()
    except Exception:
        return None, None
    try:
        import pypdf
    except ImportError:
        print("  pypdf が無いため会見PDFを飛ばします (pip install pypdf)")
        return None, None
    try:
        reader = pypdf.PdfReader(io.BytesIO(blob))
        text = "\n".join(p.extract_text() or "" for p in reader.pages)
    except Exception as e:
        print(f"  会見PDFの解析に失敗 {date}: {e}")
        return None, None
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return url, text


def resolve_minutes(url: str, raw: str) -> tuple:
    """議事要旨のプレスリリースは告知だけなので、本文ページへ辿る。

    告知ページ本文は800字程度しかなく、討議内容は
    /monetarypolicy/fomcminutes{YYYYMMDD}.htm 側にある(4〜5万字)。
    """
    m = re.search(r'href="(/monetarypolicy/fomcminutes\d+\.htm)"', raw)
    if not m:
        return url, raw
    full = BASE + m.group(1)
    try:
        return full, get(full)
    except Exception as e:
        print(f"  本文ページの取得に失敗、告知ページで保存します ({e})")
        return url, raw


def save(out_dir: str, date: str, title: str, url: str, role: str, force: bool) -> bool:
    """保存して、新規に取得したらTrueを返す。"""
    dest = os.path.join(out_dir, f"{date}_{slug(title)}.txt")
    if os.path.exists(dest) and not force:
        return False
    try:
        raw = get(url)
        if re.match(r"^Minutes of the Federal Open Market Committee", title, re.I):
            url, raw = resolve_minutes(url, raw)
        text = to_text(raw)
    except Exception as e:
        print(f"  FAIL  {date} {title[:44]} ({e})")
        return False
    header = f"# {title}\ndate: {date}\nrole: {role}\nsource: {url}\n\n"
    io.open(dest, "w", encoding="utf-8", newline="\n").write(header + text)
    print(f"  saved {date} [{role}] {title[:52]} ({len(text):,}字)")
    time.sleep(0.4)
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    os.makedirs(OUT_WARSH, exist_ok=True)
    os.makedirs(OUT_FOMC, exist_ok=True)

    # ---- 1. ウォーシュ本人の文書 -------------------------------------------
    docs = {}  # url -> (date, title, role)

    print("年次インデックス(理事時代)を確認しています...")
    for date, title, url in archive_speeches():
        docs[url] = (date, title, "governor")

    print("RSS(講演・議会証言)を確認しています...")
    for kind in ("speech", "testimony"):
        for date, title, url in feed_items(FEEDS[kind]):
            if "warsh" not in url.lower() and not title.lower().startswith("warsh"):
                continue
            role = "chair" if date >= CHAIR_SINCE else "governor"
            docs[url] = (date, title, role)

    new_warsh = 0
    for url, (date, title, role) in sorted(docs.items(), key=lambda kv: kv[1][0]):
        if save(OUT_WARSH, date, title, url, role, args.force):
            new_warsh += 1

    # ---- 2. 就任後のFOMC文書 -----------------------------------------------
    print("RSS(金融政策リリース)を確認しています...")
    fomc = []
    for date, title, url in feed_items(FEEDS["monetary"]):
        if date < CHAIR_SINCE:
            continue
        if not any(p.search(title) for p in FOMC_PATTERNS):
            continue
        fomc.append((date, title, url))

    new_fomc = 0
    for date, title, url in sorted(fomc):
        if save(OUT_FOMC, date, title, url, "fomc", args.force):
            new_fomc += 1

    # ---- 3. 記者会見の逐語録 ------------------------------------------------
    # 議長本人の言葉としては、量でも中身でもこれが一番厚い。声明の日=会合最終日に開かれる。
    # 記者の質問も含む逐語録なので、引用するときは発言者を確かめること。
    print("記者会見の逐語録を確認しています...")
    new_pc = 0
    pressers = []
    for date, title, _ in sorted(fomc):
        if "issues FOMC statement" not in title:
            continue
        pc_title = f"FOMC Press Conference (transcript), {date}"
        fname = f"{date}_{slug(pc_title)}.txt"
        dest = os.path.join(OUT_WARSH, fname)
        pc_url = f"{BASE}/mediacenter/files/FOMCpresconf{date.replace('-', '')}.pdf"
        entry = {"date": date, "title": pc_title, "role": "chair",
                 "source": pc_url, "file": fname}
        if os.path.exists(dest) and not args.force:
            pressers.append(entry)
            continue
        url, text = presser_text(date)
        if not text:
            continue
        pressers.append(entry)
        header = (f"# {pc_title}\ndate: {date}\nrole: chair\nsource: {url}\n"
                  f"note: 記者の質問を含む逐語録。引用時は発言者を確認すること。\n\n")
        io.open(dest, "w", encoding="utf-8", newline="\n").write(header + text)
        print(f"  saved {date} [chair] 記者会見 逐語録 ({len(text):,}字)")
        new_pc += 1
        time.sleep(0.4)

    io.open(os.path.join(OUT_FOMC, "index.json"), "w", encoding="utf-8",
            newline="\n").write(json.dumps(
                [{"date": d, "title": t, "role": "fomc", "source": u,
                  "file": f"{d}_{slug(t)}.txt"} for d, t, u in sorted(fomc)],
                ensure_ascii=False, indent=2) + "\n")

    # 会見の逐語録も warsh/ に入るので、索引は全部揃ってから書く
    index = [{"date": d, "title": t, "role": r, "source": u,
              "file": f"{d}_{slug(t)}.txt"}
             for u, (d, t, r) in docs.items()] + pressers
    index.sort(key=lambda i: (i["date"], i["title"]))
    io.open(os.path.join(OUT_WARSH, "index.json"), "w", encoding="utf-8",
            newline="\n").write(json.dumps(index, ensure_ascii=False, indent=2) + "\n")

    gov = sum(1 for i in index if i["role"] == "governor")
    chair = sum(1 for i in index if i["role"] == "chair")
    print(f"\n本人の文書: 理事時代 {gov}本 / 議長就任後 {chair}本 (新規 {new_warsh})")
    print(f"  うち記者会見の逐語録: {len(pressers)}本 (新規 {new_pc})")
    print(f"FOMC文書(就任後): {len(fomc)}本 (新規 {new_fomc})")
    if new_warsh or new_fomc or new_pc:
        print("新しい資料が入りました。")


if __name__ == "__main__":
    main()
