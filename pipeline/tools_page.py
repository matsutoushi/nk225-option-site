# -*- coding: utf-8 -*-
"""インタラクティブなデータ分析ページ(tools.html)を生成する。

方針: トップページは静的画像のまま軽さを守り、掘りたい人向けの機能はこの1ページに集約する。
Plotlyのグラフを自己完結HTMLとして埋め込み、期間ズーム・系列の表示切替・ホバー数値表示を提供する。
"""

import os

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

PLOTLY_CDN = "https://cdn.plot.ly/plotly-2.35.2.min.js"

# ダークテーマ(サイト本体と合わせる)
BG = "#0d1117"
PANEL = "#151b26"
INK = "#e8eef7"
INK2 = "#9aa7ba"
GRID = "#2a3247"
UP = "#e66767"
DOWN = "#3987e5"
ACCENT = "#199e70"

LAYOUT = dict(
    paper_bgcolor=PANEL, plot_bgcolor=PANEL,
    font=dict(color=INK, size=12, family='"Noto Sans JP", "Yu Gothic", Meiryo, sans-serif'),
    xaxis=dict(gridcolor=GRID, zerolinecolor=GRID),
    yaxis=dict(gridcolor=GRID, zerolinecolor=GRID),
    margin=dict(l=60, r=60, t=50, b=40),
    hovermode="x unified",
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
)

T = {
    "ja": {
        "title": "データ分析ツール | 日経225オプション データ分析",
        "h1": "データ分析ツール",
        "lead": "グラフはドラッグで期間ズーム、ダブルクリックでリセット、凡例クリックで系列の表示/非表示ができます。元データはすべてCSVでダウンロードできます。",
        "flows": "海外投資家 累積ネット売買(週次・2021年〜)",
        "flows_note": "下部のスライダーで期間を絞り込めます。累積は表示期間の起点からの積み上げではなく、全期間の通算です。",
        "cot": "COT 投機筋ネットポジション(週次)",
        "cot_note": "凡例をクリックすると市場の表示/非表示を切り替えられます(ダブルクリックでその市場だけ表示)。",
        "part": "先物 取引参加者別ネット建玉(週次)",
        "part_note": "凡例クリックで会社を絞り込めます。プラス=買い越し、マイナス=売り越し。",
        "pcr": "日経225オプション Put/Callレシオ(日次)",
        "pcr_note": "データは日々蓄積されます。",
        "dl": "元データ(CSV)",
        "back": "← 日経ダッシュボード",
        "lang": '<a href="en/tools.html" lang="en">English</a>',
        "nodata": "データ蓄積中です。数日後に再度ご覧ください。",
    },
    "en": {
        "title": "Data Explorer | Nikkei 225 Options Data",
        "h1": "Data Explorer",
        "lead": "Drag to zoom, double-click to reset, click legend entries to show/hide series. All underlying data is downloadable as CSV.",
        "flows": "Foreign Investors: Cumulative Net Buying (weekly, since 2021)",
        "flows_note": "Use the range slider below to focus on a period. The cumulative line is computed over the full history.",
        "cot": "COT Speculator Net Positions (weekly)",
        "cot_note": "Click legend entries to toggle markets (double-click to isolate one).",
        "part": "Nikkei Futures: Net OI by Trading Participant (weekly)",
        "part_note": "Click legend entries to filter firms. Positive = net long, negative = net short.",
        "pcr": "Nikkei 225 Options Put/Call Ratio (daily)",
        "pcr_note": "This series accumulates daily.",
        "dl": "Source data (CSV)",
        "back": "← Dashboard",
        "lang": '<a href="../tools.html" lang="ja">日本語</a>',
        "nodata": "Data is still accumulating. Please check back in a few days.",
    },
}


def _fig_html(fig, div_id: str) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False, div_id=div_id,
                       config={"displaylogo": False, "responsive": True,
                               "modeBarButtonsToRemove": ["lasso2d", "select2d"]})


def _flows_fig(flows: pd.DataFrame, n225: pd.DataFrame | None, lang: str):
    df = flows.copy()
    df["dt"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["dt"]).sort_values("dt")
    df["tn"] = df["net_kyen"] / 1e9
    df["cum"] = df["tn"].cumsum()
    ja = lang == "ja"

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(
        x=df["dt"], y=df["cum"], name="累積(兆円)" if ja else "Cumulative (tn)",
        line=dict(color=ACCENT, width=2), fill="tozeroy",
        fillcolor="rgba(25,158,112,0.12)",
        hovertemplate="%{y:.2f}兆円<extra></extra>" if ja else "%{y:.2f} tn<extra></extra>"))
    fig.add_trace(go.Bar(
        x=df["dt"], y=df["tn"], name="週次(兆円)" if ja else "Weekly (tn)",
        marker_color=[ACCENT if v >= 0 else UP for v in df["tn"]], opacity=0.55,
        hovertemplate="%{y:+.2f}兆円<extra></extra>" if ja else "%{y:+.2f} tn<extra></extra>"),
        secondary_y=True)
    if n225 is not None and len(n225):
        n = n225[(n225.index >= df["dt"].min()) & (n225.index <= df["dt"].max())]
        if len(n):
            fig.add_trace(go.Scatter(
                x=n.index, y=n["Close"], name="日経平均" if ja else "Nikkei 225",
                line=dict(color="#8a97ad", width=1), opacity=0.7,
                hovertemplate="%{y:,.0f}<extra></extra>", visible="legendonly"))
    layout = {**LAYOUT, "xaxis": dict(gridcolor=GRID, zerolinecolor=GRID,
                                      rangeslider=dict(visible=True, thickness=0.08))}
    fig.update_layout(**layout, height=460)
    fig.update_yaxes(title_text="累積(兆円)" if ja else "Cumulative (tn yen)", secondary_y=False)
    fig.update_yaxes(title_text="週次(兆円)" if ja else "Weekly (tn yen)", secondary_y=True,
                     showgrid=False)
    return fig


def _cot_fig(cot_hist: pd.DataFrame, markets: list, lang: str):
    fig = go.Figure()
    palette = [DOWN, ACCENT, UP, "#c98500", "#9085e9", "#d55181",
               "#1baf7a", "#eb6834", "#86b6ef", "#e6a23c", "#7ec8a9"]
    for i, m in enumerate(markets):
        sub = cot_hist[cot_hist["market"] == m["key"]].sort_values("date")
        if not len(sub):
            continue
        fig.add_trace(go.Scatter(
            x=pd.to_datetime(sub["date"]), y=sub["net"], name=m[lang],
            line=dict(color=palette[i % len(palette)], width=1.6),
            hovertemplate="%{y:,.0f}<extra></extra>",
            visible=True if i < 3 else "legendonly"))
    fig.update_layout(**LAYOUT, height=440)
    fig.update_yaxes(title_text="ネット建玉(枚)" if lang == "ja" else "Net position (contracts)")
    return fig


def _participants_fig(hist: pd.DataFrame, lang: str):
    df = hist[hist["product"] == "日経225先物"].copy()
    df["dt"] = pd.to_datetime(df["date"], format="%Y%m%d", errors="coerce")
    df = df.dropna(subset=["dt"])
    latest = df["dt"].max()
    order = (df[df["dt"] == latest].assign(mag=lambda x: x["net"].abs())
             .sort_values("mag", ascending=False)["participant"].tolist())
    palette = [DOWN, ACCENT, UP, "#c98500", "#9085e9", "#d55181",
               "#1baf7a", "#eb6834", "#86b6ef", "#e6a23c"]
    fig = go.Figure()
    for i, name in enumerate(order[:20]):
        sub = df[df["participant"] == name].sort_values("dt")
        fig.add_trace(go.Scatter(
            x=sub["dt"], y=sub["net"], name=name,
            line=dict(color=palette[i % len(palette)], width=1.6),
            hovertemplate="%{y:+,.0f}<extra></extra>",
            visible=True if i < 4 else "legendonly"))
    fig.update_layout(**LAYOUT, height=460)
    fig.update_yaxes(title_text="ネット建玉(枚)" if lang == "ja" else "Net OI (contracts)")
    return fig


def _pcr_fig(pcr_hist: pd.DataFrame, lang: str):
    df = pcr_hist.copy()
    df["dt"] = pd.to_datetime(df["date"].astype(str), format="%Y%m%d", errors="coerce")
    df = df.dropna(subset=["dt"]).sort_values("dt")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["dt"], y=df["pcr"], name="PCR", mode="lines+markers",
        line=dict(color=ACCENT, width=2), marker=dict(size=6),
        hovertemplate="%{y:.3f}<extra></extra>"))
    fig.add_hline(y=1.0, line_dash="dash", line_color=INK2)
    fig.update_layout(**LAYOUT, height=360)
    return fig


def render_tools(site_dir: str, lang: str, data_dir: str,
                 n225: pd.DataFrame | None, cot_markets: list,
                 css: str, gsv: str, og: str, nav: str, sitemap: str,
                 disclaimer: str) -> None:
    """tools.html を生成する。データが無いセクションは自動的に省略する。"""
    t = T[lang]
    prefix = "../" if lang == "en" else ""
    blocks = []

    def block(title, note, fig, div_id, csv_name):
        dl = (f'<a class="dl" href="{prefix}data/{csv_name}" download>⭳ {t["dl"]}</a>'
              if csv_name else "")
        return (f'<h2>{title}{dl}</h2>\n<p>{note}</p>\n'
                f'<div class="plot">{_fig_html(fig, div_id)}</div>')

    # 海外投資家フロー
    p = os.path.join(data_dir, "investor_flows.csv")
    if os.path.exists(p):
        flows = pd.read_csv(p, dtype={"week": str, "date": str})
        if len(flows):
            blocks.append(block(t["flows"], t["flows_note"],
                                _flows_fig(flows, n225, lang), "plot-flows",
                                "investor_flows.csv"))

    # COT
    p = os.path.join(data_dir, "cot_history.csv")
    if os.path.exists(p):
        cot = pd.read_csv(p)
        if len(cot):
            blocks.append(block(t["cot"], t["cot_note"],
                                _cot_fig(cot, cot_markets, lang), "plot-cot",
                                "cot_history.csv"))

    # 参加者別建玉
    p = os.path.join(data_dir, "participants_history.csv")
    if os.path.exists(p):
        part = pd.read_csv(p, dtype={"date": str})
        if len(part):
            blocks.append(block(t["part"], t["part_note"],
                                _participants_fig(part, lang), "plot-part",
                                "participants_history.csv"))

    # PCR
    p = os.path.join(data_dir, "pcr_history.csv")
    if os.path.exists(p):
        pcr = pd.read_csv(p, dtype={"date": str})
        if len(pcr) >= 2:
            blocks.append(block(t["pcr"], t["pcr_note"], _pcr_fig(pcr, lang),
                                "plot-pcr", "pcr_history.csv"))

    body = "\n".join(blocks) if blocks else f"<p>{t['nodata']}</p>"

    html_doc = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{gsv}
{og}
<title>{t['title']}</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">
<script src="{PLOTLY_CDN}" charset="utf-8"></script>
<style>{css}
  .plot {{ background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
           padding: 6px; margin-bottom: 8px; overflow-x: auto; }}
</style>
</head>
<body>
<header>
  <h1>{t['h1']}</h1>
  {nav}
</header>
<p class="tagline">{t['lead']}</p>
<main>
{body}
</main>
<footer>
  {sitemap}
  <p>{disclaimer}</p>
</footer>
</body>
</html>
"""
    out = os.path.join(site_dir, "tools.html") if lang == "ja" \
        else os.path.join(site_dir, "en", "tools.html")
    os.makedirs(os.path.dirname(out) or site_dir, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html_doc)
