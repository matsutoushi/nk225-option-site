# -*- coding: utf-8 -*-
"""日経225オプション可視化サイトのビルドパイプライン。

1. JPX公式データを取得(jpx.py)
2. チャート生成(建玉分布・PCR推移・日経平均)
3. 履歴をdata/に蓄積(GitHub Actionsがコミットして永続化)
4. site/index.html を生成
"""

import os
from datetime import datetime, timezone, timedelta

import pandas as pd
import yfinance as yf
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import jpx

from matplotlib import font_manager

_available = {f.name for f in font_manager.fontManager.ttflist}
plt.rcParams["font.family"] = [f for f in ("Yu Gothic", "Meiryo", "IPAexGothic")
                               if f in _available] + ["sans-serif"]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
IMG = os.path.join(SITE, "img")
DATA = os.path.join(ROOT, "data")
JST = timezone(timedelta(hours=9))


def save_history(date: str, pcr: dict, oi: pd.DataFrame) -> pd.DataFrame:
    """日次データを蓄積し、PCR履歴のDataFrameを返す。"""
    os.makedirs(DATA, exist_ok=True)
    oi.to_csv(os.path.join(DATA, f"oi_{date}.csv"), index=False)

    hist_path = os.path.join(DATA, "pcr_history.csv")
    hist = pd.read_csv(hist_path, dtype={"date": str}) if os.path.exists(hist_path) else \
        pd.DataFrame(columns=["date", "put_volume", "call_volume", "pcr"])
    hist = hist[hist["date"].astype(str).str.fullmatch(r"20\d{6}") & (hist["date"] != date)]
    hist = pd.concat([hist, pd.DataFrame([{"date": date, **pcr}])], ignore_index=True)
    hist = hist.sort_values("date")
    hist.to_csv(hist_path, index=False)
    return hist


def chart_oi_distribution(oi: pd.DataFrame, expiry: str, spot: float | None) -> str:
    """直近限月の行使価格別建玉分布(プット/コール)を描く。"""
    df = oi[oi["expiry"] == expiry]
    strikes = sorted(df["strike"].unique())
    # ATM周辺に絞る(現値±15%、なければ建玉上位帯)
    if spot:
        strikes = [s for s in strikes if 0.85 * spot <= s <= 1.15 * spot]
    puts = df[df["type"] == "P"].set_index("strike")["oi"].reindex(strikes).fillna(0)
    calls = df[df["type"] == "C"].set_index("strike")["oi"].reindex(strikes).fillna(0)

    fig, ax = plt.subplots(figsize=(10, 6))
    width = (strikes[1] - strikes[0]) * 0.4 if len(strikes) > 1 else 100
    ax.barh([s - width / 2 for s in strikes], -puts.values, height=width,
            color="#c23b22", label="プット建玉")
    ax.barh([s + width / 2 for s in strikes], calls.values, height=width,
            color="#1f4e79", label="コール建玉")
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
    ax.plot(x, hist["pcr"], marker="o", color="#1f4e79", linewidth=1.5)
    ax.axhline(1.0, color="#999", linestyle="--", linewidth=1)
    ax.set_title("日経225オプション Put/Call レシオ(出来高ベース・日次)")
    ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, "pcr.png"), dpi=120)
    plt.close(fig)
    return "img/pcr.png"


def chart_n225() -> tuple[str | None, float | None]:
    """日経平均チャート。取得失敗(CI環境でのブロック等)でもサイト生成は止めない。"""
    try:
        hist = yf.Ticker("^N225").history(period="6mo")
        if len(hist) == 0:
            raise RuntimeError("empty history")
    except Exception as e:
        print(f"WARN: N225 fetch failed, skipping market chart: {e}")
        return None, None
    spot = float(hist["Close"].iloc[-1])
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(hist.index, hist["Close"], color="#1f4e79", linewidth=1.5)
    ax.set_title("日経平均株価(直近6ヶ月)")
    ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    os.makedirs(IMG, exist_ok=True)
    fig.savefig(os.path.join(IMG, "n225.png"), dpi=120)
    plt.close(fig)
    return "img/n225.png", spot


def render_index(date: str, pcr: dict, charts: dict) -> None:
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    d = f"{date[:4]}-{date[4:6]}-{date[6:]}"
    market_section = (
        f'<h2 id="market">マーケット概況</h2>\n  <img src="{charts["n225"]}" alt="日経平均チャート">'
        if charts.get("n225") else ""
    )
    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>日経225オプション データ分析 | 建玉分布・Put/Callレシオ 毎日更新</title>
<meta name="description" content="日経225オプションの行使価格別建玉分布とPut/Callレシオを毎営業日自動更新。データ出典はJPX公式。">
<style>
  body {{ font-family: "Yu Gothic", Meiryo, sans-serif; max-width: 980px; margin: 0 auto; padding: 16px; color: #222; line-height: 1.7; }}
  header {{ border-bottom: 2px solid #1f4e79; padding-bottom: 8px; }}
  h1 {{ font-size: 1.5em; margin-bottom: 4px; }}
  .updated {{ color: #666; font-size: 0.9em; }}
  .kpi {{ display: flex; gap: 16px; margin: 16px 0; flex-wrap: wrap; }}
  .kpi div {{ background: #f4f7fb; border-left: 4px solid #1f4e79; padding: 10px 18px; }}
  .kpi b {{ font-size: 1.4em; }}
  img {{ max-width: 100%; height: auto; border: 1px solid #eee; }}
  nav a {{ margin-right: 16px; }}
  footer {{ border-top: 1px solid #ddd; margin-top: 32px; padding-top: 8px; font-size: 0.85em; color: #666; }}
</style>
</head>
<body>
<header>
  <h1>日経225オプション データ分析</h1>
  <p class="updated">データ基準日: {d} | 最終更新: {now} JST(毎営業日 自動更新)</p>
  <nav><a href="#oi">建玉分布</a><a href="#pcr">Put/Callレシオ</a><a href="#market">マーケット</a></nav>
</header>
<main>
  <div class="kpi">
    <div>Put/Call レシオ<br><b>{pcr['pcr']}</b></div>
    <div>プット出来高<br><b>{pcr['put_volume']:,}</b> 枚</div>
    <div>コール出来高<br><b>{pcr['call_volume']:,}</b> 枚</div>
  </div>

  <h2 id="oi">行使価格別 建玉分布</h2>
  <p>建玉が積み上がった行使価格は、市場参加者が意識する「壁」の目安になります。</p>
  <img src="{charts['oi']}" alt="日経225オプション行使価格別建玉分布">

  <h2 id="pcr">Put/Call レシオの推移</h2>
  <p>1.0超はプット優勢(警戒・ヘッジ需要)、1.0未満はコール優勢の目安です。</p>
  <img src="{charts['pcr']}" alt="Put/Callレシオ推移">

  {market_section}

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
        f.write(html)


def main() -> None:
    files = jpx.discover_files()
    date = files["date"]
    print(f"JPX data date: {date}")

    pcr = jpx.fetch_put_call_volume(files["whole_day"])
    print(f"PCR: {pcr}")
    oi = jpx.fetch_open_interest(files["open_interest"])
    print(f"OI rows: {len(oi)}")

    hist = save_history(date, pcr, oi)
    n225_chart, spot = chart_n225()
    expiry = jpx.nearest_expiry(oi)
    charts = {
        "oi": chart_oi_distribution(oi, expiry, spot),
        "pcr": chart_pcr(hist),
        "n225": n225_chart,
    }
    render_index(date, pcr, charts)
    print(f"site generated: {os.path.join(SITE, 'index.html')}")


if __name__ == "__main__":
    main()
