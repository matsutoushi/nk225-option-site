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

# --- ダークテーマ配色(検証済みダークモードパレット由来) ---
PAGE_BG = "#0d1117"   # ページ背景
PANEL = "#151b26"     # カード・チャート面
INK = "#e8eef7"       # 主要テキスト
INK2 = "#9aa7ba"      # 補助テキスト
GRID = "#2a3247"      # グリッド・罫線
UP = "#e66767"        # 陽線・プット系(赤)
DOWN = "#3987e5"      # 陰線・コール系(青)
ACCENT = "#199e70"    # アクセント(アクア)
WARN = "#c98500"      # シグナル線(黄)

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

def save_history(date: str, pcr: dict, oi: pd.DataFrame, weekly: dict | None) -> pd.DataFrame:
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


def chart_oi_distribution(oi: pd.DataFrame, expiry: str, spot: float | None,
                          lang: str = "ja") -> str:
    t = L[lang]
    df = oi[oi["expiry"] == expiry]
    strikes = sorted(df["strike"].unique())
    if spot:
        strikes = [s for s in strikes if 0.85 * spot <= s <= 1.15 * spot]
    puts = df[df["type"] == "P"].set_index("strike")["oi"].reindex(strikes).fillna(0)
    calls = df[df["type"] == "C"].set_index("strike")["oi"].reindex(strikes).fillna(0)

    fig, ax = plt.subplots(figsize=(10, 6))
    width = (strikes[1] - strikes[0]) * 0.4 if len(strikes) > 1 else 100
    ax.barh([s - width / 2 for s in strikes], -puts.values, height=width,
            color=UP, label=t["put_oi"])
    ax.barh([s + width / 2 for s in strikes], calls.values, height=width,
            color=DOWN, label=t["call_oi"])
    if spot:
        ax.axhline(spot, color=INK, linestyle="--", linewidth=1,
                   label=t["spot_line"].format(spot=spot))
    ax.set_title(t["oi_title"].format(exp=_exp_label(expiry, lang)))
    ax.set_xlabel(t["oi_xlabel"])
    ax.set_ylabel(t["oi_ylabel"])
    ax.xaxis.set_major_formatter(lambda x, _: f"{abs(x):,.0f}")
    ax.legend(loc="lower right")
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
    x = pd.to_datetime(hist["date"], format="%Y%m%d")
    ax.plot(x, hist["pcr"], marker="o", color=ACCENT, linewidth=1.5)
    ax.axhline(1.0, color=INK2, linestyle="--", linewidth=1)
    ax.set_title(t["pcr_title"])
    ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    name = f"pcr{t['suffix']}.png"
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

    fig = plt.figure(figsize=(11, 9))
    gs = fig.add_gridspec(4, 1, height_ratios=[3, 1, 1, 0.001], hspace=0.08)
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax3 = fig.add_subplot(gs[2], sharex=ax1)

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
                 color=INK2, alpha=0.22, zorder=0)
        axp.set_xlim(0, prof.max() * 4)  # 左1/4だけ使う
        axp.set_ylim(ax1.get_ylim())
        axp.axis("off")

    # --- オプション最大建玉ライン ---
    tx = L[lang]
    near = oi[oi["expiry"] == expiry]
    ymin, ymax = l.min() * 0.995, h.max() * 1.005
    for t, color, label in (("C", DOWN, tx["max_call"]), ("P", UP, tx["max_put"])):
        sub = near[near["type"] == t]
        if len(sub):
            k = int(sub.loc[sub["oi"].idxmax(), "strike"])
            if ymin * 0.9 <= k <= ymax * 1.1:
                ax1.axhline(k, color=color, linestyle=":", linewidth=1.6)
                ax1.text(n - 1, k, f" {label} {k:,}", color=color, fontsize=9,
                         va="bottom", ha="right")
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
    ax2.bar(x, histo, width=0.65, color=np.where(histo >= 0, UP, DOWN), alpha=0.5)
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

    # 月初の位置に日付ラベル
    dates = hist.index
    ticks = [i for i in range(n) if i == 0 or dates[i].month != dates[i - 1].month]
    ax3.set_xticks(ticks)
    ax3.set_xticklabels([dates[i].strftime("%y/%m") for i in ticks])

    name = f"market{tx['suffix']}.png"
    fig.savefig(os.path.join(IMG, name), dpi=120, bbox_inches="tight")
    plt.close(fig)
    return f"img/{name}", spot


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
        "mkt_title": "日経平均(日足6ヶ月) + 価格帯別出来高 + オプション最大建玉",
        "max_call": "コール最大建玉", "max_put": "プット最大建玉",
        "signal": "シグナル",
        "strike": "行使価格",
        "tbl_note": "前営業日終値を挟んで上下3,000円の範囲({lo:,.0f}〜{hi:,.0f}円)を表示。JPXが日次公開する直近3限月分。増減は前日比。",
        "tbl_caption": "左: 建玉残高(緑=各限月の最大) / 右: 建玉増減(前日比: 増加=緑・減少=赤)",
        "spot_marker": "▶ 前営業日終値 {spot:,.0f}",
        "wk_note": "基準日: {date}(毎週第1営業日に更新される週次データ。前週比は1週間でのネット建玉の増減)",
        "wk_sellers": "{product} 売超上位", "wk_buyers": "{product} 買超上位",
        "wk_cols": ["参加者", "ネット建玉", "前週比"],
        "products": {"日経225先物": "日経225先物", "日経225mini": "日経225mini"},
    },
    "en": {
        "suffix": "_en",
        "oi_title": "Nikkei 225 Options — Open Interest by Strike ({exp})",
        "oi_xlabel": "Open Interest (contracts)  ← Put | Call →",
        "oi_ylabel": "Strike Price",
        "put_oi": "Put OI", "call_oi": "Call OI",
        "spot_line": "Nikkei 225: {spot:,.0f}",
        "pcr_title": "Nikkei 225 Options Put/Call Ratio (volume-based, daily)",
        "mkt_title": "Nikkei 225 (daily, 6 months) + Volume Profile + Max Option OI",
        "max_call": "Max Call OI", "max_put": "Max Put OI",
        "signal": "Signal",
        "strike": "Strike",
        "tbl_note": "Strikes within ±3,000 yen of the previous close ({lo:,.0f}–{hi:,.0f}). Nearest 3 expiries published daily by JPX. Change is day-over-day.",
        "tbl_caption": "Left: Open Interest (green = largest per expiry) / Right: DoD Change (increase = green, decrease = red)",
        "spot_marker": "▶ Prev. close {spot:,.0f}",
        "wk_note": "As of {date} (weekly data published on the first business day of each week; WoW = one-week change in net open interest)",
        "wk_sellers": "{product} — Top Net Sellers", "wk_buyers": "{product} — Top Net Buyers",
        "wk_cols": ["Participant", "Net OI", "WoW"],
        "products": {"日経225先物": "Nikkei 225 Futures", "日経225mini": "Nikkei 225 mini Futures"},
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
        return f"<table>{head1}{head2}{''.join(body)}</table>"

    note = f"<p>{tx['tbl_note'].format(lo=lo, hi=hi)}</p>"
    caption = f"<h3>{tx['tbl_caption']}</h3>"
    return (f"{note}{caption}<div class='tbl-duo'>"
            f"{render(cur, False, True)}{render(chg, True, False)}</div>")


def weekly_tables_html(weekly: dict, lang: str = "ja") -> str:
    """参加者別建玉(週次)のテーブル。"""
    tx = L[lang]
    d = weekly["date"]
    date_label = f"{d[:4]}/{d[4:6]}/{d[6:]}"
    out = [f"<p>{tx['wk_note'].format(date=date_label)}</p>"]
    head = "".join(f"<th>{c}</th>" for c in tx["wk_cols"])
    for product in ("日経225先物", "日経225mini"):
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
    --bg: #0d1117; --panel: #151b26; --panel2: #1a2232;
    --ink: #e8eef7; --ink2: #9aa7ba; --line: #2a3247;
    --blue: #3987e5; --red: #e66767; --aqua: #199e70;
  }
  * { box-sizing: border-box; }
  body { font-family: "Noto Sans JP", "Yu Gothic", Meiryo, sans-serif; background: var(--bg);
         max-width: 1100px; margin: 0 auto; padding: 0 20px 40px; color: var(--ink); line-height: 1.7; }
  header { position: sticky; top: 0; z-index: 10; background: rgba(13,17,23,0.92);
            backdrop-filter: blur(6px); padding: 14px 0 10px; border-bottom: 1px solid var(--line); }
  h1 { font-size: 1.25em; margin: 0 0 2px; letter-spacing: 0.02em; }
  h1::before { content: "▮"; color: var(--aqua); margin-right: 8px; }
  h2 { font-size: 1.05em; margin: 40px 0 10px; padding-left: 10px;
        border-left: 3px solid var(--aqua); letter-spacing: 0.03em; }
  h3 { font-size: 0.92em; color: var(--ink2); font-weight: 500; margin: 12px 0 6px; }
  p { color: var(--ink2); font-size: 0.9em; }
  .updated { color: var(--ink2); font-size: 0.8em; margin: 0; }
  nav { margin-top: 6px; }
  nav a { color: var(--ink2); text-decoration: none; font-size: 0.82em; margin-right: 6px;
           padding: 3px 10px; border: 1px solid var(--line); border-radius: 999px; display: inline-block; }
  nav a:hover { color: var(--ink); border-color: var(--aqua); }
  .kpi { display: flex; gap: 12px; margin: 18px 0; flex-wrap: wrap; }
  .kpi div { background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
              padding: 10px 20px; flex: 1 1 140px; font-size: 0.82em; color: var(--ink2); }
  .kpi b { font-size: 1.7em; color: var(--ink); font-variant-numeric: tabular-nums; display: block; margin-top: 2px; }
  .kpi div:first-child b { color: var(--aqua); }
  img { max-width: 100%; height: auto; border: 1px solid var(--line); border-radius: 10px; }
  .tbl-pair { display: flex; gap: 16px; flex-wrap: wrap; align-items: flex-start; }
  .tbl-box { flex: 1 1 420px; min-width: 320px; }
  .tbl-scroll { max-height: 560px; overflow: auto; border: 1px solid var(--line); border-radius: 10px; }
  .tbl-duo { display: flex; gap: 20px; max-height: 560px; overflow: auto;
              border: 1px solid var(--line); border-radius: 10px; align-items: flex-start; }
  .tbl-duo table { width: auto; }
  table { border-collapse: collapse; font-size: 12px; white-space: nowrap; width: 100%;
           font-variant-numeric: tabular-nums; }
  th, td { border: 1px solid var(--line); padding: 2px 8px; text-align: right; }
  td { color: var(--ink); }
  th { background: var(--panel2); color: var(--ink2); position: sticky; top: 0; font-weight: 500; }
  tr > th:first-child { position: sticky; left: 0; background: var(--panel2); }
  td.name { text-align: left; }
  td.pos { color: #4cc38a; }
  td.neg { color: #f07878; }
  td.na { color: #4a5568; }
  tr.spot td { background: rgba(25,158,112,0.28); color: var(--ink); text-align: center;
                font-weight: 700; border-top: 2px solid var(--aqua); border-bottom: 2px solid var(--aqua);
                letter-spacing: 0.05em; }
  .sig { font-size: 1.1em; }
  .sig-green { color: #2ecc71; }
  .sig-yellow { color: #f1c40f; }
  .sig-red { color: #e74c3c; }
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
        "kpi_vi": "日経VI(前日差)",
        "kpi_sq": "次回SQ",
        "sec_mini": "ミニオプション建玉分布(ウィークリー: {exp}限)",
        "mini_lead": "日経225ミニオプション(週次限月)の行使価格別建玉。短期の攻防ラインの目安になります。",
        "sec_flows": "海外投資家の売買動向(週次)",
        "flows_lead": "JPX投資部門別売買状況(東証プライム・現物金額)より、海外投資家の週次ネット売買。{latest}",
        "sec_oitable": "オプション建玉一覧(限月別)",
        "sec_oi": "行使価格別 建玉分布",
        "oi_lead": '建玉が積み上がった行使価格は、市場参加者が意識する「壁」の目安になります。(<a href="guide-oi.html" style="color:#3987e5">→ 建玉分布の見方</a>)',
        "sec_weekly": "先物 取引参加者別建玉(週次)",
        "wk_chart_lead": "棒グラフ: 各社の週次ネット建玉(緑=買い越し / 赤=売り越し)。灰色の線は日経平均の推移(形状比較用・目盛りなし)。最新週の建玉規模上位12社を表示。",
        "sec_pcr": "Put/Call レシオの推移",
        "pcr_lead": '1.0超はプット優勢(警戒・ヘッジ需要)、1.0未満はコール優勢の目安です。(<a href="guide-pcr.html" style="color:#3987e5">→ Put/Callレシオの見方</a>)',
        "footer_links": '<a href="about.html" style="color:#3987e5">運営者情報</a> ｜ <a href="privacy.html" style="color:#3987e5">プライバシーポリシー</a> ｜ <a href="glossary.html" style="color:#3987e5">用語集</a>',
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
        "kpi_vi": "Nikkei VI (DoD)",
        "kpi_sq": "Next SQ",
        "sec_mini": "Mini Options OI (Weekly: {exp} expiry)",
        "mini_lead": "Open interest by strike for Nikkei 225 mini options (weekly expiries) — a gauge of short-term battle lines.",
        "sec_flows": "Foreign Investor Flows (Weekly)",
        "flows_lead": "Weekly net buying by foreign investors in TSE Prime cash equities, from JPX trading-by-investor-type data. {latest}",
        "sec_oitable": "Options Open Interest by Expiry",
        "sec_oi": "Open Interest Distribution by Strike",
        "oi_lead": "Strikes with heavy open interest often act as reference levels (\"walls\") watched by market participants.",
        "sec_weekly": "Futures Open Interest by Trading Participant (Weekly)",
        "wk_chart_lead": "Bars: weekly net open interest per participant (green = net long, red = net short). Gray line: Nikkei 225 (shape only, no scale). Top 12 participants by latest position size.",
        "sec_pcr": "Put/Call Ratio Trend",
        "pcr_lead": "Above 1.0 = puts dominant (hedging demand); below 1.0 = calls dominant. Participant names in the tables are Japanese trading-participant names as published by JPX.",
        "footer_links": '<a href="../about.html" style="color:#3987e5">About</a> | <a href="../privacy.html" style="color:#3987e5">Privacy Policy</a> | <a href="guide-participants.html" style="color:#3987e5">Guide: Participant Positioning</a> | <a href="guide-nikkei-options.html" style="color:#3987e5">Guide: Nikkei Options</a>',
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
    nav_ids = ["#market", "#oitable", "#oi", "#weekly", "#pcr"]
    nav = "".join(f'<a href="{i}">{label}</a>' for i, label in zip(nav_ids, P["nav"]))
    nav += P["guide_link"] + P["lang_switch"]
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
  <nav>{nav}</nav>
</header>
<main>
  <div class="kpi">
    <div>{P['kpi'][0]}<br><b>{pcr['pcr']}</b></div>
    <div>{P['kpi'][1]}<br><b>{pcr['put_volume']:,}</b>{P['unit']}</div>
    <div>{P['kpi'][2]}<br><b>{pcr['call_volume']:,}</b>{P['unit']}</div>
    {extra_kpi}
  </div>

  {market_section}

  <h2 id="oitable">{P['sec_oitable']}</h2>
  {tables['oi']}

  <h2 id="oi">{P['sec_oi']}</h2>
  <p>{P['oi_lead']}</p>
  <img src="{charts['oi']}" alt="Open interest by strike">

  {mini_section}

  {weekly_section}

  {flows_section}

  <h2 id="pcr">{P['sec_pcr']}</h2>
  <p>{P['pcr_lead']}</p>
  <img src="{charts['pcr']}" alt="Put/Call ratio trend">

  <!-- 収益導線: /guide/ への内部リンクをここに設置(monetization.md参照) -->
</main>
<footer>
  <p>{P['footer_links']}</p>
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
                 spot: float | None) -> str:
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
  <nav>{P['back']}{P['lang_switch']}</nav>
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
  <nav>{P['back']}{P['lang_switch']}</nav>
</header>
<main>
  <p>{P['lead']}</p>
  {''.join(sections)}
</main>
<footer>
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
        "cot_lead": "CFTC建玉明細報告より。株価指数・通貨はレバレッジファンド、金・原油はマネージドマネーのネットポジション(買い−売り)。毎週火曜時点のデータが金曜に公表されます。",
        "cot_cols": ["市場", "ネットポジション", "前週比"],
        "sec_pcr": "CBOE Put/Callレシオ(日次)",
        "pcr_lead": "米国オプション市場全体の弱気/強気の偏り。1.0超はプット優勢です。",
        "pcr_rows": {"total": "全体(Total)", "index": "指数(Index)", "equity": "株式(Equity)",
                     "spx": "SPX+SPXW", "vix": "VIX"},
        "pcr_cols": ["区分", "Put/Callレシオ"],
        "sec_etf": "SPY・QQQ 建玉の壁",
        "etf_lead": "米国の代表的ETFオプションの行使価格別建玉(45日以内の限月・現値±10%)。SPXと同様、建玉の集中する水準は意識されやすい価格帯の目安です。",
        "kpi_0dte": "SPX最短限月の出来高シェア",
        "sec_spx": "SPXオプション: 建玉の壁とガンマエクスポージャー(推定)",
        "spx_lead": "CBOE遅延データ(前営業日終値時点)より、45日以内の限月・現値±10%を集計。ガンマエクスポージャーは「ディーラーはコール買い・プット売り」という一般的な仮定に基づく推定値で、実際のディーラーポジションを示すものではありません。プラス圏=相場の変動を抑える力、マイナス圏=変動を増幅する力が働きやすいと解釈されます。",
        "spx_kpi": ["SPX終値", "合計ガンマエクスポージャー($bn/1%)", "ガンマフリップ"],
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
        "cot_lead": "From the CFTC Commitments of Traders report. Leveraged funds for index/FX futures, managed money for gold/crude. Tuesday data, released Friday.",
        "cot_cols": ["Market", "Net Position", "WoW"],
        "sec_pcr": "CBOE Put/Call Ratios (Daily)",
        "pcr_lead": "Bearish/bullish skew of the US options market. Above 1.0 = puts dominant.",
        "pcr_rows": {"total": "Total", "index": "Index", "equity": "Equity",
                     "spx": "SPX+SPXW", "vix": "VIX"},
        "pcr_cols": ["Category", "Put/Call Ratio"],
        "sec_etf": "SPY & QQQ OI Walls",
        "etf_lead": "Open interest by strike for the major US ETF options (expiries within 45 days, strikes within ±10% of spot).",
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


def chart_cot(cot: dict, lang: str, usdjpy: pd.Series | None = None) -> str:
    """全市場のネットポジション推移(スモールマルチプル)。円パネルにはドル円を重ねる。"""
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
        if m["key"] == "jpy" and usdjpy is not None and len(usdjpy):
            u = usdjpy[(usdjpy.index >= x.min()) & (usdjpy.index <= x.max())]
            if len(u):
                axp = ax.twinx()
                axp.plot(u.index, u.values, color="#8a97ad", alpha=0.55, linewidth=1)
                axp.axis("off")
        title = m[lang] + (" (灰線: ドル円)" if m["key"] == "jpy" and lang == "ja"
                           and usdjpy is not None else
                           (" (gray: USD/JPY)" if m["key"] == "jpy" and lang == "en"
                            and usdjpy is not None else ""))
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
    fig, ax = plt.subplots(figsize=(10, 5))
    width = (strikes[1] - strikes[0]) * 0.4 if len(strikes) > 1 else 50
    ax.barh([s - width / 2 for s in strikes], -puts.values, height=width, color=UP,
            label=L[lang]["put_oi"])
    ax.barh([s + width / 2 for s in strikes], calls.values, height=width, color=DOWN,
            label=L[lang]["call_oi"])
    if spot:
        ax.axhline(spot, color=INK, linestyle="--", linewidth=1,
                   label=L[lang]["spot_line"].format(spot=spot))
    exp_label = f"{exp.month}/{exp.day}"
    ax.set_title((f"日経225ミニオプション 建玉分布({exp_label}限)" if lang == "ja"
                  else f"Nikkei 225 mini Options OI ({exp_label} expiry)"), fontsize=10)
    ax.xaxis.set_major_formatter(lambda x, _: f"{abs(x):,.0f}")
    ax.legend(loc="lower right")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    name = f"mini_oi{suffix}.png"
    fig.savefig(os.path.join(IMG, name), dpi=120)
    plt.close(fig)
    return f"img/{name}", exp_label


def chart_investor(flows: pd.DataFrame, lang: str) -> str:
    """海外投資家の週次ネット売買(東証プライム・金額)。"""
    suffix = L[lang]["suffix"]
    x = pd.to_datetime(flows["week"], format="%y%m%d")
    vals = flows["net"] / 1e12  # 兆円
    fig, ax = plt.subplots(figsize=(10, 3.6))
    colors = [ACCENT if v >= 0 else UP for v in vals]
    ax.bar(x, vals, width=4.5, color=colors)
    ax.axhline(0, color=INK2, linewidth=0.8)
    ax.set_title("海外投資家の週次ネット売買(東証プライム・現物、兆円)" if lang == "ja"
                 else "Foreign Investors Weekly Net Buying (TSE Prime cash equities, tn yen)",
                 fontsize=10)
    ax.grid(alpha=0.25)
    fig.autofmt_xdate()
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
                axp.plot(n.index, n["Close"], color="#8a97ad", alpha=0.55, linewidth=1)
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


def chart_etf_walls(chains: dict, lang: str) -> str | None:
    """SPY・QQQの建玉の壁(2パネル)。chains: {"SPY": chain_dict, "QQQ": chain_dict}"""
    suffix = L[lang]["suffix"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 6))
    drawn = 0
    for ax, sym in zip(axes, ("SPY", "QQQ")):
        c = chains.get(sym)
        if not c:
            ax.axis("off")
            continue
        spot = c["spot"]
        df = c["chain"]
        cutoff = datetime.now(timezone.utc).date() + timedelta(days=45)
        df = df[(df["expiry"] <= cutoff) & (df["oi"] > 0)
                & (df["strike"] >= spot * 0.9) & (df["strike"] <= spot * 1.1)].copy()
        df["bin"] = (df["strike"] // 5) * 5
        puts = df[df["type"] == "P"].groupby("bin")["oi"].sum()
        calls = df[df["type"] == "C"].groupby("bin")["oi"].sum()
        bins = sorted(set(puts.index) | set(calls.index))
        ax.barh(bins, -puts.reindex(bins).fillna(0), height=4,
                color=UP, label="Put OI" if lang == "en" else "プット建玉")
        ax.barh(bins, calls.reindex(bins).fillna(0), height=4,
                color=DOWN, label="Call OI" if lang == "en" else "コール建玉")
        ax.axhline(spot, color=INK, linestyle="--", linewidth=1)
        ax.set_title(f"{sym}  (spot {spot:,.0f})", fontsize=10)
        ax.xaxis.set_major_formatter(lambda x, _: f"{abs(x)/1000:,.0f}k")
        ax.legend(loc="lower left", fontsize=8)
        ax.grid(alpha=0.25)
        drawn += 1
    if drawn == 0:
        plt.close(fig)
        return None
    sup = ("SPY・QQQ 行使価格別建玉(45日以内・±10%)" if lang == "ja"
           else "SPY & QQQ Open Interest by Strike (45d expiries, ±10%)")
    fig.suptitle(sup, fontsize=11)
    fig.tight_layout()
    name = f"etf_walls{suffix}.png"
    fig.savefig(os.path.join(IMG, name), dpi=120)
    plt.close(fig)
    return f"img/{name}"


def chart_spx(res: dict, lang: str) -> str:
    """SPXの建玉の壁とネットGEXを25pt刻みで並べた2パネル図。"""
    suffix = L[lang]["suffix"]
    spot = res["spot"]
    walls = res["walls"].copy()
    walls["bin"] = (walls["strike"] // 25) * 25
    gex = res["gex"].copy()
    gex["bin"] = (gex["strike"] // 25) * 25
    gex_b = gex.groupby("bin")["gex"].sum() / 1e9

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 6.5), sharey=True)

    puts = walls[walls["type"] == "P"].groupby("bin")["oi"].sum()
    calls = walls[walls["type"] == "C"].groupby("bin")["oi"].sum()
    bins = sorted(set(puts.index) | set(calls.index))
    ax1.barh(bins, -puts.reindex(bins).fillna(0), height=20, color=UP,
             label="Put OI" if lang == "en" else "プット建玉")
    ax1.barh(bins, calls.reindex(bins).fillna(0), height=20, color=DOWN,
             label="Call OI" if lang == "en" else "コール建玉")
    ax1.axhline(spot, color=INK, linestyle="--", linewidth=1)
    ax1.set_title("SPX Open Interest by Strike" if lang == "en"
                  else "SPX 行使価格別建玉(壁)", fontsize=10)
    ax1.xaxis.set_major_formatter(lambda x, _: f"{abs(x)/1000:,.0f}k")
    ax1.legend(loc="lower left", fontsize=8)
    ax1.grid(alpha=0.25)

    colors = [ACCENT if v >= 0 else UP for v in gex_b.values]
    ax2.barh(gex_b.index, gex_b.values, height=20, color=colors)
    ax2.axhline(spot, color=INK, linestyle="--", linewidth=1,
                label=f"SPX {spot:,.0f}")
    if res["flip"]:
        ax2.axhline(res["flip"], color=WARN, linestyle=":", linewidth=1.6,
                    label=("Gamma flip" if lang == "en" else "ガンマフリップ")
                    + f" {res['flip']:,.0f}")
    ax2.axvline(0, color=INK2, linewidth=0.7)
    total = res["total_gex"] / 1e9
    ax2.set_title((f"Net GEX by Strike (Total {total:+,.1f} $bn/1%)" if lang == "en"
                   else f"ネット・ガンマエクスポージャー(合計 {total:+,.1f} $bn/1%)"), fontsize=10)
    ax2.legend(loc="lower right", fontsize=8)
    ax2.grid(alpha=0.25)

    sup = ("SPX Options: OI Walls & Naive Gamma Exposure (45d expiries, ±10%)"
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
              etf_chart: str | None = None, share: dict | None = None) -> None:
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
  <h2>{P['sec_spx']}</h2>
  <div class="kpi">
    <div>{P['spx_kpi'][0]}<br><b>{spx_res['spot']:,.0f}</b></div>
    <div>{P['spx_kpi'][1]}<br><b>{gex_bn:+,.1f}</b></div>
    <div>{P['spx_kpi'][2]}<br><b>{flip_txt}</b></div>
    {share_kpi}
  </div>
  <p>{P['spx_lead']}</p>
  <img src="{spx_src}" alt="SPX OI walls and gamma exposure">"""

    etf_section = ""
    if etf_chart:
        etf_section = (f"\n  <h2>{P['sec_etf']}</h2>\n  <p>{P['etf_lead']}</p>\n"
                       f'  <img src="{P["prefix"]}{etf_chart}?v={ver}" alt="SPY QQQ OI walls">')

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
  <nav>{P['back']}{P['lang_switch']}</nav>
</header>
<main>
  <div class="kpi">
    <div>{P['kpi'][0]}<br><b>{pcr_us['total']:.2f}</b></div>
    <div>{P['kpi'][1]}<br><b>{pcr_us['equity']:.2f}</b></div>
    <div>{P['kpi'][2]}<br><b>{pcr_us['spx']:.2f}</b></div>
  </div>

  <h2>{P['sec_cot']}</h2>
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

  {etf_section}
</main>
<footer>
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
  :root { --bg: #0d1117; --panel: #151b26; --ink: #e8eef7; --ink2: #9aa7ba;
          --line: #2a3247; --aqua: #199e70; }
  * { box-sizing: border-box; }
  body { font-family: "Noto Sans JP", "Yu Gothic", Meiryo, sans-serif; background: var(--bg);
         max-width: 820px; margin: 0 auto; padding: 0 20px 40px; color: var(--ink); line-height: 1.9; }
  h1 { font-size: 1.25em; margin: 24px 0 8px; }
  h1::before { content: "▮"; color: var(--aqua); margin-right: 8px; }
  h2 { font-size: 1.0em; margin: 28px 0 8px; padding-left: 10px; border-left: 3px solid var(--aqua); }
  p, li { color: var(--ink2); font-size: 0.92em; }
  a { color: #3987e5; }
  img { max-width: 100%; height: auto; }
  footer { border-top: 1px solid var(--line); margin-top: 48px; padding-top: 10px;
           font-size: 0.78em; color: var(--ink2); }
"""


SITE_URL = "https://matsutoushi.github.io/nk225-option-site/"
GSV_META = '<meta name="google-site-verification" content="2JN1JwTzW_V10lr6LymCE5AgMGsKG0uu4BI5QdwWz24">'


def og_meta(title: str, desc: str = "") -> str:
    """OGP/Twitterカード用メタタグ(X告知でリンクカードを出すため)。"""
    img = SITE_URL + "img/market.png"
    return (f'<meta property="og:title" content="{title}">\n'
            f'<meta property="og:description" content="{desc}">\n'
            f'<meta property="og:image" content="{img}">\n'
            f'<meta property="og:type" content="website">\n'
            f'<meta name="twitter:card" content="summary_large_image">\n'
            f'<link rel="icon" type="image/png" href="{SITE_URL}favicon.png">')


def render_favicon() -> None:
    """シンプルなファビコン(ダーク地に3色のバー)を生成する。"""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (64, 64), "#0d1117")
    d = ImageDraw.Draw(img)
    d.rectangle([14, 12, 26, 52], fill="#199e70")
    d.rectangle([32, 22, 44, 52], fill="#3987e5")
    d.rectangle([50, 30, 62, 52], fill="#e66767")
    os.makedirs(SITE, exist_ok=True)
    img.save(os.path.join(SITE, "favicon.png"))


def render_seo_files() -> None:
    """sitemap.xml と robots.txt(検索エンジン向け)。"""
    pages = ["", "en/", "us.html", "en/us.html", "risk.html", "en/risk.html",
             "fedwatch.html", "en/fedwatch.html",
             "guide-start.html", "guide-oi.html", "guide-pcr.html",
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
{body}
<footer>
  <p><a href="./">トップページへ戻る</a></p>
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
{body}
<footer>
  <p><a href="./">← Back to the dashboard</a></p>
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

    # 既に処理済みの日付ならビルドせず終了(1日複数回のcronで新データの回だけ動かす)
    # workflow_dispatch / push では FORCE_BUILD=1 が入り常にビルドする
    last_path = os.path.join(DATA, "last_date.txt")
    last = open(last_path).read().strip() if os.path.exists(last_path) else ""
    if last == date and not os.environ.get("FORCE_BUILD"):
        print(f"NO_NEW_DATA: {date} is already processed")
        return

    os.makedirs(IMG, exist_ok=True)  # site/はgitignore対象なのでCIでは毎回作る
    pcr = jpx.fetch_put_call_volume(files["whole_day"])
    print(f"PCR: {pcr}")
    oi = jpx.fetch_open_interest(files["open_interest"])
    print(f"OI rows: {len(oi)}")

    try:
        weekly = jpx.fetch_weekly_participant_futures()
        print(f"weekly participants: {len(weekly['data'])} (date {weekly['date']})")
    except Exception as e:
        warn(f"weekly participant data failed: {e}")
        weekly = None

    hist = save_history(date, pcr, oi, weekly)
    expiry = nearest_expiry(oi)
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
    base_extras = {}
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
    mini_df = None
    try:
        mini_df = jpx.fetch_mini_oi(files["open_interest"])
        print(f"mini OI rows: {len(mini_df)}")
    except Exception as e:
        warn(f"mini OI failed: {e}")
    flows = None
    try:
        fl_path = os.path.join(DATA, "investor_flows.csv")
        fl_cache = pd.read_csv(fl_path, dtype={"week": str}) if os.path.exists(fl_path) else None
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
        if mini_df is not None:
            mini_res = chart_mini_oi(mini_df, spot, lang)
            if mini_res:
                charts["mini"], extras["mini_label"] = mini_res
        if flows is not None and len(flows):
            charts["investor"] = chart_investor(flows, lang)
            last = flows.iloc[-1]
            net_tn = last["net"] / 1e12
            extras["flows_latest"] = (
                f"直近({last['label']}): {net_tn:+.2f}兆円" if lang == "ja"
                else f"Latest ({last['label']}): {net_tn:+.2f} tn yen")
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
        etf_chains = {}
        usdjpy = None
        try:
            import fred
            usdjpy = fred.fetch_series("DEXJPUS")
        except Exception as e:
            print(f"WARN: USDJPY fetch failed: {e}")
        for sym in ("SPY", "QQQ"):
            try:
                etf_chains[sym] = us_data.fetch_chain(sym)
                print(f"{sym}: spot {etf_chains[sym]['spot']:,.0f}, "
                      f"rows {len(etf_chains[sym]['chain'])}")
            except Exception as e:
                warn(f"{sym} chain failed: {e}")
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

        for lang in ("ja", "en"):
            spx_chart = chart_spx(spx_res, lang) if spx_res else None
            etf_chart = chart_etf_walls(etf_chains, lang) if etf_chains else None
            render_us(cot, pcr_us, lang, chart_cot(cot, lang, usdjpy), spx_res, spx_chart,
                      etf_chart, spx_share)

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

    # 部分失敗の診断用(data/はCIがコミットするので後から確認できる)
    with open(os.path.join(DATA, "build_warnings.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(WARNINGS) if WARNINGS else "none")
    post = compose_post(date, pcr, oi, expiry, spot)
    print("--- post draft ---")
    print(post)
    with open(last_path, "w") as f:
        f.write(date)
    print(f"site generated: {os.path.join(SITE, 'index.html')}")


if __name__ == "__main__":
    main()
