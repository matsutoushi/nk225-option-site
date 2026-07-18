# -*- coding: utf-8 -*-
"""マクロリスク指標の取得(FRED・NY連銀)。

- FRED: APIキー不要のCSVエンドポイント(fredgraph.csv)を使用
- NY連銀: イールドカーブ型の12ヶ月先景気後退確率(公式Excel)

方針: 予測はしない。公表値・市場織り込み値を閾値ベースの信号(green/yellow/red)で
機械的に表示する。閾値は学術・公式・市場慣行由来のものを使い、basisに明記する。
"""

import io
import json
import os
from datetime import datetime

import pandas as pd
import requests

UA = {"User-Agent": "Mozilla/5.0 (compatible; nk225-options-site)"}
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
FRED_API = ("https://api.stlouisfed.org/fred/series/observations"
            "?series_id={sid}&api_key={key}&file_type=json")
NYFED_XLS = "https://www.newyorkfed.org/medialibrary/media/research/capital_markets/allmonth.xls"

# 取得成功時にキャッシュし、CI等で取得失敗した場合のフォールバックに使う
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "data", "fred_cache")


def _cache_path(name: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, name)


def fetch_series(sid: str) -> pd.Series:
    """FREDの系列を取得する(index=日付, 値=float)。

    優先順: 公式API(FRED_API_KEY環境変数がある場合) → fredgraph CSV → ローカルキャッシュ
    """
    s = None
    api_key = os.environ.get("FRED_API_KEY")
    if api_key:
        try:
            r = requests.get(FRED_API.format(sid=sid, key=api_key), headers=UA, timeout=60)
            r.raise_for_status()
            obs = r.json()["observations"]
            df = pd.DataFrame(obs)
            s = pd.to_numeric(df["value"], errors="coerce")
            s.index = pd.to_datetime(df["date"])
            s = s.dropna()
        except Exception as e:
            print(f"WARN: FRED API failed for {sid}: {e}")
    if s is None:
        try:
            r = requests.get(FRED_CSV.format(sid=sid), headers=UA, timeout=60)
            r.raise_for_status()
            df = pd.read_csv(io.BytesIO(r.content))
            date_col, val_col = df.columns[0], df.columns[1]
            df[date_col] = pd.to_datetime(df[date_col])
            s = pd.to_numeric(df[val_col], errors="coerce")
            s.index = df[date_col]
            s = s.dropna()
        except Exception as e:
            print(f"WARN: fredgraph CSV failed for {sid}: {e}")
    if s is not None and len(s):
        s.rename("value").to_csv(_cache_path(f"{sid}.csv"))
        return s
    # フォールバック: キャッシュ
    cp = _cache_path(f"{sid}.csv")
    if os.path.exists(cp):
        print(f"INFO: using cached series for {sid}")
        df = pd.read_csv(cp, index_col=0, parse_dates=True)
        return df["value"].dropna()
    raise RuntimeError(f"no data and no cache for {sid}")


def fetch_nyfed_recprob() -> tuple[float, str]:
    """NY連銀の12ヶ月先景気後退確率(最新の予測値, 対象月)を返す。取得失敗時はキャッシュ。"""
    cp = _cache_path("nyfed_recprob.json")
    try:
        r = requests.get(NYFED_XLS, headers=UA, timeout=60)
        r.raise_for_status()
        df = pd.read_excel(io.BytesIO(r.content))
        df = df.dropna(subset=["Rec_prob"])
        last = df.iloc[-1]
        result = {"prob": float(last["Rec_prob"]) * 100,
                  "month": pd.Timestamp(last["Date"]).strftime("%Y-%m")}
        with open(cp, "w") as f:
            json.dump(result, f)
    except Exception as e:
        if not os.path.exists(cp):
            raise
        print(f"INFO: using cached NY Fed prob ({e})")
        result = json.load(open(cp))
    return result["prob"], result["month"]


def _signal(value: float, green, yellow, higher_is_worse=True) -> str:
    """閾値判定。green/yellowは境界値(それを超えたら次の段階)。"""
    if higher_is_worse:
        if value < green:
            return "green"
        if value < yellow:
            return "yellow"
        return "red"
    else:
        if value > green:
            return "green"
        if value > yellow:
            return "yellow"
        return "red"


def collect_indicators() -> dict:
    """全リスク指標を取得して信号付きで返す。

    Returns: {"date": 取得日, "groups": [{key, name, items: [indicator...]}], "series": {sid: Series}}
    indicator: {key, ja, en, value, disp, date, signal, basis_ja, basis_en}
    """
    cache = {}

    def get(sid):
        if sid not in cache:
            cache[sid] = fetch_series(sid)
        return cache[sid]

    items = []

    def add(group, key, ja, en, value, date, signal, basis_ja, basis_en, disp=None):
        items.append({"group": group, "key": key, "ja": ja, "en": en,
                      "value": value, "disp": disp or f"{value:,.2f}",
                      "date": date, "signal": signal,
                      "basis_ja": basis_ja, "basis_en": basis_en})

    def latest(sid):
        s = get(sid)
        return float(s.iloc[-1]), s.index[-1].strftime("%Y-%m-%d")

    # --- 景気後退リスク ---
    v, d = latest("SAHMREALTIME")
    add("recession", "sahm", "Sahmルール", "Sahm Rule", v, d,
        _signal(v, 0.30, 0.50), "0.50以上で景気後退入りの経験則(公式)",
        "0.50+ historically marks recession onset")

    s = get("ICSA")
    v4 = float(s.tail(4).mean())
    add("recession", "claims", "新規失業保険申請(4週平均)", "Initial Claims (4wk avg)",
        v4, s.index[-1].strftime("%Y-%m-%d"), _signal(v4, 280000, 350000),
        "28万件超で注意、35万件超で警告(歴史的水準)",
        "Caution above 280k, warning above 350k", disp=f"{v4/1000:,.0f}k")

    v, d = latest("T10Y3M")
    add("recession", "t10y3m", "イールドカーブ(10年-3ヶ月)", "Yield Curve (10y-3m)", v, d,
        _signal(-v, -0.25, 0.0), "逆転(マイナス)は歴史的に景気後退の先行シグナル",
        "Inversion has preceded recessions", disp=f"{v:+.2f}%")

    v, d = latest("T10Y2Y")
    add("recession", "t10y2y", "イールドカーブ(10年-2年)", "Yield Curve (10y-2y)", v, d,
        _signal(-v, -0.25, 0.0), "同上", "Same as above", disp=f"{v:+.2f}%")

    v, d = latest("RECPROUSM156N")
    add("recession", "cp_prob", "景気後退確率(Chauvet-Piger)", "Recession Prob. (Chauvet-Piger)",
        v, d, _signal(v, 20, 50), "セントルイス連銀公表の平滑化確率。50%超で警告",
        "St. Louis Fed smoothed probability", disp=f"{v:.1f}%")

    try:
        v, d = fetch_nyfed_recprob()
        add("recession", "nyfed_prob", "NY連銀 12ヶ月先景気後退確率", "NY Fed 12m Recession Prob.",
            v, d, _signal(v, 20, 35), "イールドカーブ型モデル(NY連銀公式)。歴史的に30%超は強い警告",
            "NY Fed yield-curve model; 30%+ is a strong signal", disp=f"{v:.1f}%")
    except Exception as e:
        print(f"WARN: NY Fed prob failed: {e}")

    # --- インフレ再燃リスク ---
    v, d = latest("T10YIE")
    add("inflation", "bei10", "期待インフレ率(10年BEI)", "10y Breakeven Inflation", v, d,
        _signal(v, 2.5, 3.0), "2.5%超で注意、3%超で警告(インフレ期待の脱錨)",
        "Caution above 2.5%, warning above 3%", disp=f"{v:.2f}%")

    v, d = latest("T5YIFR")
    add("inflation", "f5y5y", "期待インフレ率(5年先5年)", "5y5y Forward Inflation", v, d,
        _signal(v, 2.5, 3.0), "Fedが重視する長期期待インフレの指標",
        "Fed's preferred long-run expectations gauge", disp=f"{v:.2f}%")

    s = get("CPIAUCSL")
    yoy = float((s.iloc[-1] / s.iloc[-13] - 1) * 100)
    add("inflation", "cpi", "CPI(前年比)", "CPI (YoY)", yoy,
        s.index[-1].strftime("%Y-%m"), _signal(yoy, 3.0, 4.0),
        "3%超で注意、4%超で警告", "Caution above 3%, warning above 4%",
        disp=f"{yoy:.1f}%")

    s = get("PCEPILFE")
    yoy = float((s.iloc[-1] / s.iloc[-13] - 1) * 100)
    add("inflation", "corepce", "コアPCE(前年比)", "Core PCE (YoY)", yoy,
        s.index[-1].strftime("%Y-%m"), _signal(yoy, 2.5, 3.5),
        "Fed目標2%。2.5%超で注意", "Fed target 2%; caution above 2.5%",
        disp=f"{yoy:.1f}%")

    s = get("DCOILWTICO")
    cur = float(s.iloc[-1])
    ago = float(s[s.index <= s.index[-1] - pd.Timedelta(days=365)].iloc[-1])
    chg = (cur / ago - 1) * 100
    add("inflation", "wti", "WTI原油(前年比)", "WTI Crude (YoY)", chg,
        s.index[-1].strftime("%Y-%m-%d"), _signal(chg, 20, 50),
        "前年比+20%超で注意(エネルギー起点の再インフレ)",
        "Caution above +20% YoY", disp=f"${cur:,.0f} ({chg:+.0f}%)")

    # --- 金融ストレス ---
    v, d = latest("NFCI")
    add("stress", "nfci", "シカゴ連銀 金融環境指数", "Chicago Fed NFCI", v, d,
        _signal(v, 0.0, 0.5), "0超=歴史平均よりタイト(公式基準)",
        "Above 0 = tighter than average", disp=f"{v:+.2f}")

    v, d = latest("STLFSI4")
    add("stress", "stlfsi", "セントルイス連銀 金融ストレス指数", "St. Louis Fed Stress Index", v, d,
        _signal(v, 0.0, 1.0), "0超=平常よりストレス高(公式基準)",
        "Above 0 = above-normal stress", disp=f"{v:+.2f}")

    v, d = latest("BAMLH0A0HYM2")
    add("stress", "hy", "ハイイールド債スプレッド", "High Yield Spread", v, d,
        _signal(v, 4.0, 6.0), "4%超で注意、6%超で警告(信用不安)",
        "Caution above 4%, warning above 6%", disp=f"{v:.2f}%")

    v, d = latest("VIXCLS")
    add("stress", "vix", "VIX指数", "VIX", v, d,
        _signal(v, 20, 30), "20超で注意、30超で警告",
        "Caution above 20, warning above 30", disp=f"{v:.1f}")

    return {"date": datetime.now().strftime("%Y-%m-%d"), "items": items, "series": cache}
