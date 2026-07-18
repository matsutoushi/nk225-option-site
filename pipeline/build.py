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


def chart_oi_distribution(oi: pd.DataFrame, expiry: str, spot: float | None) -> str:
    df = oi[oi["expiry"] == expiry]
    strikes = sorted(df["strike"].unique())
    if spot:
        strikes = [s for s in strikes if 0.85 * spot <= s <= 1.15 * spot]
    puts = df[df["type"] == "P"].set_index("strike")["oi"].reindex(strikes).fillna(0)
    calls = df[df["type"] == "C"].set_index("strike")["oi"].reindex(strikes).fillna(0)

    fig, ax = plt.subplots(figsize=(10, 6))
    width = (strikes[1] - strikes[0]) * 0.4 if len(strikes) > 1 else 100
    ax.barh([s - width / 2 for s in strikes], -puts.values, height=width,
            color=UP, label="プット建玉")
    ax.barh([s + width / 2 for s in strikes], calls.values, height=width,
            color=DOWN, label="コール建玉")
    if spot:
        ax.axhline(spot, color=INK, linestyle="--", linewidth=1,
                   label=f"日経平均 {spot:,.0f}")
    ax.set_title(f"日経225オプション 行使価格別建玉分布(20{expiry[:2]}年{int(expiry[2:])}月限)")
    ax.set_xlabel("建玉残高(枚)  ← プット | コール →")
    ax.set_ylabel("権利行使価格")
    ax.xaxis.set_major_formatter(lambda x, _: f"{abs(x):,.0f}")
    ax.legend(loc="lower right")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    os.makedirs(IMG, exist_ok=True)
    fig.savefig(os.path.join(IMG, "oi_dist.png"), dpi=120)
    plt.close(fig)
    return "img/oi_dist.png"


def chart_pcr(hist: pd.DataFrame) -> str:
    fig, ax = plt.subplots(figsize=(10, 4))
    x = pd.to_datetime(hist["date"], format="%Y%m%d")
    ax.plot(x, hist["pcr"], marker="o", color=ACCENT, linewidth=1.5)
    ax.axhline(1.0, color=INK2, linestyle="--", linewidth=1)
    ax.set_title("日経225オプション Put/Call レシオ(出来高ベース・日次)")
    ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, "pcr.png"), dpi=120)
    plt.close(fig)
    return "img/pcr.png"


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    rsi.iloc[:period] = np.nan  # 計算初期は信頼できないので表示しない
    return rsi


def chart_market(oi: pd.DataFrame, expiry: str, data_date: str) -> tuple[str | None, float | None]:
    """ローソク足+価格帯別出来高+最大建玉ライン+MACD+RSI。

    価格データは日経公式CSV(基準日まで確定値)。出来高はYahoo(取得できた日のみ)。
    """
    try:
        hist = jpx.fetch_n225_official()
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
    near = oi[oi["expiry"] == expiry]
    ymin, ymax = l.min() * 0.995, h.max() * 1.005
    for t, color, label in (("C", DOWN, "コール最大建玉"), ("P", UP, "プット最大建玉")):
        sub = near[near["type"] == t]
        if len(sub):
            k = int(sub.loc[sub["oi"].idxmax(), "strike"])
            if ymin * 0.9 <= k <= ymax * 1.1:
                ax1.axhline(k, color=color, linestyle=":", linewidth=1.6)
                ax1.text(n - 1, k, f" {label} {k:,}", color=color, fontsize=9,
                         va="bottom", ha="right")
    ax1.set_ylim(ymin, ymax)
    ax1.set_title("日経平均(日足6ヶ月) + 価格帯別出来高 + オプション最大建玉")
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
    ax2.plot(x, signal, color=WARN, linewidth=1.2, label="シグナル")
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

    fig.savefig(os.path.join(IMG, "market.png"), dpi=120, bbox_inches="tight")
    plt.close(fig)
    return "img/market.png", spot


# ---------------------------------------------------------------------------
# テーブル生成
# ---------------------------------------------------------------------------

def _exp_label(exp: str) -> str:
    return f"{exp[:2]}年{int(exp[2:])}月"


def _change_color(v: int, maxabs: float) -> str | None:
    """増減の強弱: 増加=緑、減少=赤。大きいほど濃く、0は無色(ダーク面向けrgba)。"""
    if v == 0 or maxabs <= 0:
        return None
    strength = min(abs(v) / maxabs, 1.0)
    alpha = 0.15 + 0.5 * strength
    rgb = "12,163,12" if v > 0 else "208,59,59"
    return f"rgba({rgb}, {alpha:.2f})"


def oi_tables_html(oi: pd.DataFrame, center: float) -> str:
    """行使価格別建玉テーブル(現在値と増減を横並び)。現値±5,000円に限定。"""
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

    def render(table, is_change):
        ncols = 1 + 2 * len(expiries)
        head1 = "<tr><th rowspan='2'>行使価格</th>"
        head1 += f"<th colspan='{len(expiries)}'>Call</th><th colspan='{len(expiries)}'>Put</th></tr>"
        head2 = "<tr>" + "".join(f"<th>{_exp_label(e)}</th>" for e in expiries) * 2 + "</tr>"
        body = []
        spot_inserted = False
        for s in strikes:
            # 降順リストの中で、現値を最初に下回る行の直前に現値ラインを挿入
            if not spot_inserted and s < center:
                body.append(f"<tr class='spot'><td colspan='{ncols}'>▶ 前営業日終値 {center:,.0f}</td></tr>")
                spot_inserted = True
            tds = [f"<th>{s:,}</th>"]
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
        cap = "建玉増減(前日比: 増加=緑 / 減少=赤)" if is_change else "建玉残高(緑=各限月の最大)"
        return (f"<div class='tbl-box'><h3>{cap}</h3><div class='tbl-scroll'>"
                f"<table>{head1}{head2}{''.join(body)}</table></div></div>")

    note = (f"<p>前営業日終値を挟んで上下3,000円の範囲({lo:,.0f}〜{hi:,.0f}円)を表示。"
            f"JPXが日次公開する直近3限月分。増減は前日比。</p>")
    return f"{note}<div class='tbl-pair'>{render(cur, False)}{render(chg, True)}</div>"


def weekly_tables_html(weekly: dict) -> str:
    """参加者別建玉(週次)のテーブル。"""
    d = weekly["date"]
    date_label = f"{d[:4]}/{d[4:6]}/{d[6:]}"
    out = [f"<p>基準日: {date_label}(毎週第1営業日に更新される週次データ。"
           f"前週比は1週間でのネット建玉の増減)</p>"]
    for product in ("日経225先物", "日経225mini"):
        df = weekly["data"][weekly["data"]["product"] == product]
        if len(df) == 0:
            continue
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
  <div class='tbl-box'><h3>{product} 売超上位</h3><div class='tbl-scroll'>
    <table><tr><th>参加者</th><th>ネット建玉</th><th>前週比</th></tr>{rows(sellers)}</table>
  </div></div>
  <div class='tbl-box'><h3>{product} 買超上位</h3><div class='tbl-scroll'>
    <table><tr><th>参加者</th><th>ネット建玉</th><th>前週比</th></tr>{rows(buyers)}</table>
  </div></div>
</div>""")
    return "".join(out)


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

def render_index(date: str, pcr: dict, charts: dict, tables: dict) -> None:
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    d = f"{date[:4]}-{date[4:6]}-{date[6:]}"
    market_section = (
        f'<h2 id="market">マーケット概況</h2>\n  <img src="{charts["market"]}" '
        f'alt="日経平均ローソク足・MACD・RSI・価格帯別出来高">'
        if charts.get("market") else ""
    )
    weekly_section = (
        f'<h2 id="weekly">先物 取引参加者別建玉(週次)</h2>\n  {tables["weekly"]}'
        if tables.get("weekly") else ""
    )
    html_doc = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>日経225オプション データ分析 | 建玉分布・Put/Callレシオ 毎日更新</title>
<meta name="description" content="日経225オプションの行使価格別建玉・増減、Put/Callレシオ、先物の参加者別建玉を毎営業日自動更新。データ出典はJPX公式。">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #0d1117; --panel: #151b26; --panel2: #1a2232;
    --ink: #e8eef7; --ink2: #9aa7ba; --line: #2a3247;
    --blue: #3987e5; --red: #e66767; --aqua: #199e70;
  }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: "Noto Sans JP", "Yu Gothic", Meiryo, sans-serif; background: var(--bg);
         max-width: 1100px; margin: 0 auto; padding: 0 20px 40px; color: var(--ink); line-height: 1.7; }}
  header {{ position: sticky; top: 0; z-index: 10; background: rgba(13,17,23,0.92);
            backdrop-filter: blur(6px); padding: 14px 0 10px; border-bottom: 1px solid var(--line); }}
  h1 {{ font-size: 1.25em; margin: 0 0 2px; letter-spacing: 0.02em; }}
  h1::before {{ content: "▮"; color: var(--aqua); margin-right: 8px; }}
  h2 {{ font-size: 1.05em; margin: 40px 0 10px; padding-left: 10px;
        border-left: 3px solid var(--aqua); letter-spacing: 0.03em; }}
  h3 {{ font-size: 0.92em; color: var(--ink2); font-weight: 500; margin: 12px 0 6px; }}
  p {{ color: var(--ink2); font-size: 0.9em; }}
  .updated {{ color: var(--ink2); font-size: 0.8em; margin: 0; }}
  nav {{ margin-top: 6px; }}
  nav a {{ color: var(--ink2); text-decoration: none; font-size: 0.82em; margin-right: 6px;
           padding: 3px 10px; border: 1px solid var(--line); border-radius: 999px; display: inline-block; }}
  nav a:hover {{ color: var(--ink); border-color: var(--aqua); }}
  .kpi {{ display: flex; gap: 12px; margin: 18px 0; flex-wrap: wrap; }}
  .kpi div {{ background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
              padding: 10px 20px; flex: 1 1 140px; font-size: 0.82em; color: var(--ink2); }}
  .kpi b {{ font-size: 1.7em; color: var(--ink); font-variant-numeric: tabular-nums; display: block; margin-top: 2px; }}
  .kpi div:first-child b {{ color: var(--aqua); }}
  img {{ max-width: 100%; height: auto; border: 1px solid var(--line); border-radius: 10px; }}
  .tbl-pair {{ display: flex; gap: 16px; flex-wrap: wrap; align-items: flex-start; }}
  .tbl-box {{ flex: 1 1 420px; min-width: 320px; }}
  .tbl-scroll {{ max-height: 560px; overflow: auto; border: 1px solid var(--line); border-radius: 10px; }}
  table {{ border-collapse: collapse; font-size: 12px; white-space: nowrap; width: 100%;
           font-variant-numeric: tabular-nums; }}
  th, td {{ border: 1px solid var(--line); padding: 2px 8px; text-align: right; }}
  td {{ color: var(--ink); }}
  th {{ background: var(--panel2); color: var(--ink2); position: sticky; top: 0; font-weight: 500; }}
  tr > th:first-child {{ position: sticky; left: 0; background: var(--panel2); }}
  td.name {{ text-align: left; }}
  td.pos {{ color: #4cc38a; }}
  td.neg {{ color: #f07878; }}
  td.na {{ color: #4a5568; }}
  tr.spot td {{ background: rgba(25,158,112,0.28); color: var(--ink); text-align: center;
                font-weight: 700; border-top: 2px solid var(--aqua); border-bottom: 2px solid var(--aqua);
                letter-spacing: 0.05em; }}
  footer {{ border-top: 1px solid var(--line); margin-top: 48px; padding-top: 10px;
            font-size: 0.78em; color: var(--ink2); }}
  @media (max-width: 600px) {{
    body {{ padding: 0 10px 24px; }}
    h1 {{ font-size: 1.05em; }}
    .kpi div {{ padding: 8px 14px; }}
    .kpi b {{ font-size: 1.3em; }}
    table {{ font-size: 11px; }}
    .tbl-scroll {{ max-height: 420px; }}
    nav a {{ margin-right: 4px; font-size: 0.78em; }}
  }}
</style>
</head>
<body>
<header>
  <h1>日経225オプション データ分析</h1>
  <p class="updated">データ基準日: {d} | 最終更新: {now} JST(毎営業日 自動更新)</p>
  <nav><a href="#market">マーケット</a><a href="#oitable">建玉一覧</a><a href="#oi">建玉分布</a><a href="#weekly">参加者別建玉</a><a href="#pcr">Put/Callレシオ</a></nav>
</header>
<main>
  <div class="kpi">
    <div>Put/Call レシオ<br><b>{pcr['pcr']}</b></div>
    <div>プット出来高<br><b>{pcr['put_volume']:,}</b> 枚</div>
    <div>コール出来高<br><b>{pcr['call_volume']:,}</b> 枚</div>
  </div>

  {market_section}

  <h2 id="oitable">オプション建玉一覧(限月別)</h2>
  {tables['oi']}

  <h2 id="oi">行使価格別 建玉分布</h2>
  <p>建玉が積み上がった行使価格は、市場参加者が意識する「壁」の目安になります。</p>
  <img src="{charts['oi']}" alt="日経225オプション行使価格別建玉分布">

  {weekly_section}

  <h2 id="pcr">Put/Call レシオの推移</h2>
  <p>1.0超はプット優勢(警戒・ヘッジ需要)、1.0未満はコール優勢の目安です。</p>
  <img src="{charts['pcr']}" alt="Put/Callレシオ推移">

  <!-- 収益導線: /guide/ への内部リンクをここに設置(monetization.md参照) -->
</main>
<footer>
  <p>データ出典: 日本取引所グループ(JPX)公表データより当サイト作成。日経平均株価は日本経済新聞社の公表データ(著作権は日本経済新聞社に帰属)。</p>
  <p>本サイトは情報提供を目的としたものであり、投資勧誘や投資助言ではありません。投資判断はご自身の責任でお願いします。</p>
</footer>
</body>
</html>
"""
    os.makedirs(SITE, exist_ok=True)
    with open(os.path.join(SITE, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_doc)


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
        print(f"WARN: weekly participant data failed: {e}")
        weekly = None

    hist = save_history(date, pcr, oi, weekly)
    expiry = nearest_expiry(oi)
    market_chart, spot = chart_market(oi, expiry, date)
    # テーブルの中心価格: 日経平均が取れなければ建玉加重平均の行使価格で代用
    center = spot if spot else float((oi["strike"] * oi["oi"]).sum() / max(oi["oi"].sum(), 1))
    charts = {
        "oi": chart_oi_distribution(oi, expiry, spot),
        "pcr": chart_pcr(hist),
        "market": market_chart,
    }
    tables = {
        "oi": oi_tables_html(oi, center),
        "weekly": weekly_tables_html(weekly) if weekly else None,
    }
    render_index(date, pcr, charts, tables)
    with open(last_path, "w") as f:
        f.write(date)
    print(f"site generated: {os.path.join(SITE, 'index.html')}")


if __name__ == "__main__":
    main()
