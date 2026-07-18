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
                 lang: str = "ja") -> tuple[str | None, float | None]:
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

# ページ本文の文言(日英)
PAGE = {
    "ja": {
        "title": "日経225オプション データ分析 | 建玉分布・Put/Callレシオ 毎日更新",
        "desc": "日経225オプションの行使価格別建玉・増減、Put/Callレシオ、先物の参加者別建玉を毎営業日自動更新。データ出典はJPX公式。",
        "h1": "日経225オプション データ分析",
        "updated": "データ基準日: {d} | 最終更新: {now} JST(毎営業日 自動更新)",
        "nav": ["マーケット", "建玉一覧", "建玉分布", "参加者別建玉", "Put/Callレシオ"],
        "guide_link": '<a href="guide-start.html">始め方ガイド</a>',
        "lang_switch": '<a href="en/" lang="en">English</a>',
        "kpi": ["Put/Call レシオ", "プット出来高", "コール出来高"], "unit": " 枚",
        "sec_market": "マーケット概況",
        "sec_oitable": "オプション建玉一覧(限月別)",
        "sec_oi": "行使価格別 建玉分布",
        "oi_lead": '建玉が積み上がった行使価格は、市場参加者が意識する「壁」の目安になります。(<a href="guide-oi.html" style="color:#3987e5">→ 建玉分布の見方</a>)',
        "sec_weekly": "先物 取引参加者別建玉(週次)",
        "sec_pcr": "Put/Call レシオの推移",
        "pcr_lead": '1.0超はプット優勢(警戒・ヘッジ需要)、1.0未満はコール優勢の目安です。(<a href="guide-pcr.html" style="color:#3987e5">→ Put/Callレシオの見方</a>)',
        "footer_links": '<a href="about.html" style="color:#3987e5">運営者情報</a> ｜ <a href="privacy.html" style="color:#3987e5">プライバシーポリシー</a>',
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
        "guide_link": "",
        "lang_switch": '<a href="../" lang="ja">日本語</a>',
        "kpi": ["Put/Call Ratio", "Put Volume", "Call Volume"], "unit": "",
        "sec_market": "Market Overview",
        "sec_oitable": "Options Open Interest by Expiry",
        "sec_oi": "Open Interest Distribution by Strike",
        "oi_lead": "Strikes with heavy open interest often act as reference levels (\"walls\") watched by market participants.",
        "sec_weekly": "Futures Open Interest by Trading Participant (Weekly)",
        "sec_pcr": "Put/Call Ratio Trend",
        "pcr_lead": "Above 1.0 = puts dominant (hedging demand); below 1.0 = calls dominant. Participant names in the tables are Japanese trading-participant names as published by JPX.",
        "footer_links": '<a href="../about.html" style="color:#3987e5">About</a> | <a href="../privacy.html" style="color:#3987e5">Privacy Policy</a>',
        "footer_src": "Data source: compiled from official Japan Exchange Group (JPX) publications. Nikkei 225 price data by Nikkei Inc. (copyright belongs to Nikkei Inc.).",
        "footer_disclaimer": "This site is for informational purposes only and does not constitute investment advice or solicitation. Trade at your own risk.",
        "out": os.path.join("en", "index.html"), "prefix": "../", "html_lang": "en",
    },
}


def render_index(date: str, pcr: dict, charts: dict, tables: dict, lang: str = "ja") -> None:
    P = PAGE[lang]
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
    weekly_section = (
        f'<h2 id="weekly">{P["sec_weekly"]}</h2>\n  {tables["weekly"]}'
        if tables.get("weekly") else ""
    )
    nav_ids = ["#market", "#oitable", "#oi", "#weekly", "#pcr"]
    nav = "".join(f'<a href="{i}">{label}</a>' for i, label in zip(nav_ids, P["nav"]))
    nav += P["guide_link"] + P["lang_switch"]
    html_doc = f"""<!DOCTYPE html>
<html lang="{P['html_lang']}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{P['title']}</title>
<meta name="description" content="{P['desc']}">
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
  .tbl-duo {{ display: flex; gap: 20px; max-height: 560px; overflow: auto;
              border: 1px solid var(--line); border-radius: 10px; align-items: flex-start; }}
  .tbl-duo table {{ width: auto; }}
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
  <h1>{P['h1']}</h1>
  <p class="updated">{P['updated'].format(d=d, now=now)}</p>
  <nav>{nav}</nav>
</header>
<main>
  <div class="kpi">
    <div>{P['kpi'][0]}<br><b>{pcr['pcr']}</b></div>
    <div>{P['kpi'][1]}<br><b>{pcr['put_volume']:,}</b>{P['unit']}</div>
    <div>{P['kpi'][2]}<br><b>{pcr['call_volume']:,}</b>{P['unit']}</div>
  </div>

  {market_section}

  <h2 id="oitable">{P['sec_oitable']}</h2>
  {tables['oi']}

  <h2 id="oi">{P['sec_oi']}</h2>
  <p>{P['oi_lead']}</p>
  <img src="{charts['oi']}" alt="Open interest by strike">

  {weekly_section}

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
  footer { border-top: 1px solid var(--line); margin-top: 48px; padding-top: 10px;
           font-size: 0.78em; color: var(--ink2); }
"""


def render_static_pages() -> None:
    """運営者情報・プライバシーポリシー(ASP審査・ステマ規制対応の必須ページ)。"""
    def shell(title, body):
        return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
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
    market_ja, spot = chart_market(oi, expiry, date, "ja")
    market_en, _ = chart_market(oi, expiry, date, "en")
    # テーブルの中心価格: 日経平均が取れなければ建玉加重平均の行使価格で代用
    center = spot if spot else float((oi["strike"] * oi["oi"]).sum() / max(oi["oi"].sum(), 1))
    for lang, market_chart in (("ja", market_ja), ("en", market_en)):
        charts = {
            "oi": chart_oi_distribution(oi, expiry, spot, lang),
            "pcr": chart_pcr(hist, lang),
            "market": market_chart,
        }
        tables = {
            "oi": oi_tables_html(oi, center, lang),
            "weekly": weekly_tables_html(weekly, lang) if weekly else None,
        }
        render_index(date, pcr, charts, tables, lang)
    render_static_pages()
    post = compose_post(date, pcr, oi, expiry, spot)
    print("--- post draft ---")
    print(post)
    with open(last_path, "w") as f:
        f.write(date)
    print(f"site generated: {os.path.join(SITE, 'index.html')}")


if __name__ == "__main__":
    main()
