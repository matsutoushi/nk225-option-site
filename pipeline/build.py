# -*- coding: utf-8 -*-
"""日経225オプション可視化サイトのビルドパイプライン。

1. JPX公式データを取得(jpx.py)
   - 日次: 行使価格別建玉・増減、プット/コール出来高
   - 週次: 指数先物の取引参加者別建玉残高(旧・手口の後継)
2. チャート・テーブル生成
3. 履歴をdata/に蓄積(GitHub Actionsがコミットして永続化)
4. site/index.html を生成
"""

import html
import os
import re
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

import jpx
import pages

_available = {f.name for f in font_manager.fontManager.ttflist}
plt.rcParams["font.family"] = [f for f in ("Yu Gothic", "Meiryo", "IPAexGothic")
                               if f in _available] + ["sans-serif"]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
IMG = os.path.join(SITE, "img")
DATA = os.path.join(ROOT, "data")
JST = timezone(timedelta(hours=9))

# --- ライトテーマ配色 ---
# 白背景・濃い文字で可読性を優先。チャート画像もこの配色で生成する。
PAGE_BG = "#f6f7f9"   # ページ背景(わずかにグレー)
PANEL = "#ffffff"     # カード・チャート面
INK = "#111820"       # 主要テキスト
INK2 = "#5b6675"      # 補助テキスト(白地で十分なコントラスト)
GRID = "#dfe3e9"      # グリッド・罫線
UP = "#d1453b"        # 陽線・プット系(赤・白地向けに濃く)
DOWN = "#1f6fd0"      # 陰線・コール系(青・白地向けに濃く)
ACCENT = "#0f8a5f"    # アクセント(緑)
WARN = "#b3730a"      # シグナル線(黄・白地向けに濃く)

# 参加者別建玉で使う合算商品名(mini建玉を1/10してラージと合計したもの)
COMBINED_FUT = "日経225先物+mini(ラージ換算)"

plt.rcParams.update({
    "figure.facecolor": PANEL,
    "axes.facecolor": PANEL,
    "savefig.facecolor": PANEL,
    "text.color": INK,
    "axes.edgecolor": GRID,
    "axes.labelcolor": INK2,
    "xtick.color": INK2,
    "ytick.color": INK2,
    "grid.color": GRID,
    "legend.facecolor": PANEL,
    "legend.edgecolor": GRID,
    "legend.labelcolor": INK,
    "axes.titlecolor": INK,
})


# ---------------------------------------------------------------------------
# データ蓄積
# ---------------------------------------------------------------------------

def save_history(date: str, pcr: dict, oi: pd.DataFrame, weekly: dict | None,
                 pcr_mini: dict | None = None) -> pd.DataFrame:
    os.makedirs(DATA, exist_ok=True)
    oi.to_csv(os.path.join(DATA, f"oi_{date}.csv"), index=False)
    if weekly:
        weekly["data"].to_csv(os.path.join(DATA, f"weekly_fut_{weekly['date']}.csv"), index=False)

    hist_path = os.path.join(DATA, "pcr_history.csv")
    hist = pd.read_csv(hist_path, dtype={"date": str}) if os.path.exists(hist_path) else \
        pd.DataFrame(columns=["date", "put_volume", "call_volume", "pcr"])
    hist = hist[hist["date"].astype(str).str.fullmatch(r"20\d{6}") & (hist["date"] != date)]
    hist = pd.concat([hist, pd.DataFrame([{"date": date, **pcr}])], ignore_index=True)
    hist = hist.sort_values("date")
    hist.to_csv(hist_path, index=False)

    # ミニ込みPCR(ラージ換算)は別系列として蓄積する。
    # 既存のpcr_history.csvはラージのみで積み上げてきたため、途中で定義を変えると
    # 過去と接続しない系列になる。よって上書きせず新しいCSVに分ける。
    if pcr_mini:
        put_all = pcr["put_volume"] + pcr_mini["put_volume"] / 10.0
        call_all = pcr["call_volume"] + pcr_mini["call_volume"] / 10.0
        row = {"date": date,
               "put_volume": round(put_all, 1), "call_volume": round(call_all, 1),
               "pcr": round(put_all / call_all, 3) if call_all else None,
               "mini_put": pcr_mini["put_volume"], "mini_call": pcr_mini["call_volume"]}
        p2 = os.path.join(DATA, "pcr_history_incl_mini.csv")
        h2 = pd.read_csv(p2, dtype={"date": str}) if os.path.exists(p2) else \
            pd.DataFrame(columns=list(row))
        h2 = h2[h2["date"].astype(str).str.fullmatch(r"20\d{6}") & (h2["date"] != date)]
        h2 = pd.concat([h2, pd.DataFrame([row])], ignore_index=True).sort_values("date")
        h2.to_csv(p2, index=False)
    return hist


# ---------------------------------------------------------------------------
# チャート
# ---------------------------------------------------------------------------

def nearest_expiry(oi: pd.DataFrame) -> str:
    totals = oi.groupby("expiry")["oi"].sum()
    for exp in sorted(totals.index):
        if totals[exp] > 1000:
            return exp
    return sorted(totals.index)[0]


def wall_strikes(oi: pd.DataFrame, expiry: str, spot: float | None,
                 band: float = 0.10) -> dict:
    """「壁」として意味のある建玉水準を返す。

    単純な建玉最大だと、深いテールヘッジ(現値-50%のプットなど)が選ばれてしまい
    実際の攻防水準を表さない。またコールが現値より下・プットが現値より上にあると
    すでにITMで壁として機能しない。そこで
      上の壁 = 現値より上、現値+band以内で建玉最大のコール
      下の壁 = 現値より下、現値-band以内で建玉最大のプット
    と定義する。チャートの線とサマリー文で同じ定義を使う。

    Returns: {"call": (strike, oi), "put": (strike, oi)} 該当なしのキーは省く。
    """
    out = {}
    if not spot:
        return out
    near = oi[oi["expiry"] == expiry]
    for t, key, lo, hi in (("C", "call", spot, spot * (1 + band)),
                           ("P", "put", spot * (1 - band), spot)):
        sub = near[(near["type"] == t) & (near["strike"] > lo) & (near["strike"] <= hi)]             if t == "C" else             near[(near["type"] == t) & (near["strike"] >= lo) & (near["strike"] < hi)]
        if len(sub):
            r = sub.loc[sub["oi"].idxmax()]
            out[key] = (int(r["strike"]), int(r["oi"]))
    return out


def hedge_pressure(oi: pd.DataFrame, settle: dict, expiry: str,
                   band: float = 0.10, max_days: int = 45) -> dict | None:
    """建玉と清算値段のボラティリティから、ヘッジ売買が値動きに与える向きを推定する。

    オプションを売った側(証券会社)は、リスクを打ち消すため先物を売買してヘッジする。
    その売買が値動きを「抑える」向きか「増幅する」向きかは、どの行使価格に
    どれだけ建玉があるかで決まる。ここではその強さを行使価格ごとに集計する。

    前提(業界で広く使われるもの): 証券会社はコールを買い持ち・プットを売り持ち。
    実際の保有は非公開のため、あくまで推定値。

    Returns: {"spot","by_strike","total","flip"} 計算できなければ None
    """
    if not settle or "data" not in settle:
        return None
    spot = settle.get("spot")
    if not spot:
        return None
    # 直近の月限(45日以内)をまとめて見る。1限月だけだと満期直前に振れやすいため。
    iv = settle["data"]
    iv = iv[(iv["iv"] > 0) & (iv["days"] > 0) & (iv["days"] <= max_days)
            & (iv["expiry"].str.len() == 4)]
    if not len(iv):
        return None
    df = oi.merge(iv[["type", "expiry", "strike", "iv", "days"]],
                  on=["type", "expiry", "strike"], how="inner")
    df = df[(df["strike"] >= spot * (1 - band)) & (df["strike"] <= spot * (1 + band))]
    if not len(df):
        return None

    t = df["days"] / 365.0
    r = settle.get("rate", 0.0)
    sig = df["iv"]
    d1 = (np.log(spot / df["strike"]) + (r + sig ** 2 / 2) * t) / (sig * np.sqrt(t))
    # 標準正規分布の密度関数
    gamma = np.exp(-d1 ** 2 / 2) / np.sqrt(2 * np.pi) / (spot * sig * np.sqrt(t))
    # 指数が1%動いたときの円建てインパクト。コールは+、プットは−で合算する。
    sign = df["type"].map({"C": 1, "P": -1})
    df = df.assign(force=gamma * df["oi"] * 1000 * spot * spot * 0.01 * sign)

    by = df.groupby("strike", as_index=False)["force"].sum().sort_values("strike")
    by["cum"] = by["force"].cumsum()
    flip = None
    if len(by):
        pos = by["cum"].iloc[0] >= 0
        for _, row in by.iterrows():
            if (row["cum"] >= 0) != pos:
                flip = float(row["strike"])
                break
    return {"spot": spot, "by_strike": by, "total": float(df["force"].sum()),
            "flip": flip, "days": int(df["days"].max()),
            "expiries": sorted(df["expiry"].unique().tolist())}


def _sq_date(expiry: str) -> pd.Timestamp:
    """限月コード(YYMM)のSQ日=第2金曜を返す。"""
    y, m = 2000 + int(expiry[:2]), int(expiry[2:])
    fridays = [x for x in pd.date_range(pd.Timestamp(y, m, 1), periods=14, freq="D")
               if x.weekday() == 4]
    return fridays[1]


def merge_mini_into_oi(oi: pd.DataFrame, mini: pd.DataFrame | None,
                       expiry: str) -> tuple[pd.DataFrame, int]:
    """月限に対応するミニオプションをラージ換算(÷10)して建玉分布に合算する。

    ミニは想定元本がラージの1/10。ミニはウィークリー限月なので、月限のSQと
    同じ回号(最終売買日=SQ前日、またはSQ当日)のものだけを対象にする。
    週次限月のミニは短期需給として別セクションに残すため、ここでは合算しない。

    Returns: (合算後のoi, 合算したミニの枚数)。対象が無ければ元のoiをそのまま返す。
    """
    if mini is None or not len(mini):
        return oi, 0
    sq = _sq_date(expiry)
    targets = {sq.date(), (sq - pd.Timedelta(days=1)).date()}
    m = mini[mini["expiry"].isin(targets)]
    if not len(m):
        return oi, 0
    raw_contracts = int(m["oi"].sum())
    add = (m.groupby(["type", "strike"], as_index=False)["oi"].sum()
             .assign(expiry=expiry, change=0))
    add["oi"] = add["oi"] / 10.0  # ラージ換算
    merged = pd.concat([oi, add[["type", "expiry", "strike", "oi", "change"]]],
                       ignore_index=True)
    merged = merged.groupby(["type", "expiry", "strike"], as_index=False)[["oi", "change"]].sum()
    merged["oi"] = merged["oi"].round().astype(int)
    return merged, raw_contracts


def _smooth(x: list, y, window: int = 31, std: float = 7.0):
    """行使価格の系列をなめらかな曲線にする。

    行使価格は等間隔ではない(現値付近は125円刻み、遠いと500〜1000円刻み)ため、
    まず等間隔の格子に載せ替えてからガウス窓で平滑化する。
    窓は「概形が分かる程度」に広めに取り、個々の行使価格の棘を均す。

    平滑化はnumpyだけで完結させる。pandasのrolling(win_type="gaussian")は
    内部でscipyを必要とし、scipyはrequirements.txtに入っていないためCIで落ちる。
    """
    if len(x) < 3:
        return np.array(x), np.array(y)
    grid = np.linspace(min(x), max(x), 240)
    vals = np.interp(grid, x, np.asarray(y, dtype=float))

    half = window // 2
    offs = np.arange(-half, half + 1)
    w = np.exp(-0.5 * (offs / std) ** 2)

    # 端は窓が外にはみ出すぶん重みが減る。値をゼロ扱いにすると端が落ち込むので、
    # 実際に重なった重みの合計で割り直す(pandasのmin_periods=1と同じ考え方)。
    padded = np.pad(vals, half, mode="edge")
    num = np.convolve(padded, w, mode="same")[half:half + len(vals)]
    return grid, num / w.sum()


def chart_oi_distribution(oi: pd.DataFrame, expiry: str, spot: float | None,
                          lang: str = "ja") -> str:
    t = L[lang]
    df = oi[oi["expiry"] == expiry]
    strikes = sorted(df["strike"].unique())
    if spot:
        strikes = [s for s in strikes if 0.85 * spot <= s <= 1.15 * spot]
    puts = df[df["type"] == "P"].set_index("strike")["oi"].reindex(strikes).fillna(0)
    calls = df[df["type"] == "C"].set_index("strike")["oi"].reindex(strikes).fillna(0)

    # 縦棒。行使価格を横軸に取り、コールを上・プットを下に振り分ける。
    # 「壁」の位置を正確に読ませたいので、ここは平滑化しない。
    fig, ax = plt.subplots(figsize=(11, 6))
    width = (strikes[1] - strikes[0]) * 0.8 if len(strikes) > 1 else 100
    ax.bar(strikes, calls.values, width=width, color=DOWN, label=t["call_oi"])
    ax.bar(strikes, -puts.values, width=width, color=UP, label=t["put_oi"])
    ax.axhline(0, color=INK2, linewidth=0.8)
    if spot:
        ax.axvline(spot, color=INK, linestyle="--", linewidth=1.2,
                   label=t["spot_line"].format(spot=spot))
    ax.set_title(t["oi_title"].format(exp=_exp_label(expiry, lang)))
    ax.set_xlabel(t["oi_ylabel"])
    ax.set_ylabel(t["oi_xlabel"])
    ax.yaxis.set_major_formatter(lambda x, _: f"{abs(x):,.0f}")
    ax.xaxis.set_major_formatter(lambda x, _: f"{x:,.0f}")
    ax.legend(loc="upper left")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    os.makedirs(IMG, exist_ok=True)
    name = f"oi_dist{t['suffix']}.png"
    fig.savefig(os.path.join(IMG, name), dpi=120)
    plt.close(fig)
    return f"img/{name}"


def chart_pcr(hist: pd.DataFrame, lang: str = "ja") -> str:
    t = L[lang]
    fig, ax = plt.subplots(figsize=(10, 4))
    dates = pd.to_datetime(hist["date"], format="%Y%m%d").reset_index(drop=True)
    n = len(dates)
    x = np.arange(n)  # 営業日のみを等間隔に並べる(土日祝の空白を作らない)
    ax.plot(x, hist["pcr"].to_numpy(), marker="o", color=ACCENT, linewidth=1.5)
    ax.axhline(1.0, color=INK2, linestyle="--", linewidth=1)
    ax.set_title(t["pcr_title"])
    ax.grid(alpha=0.3)
    # 日付(月/日)が読めるように目盛りを立てる。点が多い場合は最大約12個に間引き、
    # 最新営業日は必ずラベル表示する。
    step = max(1, n // 12)
    ticks = list(range(0, n, step))
    if ticks[-1] != n - 1:
        ticks.append(n - 1)
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{dates[i].month}/{dates[i].day}" for i in ticks],
                       rotation=45, ha="right")
    ax.set_xlim(-0.5, n - 0.5)
    fig.tight_layout()
    name = f"pcr{t['suffix']}.png"
    fig.savefig(os.path.join(IMG, name), dpi=120)
    plt.close(fig)
    return f"img/{name}"


def chart_hedge(h: dict, lang: str = "ja") -> str | None:
    """ヘッジ売買が値動きに与える向きを行使価格別に描く。

    プラス(緑)= 値動きを抑える向き / マイナス(赤)= 増幅する向き。
    """
    if not h or h["by_strike"].empty:
        return None
    t = L[lang]
    by = h["by_strike"].copy()
    by["oku"] = by["force"] / 1e8          # 億円
    spot = h["spot"]
    fig, ax = plt.subplots(figsize=(11, 6))
    gx, gy = _smooth(by["strike"].tolist(), by["oku"].values)
    ax.plot(gx, gy, color=INK2, linewidth=1.4)
    ax.fill_between(gx, gy, 0, where=(gy >= 0), color=ACCENT, alpha=0.55,
                    interpolate=True)
    ax.fill_between(gx, gy, 0, where=(gy < 0), color=UP, alpha=0.55,
                    interpolate=True)
    ax.axhline(0, color=INK2, linewidth=0.9)
    ax.axvline(spot, color=INK, linestyle="--", linewidth=1.2)
    ax.text(spot, ax.get_ylim()[1], t["hedge_spot"].format(spot=spot),
            color=INK, fontsize=9, va="top", ha="left")
    ax.set_xlabel(t["strike"])
    ax.set_ylabel(t["hedge_xlabel"])
    ax.set_title(t["hedge_title"])
    ax.xaxis.set_major_formatter(lambda x, _: f"{x:,.0f}")
    ax.grid(alpha=0.25, axis="y")
    fig.tight_layout()
    os.makedirs(IMG, exist_ok=True)
    name = f"hedge{t['suffix']}.png"
    fig.savefig(os.path.join(IMG, name), dpi=120)
    plt.close(fig)
    return f"img/{name}"


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    rsi.iloc[:period] = np.nan  # 計算初期は信頼できないので表示しない
    return rsi


def chart_market(oi: pd.DataFrame, expiry: str, data_date: str,
                 lang: str = "ja", n225: pd.DataFrame | None = None) -> tuple[str | None, float | None]:
    """ローソク足+価格帯別出来高+最大建玉ライン+MACD+RSI。

    価格データは日経公式CSV(基準日まで確定値)。出来高はYahoo(取得できた日のみ)。
    """
    try:
        hist = n225 if n225 is not None else jpx.fetch_n225_official()
        hist = hist[hist.index <= pd.Timestamp(data_date)].tail(125)  # 約6ヶ月
        if len(hist) < 30:
            raise RuntimeError("insufficient history")
    except Exception as e:
        print(f"WARN: N225 fetch failed, skipping market chart: {e}")
        return None, None

    spot = float(hist["Close"].iloc[-1])
    o, h, l, c = (hist[k].values for k in ("Open", "High", "Low", "Close"))
    # 出来高: 公式CSVには無いのでYahooから日付合わせで補完(失敗時はゼロ=プロファイル省略)
    vol = np.zeros(len(hist))
    try:
        yhist = yf.Ticker("^N225").history(period="8mo")
        yvol = yhist["Volume"]
        yvol.index = yvol.index.tz_localize(None).normalize()
        vol = yvol.reindex(hist.index).fillna(0).values
    except Exception as e:
        print(f"WARN: volume fetch failed, skipping volume profile: {e}")
    n = len(hist)
    x = np.arange(n)

    fig = plt.figure(figsize=(11, 10))
    gs = fig.add_gridspec(4, 1, height_ratios=[3, 1, 1, 1], hspace=0.08)
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax3 = fig.add_subplot(gs[2], sharex=ax1)
    ax4 = fig.add_subplot(gs[3], sharex=ax1)

    # --- ローソク足 ---
    up = c >= o
    colors = np.where(up, UP, DOWN)
    ax1.vlines(x, l, h, color=colors, linewidth=0.8)
    ax1.bar(x[up], (c - o)[up], bottom=o[up], width=0.65, color=UP)
    ax1.bar(x[~up], (c - o)[~up], bottom=o[~up], width=0.65, color=DOWN)

    # --- 価格帯別出来高(左側の横棒) ---
    if vol.sum() > 0:
        bins = np.linspace(l.min(), h.max(), 30)
        centers = (bins[:-1] + bins[1:]) / 2
        prof, _ = np.histogram(c, bins=bins, weights=vol)
        axp = ax1.twiny()
        axp.barh(centers, prof, height=(bins[1] - bins[0]) * 0.9,
                 color=INK2, alpha=0.35, zorder=0)
        axp.set_xlim(0, prof.max() * 4)  # 左1/4だけ使う
        axp.set_ylim(ax1.get_ylim())
        axp.axis("off")

    # --- オプション最大建玉ライン ---
    tx = L[lang]
    near = oi[oi["expiry"] == expiry]
    ymin, ymax = l.min() * 0.995, h.max() * 1.005
    walls = wall_strikes(oi, expiry, spot)
    for key, color, label in (("call", DOWN, tx["max_call"]), ("put", UP, tx["max_put"])):
        if key not in walls:
            continue
        k = walls[key][0]
        if ymin * 0.9 <= k <= ymax * 1.1:
            ax1.axhline(k, color=color, linestyle=":", linewidth=1.6)
            # ラベルは左寄りに置く。右端は直近のローソク足と重なり、
            # 完全な左端は価格帯別出来高の棒と重なるため、その右隣に配置する。
            ax1.text(n * 0.27, k, f"{label} {k:,}", color=color, fontsize=9,
                     va="bottom", ha="left",
                     bbox=dict(facecolor=PANEL, edgecolor="none", pad=1.5, alpha=0.85))
    ax1.set_ylim(ymin, ymax)
    ax1.set_title(tx["mkt_title"])
    ax1.grid(alpha=0.3)
    plt.setp(ax1.get_xticklabels(), visible=False)

    # --- MACD ---
    close_s = pd.Series(c)
    ema12 = close_s.ewm(span=12, adjust=False).mean()
    ema26 = close_s.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    histo = macd - signal
    ax2.bar(x, histo, width=0.65, color=np.where(histo >= 0, UP, DOWN), alpha=0.75)
    ax2.plot(x, macd, color=INK, linewidth=1.2, label="MACD")
    ax2.plot(x, signal, color=WARN, linewidth=1.2, label=tx["signal"])
    ax2.axhline(0, color=INK2, linewidth=0.8)
    ax2.legend(loc="upper left", fontsize=8, ncol=2)
    ax2.set_ylabel("MACD")
    ax2.grid(alpha=0.3)
    plt.setp(ax2.get_xticklabels(), visible=False)

    # --- RSI ---
    rsi = _rsi(close_s)
    ax3.plot(x, rsi, color=ACCENT, linewidth=1.2)
    for lv, style in ((70, "--"), (30, "--"), (50, ":")):
        ax3.axhline(lv, color=INK2, linestyle=style, linewidth=0.8)
    ax3.set_ylim(0, 100)
    ax3.set_ylabel("RSI(14)")
    ax3.grid(alpha=0.3)
    plt.setp(ax3.get_xticklabels(), visible=False)

    # --- 日次出来高(棒) ---
    # 未取得日(0)はマスクして棒を描かない。色はローソク足と同じ上げ下げ配色。
    volm = np.ma.masked_where(vol <= 0, vol)
    ax4.bar(x, volm / 1e8, width=0.65, color=colors, alpha=0.8)
    ax4.set_ylabel(tx["vol_axis"])
    ax4.set_ylim(bottom=0)
    ax4.grid(alpha=0.3)

    # 月初の位置に日付ラベル(最下段のみ)
    dates = hist.index
    ticks = [i for i in range(n) if i == 0 or dates[i].month != dates[i - 1].month]
    if len(ticks) > 1 and ticks[1] - ticks[0] < n * 0.05:
        ticks = ticks[1:]  # 先頭ラベルが月初と重なるので省く
    ax4.set_xticks(ticks)
    ax4.set_xticklabels([dates[i].strftime("%y/%m") for i in ticks])

    name = f"market{tx['suffix']}.png"
    fig.savefig(os.path.join(IMG, name), dpi=120, bbox_inches="tight")
    plt.close(fig)
    return f"img/{name}", spot


def latest_n225_volume(data_date: str) -> dict | None:
    """日経225の直近営業日(<=基準日)の売買高と前日比を返す。

    出来高はYahoo由来で、当日夜は未確定(0)のことがあるため、
    0・欠測は除外し取得できた最新営業日を採用する。失敗時はNone。
    Returns: {"value": 株数, "date": Timestamp, "pct": 前日比%|None}
    """
    try:
        yvol = yf.Ticker("^N225").history(period="2mo")["Volume"].copy()
    except Exception as e:
        print(f"WARN: N225 volume fetch failed: {e}")
        return None
    yvol.index = yvol.index.tz_localize(None).normalize()
    yvol = yvol[(yvol.index <= pd.Timestamp(data_date)) & (yvol > 0)].dropna()
    if len(yvol) == 0:
        return None
    latest = float(yvol.iloc[-1])
    prev = float(yvol.iloc[-2]) if len(yvol) > 1 else None
    return {
        "value": latest,
        "date": yvol.index[-1],
        "pct": ((latest - prev) / prev * 100) if prev else None,
    }


# ---------------------------------------------------------------------------
# テーブル生成
# ---------------------------------------------------------------------------

_EN_MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _exp_label(exp: str, lang: str = "ja") -> str:
    if lang == "en":
        return f"{_EN_MONTHS[int(exp[2:])]} 20{exp[:2]}"
    return f"{exp[:2]}年{int(exp[2:])}月"


# チャート・テーブルの文言(日英)
L = {
    "ja": {
        "suffix": "",
        "oi_title": "日経225オプション 行使価格別建玉分布({exp})",
        "oi_xlabel": "建玉残高(枚)  ← プット | コール →",
        "oi_ylabel": "権利行使価格",
        "put_oi": "プット建玉", "call_oi": "コール建玉",
        "spot_line": "日経平均 {spot:,.0f}",
        "pcr_title": "日経225オプション Put/Call レシオ(出来高ベース・日次)",
        "mkt_title": "日経平均(日足6ヶ月) + 価格帯別出来高 + オプションの壁",
        "max_call": "上の壁(コール建玉)", "max_put": "下の壁(プット建玉)",
        "signal": "シグナル",
        "vol_axis": "出来高(億株)",
        "hedge_title": "日経225 ガンマエクスポージャー(推定・直近3限月)",
        "hedge_xlabel": "抑える ↑ ｜ ↓ 増幅する(億円 / 指数1%)",
        "hedge_spot": "日経平均 {spot:,.0f} ",
        "strike": "行使価格",
        "tbl_note": "前営業日終値を挟んで上下3,000円の範囲({lo:,.0f}〜{hi:,.0f}円)を表示。JPXが日次公開する直近3限月分。増減は前日比。",
        "tbl_caption": "左: 建玉残高(緑=各限月の最大) / 右: 建玉増減(前日比: 増加=緑・減少=赤)",
        "spot_marker": "▶ 前営業日終値 {spot:,.0f}",
        "wk_note": "基準日: {date}(毎週第1営業日に更新される週次データ。前週比は1週間でのネット建玉の増減)",
        "wk_sellers": "{product} 売超上位", "wk_buyers": "{product} 買超上位",
        "wk_cols": ["参加者", "ネット建玉", "前週比"],
        "pv_note": "取引日: {date}(JPX公表 {upd})。各社の当日の取引高と全体に占める割合です。売買の方向までは分かりませんが、どの参加者が主戦場にいるかの目安になります。",
        "pv_cols": ["参加者", "取引高(枚)", "シェア"],
        "products": {"日経225先物": "日経225先物", "日経225mini": "日経225mini",
                     COMBINED_FUT: "日経225先物+mini(ラージ換算)"},
    },
    "en": {
        "suffix": "_en",
        "oi_title": "Nikkei 225 Options — Open Interest by Strike ({exp})",
        "oi_xlabel": "Open Interest (contracts)  ← Put | Call →",
        "oi_ylabel": "Strike Price",
        "put_oi": "Put OI", "call_oi": "Call OI",
        "spot_line": "Nikkei 225: {spot:,.0f}",
        "pcr_title": "Nikkei 225 Options Put/Call Ratio (volume-based, daily)",
        "mkt_title": "Nikkei 225 (daily, 6 months) + Volume Profile + Option Walls",
        "max_call": "Upper wall (call OI)", "max_put": "Lower wall (put OI)",
        "signal": "Signal",
        "vol_axis": "Volume (100M sh)",
        "hedge_title": "Nikkei 225 Gamma Exposure (estimate, near expiries)",
        "hedge_xlabel": "dampens ↑ | ↓ amplifies (100M yen / 1%)",
        "hedge_spot": "Nikkei 225 {spot:,.0f} ",
        "strike": "Strike",
        "tbl_note": "Strikes within ±3,000 yen of the previous close ({lo:,.0f}–{hi:,.0f}). Nearest 3 expiries published daily by JPX. Change is day-over-day.",
        "tbl_caption": "Left: Open Interest (green = largest per expiry) / Right: DoD Change (increase = green, decrease = red)",
        "spot_marker": "▶ Prev. close {spot:,.0f}",
        "wk_note": "As of {date} (weekly data published on the first business day of each week; WoW = one-week change in net open interest)",
        "wk_sellers": "{product} — Top Net Sellers", "wk_buyers": "{product} — Top Net Buyers",
        "wk_cols": ["Participant", "Net OI", "WoW"],
        "pv_note": "Trading date: {date} (published by JPX at {upd}). Volume and share by participant. Direction is not disclosed, but it shows who is most active.",
        "pv_cols": ["Participant", "Volume", "Share"],
        "products": {"日経225先物": "Nikkei 225 Futures", "日経225mini": "Nikkei 225 mini Futures",
                     COMBINED_FUT: "Nikkei 225 Futures + mini (large-equivalent)"},
    },
}


def _change_color(v: int, maxabs: float) -> str | None:
    """増減の強弱: 増加=緑、減少=赤。大きいほど濃く、0は無色(ダーク面向けrgba)。"""
    if v == 0 or maxabs <= 0:
        return None
    strength = min(abs(v) / maxabs, 1.0)
    alpha = 0.15 + 0.5 * strength
    rgb = "12,163,12" if v > 0 else "208,59,59"
    return f"rgba({rgb}, {alpha:.2f})"


def oi_tables_html(oi: pd.DataFrame, center: float, lang: str = "ja") -> str:
    """行使価格別建玉テーブル(現在値と増減を横並び)。前営業日終値±3,000円に限定。"""
    tx = L[lang]
    lo, hi = center - 3000, center + 3000
    oi = oi[(oi["strike"] >= lo) & (oi["strike"] <= hi)]
    expiries = sorted(oi["expiry"].unique())
    strikes = sorted(oi["strike"].unique(), reverse=True)

    def pivot(col):
        return {(t, e): oi[(oi["type"] == t) & (oi["expiry"] == e)]
                .set_index("strike")[col].to_dict()
                for t in ("C", "P") for e in expiries}

    cur, chg = pivot("oi"), pivot("change")

    # 建玉残高: 各限月×Call/Put列の最大値セルだけ緑にする
    col_max = {key: max(tbl.values()) if tbl else None for key, tbl in cur.items()}
    # 増減: 全セルの最大絶対値を基準に濃淡を付ける
    maxabs = max((abs(v) for tbl in chg.values() for v in tbl.values()), default=0)

    def render(table, is_change, with_strike):
        ncols = (1 if with_strike else 0) + 2 * len(expiries)
        head1 = "<tr>"
        if with_strike:
            head1 += f"<th rowspan='2'>{tx['strike']}</th>"
        head1 += f"<th colspan='{len(expiries)}'>Call</th><th colspan='{len(expiries)}'>Put</th></tr>"
        head2 = "<tr>" + "".join(f"<th>{_exp_label(e, lang)}</th>" for e in expiries) * 2 + "</tr>"
        body = []
        spot_inserted = False
        for s in strikes:
            # 降順リストの中で、終値を最初に下回る行の直前に終値ラインを挿入(両表で同位置)
            if not spot_inserted and s < center:
                label = tx["spot_marker"].format(spot=center) if with_strike else "▶"
                body.append(f"<tr class='spot'><td colspan='{ncols}'>{label}</td></tr>")
                spot_inserted = True
            tds = [f"<th>{s:,}</th>"] if with_strike else []
            for t in ("C", "P"):
                for e in expiries:
                    v = table[(t, e)].get(s)
                    if v is None or (is_change and cur[(t, e)].get(s) is None):
                        tds.append("<td class='na'>-</td>")
                    elif is_change:
                        color = _change_color(v, maxabs)
                        style = f" style='background:{color}'" if color else ""
                        tds.append(f"<td{style}>{v:+,}</td>" if v else "<td>0</td>")
                    else:
                        is_max = col_max[(t, e)] is not None and v == col_max[(t, e)]
                        style = " style='background:rgba(25,158,112,0.45); font-weight:bold'" if is_max else ""
                        tds.append(f"<td{style}>{v:,}</td>")
            body.append("<tr>" + "".join(tds) + "</tr>")
        return (f"<table><thead>{head1}{head2}</thead>"
                f"<tbody>{''.join(body)}</tbody></table>")

    note = f"<p>{tx['tbl_note'].format(lo=lo, hi=hi)}</p>"
    caption = f"<h3>{tx['tbl_caption']}</h3>"
    return (f"{note}{caption}<div class='tbl-duo'>"
            f"{render(cur, False, True)}{render(chg, True, False)}</div>")


def add_combined_futures(weekly: dict | None) -> dict | None:
    """参加者別建玉に「日経225先物+mini(ラージ換算)」の合計を追加する。

    miniは想定元本がラージの1/10。枚数のままでは規模を比較できないため、
    mini建玉を1/10してラージと足し合わせた合計を1商品として持たせる。
    """
    if not weekly or "data" not in weekly:
        return weekly
    df = weekly["data"]
    if "product" not in df.columns:
        return weekly
    lg = df[df["product"] == "日経225先物"].copy()
    mn = df[df["product"] == "日経225mini"].copy()
    if not len(lg) and not len(mn):
        return weekly
    for c in ("net", "net_prev", "change"):
        if c in mn.columns:
            mn[c] = mn[c] / 10.0
    comb = pd.concat([lg, mn], ignore_index=True)
    cols = [c for c in ("net", "net_prev", "change") if c in comb.columns]
    comb = comb.groupby("participant", as_index=False)[cols].sum()
    for c in cols:
        comb[c] = comb[c].round().astype(int)
    comb["product"] = COMBINED_FUT
    weekly = dict(weekly)
    weekly["data"] = pd.concat([df, comb[df.columns.intersection(comb.columns)]],
                               ignore_index=True)
    return weekly


def participant_volume_html(pv: dict, lang: str = "ja") -> str:
    """日次の手口上位一覧(取引参加者別取引高)。日経225先物とminiの上位を出す。

    JPXは17:45頃にこのデータを公表する(建玉残高は20:00頃)。建玉より早いため、
    夕方の時点ではこのセクションだけが当日データになることがある。
    """
    tx = L[lang]
    df = pv["data"]
    d = pv["date"]
    date_label = f"{d[:4]}/{d[4:6]}/{d[6:]}"
    out = [f"<p>{tx['pv_note'].format(date=date_label, upd=pv.get('update', ''))}</p>"]
    head = "".join(f"<th>{c}</th>" for c in tx["pv_cols"])
    blocks = []
    for cls in ("NK225F", "NK225MF"):
        sub = df[df["cls"] == cls]
        if not len(sub):
            continue
        top = (sub.groupby("participant", as_index=False)["volume"].sum()
                  .sort_values("volume", ascending=False).head(10))
        total = int(sub["volume"].sum())
        rows = "".join(
            f"<tr><td class='name'>{html.escape(str(r['participant']))}</td>"
            f"<td>{int(r['volume']):,}</td>"
            f"<td>{int(r['volume']) / total * 100:.1f}%</td></tr>"
            for _, r in top.iterrows()) if total else ""
        label = jpx.PV_CLASSES.get(cls, cls)
        blocks.append(f"<div class='tbl-box'><h3>{label}</h3><div class='tbl-scroll'>"
                      f"<table><tr>{head}</tr>{rows}</table></div></div>")
    if not blocks:
        return ""
    out.append(f"<div class='tbl-pair'>{''.join(blocks)}</div>")
    return "".join(out)


def weekly_tables_html(weekly: dict, lang: str = "ja") -> str:
    """参加者別建玉(週次)のテーブル。"""
    tx = L[lang]
    d = weekly["date"]
    date_label = f"{d[:4]}/{d[4:6]}/{d[6:]}"
    out = [f"<p>{tx['wk_note'].format(date=date_label)}</p>"]
    head = "".join(f"<th>{c}</th>" for c in tx["wk_cols"])
    for product in (COMBINED_FUT, "日経225先物", "日経225mini"):
        df = weekly["data"][weekly["data"]["product"] == product]
        if len(df) == 0:
            continue
        p_label = tx["products"].get(product, product)
        sellers = df[df["net"] < 0].sort_values("net").head(8)
        buyers = df[df["net"] > 0].sort_values("net", ascending=False).head(8)

        def rows(sub):
            r = []
            for _, row in sub.iterrows():
                cls = "pos" if row["change"] > 0 else ("neg" if row["change"] < 0 else "")
                r.append(f"<tr><td class='name'>{html.escape(row['participant'])}</td>"
                         f"<td>{row['net']:+,}</td>"
                         f"<td class='{cls}'>{row['change']:+,}</td></tr>")
            return "".join(r)

        out.append(f"""
<div class='tbl-pair'>
  <div class='tbl-box'><h3>{tx['wk_sellers'].format(product=p_label)}</h3><div class='tbl-scroll'>
    <table><tr>{head}</tr>{rows(sellers)}</table>
  </div></div>
  <div class='tbl-box'><h3>{tx['wk_buyers'].format(product=p_label)}</h3><div class='tbl-scroll'>
    <table><tr>{head}</tr>{rows(buyers)}</table>
  </div></div>
</div>""")
    return "".join(out)


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

CSS_MAIN = """
  :root {
    --bg: #f6f7f9; --panel: #ffffff; --panel2: #eef1f5;
    --ink: #111820; --ink2: #4b5563; --line: #dfe3e9;
    --blue: #1f6fd0; --red: #d1453b; --aqua: #0f8a5f;
  }
  * { box-sizing: border-box; }
  body { font-family: "Noto Sans JP", "Yu Gothic", Meiryo, sans-serif; background: var(--bg);
         max-width: 1100px; margin: 0 auto; padding: 0 20px 56px; color: var(--ink);
         font-size: 16px; line-height: 1.85; }
  header { position: sticky; top: 0; z-index: 10; background: rgba(246,247,249,0.94);
            backdrop-filter: blur(6px); padding: 16px 0 12px; border-bottom: 1px solid var(--line); }
  h1 { font-size: 1.4em; margin: 0 0 3px; letter-spacing: 0.02em; }
  h1::before { content: "▮"; color: var(--aqua); margin-right: 8px; }
  h2 { font-size: 1.25em; margin: 52px 0 14px; padding-left: 12px;
        border-left: 4px solid var(--aqua); letter-spacing: 0.02em; }
  h3 { font-size: 1.02em; color: var(--ink); font-weight: 500; margin: 16px 0 8px; }
  p { color: var(--ink2); font-size: 0.95em; }
  .updated { color: var(--ink2); font-size: 0.85em; margin: 0; }
  nav { margin-top: 8px; }
  nav a { color: var(--ink2); text-decoration: none; font-size: 0.88em; margin-right: 6px;
           padding: 5px 13px; border: 1px solid var(--line); border-radius: 999px;
           display: inline-block; background: var(--panel); }
  nav a:hover { color: var(--aqua); border-color: var(--aqua); }
  .tagline { color: var(--ink2); font-size: 0.9em; margin: 6px 0 0; }
  .menu { display: none; position: relative; margin-top: 6px; }
  .menu summary { list-style: none; cursor: pointer; color: var(--ink2); font-size: 0.85em;
                  border: 1px solid var(--line); border-radius: 8px; padding: 4px 12px;
                  display: inline-block; user-select: none; }
  .menu summary::-webkit-details-marker { display: none; }
  .menu[open] summary { color: var(--ink); border-color: var(--aqua); }
  .menu-panel { position: absolute; left: 0; top: calc(100% + 6px); background: var(--panel);
                border: 1px solid var(--line); border-radius: 10px; padding: 8px; z-index: 30;
                min-width: 230px; box-shadow: 0 10px 28px rgba(17,24,32,0.14); }
  .menu-panel a { display: block; padding: 9px 12px; color: var(--ink); text-decoration: none;
                  border-radius: 6px; font-size: 0.95em; }
  .menu-panel a:hover { background: var(--panel); }
  .menu-panel .sub { color: var(--ink2); font-size: 0.75em; padding: 8px 12px 2px;
                     border-top: 1px solid var(--line); margin-top: 6px; }
  .menu-panel a.lang { border-top: 1px solid var(--line); margin-top: 6px; border-radius: 0 0 6px 6px; }
  .sitemap { line-height: 2; }
  a.dl { display: inline-block; font-size: 0.78em; color: var(--ink2); text-decoration: none;
         border: 1px solid var(--line); border-radius: 6px; padding: 2px 10px; margin-left: 8px;
         vertical-align: middle; }
  a.dl:hover { color: var(--aqua); border-color: var(--aqua); }
  @media (max-width: 600px) {
    nav.pills { display: none; }
    .menu { display: block; }
  }
  .kpi { display: flex; gap: 12px; margin: 22px 0 10px; flex-wrap: wrap; }
  .summary { font-size: 1.02em; color: var(--ink); background: var(--panel);
             border: 1px solid var(--line); border-left: 4px solid var(--aqua);
             border-radius: 0 10px 10px 0; padding: 12px 16px; margin: 18px 0 0; line-height: 1.9; }
  .summary b { font-variant-numeric: tabular-nums; }
  .kpi-guide { font-size: 0.88em; color: var(--ink2); margin: 0 0 6px; }
  .src-dates { font-size: 0.78em; opacity: 0.85; margin-top: 2px; }
  .kpi div { background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
              padding: 14px 20px; flex: 1 1 150px; font-size: 0.9em; color: var(--ink2); }
  .kpi b { font-size: 1.9em; color: var(--ink); font-variant-numeric: tabular-nums;
            display: block; margin-top: 4px; line-height: 1.2; }
  .kpi div:first-child b { color: var(--aqua); }
  img { max-width: 100%; height: auto; border: 1px solid var(--line); border-radius: 10px; }
  .tbl-pair { display: flex; gap: 16px; flex-wrap: wrap; align-items: flex-start; }
  .tbl-box { flex: 1 1 420px; min-width: 320px; }
  .tbl-scroll { max-height: 560px; overflow: auto; border: 1px solid var(--line); border-radius: 10px; }
  .tbl-duo { display: flex; gap: 20px; max-height: 560px; overflow: auto;
              border: 1px solid var(--line); border-radius: 10px; align-items: flex-start; }
  .tbl-duo table { width: auto; }
  table { border-collapse: collapse; font-size: 14px; white-space: nowrap; width: 100%;
           font-variant-numeric: tabular-nums; background: var(--panel); }
  th, td { border: 1px solid var(--line); padding: 5px 10px; text-align: right; }
  td { color: var(--ink); }
  th { background: var(--panel2); color: var(--ink2); position: sticky; top: 0; font-weight: 500; }
  tr > th:first-child { position: sticky; left: 0; background: var(--panel2); z-index: 3; }
  /* ヘッダーが2段の表(建玉一覧)では、2段目を1段目の下に固定する。
     両方 top:0 にすると2段目が1段目(Call/Put)を覆って見えなくなる。 */
  thead th { line-height: 20px; padding: 5px 10px; z-index: 2; }
  thead tr:first-child th { top: 0; height: 30px; }
  /* 2段目は1段目の高さ分だけ下げる。わずかに小さめにして隙間からデータが覗くのを防ぐ
     (1pxの重なりは見えないが、1pxの隙間は行が透けて見えてしまうため) */
  thead tr:nth-child(2) th { top: 30px; height: 30px; }
  thead tr:first-child th:first-child { z-index: 4; }
  td.name { text-align: left; }
  td.pos { color: #0f7a4a; }
  td.neg { color: #c0392b; }
  td.na { color: #9aa3af; }
  tr.spot td { background: rgba(15,138,95,0.14); color: var(--ink); text-align: center;
                font-weight: 700; border-top: 2px solid var(--aqua); border-bottom: 2px solid var(--aqua);
                letter-spacing: 0.05em; }
  .sig { font-size: 1.1em; }
  .sig-green { color: #0f7a4a; }
  .sig-yellow { color: #b3730a; }
  .sig-red { color: #c0392b; }
  td.basis { text-align: left; color: var(--ink2); font-size: 11px; white-space: normal; min-width: 200px; }
  footer { border-top: 1px solid var(--line); margin-top: 48px; padding-top: 10px;
            font-size: 0.78em; color: var(--ink2); }
  @media (max-width: 600px) {
    body { padding: 0 10px 24px; }
    h1 { font-size: 1.05em; }
    .kpi div { padding: 8px 14px; }
    .kpi b { font-size: 1.3em; }
    table { font-size: 11px; }
    .tbl-scroll { max-height: 420px; }
    nav a { margin-right: 4px; font-size: 0.78em; }
  }
"""

# ページ本文の文言(日英)
PAGE = {
    "ja": {
        "title": "日経225オプション データ分析 | 建玉分布・Put/Callレシオ 毎日更新",
        "desc": "日経225オプションの行使価格別建玉・増減、Put/Callレシオ、先物の参加者別建玉を毎営業日自動更新。データ出典はJPX公式。",
        "h1": "日経225オプション データ分析",
        "updated": "データ基準日: {d} | 最終更新: {now} JST(毎営業日 自動更新)",
        "nav": ["マーケット", "建玉一覧", "建玉分布", "参加者別建玉", "Put/Callレシオ"],
        "guide_link": '<a href="us.html">米国市場</a><a href="risk.html">リスクモニター</a><a href="fedwatch.html">要人発言</a><a href="guide-start.html">始め方ガイド</a>',
        "lang_switch": '<a href="en/" lang="en">English</a>',
        "kpi": ["Put/Call レシオ", "プット出来高", "コール出来高"], "unit": " 枚",
        "sec_market": "マーケット概況",
        "tagline": "日経225オプションの建玉・米国市場のポジション・マクロリスク指標を、JPX・CFTC・CBOE・FREDなどの公式データから毎営業日自動更新するデータサイトです。",
        "kpi_vi": "日経VI(前日差)",
        "kpi_vol": "日経売買高(株数・前日比)",
        "vol_unit": " 億株",
        "kpi_sq": "次回SQ",
        "sec_mini": "ミニオプション建玉分布(ウィークリー: {exp}限)",
        "mini_lead": "日経225ミニオプション(週次限月)の行使価格別建玉。短期の攻防ラインの目安になります。",
        "sec_flows": "海外投資家の売買動向(週次)",
        "flows_lead": "JPX投資部門別売買状況(東証プライム・現物金額)より。上段=累積ネット売買(日経平均を重ね描き)、下段=直近1年の週次。プラス=買い越し、マイナス=売り越し。{latest}",
        "sec_oitable": "オプション建玉一覧(限月別)",
        "sec_oi": "行使価格別 建玉分布",
        "mini_note": "※ミニオプション({n:,}枚)を1/10のラージ換算で合算しています。",
        "sm_price": "日経平均は<b>{spot:,.0f}円</b>({chg:+,.0f}円)。",
        "sm_price_only": "日経平均は<b>{spot:,.0f}円</b>。",
        "sm_pcr_prev": "Put/Callレシオは<b>{v}</b>(前営業日 {p})。",
        "sm_pcr": "Put/Callレシオは<b>{v}</b>。",
        "sm_walls": "現値近辺で建玉が厚いのはコール<b>{c:,}円</b>・プット<b>{p:,}円</b>です。",
        "src_volume": "出来高・価格 {d}",
        "src_pv": "手口 {d}",
        "src_oi": "建玉残高 {d}",
        "sec_hedge": "ガンマエクスポージャー",
        "hedge_lead": "オプションを売った側(証券会社)は、リスクを打ち消すために先物を売り買いしてヘッジします。この売買は、相場の位置によって値動きを<b>抑える向き</b>にも<b>増幅する向き</b>にも働きます。下の図は、建玉と清算値段のボラティリティから、その強さを行使価格ごとに推定したものです。<b>証券会社の実際の保有は公表されていないため、あくまで推定値</b>です(コールを買い持ち・プットを売り持ちという一般的な前提を置いています)。",
        "hedge_sum": "現値より上は{up:+,.0f}億円、現値より下は{dn:+,.0f}億円。合計では<b>{word}</b>({total:+,.0f}億円 / 指数1%あたり)。",
        "hedge_damp": "値動きを抑える向き", "hedge_amp": "値動きを増幅する向き",
        "hedge_more": '見方の詳しい解説は <a href="guide-gex.html">ガンマエクスポージャーとは</a> をどうぞ。',
        "sec_pv": "手口上位一覧(取引参加者別 取引高)",
        "sec_fut": "先物の出来高(ラージ換算での比較)",
        "fut_lead": "miniは想定元本がラージの1/10、マイクロは1/100です。枚数のままでは規模を比較できないため、ラージ換算した列を併記しています。",
        "fut_cols": ["商品", "出来高(枚)", "ラージ換算", "取引代金"],
        "fut_total": "合計",
        "oi_lead": '建玉が積み上がった行使価格は、市場参加者が意識する「壁」の目安になります。(<a href="guide-oi.html" style="color:#1f6fd0">→ 建玉分布の見方</a>)',
        "sec_weekly": "先物 取引参加者別建玉(週次)",
        "wk_chart_lead": "棒グラフ: 各社の週次ネット建玉(緑=買い越し / 赤=売り越し)。灰色の線は日経平均の推移(形状比較用・目盛りなし)。最新週の建玉規模上位12社を表示。",
        "sec_pcr": "Put/Call レシオの推移",
        "pcr_lead": '1.0超はプット優勢(警戒・ヘッジ需要)、1.0未満はコール優勢の目安です。(<a href="guide-pcr.html" style="color:#1f6fd0">→ Put/Callレシオの見方</a>)',
        "kpi_guide": 'この数字の意味は? → <a href="guide-pcr.html">Put/Callレシオとは</a>'
                     ' ・ <a href="guide-oi.html">建玉の「壁」の見方</a>'
                     ' ・ <a href="guide-gex.html">急落を増幅するディーラーのヘッジ</a>',
        "sec_guides": "データの読み方ガイド",
        "guides_lead": "各指標の意味と実践的な使い方を、図解付きで解説しています。",
        "guides": [
            ("guide-oi.html", "建玉分布の見方",
             "行使価格に積み上がった建玉が「壁」として意識される仕組み"),
            ("guide-pcr.html", "Put/Callレシオとは",
             "市場心理の偏りを1つの数字で読む。水準より変化を見る"),
            ("guide-gex.html", "ガンマエクスポージャーとは",
             "証券会社のヘッジ売買が、なぜ相場を増幅・抑制するのか"),
            ("guide-teguchi.html", "先物の手口の見方",
             "ABNクリアリンやソシエテGは何者か。どこまで読めるか"),
            ("guide-sq.html", "SQとは",
             "満期の決済価格。SQ値は日経平均の始値とは別物"),
            ("guide-cot.html", "COT(投機筋ポジション)の見方",
             "米国先物市場のポジションの偏りを週次で追う"),
            ("glossary.html", "用語集",
             "SQ・限月・デルタなど、オプションの基本用語"),
            ("guide-start.html", "日経225オプションを始めるには",
             "口座開設から取引開始までの一般的な流れ"),
        ],
        "footer_links": '<a href="about.html" style="color:#1f6fd0">運営者情報</a> ｜ <a href="privacy.html" style="color:#1f6fd0">プライバシーポリシー</a> ｜ <a href="glossary.html" style="color:#1f6fd0">用語集</a>',
        "footer_src": "データ出典: 日本取引所グループ(JPX)公表データより当サイト作成。日経平均株価は日本経済新聞社の公表データ(著作権は日本経済新聞社に帰属)。",
        "footer_disclaimer": "本サイトは情報提供を目的としたものであり、投資勧誘や投資助言ではありません。投資判断はご自身の責任でお願いします。",
        "out": "index.html", "prefix": "", "html_lang": "ja",
    },
    "en": {
        "title": "Nikkei 225 Options Data | Open Interest & Put/Call Ratio, Updated Daily",
        "desc": "Nikkei 225 options open interest by strike, day-over-day changes, put/call ratio, and futures positions by trading participant. Auto-updated every business day from official JPX data.",
        "h1": "Nikkei 225 Options Data",
        "updated": "Data as of {d} | Last updated {now} JST (auto-updated every business day)",
        "nav": ["Market", "OI Table", "OI Distribution", "Participants", "Put/Call Ratio"],
        "guide_link": '<a href="us.html">US Markets</a><a href="risk.html">Risk Monitor</a><a href="fedwatch.html">Fed Watch</a>',
        "lang_switch": '<a href="../" lang="ja">日本語</a>',
        "kpi": ["Put/Call Ratio", "Put Volume", "Call Volume"], "unit": "",
        "sec_market": "Market Overview",
        "tagline": "Nikkei 225 options open interest, US positioning and macro risk gauges — auto-updated every business day from official JPX, CFTC, CBOE and FRED data.",
        "kpi_vi": "Nikkei VI (DoD)",
        "kpi_vol": "Nikkei Volume (shares, DoD)",
        "vol_unit": " M sh",
        "kpi_sq": "Next SQ",
        "sec_mini": "Mini Options OI (Weekly: {exp} expiry)",
        "mini_lead": "Open interest by strike for Nikkei 225 mini options (weekly expiries) — a gauge of short-term battle lines.",
        "sec_flows": "Foreign Investor Flows (Weekly)",
        "flows_lead": "Weekly net buying by foreign investors in TSE Prime cash equities, shown as a cumulative line (top) and weekly bars (bottom), from JPX trading-by-investor-type data. Positive = net buying. {latest}",
        "sec_oitable": "Options Open Interest by Expiry",
        "sec_oi": "Open Interest Distribution by Strike",
        "mini_note": "Includes mini options ({n:,} contracts) converted to large-equivalent (1/10).",
        "sm_price": "Nikkei 225 closed at <b>{spot:,.0f}</b> ({chg:+,.0f}). ",
        "sm_price_only": "Nikkei 225 closed at <b>{spot:,.0f}</b>. ",
        "sm_pcr_prev": "Put/call ratio <b>{v}</b> (prev {p}). ",
        "sm_pcr": "Put/call ratio <b>{v}</b>. ",
        "sm_walls": "Heaviest open interest near spot: call <b>{c:,}</b>, put <b>{p:,}</b>.",
        "src_volume": "Volume/price {d}",
        "src_pv": "Participant volume {d}",
        "src_oi": "Open interest {d}",
        "sec_hedge": "Gamma Exposure",
        "hedge_lead": "Dealers who sold options hedge by trading futures. Depending on where the index sits, that hedging can either <b>dampen</b> or <b>amplify</b> moves. The chart below estimates that force by strike, using open interest and the implied volatility in JPX settlement prices. <b>Actual dealer positions are not disclosed, so this is an estimate</b> (assuming dealers are long calls and short puts).",
        "hedge_sum": "Above spot {up:+,.0f}, below spot {dn:+,.0f} (100M yen). Net: <b>{word}</b> ({total:+,.0f} per 1% move).",
        "hedge_damp": "dampening moves", "hedge_amp": "amplifying moves",
        "hedge_more": '',
        "sec_pv": "Trading Volume by Participant (daily ranking)",
        "sec_fut": "Futures Volume (large-equivalent comparison)",
        "fut_lead": "Mini is 1/10 the notional of the large contract; micro is 1/100. Raw contract counts are not comparable, so a large-equivalent column is shown.",
        "fut_cols": ["Product", "Volume (contracts)", "Large-equiv", "Turnover"],
        "fut_total": "Total",
        "oi_lead": "Strikes with heavy open interest often act as reference levels (\"walls\") watched by market participants.",
        "sec_weekly": "Futures Open Interest by Trading Participant (Weekly)",
        "wk_chart_lead": "Bars: weekly net open interest per participant (green = net long, red = net short). Gray line: Nikkei 225 (shape only, no scale). Top 12 participants by latest position size.",
        "sec_pcr": "Put/Call Ratio Trend",
        "pcr_lead": "Above 1.0 = puts dominant (hedging demand); below 1.0 = calls dominant. Participant names in the tables are Japanese trading-participant names as published by JPX.",
        "kpi_guide": 'What do these numbers mean? → '
                     '<a href="guide-participants.html">JPX participant positioning</a>'
                     ' ・ <a href="guide-nikkei-options.html">Nikkei options field guide</a>',
        "sec_guides": "Guides — How to Read This Data",
        "guides_lead": "Background on each indicator and how traders actually use it.",
        "guides": [
            ("guide-participants.html", "JPX Participant Positioning",
             "Japan's hidden COT — weekly futures positions by named firm"),
            ("guide-nikkei-options.html", "Nikkei 225 Options: Field Guide",
             "Contract basics, SQ, and what the official data covers"),
        ],
        "footer_links": '<a href="../about.html" style="color:#1f6fd0">About</a> | <a href="../privacy.html" style="color:#1f6fd0">Privacy Policy</a> | <a href="guide-participants.html" style="color:#1f6fd0">Guide: Participant Positioning</a> | <a href="guide-nikkei-options.html" style="color:#1f6fd0">Guide: Nikkei Options</a>',
        "footer_src": "Data source: compiled from official Japan Exchange Group (JPX) publications. Nikkei 225 price data by Nikkei Inc. (copyright belongs to Nikkei Inc.).",
        "footer_disclaimer": "This site is for informational purposes only and does not constitute investment advice or solicitation. Trade at your own risk.",
        "out": os.path.join("en", "index.html"), "prefix": "../", "html_lang": "en",
    },
}


def render_index(date: str, pcr: dict, charts: dict, tables: dict, lang: str = "ja",
                 extras: dict | None = None) -> None:
    P = PAGE[lang]
    og = og_meta(P["title"], P["desc"])
    extras = extras or {}
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    d = f"{date[:4]}-{date[4:6]}-{date[6:]}"
    # キャッシュ対策: 画像URLにビルド時刻を付け、更新のたびに再取得させる
    ver = datetime.now(JST).strftime("%Y%m%d%H%M")
    charts = {k: (f"{P['prefix']}{v}?v={ver}" if v else v) for k, v in charts.items()}
    market_section = (
        f'<h2 id="market">{P["sec_market"]}</h2>\n  <img src="{charts["market"]}" '
        f'alt="Nikkei 225 candlestick, MACD, RSI, volume profile">'
        if charts.get("market") else ""
    )
    if charts.get("vi"):
        market_section += f'\n  <img src="{charts["vi"]}" alt="Nikkei VI">'

    extra_kpi = ""
    if extras.get("vi_last") is not None:
        delta = extras.get("vi_delta")
        dtxt = f" ({delta:+.1f})" if delta is not None else ""
        extra_kpi += f"<div>{P['kpi_vi']}<br><b>{extras['vi_last']:.1f}</b>{dtxt}</div>"
    if extras.get("n225_vol"):
        v = extras["n225_vol"]
        pct = v.get("pct")
        dtxt = f" ({pct:+.0f}%)" if pct is not None else ""
        div, fmt = (1e8, "{:.2f}") if lang == "ja" else (1e6, "{:.0f}")
        val = fmt.format(v["value"] / div)
        # Yahoo未更新で基準日と出来高日がズレる場合のみ日付を併記(誤認防止)
        vd = v.get("date")
        asof = (f" <small>({vd.month}/{vd.day})</small>"
                if vd is not None and vd.strftime("%Y%m%d") != date else "")
        extra_kpi += (f"<div>{P['kpi_vol']}<br><b>{val}</b>{P['vol_unit']}"
                      f"{dtxt}{asof}</div>")
    if extras.get("sq"):
        sq = extras["sq"]
        t = sq["type_ja"] if lang == "ja" else sq["type_en"]
        days = (f"あと{sq['days']}日" if lang == "ja" else f"in {sq['days']}d")
        extra_kpi += (f"<div>{P['kpi_sq']}<br><b>{sq['date'].month}/{sq['date'].day}</b>"
                      f" {t}・{days}</div>")

    mini_section = ""
    if charts.get("mini"):
        mini_section = (f'<h2 id="mini">{P["sec_mini"].format(exp=extras.get("mini_label", ""))}</h2>\n'
                        f'  <p>{P["mini_lead"]}</p>\n'
                        f'  <img src="{charts["mini"]}" alt="Mini options OI">')

    flows_section = ""
    if charts.get("investor"):
        flows_section = (f'<h2 id="flows">{P["sec_flows"]}</h2>\n'
                         f'  <p>{P["flows_lead"].format(latest=extras.get("flows_latest", ""))}</p>\n'
                         f'  <img src="{charts["investor"]}" alt="Foreign investor flows">')

    weekly_section = ""
    if tables.get("weekly"):
        chart_part = (
            f'<p>{P["wk_chart_lead"]}</p>\n  <img src="{charts["participants"]}" '
            f'alt="Net OI by participant">\n  '
            if charts.get("participants") else ""
        )
        weekly_section = (f'<h2 id="weekly">{P["sec_weekly"]}</h2>\n  '
                          f'{chart_part}{tables["weekly"]}')
    # 冒頭サマリー。数秒しか見ない訪問者に「今日の要点」だけ先に届ける。
    summary_section = ""
    try:
        sp = extras.get("spot")
        chg = extras.get("chg")
        bits = []
        if sp:
            if chg is not None:
                bits.append(P["sm_price"].format(spot=sp, chg=chg))
            else:
                bits.append(P["sm_price_only"].format(spot=sp))
        if pcr.get("pcr"):
            prev = extras.get("pcr_prev")
            if prev:
                bits.append(P["sm_pcr_prev"].format(v=pcr["pcr"], p=prev))
            else:
                bits.append(P["sm_pcr"].format(v=pcr["pcr"]))
        w = extras.get("walls") or {}
        if w.get("call") and w.get("put"):
            bits.append(P["sm_walls"].format(c=w["call"][0], p=w["put"][0]))
        if bits:
            summary_section = (
                '<p class="summary">' + "".join(bits) + '</p>')
    except Exception:
        summary_section = ""

    # データ源ごとの基準日。JPXは公表時刻が異なる(手口17:45頃 / 建玉20:00頃)ため、
    # どのデータがいつ時点なのかを明示して誤読を防ぐ。
    def _fmt(x):
        x = str(x)
        return f"{x[:4]}/{x[4:6]}/{x[6:]}" if len(x) == 8 and x.isdigit() else x
    parts = []
    if extras.get("src_volume"):
        parts.append(P["src_volume"].format(d=_fmt(extras["src_volume"])))
    if extras.get("pv"):
        parts.append(P["src_pv"].format(d=_fmt(extras["pv"]["date"])))
    if extras.get("src_oi"):
        parts.append(P["src_oi"].format(d=_fmt(extras["src_oi"])))
    src_dates = " ／ ".join(parts) if lang == "ja" else " / ".join(parts)

    # オプションのヘッジが値動きに与える向き
    hedge_section = ""
    hp = extras.get("hedge")
    if hp and charts.get("hedge"):
        by = hp["by_strike"]
        up = by[by["strike"] > hp["spot"]]["force"].sum() / 1e8
        dn = by[by["strike"] < hp["spot"]]["force"].sum() / 1e8
        tot = hp["total"] / 1e8
        word = P["hedge_damp"] if tot >= 0 else P["hedge_amp"]
        summary_line = P["hedge_sum"].format(up=up, dn=dn, total=tot, word=word)
        hedge_section = (
            f'<h2 id="hedge">{P["sec_hedge"]}</h2>'
            f'<p>{P["hedge_lead"]}</p>'
            f'<p><b>{summary_line}</b></p>'
            f'<img src="{charts["hedge"]}" alt="Option hedging direction by strike">'
            f'<p>{P["hedge_more"]}</p>')

    # 手口上位一覧(日次)。建玉より早く公表されるので独立セクションにする。
    pv_section = ""
    if extras.get("pv"):
        inner = participant_volume_html(extras["pv"], lang)
        if inner:
            pv_section = f'<h2 id="pv">{P["sec_pv"]}</h2>\n  {inner}'

    # 建玉分布にミニを合算した場合の注記
    mini_note = ""
    if extras.get("mini_merged"):
        mini_note = " " + P["mini_note"].format(n=extras["mini_merged"])

    # 先物の出来高: ラージ/mini/マイクロをラージ換算で並べる
    fut_section = ""
    if extras.get("fut_vol"):
        rows, tot_eq, tot_val = [], 0.0, 0
        for fv in extras["fut_vol"]:
            tot_eq += fv["large_equiv"]
            tot_val += fv["value"]
            rows.append(
                f"<tr><td class='name'>{html.escape(fv['product'])}</td>"
                f"<td>{fv['volume']:,}</td><td>{fv['large_equiv']:,.0f}</td>"
                f"<td>{fv['value'] / 1e12:.2f}兆円</td></tr>"
                if lang == "ja" else
                f"<tr><td class='name'>{html.escape(fv['product'])}</td>"
                f"<td>{fv['volume']:,}</td><td>{fv['large_equiv']:,.0f}</td>"
                f"<td>{fv['value'] / 1e12:.2f} tn yen</td></tr>")
        unit = "兆円" if lang == "ja" else " tn yen"
        rows.append(f"<tr class='spot'><td>{P['fut_total']}</td><td>-</td>"
                    f"<td>{tot_eq:,.0f}</td><td>{tot_val / 1e12:.2f}{unit}</td></tr>")
        head = "".join(f"<th>{c}</th>" for c in P["fut_cols"])
        fut_section = (f"<h2 id=\"fut\">{P['sec_fut']}</h2>\n  <p>{P['fut_lead']}</p>\n"
                       f"  <div class='tbl-scroll'><table><tr>{head}</tr>"
                       f"{''.join(rows)}</table></div>")

    # データの読み方ガイドへの導線。GA4(2026-07-27)ではトップに64%のビューが集中し
    # 解説記事まで回遊していなかったため、本文中の小さなリンクとは別にカード型で明示する。
    guide_section = (
        f'<h2 id="guides">{P["sec_guides"]}</h2>\n'
        f'  <p>{P["guides_lead"]}</p>\n'
        '  <div style="display:grid; gap:10px; '
        'grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); margin-bottom:8px;">\n'
        + "".join(
            f'    <a href="{href}" '  # 日英ともガイドはトップと同じ階層に出力される
            'style="display:block; padding:12px 14px; border:1px solid var(--line); '
            'border-radius:10px; background:var(--panel); text-decoration:none;">'
            f'<b style="color:#1f6fd0">{title}</b>'
            f'<br><span style="font-size:0.88em; color:var(--ink2)">{desc}</span></a>\n'
            for href, title, desc in P["guides"])
        + '  </div>'
    )
    nav_ids = ["#market", "#oitable", "#oi", "#weekly", "#pcr"]
    nav = site_nav(lang, P["lang_switch"], anchors=list(zip(nav_ids, P["nav"])))
    html_doc = f"""<!DOCTYPE html>
<html lang="{P['html_lang']}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{GSV_META}
{og}
<title>{P['title']}</title>
<meta name="description" content="{P['desc']}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">
<style>{CSS_MAIN}</style>
</head>
<body>
<header>
  <h1>{P['h1']}</h1>
  <p class="updated">{P['updated'].format(d=d, now=now)}</p>
  <p class="updated src-dates">{src_dates}</p>
  {nav}
</header>
<p class="tagline">{P['tagline']}</p>
<main>
  {summary_section}
  <div class="kpi">
    <div>{P['kpi'][0]}<br><b>{pcr['pcr']}</b></div>
    <div>{P['kpi'][1]}<br><b>{pcr['put_volume']:,}</b>{P['unit']}</div>
    <div>{P['kpi'][2]}<br><b>{pcr['call_volume']:,}</b>{P['unit']}</div>
    {extra_kpi}
  </div>
  <p class="kpi-guide">{P['kpi_guide']}</p>

  {market_section}

  <h2 id="oitable">{P['sec_oitable']}</h2>
  {tables['oi']}

  <h2 id="oi">{P['sec_oi']}</h2>
  <p>{P['oi_lead']}{mini_note}</p>
  <img src="{charts['oi']}" alt="Open interest by strike">

  {mini_section}

  {hedge_section}

  {fut_section}

  {pv_section}

  {weekly_section}

  {flows_section}

  <h2 id="pcr">{P['sec_pcr']}</h2>
  <p>{P['pcr_lead']}</p>
  <img src="{charts['pcr']}" alt="Put/Call ratio trend">

  {guide_section}
</main>
<footer>
  {footer_sitemap(lang)}
  <p>{P['footer_src']}</p>
  <p>{P['footer_disclaimer']}</p>
</footer>
</body>
</html>
"""
    out_path = os.path.join(SITE, P["out"])
    os.makedirs(os.path.dirname(out_path) or SITE, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_doc)


def compose_post(date: str, pcr: dict, oi: pd.DataFrame, expiry: str,
                 spot: float | None, vol_info: dict | None = None) -> str:
    """X投稿用の下書きテキストを生成し、site/post.txt にも出力する。"""
    d = f"{int(date[4:6])}/{int(date[6:])}"
    exp_label = f"{int(expiry[2:])}月限"
    near = oi[oi["expiry"] == expiry]
    lines = [f"【日経225オプションデータ {d}】", ""]
    mood = "プット優勢" if pcr["pcr"] and pcr["pcr"] > 1 else "コール優勢"
    lines.append(f"Put/Callレシオ: {pcr['pcr']}({mood})")
    lines.append(f"プット出来高 {pcr['put_volume']:,}枚 / コール出来高 {pcr['call_volume']:,}枚")
    lines.append("")
    lines.append(f"{exp_label}の最大建玉")
    for t, name in (("C", "コール"), ("P", "プット")):
        sub = near[near["type"] == t]
        if len(sub):
            row = sub.loc[sub["oi"].idxmax()]
            lines.append(f"・{name}: {int(row['strike']):,}円({int(row['oi']):,}枚)")
    # 建玉が最も増えた銘柄(前日比)
    inc = near.loc[near["change"].idxmax()] if len(near) else None
    if inc is not None and inc["change"] > 0:
        t_label = "コール" if inc["type"] == "C" else "プット"
        lines.append("")
        lines.append(f"建玉増加トップ: {t_label} {int(inc['strike']):,}円(+{int(inc['change']):,}枚)")
    if spot:
        lines.append("")
        lines.append(f"日経平均終値: {spot:,.0f}円")
    if vol_info:
        pct = vol_info.get("pct")
        pct_txt = f"(前日比 {pct:+.0f}%)" if pct is not None else ""
        vd = vol_info.get("date")
        asof = (f" ※{vd.month}/{vd.day}時点"
                if vd is not None and vd.strftime("%Y%m%d") != date else "")
        lines.append(f"日経売買高: {vol_info['value'] / 1e8:.2f}億株{pct_txt}{asof}")
    text = "\n".join(lines)
    os.makedirs(SITE, exist_ok=True)
    with open(os.path.join(SITE, "post.txt"), "w", encoding="utf-8") as f:
        f.write(text)
    return text


RISKPAGE = {
    "ja": {
        "title": "マクロリスクモニター | 景気後退・インフレ再燃・金融ストレスの兆候チェック",
        "h1": "マクロリスクモニター",
        "updated": "最終更新: {now} JST(毎営業日 自動更新。指標により月次・週次)",
        "lead": "米国の公式統計・市場データから、リスクイベントの兆候を機械的にチェックするページです。信号は出典に記載の閾値による自動判定で、当サイトの相場予想ではありません。",
        "groups": {"recession": "景気後退リスク", "inflation": "インフレ再燃リスク", "stress": "金融ストレス"},
        "cols": ["信号", "指標", "最新値", "基準日", "判定基準"],
        "legend": "●緑=平常 / ●黄=注意 / ●赤=警告",
        "summary": "現在の状態: 緑 {g} / 黄 {y} / 赤 {r}",
        "sec_chart": "主要指標の推移(直近3年)",
        "back": '<a href="./">← 日本市場データへ</a><a href="us.html">米国市場</a>',
        "lang_switch": '<a href="en/risk.html" lang="en">English</a>',
        "footer_src": "データ出典: FRED(セントルイス連銀)、ニューヨーク連銀公表データより当サイト作成。閾値は各出典・学術研究・市場慣行に基づく目安です。",
        "out": "risk.html", "prefix": "",
    },
    "en": {
        "title": "Macro Risk Monitor | Recession, Inflation & Financial Stress Signals",
        "h1": "Macro Risk Monitor",
        "updated": "Last updated {now} JST (auto-updated every business day; some series weekly/monthly)",
        "lead": "A mechanical check of risk-event signals from official US statistics and market data. Signals are threshold-based flags per the cited sources — not this site's market forecast.",
        "groups": {"recession": "Recession Risk", "inflation": "Inflation Re-acceleration Risk", "stress": "Financial Stress"},
        "cols": ["Signal", "Indicator", "Latest", "As of", "Threshold Basis"],
        "legend": "●Green = normal / ●Yellow = caution / ●Red = warning",
        "summary": "Current status: {g} green / {y} yellow / {r} red",
        "sec_chart": "Key Series (3 years)",
        "back": '<a href="../">← Nikkei data</a><a href="us.html">US Markets</a>',
        "lang_switch": '<a href="../risk.html" lang="ja">日本語</a>',
        "footer_src": "Data sources: FRED (St. Louis Fed), Federal Reserve Bank of New York. Thresholds are guideline values based on the cited sources, academic research and market convention.",
        "out": os.path.join("en", "risk.html"), "prefix": "../",
    },
}


def chart_risk(series: dict, lang: str) -> str | None:
    """主要リスク指標6系列の3年チャート。"""
    suffix = L[lang]["suffix"]
    panels = [
        ("T10Y3M", "イールドカーブ(10年-3ヶ月, %)", "Yield Curve (10y-3m, %)", 0.0),
        ("SAHMREALTIME", "Sahmルール", "Sahm Rule", 0.5),
        ("RECPROUSM156N", "景気後退確率(C-P, %)", "Recession Prob. (C-P, %)", 50),
        ("T10YIE", "期待インフレ(10年BEI, %)", "10y Breakeven (%)", 3.0),
        ("BAMLH0A0HYM2", "HY債スプレッド(%)", "High Yield Spread (%)", 6.0),
        ("VIXCLS", "VIX", "VIX", 30),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(11, 6))
    drawn = 0
    for ax, (sid, ja, en, thresh) in zip(axes.flat, panels):
        s = series.get(sid)
        if s is None or len(s) == 0:
            ax.axis("off")
            continue
        s3 = s[s.index >= s.index[-1] - pd.Timedelta(days=365 * 3)]
        ax.plot(s3.index, s3.values, color=ACCENT, linewidth=1.2)
        ax.axhline(thresh, color=UP, linestyle="--", linewidth=0.9, alpha=0.8)
        ax.set_title(ja if lang == "ja" else en, fontsize=9)
        ax.grid(alpha=0.25)
        ax.tick_params(labelsize=7)
        drawn += 1
    if drawn == 0:
        plt.close(fig)
        return None
    sup = ("マクロリスク指標(赤点線=警告水準の目安)" if lang == "ja"
           else "Macro Risk Indicators (red dashed = warning threshold)")
    fig.suptitle(sup, fontsize=11)
    fig.tight_layout()
    os.makedirs(IMG, exist_ok=True)
    name = f"risk{suffix}.png"
    fig.savefig(os.path.join(IMG, name), dpi=120)
    plt.close(fig)
    return f"img/{name}"


def chart_rates(series: dict, lang: str) -> str | None:
    """日米10年金利差とドル円(3年)。"""
    suffix = L[lang]["suffix"]
    us10 = series.get("DGS10")
    jp10 = series.get("IRLTLT01JPM156N")
    fx = series.get("DEXJPUS")
    if us10 is None or jp10 is None or fx is None:
        return None
    jp_d = jp10.reindex(us10.index, method="ffill")
    spread = (us10 - jp_d).dropna()
    spread = spread[spread.index >= spread.index[-1] - pd.Timedelta(days=365 * 3)]
    fx3 = fx[fx.index >= fx.index[-1] - pd.Timedelta(days=365 * 3)]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 3.8))
    ax1.plot(spread.index, spread.values, color=DOWN, linewidth=1.3)
    ax1.set_title("日米10年金利差(%pt)" if lang == "ja" else "US-Japan 10y Yield Spread (%pt)",
                  fontsize=10)
    ax1.grid(alpha=0.25)
    ax2.plot(fx3.index, fx3.values, color=ACCENT, linewidth=1.3)
    ax2.set_title("ドル円" if lang == "ja" else "USD/JPY", fontsize=10)
    ax2.grid(alpha=0.25)
    fig.autofmt_xdate()
    fig.tight_layout()
    name = f"rates{suffix}.png"
    fig.savefig(os.path.join(IMG, name), dpi=120)
    plt.close(fig)
    return f"img/{name}"


def render_risk(risk: dict, lang: str, chart_rel: str | None,
                rates_rel: str | None = None) -> None:
    P = RISKPAGE[lang]
    og = og_meta(P["title"])
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    ver = datetime.now(JST).strftime("%Y%m%d%H%M")
    counts = {"green": 0, "yellow": 0, "red": 0}
    for it in risk["items"]:
        counts[it["signal"]] += 1

    sections = []
    for gkey, gname in P["groups"].items():
        rows = []
        for it in (x for x in risk["items"] if x["group"] == gkey):
            dot = f"<span class='sig sig-{it['signal']}'>●</span>"
            name = it["ja"] if lang == "ja" else it["en"]
            basis = it["basis_ja"] if lang == "ja" else it["basis_en"]
            rows.append(f"<tr><td style='text-align:center'>{dot}</td>"
                        f"<td class='name'>{name}</td><td>{it['disp']}</td>"
                        f"<td>{it['date']}</td><td class='basis'>{basis}</td></tr>")
        head = "".join(f"<th>{c}</th>" for c in P["cols"])
        sections.append(f"<h2>{gname}</h2><div class='tbl-pair'><div class='tbl-box' style='flex:1 1 100%'>"
                        f"<div class='tbl-scroll'><table><tr>{head}</tr>{''.join(rows)}</table></div></div></div>")

    chart_html = ""
    if chart_rel:
        chart_html = (f"<h2>{P['sec_chart']}</h2>\n"
                      f'<img src="{P["prefix"]}{chart_rel}?v={ver}" alt="macro risk indicators">')
    if rates_rel:
        sec = "日米金利差とドル円" if lang == "ja" else "US-Japan Rate Spread & USD/JPY"
        chart_html += (f"\n<h2>{sec}</h2>\n"
                       f'<img src="{P["prefix"]}{rates_rel}?v={ver}" alt="rates and USDJPY">')

    html_doc = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{GSV_META}
{og}
<title>{P['title']}</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">
<style>{CSS_MAIN}</style>
</head>
<body>
<header>
  <h1>{P['h1']}</h1>
  <p class="updated">{P['updated'].format(now=now)}</p>
  {site_nav(lang, P['lang_switch'])}
</header>
<main>
  <p>{P['lead']}</p>
  <div class="kpi">
    <div>{P['summary'].format(g=counts['green'], y=counts['yellow'], r=counts['red'])}<br>
    <b><span class='sig sig-green'>●</span>{counts['green']}
       <span class='sig sig-yellow'>●</span>{counts['yellow']}
       <span class='sig sig-red'>●</span>{counts['red']}</b></div>
  </div>
  <p>{P['legend']}</p>
  {''.join(sections)}
  {chart_html}
</main>
<footer>
  {footer_sitemap(lang)}
  <p>{P['footer_src']}</p>
  <p>{PAGE[lang]['footer_disclaimer']}</p>
</footer>
</body>
</html>
"""
    out_path = os.path.join(SITE, P["out"])
    os.makedirs(os.path.dirname(out_path) or SITE, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_doc)


FEDPAGE = {
    "ja": {
        "title": "FRB要人発言・公式文書トラッカー | FOMC声明・講演・議会証言",
        "h1": "FRB要人発言トラッカー",
        "updated": "最終更新: {now} JST(毎営業日 自動更新)",
        "lead": "米連邦準備制度理事会(FRB)の公式サイトから、FOMC関連リリース・講演・議会証言を自動収集しています。リンク先はすべて英語の原文(federalreserve.gov)です。FOMC声明など重要文書の日本語解説は、今後不定期で追加予定です。",
        "cols": ["日付", "タイトル(英語原文へのリンク)"],
        "back": '<a href="./">← 日本市場データ</a><a href="us.html">米国市場</a><a href="risk.html">リスクモニター</a>',
        "lang_switch": '<a href="en/fedwatch.html" lang="en">English</a>',
        "footer_src": "出典: Board of Governors of the Federal Reserve System(federalreserve.gov)公式RSS。",
        "out": "fedwatch.html", "prefix": "",
    },
    "en": {
        "title": "Fed Watch | FOMC Releases, Speeches & Testimony Tracker",
        "h1": "Fed Watch",
        "updated": "Last updated {now} JST (auto-updated every business day)",
        "lead": "Latest FOMC-related releases, speeches and congressional testimony, collected automatically from the Federal Reserve Board's official RSS feeds. All links go to original documents on federalreserve.gov.",
        "cols": ["Date", "Title"],
        "back": '<a href="../">← Nikkei data</a><a href="us.html">US Markets</a><a href="risk.html">Risk Monitor</a>',
        "lang_switch": '<a href="../fedwatch.html" lang="ja">日本語</a>',
        "footer_src": "Source: Board of Governors of the Federal Reserve System (federalreserve.gov) official RSS feeds.",
        "out": os.path.join("en", "fedwatch.html"), "prefix": "../",
    },
}


def render_fedwatch(feeds: dict, lang: str) -> None:
    import fed_watch
    P = FEDPAGE[lang]
    og = og_meta(P["title"])
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    sections = []
    head = "".join(f"<th>{c}</th>" for c in P["cols"])
    for f in fed_watch.FEEDS:
        items = feeds.get(f["key"], [])
        if not items:
            continue
        rows = "".join(
            f"<tr><td style='white-space:nowrap'>{it['date']}</td>"
            f"<td class='name'><a href='{it['link']}' rel='noopener' target='_blank'>"
            f"{html.escape(it['title'])}</a></td></tr>"
            for it in items)
        sections.append(f"<h2>{f[lang]}</h2><div class='tbl-pair'>"
                        f"<div class='tbl-box' style='flex:1 1 100%'><div class='tbl-scroll'>"
                        f"<table><tr>{head}</tr>{rows}</table></div></div></div>")

    html_doc = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{GSV_META}
{og}
<title>{P['title']}</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">
<style>{CSS_MAIN}</style>
</head>
<body>
<header>
  <h1>{P['h1']}</h1>
  <p class="updated">{P['updated'].format(now=now)}</p>
  {site_nav(lang, P['lang_switch'])}
</header>
<main>
  <p>{P['lead']}</p>
  {''.join(sections)}
</main>
<footer>
  {footer_sitemap(lang)}
  <p>{P['footer_src']}</p>
  <p>{PAGE[lang]['footer_disclaimer']}</p>
</footer>
</body>
</html>
"""
    out_path = os.path.join(SITE, P["out"])
    os.makedirs(os.path.dirname(out_path) or SITE, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_doc)


USPAGE = {
    "ja": {
        "title": "米国市場データ | COTポジション・CBOE Put/Callレシオ",
        "h1": "米国市場データ",
        "updated": "COT基準日: {cot_date}(毎週金曜更新) | CBOE基準日: {pcr_date} | 最終更新: {now} JST",
        "kpi": ["CBOE 全体PCR", "株式PCR", "SPX PCR"],
        "sec_cot": "COT 投機筋ネットポジション(週次)",
        "cot_lead": "CFTC建玉明細報告より。株価指数・通貨はレバレッジファンド、金・原油はマネージドマネーのネットポジション(買い−売り)。毎週火曜時点のデータが金曜に公表されます。<b>灰色の線は各市場の価格(右軸)</b>で、ポジションの偏りと値動きを見比べられます。",
        "cot_cols": ["市場", "ネットポジション", "前週比"],
        "sec_pcr": "CBOE Put/Callレシオ(日次)",
        "pcr_lead": "米国オプション市場全体の弱気/強気の偏り。1.0超はプット優勢です。",
        "pcr_rows": {"total": "全体(Total)", "index": "指数(Index)", "equity": "株式(Equity)",
                     "spx": "SPX+SPXW", "vix": "VIX"},
        "pcr_cols": ["区分", "Put/Callレシオ"],
        "sec_letf": "レバレッジETFの規模と推定リバランス",
        "letf_lead": "レバレッジETF(TQQQ・SOXL等)は一定倍率を保つため、引けにかけて原資産を売買します。上昇日は買い・下落日は売りで、値動きを増幅する方向に働きます。<b>この力の大きさは各ETFの純資産に比例する</b>ため、まず残高の規模を掲載しています。表には純資産と当日リターンから推定した引けのリバランス額も併記します(推定値)。<b>オプションのヘッジとは別のメカニズムなので、単純に足し合わせることはできません。</b>",
        "letf_kpi": "推定リバランス額 合計($bn)",
        "letf_cols": ["ETF", "原資産", "レバレッジ", "純資産($bn)", "当日%", "推定フロー($bn)"],
        "kpi_0dte": "SPX最短限月の出来高シェア",
        "sec_spx": "SPXオプション: 建玉の壁とガンマエクスポージャー(推定)",
        "spx_lead": "CBOE遅延データ(前営業日終値時点)より、45日以内の限月・現値±10%を集計。ガンマエクスポージャーは「ディーラーはコール買い・プット売り」という一般的な仮定に基づく推定値で、実際のディーラーポジションを示すものではありません。プラス圏=相場の変動を抑える力、マイナス圏=変動を増幅する力が働きやすいと解釈されます。",
        "spx_kpi": ["SPX終値", "合計ガンマエクスポージャー($bn/1%)", "性質が変わる水準"],
        "back": '<a href="./">← 日本市場データへ</a>',
        "lang_switch": '<a href="en/us.html" lang="en">English</a>',
        "footer_src": "データ出典: CFTC(建玉明細報告)、Cboe Global Markets公表データより当サイト作成。",
        "out": "us.html", "prefix": "",
    },
    "en": {
        "title": "US Markets | COT Positioning & CBOE Put/Call Ratios",
        "h1": "US Markets Data",
        "updated": "COT as of {cot_date} (updated every Friday) | CBOE as of {pcr_date} | Last updated {now} JST",
        "kpi": ["CBOE Total P/C", "Equity P/C", "SPX P/C"],
        "sec_cot": "COT Speculator Net Positions (Weekly)",
        "cot_lead": "From the CFTC Commitments of Traders report. Leveraged funds for index/FX futures, managed money for gold/crude. Tuesday data, released Friday. <b>The gray line is the price of each market (right axis)</b>, so positioning can be compared against price action.",
        "cot_cols": ["Market", "Net Position", "WoW"],
        "sec_pcr": "CBOE Put/Call Ratios (Daily)",
        "pcr_lead": "Bearish/bullish skew of the US options market. Above 1.0 = puts dominant.",
        "pcr_rows": {"total": "Total", "index": "Index", "equity": "Equity",
                     "spx": "SPX+SPXW", "vix": "VIX"},
        "pcr_cols": ["Category", "Put/Call Ratio"],
        "sec_letf": "Leveraged ETF Size & Estimated Rebalancing",
        "letf_lead": "Leveraged ETFs (TQQQ, SOXL, etc.) rebalance into the close to maintain constant leverage: buying on up days, selling on down days — a momentum force. <b>Its size scales with each fund's AUM</b>, so the chart shows assets under management. The table also lists the estimated end-of-day rebalancing flow derived from AUM and the daily return (an estimate). <b>This is a different mechanism from options gamma exposure and cannot simply be added to it.</b>",
        "letf_kpi": "Estimated total rebalancing flow ($bn)",
        "letf_cols": ["ETF", "Underlying", "Leverage", "AUM($bn)", "Day%", "Est. flow($bn)"],
        "kpi_0dte": "SPX Nearest-Expiry Volume Share",
        "sec_spx": "SPX Options: OI Walls & Gamma Exposure (Estimate)",
        "spx_lead": "From Cboe delayed data (as of last US close), expiries within 45 days, strikes within ±10% of spot. GEX uses the standard naive assumption (dealers long calls, short puts) and is an estimate, not actual dealer positioning. Positive GEX tends to dampen volatility; negative GEX tends to amplify it.",
        "spx_kpi": ["SPX Close", "Total GEX ($bn/1%)", "Gamma Flip"],
        "back": '<a href="./">← Nikkei data</a>',
        "lang_switch": '<a href="../us.html" lang="ja">日本語</a>',
        "footer_src": "Data sources: CFTC Commitments of Traders; Cboe Global Markets.",
        "out": os.path.join("en", "us.html"), "prefix": "../",
    },
}


# COT各市場に重ねる価格のティッカー。投機筋のポジションと値動きを見比べられるようにする。
COT_PRICE_TICKERS = {
    "es": "^GSPC", "nq": "^NDX", "nikkei": "^N225", "jpy": "JPY=X",
    "eur": "EURUSD=X", "gbp": "GBPUSD=X", "gold": "GC=F", "silver": "SI=F",
    "copper": "HG=F", "wti": "CL=F", "natgas": "NG=F",
}


def fetch_cot_prices() -> dict:
    """COTパネルに重ねる価格を1年分まとめて取得する。失敗した銘柄は黙って飛ばす。"""
    out = {}
    for key, ticker in COT_PRICE_TICKERS.items():
        try:
            h = yf.Ticker(ticker).history(period="1y")["Close"].dropna()
            if len(h):
                h.index = h.index.tz_localize(None)
                out[key] = h
        except Exception as e:
            print(f"WARN: COT price {key}({ticker}) failed: {e}")
    return out


def chart_cot(cot: dict, lang: str, usdjpy: pd.Series | None = None,
              prices: dict | None = None) -> str:
    """全市場のネットポジション推移(スモールマルチプル)。各パネルに価格を重ねる。"""
    import us_data
    suffix = L[lang]["suffix"]
    markets = [m for m in us_data.COT_MARKETS if m["key"] in cot["markets"]]
    ncols = 3
    nrows = (len(markets) + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(11, 3 * nrows), sharex=False)
    axes = np.atleast_2d(axes)
    for ax, m in zip(axes.flat, markets):
        df = cot["markets"][m["key"]]
        x = pd.to_datetime(df["date"])
        color = ACCENT if df["net"].iloc[-1] >= 0 else UP
        ax.plot(x, df["net"], color=color, linewidth=1.3)
        ax.fill_between(x, df["net"], 0, color=color, alpha=0.15)
        ax.axhline(0, color=INK2, linewidth=0.7)
        # 価格を重ねる。ドル円だけはFRED由来の系列を優先し、無ければ共通取得分を使う。
        px = None
        if m["key"] == "jpy" and usdjpy is not None and len(usdjpy):
            px = usdjpy
        elif prices:
            px = prices.get(m["key"])
        drawn = False
        if px is not None and len(px):
            u = px[(px.index >= x.min()) & (px.index <= x.max())]
            if len(u):
                axp = ax.twinx()
                axp.plot(u.index, u.values, color="#6b7280", alpha=0.8, linewidth=1.2)
                axp.axis("off")
                drawn = True
        note = (" (灰線: 価格)" if lang == "ja" else " (gray: price)") if drawn else ""
        title = m[lang] + note
        ax.set_title(title, fontsize=9)
        ax.grid(alpha=0.25)
        ax.tick_params(labelsize=7)
        ax.yaxis.set_major_formatter(lambda v, _: f"{v/1000:,.0f}k")
    for ax in axes.flat[len(markets):]:
        ax.axis("off")
    sup = ("COT 投機筋ネットポジション(直近1年・枚)" if lang == "ja"
           else "COT Speculator Net Positions (1 year, contracts)")
    fig.suptitle(sup, fontsize=11)
    fig.tight_layout()
    os.makedirs(IMG, exist_ok=True)
    name = f"cot{suffix}.png"
    fig.savefig(os.path.join(IMG, name), dpi=120)
    plt.close(fig)
    return f"img/{name}"


def next_sq(today: datetime) -> dict:
    """次回SQ(第2金曜)の日付・残日数・種別(メジャー/マイナー)を返す。"""
    d = today.date()
    for add_month in range(0, 3):
        y = d.year + (d.month - 1 + add_month) // 12
        m = (d.month - 1 + add_month) % 12 + 1
        first = pd.Timestamp(y, m, 1)
        # 第2金曜 = 月内の金曜日リストの2番目
        fridays = [x.date() for x in pd.date_range(first, periods=14, freq="D")
                   if x.weekday() == 4]
        sq = fridays[1]
        if sq >= d:
            major = m in (3, 6, 9, 12)
            return {"date": sq, "days": (sq - d).days,
                    "type_ja": "メジャーSQ" if major else "オプションSQ",
                    "type_en": "Major SQ" if major else "Options SQ"}
    raise RuntimeError("SQ calc failed")


def chart_vi(vi: pd.DataFrame, lang: str) -> str:
    """日経VIの1年チャート(警戒水準ライン付き)。"""
    suffix = L[lang]["suffix"]
    s = vi["Close"]
    s = s[s.index >= s.index[-1] - pd.Timedelta(days=365)]
    fig, ax = plt.subplots(figsize=(10, 3.6))
    ax.plot(s.index, s.values, color=ACCENT, linewidth=1.4)
    ax.fill_between(s.index, s.values, s.values.min() * 0.95, color=ACCENT, alpha=0.08)
    for lv in (20, 30):
        ax.axhline(lv, color=UP if lv == 30 else INK2, linestyle="--", linewidth=0.9)
    ax.set_title("日経VI(日経平均ボラティリティー・インデックス、1年)" if lang == "ja"
                 else "Nikkei VI (Nikkei Volatility Index, 1 year)", fontsize=10)
    ax.grid(alpha=0.25)
    fig.autofmt_xdate()
    fig.tight_layout()
    os.makedirs(IMG, exist_ok=True)
    name = f"vi{suffix}.png"
    fig.savefig(os.path.join(IMG, name), dpi=120)
    plt.close(fig)
    return f"img/{name}"


def chart_mini_oi(mini: pd.DataFrame, spot: float | None, lang: str) -> tuple[str, str] | None:
    """ミニオプション(直近ウィークリー限月)の建玉分布チャート。"""
    suffix = L[lang]["suffix"]
    totals = mini.groupby("expiry")["oi"].sum()
    cands = [e for e in sorted(totals.index) if totals[e] > 500]
    if not cands:
        return None
    exp = cands[0]
    df = mini[mini["expiry"] == exp]
    strikes = sorted(df["strike"].unique())
    if spot:
        strikes = [s for s in strikes if 0.92 * spot <= s <= 1.08 * spot]
    puts = df[df["type"] == "P"].set_index("strike")["oi"].reindex(strikes).fillna(0)
    calls = df[df["type"] == "C"].set_index("strike")["oi"].reindex(strikes).fillna(0)
    fig, ax = plt.subplots(figsize=(11, 5))
    width = (strikes[1] - strikes[0]) * 0.8 if len(strikes) > 1 else 50
    ax.bar(strikes, calls.values, width=width, color=DOWN, label=L[lang]["call_oi"])
    ax.bar(strikes, -puts.values, width=width, color=UP, label=L[lang]["put_oi"])
    ax.axhline(0, color=INK2, linewidth=0.8)
    if spot:
        ax.axvline(spot, color=INK, linestyle="--", linewidth=1.2,
                   label=L[lang]["spot_line"].format(spot=spot))
    exp_label = f"{exp.month}/{exp.day}"
    ax.set_title((f"日経225ミニオプション 建玉分布({exp_label}限)" if lang == "ja"
                  else f"Nikkei 225 mini Options OI ({exp_label} expiry)"), fontsize=10)
    ax.yaxis.set_major_formatter(lambda x, _: f"{abs(x):,.0f}")
    ax.xaxis.set_major_formatter(lambda x, _: f"{x:,.0f}")
    ax.legend(loc="upper left")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    name = f"mini_oi{suffix}.png"
    fig.savefig(os.path.join(IMG, name), dpi=120)
    plt.close(fig)
    return f"img/{name}", exp_label


def chart_investor(flows: pd.DataFrame, lang: str, n225: pd.DataFrame | None = None) -> str:
    """海外投資家の週次ネット売買(棒)と累積(線)。単位: 千円→兆円は/1e9。

    上段: 累積ネット(線)+日経平均(灰線)。下段: 直近1年の週次ネット(棒)。
    """
    suffix = L[lang]["suffix"]
    df = flows.copy()
    df["dt"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["dt"]).sort_values("dt")
    df["tn"] = df["net_kyen"] / 1e9  # 兆円
    df["cum"] = df["tn"].cumsum()

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6.4),
                                   gridspec_kw={"height_ratios": [1.5, 1]})

    # 上段: 累積 + 日経平均
    ax1.plot(df["dt"], df["cum"], color=ACCENT, linewidth=2)
    ax1.fill_between(df["dt"], df["cum"], 0, color=ACCENT, alpha=0.12)
    ax1.axhline(0, color=INK2, linewidth=0.8)
    ax1.set_ylabel("累積(兆円)" if lang == "ja" else "Cumulative (tn yen)", fontsize=9)
    if n225 is not None and len(n225):
        n = n225[(n225.index >= df["dt"].min()) & (n225.index <= df["dt"].max())]
        if len(n):
            axp = ax1.twinx()
            axp.plot(n.index, n["Close"], color="#6b7280", alpha=0.8, linewidth=1.2)
            axp.set_ylabel("日経平均" if lang == "ja" else "Nikkei 225",
                           color="#8a97ad", fontsize=8)
            axp.tick_params(axis="y", labelcolor="#8a97ad", labelsize=7)
    ax1.set_title(("海外投資家の累積ネット売買(東証プライム・現物、灰線=日経平均)"
                   if lang == "ja" else
                   "Foreign Investors: Cumulative Net Buying (TSE Prime cash; gray = Nikkei 225)"),
                  fontsize=10)
    ax1.grid(alpha=0.2)

    # 下段: 直近1年の週次
    recent = df[df["dt"] >= df["dt"].max() - pd.Timedelta(days=365)]
    colors = [ACCENT if v >= 0 else UP for v in recent["tn"]]
    ax2.bar(recent["dt"], recent["tn"], width=5, color=colors)
    ax2.axhline(0, color=INK2, linewidth=0.8)
    ax2.set_ylabel("週次(兆円)" if lang == "ja" else "Weekly (tn yen)", fontsize=9)
    ax2.set_title(("週次ネット売買(直近1年)" if lang == "ja"
                   else "Weekly Net Buying (last 12 months)"), fontsize=9)
    ax2.grid(alpha=0.2)

    # 上下でx軸の期間が異なるため、それぞれにラベルを出す
    for ax in (ax1, ax2):
        for lb in ax.get_xticklabels():
            lb.set_rotation(30)
            lb.set_ha("right")
        ax.tick_params(axis="x", labelsize=8)
    fig.tight_layout()
    name = f"investor{suffix}.png"
    fig.savefig(os.path.join(IMG, name), dpi=120)
    plt.close(fig)
    return f"img/{name}"


def chart_participants(hist: pd.DataFrame, n225: pd.DataFrame | None, lang: str) -> str | None:
    """参加者別ネット建玉の週次推移(棒)+日経平均(灰線)の個社別スモールマルチプル。"""
    suffix = L[lang]["suffix"]
    df = hist[hist["product"] == "日経225先物"].copy()
    if len(df) == 0:
        return None
    df["dt"] = pd.to_datetime(df["date"], format="%Y%m%d")
    latest = df["dt"].max()
    top = (df[df["dt"] == latest].assign(mag=lambda x: x["net"].abs())
           .nlargest(12, "mag")["participant"].tolist())

    fig, axes = plt.subplots(4, 3, figsize=(11, 12), sharex=True)
    for ax, name in zip(axes.flat, top):
        sub = df[df["participant"] == name].sort_values("dt")
        colors = [ACCENT if v >= 0 else UP for v in sub["net"]]
        ax.bar(sub["dt"], sub["net"], width=5, color=colors)
        ax.axhline(0, color=INK2, linewidth=0.7)
        if n225 is not None and len(sub) > 1:
            n = n225[(n225.index >= sub["dt"].min()) & (n225.index <= latest)]
            if len(n):
                axp = ax.twinx()
                axp.plot(n.index, n["Close"], color="#6b7280", alpha=0.8, linewidth=1.2)
                axp.axis("off")
        ax.set_title(name, fontsize=8.5)
        ax.grid(alpha=0.2)
        ax.tick_params(labelsize=7)
        ax.yaxis.set_major_formatter(lambda v, _: f"{v/1000:,.0f}k")
    for ax in axes.flat[len(top):]:
        ax.axis("off")
    sup = ("日経225先物 参加者別ネット建玉の推移(週次・直近1年・上位12社)" if lang == "ja"
           else "Nikkei 225 Futures: Net OI by Participant (weekly, 1yr, top 12)")
    fig.suptitle(sup, fontsize=11)
    fig.tight_layout()
    os.makedirs(IMG, exist_ok=True)
    name_f = f"participants{suffix}.png"
    fig.savefig(os.path.join(IMG, name_f), dpi=120)
    plt.close(fig)
    return f"img/{name_f}"


def chart_letf(history: pd.DataFrame, letf: dict, lang: str) -> str | None:
    """レバレッジETFの純資産(残高)を描く。

    以前は推定リバランス額の日次推移を棒で出していたが、日々の符号が
    相場次第で反転するだけで、系列として意味を読み取りにくかった。
    残高の方が「この仕組みがどれだけの規模で効いているか」を素直に表す。

    残高が積み上がっているほどリバランスの力も大きくなるので、
    規模の増減は残高の推移で見るのが素直。
    """
    suffix = L[lang]["suffix"]
    ja = lang == "ja"
    df = history.copy() if history is not None else pd.DataFrame()
    if len(df) and "total_aum_bn" in df.columns:
        df = df[df["date"].astype(str).str.fullmatch(r"20\d{6}")]
        df = df[df["total_aum_bn"].notna()]
    else:
        df = pd.DataFrame()

    if len(df) >= 3:
        x = pd.to_datetime(df["date"], format="%Y%m%d")
        vals = df["total_aum_bn"].astype(float)
        fig, ax = plt.subplots(figsize=(10, 3.8))
        ax.plot(x, vals, color=ACCENT, linewidth=1.8)
        ax.fill_between(x, vals, 0, color=ACCENT, alpha=0.18)
        ax.set_ylim(bottom=0)
        cur, lo, hi = vals.iloc[-1], vals.min(), vals.max()
        ax.annotate(f"{cur:,.0f}", (x.iloc[-1], cur), textcoords="offset points",
                    xytext=(4, 5), fontsize=9, color=ACCENT, fontweight="bold")
        ax.set_ylabel("純資産($bn)" if ja else "AUM ($bn)", fontsize=9)
        ax.set_title((f"主要レバレッジETFの純資産合計の推移(レンジ {lo:,.0f}〜{hi:,.0f} $bn)" if ja
                      else f"Total AUM of Major Leveraged ETFs (range {lo:,.0f}-{hi:,.0f} $bn)"),
                     fontsize=10)
        ax.grid(alpha=0.25)
        fig.autofmt_xdate()
    else:
        items = (letf or {}).get("items") or []
        if not items:
            return None
        items = sorted(items, key=lambda r: r["aum_bn"])
        fig, ax = plt.subplots(figsize=(10, max(3.0, 0.42 * len(items) + 1.2)))
        ax.barh([r["sym"] for r in items], [r["aum_bn"] for r in items],
                color=ACCENT, alpha=0.85)
        for i, r in enumerate(items):
            ax.text(r["aum_bn"], i, f" {r['aum_bn']:,.1f}", va="center",
                    fontsize=8, color=INK2)
        ax.set_xlabel("純資産($bn)" if ja else "AUM ($bn)", fontsize=9)
        ax.set_title(("主要レバレッジETFの純資産(銘柄別)" if ja
                      else "AUM of Major Leveraged ETFs"), fontsize=10)
        ax.grid(alpha=0.25, axis="x")

    fig.tight_layout()
    os.makedirs(IMG, exist_ok=True)
    name = f"letf{suffix}.png"
    fig.savefig(os.path.join(IMG, name), dpi=120)
    plt.close(fig)
    return f"img/{name}"




def chart_spx(res: dict, lang: str) -> str:
    """SPXの建玉分布とガンマエクスポージャーを縦2段で描く。

    日経(chart_oi_distribution / chart_hedge)と同じ流儀に揃えている:
    - 建玉は「壁」の位置を正確に読ませたいので縦棒のまま平滑化しない
    - ガンマは連続的な量なので、なめらかな曲線にして符号で塗り分ける
    どちらも横軸を行使価格に取り、現値を縦の破線で示す。
    """
    suffix = L[lang]["suffix"]
    spot = res["spot"]
    walls = res["walls"].copy()
    walls["bin"] = (walls["strike"] // 25) * 25
    gex = res["gex"].copy()
    gex["bin"] = (gex["strike"] // 25) * 25
    gex_b = (gex.groupby("bin")["gex"].sum() / 1e9).sort_index()

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 9), sharex=True)

    puts = walls[walls["type"] == "P"].groupby("bin")["oi"].sum()
    calls = walls[walls["type"] == "C"].groupby("bin")["oi"].sum()
    bins = sorted(set(puts.index) | set(calls.index))
    width = (bins[1] - bins[0]) * 0.8 if len(bins) > 1 else 20
    ax1.bar(bins, calls.reindex(bins).fillna(0), width=width, color=DOWN,
            label="Call OI" if lang == "en" else "コール建玉")
    ax1.bar(bins, -puts.reindex(bins).fillna(0), width=width, color=UP,
            label="Put OI" if lang == "en" else "プット建玉")
    ax1.axhline(0, color=INK2, linewidth=0.8)
    ax1.axvline(spot, color=INK, linestyle="--", linewidth=1.2,
                label=f"SPX {spot:,.0f}")
    ax1.set_title("SPX Open Interest by Strike" if lang == "en"
                  else "SPX 行使価格別建玉(壁)", fontsize=10)
    ax1.set_ylabel("Open interest" if lang == "en" else "建玉", fontsize=9)
    ax1.yaxis.set_major_formatter(lambda x, _: f"{abs(x)/1000:,.0f}k")
    ax1.legend(loc="upper left", fontsize=8)
    ax1.grid(alpha=0.25)

    gx, gy = _smooth(gex_b.index.tolist(), gex_b.values)
    ax2.plot(gx, gy, color=INK2, linewidth=1.4)
    ax2.fill_between(gx, gy, 0, where=(gy >= 0), color=ACCENT, alpha=0.55,
                     interpolate=True)
    ax2.fill_between(gx, gy, 0, where=(gy < 0), color=UP, alpha=0.55,
                     interpolate=True)
    ax2.axhline(0, color=INK2, linewidth=0.9)
    ax2.axvline(spot, color=INK, linestyle="--", linewidth=1.2)
    if res["flip"]:
        ax2.axvline(res["flip"], color=WARN, linestyle=":", linewidth=1.6,
                    label=("Gamma flip" if lang == "en" else "性質が変わる水準")
                    + f" {res['flip']:,.0f}")
        ax2.legend(loc="upper left", fontsize=8)
    total = res["total_gex"] / 1e9
    ax2.set_title((f"Net Gamma Exposure (Total {total:+,.1f} $bn/1%)" if lang == "en"
                   else f"ガンマエクスポージャー(合計 {total:+,.1f} $bn/1%)"), fontsize=10)
    ax2.set_xlabel("Strike" if lang == "en" else "行使価格", fontsize=9)
    ax2.set_ylabel(("Dampen ↑ | ↓ Amplify" if lang == "en"
                    else "抑える ↑ | ↓ 増幅する"), fontsize=9)
    ax2.xaxis.set_major_formatter(lambda x, _: f"{x:,.0f}")
    ax2.grid(alpha=0.25, axis="y")

    sup = ("SPX Options: OI Walls & Estimated Gamma Exposure (45d expiries, ±10%)"
           if lang == "en" else
           "SPXオプション: 建玉の壁とガンマエクスポージャー推定(45日以内の限月・現値±10%)")
    fig.suptitle(sup, fontsize=11)
    fig.tight_layout()
    name = f"spx{suffix}.png"
    fig.savefig(os.path.join(IMG, name), dpi=120)
    plt.close(fig)
    return f"img/{name}"


def render_us(cot: dict, pcr_us: dict, lang: str, chart_rel: str,
              spx_res: dict | None = None, spx_chart: str | None = None,
              share: dict | None = None,
              letf: dict | None = None) -> None:
    import us_data
    P = USPAGE[lang]
    og = og_meta(P["title"])
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    ver = datetime.now(JST).strftime("%Y%m%d%H%M")
    chart_src = f"{P['prefix']}{chart_rel}?v={ver}"

    rows = []
    for m in us_data.COT_MARKETS:
        if m["key"] not in cot["markets"]:
            continue
        df = cot["markets"][m["key"]]
        net = int(df["net"].iloc[-1])
        wow = net - int(df["net"].iloc[-2])
        cls = "pos" if wow > 0 else ("neg" if wow < 0 else "")
        rows.append(f"<tr><td class='name'>{m[lang]}</td>"
                    f"<td>{net:+,}</td><td class='{cls}'>{wow:+,}</td></tr>")
    cot_head = "".join(f"<th>{c}</th>" for c in P["cot_cols"])
    pcr_head = "".join(f"<th>{c}</th>" for c in P["pcr_cols"])
    pcr_rows = "".join(f"<tr><td class='name'>{label}</td><td>{pcr_us[k]:.2f}</td></tr>"
                       for k, label in P["pcr_rows"].items() if pcr_us.get(k) is not None)

    spx_section = ""
    if spx_res and spx_chart:
        flip_txt = f"{spx_res['flip']:,.0f}" if spx_res["flip"] else "-"
        gex_bn = spx_res["total_gex"] / 1e9
        spx_src = f"{P['prefix']}{spx_chart}?v={ver}"
        share_kpi = ""
        if share:
            exp_lbl = f"{share['expiry'].month}/{share['expiry'].day}"
            share_kpi = (f"<div>{P['kpi_0dte']}<br><b>{share['share']*100:.0f}%</b>"
                         f" ({exp_lbl})</div>")
        spx_section = f"""
  <h2>{P['sec_spx']}{dl_link("spx_gex_history.csv", lang, P['prefix'])}</h2>
  <div class="kpi">
    <div>{P['spx_kpi'][0]}<br><b>{spx_res['spot']:,.0f}</b></div>
    <div>{P['spx_kpi'][1]}<br><b>{gex_bn:+,.1f}</b></div>
    <div>{P['spx_kpi'][2]}<br><b>{flip_txt}</b></div>
    {share_kpi}
  </div>
  <p>{P['spx_lead']}</p>
  <img src="{spx_src}" alt="SPX OI walls and gamma exposure">"""

    letf_section = ""
    if letf and letf.get("items"):
        total = letf["total_bn"]
        dir_ja = "引けに買い(上昇を増幅)" if total > 0 else "引けに売り(下落を増幅)"
        dir_en = "net buying into close (amplifies up-moves)" if total > 0 \
            else "net selling into close (amplifies down-moves)"
        rows = []
        for it in letf["items"]:
            cls = "pos" if it["flow_bn"] > 0 else ("neg" if it["flow_bn"] < 0 else "")
            rows.append(f"<tr><td class='name'>{it['sym']}</td><td class='name'>{it['underlying']}</td>"
                        f"<td>{it['lev']:+d}x</td><td>{it['aum_bn']:,.1f}</td>"
                        f"<td>{it['ret_pct']:+.2f}</td>"
                        f"<td class='{cls}'>{it['flow_bn']:+.3f}</td></tr>")
        head = "".join(f"<th>{c}</th>" for c in P["letf_cols"])
        letf_dl = dl_link("letf_history.csv", lang, P["prefix"])
        letf_chart_html = ""
        if letf.get("chart"):
            letf_chart_html = (f'\n  <img src="{P["prefix"]}{letf["chart"]}?v={ver}" '
                               f'alt="LETF rebalancing flow history">')
        letf_section = f"""
  <h2>{P['sec_letf']}{letf_dl}</h2>
  <div class="kpi">
    <div>{P['letf_kpi']}<br><b>{total:+,.2f}</b> ({dir_ja if lang == 'ja' else dir_en})</div>
  </div>
  <p>{P['letf_lead']}</p>{letf_chart_html}
  <div class="tbl-pair"><div class="tbl-box" style="flex:1 1 100%"><div class="tbl-scroll">
    <table><tr>{head}</tr>{''.join(rows)}</table>
  </div></div></div>"""

    html_doc = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{GSV_META}
{og}
<title>{P['title']}</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">
<style>{CSS_MAIN}</style>
</head>
<body>
<header>
  <h1>{P['h1']}</h1>
  <p class="updated">{P['updated'].format(cot_date=cot['date'], pcr_date=pcr_us['date'], now=now)}</p>
  {site_nav(lang, P['lang_switch'])}
</header>
<main>
  <div class="kpi">
    <div>{P['kpi'][0]}<br><b>{pcr_us['total']:.2f}</b></div>
    <div>{P['kpi'][1]}<br><b>{pcr_us['equity']:.2f}</b></div>
    <div>{P['kpi'][2]}<br><b>{pcr_us['spx']:.2f}</b></div>
  </div>

  <h2>{P['sec_cot']}{dl_link("cot_history.csv", lang, P['prefix'])}</h2>
  <p>{P['cot_lead']}</p>
  <img src="{chart_src}" alt="COT net positions">
  <div class="tbl-pair"><div class="tbl-box"><div class="tbl-scroll">
    <table><tr>{cot_head}</tr>{''.join(rows)}</table>
  </div></div></div>

  <h2>{P['sec_pcr']}</h2>
  <p>{P['pcr_lead']}</p>
  <div class="tbl-pair"><div class="tbl-box"><div class="tbl-scroll">
    <table><tr>{pcr_head}</tr>{pcr_rows}</table>
  </div></div></div>

  {spx_section}

  {letf_section}

</main>
<footer>
  {footer_sitemap(lang)}
  <p>{P['footer_src']}</p>
  <p>{PAGE[lang]['footer_disclaimer']}</p>
</footer>
</body>
</html>
"""
    out_path = os.path.join(SITE, P["out"])
    os.makedirs(os.path.dirname(out_path) or SITE, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_doc)


SUB_CSS = """
  :root { --bg: #f6f7f9; --panel: #ffffff; --panel2: #eef1f5; --ink: #111820; --ink2: #4b5563;
          --line: #dfe3e9; --aqua: #0f8a5f; }
  nav a { color: var(--ink2); text-decoration: none; font-size: 0.82em; margin-right: 6px;
          padding: 3px 10px; border: 1px solid var(--line); border-radius: 999px; display: inline-block; }
  nav a:hover { color: var(--ink); border-color: var(--aqua); }
  .site-header { padding-top: 14px; }
  .menu { display: none; position: relative; margin-top: 6px; }
  .menu summary { list-style: none; cursor: pointer; color: var(--ink2); font-size: 0.85em;
                  border: 1px solid var(--line); border-radius: 8px; padding: 4px 12px;
                  display: inline-block; user-select: none; }
  .menu summary::-webkit-details-marker { display: none; }
  .menu[open] summary { color: var(--ink); border-color: var(--aqua); }
  .menu-panel { position: absolute; left: 0; top: calc(100% + 6px); background: var(--panel);
                border: 1px solid var(--line); border-radius: 10px; padding: 8px; z-index: 30;
                min-width: 230px; box-shadow: 0 10px 28px rgba(17,24,32,0.14); }
  .menu-panel a { display: block; padding: 9px 12px; color: var(--ink); text-decoration: none;
                  border-radius: 6px; font-size: 0.95em; border: none; margin: 0; }
  .menu-panel a:hover { background: var(--panel); }
  .menu-panel .sub { color: var(--ink2); font-size: 0.75em; padding: 8px 12px 2px;
                     border-top: 1px solid var(--line); margin-top: 6px; }
  @media (max-width: 600px) {
    nav.pills { display: none; }
    .menu { display: block; }
  }
  * { box-sizing: border-box; }
  body { font-family: "Noto Sans JP", "Yu Gothic", Meiryo, sans-serif; background: var(--bg);
         max-width: 820px; margin: 0 auto; padding: 0 20px 40px; color: var(--ink); line-height: 1.9; }
  h1 { font-size: 1.25em; margin: 24px 0 8px; }
  h1::before { content: "▮"; color: var(--aqua); margin-right: 8px; }
  h2 { font-size: 1.0em; margin: 28px 0 8px; padding-left: 10px; border-left: 3px solid var(--aqua); }
  p, li { color: var(--ink2); font-size: 0.92em; }
  a { color: #1f6fd0; }
  img { max-width: 100%; height: auto; }
  /* 解説記事の表。トップの数値表(全て右寄せ・nowrap)と違い1列目に文章が入るので、
     1列目だけ左寄せ・折り返しあり、数値列は右寄せにする。
     スマホでは表だけを横スクロールさせ、ページ本体を横に振らせない。 */
  .tbl-wrap { overflow-x: auto; margin: 12px 0; }
  table { border-collapse: collapse; width: 100%; font-size: 0.88em;
          font-variant-numeric: tabular-nums; background: var(--panel); }
  th, td { border: 1px solid var(--line); padding: 7px 10px; text-align: right; }
  th { background: var(--panel2); color: var(--ink2); font-weight: 500; }
  td { color: var(--ink2); }
  th:first-child, td:first-child { text-align: left; }
  footer { border-top: 1px solid var(--line); margin-top: 48px; padding-top: 10px;
           font-size: 0.78em; color: var(--ink2); }
"""


SITE_URL = "https://matsutoushi.github.io/nk225-option-site/"
GSV_META = ('<meta name="google-site-verification" content="2JN1JwTzW_V10lr6LymCE5AgMGsKG0uu4BI5QdwWz24">\n'
            '<script async src="https://www.googletagmanager.com/gtag/js?id=G-B0F8KB2KW7"></script>\n'
            '<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}'
            'gtag("js",new Date());gtag("config","G-B0F8KB2KW7");</script>')


def og_meta(title: str, desc: str = "") -> str:
    """OGP/Twitterカード用メタタグ(X告知でリンクカードを出すため)。"""
    img = SITE_URL + "img/market.png"
    return (f'<meta property="og:title" content="{title}">\n'
            f'<meta property="og:description" content="{desc}">\n'
            f'<meta property="og:image" content="{img}">\n'
            f'<meta property="og:type" content="website">\n'
            f'<meta name="twitter:card" content="summary_large_image">\n'
            f'<link rel="icon" type="image/png" href="{SITE_URL}favicon.png">')


# 全ページ共通のナビゲーションリンク(各言語のページからの相対パス)
NAV_LINKS = {
    "ja": [("./", "日経ダッシュボード"), ("us.html", "米国市場"),
           ("risk.html", "リスクモニター"), ("fedwatch.html", "要人発言"),
           ("tools.html", "データ分析ツール"),
           ("guide-start.html", "始め方ガイド"), ("glossary.html", "用語集")],
    "en": [("./", "Dashboard"), ("us.html", "US Markets"),
           ("risk.html", "Risk Monitor"), ("fedwatch.html", "Fed Watch"),
           ("tools.html", "Data Explorer"),
           ("guide-nikkei-options.html", "Nikkei Guide"),
           ("guide-participants.html", "Positioning Guide")],
}


def site_nav(lang: str, lang_switch: str = "", anchors: list | None = None) -> str:
    """共通ナビ: PC=ピル型 / スマホ=ハンバーガー(details要素・JS不要)。"""
    links = NAV_LINKS[lang]
    pills = "".join(f'<a href="{h}">{t}</a>' for h, t in links) + lang_switch
    menu_items = "".join(f'<a href="{h}">{t}</a>' for h, t in links)
    if anchors:
        label = "このページ内" if lang == "ja" else "On this page"
        menu_items += f'<div class="sub">{label}</div>'
        menu_items += "".join(f'<a href="{h}">{t}</a>' for h, t in anchors)
    menu_items += lang_switch.replace("<a ", '<a class="lang" ')
    menu_label = "☰ メニュー" if lang == "ja" else "☰ Menu"
    return (f'<nav class="pills">{pills}</nav>'
            f'<details class="menu"><summary>{menu_label}</summary>'
            f'<div class="menu-panel">{menu_items}</div></details>')


def footer_sitemap(lang: str) -> str:
    """フッターのサイトマップ(全コンテンツへの回遊リンク)。"""
    if lang == "ja":
        items = NAV_LINKS["ja"] + [
            ("guide-oi.html", "建玉分布の見方"), ("guide-pcr.html", "PCRとは"),
            ("guide-teguchi.html", "手口の見方"), ("guide-sq.html", "SQとは"),
            ("guide-gex.html", "ガンマエクスポージャーとは"), ("guide-cot.html", "COTの見方"),
            ("about.html", "運営者情報"), ("privacy.html", "プライバシーポリシー"),
            ("en/", "English")]
    else:
        items = NAV_LINKS["en"] + [
            ("../about.html", "About"), ("../privacy.html", "Privacy"),
            ("../", "日本語")]
    links = " ｜ ".join(f'<a href="{h}" style="color:#1f6fd0">{t}</a>' for h, t in items)
    return f'<p class="sitemap">{links}</p>'


# 公開するデータファイル {出力名: (元ファイル, 日本語説明, 英語説明)}
# 注意: JPX(東証)公表データは2次配布がライセンス上問題となりうるため、生CSVは公開しない
# (サイト上での可視化・加工表示のみ)。ここに載せるのは非JPX由来のみ。
PUBLIC_DATA = {
    "cot_history.csv": ("cot_history.csv",
                        "CFTC COT 投機筋ネットポジション(週次)",
                        "CFTC COT speculator net positions (weekly)"),
    "spx_gex_history.csv": ("spx_gex_history.csv",
                            "SPX ガンマエクスポージャー推定(日次)",
                            "SPX gamma exposure estimate (daily)"),
    "letf_history.csv": ("letf_history.csv",
                         "レバレッジETF 推定リバランス額(日次)",
                         "Leveraged ETF estimated rebalancing flow (daily)"),
    "risk_latest.csv": ("risk_latest.csv",
                        "マクロリスク指標 最新値",
                        "Macro risk indicators (latest)"),
}

# JPX由来でダウンロード提供しない出力名(念のため除外を明示)
JPX_NO_DOWNLOAD = {"oi_latest.csv", "participants_history.csv",
                   "pcr_history.csv", "investor_flows.csv"}


def publish_data_files() -> list:
    """非JPX由来の履歴CSVのみ site/data/ に公開する。Returns: 公開できたキーの一覧。"""
    out_dir = os.path.join(SITE, "data")
    os.makedirs(out_dir, exist_ok=True)
    # 過去にJPXデータを公開してしまっていた場合に備え、site/data/内の該当ファイルを削除
    for name in JPX_NO_DOWNLOAD:
        stale = os.path.join(out_dir, name)
        if os.path.exists(stale):
            os.remove(stale)
    published = []
    for name, (src, _, _) in PUBLIC_DATA.items():
        if name in JPX_NO_DOWNLOAD:
            continue
        src_path = os.path.join(DATA, src)
        if not os.path.exists(src_path):
            continue
        with open(src_path, "rb") as f:
            content = f.read()
        with open(os.path.join(out_dir, name), "wb") as f:
            f.write(content)
        published.append(name)
    print(f"published data files: {len(published)} (JPX data excluded)")
    return published


def dl_link(name: str, lang: str, prefix: str = "") -> str:
    """CSVダウンロードリンクの小さなHTML片。"""
    label = "CSVダウンロード" if lang == "ja" else "Download CSV"
    return (f'<a class="dl" href="{prefix}data/{name}" download>'
            f'⭳ {label}</a>')


def render_favicon() -> None:
    """シンプルなファビコン(ダーク地に3色のバー)を生成する。"""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (64, 64), "#ffffff")
    d = ImageDraw.Draw(img)
    d.rectangle([14, 12, 26, 52], fill="#0f8a5f")
    d.rectangle([32, 22, 44, 52], fill="#1f6fd0")
    d.rectangle([50, 30, 62, 52], fill="#d1453b")
    os.makedirs(SITE, exist_ok=True)
    img.save(os.path.join(SITE, "favicon.png"))


def render_seo_files() -> None:
    """sitemap.xml と robots.txt(検索エンジン向け)。"""
    pages = ["", "en/", "us.html", "en/us.html", "risk.html", "en/risk.html",
             "fedwatch.html", "en/fedwatch.html",
             "tools.html", "en/tools.html",
             "guide-start.html", "guide-oi.html", "guide-pcr.html", "guide-teguchi.html",
             "guide-sq.html",
             "guide-gex.html", "guide-cot.html", "glossary.html",
             "en/guide-participants.html", "en/guide-nikkei-options.html",
             "about.html", "privacy.html"]
    today = datetime.now(JST).strftime("%Y-%m-%d")
    urls = "\n".join(
        f"  <url><loc>{SITE_URL}{p}</loc><lastmod>{today}</lastmod></url>" for p in pages)
    sitemap = (f"<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
               f"<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n{urls}\n</urlset>\n")
    with open(os.path.join(SITE, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(sitemap)
    with open(os.path.join(SITE, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}sitemap.xml\n")


def render_static_pages() -> None:
    """運営者情報・プライバシーポリシー(ASP審査・ステマ規制対応の必須ページ)。"""
    def shell(title, body):
        og = og_meta(f"{title} | 日経225オプション データ分析")
        return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{GSV_META}
{og}
<title>{title} | 日経225オプション データ分析</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">
<style>{SUB_CSS}</style>
</head>
<body>
<header class="site-header">{site_nav("ja")}</header>
{body}
<footer>
  {footer_sitemap("ja")}
  <p>本サイトは情報提供を目的としたものであり、投資勧誘や投資助言ではありません。投資判断はご自身の責任でお願いします。</p>
</footer>
</body>
</html>
"""

    about = """
<h1>運営者情報</h1>
<h2>運営者</h2>
<p>matsutoushi(個人投資家)</p>
<h2>サイトについて</h2>
<p>日経225オプション・先物のパブリックデータ(日本取引所グループ公表)を毎営業日自動集計し、
建玉分布・Put/Callレシオ・取引参加者別建玉などを可視化しています。
以前より金融データの収集・分析を行っており、個人投資家のマーケット分析の一助となることを目的としています。</p>
<h2>お問い合わせ</h2>
<p>X(旧Twitter)のダイレクトメッセージにてご連絡ください。</p>
<h2>広告掲載について</h2>
<p>当サイトは、アフィリエイトプログラムに参加し、広告を掲載する場合があります。
広告を含むページにはその旨を表記します。</p>
"""
    privacy = """
<h1>プライバシーポリシー</h1>
<h2>個人情報の取り扱い</h2>
<p>当サイトは、閲覧にあたって個人情報の入力を求めることはありません。</p>
<h2>広告について</h2>
<p>当サイトは、第三者配信の広告サービスおよびアフィリエイトプログラム
(A8.net、アクセストレード、TGアフィリエイト等)を利用する場合があります。
広告配信事業者は、ユーザーの興味に応じた広告を表示するためにCookieを使用することがあります。</p>
<h2>アクセス解析について</h2>
<p>当サイトは、アクセス解析ツールを利用する場合があります。
これらのツールはトラフィックデータの収集のためにCookieを使用することがありますが、
個人を特定する情報は含まれません。</p>
<h2>免責事項</h2>
<p>当サイトに掲載する情報の正確性には万全を期していますが、その内容の正確性・安全性を保証するものではありません。
当サイトの利用によって生じた損害について、運営者は一切の責任を負いません。
掲載データの出典は日本取引所グループ(JPX)および日本経済新聞社の公表データです。</p>
<h2>制定日</h2>
<p>2026年7月18日</p>
"""
    with open(os.path.join(SITE, "about.html"), "w", encoding="utf-8") as f:
        f.write(shell("運営者情報", about))
    with open(os.path.join(SITE, "privacy.html"), "w", encoding="utf-8") as f:
        f.write(shell("プライバシーポリシー", privacy))
    for fname, (title, body) in pages.GUIDE_PAGES.items():
        with open(os.path.join(SITE, fname), "w", encoding="utf-8") as f:
            f.write(shell(title, body))

    def shell_en(title, body):
        og = og_meta(f"{title} | Nikkei 225 Options Data")
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{GSV_META}
{og}
<title>{title} | Nikkei 225 Options Data</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">
<style>{SUB_CSS}</style>
</head>
<body>
<header class="site-header">{site_nav("en")}</header>
{body}
<footer>
  {footer_sitemap("en")}
  <p>This site is for informational purposes only and does not constitute investment advice or solicitation. Trade at your own risk.</p>
</footer>
</body>
</html>
"""

    os.makedirs(os.path.join(SITE, "en"), exist_ok=True)
    for fname, (title, body) in pages.EN_GUIDE_PAGES.items():
        with open(os.path.join(SITE, "en", fname), "w", encoding="utf-8") as f:
            f.write(shell_en(title, body))


WARNINGS: list[str] = []


def warn(msg: str) -> None:
    print(f"WARN: {msg}")
    WARNINGS.append(msg)


def main() -> None:
    files = jpx.discover_files()
    date = files["date"]
    print(f"JPX data date: {date}")

    # JPXは公表時刻が異なる(出来高16時台 / 手口17:45頃 / 建玉20:00頃)。
    # 日付だけで判定すると、夕方にビルドした後に公表される建玉を当日中に取り込めない。
    # そこで「出来高日付|手口日付|建玉日付」の組を鍵にし、どれかが進んだら再ビルドする。
    oi_date = ""
    m = re.search(r"/(\d{8})open_interest", files["open_interest"])
    if m:
        oi_date = m.group(1)
    pv_head = None
    pv_date = ""
    try:
        pv_head = jpx.fetch_participant_volume()
        pv_date = pv_head["date"]
    except Exception as e:
        warn(f"participant volume failed: {e}")
    key = f"{date}|{pv_date}|{oi_date}"
    print(f"data key: {key} (volume|participant|open-interest)")

    last_path = os.path.join(DATA, "last_date.txt")
    last = open(last_path).read().strip() if os.path.exists(last_path) else ""
    if last == key and not os.environ.get("FORCE_BUILD"):
        print(f"NO_NEW_DATA: {key} is already processed")
        return

    os.makedirs(IMG, exist_ok=True)  # site/はgitignore対象なのでCIでは毎回作る
    pcr = jpx.fetch_put_call_volume(files["whole_day"])
    print(f"PCR: {pcr}")
    oi = jpx.fetch_open_interest(files["open_interest"])
    print(f"OI rows: {len(oi)}")

    try:
        weekly = jpx.fetch_weekly_participant_futures()
        weekly = add_combined_futures(weekly)  # 先物+mini(ラージ換算)の合計を追加
        print(f"weekly participants: {len(weekly['data'])} (date {weekly['date']})")
    except Exception as e:
        warn(f"weekly participant data failed: {e}")
        weekly = None

    # ミニオプションのPCR(ラージ換算で合算した系列を別途蓄積する)
    pcr_mini = None
    try:
        pcr_mini = jpx.fetch_mini_put_call_volume(files["whole_day"])
        if pcr_mini:
            print(f"PCR(mini): {pcr_mini}")
    except Exception as e:
        warn(f"mini PCR failed: {e}")

    hist = save_history(date, pcr, oi, weekly, pcr_mini)
    expiry = nearest_expiry(oi)
    # ミニオプション: 月限に対応する回号はラージ換算(÷10)で建玉分布に合算する。
    # 週次限月のミニは短期需給として別セクションに残すため合算しない。
    mini_df = None
    mini_merged = 0
    try:
        mini_df = jpx.fetch_mini_oi(files["open_interest"])
        print(f"mini OI rows: {len(mini_df)}")
        oi, mini_merged = merge_mini_into_oi(oi, mini_df, expiry)
        if mini_merged:
            print(f"merged mini into OI: {mini_merged:,} contracts "
                  f"({mini_merged / 10:,.0f} large-equiv)")
    except Exception as e:
        warn(f"mini OI/merge failed: {e}")
    try:
        n225_hist = jpx.fetch_n225_official()
    except Exception as e:
        warn(f"N225 official fetch failed: {e}")
        n225_hist = None
    market_ja, spot = chart_market(oi, expiry, date, "ja", n225_hist)
    market_en, _ = chart_market(oi, expiry, date, "en", n225_hist)

    # 参加者別建玉の履歴を蓄積してトレンドチャートを生成
    part_charts = {}
    try:
        ph_path = os.path.join(DATA, "participants_history.csv")
        ph_cache = pd.read_csv(ph_path, dtype={"date": str}) if os.path.exists(ph_path) else None
        ph = jpx.update_participant_history(ph_cache)
        ph.to_csv(ph_path, index=False)
        for lg in ("ja", "en"):
            part_charts[lg] = chart_participants(ph, n225_hist, lg)
    except Exception as e:
        warn(f"participant history failed: {e}")
    # テーブルの中心価格: 日経平均が取れなければ建玉加重平均の行使価格で代用
    center = spot if spot else float((oi["strike"] * oi["oi"]).sum() / max(oi["oi"].sum(), 1))
    # --- 日経VI・SQカレンダー・ミニオプション・海外投資家動向 ---
    # 冒頭サマリー用の材料。X経由の訪問者は数秒で離脱するため、
    # 最初の画面で「今日何が起きたか」を1〜2行で伝えられるようにする。
    base_extras = {"src_volume": date, "src_oi": oi_date, "spot": spot}
    try:
        if n225_hist is not None and len(n225_hist) >= 2:
            base_extras["chg"] = float(n225_hist["Close"].iloc[-1] - n225_hist["Close"].iloc[-2])
        w = wall_strikes(oi, expiry, spot)
        if w:
            base_extras["walls"] = w
        if len(hist) >= 2:
            base_extras["pcr_prev"] = float(hist["pcr"].iloc[-2])
    except Exception as e:
        warn(f"summary data failed: {e}")
    if pv_head:
        base_extras["pv"] = pv_head
    if mini_merged:
        base_extras["mini_merged"] = mini_merged
    vi_df = None
    try:
        vi_df = jpx.fetch_nikkei_vi()
        base_extras["vi_last"] = float(vi_df["Close"].iloc[-1])
        if len(vi_df) > 1:
            base_extras["vi_delta"] = float(vi_df["Close"].iloc[-1] - vi_df["Close"].iloc[-2])
        print(f"nikkei VI: {base_extras['vi_last']:.2f}")
    except Exception as e:
        warn(f"nikkei VI failed: {e}")
    try:
        base_extras["sq"] = next_sq(datetime.now(JST))
        print(f"next SQ: {base_extras['sq']['date']} ({base_extras['sq']['days']}d)")
    except Exception as e:
        warn(f"SQ calc failed: {e}")
    try:
        vol_info = latest_n225_volume(date)
        if vol_info:
            base_extras["n225_vol"] = vol_info
            print(f"N225 volume: {vol_info['value']:,.0f} "
                  f"({vol_info['date'].date()}, {vol_info['pct']}%)")
    except Exception as e:
        warn(f"N225 volume failed: {e}")
    # 清算値段のボラティリティから、ヘッジ売買が値動きに与える向きを推定する
    try:
        settle = jpx.fetch_option_settlement()
        hp = hedge_pressure(oi, settle, expiry)
        if hp:
            base_extras["hedge"] = hp
            print(f"hedge pressure: total {hp['total']/1e8:+,.0f} oku "
                  f"(expiries {hp['expiries']})")
    except Exception as e:
        warn(f"hedge pressure failed: {e}")

    # 先物の出来高・取引代金(ラージ/mini/マイクロをラージ換算で比較)
    try:
        fv = jpx.fetch_futures_volume(files["whole_day"])
        if fv:
            base_extras["fut_vol"] = fv
            print("futures: " + " / ".join(
                f"{d['product']} {d['volume']:,}枚(換算{d['large_equiv']:,.0f})" for d in fv))
    except Exception as e:
        warn(f"futures volume failed: {e}")
    flows = None
    try:
        fl_path = os.path.join(DATA, "investor_flows.csv")
        fl_cache = (pd.read_csv(fl_path, dtype={"week": str, "date": str})
                    if os.path.exists(fl_path) else None)
        if fl_cache is not None and "week" not in fl_cache.columns:
            fl_cache = None  # 旧・月次形式のキャッシュは破棄
        flows = jpx.fetch_investor_flows(fl_cache)
        flows.to_csv(fl_path, index=False)
    except Exception as e:
        warn(f"investor flows failed: {e}")

    for lang, market_chart in (("ja", market_ja), ("en", market_en)):
        extras = dict(base_extras)
        charts = {
            "oi": chart_oi_distribution(oi, expiry, spot, lang),
            "pcr": chart_pcr(hist, lang),
            "market": market_chart,
            "participants": part_charts.get(lang),
        }
        if vi_df is not None:
            charts["vi"] = chart_vi(vi_df, lang)
        if base_extras.get("hedge"):
            hc = chart_hedge(base_extras["hedge"], lang)
            if hc:
                charts["hedge"] = hc
        if mini_df is not None:
            mini_res = chart_mini_oi(mini_df, spot, lang)
            if mini_res:
                charts["mini"], extras["mini_label"] = mini_res
        if flows is not None and len(flows):
            charts["investor"] = chart_investor(flows, lang, n225_hist)
            last = flows.iloc[-1]
            lw = str(last["week"]).zfill(6)
            first_yy = str(flows.iloc[0]["week"]).zfill(6)[:2]
            net_tn = last["net_kyen"] / 1e9
            cum_tn = flows["net_kyen"].sum() / 1e9
            extras["flows_latest"] = (
                f"直近週(20{lw[:2]}年{int(lw[2:4])}月第{int(lw[4:])}週): {net_tn:+.2f}兆円 / "
                f"20{first_yy}年以降の累積: {cum_tn:+.2f}兆円"
                if lang == "ja" else
                f"Latest week (20{lw[:2]}-{lw[2:4]} W{int(lw[4:])}): {net_tn:+.2f} tn / "
                f"cumulative since 20{first_yy}: {cum_tn:+.2f} tn yen")
        tables = {
            "oi": oi_tables_html(oi, center, lang),
            "weekly": weekly_tables_html(weekly, lang) if weekly else None,
        }
        render_index(date, pcr, charts, tables, lang, extras)
    render_static_pages()
    render_seo_files()

    # 米国市場データ(取得失敗しても日本側のビルドは止めない)
    try:
        import us_data
        cot = us_data.fetch_cot()
        pcr_us = us_data.fetch_cboe_pcr()
        print(f"US data: COT {cot['date']}, CBOE {pcr_us['date']} (total {pcr_us['total']})")
        combined = pd.concat(
            [df.assign(market=k) for k, df in cot["markets"].items()], ignore_index=True)
        combined.to_csv(os.path.join(DATA, "cot_history.csv"), index=False)

        # SPX建玉の壁+GEX(失敗してもCOT/PCRセクションは出す)
        spx_res = None
        spx_share = None
        usdjpy = None
        try:
            import fred
            usdjpy = fred.fetch_series("DEXJPUS")
        except Exception as e:
            print(f"WARN: USDJPY fetch failed: {e}")
        try:
            spx_chain = us_data.fetch_spx_chain()
            try:
                spx_share = us_data.nearest_expiry_share(spx_chain)
                print(f"SPX nearest-expiry share: {spx_share['share']*100:.0f}%")
            except Exception as e:
                print(f"WARN: 0DTE share failed: {e}")
            spx_res = us_data.spx_walls_and_gex(spx_chain)
            print(f"SPX: spot {spx_res['spot']:,.0f}, GEX {spx_res['total_gex']/1e9:+,.1f}bn, "
                  f"flip {spx_res['flip']}")
            hist_path = os.path.join(DATA, "spx_gex_history.csv")
            gh = pd.read_csv(hist_path, dtype={"date": str}) if os.path.exists(hist_path) else \
                pd.DataFrame(columns=["date", "spot", "total_gex_bn", "flip"])
            gh = gh[gh["date"] != date]
            gh = pd.concat([gh, pd.DataFrame([{
                "date": date, "spot": round(spx_res["spot"], 2),
                "total_gex_bn": round(spx_res["total_gex"] / 1e9, 2),
                "flip": spx_res["flip"] or "",
            }])], ignore_index=True).sort_values("date")
            gh.to_csv(hist_path, index=False)
        except Exception as e:
            warn(f"SPX section failed: {e}")

        try:
            # 口数は設定・解約で動くので、残高を計算する前に更新しておく。
            # 失敗しても保存済みのスナップショットで計算は続けられる。
            try:
                us_data.refresh_letf_shares()
            except Exception as e:
                warn(f"LETF shares refresh failed: {e!r}")
            letf = us_data.fetch_letf_rebalance()
            print(f"LETF flow: {letf['total_bn']:+.2f}bn ({len(letf['items'])} ETFs)")
            # 推定リバランス額の日次履歴(表とCSV配布用)
            lh_path = os.path.join(DATA, "letf_history.csv")
            lh = pd.read_csv(lh_path, dtype={"date": str}) if os.path.exists(lh_path) else \
                pd.DataFrame(columns=["date", "total_bn"])
            lh = lh[lh["date"].astype(str) != date]
            lh = pd.concat([lh, pd.DataFrame([{"date": date, "total_bn": letf["total_bn"]}])],
                           ignore_index=True).sort_values("date")
            lh.to_csv(lh_path, index=False)
            letf["history"] = lh

            # 純資産の日次履歴(グラフ用)。過去分はBloombergから一度だけ入れてあり、
            # 以降は口数スナップショット×終値で算出した値を継ぎ足していく。
            letf["total_aum_bn"] = round(sum(it["aum_bn"] for it in letf["items"]), 2)
            ah_path = os.path.join(DATA, "letf_aum_history.csv")
            ah = pd.read_csv(ah_path, dtype={"date": str}) if os.path.exists(ah_path) else \
                pd.DataFrame(columns=["date", "total_aum_bn"])
            ah = ah[ah["date"].astype(str) != date]
            ah = pd.concat([ah, pd.DataFrame([{"date": date,
                                               "total_aum_bn": letf["total_aum_bn"]}])],
                           ignore_index=True).sort_values("date")
            ah.to_csv(ah_path, index=False)
            letf["aum_history"] = ah
        except Exception as e:
            warn(f"LETF flow failed: {e!r}")
            letf = None

        # COTパネルに重ねる価格。日英で使い回すのでループの外で1回だけ取得する。
        try:
            cot_prices = fetch_cot_prices()
            print(f"COT prices: {len(cot_prices)}/{len(COT_PRICE_TICKERS)} markets")
        except Exception as e:
            warn(f"COT prices failed: {e!r}")
            cot_prices = {}

        for lang in ("ja", "en"):
            spx_chart = chart_spx(spx_res, lang) if spx_res else None
            if letf is not None:
                letf["chart"] = chart_letf(letf.get("aum_history"), letf, lang)
            render_us(cot, pcr_us, lang, chart_cot(cot, lang, usdjpy, cot_prices), spx_res, spx_chart,
                      spx_share, letf)

        # 米国データ版のX投稿下書き(site/post_us.txt)
        lines = [f"【米国市場データ {int(pcr_us['date'][5:7])}/{int(pcr_us['date'][8:])}】", ""]
        if spx_res:
            gex_bn = spx_res["total_gex"] / 1e9
            mood = "ネガティブガンマ・値動き増幅域" if gex_bn < 0 else "ポジティブガンマ・値動き抑制域"
            lines.append(f"SPXガンマエクスポージャー: {gex_bn:+,.1f}bn$({mood})")
            w = spx_res["walls"]
            cw = w[w["type"] == "C"].nlargest(1, "oi").iloc[0]
            pw = w[w["type"] == "P"].nlargest(1, "oi").iloc[0]
            lines.append(f"コール最大壁 {cw['strike']:,.0f} / プット最大壁 {pw['strike']:,.0f}")
            lines.append("")
        lines.append(f"CBOE Put/Callレシオ: {pcr_us['total']:.2f}(株式 {pcr_us['equity']:.2f})")
        if "es" in cot["markets"]:
            es = cot["markets"]["es"]
            es_net = int(es["net"].iloc[-1])
            es_wow = es_net - int(es["net"].iloc[-2])
            lines.append(f"COT: ES投機筋ネット {es_net:+,}枚(前週比 {es_wow:+,})")
        with open(os.path.join(SITE, "post_us.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception as e:
        warn(f"US market section failed: {e}")

    # マクロリスクモニター(失敗しても他セクションは影響を受けない)
    try:
        import fred
        risk = fred.collect_indicators()
        counts = {}
        for it in risk["items"]:
            counts[it["signal"]] = counts.get(it["signal"], 0) + 1
        print(f"risk monitor: {len(risk['items'])} indicators, signals {counts}")
        pd.DataFrame([{k: it[k] for k in ("group", "key", "ja", "disp", "date", "signal")}
                      for it in risk["items"]]).to_csv(
            os.path.join(DATA, "risk_latest.csv"), index=False)
        src_counts = {}
        for v in fred.SOURCES.values():
            src_counts[v] = src_counts.get(v, 0) + 1
        with open(os.path.join(DATA, "fred_status.txt"), "w", encoding="utf-8") as f:
            f.write(f"sources: {src_counts}\n")
        print(f"fred sources: {src_counts}")
        for lang in ("ja", "en"):
            render_risk(risk, lang, chart_risk(risk["series"], lang),
                        chart_rates(risk["series"], lang))
    except Exception as e:
        warn(f"risk monitor failed: {e!r}")

    # FRB要人発言トラッカー
    try:
        import fed_watch
        feeds = fed_watch.fetch_feeds()
        print(f"fed watch: {sum(len(v) for v in feeds.values())} items")
        for lang in ("ja", "en"):
            render_fedwatch(feeds, lang)
    except Exception as e:
        warn(f"fed watch failed: {e!r}")

    render_favicon()

    # データ公開(CSV)とインタラクティブなデータ分析ページ
    try:
        publish_data_files()
    except Exception as e:
        warn(f"publish data files failed: {e!r}")
    try:
        import tools_page
        import us_data
        for lang in ("ja", "en"):
            tools_page.render_tools(
                SITE, lang, DATA, n225_hist, us_data.COT_MARKETS,
                CSS_MAIN, GSV_META,
                og_meta(tools_page.T[lang]["title"]),
                site_nav(lang, tools_page.T[lang]["lang"]),
                footer_sitemap(lang), PAGE[lang]["footer_disclaimer"])
        print("tools page generated")
    except Exception as e:
        warn(f"tools page failed: {e!r}")

    # 部分失敗の診断用(data/はCIがコミットするので後から確認できる)
    with open(os.path.join(DATA, "build_warnings.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(WARNINGS) if WARNINGS else "none")
    post = compose_post(date, pcr, oi, expiry, spot, base_extras.get("n225_vol"))
    print("--- post draft ---")
    print(post)
    with open(last_path, "w") as f:
        f.write(key)
    print(f"site generated: {os.path.join(SITE, 'index.html')}")


if __name__ == "__main__":
    main()
