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

# ライトテーマ(サイト本体と合わせる)
BG = "#f6f7f9"
PANEL = "#ffffff"
INK = "#111820"
INK2 = "#4b5563"
GRID = "#dfe3e9"
UP = "#d1453b"
DOWN = "#1f6fd0"
ACCENT = "#0f8a5f"

LAYOUT = dict(
    paper_bgcolor=PANEL, plot_bgcolor=PANEL,
    font=dict(color=INK, size=12, family='"Noto Sans JP", "Yu Gothic", Meiryo, sans-serif'),
    xaxis=dict(gridcolor=GRID, zerolinecolor=GRID),
    yaxis=dict(gridcolor=GRID, zerolinecolor=GRID),
    margin=dict(l=60, r=60, t=50, b=40),
    hovermode="x unified",
    # 凡例はチャート上部に横並び。右側縦並び(既定)はスマホで幅を食い潰すため使わない。
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=11),
                orientation="h", yanchor="bottom", y=1.02,
                xanchor="left", x=0),
)

T = {
    "ja": {
        "title": "データ分析ツール | 日経225オプション データ分析",
        "desc": "海外投資家の累積売買、COT投機筋ポジション、証券会社別の先物建玉、Put/Callレシオの時系列を、期間を変えながら自分で確かめられるページです。各グラフに読み方の解説を添えています。",
        "h1": "データ分析ツール",
        "lead": "日次・週次で更新している時系列データを、期間を変えながら自分で確かめるためのページです。グラフはドラッグで期間ズーム、ダブルクリックでリセット、凡例クリックで系列の表示/非表示ができます。",
        "intro": "ダッシュボードが「今日どうなっているか」を示すのに対して、このページは<b>「これまでどう動いてきたか」</b>を見るためのものです。"
                 "ポジション系の指標は、その日の水準だけを見ても意味が取れません。過去のレンジのどこにいるのか、"
                 "どちらへ向かっているのかが分かってはじめて判断材料になります。"
                 "以下の4つは、いずれも公表データを当サイトで集計したものです。各グラフの下に読み方を添えています。",
        "flows": "海外投資家 累積ネット売買(週次・2021年〜)",
        "flows_note": "下部のスライダーで期間を絞り込めます。累積は表示期間の起点からの積み上げではなく、全期間の通算です。",
        "flows_how": "<b>水準ではなく傾きを見ます。</b>日本株の売買代金は海外投資家が大きな割合を占めるため、"
                     "この線の向きが変わるところは需給の転換点になりやすい箇所です。"
                     "2021年以降の通算は+18.30兆円で、直近週(2026年8月第2週)は+0.21兆円でした。"
                     "累積値そのものは起点の取り方で変わるので、絶対額を評価する使い方には向きません。"
                     "週次データなので反応は遅く、日々の値動きの説明には使えない点にも注意してください。",
        "cot": "COT 投機筋ネットポジション(週次)",
        "cot_note": "凡例をクリックすると市場の表示/非表示を切り替えられます(ダブルクリックでその市場だけ表示)。",
        "cot_how": "米CFTCが公表する建玉明細から、投機筋(非商業部門)のネットを市場ごとに追っています。"
                   "対象はS&amp;P500・ナスダック100・日経225・円・ユーロ・ポンド・金・銀・銅・原油・天然ガスの11市場です。"
                   "<b>使いどころは、片側に偏りきった状態からの反転</b>です。"
                   "偏りが極端なほど、同じ方向のニュースが出ても新規の買い手(売り手)が残っておらず、"
                   "逆方向に振れたときの巻き戻しが大きくなります。"
                   "ただし火曜時点の集計が金曜に公表されるため、<b>常に3営業日遅れ</b>です。売買のタイミングを計る用途には向きません。",
        "part": "先物 取引参加者別ネット建玉(週次)",
        "part_note": "凡例クリックで会社を絞り込めます(プラス=買い越し、マイナス=売り越し)。「日経平均」をクリックすると右軸に重ねて表示できます。",
        "part_how": "日本取引所グループは、証券会社名を明示したうえで週次の建玉を公表しています。"
                    "匿名のカテゴリー別で公表される米国のCOTと違い、どの会社がどちら側にいるかが分かります。"
                    "<b>ただしゼロと比べても意味がありません。</b>"
                    "直近1年(52週)を集計すると、ＨＳＢＣ証券は52週すべてが売り越し(平均−31,604枚)、"
                    "ＳＭＢＣ日興証券は52週すべてが買い越しでした。この間、日経平均は大きく上下しています。"
                    "仕組債のヘッジ、顧客注文の裏側、裁定取引といった業務の形から来る構造的な偏りなので、"
                    "「売り越しだから弱気」と読むと1年間外し続けることになります。"
                    "見るべきは<b>その会社自身の平常値からのズレ</b>で、"
                    "平常が−31,000枚の会社が−5,000枚になっていれば、符号は売り越しのままでも実質は買い戻しです。",
        "pcr": "日経225オプション Put/Callレシオ(日次)",
        "pcr_note": "データは日々蓄積されます。",
        "pcr_how": "プット出来高をコール出来高で割った比率です。<b>1.0は中立ではありません。</b>"
                   "機関投資家の下落ヘッジが恒常的にあるため、ラージの実測平均は1.57、ミニは0.91でした。"
                   "水準ではなく、直近レンジの中での位置で見てください。"
                   "また比率は分母でも動きます。2026年7月28日、日経平均が3.95%下落した日にレシオは1.995から1.387へ<b>下がりました</b>。"
                   "プット出来高は21,148枚から35,728枚へ1.7倍になりましたが、"
                   "コール出来高が10,603枚から25,764枚へ2.4倍と、それ以上に膨らんだためです。"
                   "急落局面では利益確定・反発狙いの買い・不要になったコールの処分が同時に起きます。"
                   "<b>両方の絶対量を見ないと、事実を正反対に読み違えます。</b>",
        "outro_h": "組み合わせて読む",
        "outro": "単独で結論が出る指標はありません。実際には、"
                 "<b>COTで米国側の偏りを見て、参加者別建玉で国内の誰が反対側にいるかを確かめ、"
                 "Put/Callレシオでヘッジ需要の温度を測る</b>、という順で突き合わせると矛盾が見つけやすくなります。"
                 "たとえば投機筋が買いに偏っている一方で国内勢が平常より売りを積んでいるなら、"
                 "どちらかが先に降りることになります。"
                 "各指標の詳しい解説は <a href=\"guide-cot.html\">COTレポートの見方</a>・"
                 "<a href=\"guide-teguchi.html\">先物の手口の見方</a>・"
                 "<a href=\"guide-pcr.html\">Put/Callレシオとは</a> にまとめています。",
        "dl": "元データ(CSV)",
        "back": "← 日経ダッシュボード",
        "lang": '<a href="en/tools.html" lang="en">English</a>',
        "nodata": "データ蓄積中です。数日後に再度ご覧ください。",
        "legend_show": "凡例を表示", "legend_hide": "凡例を隠す",
        "zoom_on": "拡大操作 オフ", "zoom_off": "拡大操作 オン",
    },
    "en": {
        "title": "Data Explorer | Nikkei 225 Options Data",
        "desc": "Interactive history for foreign-investor flows, CFTC speculator positioning, Nikkei futures open interest by named participant, and the put/call ratio. Each chart carries a note on what it does and does not tell you.",
        "h1": "Data Explorer",
        "lead": "Interactive history for the daily and weekly series this site collects. Drag to zoom, double-click to reset, click legend entries to show/hide series.",
        "intro": "The dashboard shows where things stand today. This page shows <b>how they got there</b>. "
                 "Positioning data rarely means anything at a single point in time — you need to know where the "
                 "current reading sits in its own range, and which way it is moving. "
                 "All four series below are compiled from official public data, with reading notes under each chart.",
        "flows": "Foreign Investors: Cumulative Net Buying (weekly, since 2021)",
        "flows_note": "Use the range slider below to focus on a period. The cumulative line is computed over the full history.",
        "flows_how": "<b>Read the slope, not the level.</b> Foreign investors account for a large share of Japanese "
                     "cash equity turnover, so changes in direction here tend to mark supply-demand turning points. "
                     "The cumulative total since 2021 stands at +¥18.30tn, with the latest week (2nd week of August 2026) at +¥0.21tn. "
                     "The cumulative value depends on the chosen starting point, so the absolute number is not meaningful on its own. "
                     "This is weekly data and therefore slow — it will not explain any given day's move.",
        "cot": "COT Speculator Net Positions (weekly)",
        "cot_note": "Click legend entries to toggle markets (double-click to isolate one).",
        "cot_how": "Non-commercial (speculator) net positions from the CFTC's Commitments of Traders report, across eleven "
                   "markets: S&amp;P 500, Nasdaq 100, Nikkei 225, yen, euro, sterling, gold, silver, copper, crude and natural gas. "
                   "<b>The useful signal is a reversal out of a crowded extreme</b> — the more one-sided the positioning, "
                   "the fewer marginal buyers (or sellers) remain to act on confirming news, and the sharper the unwind when it turns. "
                   "Note the lag: positions are measured on Tuesday and published on Friday, so the data is <b>always three "
                   "business days old</b>. It is not a timing tool.",
        "part": "Nikkei Futures: Net OI by Trading Participant (weekly)",
        "part_note": "Click legend entries to filter firms (positive = net long, negative = net short). Click \"Nikkei 225\" to overlay the index on the right axis.",
        "part_how": "JPX publishes weekly futures positions <b>by named trading participant</b> — unlike the CFTC's anonymous "
                    "categories, you can see which firm is on which side. "
                    "<b>Comparing against zero is useless, though.</b> Over the last 52 weeks, HSBC was net short in all 52 "
                    "(averaging −31,604 contracts) and SMBC Nikko net long in all 52, while the Nikkei moved substantially "
                    "in both directions. These are structural positions arising from structured-product hedging, the other "
                    "side of client flow and index arbitrage — not house views. "
                    "Compare each firm against <b>its own baseline</b>: a firm that normally sits at −31,000 and now reads "
                    "−5,000 has effectively bought back a large short, even though the sign is still negative. "
                    "<a href=\"guide-participants.html\">Full explanation</a>",
        "pcr": "Nikkei 225 Options Put/Call Ratio (daily)",
        "pcr_note": "This series accumulates daily.",
        "pcr_how": "Put volume divided by call volume. <b>1.0 is not the neutral line.</b> Institutional downside hedging is "
                   "structural, so the measured average is 1.57 for large contracts and 0.91 for mini. Judge the reading "
                   "against its own recent range. "
                   "The ratio also moves on its denominator: on 28 July 2026 the Nikkei fell 3.95% and the ratio <b>fell</b> "
                   "from 1.995 to 1.387. Put volume rose from 21,148 to 35,728 (×1.7), but call volume rose from 10,603 to "
                   "25,764 (×2.4) — more. Sharp declines trigger profit-taking on puts, cheap calls bought for a bounce, and "
                   "the closing of calls that are now far out of the money, all at once. "
                   "<b>Without both raw volumes you can read the day exactly backwards.</b> "
                   "<a href=\"guide-put-call-ratio.html\">Full explanation</a>",
        "outro_h": "Reading them together",
        "outro": "No single series settles anything. In practice it helps to work in order: "
                 "<b>check where US speculative positioning is crowded, then see which domestic firms are on the other side, "
                 "then use the put/call ratio to gauge hedging demand.</b> "
                 "Contradictions show up quickly that way — if speculators are heavily long while domestic participants are "
                 "shorter than their own baseline, one of the two has to give first. "
                 "See <a href=\"guide-participants.html\">JPX participant positioning</a>, "
                 "<a href=\"guide-put-call-ratio.html\">the put/call ratio</a> and "
                 "<a href=\"guide-gamma-exposure.html\">gamma exposure</a> for the detail.",
        "dl": "Source data (CSV)",
        "back": "← Dashboard",
        "lang": '<a href="../tools.html" lang="ja">日本語</a>',
        "nodata": "Data is still accumulating. Please check back in a few days.",
        "legend_show": "Show legend", "legend_hide": "Hide legend",
        "zoom_on": "Zoom: off", "zoom_off": "Zoom: on",
    },
}


def _fig_html(fig, div_id: str) -> str:
    # 凡例は必ず上部の横並びにする(右側縦並びだとスマホでチャートが潰れる)。
    # 各図の update_layout 後に強制するため、ここで最終指定する。
    fig.update_layout(legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=11),
                                  orientation="h", yanchor="bottom", y=1.02,
                                  xanchor="left", x=0))
    return fig.to_html(full_html=False, include_plotlyjs=False, div_id=div_id,
                       config={"displaylogo": False, "responsive": True,
                               # スクロール中の誤ズームを防ぐ。ダブルタップで元の表示に戻す。
                               "scrollZoom": False, "doubleClick": "reset",
                               "modeBarButtonsToRemove": ["lasso2d", "select2d",
                                                          "autoScale2d", "toggleSpikelines"]})


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
        fillcolor="rgba(15,138,95,0.12)",
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
                line=dict(color="#6b7280", width=1), opacity=0.7,
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
    palette = [DOWN, ACCENT, UP, "#b3730a", "#6b5fd0", "#d55181",
               "#0f7a4a", "#eb6834", "#4a7fb5", "#b3730a", "#4a9b7a"]
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


def _participants_fig(hist: pd.DataFrame, lang: str, n225: pd.DataFrame | None = None):
    ja = lang == "ja"
    df = hist[hist["product"] == "日経225先物"].copy()
    df["dt"] = pd.to_datetime(df["date"], format="%Y%m%d", errors="coerce")
    df = df.dropna(subset=["dt"])
    latest = df["dt"].max()
    order = (df[df["dt"] == latest].assign(mag=lambda x: x["net"].abs())
             .sort_values("mag", ascending=False)["participant"].tolist())
    palette = [DOWN, ACCENT, UP, "#b3730a", "#6b5fd0", "#d55181",
               "#0f7a4a", "#eb6834", "#4a7fb5", "#b3730a"]
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    for i, name in enumerate(order[:20]):
        sub = df[df["participant"] == name].sort_values("dt")
        fig.add_trace(go.Scatter(
            x=sub["dt"], y=sub["net"], name=name,
            line=dict(color=palette[i % len(palette)], width=1.6),
            hovertemplate="%{y:+,.0f}<extra></extra>",
            visible=True if i < 4 else "legendonly"), secondary_y=False)
    if n225 is not None and len(n225):
        n = n225[(n225.index >= df["dt"].min()) & (n225.index <= df["dt"].max())]
        if len(n):
            fig.add_trace(go.Scatter(
                x=n.index, y=n["Close"], name="日経平均" if ja else "Nikkei 225",
                line=dict(color="#6b7280", width=1.4), opacity=0.75,
                hovertemplate="%{y:,.0f}<extra></extra>",
                visible="legendonly"), secondary_y=True)
    fig.update_layout(**LAYOUT, height=460)
    fig.update_yaxes(title_text="ネット建玉(枚)" if ja else "Net OI (contracts)",
                     secondary_y=False)
    fig.update_yaxes(title_text="日経平均" if ja else "Nikkei 225", secondary_y=True,
                     showgrid=False)
    return fig


def _pcr_fig(pcr_hist: pd.DataFrame, lang: str):
    df = pcr_hist.copy()
    df["dt"] = pd.to_datetime(df["date"].astype(str), format="%Y%m%d", errors="coerce")
    df = df.dropna(subset=["dt"]).sort_values("dt")
    # 営業日のみをカテゴリ軸として等間隔に並べる(土日祝の空白を作らない)
    df["label"] = df["dt"].dt.strftime("%Y-%m-%d")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["label"], y=df["pcr"], name="PCR", mode="lines+markers",
        line=dict(color=ACCENT, width=2), marker=dict(size=6),
        hovertemplate="%{y:.3f}<extra></extra>"))
    fig.add_hline(y=1.0, line_dash="dash", line_color=INK2)
    fig.update_layout(**LAYOUT, height=360)
    fig.update_xaxes(type="category", nticks=10)
    return fig


def render_tools(site_dir: str, lang: str, data_dir: str,
                 n225: pd.DataFrame | None, cot_markets: list,
                 css: str, gsv: str, og: str, nav: str, sitemap: str,
                 disclaimer: str) -> None:
    """tools.html を生成する。データが無いセクションは自動的に省略する。"""
    t = T[lang]
    prefix = "../" if lang == "en" else ""
    blocks = []

    def block(title, note, fig, div_id, csv_name, how=""):
        dl = (f'<a class="dl" href="{prefix}data/{csv_name}" download>⭳ {t["dl"]}</a>'
              if csv_name else "")
        # 読み方(how)はグラフの後ろに置く。図を見てから解説を読む順にする。
        how_html = f'\n<p class="how">{how}</p>' if how else ""
        return (f'<h2>{title}{dl}</h2>\n<p>{note}</p>\n'
                f'<div class="plot">{_fig_html(fig, div_id)}</div>{how_html}')

    # 海外投資家フロー
    p = os.path.join(data_dir, "investor_flows.csv")
    if os.path.exists(p):
        flows = pd.read_csv(p, dtype={"week": str, "date": str})
        if len(flows):
            # JPX由来のため生CSVダウンロードは提供しない(csv_name=None)
            blocks.append(block(t["flows"], t["flows_note"],
                                _flows_fig(flows, n225, lang), "plot-flows", None,
                                t["flows_how"]))

    # COT(CFTC=米政府データ、ダウンロード可)
    p = os.path.join(data_dir, "cot_history.csv")
    if os.path.exists(p):
        cot = pd.read_csv(p)
        if len(cot):
            blocks.append(block(t["cot"], t["cot_note"],
                                _cot_fig(cot, cot_markets, lang), "plot-cot",
                                "cot_history.csv", t["cot_how"]))

    # 参加者別建玉(JPX由来のためダウンロード不可)
    p = os.path.join(data_dir, "participants_history.csv")
    if os.path.exists(p):
        part = pd.read_csv(p, dtype={"date": str})
        if len(part):
            blocks.append(block(t["part"], t["part_note"],
                                _participants_fig(part, lang, n225), "plot-part", None,
                                t["part_how"]))

    # PCR(JPX出来高由来のためダウンロード不可)
    p = os.path.join(data_dir, "pcr_history.csv")
    if os.path.exists(p):
        pcr = pd.read_csv(p, dtype={"date": str})
        if len(pcr) >= 2:
            blocks.append(block(t["pcr"], t["pcr_note"], _pcr_fig(pcr, lang),
                                "plot-pcr", None, t["pcr_how"]))

    if blocks:
        # 最後に指標同士の突き合わせ方を置く。個別の図だけでは判断できないため。
        blocks.append(f'<h2>{t["outro_h"]}</h2><p class="how">{t["outro"]}</p>')
    body = "\n".join(blocks) if blocks else f"<p>{t['nodata']}</p>"

    html_doc = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{gsv}
{og}
<meta name="description" content="{t['desc']}">
<title>{t['title']}</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">
<script src="{PLOTLY_CDN}" charset="utf-8"></script>
<style>{css}
  .plot {{ background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
           padding: 6px; margin-bottom: 8px; overflow-x: auto; }}
  /* グラフの下に置く読み方の解説。操作説明(通常のp)より一段沈めて区別する。 */
  .how {{ font-size: 0.9em; line-height: 1.9; color: var(--ink2);
          border-left: 3px solid var(--line); padding-left: 12px; margin: 0 0 26px; }}
  .how b {{ color: var(--ink); }}
  /* スマホでは凡例が幅を食うため、モードバーとホバーも含めて詰める */
  @media (max-width: 600px) {{
    .plot {{ padding: 4px; }}
    .plot .modebar {{ transform: scale(0.85); transform-origin: top right; }}
  }}
</style>
</head>
<body>
<header>
  <h1>{t['h1']}</h1>
  {nav}
</header>
<p class="tagline">{t['lead']}</p>
<p class="how">{t['intro']}</p>
<main>
{body}
</main>
<footer>
  {sitemap}
  <p>{disclaimer}</p>
</footer>
<script>
// スマホでは凡例がチャート面積を奪うため、画面幅に応じてレイアウトを詰める。
// 凡例は上部に横並び(既定の右側縦並びだと375px幅でチャートがほぼ潰れる)。
(function () {{
  function tune() {{
    var narrow = window.innerWidth <= 600;
    document.querySelectorAll('.plot .js-plotly-plot').forEach(function (gd) {{
      if (!window.Plotly || !gd.layout) return;
      Plotly.relayout(gd, narrow ? {{
        // 凡例は常に表示(上部・横並び)。隠すのはユーザーがボタンで選んだときだけ。
        'legend.orientation': 'h',
        'legend.yanchor': 'bottom',
        'legend.y': 1.02,
        'legend.xanchor': 'left',
        'legend.x': 0,
        'legend.font.size': 9,
        'showlegend': true,
        'margin.l': 44, 'margin.r': 12, 'margin.t': 54, 'margin.b': 34,
        'font.size': 10,
        'hovermode': 'closest',
        // 触れただけでズーム矩形が始まるのを防ぐ(指はページスクロールに使う)。
        // 拡大したいときは下のボタンで明示的に有効化する。
        'dragmode': false,
        'xaxis.tickfont.size': 9, 'yaxis.tickfont.size': 9,
        'xaxis.nticks': 5
      }} : {{
        'legend.orientation': 'h',
        'legend.yanchor': 'bottom',
        'legend.y': 1.02,
        'legend.xanchor': 'left',
        'legend.x': 0,
        'legend.font.size': 11,
        'showlegend': true,
        'margin.l': 60, 'margin.r': 60, 'margin.t': 50, 'margin.b': 40,
        'font.size': 12,
        'hovermode': 'x unified',
        'dragmode': 'zoom',
        'xaxis.tickfont.size': 12, 'yaxis.tickfont.size': 12
      }});
    }});
  }}
  function btn(label) {{
    var b = document.createElement('button');
    b.textContent = label;
    b.style.cssText = 'padding:6px 12px;font-size:12px;background:transparent;color:#4b5563;'
      + 'border:1px solid #dfe3e9;border-radius:6px;margin:0 4px;';
    return b;
  }}
  // スマホ用の操作ボタン: ①凡例の表示/非表示 ②ズーム操作の有効/無効
  function addControls() {{
    if (window.innerWidth > 600) return;
    document.querySelectorAll('.plot').forEach(function (box) {{
      var gd = box.querySelector('.js-plotly-plot');
      if (!gd || box.parentNode.querySelector('.plot-ctl')) return;
      var bar = document.createElement('div');
      bar.className = 'plot-ctl';
      bar.style.cssText = 'display:flex;justify-content:center;margin:2px 0 10px;';

      var lb = btn('{t['legend_hide']}');
      lb.addEventListener('click', function () {{
        var on = !gd.layout.showlegend;
        Plotly.relayout(gd, {{'showlegend': on, 'margin.t': on ? 54 : 24}});
        lb.textContent = on ? '{t['legend_hide']}' : '{t['legend_show']}';
      }});

      var zb = btn('{t['zoom_on']}');
      zb.addEventListener('click', function () {{
        var on = gd.layout.dragmode === false;
        Plotly.relayout(gd, {{'dragmode': on ? 'zoom' : false}});
        zb.textContent = on ? '{t['zoom_off']}' : '{t['zoom_on']}';
        zb.style.color = on ? '#0f8a5f' : '#4b5563';
        zb.style.borderColor = on ? '#0f8a5f' : '#dfe3e9';
      }});

      bar.appendChild(lb); bar.appendChild(zb);
      box.parentNode.insertBefore(bar, box.nextSibling);
    }});
  }}
  var t;
  window.addEventListener('resize', function () {{
    clearTimeout(t); t = setTimeout(function () {{ tune(); addControls(); }}, 200);
  }});
  function init() {{ tune(); addControls(); }}
  if (document.readyState === 'complete') init();
  else window.addEventListener('load', init);
}})();
</script>
</body>
</html>
"""
    out = os.path.join(site_dir, "tools.html") if lang == "ja" \
        else os.path.join(site_dir, "en", "tools.html")
    os.makedirs(os.path.dirname(out) or site_dir, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html_doc)
