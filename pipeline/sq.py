# -*- coding: utf-8 -*-
"""SQ(特別清算数値)の算出日カレンダーと、過去のSQ値。

なぜ必要か:
  Search Console(2026-09-05)を見ると、sq 何時 / sq 時間 / sq 値 / sq いつ /
  sq日 / sq 気配 といったクエリが23語・44表示ぶん出ていた。
  ところが guide-sq.html の平均掲載順位は41.0で、ほぼ誰にも届いていない。
  検索意図は「概念の説明」ではなく「いつ・何時・いくらだったか」なので、
  そこを実データで答えられるようにする。

算出日の決め方(JPXの規則):
  SQ算出日  = 各限月の第2金曜日。休業日の場合は順次繰り上げる。
  取引最終日 = SQ算出日の前営業日。
  JPXの最終清算数値ページに「決定日は取引最終日の翌営業日」とある。

  第2金曜(8〜14日)に当たりうる国民の祝日は
  建国記念の日(2/11)と山の日(8/11)の2つだけ。
  成人の日・スポーツの日は第2月曜なので金曜には来ない。
  実測でも、2023-01以降で第2金曜が非営業日だったのは2023-08-11(山の日)のみで、
  この2つを見るだけで足りることを確認した。
"""

import datetime as dt
import io
import re

import pandas as pd
import requests

UA = {"User-Agent": "Mozilla/5.0 (compatible; nk225-options-site)"}
SQ_HIS_PDF = ("https://www.jpx.co.jp/markets/derivatives/special-quotation/"
              "mklp7700000028jz-att/sq_his.pdf")

MAJOR_MONTHS = (3, 6, 9, 12)
# 第2金曜・その前日に当たりうる国民の祝日(月日)
_HOLIDAYS = {(2, 11), (8, 11)}


def _closed(d: dt.date) -> bool:
    """取引所の休業日か。土日と、上の2つの祝日だけ見れば足りる。"""
    return d.weekday() >= 5 or (d.month, d.day) in _HOLIDAYS


def _prev_open(d: dt.date) -> dt.date:
    while _closed(d):
        d -= dt.timedelta(days=1)
    return d


def second_friday(year: int, month: int) -> dt.date:
    d = dt.date(year, month, 1)
    d += dt.timedelta(days=(4 - d.weekday()) % 7)   # その月の最初の金曜
    return d + dt.timedelta(days=7)


def sq_date(year: int, month: int) -> dt.date:
    """その限月のSQ算出日。第2金曜が休業日なら繰り上げる。"""
    return _prev_open(second_friday(year, month))


def last_trading_day(sq: dt.date) -> dt.date:
    """取引最終日(SQ算出日の前営業日)。"""
    return _prev_open(sq - dt.timedelta(days=1))


def upcoming(today: dt.date, count: int = 12) -> list[dict]:
    """今日以降のSQを古い順に返す。

    Returns: [{"month": "2026-09", "sq": date, "last": date,
               "major": bool, "days": 残り日数}]
    """
    out = []
    y, m = today.year, today.month
    while len(out) < count:
        s = sq_date(y, m)
        if s >= today:
            out.append({"month": f"{y}-{m:02d}", "sq": s,
                        "last": last_trading_day(s),
                        "major": m in MAJOR_MONTHS,
                        "days": (s - today).days})
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


# ---------------------------------------------------------------------------
# 過去のSQ値(JPXが公表しているPDFから)
# ---------------------------------------------------------------------------

_YEAR_RE = re.compile(r"^(\d{4})年(\d{1,2})月\s+([\d,]+\.\d+)")
_MONTH_RE = re.compile(r"^(\d{1,2})月\s+([\d,]+\.\d+)")


def fetch_sq_values() -> dict:
    """sq_his.pdf から {"YYYY-MM": 日経225のSQ値} を返す。

    PDFは1行1限月で、先頭が「2021年1月」または「2月」、
    その次の数字が日経225の最終清算数値。以降の列は他の指数なので読まない。
    """
    r = requests.get(SQ_HIS_PDF, headers=UA, timeout=60)
    r.raise_for_status()
    import pypdf
    reader = pypdf.PdfReader(io.BytesIO(r.content))
    out, year = {}, None
    for page in reader.pages:
        for line in (page.extract_text() or "").splitlines():
            line = line.strip()
            m = _YEAR_RE.match(line)
            if m:
                year = int(m.group(1))
                out[f"{year}-{int(m.group(2)):02d}"] = float(m.group(3).replace(",", ""))
                continue
            m = _MONTH_RE.match(line)
            if m and year:
                out[f"{year}-{int(m.group(1)):02d}"] = float(m.group(2).replace(",", ""))
    if len(out) < 12:
        raise RuntimeError(f"SQ history: parsed only {len(out)} rows — PDF format changed?")
    return out


def build_history(nikkei: pd.DataFrame | None = None) -> pd.DataFrame:
    """過去のSQ値に、算出日とその日の日経平均始値を並べる。

    SQ値は225銘柄それぞれの寄り付き値から作るので、
    「その日の日経平均の始値」とは一致しない。差を出せるようにしておく。

    Returns: DataFrame[month, sq_date, sq_value, nikkei_open, diff, major]
    """
    values = fetch_sq_values()
    opens = {}
    if nikkei is not None and len(nikkei):
        for _, r in nikkei.iterrows():
            opens[str(r["date"])] = float(r["始値"])
    rows = []
    for month, val in sorted(values.items()):
        y, m = int(month[:4]), int(month[5:])
        s = sq_date(y, m)
        op = opens.get(s.isoformat())
        rows.append({
            "month": month,
            "sq_date": s.isoformat(),
            "sq_value": round(val, 2),
            "nikkei_open": round(op, 2) if op is not None else None,
            "diff": round(val - op, 2) if op is not None else None,
            "major": m in MAJOR_MONTHS,
        })
    return pd.DataFrame(rows)
