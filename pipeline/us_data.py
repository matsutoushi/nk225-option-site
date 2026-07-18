# -*- coding: utf-8 -*-
"""米国市場データの取得。

- CFTC COT(建玉明細報告): 週次・公式Socrata API
    TFF(金融先物): レバレッジファンドのポジション
    Disaggregated(商品先物): マネージドマネーのポジション
- CBOE 日次Put/Callレシオ: 公式CDNのJSON
"""

import re
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

UA = {"User-Agent": "Mozilla/5.0 (compatible; nk225-options-site)"}
COT_BASE = "https://publicreporting.cftc.gov/resource"
CBOE_URL = "https://cdn.cboe.com/data/us/options/market_statistics/daily/{date}_daily_options"

# cat: lev=TFFのレバレッジファンド, mm=Disaggregatedのマネージドマネー
COT_MARKETS = [
    {"key": "es", "ja": "S&P500先物(ES)", "en": "E-mini S&P 500",
     "ds": "gpe5-46if", "code": "13874A", "cat": "lev"},
    {"key": "nq", "ja": "ナスダック100先物(NQ)", "en": "E-mini Nasdaq-100",
     "ds": "gpe5-46if", "code": "209742", "cat": "lev"},
    {"key": "nikkei", "ja": "日経平均先物(CME・円建て)", "en": "Nikkei 225 (CME, yen)",
     "ds": "gpe5-46if", "code": "240743", "cat": "lev"},
    {"key": "jpy", "ja": "日本円先物", "en": "Japanese Yen",
     "ds": "gpe5-46if", "code": "097741", "cat": "lev"},
    {"key": "gold", "ja": "金先物", "en": "Gold",
     "ds": "72hh-3qpy", "code": "088691", "cat": "mm"},
    {"key": "wti", "ja": "WTI原油先物", "en": "WTI Crude Oil",
     "ds": "72hh-3qpy", "code": "067411", "cat": "mm"},
]

_FIELDS = {
    "lev": ("lev_money_positions_long", "lev_money_positions_short"),
    "mm": ("m_money_positions_long_all", "m_money_positions_short_all"),
}


def fetch_cot(weeks: int = 56) -> dict:
    """全対象市場のCOT履歴を取得する。

    Returns: {"date": 最新報告日(str), "markets": {key: DataFrame[date, long, short, net]}}
    """
    out = {}
    latest = None
    for m in COT_MARKETS:
        long_f, short_f = _FIELDS[m["cat"]]
        r = requests.get(f"{COT_BASE}/{m['ds']}.json", params={
            "$select": f"report_date_as_yyyy_mm_dd, {long_f}, {short_f}",
            "$where": f"cftc_contract_market_code='{m['code']}'",
            "$order": "report_date_as_yyyy_mm_dd DESC",
            "$limit": weeks,
        }, headers=UA, timeout=60)
        r.raise_for_status()
        rows = r.json()
        if not rows:
            raise RuntimeError(f"no COT rows for {m['key']}")
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["report_date_as_yyyy_mm_dd"]).dt.date
        df["long"] = df[long_f].astype(float).astype(int)
        df["short"] = df[short_f].astype(float).astype(int)
        df["net"] = df["long"] - df["short"]
        df = df[["date", "long", "short", "net"]].sort_values("date").reset_index(drop=True)
        out[m["key"]] = df
        d = df["date"].iloc[-1]
        latest = max(latest, d) if latest else d
    return {"date": str(latest), "markets": out}


SPX_URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/_SPX.json"
_OPT_RE = re.compile(r"^(SPXW?)(\d{6})([CP])(\d{8})$")


def fetch_spx_chain() -> dict:
    """SPX全オプションチェーン(建玉・ガンマ入り)を取得する。

    Returns: {"spot": float, "chain": DataFrame[expiry, type, strike, oi, gamma]}
    """
    r = requests.get(SPX_URL, headers=UA, timeout=90)
    r.raise_for_status()
    data = r.json()["data"]
    spot = float(data["close"])
    rows = []
    for o in data["options"]:
        m = _OPT_RE.match(o.get("option", ""))
        if not m:
            continue
        oi = o.get("open_interest") or 0
        if oi <= 0:
            continue
        rows.append({
            "expiry": datetime.strptime(m.group(2), "%y%m%d").date(),
            "type": m.group(3),
            "strike": int(m.group(4)) / 1000,
            "oi": int(oi),
            "gamma": float(o.get("gamma") or 0),
        })
    if not rows:
        raise RuntimeError("no SPX option rows parsed")
    return {"spot": spot, "chain": pd.DataFrame(rows)}


def spx_walls_and_gex(spx: dict, days: int = 45, band: float = 0.10) -> dict:
    """建玉の壁とネットGEX(ナイーブ推定)を行使価格別に集計する。

    GEXの想定(業界標準のナイーブ仮定): ディーラーはコール買い持ち・プット売り持ち
    → コールのガンマを正、プットのガンマを負として合算。
    GEX($) = gamma × OI × 100(乗数) × spot^2 × 1% で「指数1%変動あたりのドル建てガンマ」。
    """
    spot = spx["spot"]
    df = spx["chain"].copy()
    cutoff = datetime.now(timezone.utc).date() + timedelta(days=days)
    df = df[(df["expiry"] <= cutoff)
            & (df["strike"] >= spot * (1 - band)) & (df["strike"] <= spot * (1 + band))]

    walls = df.groupby(["type", "strike"], as_index=False)["oi"].sum()
    df["gex"] = df["gamma"] * df["oi"] * 100 * spot * spot * 0.01 \
        * df["type"].map({"C": 1, "P": -1})
    gex = df.groupby("strike", as_index=False)["gex"].sum()
    total_gex = float(df["gex"].sum())

    # ガンマフリップの近似: 下の行使価格から累積GEXの符号が変わる水準
    g = gex.sort_values("strike").reset_index(drop=True)
    g["cum"] = g["gex"].cumsum()
    flip = None
    sign = g["cum"].iloc[0] >= 0
    for _, row in g.iterrows():
        if (row["cum"] >= 0) != sign:
            flip = float(row["strike"])
            break
    return {"spot": spot, "walls": walls, "gex": gex,
            "total_gex": total_gex, "flip": flip}


def fetch_cboe_pcr() -> dict:
    """CBOEの直近営業日のPut/Callレシオを取得する。

    Returns: {"date": "YYYY-MM-DD", "total": float, "index": float,
              "equity": float, "spx": float, "vix": float}
    """
    now = datetime.now(timezone.utc)
    for back in range(1, 8):  # 米国の直近営業日を後ろ向きに探す
        d = (now - timedelta(days=back)).strftime("%Y-%m-%d")
        r = requests.get(CBOE_URL.format(date=d), headers=UA, timeout=30)
        if r.status_code != 200:
            continue
        try:
            ratios = {x["name"]: float(x["value"]) for x in r.json()["ratios"]}
        except Exception:
            continue
        return {
            "date": d,
            "total": ratios.get("TOTAL PUT/CALL RATIO"),
            "index": ratios.get("INDEX PUT/CALL RATIO"),
            "equity": ratios.get("EQUITY PUT/CALL RATIO"),
            "spx": ratios.get("SPX + SPXW PUT/CALL RATIO"),
            "vix": ratios.get("CBOE VOLATILITY INDEX (VIX) PUT/CALL RATIO"),
        }
    raise RuntimeError("no recent CBOE daily file found")
