# -*- coding: utf-8 -*-
"""米国市場データの取得。

- CFTC COT(建玉明細報告): 週次・公式Socrata API
    TFF(金融先物): レバレッジファンドのポジション
    Disaggregated(商品先物): マネージドマネーのポジション
- CBOE 日次Put/Callレシオ: 公式CDNのJSON
"""

import json
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
    # 日次満期(0DTE)まで含める。SPXは残存1日以内が全体の6割を占めるため、
    # 短い限月を落とすと形そのものを取り違える。
    # ただし満期を過ぎた銘柄は除く。CBOEのチェーンには前営業日に満期を迎えた
    # 銘柄が建玉付きで残っており、下限を切らないとGEXが大きく水増しされる
    # (2026-08-14時点で、期限切れ分だけで合計の51%を占めていた)。
    today = datetime.now(timezone.utc).date()
    cutoff = today + timedelta(days=days)
    df = df[(df["expiry"] >= today) & (df["expiry"] <= cutoff)
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
_LETF_SHARES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "data", "letf_shares.json")

_SIZE_SUFFIX = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}


def _parse_size(s) -> float | None:
    """"501.60M" や "$37.82B" のような表記を数値にする。"""
    if isinstance(s, (int, float)):
        return float(s)
    if not s:
        return None
    m = re.fullmatch(r"\$?([\d,.]+)\s*([KMBT])?", str(s).strip())
    if not m:
        return None
    return float(m.group(1).replace(",", "")) * _SIZE_SUFFIX.get(m.group(2) or "", 1)


def refresh_letf_shares() -> dict:
    """レバレッジETFの口数(発行済口数)を更新して data/letf_shares.json に保存する。

    純資産 = 口数 × 基準価額 で、基準価額は終値とほぼ一致する。口数は設定・解約で
    動くため、放置すると残高の推定がずれていく。

    取得先はstockanalysis.com。Bloombergの EQY_SH_OUT と全14銘柄で突き合わせた
    ところ、誤差の中央値は0.97%で、残高の大きいTQQQ・SOXL・QLD・SSO・SPXLは
    いずれも0.1%以内だった(差が大きいのはSDOW等の小型のみで合計への影響は軽微)。

    取得できなかった銘柄は既存の値を残す。全滅した場合も既存ファイルをそのまま返す。
    """
    cur = {}
    try:
        with open(_LETF_SHARES, encoding="utf-8") as f:
            cur = json.load(f)
    except Exception:
        pass
    shares = dict(cur.get("shares", {}))

    got, failed = 0, []
    for sym, _lev, _und in LETFS:
        try:
            url = f"https://stockanalysis.com/etf/{sym.lower()}/__data.json"
            r = requests.get(url, headers=UA, timeout=25)
            r.raise_for_status()
            j = r.json()
            val = None
            for node in j.get("nodes", []):
                arr = node.get("data")
                if not isinstance(arr, list):
                    continue
                for elem in arr:
                    if isinstance(elem, dict) and "sharesOut" in elem:
                        i = elem["sharesOut"]
                        if isinstance(i, int) and 0 <= i < len(arr):
                            val = _parse_size(arr[i])
                        break
                if val:
                    break
            # 桁違いの値を拾って残高を壊さないよう、既存値から大きく動いた分は捨てる
            old = shares.get(sym)
            if val and old and not (0.5 <= val / old <= 2.0):
                failed.append(f"{sym}(前回比x{val/old:.1f}のため不採用)")
                continue
            if val:
                shares[sym] = round(val)
                got += 1
            else:
                failed.append(sym)
        except Exception as e:
            failed.append(f"{sym}({type(e).__name__})")

    if failed:
        print(f"WARN: LETF shares not updated: {', '.join(failed)}")
    if not got:
        print("INFO: using stored LETF shares")
        return cur
    out = {"asof": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
           "source": "stockanalysis.com", "shares": shares}
    try:
        with open(_LETF_SHARES, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
    except Exception as e:
        print(f"WARN: could not save LETF shares: {e}")
    print(f"LETF shares: {got}/{len(LETFS)} updated")
    return out


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

    # yfinanceのtotalAssetsは更新が遅く、実勢より1割ほど低く出ることがある
    # (2026-08-07時点でTQQQ -13.9%、SOXL -23.2%の乖離を確認)。
    # ETFの純資産は口数×基準価額で、基準価額は終値とほぼ一致するため、
    # 口数のスナップショット(letf_shares.json)があればそちらから算出する。
    # 口数は設定・解約で動くので、スナップショットは時々更新すること。
    shares = {}
    try:
        with open(_LETF_SHARES, encoding="utf-8") as f:
            shares = json.load(f).get("shares", {})
    except Exception:
        pass

    items, total = [], 0.0
    for sym, lev, und in LETFS:
        try:
            t = yf.Ticker(sym)
            hist = t.history(period="5d")
            if len(hist) < 2:
                continue
            px = float(hist["Close"].iloc[-1])
            aum = shares[sym] * px if sym in shares else t.info.get("totalAssets")
            if not aum:
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
