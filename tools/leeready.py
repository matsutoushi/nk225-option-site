# -*- coding: utf-8 -*-
"""Lee-Readyでディーラーのガンマを推定する(分析用・非公開)。

【これは何か】
約定を「買い手が仕掛けたか/売り手が仕掛けたか」に分け、符号付きの出来高を作る。
顧客が買った反対側にディーラーが立つと考えると、行使価格ごとにディーラーが
どちら向きに持っているかを推定でき、サイトで使っている
「コール買い持ち・プット売り持ち」という一律の仮定を置き換えられる。

判定(Lee & Ready 1991):
  1. 約定値段 > 気配の中値 → 買い仕掛け(+1)
     約定値段 < 気配の中値 → 売り仕掛け(-1)
  2. ちょうど中値 → 直前の「値段が違う約定」と比べ、上なら+1・下なら-1(ティックテスト)
  3. それでも決まらなければ0(集計から除く)

【重要・取り扱い】
Bloombergのデータは契約者本人の利用に限られ、加工後であっても公開サイトへの
掲載は契約違反になりうる。このスクリプトの出力は private/ に書き出し、
リポジトリには含めない(.gitignoreで除外)。サイトのビルドからは一切参照しない。

【使い方】
  1. Bloombergターミナルで、日経225オプションの各銘柄のティック(約定と気配)を
     CSVに書き出す。1ファイル=1銘柄でも、複数銘柄が混ざっていてもよい。
  2. private/bbg/ に置く(サブフォルダ可)。
  3. python tools/leeready.py
     → private/leeready_YYYYMMDD.csv(行使価格別の集計)
       private/leeready_YYYYMMDD.png(ディーラーのガンマ推定)
       と、画面に要約を表示する。

【CSVに必要な列】(名前は自動で見分ける。大文字小文字・日本語可)
  必須: 時刻(time/date/日時)、約定値段(price/trade/約定)、出来高(size/volume/数量)
  推奨: 買い気配(bid)、売り気配(ask/offer) ※無い場合はティックテストのみで判定
  銘柄: ticker/security/銘柄 のいずれか。無ければファイル名から読み取る
        例: NK 66000C 10/26.csv / NKY 10/26 P60000.csv など
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys
from datetime import datetime

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
IN_DIR = os.path.join(ROOT, "private", "bbg")
OUT_DIR = os.path.join(ROOT, "private")
MULT = 1000          # 日経225オプション(ラージ)の乗数


# ---------------------------------------------------------------------------
# 読み込み
# ---------------------------------------------------------------------------

_ALIASES = {
    "time": ["time", "datetime", "date", "timestamp", "日時", "時刻", "約定日時"],
    "price": ["price", "trade", "last", "value", "約定値段", "約定価格", "値段"],
    "size": ["size", "volume", "qty", "quantity", "出来高", "数量", "枚数"],
    "bid": ["bid", "bid price", "買気配", "買い気配"],
    "ask": ["ask", "offer", "ask price", "売気配", "売り気配"],
    "ticker": ["ticker", "security", "symbol", "銘柄", "銘柄コード"],
    "type": ["type", "side type", "put/call", "コールプット"],
}


def _find_col(cols: list[str], key: str) -> str | None:
    low = {c.strip().lower(): c for c in cols}
    for a in _ALIASES[key]:
        if a in low:
            return low[a]
    for a in _ALIASES[key]:                      # 部分一致(Bloombergは列名が長いことがある)
        for c_low, c in low.items():
            if a in c_low:
                return c
    return None


def parse_contract(text: str) -> tuple[str | None, float | None, str | None]:
    """銘柄名やファイル名から (限月YYMM, 行使価格, C/P) を読み取る。

    Bloombergの日経225オプションは "NKY 10/09/26 C66000 Index" のような形。
    書式は環境で変わるので、ゆるく拾う。"""
    t = str(text).upper()
    kind = None
    m = re.search(r"\b([CP])\s?(\d{4,6})\b", t)
    strike = None
    if m:
        kind, strike = m.group(1), float(m.group(2))
    else:
        m = re.search(r"(\d{4,6})\s?([CP])\b", t)
        if m:
            strike, kind = float(m.group(1)), m.group(2)
    if kind is None:
        if re.search(r"\bCALL\b|コール", t):
            kind = "C"
        elif re.search(r"\bPUT\b|プット", t):
            kind = "P"
    exp = None
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", t)          # 月/日/年
    if m:
        y = int(m.group(3)) % 100
        exp = f"{y:02d}{int(m.group(1)):02d}"
    else:
        m = re.search(r"\b(20)?(\d{2})[-/ ]?(0[1-9]|1[0-2])\b", t)
        if m:
            exp = f"{int(m.group(2)):02d}{int(m.group(3)):02d}"
    return exp, strike, kind


def load_ticks(path: str) -> pd.DataFrame:
    """1ファイル読み込み。列名を寄せ、銘柄が無ければファイル名から補う。"""
    try:
        raw = pd.read_csv(path)
    except UnicodeDecodeError:
        raw = pd.read_csv(path, encoding="cp932")
    if not len(raw):
        return pd.DataFrame()
    cols = list(raw.columns)
    out = pd.DataFrame()
    for key in ("time", "price", "size", "bid", "ask", "ticker"):
        c = _find_col(cols, key)
        if c is not None:
            out[key] = raw[c]
    if "price" not in out or "size" not in out:
        print(f"  スキップ(値段か出来高の列が見つからない): {os.path.basename(path)}")
        return pd.DataFrame()
    if "time" in out:
        out["time"] = pd.to_datetime(out["time"], errors="coerce")
    for c in ("price", "size", "bid", "ask"):
        if c in out:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(subset=["price", "size"])
    out = out[out["size"] > 0]
    src = out["ticker"] if "ticker" in out else pd.Series([os.path.basename(path)] * len(out))
    parsed = [parse_contract(x) for x in src]
    out["expiry"] = [p[0] for p in parsed]
    out["strike"] = [p[1] for p in parsed]
    out["type"] = [p[2] for p in parsed]
    if out["strike"].isna().all() or out["type"].isna().all():
        print(f"  スキップ(銘柄を読み取れない): {os.path.basename(path)}")
        return pd.DataFrame()
    out["file"] = os.path.basename(path)
    return out.dropna(subset=["strike", "type"])


# ---------------------------------------------------------------------------
# Lee-Ready
# ---------------------------------------------------------------------------

def classify(df: pd.DataFrame) -> pd.DataFrame:
    """約定ごとに +1(買い仕掛け) / -1(売り仕掛け) / 0(判定不能) を付ける。"""
    df = df.sort_values([c for c in ("expiry", "strike", "type", "time") if c in df]).copy()
    signs = np.zeros(len(df), dtype=int)
    has_quote = "bid" in df and "ask" in df
    price = df["price"].to_numpy()
    mid = ((df["bid"].to_numpy() + df["ask"].to_numpy()) / 2
           if has_quote else np.full(len(df), np.nan))
    keys = list(zip(df["expiry"], df["strike"], df["type"]))
    last_price = {}
    last_sign = {}
    for i in range(len(df)):
        k = keys[i]
        s = 0
        m = mid[i]
        if m == m and m > 0:                       # 気配がある行は中値で判定
            if price[i] > m:
                s = 1
            elif price[i] < m:
                s = -1
        if s == 0:                                  # 中値と同値、または気配なし → ティックテスト
            lp = last_price.get(k)
            if lp is not None:
                if price[i] > lp:
                    s = 1
                elif price[i] < lp:
                    s = -1
                else:
                    s = last_sign.get(k, 0)         # 同値が続くときは直前の判定を引き継ぐ
        if price[i] != last_price.get(k):
            last_price[k] = price[i]
        if s:
            last_sign[k] = s
        signs[i] = s
    df["sign"] = signs
    df["signed_size"] = df["sign"] * df["size"]
    return df


# ---------------------------------------------------------------------------
# ガンマ
# ---------------------------------------------------------------------------

def dealer_gamma(agg: pd.DataFrame, spot: float, settle: dict | None) -> pd.DataFrame:
    """行使価格ごとのディーラー建玉から、指数1%あたりの円建てガンマを出す。

    顧客の買い越し分だけ、ディーラーは売り持ちになると考える(dealer = -customer)。
    IVと残存日数はJPXの清算値段ファイルから取る(無ければ25%・30日で代用)。"""
    from strategies import bs
    rows = []
    iv_tbl = settle["data"] if settle else None
    for r in agg.itertuples():
        iv, days = None, None
        if iv_tbl is not None:
            g = iv_tbl[(iv_tbl["type"] == r.type) & (iv_tbl["strike"] == r.strike)]
            if r.expiry:
                g2 = g[g["expiry"] == r.expiry]
                g = g2 if len(g2) else g
            if len(g):
                iv, days = float(g["iv"].iloc[0]), int(g["days"].iloc[0])
        if not iv or iv <= 0.02:
            iv = 0.25
        if not days or days <= 0:
            days = 30
        gam = float(bs(spot, r.strike, days / 365, iv, r.type)["gamma"])
        dealer = -r.signed_size                       # 顧客の反対側
        rows.append({"expiry": r.expiry, "type": r.type, "strike": r.strike,
                     "customer_net": r.signed_size, "dealer_net": dealer,
                     "volume": r.size, "classified": r.classified,
                     "iv": iv, "days": days,
                     "gamma_yen": gam * dealer * MULT * spot * spot * 0.01})
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=IN_DIR, help="ティックCSVの置き場所")
    ap.add_argument("--spot", type=float, default=None, help="日経平均(省略時はJPXの清算値段ファイルから)")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.dir, "**", "*.csv"), recursive=True))
    if not files:
        print(f"CSVが見つかりません: {args.dir}")
        print("Bloombergから書き出したティックCSVをこのフォルダに置いてください。")
        return
    print(f"{len(files)}ファイルを読み込みます")
    parts = [load_ticks(f) for f in files]
    df = pd.concat([p for p in parts if len(p)], ignore_index=True) if any(len(p) for p in parts) else pd.DataFrame()
    if not len(df):
        print("読み込める約定がありませんでした。列名と銘柄の形式をご確認ください。")
        return

    df = classify(df)
    n_ok = int((df["sign"] != 0).sum())
    print(f"約定 {len(df):,}件のうち、判定できたのは {n_ok:,}件 "
          f"({n_ok / len(df):.1%})。買い仕掛け {int((df['sign'] > 0).sum()):,}件 / "
          f"売り仕掛け {int((df['sign'] < 0).sum()):,}件")
    if "time" in df and df["time"].notna().any():
        print(f"期間: {df['time'].min()} 〜 {df['time'].max()}")

    agg = (df.assign(classified=(df["sign"] != 0).astype(int))
             .groupby(["expiry", "type", "strike"], as_index=False)
             .agg(signed_size=("signed_size", "sum"), size=("size", "sum"),
                  classified=("classified", "sum")))

    settle, spot = None, args.spot
    try:
        import jpx
        settle = jpx.fetch_option_settlement()
        spot = spot or float(settle["spot"])
        print(f"JPXの清算値段({settle['date']})からIVと残存日数を取得しました")
    except Exception as e:
        print(f"JPXの清算値段を取得できませんでした({e})。IV 25%・残存30日で代用します")
    if not spot:
        print("日経平均が分かりません。--spot で指定してください。")
        return

    res = dealer_gamma(agg, spot, settle)
    res = res.sort_values(["expiry", "type", "strike"])
    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    csv_path = os.path.join(OUT_DIR, f"leeready_{stamp}.csv")
    res.to_csv(csv_path, index=False)

    total = res["gamma_yen"].sum()
    near = res[(res["strike"] >= spot * 0.9) & (res["strike"] <= spot * 1.1)]
    print()
    print(f"日経平均 {spot:,.0f}円")
    print(f"ディーラーのガンマ推定(Lee-Ready): 合計 {total / 1e8:+,.0f}億円 / 指数1%")
    print(f"  うち現値±10%: {near['gamma_yen'].sum() / 1e8:+,.0f}億円")
    print(f"  現値より上 {near[near.strike > spot]['gamma_yen'].sum() / 1e8:+,.0f}億円 / "
          f"下 {near[near.strike < spot]['gamma_yen'].sum() / 1e8:+,.0f}億円")
    print("  " + ("値動きを抑える向き" if total >= 0 else "値動きを増幅する向き"))
    print()
    top = res.reindex(res["gamma_yen"].abs().sort_values(ascending=False).index).head(10)
    print("影響の大きい行使価格:")
    for r in top.itertuples():
        print(f"  {r.expiry or '-'} {r.strike:>7,.0f} {r.type}  "
              f"顧客 {r.customer_net:+7,.0f}枚  ガンマ {r.gamma_yen / 1e8:+7,.1f}億円")
    print(f"\n明細: {csv_path}")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib import font_manager
        for name in ("Yu Gothic", "Meiryo", "MS Gothic"):
            if any(name == f.name for f in font_manager.fontManager.ttflist):
                plt.rcParams["font.family"] = name
                break
        by = near.groupby("strike", as_index=False)["gamma_yen"].sum()
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.bar(by["strike"], by["gamma_yen"] / 1e8,
               width=90, color=["#0f8a5f" if v >= 0 else "#d1453b" for v in by["gamma_yen"]])
        ax.axvline(spot, color="#111820", linestyle=":", linewidth=1)
        ax.axhline(0, color="#5b6675", linewidth=0.8)
        ax.set_xlabel("行使価格"); ax.set_ylabel("ディーラーのガンマ(億円 / 指数1%)")
        ax.set_title(f"Lee-Readyによるディーラーのガンマ推定(合計 {total / 1e8:+,.0f}億円)")
        ax.grid(alpha=0.25)
        fig.tight_layout()
        png = os.path.join(OUT_DIR, f"leeready_{stamp}.png")
        fig.savefig(png, dpi=120)
        plt.close(fig)
        print(f"図: {png}")
    except Exception as e:
        print(f"図の作成をスキップしました({e})")

    print("\n※Bloomberg由来のデータと、その加工結果です。公開サイトには使えません。")


if __name__ == "__main__":
    main()
