# -*- coding: utf-8 -*-
"""ディーラーの持ち高を「量=建玉・向き=Lee-Ready」で推定する(分析用・非公開)。

【考え方】
JPXの建玉は「何枚増えた/減った」は分かるが、買い建てか売り建てかは分からない。
Bloombergのティックは向きは分かるが、立会外(J-NET)など出てこない売買がある。
そこで役割を分ける。

  その日・その行使価格について
    偏り w = (買い仕掛けの枚数 − 売り仕掛けの枚数) ÷ (買い + 売り)     … −1〜+1
    顧客の持ち高の変化 = w × |建玉の増減|
    ディーラーの持ち高の変化 = −(顧客の持ち高の変化)

  建玉が増えた日は新しく作られた分、減った日は閉じられた分に、その日の向きを当てる。
  これを毎日積み上げたものを「今の持ち高」とし、ガンマに換算する。

【確からしさ】
  カバー率 = その日のティック出来高 ÷ |建玉の増減|
  これが小さい日は、ティックに出ない売買で建玉が動いた可能性が高い。
  既定では 0.3 未満の日を除く(--min-coverage で変更可)。
  偏り w の絶対値が小さい日も、向きが定まらないので効きは小さくなる。

【前提の限界】
  「仕掛けた側=顧客、受けた側=ディーラー」は必ずしも成り立たない。
  積み上げの開始日より前の持ち高は分からないので、開始日をゼロとした推定になる。

【使い方】
  python tools/bbg_fetch.py --days 30 --band 0.05 --expiries 2   # ティック取得
  python tools/dealer_inventory.py                               # 本スクリプト

  出力: private/dealer_inventory_<日時>.csv / .png
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
IN_DIR = os.path.join(ROOT, "private", "bbg")
OUT_DIR = os.path.join(ROOT, "private")
DATA = os.path.join(ROOT, "data")
MULT = 1000
CUTOFF_HOUR = 16.5      # これ以降(JST)の約定は、翌営業日のセッションとして扱う


def business_days() -> list[str]:
    """建玉ファイルのある日=JPXの営業日(YYYYMMDD)。"""
    days = [re.search(r"oi_(\d{8})\.csv$", f).group(1)
            for f in glob.glob(os.path.join(DATA, "oi_*.csv"))]
    return sorted(days)


def trading_day_of(ts: pd.Timestamp, days: list[str]) -> str | None:
    """約定時刻(JST)を、JPXの取引日に割り当てる。

    夕方以降のナイトセッションは翌営業日の扱い。祝日の取引も、次の営業日に入る。"""
    d = ts.date()
    if ts.hour + ts.minute / 60 >= CUTOFF_HOUR:
        d = d + timedelta(days=1)
    s = d.strftime("%Y%m%d")
    for x in days:                      # その日以降で最初の営業日へ送る
        if x >= s:
            return x
    return None


def daily_flow(days: list[str]) -> pd.DataFrame:
    """ティックを読み、取引日×行使価格ごとの買い/売り仕掛けの枚数を返す。"""
    from leeready import load_ticks, classify
    files = sorted(glob.glob(os.path.join(IN_DIR, "**", "*.csv"), recursive=True))
    parts = [load_ticks(f) for f in files]
    parts = [p for p in parts if len(p)]
    if not parts:
        return pd.DataFrame()
    df = classify(pd.concat(parts, ignore_index=True))
    df = df[df["time"].notna()]
    df["day"] = [trading_day_of(t, days) for t in df["time"]]
    df = df[df["day"].notna()]
    df["buy"] = np.where(df["sign"] > 0, df["size"], 0)
    df["sell"] = np.where(df["sign"] < 0, df["size"], 0)
    return (df.groupby(["day", "expiry", "type", "strike"], as_index=False)
              .agg(buy=("buy", "sum"), sell=("sell", "sum"), vol=("size", "sum")))


def daily_oi() -> pd.DataFrame:
    """日次の建玉と前日比。"""
    rows = []
    for f in sorted(glob.glob(os.path.join(DATA, "oi_*.csv"))):
        d = re.search(r"oi_(\d{8})\.csv$", f).group(1)
        x = pd.read_csv(f)
        x["day"] = d
        rows.append(x[["day", "type", "expiry", "strike", "oi", "change"]])
    out = pd.concat(rows, ignore_index=True)
    out["expiry"] = out["expiry"].astype(str)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-coverage", type=float, default=0.3,
                    help="その日のティック出来高÷|建玉増減| がこれ未満の日は使わない")
    ap.add_argument("--spot", type=float, default=None)
    ap.add_argument("--mode", choices=("weighted", "sign"), default="weighted",
                    help="weighted: 偏りの大きさをそのまま掛ける(控えめ) / "
                         "sign: その日の建玉の増減すべてを、偏りの向きに割り当てる(強め)")
    args = ap.parse_args()

    days = business_days()
    flow = daily_flow(days)
    if not len(flow):
        print(f"ティックがありません: {IN_DIR}")
        print("先に python tools/bbg_fetch.py を実行してください。")
        return
    oi = daily_oi()
    flow["expiry"] = flow["expiry"].astype(str)
    flow["strike"] = flow["strike"].astype(float)
    oi["strike"] = oi["strike"].astype(float)

    m = flow.merge(oi, on=["day", "expiry", "type", "strike"], how="inner")
    if not len(m):
        print("ティックと建玉を突き合わせられませんでした(限月や行使価格の形式をご確認ください)。")
        return
    m["w"] = (m["buy"] - m["sell"]) / (m["buy"] + m["sell"]).replace(0, np.nan)
    m["w"] = m["w"].fillna(0.0)
    m["dOI"] = m["change"].abs()
    m["coverage"] = m["vol"] / m["dOI"].replace(0, np.nan)
    used = m[(m["dOI"] > 0) & (m["coverage"] >= args.min_coverage)].copy()
    skipped = m[(m["dOI"] > 0) & (m["coverage"] < args.min_coverage)]
    weight = used["w"] if args.mode == "weighted" else np.sign(used["w"])
    used["customer"] = weight * used["dOI"]
    used["dealer"] = -used["customer"]

    pos = (used.groupby(["expiry", "type", "strike"], as_index=False)
                .agg(dealer_net=("dealer", "sum"), days_used=("day", "nunique"),
                     vol=("vol", "sum"), doi_abs=("dOI", "sum")))
    first_day, last_day = used["day"].min(), used["day"].max()

    settle, spot = None, args.spot
    try:
        import jpx
        settle = jpx.fetch_option_settlement()
        spot = spot or float(settle["spot"])
    except Exception as e:
        print(f"JPXの清算値段を取得できませんでした({e})")
    if not spot:
        print("日経平均が分かりません。--spot で指定してください。")
        return

    from strategies import bs
    iv_tbl = settle["data"] if settle else None
    rows = []
    for r in pos.itertuples():
        iv, dd = 0.25, 30
        if iv_tbl is not None:
            g = iv_tbl[(iv_tbl["type"] == r.type) & (iv_tbl["strike"] == r.strike)
                       & (iv_tbl["expiry"] == r.expiry)]
            if len(g):
                iv = float(g["iv"].iloc[0]) or 0.25
                dd = int(g["days"].iloc[0]) or 30
        if iv <= 0.02:
            iv = 0.25
        gam = float(bs(spot, r.strike, max(dd, 1) / 365, iv, r.type)["gamma"])
        rows.append({"expiry": r.expiry, "type": r.type, "strike": r.strike,
                     "dealer_net": r.dealer_net, "days_used": r.days_used,
                     "tick_vol": r.vol, "oi_moved": r.doi_abs, "iv": iv, "days": dd,
                     "gamma_yen": gam * r.dealer_net * MULT * spot * spot * 0.01})
    res = pd.DataFrame(rows).sort_values(["expiry", "type", "strike"])

    # 比較対象: サイトと同じ一律仮定(コール買い持ち・プット売り持ち)
    site_total = None
    try:
        import build
        last_oi = pd.read_csv(os.path.join(DATA, f"oi_{max(days)}.csv"))
        last_oi["expiry"] = last_oi["expiry"].astype(str)
        exp0 = sorted(last_oi["expiry"].unique())[0]
        hp = build.hedge_pressure(last_oi, settle, exp0) if settle else None
        site_total = hp["total"] / 1e8 if hp else None
    except Exception as e:
        print(f"(サイト側の推定は計算できませんでした: {e})")

    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    path = os.path.join(OUT_DIR, f"dealer_inventory_{stamp}.csv")
    res.to_csv(path, index=False)

    total = res["gamma_yen"].sum() / 1e8
    up = res[res["strike"] > spot]["gamma_yen"].sum() / 1e8
    dn = res[res["strike"] < spot]["gamma_yen"].sum() / 1e8
    print(f"期間: {first_day} 〜 {last_day}(建玉が動いた日のうち、カバー率{args.min_coverage:.0%}以上の日を使用)")
    print(f"使った日×行使価格: {len(used):,}件 / 除いた(カバー率不足): {len(skipped):,}件")
    print(f"向きの付け方: {args.mode}(weighted=偏りの大きさを掛ける / sign=偏りの向きに全量)")
    print(f"その日の偏り|w|の平均: {used['w'].abs().mean():.2f}")
    print(f"日経平均 {spot:,.0f}円")
    print()
    print(f"ディーラーのガンマ推定(建玉×Lee-Ready): 合計 {total:+,.0f}億円 / 指数1%")
    print(f"  現値より上 {up:+,.0f}億円 / 下 {dn:+,.0f}億円")
    print(f"  {'値動きを抑える向き' if total >= 0 else '値動きを増幅する向き'}")
    if site_total is not None:
        print(f"参考・サイトの推定(一律仮定・建玉の残高すべて): {site_total:+,.0f}億円")
    print()
    top = res.reindex(res["gamma_yen"].abs().sort_values(ascending=False).index).head(10)
    print("影響の大きい行使価格:")
    for r in top.itertuples():
        print(f"  {r.expiry} {r.strike:>7,.0f} {r.type}  ディーラー {r.dealer_net:+7,.0f}枚  "
              f"ガンマ {r.gamma_yen / 1e8:+7,.1f}億円  (使った日数 {r.days_used})")
    print(f"\n明細: {path}")

    # 毎日の推移を1行ずつためる(サイトの一律仮定との食い違いを追うため)
    hist_path = os.path.join(OUT_DIR, "dealer_gamma_history.csv")
    row = {"asof": last_day, "run": stamp, "mode": args.mode, "spot": round(spot, 2),
           "total_oku": round(total, 1), "above_oku": round(up, 1), "below_oku": round(dn, 1),
           "site_oku": round(site_total, 1) if site_total is not None else None,
           "strikes": len(res), "days_used": used["day"].nunique(),
           "mean_abs_w": round(float(used["w"].abs().mean()), 3)}
    hist = pd.DataFrame([row])
    if os.path.exists(hist_path):
        prev = pd.read_csv(hist_path)
        hist = pd.concat([prev, hist], ignore_index=True)
        hist = hist.drop_duplicates(subset=["asof", "mode"], keep="last")
    hist.to_csv(hist_path, index=False)
    print(f"推移: {hist_path}({len(hist)}行)")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
        for name in ("Yu Gothic", "Meiryo", "MS Gothic"):
            if any(name == f.name for f in font_manager.fontManager.ttflist):
                plt.rcParams["font.family"] = name
                break
        near = res[(res["strike"] >= spot * 0.9) & (res["strike"] <= spot * 1.1)]
        by = near.groupby("strike", as_index=False)["gamma_yen"].sum()
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.bar(by["strike"], by["gamma_yen"] / 1e8, width=90,
               color=["#0f8a5f" if v >= 0 else "#d1453b" for v in by["gamma_yen"]])
        ax.axvline(spot, color="#111820", linestyle=":", linewidth=1)
        ax.axhline(0, color="#5b6675", linewidth=0.8)
        ax.set_xlabel("行使価格"); ax.set_ylabel("ディーラーのガンマ(億円 / 指数1%)")
        ax.set_title(f"建玉×Lee-Ready によるディーラーのガンマ推定(合計 {total:+,.0f}億円)")
        ax.grid(alpha=0.25)
        fig.tight_layout()
        png = os.path.join(OUT_DIR, f"dealer_inventory_{stamp}.png")
        fig.savefig(png, dpi=120); plt.close(fig)
        print(f"図: {png}")
    except Exception as e:
        print(f"図の作成をスキップしました({e})")

    print("\n※Bloomberg由来のデータと、その加工結果です。公開サイトには使えません。")


if __name__ == "__main__":
    main()
