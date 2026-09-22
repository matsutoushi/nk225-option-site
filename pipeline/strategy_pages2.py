# -*- coding: utf-8 -*-
"""オプション戦略ページ 第2弾: アイアンコンドル、バタフライ、カバードコール、カレンダースプレッド。

第1弾(strategy_pages.py)と同じ約束で書く。加えて、ここでは
「過去のSQ間で同じ形を組んでいたらどうなったか」を試算する。

試算の前提(本文にも書く):
  - SQの日の日経平均終値で、次のSQまでの限月を組んだとする
  - 値段はその日の日経VIをすべての行使価格に使ったブラック・ショールズ式で付ける
    (実際には下側のプットほどIVが高い=スキューがあるので、実際の値段とは違う)
  - 行使価格は現値からの割合(±5%など)をそのまま使う(実際の行使価格の刻みは無視)
  - 清算は次のSQ値。手数料・証拠金の金利は含まない
過去の清算値段を蓄積していないため、この近似で「形ごとの損益の出方」を見る。
"""
from __future__ import annotations

import math
import os

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from strategies import LARGE, MINI, Chain, Leg, bs, chart_payoff, count_line, example_block
from strategy_pages import RISK_NOTE, _period_note, _pct


# ---------------------------------------------------------------------------
# 過去のSQ間での試算
# ---------------------------------------------------------------------------

def backtest(p: pd.DataFrame, spec: list[tuple]) -> pd.DataFrame:
    """spec = [(kind, 現値に対する倍率, 枚数), ...]。kind は "C"/"P"/"F"。

    各SQ間について、組んだときの受け渡しと、次のSQ値での損益(ポイント)を返す。"""
    rows = []
    for r in p.itertuples():
        if not r.vi:
            continue
        iv, T, S0, S1 = r.vi / 100, r.days / 365, r.s0, r.s1
        pnl, net = 0.0, 0.0
        for kind, m, q in spec:
            K = S0 * m
            if kind == "F":
                pnl += q * (S1 - S0)
                continue
            prem = float(bs(S0, K, T, iv, kind)["price"])
            pay = max(S1 - K, 0) if kind == "C" else max(K - S1, 0)
            pnl += q * (pay - prem)
            net -= q * prem
        rows.append({"start": r.start, "s0": S0, "s1": S1, "ret": r.ret, "vi": r.vi,
                     "net": net, "pnl": pnl, "pnl_pct": pnl / S0})
    return pd.DataFrame(rows)


def bt_summary(bt: pd.DataFrame, label: str) -> str:
    """試算結果を、回数と損益の大きさの両方で書く。"""
    if not len(bt):
        return ""
    n = len(bt)
    win = bt[bt["pnl"] > 0]
    lose = bt[bt["pnl"] <= 0]
    avg_w = win["pnl_pct"].mean() if len(win) else 0.0
    avg_l = lose["pnl_pct"].mean() if len(lose) else 0.0
    worst = bt.loc[bt["pnl_pct"].idxmin()]
    total = bt["pnl_pct"].sum()
    return f"""
<ul>
<li>利益で終わったのは<b>{count_line(len(win), n)}</b></li>
<li>利益の回の平均は日経平均の<b>{avg_w * 100:+.2f}%</b>分、損失の回の平均は<b>{avg_l * 100:+.2f}%</b>分</li>
<li>最も大きな損失は{worst['start'].year}年{worst['start'].month}月に組んだ回で、日経平均の{worst['pnl_pct'] * 100:+.2f}%分
(その間の日経平均は{_pct(worst['ret'])})</li>
<li>{n}回を合計すると日経平均の<b>{total * 100:+.2f}%</b>分</li>
</ul>
<p style="font-size:.9em;color:#666">{label}。損益は「日経平均の何%分か」で表しています
(日経平均6万5千円なら、1%分はラージ1枚で約65万円・ミニ1枚で約6万5千円)。</p>
"""


def bt_verdict(bt: pd.DataFrame) -> str:
    """勝ち数と合計の関係を、結果に合わせて1文で書く(決め打ちの結論を書かない)。"""
    if not len(bt):
        return ""
    n, w = len(bt), int((bt["pnl"] > 0).sum())
    tot = bt["pnl_pct"].sum() * 100
    if abs(tot) < 3:
        how = "ほぼ横ばい"
    elif tot > 0:
        how = "プラス"
    else:
        how = "マイナス"
    return f"この試算では{n}回中{w}回が利益で、{n}回の合計は日経平均の{tot:+.2f}%分({how})でした。"


BT_NOTE = ("試算の前提: SQの日の日経平均終値で次の限月を組み、次のSQ値で清算したとして計算。"
           "値段はその日の日経VIをすべての行使価格に当てはめたブラック・ショールズ式で、"
           "実際の値段(下側ほどIVが高い)とは違います。手数料は含みません")


# ---------------------------------------------------------------------------
# アイアンコンドル
# ---------------------------------------------------------------------------

def page_condor(ch: Chain, p: pd.DataFrame, img, C):
    S = ch.spot
    legs = [ch.leg("P", S * 0.92, 1), ch.leg("P", S * 0.95, -1),
            ch.leg("C", S * 1.05, -1), ch.leg("C", S * 1.08, 1)]
    if None in legs:
        return None
    ex = example_block("アイアンコンドル(売り)", legs, ch,
                       chart_payoff(legs, ch, "st_condor.png", "アイアンコンドル(売り)", img, C))
    n = len(p)
    inside = int((p["ret"].abs() < 0.05).sum()) if n else 0
    outer = int((p["ret"].abs() >= 0.08).sum()) if n else 0
    bt = backtest(p, [("P", 0.92, 1), ("P", 0.95, -1), ("C", 1.05, -1), ("C", 1.08, 1)])
    body = f"""
<h1>アイアンコンドルとは — 日経225オプションの「動かなければ得」を、過去のSQで試算する</h1>
<p>アイアンコンドルは、<b>下のプットと上のコールを1枚ずつ売り、さらに外側を1枚ずつ買って損失に上限を付ける</b>形です。
売りのストラングルに「保険」を付けたものと考えると分かりやすいです。</p>
<ul>
<li>日経平均がSQまでに<b>売った2つの行使価格の間に収まれば</b>、受け取った分が利益になります</li>
<li>外に出ると損失が出ますが、<b>買った外側の行使価格で損失が止まります</b></li>
<li>ストラングルの売りと違い、<b>損失は限定されます</b>。そのぶん受け取りは小さくなります</li>
</ul>
<p>検索では「アイアンコンドル 勝率」「勝てない」という言葉がよく一緒に出てきます。
このページでは、今日の値段で組んだ例に加えて、<b>過去のSQ間で同じ形を組んでいたらどうなったか</b>を試算しています。</p>

<h2>今日の値段で組んだ例</h2>
<p>ルール: 売りは現値から±5%、買いは±8%に最も近い行使価格です。</p>
{ex}

<h2>過去のSQ間では、どれくらい収まったか</h2>
<p>{_period_note(p)}</p>
<ul>
<li>±5%の中に収まったのは<b>{count_line(inside, n)}</b></li>
<li>±8%の外まで動いた(損失が上限に達する)のは<b>{count_line(outer, n)}</b></li>
</ul>

<h2>同じ形を毎回組んでいたら — 「勝率」と損益の大きさ</h2>
{bt_summary(bt, BT_NOTE)}
<p>{bt_verdict(bt)}
アイアンコンドルは<b>勝つ回数が多く、1回の利益は小さく、負けた回の損失が大きい</b>形です。
勝った回数ほどには合計が増えにくく、「勝率が高いのに勝てない」と言われるのはこのためです。
実際の値段では下側のプットのIVが高く(この試算より受け取りが大きい)、
一方で手数料や売買の差がかかるので、結果はこの試算から上下どちらにもずれます。</p>

<h2>どのデータを見るか</h2>
<ul>
<li><a href="nikkei-vi.html">日経VI</a> — 受け取れる額はIVの水準で決まります。IVが高いほど受け取りは大きく、そのぶん大きく動く見込みも高い</li>
<li><a href="./#iv">行使価格別のIV</a> — 下側のプットは上側より高いので、同じ距離でもプット側の受け取りが大きくなります</li>
<li><a href="sq-values.html">SQ値一覧</a> — SQ値は寄り付きで決まるため、前日の終値から離れることがあります</li>
</ul>
<p>関連: <a href="strategies.html">戦略一覧</a> ・ <a href="strategy-straddle-strangle.html">ストラドル・ストラングル</a> ・
<a href="strategy-butterfly.html">バタフライ</a></p>
{RISK_NOTE}
"""
    title = "アイアンコンドルとは｜日経225オプションの勝率と損益を過去のSQで試算・今日の値段で例示"
    desc = ("日経225オプションのアイアンコンドル(売り)を今日の清算値段で組んだ例と、"
            f"過去{n}回のSQ間で同じ形を組んでいた場合の勝率・平均損益・最大損失の試算。"
            "「勝率が高いのに勝てない」と言われる理由をデータで説明します。")
    return title, desc, body


# ---------------------------------------------------------------------------
# バタフライ
# ---------------------------------------------------------------------------

def page_butterfly(ch: Chain, p: pd.DataFrame, img, C):
    S = ch.spot
    k = ch.near(S)
    lo, hi = ch.near(S * 0.975), ch.near(S * 1.025)
    legs = [ch.leg("C", lo, 1), ch.leg("C", k, -2), ch.leg("C", hi, 1)]
    if None in legs:
        return None
    ex = example_block("コール・バタフライ(買い)", legs, ch,
                       chart_payoff(legs, ch, "st_butterfly.png", "コール・バタフライ(買い)", img, C))
    n = len(p)
    near = int((p["ret"].abs() < 0.025).sum()) if n else 0
    bt = backtest(p, [("C", 0.975, 1), ("C", 1.0, -2), ("C", 1.025, 1)])
    body = f"""
<h1>バタフライ・スプレッドとは — 日経225オプションで「ここに着地する」に賭ける形</h1>
<p>バタフライは、<b>真ん中の行使価格を2枚売り、その上下を1枚ずつ買う</b>形です(1:2:1)。
SQ値が<b>真ん中の行使価格ちょうどに着地したとき</b>に利益が最も大きくなり、
上下の外側に外れると、支払った分が損失になります。</p>
<ul>
<li><b>損失も利益も限定されています。</b>最大損失は組んだときの支払いです</li>
<li>支払いが小さく、当たったときの利益は支払いの何倍にもなりえます。ただし当たる範囲は狭くなります</li>
<li>コールだけでもプットだけでも同じ形が作れます。売り買いを逆にした「ショート・バタフライ」は、大きく動けば得になります</li>
<li>真ん中をプットとコールで売り、外側を買う形は「アイアンバタフライ」と呼ばれ、損益の形はほぼ同じです</li>
</ul>

<h2>今日の値段で組んだ例</h2>
<p>ルール: 真ん中は現値に最も近い行使価格、上下は現値から±2.5%に最も近い行使価格のコールです。</p>
{ex}

<h2>過去のSQ間で、真ん中の近くに着地したか</h2>
<p>{_period_note(p)}</p>
<ul>
<li>SQ値が組んだ日から±2.5%の中に着地したのは<b>{count_line(near, n)}</b></li>
</ul>

<h2>同じ形を毎回組んでいたら</h2>
{bt_summary(bt, BT_NOTE)}
<p>{bt_verdict(bt)}
バタフライは<b>外れる回が多く、当たった回の利益が大きい</b>形です。アイアンコンドルとは損益の出方が逆になります。
この試算は、真ん中と外側に同じIV(日経VI)を当てはめているため、実際の値段で組んだ場合とは結果が変わります。
SQの日の着地点を狙うので、<a href="sq-values.html">SQ値が寄り付きで決まる</a>こと
(前日の終値から数百円離れることもある)も考えに入れる必要があります。</p>
<p>関連: <a href="strategies.html">戦略一覧</a> ・ <a href="strategy-iron-condor.html">アイアンコンドル</a></p>
{RISK_NOTE}
"""
    title = "バタフライ・スプレッドとは｜日経225オプションの今日の値段で損益計算・過去のSQで試算"
    desc = ("日経225オプションのコール・バタフライ(1:2:1)を今日の清算値段で組んだ例。"
            f"最大損失・最大利益・損益分岐点と、過去{n}回のSQ間で真ん中の近くに着地した回数、"
            "同じ形を毎回組んでいた場合の試算を毎日更新しています。")
    return title, desc, body


# ---------------------------------------------------------------------------
# カバードコール
# ---------------------------------------------------------------------------

def page_covered_call(ch: Chain, p: pd.DataFrame, img, C):
    S = ch.spot
    fut = Leg("F", round(S), 1, round(S))
    atm = ch.leg("C", S, -1)
    otm = ch.leg("C", S * 1.05, -1)
    if atm is None or otm is None:
        return None
    ex1 = example_block("カバードコール(現値に近いコールを売る)", [fut, atm], ch,
                        chart_payoff([fut, atm], ch, "st_cc_atm.png", "カバードコール(現値のコール)", img, C))
    ex2 = example_block("カバードコール(+5%のコールを売る)", [fut, otm], ch,
                        chart_payoff([fut, otm], ch, "st_cc_otm.png", "カバードコール(+5%のコール)", img, C))
    n = len(p)
    bt_f = backtest(p, [("F", 1.0, 1)])
    bt_a = backtest(p, [("F", 1.0, 1), ("C", 1.0, -1)])
    bt_o = backtest(p, [("F", 1.0, 1), ("C", 1.05, -1)])
    cmp = ""
    if len(bt_f):
        def row(nm, b):
            return (f"<tr><td>{nm}</td><td>{b['pnl_pct'].sum() * 100:+.1f}%</td>"
                    f"<td>{b['pnl_pct'].max() * 100:+.1f}%</td><td>{b['pnl_pct'].min() * 100:+.1f}%</td>"
                    f"<td>{int((b['pnl'] > 0).sum())}回</td></tr>")
        up_big = int((bt_f["ret"] >= 0.05).sum())
        tf, ta, to = (bt_f["pnl_pct"].sum() * 100, bt_a["pnl_pct"].sum() * 100,
                      bt_o["pnl_pct"].sum() * 100)

        def vs(x):
            return "上回り" if x > tf else "下回り"
        cc_line = (f"合計で見ると、先物だけは{tf:+.1f}%分。現値のコールを売る形は{ta:+.1f}%分で先物だけを{vs(ta)}、"
                   f"+5%上のコールを売る形は{to:+.1f}%分で先物だけを{vs(to)}ました。"
                   f"どちらが上になるかは、その期間に大きな上昇が何回あったかで変わります。")
        cmp = f"""
<div class="tbl-wrap"><table>
<thead><tr><th>持ち方</th><th>{len(bt_f)}回の合計</th><th>1回の最大の利益</th><th>1回の最大の損失</th><th>利益の回数</th></tr></thead>
<tbody>
{row("先物だけ", bt_f)}
{row("先物+現値のコールを売る", bt_a)}
{row("先物+5%上のコールを売る", bt_o)}
</tbody></table></div>
<p style="font-size:.9em;color:#666">{BT_NOTE}。損益は日経平均の何%分かで表示。</p>
<p>{cc_line}</p>
<p>コールを売った分、<b>下げた回の損失は受け取った分だけ小さくなり</b>、
<b>大きく上げた回の利益はコールの行使価格で止まります</b>。
この期間はSQ間で+5%以上上がった回が{count_line(up_big, len(bt_f))}あり、その回でコールを売った形は上昇を取り逃しています。</p>
"""
    body = f"""
<h1>カバードコールとは — 日経225先物にコールの売りを重ねると何が変わるか</h1>
<p>カバードコールは、<b>持っている先物(または株・ETF)に対して、コールを売る</b>形です。
コールを売った代金を受け取る代わりに、<b>上昇したときの利益はコールの行使価格で頭打ち</b>になります。</p>
<ul>
<li>横ばいや小幅な上昇なら、受け取った分だけ先物だけより有利です</li>
<li>下落したとき、受け取った分だけ損失が小さくなります。ただし<b>下落の損失そのものは止まりません</b>(プットで保険をかける<a href="strategy-collar.html">カラー</a>との違い)</li>
<li>大きく上昇すると、先物だけを持っていた場合より利益が少なくなります</li>
</ul>
<p>日経225に連動し、毎月コールを売る仕組みの「カバードコール型」のETFや投資信託もあります。
仕組みは同じで、<b>分配の原資になるコールの受け取りと引き換えに、大きな上昇を手放している</b>と考えると中身が分かります。</p>

<h2>今日の値段で組んだ例</h2>
<p>ルール: 先物(ラージ)を現値で1枚買ったとして、現値に最も近いコール、または+5%に最も近いコールを1枚売ります。</p>
{ex1}{ex2}

<h2>過去のSQ間で、毎月コールを売っていたら</h2>
<p>{_period_note(p)}</p>
{cmp}
<p>関連: <a href="strategies.html">戦略一覧</a> ・ <a href="strategy-collar.html">カラー</a></p>
{RISK_NOTE}
"""
    title = "カバードコールとは｜日経225先物+コール売りを今日の値段で計算・過去のSQで先物だけと比較"
    desc = ("日経225のカバードコール(先物買い+コール売り)を今日の清算値段で組んだ例と、"
            f"過去{n}回のSQ間で毎月コールを売っていた場合と先物だけの場合の損益比較。"
            "カバードコール型ETFの仕組みも説明します。")
    return title, desc, body


# ---------------------------------------------------------------------------
# カレンダースプレッド
# ---------------------------------------------------------------------------

def page_calendar(ch: Chain, ch2: Chain, img, C):
    """期近のコールを売り、次の限月の同じ行使価格のコールを買う。

    期近のSQ時点での損益は、期近のコールは本質的価値、次の限月のコールは残り期間の理論値で計算する。"""
    S = ch.spot
    k = ch.near(S)
    near = ch.leg("C", k, -1)
    far = ch2.leg("C", k, 1)
    if near is None or far is None or ch2.expiry == ch.expiry:
        return None
    t_left = max(ch2.T - ch.T, 1 / 365)
    grid = np.linspace(S * 0.88, S * 1.12, 400)

    def pnl_at_near_sq(x):
        near_v = np.maximum(x - k, 0)
        far_v = bs(x, k, t_left, far.iv, "C")["price"]
        return (-(near_v - near.price) + (far_v - far.price))

    pnl = pnl_at_near_sq(grid)
    cost = far.price - near.price
    peak = float(pnl.max())
    # 損益分岐
    be = [float(grid[i]) for i in range(1, len(grid)) if pnl[i - 1] * pnl[i] < 0]
    fig, ax = plt.subplots(figsize=(9, 3.6))
    ax.axhline(0, color=C["ink2"], linewidth=0.8)
    y = pnl * LARGE / 1e4
    ax.plot(grid, y, color=C["accent"], linewidth=2.0, label="期近のSQでの損益(次の限月は理論値)")
    ax.fill_between(grid, y, 0, where=y >= 0, color=C["accent"], alpha=0.10)
    ax.fill_between(grid, y, 0, where=y < 0, color=C["down"], alpha=0.10)
    ax.axvline(S, color=C["ink"], linestyle=":", linewidth=1.0)
    ax.set_xlabel("期近のSQ値(日経平均)", fontsize=9)
    ax.set_ylabel("損益(万円・ラージ1枚あたり)", fontsize=9)
    ax.set_title("カレンダー・スプレッド(期近コール売り+次の限月コール買い)", fontsize=10)
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8)
    fig.tight_layout()
    os.makedirs(img, exist_ok=True)
    fig.savefig(os.path.join(img, "st_calendar.png"), dpi=110)
    plt.close(fig)
    md = f"{ch.date[4:6].lstrip('0')}月{ch.date[6:].lstrip('0')}日"
    theta_near = float(bs(S, k, ch.T, near.iv, "C")["theta"])
    theta_far = float(bs(S, k, ch2.T, far.iv, "C")["theta"])
    body = f"""
<h1>カレンダー・スプレッドとは — 期近と次の限月の「時間の減り方の差」を使う</h1>
<p>カレンダー・スプレッド(タイム・スプレッド)は、<b>同じ行使価格で、期近の限月を売り、先の限月を買う</b>形です。
満期が近いオプションほど、時間の経過による値下がりが速いという性質を使います。</p>
<ul>
<li>期近のSQで日経平均が<b>行使価格の近くにある</b>と、売った期近は価値がほぼゼロになり、買った先の限月には価値が残るので利益が最も大きくなります</li>
<li>大きく上下に外れると、先の限月の価値も期近との差が縮み、損失になります。<b>最大損失はおおよそ組んだときの支払い</b>です</li>
<li>先の限月を買っているので、<b>IVが上がると得、下がると損</b>をしやすい形です</li>
</ul>

<h2>今日の値段で組んだ例</h2>
<div class="latest">
<h3>カレンダー・スプレッドの今日の例({md}の清算値段)</h3>
<p>{ch.label()}の{k:,.0f}円コール 売り1枚(清算値段 {near.price:,.0f}) ＋
{ch2.label()}の{k:,.0f}円コール 買い1枚(清算値段 {far.price:,.0f})</p>
<img src="img/st_calendar.png?v={ch.date}" alt="カレンダー・スプレッドの損益図">
<div class="tbl-wrap"><table><tbody>
<tr><th>組んだときの支払い</th><td><b>{cost:,.0f}ポイント</b>(ラージ {cost * LARGE:,.0f}円・ミニ {cost * MINI:,.0f}円)</td></tr>
<tr><th>期近のSQで最も大きい利益(試算)</th><td>{peak:,.0f}ポイント(ラージ {peak * LARGE:,.0f}円)</td></tr>
<tr><th>損益分岐点(期近のSQ値・試算)</th><td>{"・".join(f"{x:,.0f}円" for x in be) or "-"}</td></tr>
<tr><th>1日あたりの時間価値の減り方</th><td>期近 {abs(theta_near):,.1f}ポイント / 先の限月 {abs(theta_far):,.1f}ポイント</td></tr>
</tbody></table></div>
<p class="latest-note">期近のSQ時点で、先の限月のコールを今日と同じIV({far.iv * 100:.1f}%)で評価した試算です。
IVが変われば損益は変わります。手数料は含みません。</p>
</div>
<p>今日のIVは、期近が{near.iv * 100:.1f}%、先の限月が{far.iv * 100:.1f}%です。
期近のIVのほうが高いときは、売る側が割高になるので、この形には有利な条件になります
(逆に先の限月のほうが高いと、買う側が割高です)。</p>

<h2>ほかの戦略との違い</h2>
<p>ほかの戦略は1つの限月の中で組みますが、カレンダーは<b>2つの限月にまたがる</b>ため、
満期の損益だけでは形が決まりません。期近のSQの時点で、先の限月にどれだけ価値が残っているか
(残り期間とIV)に左右されます。そのため、このページでは過去のSQ間での試算は行っていません。</p>
<p>関連: <a href="strategies.html">戦略一覧</a> ・ <a href="strategy-butterfly.html">バタフライ</a> ・
<a href="nikkei-vi.html">日経VI</a></p>
{RISK_NOTE}
"""
    title = "カレンダースプレッドとは｜日経225オプションの期近売り・先の限月買いを今日の値段で計算"
    desc = ("日経225オプションのカレンダー・スプレッド(期近コール売り+次の限月コール買い)を今日の清算値段で組んだ例。"
            "支払い・期近のSQでの損益の試算・時間価値の減り方の差、期近と先の限月のIVを毎日更新しています。")
    return title, desc, body
