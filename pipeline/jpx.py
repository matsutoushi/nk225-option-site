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
    """open_interestファイルから日経225オプションの行使価格別建玉と前日比を返す。

    ファイル内の列構成: 銘柄名称 | 取組高 | 建玉残高 | 増減 | 前日建玉残高
    Returns: DataFrame[type(P/C), expiry(YYMM), strike, oi, change]
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
                try:
                    oi = int(raw.loc[idx, col + 2])
                except (ValueError, TypeError, KeyError):
                    continue
                try:
                    change = int(raw.loc[idx, col + 3])
                except (ValueError, TypeError, KeyError):
                    change = 0
                rows.append({
                    "type": m.group(1),
                    "expiry": m.group(2),  # YYMM
                    "strike": int(m.group(3)),
                    "oi": oi,
                    "change": change,
                })
    if not rows:
        raise RuntimeError("no NIKKEI 225 option rows found in open_interest file")
    df = pd.DataFrame(rows).groupby(["type", "expiry", "strike"], as_index=False)[["oi", "change"]].sum()
    return df


# ---------------------------------------------------------------------------
# 週次: 指数先物 取引参加者別建玉残高(旧・手口の後継データ)
# ---------------------------------------------------------------------------

OI_YEARLIST = BASE + "/automation/markets/derivatives/open-interest/json/open_interest_yearlist.json"
SECTION_RE = re.compile(r"＜(.+?)＞")


def _weekly_file_list() -> list[dict]:
    """週次・取引参加者別建玉のファイル一覧(新しい順)を返す。"""
    years = requests.get(OI_YEARLIST, headers=UA, timeout=30).json()["TableDatas"]
    entries = []
    for y in years[:2]:  # 直近2年分あれば十分
        data = requests.get(BASE + y["Jsonfile"], headers=UA, timeout=30).json()["TableDatas"]
        entries.extend(data)
    entries.sort(key=lambda e: e["TradeDate"], reverse=True)
    return entries


def _parse_participant_futures(content: bytes) -> pd.DataFrame:
    """indexfut_oi_by_tp.xlsx をパースする。

    Returns: DataFrame[product, expiry, participant, net] (net: 買超+/売超-)
    """
    raw = pd.ExcelFile(io.BytesIO(content)).parse(0, header=None)
    rows = []
    product = None
    for _, r in raw.iterrows():
        c0 = str(r.iloc[0]) if pd.notna(r.iloc[0]) else ""
        m = SECTION_RE.search(c0)
        if m:
            product = m.group(1)
            continue
        if product is None:
            continue
        # ランク行: col0=順位(数値), col1=限月
        try:
            int(float(r.iloc[0]))
        except (ValueError, TypeError):
            continue
        expiry = str(r.iloc[1]) if pd.notna(r.iloc[1]) else ""
        # 売超側: col3=参加者名, col4=枚数 / 買超側: col6=参加者名, col7=枚数
        for name_col, qty_col, sign in ((3, 4, -1), (6, 7, +1)):
            name = r.iloc[name_col] if len(r) > qty_col else None
            qty = r.iloc[qty_col] if len(r) > qty_col else None
            if pd.notna(name) and pd.notna(qty):
                rows.append({
                    "product": product,
                    "expiry": expiry,
                    "participant": str(name).strip(),
                    "net": sign * int(float(qty)),
                })
    if not rows:
        raise RuntimeError("no participant rows parsed from weekly futures file")
    return pd.DataFrame(rows)


def update_participant_history(cache: pd.DataFrame | None, weeks: int = 52) -> pd.DataFrame:
    """週次の参加者別建玉の履歴を更新する(不足している週だけ取得)。

    cache: DataFrame[date(str YYYYMMDD), product, participant, net] または None
    Returns: 直近weeks週分に整えた履歴DataFrame
    """
    entries = _weekly_file_list()[:weeks]
    have = set(cache["date"].astype(str)) if cache is not None and len(cache) else set()
    frames = [cache] if cache is not None and len(cache) else []
    fetched = 0
    for e in entries:
        if e["TradeDate"] in have:
            continue
        df = _parse_participant_futures(_download(BASE + e["IndexFutures"]))
        agg = df.groupby(["product", "participant"], as_index=False)["net"].sum()
        agg.insert(0, "date", e["TradeDate"])
        frames.append(agg)
        fetched += 1
    print(f"participant history: fetched {fetched} new weekly files")
    hist = pd.concat(frames, ignore_index=True)
    keep = {e["TradeDate"] for e in entries}
    hist = hist[hist["date"].astype(str).isin(keep)]
    return hist.sort_values(["date", "product", "participant"]).reset_index(drop=True)


def fetch_weekly_participant_futures() -> dict:
    """直近2週分の参加者別建玉を取得し、最新週+前週比を返す。

    Returns: {date, prev_date, data: DataFrame[product, participant, net, net_prev, change]}
    """
    entries = _weekly_file_list()
    latest, prev = entries[0], entries[1]

    def load(entry):
        df = _parse_participant_futures(_download(BASE + entry["IndexFutures"]))
        # 限月をまたいで参加者ごとのネットを合算
        return df.groupby(["product", "participant"], as_index=False)["net"].sum()

    cur, before = load(latest), load(prev)
    merged = cur.merge(before, on=["product", "participant"],
                       how="outer", suffixes=("", "_prev")).fillna(0)
    merged["net"] = merged["net"].astype(int)
    merged["net_prev"] = merged["net_prev"].astype(int)
    merged["change"] = merged["net"] - merged["net_prev"]
    return {"date": latest["TradeDate"], "prev_date": prev["TradeDate"], "data": merged}


NIKKEI_CSV = "https://indexes.nikkei.co.jp/nkave/historical/nikkei_stock_average_daily_jp.csv"
NIKKEI_VI_CSV = "https://indexes.nikkei.co.jp/nkave/historical/nikkei_stock_average_vi_daily_jp.csv"
MINI_RE = re.compile(r"NK225 MINI ([PC])(\d{6})-(\d+)")
INVESTOR_URL = "https://www.jpx.co.jp/markets/statistics-equities/investor-type/index.html"


def fetch_nikkei_vi() -> pd.DataFrame:
    """日経公式CSVから日経VI(ボラティリティー・インデックス)のOHLCを取得する。"""
    r = requests.get(NIKKEI_VI_CSV, headers=UA, timeout=60)
    r.raise_for_status()
    df = pd.read_csv(io.BytesIO(r.content), encoding="shift_jis")
    df = df.rename(columns={"データ日付": "date", "終値": "Close", "始値": "Open",
                            "高値": "High", "安値": "Low"})
    df["date"] = pd.to_datetime(df["date"], format="%Y/%m/%d", errors="coerce")
    df = df.dropna(subset=["date", "Close"]).set_index("date").sort_index()
    return df[["Open", "High", "Low", "Close"]].astype(float)


def fetch_mini_oi(url: str) -> pd.DataFrame:
    """open_interestファイルからミニオプション(ウィークリー限月含む)の建玉を返す。

    Returns: DataFrame[type(P/C), expiry(date), strike, oi]
    """
    xls = pd.ExcelFile(io.BytesIO(_download(url)))
    rows = []
    for sheet in xls.sheet_names:
        raw = xls.parse(sheet, header=None)
        for col in raw.columns:
            series = raw[col].astype(str)
            if not series.str.contains("NK225 MINI", na=False).any():
                continue
            for idx in raw.index[series.str.contains("NK225 MINI", na=False)]:
                m = MINI_RE.search(str(raw.loc[idx, col]))
                if not m:
                    continue
                try:
                    oi = int(raw.loc[idx, col + 2])
                except (ValueError, TypeError, KeyError):
                    continue
                rows.append({
                    "type": m.group(1),
                    "expiry": pd.to_datetime("20" + m.group(2), format="%Y%m%d").date(),
                    "strike": int(m.group(3)),
                    "oi": oi,
                })
    if not rows:
        raise RuntimeError("no NK225 MINI option rows found")
    return pd.DataFrame(rows).groupby(["type", "expiry", "strike"], as_index=False)["oi"].sum()


def _parse_investor_foreign_net(content: bytes) -> float | None:
    """投資部門別xlsから海外投資家のネット売買(買い−売り、単位:千円)を返す。"""
    raw = pd.read_excel(io.BytesIO(content), header=None)
    for i in raw.index:
        if str(raw.iloc[i, 0]).strip() == "海外投資家":
            try:
                sales = float(str(raw.iloc[i, 4]).replace(",", ""))
                purchases = float(str(raw.iloc[i + 1, 4]).replace(",", ""))
                return purchases - sales
            except (ValueError, TypeError, KeyError):
                return None
    return None


INVESTOR_DIR = "/markets/statistics-equities/investor-type/"


def _investor_week_files(years_back: int = 5) -> dict:
    """週次の投資部門別ファイル一覧 {YYMMW: path} を返す。

    JPXはトップに直近5週、アーカイブ(00-00-archives-NN.html、NN=0が今年)に年別で
    2016年分まで掲載している。years_back でどこまで遡るかを指定する。
    """
    weeks = {}
    pages = ["index.html"] + [f"00-00-archives-{n:02d}.html" for n in range(years_back + 1)]
    for p in pages:
        try:
            r = requests.get(BASE + INVESTOR_DIR + p, headers=UA, timeout=60)
            if r.status_code != 200:
                continue
        except Exception:
            continue
        for path, code in re.findall(r'href="([^"]+stock_val_1_(\d{6})\.xls)"', r.text):
            weeks[code] = path
    return weeks


def _parse_investor_weekly(content: bytes) -> tuple[float, str] | None:
    """週次xlsから海外投資家のネット売買(千円)と週末日付を返す。

    週次ファイルは2週分を並記し、ファイル名の週(見出し週)は右ブロック(col8)。
    行10のcol7に「MM/DD～MM/DD」の期間、行3に「YYYY年M月第N週」がある。
    """
    raw = pd.read_excel(io.BytesIO(content), header=None)
    net = None
    for i in raw.index:
        if str(raw.iloc[i, 0]).strip() == "海外投資家":
            try:
                sales = float(str(raw.iloc[i, 8]).replace(",", ""))
                purchases = float(str(raw.iloc[i + 1, 8]).replace(",", ""))
                net = purchases - sales
            except (ValueError, TypeError, KeyError):
                return None
            break
    if net is None:
        return None

    # 週末日付(YYYY-MM-DD)を組み立てる
    year = None
    for i in range(min(6, len(raw))):
        m = re.search(r"(\d{4})年", str(raw.iloc[i, 0]))
        if m:
            year = int(m.group(1))
            break
    date = ""
    if year:
        for i in range(min(14, len(raw))):
            m = re.search(r"(\d{2})/(\d{2})[~～](\d{2})/(\d{2})", str(raw.iloc[i, 7]))
            if m:
                mm, dd = int(m.group(3)), int(m.group(4))
                date = f"{year:04d}-{mm:02d}-{dd:02d}"
                break
    return net, date


def fetch_investor_flows(cache: pd.DataFrame | None, years_back: int = 5) -> pd.DataFrame:
    """海外投資家の週次ネット売買(東証プライム・現物金額)を取得・蓄積する。

    Returns: DataFrame[week(str YYMMW), date(str YYYY-MM-DD), net_kyen(千円)]
    """
    files = _investor_week_files(years_back)
    have = set(cache["week"].astype(str)) if cache is not None and len(cache) else set()
    rows = []
    for code, path in sorted(files.items()):
        if code in have:
            continue
        parsed = _parse_investor_weekly(_download(BASE + path))
        if parsed is None:
            print(f"WARN: investor weekly parse failed for {code}")
            continue
        net, date = parsed
        rows.append({"week": code, "date": date, "net_kyen": net})
    print(f"investor flows: fetched {len(rows)} new weekly files")
    frames = ([cache] if cache is not None and len(cache) else []) + \
             ([pd.DataFrame(rows)] if rows else [])
    if not frames:
        raise RuntimeError("no investor flow data")
    hist = pd.concat(frames, ignore_index=True)
    hist["week"] = hist["week"].astype(str).str.zfill(6)
    hist = hist[hist["week"].str.fullmatch(r"\d{6}")]
    return hist.drop_duplicates("week").sort_values("week").reset_index(drop=True)


def fetch_n225_official() -> pd.DataFrame:
    """日経公式サイトの日次CSVから日経平均のOHLCを取得する。

    Returns: DataFrame[Open, High, Low, Close] (index: 日付, 昇順)
    """
    r = requests.get(NIKKEI_CSV, headers=UA, timeout=60)
    r.raise_for_status()
    df = pd.read_csv(io.BytesIO(r.content), encoding="shift_jis")
    df = df.rename(columns={"データ日付": "date", "終値": "Close", "始値": "Open",
                            "高値": "High", "安値": "Low"})
    # 末尾の著作権表記行などを除外
    df["date"] = pd.to_datetime(df["date"], format="%Y/%m/%d", errors="coerce")
    df = df.dropna(subset=["date", "Close"]).set_index("date").sort_index()
    return df[["Open", "High", "Low", "Close"]].astype(float)


def nearest_expiry(df: pd.DataFrame) -> str:
    """建玉が最も多い直近限月(YYMM)を返す。"""
    totals = df.groupby("expiry")["oi"].sum()
    # 直近限月=辞書順最小(YYMM形式)。ただし建玉ゼロ同然の限月はスキップ
    for exp in sorted(totals.index):
        if totals[exp] > 1000:
            return exp
    return sorted(totals.index)[0]
