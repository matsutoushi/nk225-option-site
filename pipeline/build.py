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

UP = "#c23b22"    # 陽線・プット系(赤)
DOWN = "#1f4e79"  # 陰線・コール系(青)


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
        ax.axhline(spot, color="#333", linestyle="--", linewidth=1,
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
    ax.plot(x, hist["pcr"], marker="o", color=DOWN, linewidth=1.5)
    ax.axhline(1.0, color="#999", linestyle="--", linewidth=1)
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


def chart_market(oi: pd.DataFrame, expiry: str) -> tuple[str | None, float | None]:
    """ローソク足+価格帯別出来高+最大建玉ライン+MACD+RSI。"""
    try:
        hist = yf.Ticker("^N225").history(period="6mo")
        if len(hist) < 30:
            raise RuntimeError("insufficient history")
    except Exception as e:
        print(f"WARN: N225 fetch failed, skipping market chart: {e}")
        return None, None

    spot = float(hist["Close"].iloc[-1])
    o, h, l, c = (hist[k].values for k in ("Open", "High", "Low", "Close"))
    vol = hist["Volume"].fillna(0).values
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
                 color="#888", alpha=0.25, zorder=0)
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
    ax2.plot(x, macd, color="#333", linewidth=1.2, label="MACD")
    ax2.plot(x, signal, color="#e69f00", linewidth=1.2, label="シグナル")
    ax2.axhline(0, color="#999", linewidth=0.8)
    ax2.legend(loc="upper left", fontsize=8, ncol=2)
    ax2.set_ylabel("MACD")
    ax2.grid(alpha=0.3)
    plt.setp(ax2.get_xticklabels(), visible=False)

    # --- RSI ---
    rsi = _rsi(close_s)
    ax3.plot(x, rsi, color=DOWN, linewidth=1.2)
    for lv, style in ((70, "--"), (30, "--"), (50, ":")):
        ax3.axhline(lv, color="#999", linestyle=style, linewidth=0.8)
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


def _heat_color(pct: float) -> str:
    """0(最小)→赤、0.5→黄、1(最大)→緑 の淡色グラデーション。"""
    hue = int(120 * pct)  # 0=red, 120=green
    return f"hsl({hue}, 75%, 85%)"


def oi_tables_html(oi: pd.DataFrame, center: float) -> str:
    """行使価格別建玉テーブル(現在値と増減を横並び)。現値±20,000円に限定。"""
    lo, hi = center - 20000, center + 20000
    oi = oi[(oi["strike"] >= lo) & (oi["strike"] <= hi)]
    expiries = sorted(oi["expiry"].unique())
    strikes = sorted(oi["strike"].unique(), reverse=True)

    def pivot(col):
        return {(t, e): oi[(oi["type"] == t) & (oi["expiry"] == e)]
                .set_index("strike")[col].to_dict()
                for t in ("C", "P") for e in expiries}

    cur, chg = pivot("oi"), pivot("change")

    # 建玉の多寡→色: 偏りが大きいのでパーセンタイル順位でグラデーションを付ける
    all_values = sorted(v for tbl in cur.values() for v in tbl.values())

    def pct_rank(v):
        if not all_values:
            return 0.0
        import bisect
        return bisect.bisect_left(all_values, v) / max(len(all_values) - 1, 1)

    def render(table, is_change):
        head1 = "<tr><th rowspan='2'>行使価格</th>"
        head1 += f"<th colspan='{len(expiries)}'>Call</th><th colspan='{len(expiries)}'>Put</th></tr>"
        head2 = "<tr>" + "".join(f"<th>{_exp_label(e)}</th>" for e in expiries) * 2 + "</tr>"
        body = []
        for s in strikes:
            tds = [f"<th>{s:,}</th>"]
            for t in ("C", "P"):
                for e in expiries:
                    v = table[(t, e)].get(s)
                    if v is None or (is_change and cur[(t, e)].get(s) is None):
                        tds.append("<td class='na'>-</td>")
                    elif is_change:
                        cls = "pos" if v > 0 else ("neg" if v < 0 else "")
                        tds.append(f"<td class='{cls}'>{v:+,}</td>" if v else "<td>0</td>")
                    else:
                        style = f" style='background:{_heat_color(pct_rank(v))}'"
                        tds.append(f"<td{style}>{v:,}</td>")
            body.append("<tr>" + "".join(tds) + "</tr>")
        cap = "建玉増減(前日比)" if is_change else "建玉残高(多=緑 / 少=赤)"
        return (f"<div class='tbl-box'><h3>{cap}</h3><div class='tbl-scroll'>"
                f"<table>{head1}{head2}{''.join(body)}</table></div></div>")

    note = (f"<p>現値を挟んで上下20,000円の範囲({lo:,.0f}〜{hi:,.0f}円)を表示。"
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
<style>
  body {{ font-family: "Yu Gothic", Meiryo, sans-serif; max-width: 1100px; margin: 0 auto; padding: 16px; color: #222; line-height: 1.7; }}
  header {{ border-bottom: 2px solid #1f4e79; padding-bottom: 8px; }}
  h1 {{ font-size: 1.5em; margin-bottom: 4px; }}
  .updated {{ color: #666; font-size: 0.9em; }}
  .kpi {{ display: flex; gap: 16px; margin: 16px 0; flex-wrap: wrap; }}
  .kpi div {{ background: #f4f7fb; border-left: 4px solid #1f4e79; padding: 10px 18px; }}
  .kpi b {{ font-size: 1.4em; }}
  img {{ max-width: 100%; height: auto; border: 1px solid #eee; }}
  nav a {{ margin-right: 16px; }}
  .tbl-pair {{ display: flex; gap: 16px; flex-wrap: wrap; align-items: flex-start; }}
  .tbl-box {{ flex: 1 1 420px; min-width: 320px; }}
  .tbl-scroll {{ max-height: 560px; overflow: auto; border: 1px solid #ddd; }}
  table {{ border-collapse: collapse; font-size: 12px; white-space: nowrap; width: 100%; }}
  th, td {{ border: 1px solid #ddd; padding: 2px 8px; text-align: right; }}
  th {{ background: #f4f7fb; position: sticky; top: 0; }}
  tr > th:first-child {{ position: sticky; left: 0; background: #f4f7fb; }}
  td.name {{ text-align: left; }}
  td.pos {{ color: #c23b22; }}
  td.neg {{ color: #1f4e79; }}
  td.na {{ color: #bbb; }}
  footer {{ border-top: 1px solid #ddd; margin-top: 32px; padding-top: 8px; font-size: 0.85em; color: #666; }}
  @media (max-width: 600px) {{
    body {{ padding: 8px; }}
    h1 {{ font-size: 1.2em; }}
    .kpi div {{ padding: 6px 12px; }}
    .kpi b {{ font-size: 1.1em; }}
    table {{ font-size: 11px; }}
    .tbl-scroll {{ max-height: 420px; }}
    nav a {{ margin-right: 10px; font-size: 0.9em; }}
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
  <p>データ出典: 日本取引所グループ(JPX)公表データより当サイト作成。Yahoo Finance(日経平均、遅延データ)。</p>
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
    market_chart, spot = chart_market(oi, expiry)
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
