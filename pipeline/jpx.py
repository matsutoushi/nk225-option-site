# -*- coding: utf-8 -*-
"""JPX公式サイトから日経225オプションの日次データを取得・解析する。

データ源(いずれも無料・毎日更新):
  https://www.jpx.co.jp/markets/derivatives/trading-volume/index.html
  - YYYYMMDD_derivatives_market_data_whole_day.xlsx : 商品別プット/コール出来高(PCR用)
  - YYYYMMDDopen_interest.xlsx : 行使価格別の建玉残高(別紙1=日経225オプション)

注意: JPXのページ構成・ファイル書式は予告なく変わりうる。
      パースに失敗したら例外を投げて前日の生成物を残す(サイトを壊さない)。
"""

import io
import re

import pandas as pd
import requests

UA = {"User-Agent": "Mozilla/5.0 (compatible; nk225-options-site)"}
INDEX_URL = "https://www.jpx.co.jp/markets/derivatives/trading-volume/index.html"
BASE = "https://www.jpx.co.jp"

# 例: NIKKEI 225 P2608-20000 → put, 2026年8月限, 行使価格20000
NAME_RE = re.compile(r"NIKKEI 225 ([PC])(\d{4})-(\d+)")


def discover_files() -> dict:
    """当日取引高ページから各データファイルのURLを見つける。"""
    r = requests.get(INDEX_URL, headers=UA, timeout=30)
    r.raise_for_status()
    links = re.findall(r'href="([^"]+\.(?:xlsx|csv))"', r.text)
    out = {}
    for l in links:
        if "whole_day" in l:
            out["whole_day"] = BASE + l
        elif "open_interest" in l:
            out["open_interest"] = BASE + l
    missing = {"whole_day", "open_interest"} - set(out)
    if missing:
        raise RuntimeError(f"JPX page layout changed? missing: {missing}")
    m = re.search(r"/(\d{8})_derivatives", out["whole_day"])
    if not m:
        raise RuntimeError(f"date not found in URL: {out['whole_day']}")
    out["date"] = m.group(1)
    return out


def _download(url: str) -> bytes:
    r = requests.get(url, headers=UA, timeout=60)
    r.raise_for_status()
    return r.content


def fetch_put_call_volume(url: str) -> dict:
    """whole_dayファイルから日経225オプション(ラージ)の日通しプット/コール出来高を返す。"""
    raw = pd.read_excel(io.BytesIO(_download(url)), sheet_name="market_data_OP", header=None)
    # 「Nikkei 225 Options」行から4行(夜間/前場/後場/合計)のうち合計行を探す
    prod_rows = raw.index[
        raw[1].astype(str).str.contains("Nikkei 225 Options", na=False)
        & ~raw[1].astype(str).str.contains("mini", na=False, case=False)
    ]
    if len(prod_rows) == 0:
        raise RuntimeError("Nikkei 225 Options row not found in whole_day file")
    start = prod_rows[0]
    for i in range(start, start + 6):
        if "Total" in str(raw.loc[i, 2]):
            put_vol = int(raw.loc[i, 3])
            call_vol = int(raw.loc[i, 5])
            return {"put_volume": put_vol, "call_volume": call_vol,
                    "pcr": round(put_vol / call_vol, 3) if call_vol else None}
    raise RuntimeError("Total row not found for Nikkei 225 Options")


def fetch_open_interest(url: str) -> pd.DataFrame:
    """open_interestファイルから日経225オプションの行使価格別建玉を返す。

    Returns: DataFrame[type(P/C), expiry(YYMM), strike, oi]
    """
    xls = pd.ExcelFile(io.BytesIO(_download(url)))
    rows = []
    for sheet in xls.sheet_names:
        raw = xls.parse(sheet, header=None)
        for col in raw.columns:
            series = raw[col].astype(str)
            hit = series.str.extract(NAME_RE)
            mask = hit[0].notna()
            if not mask.any():
                continue
            for idx in raw.index[mask]:
                m = NAME_RE.search(str(raw.loc[idx, col]))
                # 銘柄名の2列右が建玉残高(日中取引終了時点)
                try:
                    oi = int(raw.loc[idx, col + 2])
                except (ValueError, TypeError, KeyError):
                    continue
                rows.append({
                    "type": m.group(1),
                    "expiry": m.group(2),  # YYMM
                    "strike": int(m.group(3)),
                    "oi": oi,
                })
    if not rows:
        raise RuntimeError("no NIKKEI 225 option rows found in open_interest file")
    df = pd.DataFrame(rows).groupby(["type", "expiry", "strike"], as_index=False)["oi"].sum()
    return df


def nearest_expiry(df: pd.DataFrame) -> str:
    """建玉が最も多い直近限月(YYMM)を返す。"""
    totals = df.groupby("expiry")["oi"].sum()
    # 直近限月=辞書順最小(YYMM形式)。ただし建玉ゼロ同然の限月はスキップ
    for exp in sorted(totals.index):
        if totals[exp] > 1000:
            return exp
    return sorted(totals.index)[0]
