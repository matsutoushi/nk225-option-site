# -*- coding: utf-8 -*-
"""Bloombergから日経225オプションのティック(約定と気配)を取得する(分析用・非公開)。

tools/leeready.py が読む形のCSVを private/bbg/ に書き出す。

【前提】
  - 同じPCでBloombergターミナルにログインしていること(Desktop APIはlocalhost:8194)
  - blpapi が入っていること:
      pip install --index-url=https://blpapi.bloomberg.com/repository/releases/python/simple/ blpapi

【使い方】
  # 取れるか確認(1銘柄だけ・当日分)
  python tools/bbg_fetch.py --check

  # 現値±7%の行使価格、期近2限月、直近3営業日分を取得
  python tools/bbg_fetch.py --days 3 --band 0.07

  # 取得したあと、そのままLee-Readyの集計まで行う
  python tools/bbg_fetch.py --days 3 --then-analyze

【ティッカーの形】
  日経225オプションは "NKY 10/09/26 C66000 Index" の形が標準(限月のSQ日・C/P・行使価格)。
  環境によって違う場合は --template で変えられる。使える記号:
      {mm} {dd} {yy} 満期日(SQ日)  {cp} C/P  {k} 行使価格(整数)
  例: --template "NKY {mm}/{dd}/{yy} {cp}{k} Index"

【取り扱い】
  Bloombergのデータは契約者本人の利用に限る。出力先の private/ は .gitignore 済みで、
  GitHubにも公開サイトにも出ない。サイトのガンマ推定はJPXの公表データだけで作る。
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
OUT_DIR = os.path.join(ROOT, "private", "bbg")
JST = dt.timezone(dt.timedelta(hours=9))
DEFAULT_TEMPLATE = "NKY {mm}/{dd}/{yy} {cp}{k} Index"


# ---------------------------------------------------------------------------
# 取得する銘柄を決める
# ---------------------------------------------------------------------------

def target_contracts(band: float, expiries: int) -> tuple[list[dict], float, str]:
    """JPXの清算値段ファイルから、取りに行く銘柄(限月・行使価格・C/P)を組み立てる。

    現値から band の範囲、125円刻みの行使価格、期近から expiries 限月分。"""
    import jpx
    import sq as sq_mod
    s = jpx.fetch_option_settlement()
    spot = float(s["spot"])
    df = s["data"]
    months = sorted(e for e in df["expiry"].unique() if len(str(e)) == 4)
    months = months[:expiries]
    out = []
    for e in months:
        g = df[(df["expiry"] == e) & (df["strike"] % 125 == 0)]
        lo, hi = spot * (1 - band), spot * (1 + band)
        g = g[(g["strike"] >= lo) & (g["strike"] <= hi)]
        y, m = 2000 + int(str(e)[:2]), int(str(e)[2:])
        exp_date = sq_mod.sq_date(y, m)          # SQ日(第2金曜、休業日なら繰り上げ)
        for r in g.itertuples():
            out.append({"expiry": str(e), "strike": int(r.strike), "type": r.type,
                        "exp_date": exp_date, "days": int(r.days)})
    return out, spot, s["date"]


def ticker_of(c: dict, template: str) -> str:
    d = c["exp_date"]
    return template.format(mm=f"{d.month:02d}", dd=f"{d.day:02d}", yy=f"{d.year % 100:02d}",
                           cp=c["type"], k=c["strike"])


# ---------------------------------------------------------------------------
# Bloomberg Desktop API
# ---------------------------------------------------------------------------

def open_session():
    try:
        import blpapi
    except ImportError:
        print("blpapi が入っていません。Bloombergターミナルにログインした状態で、次を実行してください:")
        print("  pip install --index-url=https://blpapi.bloomberg.com/repository/releases/python/simple/ blpapi")
        return None, None
    opts = blpapi.SessionOptions()
    opts.setServerHost("localhost")
    opts.setServerPort(8194)
    session = blpapi.Session(opts)
    if not session.start():
        print("Bloombergに接続できませんでした。ターミナルにログインしているか確認してください。")
        return None, None
    if not session.openService("//blp/refdata"):
        print("//blp/refdata を開けませんでした。")
        session.stop()
        return None, None
    return session, blpapi


def fetch_ticks(session, blpapi, ticker: str, start: dt.datetime, end: dt.datetime,
                events=("TRADE", "BID", "ASK")) -> pd.DataFrame:
    """IntradayTickRequest で約定と気配を取る。時刻はUTC指定、返りもUTC。"""
    svc = session.getService("//blp/refdata")
    req = svc.createRequest("IntradayTickRequest")
    req.set("security", ticker)
    for e in events:
        req.append("eventTypes", e)
    req.set("startDateTime", start)
    req.set("endDateTime", end)
    req.set("includeConditionCodes", True)
    session.sendRequest(req)
    rows = []
    while True:
        ev = session.nextEvent(60000)
        for msg in ev:
            if msg.hasElement("responseError"):
                print(f"  エラー({ticker}): {msg.getElement('responseError')}")
                return pd.DataFrame()
            if not msg.hasElement("tickData"):
                continue
            data = msg.getElement("tickData").getElement("tickData")
            for i in range(data.numValues()):
                it = data.getValueAsElement(i)
                rows.append({
                    "time": it.getElementAsDatetime("time"),
                    "type_ev": it.getElementAsString("type"),
                    "value": it.getElementAsFloat("value"),
                    "size": (it.getElementAsInteger("size")
                             if it.hasElement("size") else 0),
                })
        if ev.eventType() == blpapi.Event.RESPONSE:
            break
    return pd.DataFrame(rows)


def to_lee_ready_csv(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """約定の行に、その時点の直近の買い気配・売り気配を付ける。"""
    if not len(raw):
        return pd.DataFrame()
    raw = raw.sort_values("time")
    trades = raw[raw["type_ev"] == "TRADE"].copy()
    if not len(trades):
        return pd.DataFrame()
    out = trades[["time", "value", "size"]].rename(columns={"value": "price"})
    for side, name in (("BID", "bid"), ("ASK", "ask")):
        q = raw[raw["type_ev"] == side][["time", "value"]].rename(columns={"value": name})
        if len(q):
            out = pd.merge_asof(out.sort_values("time"), q.sort_values("time"),
                                on="time", direction="backward")
        else:
            out[name] = pd.NA
    out["ticker"] = ticker
    # UTC → JST(見るときのため。判定そのものには影響しない)
    out["time"] = pd.to_datetime(out["time"]).dt.tz_localize("UTC").dt.tz_convert(JST).dt.tz_localize(None)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3, help="さかのぼる日数(暦日)")
    ap.add_argument("--band", type=float, default=0.07, help="現値からの範囲(0.07=±7%%)")
    ap.add_argument("--expiries", type=int, default=2, help="期近から何限月")
    ap.add_argument("--template", default=DEFAULT_TEMPLATE, help="ティッカーの形")
    ap.add_argument("--check", action="store_true", help="1銘柄だけ試して形式を確認する")
    ap.add_argument("--then-analyze", action="store_true", help="取得後にleeready.pyの集計まで行う")
    args = ap.parse_args()

    contracts, spot, sdate = target_contracts(args.band, args.expiries)
    if not contracts:
        print("対象の銘柄が作れませんでした。")
        return
    print(f"JPXの清算値段({sdate})より、日経平均 {spot:,.0f}円。対象 {len(contracts)}銘柄")
    if args.check:
        contracts = contracts[len(contracts) // 2:len(contracts) // 2 + 1]
        print(f"確認のため1銘柄だけ取得します: {ticker_of(contracts[0], args.template)}")

    session, blpapi = open_session()
    if session is None:
        return
    end = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    start = end - dt.timedelta(days=args.days)
    os.makedirs(OUT_DIR, exist_ok=True)
    total, saved = 0, 0
    try:
        for i, c in enumerate(contracts, 1):
            tk = ticker_of(c, args.template)
            raw = fetch_ticks(session, blpapi, tk, start, end)
            df = to_lee_ready_csv(raw, tk)
            if len(df):
                # 毎日少しずつ取って積み上げる。同じ約定は重複させない。
                name = f"{c['expiry']}_{c['type']}{c['strike']}.csv"
                path = os.path.join(OUT_DIR, name)
                if os.path.exists(path):
                    try:
                        prev = pd.read_csv(path, parse_dates=["time"])
                        df = pd.concat([prev, df], ignore_index=True)
                    except Exception:
                        pass
                df = (df.drop_duplicates(subset=["time", "price", "size", "ticker"])
                        .sort_values("time"))
                df.to_csv(path, index=False)
                saved += 1
                total += len(df)
            print(f"  [{i}/{len(contracts)}] {tk}: 累計 {len(df):,}件")
    finally:
        session.stop()

    print(f"\n{saved}銘柄・約定 {total:,}件を {OUT_DIR} に保存しました")
    if total == 0:
        print("0件でした。ティッカーの形が違う可能性があります。")
        print("ターミナルの銘柄画面に出ている表記を教えてもらえれば、--template を合わせます。")
        return
    if args.then_analyze:
        print()
        os.system(f'"{sys.executable}" "{os.path.join(ROOT, "tools", "leeready.py")}"')


if __name__ == "__main__":
    main()
