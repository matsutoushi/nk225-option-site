# -*- coding: utf-8 -*-
"""米国市場データの取得。

- CFTC COT(建玉明細報告): 週次・公式Socrata API
    TFF(金融先物): レバレッジファンドのポジション
    Disaggregated(商品先物): マネージドマネーのポジション
- CBOE 日次Put/Callレシオ: 公式CDNのJSON
"""

import os
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
    {"key": "eur", "ja": "ユーロ先物", "en": "Euro FX",
     "ds": "gpe5-46if", "code": "099741", "cat": "lev"},
    {"key": "gbp", "ja": "ポンド先物", "en": "British Pound",
     "ds": "gpe5-46if", "code": "096742", "cat": "lev"},
    {"key": "gold", "ja": "金先物", "en": "Gold",
     "ds": "72hh-3qpy", "code": "088691", "cat": "mm"},
    {"key": "silver", "ja": "銀先物", "en": "Silver",
     "ds": "72hh-3qpy", "code": "084691", "cat": "mm"},
    {"key": "copper", "ja": "銅先物", "en": "Copper",
     "ds": "72hh-3qpy", "code": "085692", "cat": "mm"},
    {"key": "wti", "ja": "WTI原油先物", "en": "WTI Crude Oil",
     "ds": "72hh-3qpy", "code": "067411", "cat": "mm"},
    {"key": "natgas", "ja": "天然ガス先物", "en": "Natural Gas",
     "ds": "72hh-3qpy", "code": "023651", "cat": "mm"},
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
        try:
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
                raise RuntimeError("no rows")
            df = pd.DataFrame(rows)
            df["date"] = pd.to_datetime(df["report_date_as_yyyy_mm_dd"]).dt.date
            df["long"] = df[long_f].astype(float).astype(int)
            df["short"] = df[short_f].astype(float).astype(int)
            df["net"] = df["long"] - df["short"]
            df = df[["date", "long", "short", "net"]].sort_values("date").reset_index(drop=True)
            out[m["key"]] = df
            d = df["date"].iloc[-1]
            latest = max(latest, d) if latest else d
        except Exception as e:
            print(f"WARN: COT fetch failed for {m['key']}: {e}")
    if not out:
        raise RuntimeError("all COT markets failed")
    return {"date": str(latest), "markets": out}


CHAIN_URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/{sym}.json"
_OPT_RE = re.compile(r"^([A-Z]+?)W?(\d{6})([CP])(\d{8})$")


def fetch_chain(symbol: str, index: bool = False) -> dict:
    """CBOE遅延クオートからオプションチェーン(建玉・ガンマ・出来高入り)を取得する。

    symbol: "SPX"(index=True), "SPY", "QQQ" など
    Returns: {"spot": float, "chain": DataFrame[expiry, type, strike, oi, gamma, volume]}
    """
    sym = ("_" + symbol) if index else symbol
    r = requests.get(CHAIN_URL.format(sym=sym), headers=UA, timeout=90)
    r.raise_for_status()
    data = r.json()["data"]
    spot = float(data["close"])
    rows = []
    for o in data["options"]:
        m = _OPT_RE.match(o.get("option", ""))
        if not m:
            continue
        oi = o.get("open_interest") or 0
        vol = o.get("volume") or 0
        if oi <= 0 and vol <= 0:
            continue
        rows.append({
            "expiry": datetime.strptime(m.group(2), "%y%m%d").date(),
            "type": m.group(3),
            "strike": int(m.group(4)) / 1000,
            "oi": int(oi),
            "gamma": float(o.get("gamma") or 0),
            "volume": int(vol),
        })
    if not rows:
        raise RuntimeError(f"no option rows parsed for {symbol}")
    return {"spot": spot, "chain": pd.DataFrame(rows)}


def fetch_spx_chain() -> dict:
    return fetch_chain("SPX", index=True)


def nearest_expiry_share(spx: dict) -> dict:
    """最短限月(次の満期)の出来高シェア。0DTE的な超短期活動の目安。

    Returns: {"expiry": date, "share": float(0-1), "volume": int, "total": int}
    """
    df = spx["chain"]
    total = int(df["volume"].sum())
    if total == 0:
        raise RuntimeError("no volume data")
    nearest = df["expiry"].min()
    vol = int(df[df["expiry"] == nearest]["volume"].sum())
    return {"expiry": nearest, "share": vol / total, "volume": vol, "total": total}


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


# レバレッジETF(株価指数): (ティッカー, 符号付きレバレッジ, 原資産ラベル)
LETFS = [
    ("TQQQ", 3, "NASDAQ100"), ("SQQQ", -3, "NASDAQ100"), ("QLD", 2, "NASDAQ100"),
    ("SOXL", 3, "半導体(SOX)"), ("SOXS", -3, "半導体(SOX)"),
    ("SPXL", 3, "S&P500"), ("SPXS", -3, "S&P500"),
    ("UPRO", 3, "S&P500"), ("SPXU", -3, "S&P500"), ("SSO", 2, "S&P500"),
    ("TNA", 3, "ラッセル2000"), ("TZA", -3, "ラッセル2000"),
    ("UDOW", 3, "NYダウ"), ("SDOW", -3, "NYダウ"),
]
_LETF_CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "data", "letf_flow.json")


def fetch_letf_rebalance() -> dict:
    """レバレッジETFの引け推定リバランス・フローを計算する。

    一定レバレッジを保つための引けの売買額 = 純資産 × レバレッジ × (レバレッジ-1) × 原資産リターン。
    ブル・ベア問わず係数は正で、上昇日は買い・下落日は売り(値動きを増幅)。
    原資産リターンは ETFリターン ÷ レバレッジ で近似。

    取得失敗時はキャッシュにフォールバックする。
    Returns: {"total_bn": float, "items": [{sym, lev, underlying, aum_bn, ret_pct, flow_bn}...]}
    """
    import json
    import yfinance as yf
    items, total = [], 0.0
    for sym, lev, und in LETFS:
        try:
            t = yf.Ticker(sym)
            aum = t.info.get("totalAssets")
            hist = t.history(period="5d")
            if not aum or len(hist) < 2:
                continue
            etf_ret = float(hist["Close"].iloc[-1] / hist["Close"].iloc[-2] - 1)
            flow = aum * (lev - 1) * etf_ret  # = AUM×L(L-1)×原資産リターン
            total += flow
            items.append({"sym": sym, "lev": lev, "underlying": und,
                          "aum_bn": round(aum / 1e9, 2), "ret_pct": round(etf_ret * 100, 2),
                          "flow_bn": round(flow / 1e9, 3)})
        except Exception as e:
            print(f"WARN: LETF {sym} failed: {e}")
    if items:
        items.sort(key=lambda r: abs(r["flow_bn"]), reverse=True)
        result = {"total_bn": round(total / 1e9, 2), "items": items}
        try:
            os.makedirs(os.path.dirname(_LETF_CACHE), exist_ok=True)
            with open(_LETF_CACHE, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False)
        except Exception:
            pass
        return result
    if os.path.exists(_LETF_CACHE):
        print("INFO: using cached LETF flow")
        return json.load(open(_LETF_CACHE, encoding="utf-8"))
    raise RuntimeError("no LETF data and no cache")


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
