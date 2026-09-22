# -*- coding: utf-8 -*-
"""オプション戦略ページの本文。計算は strategies.py。

書き方の約束(strategies.py と同じ):
  - 売買を勧めない。「勝てる」「稼げる」は使わない
  - 損失が限定されない形には必ずそう書く
  - 数字は毎回データから計算する。本文に手で数字を書かない
"""
from __future__ import annotations

import math

import pandas as pd

from strategies import (LARGE, MINI, Chain, Leg, analyze, chart_payoff, count_line,
                        example_block, greeks, sq_periods)

RISK_NOTE = """
<h2>始める前に</h2>
<ul>
<li><b>売りを含む戦略は証拠金が必要です。</b>必要額は取引所の証拠金制度(VaR方式)で日々変わり、
相場が荒れると急に増えることがあります</li>
<li><b>清算値段は理論値です。</b>実際には売値と買値の差(スプレッド)があり、
遠い行使価格ほど取引が少なく、思った値段で約定しないことがあります</li>
<li><b>SQをまたぐと自動で清算されます。</b>SQ値は寄り付きの値段から決まり、
前日の終値から大きく離れることがあります(<a href="sq-values.html">幻のSQ</a>)</li>
<li>このページは仕組みとデータの説明で、特定の取引を勧めるものではありません。</li>
</ul>
"""


def _pct(x: float) -> str:
    return f"{x * 100:+.1f}%"


def _period_note(p: pd.DataFrame) -> str:
    if not len(p):
        return ""
    a, b = p["start"].min(), p["end"].max()
    return (f"{a.year}年{a.month}月から{b.year}年{b.month}月までの<b>{len(p)}回</b>のSQ間"
            f"(SQの日の日経平均終値 → 次のSQ値)で数えています。")


def page_vertical(ch: Chain, p: pd.DataFrame, img, C):
    S = ch.spot
    ex = {
        "bull_call": [ch.leg("C", S, 1), ch.leg("C", S * 1.05, -1)],
        "bear_put": [ch.leg("P", S, 1), ch.leg("P", S * 0.95, -1)],
        "bear_call": [ch.leg("C", S * 1.05, -1), ch.leg("C", S * 1.08, 1)],
        "bull_put": [ch.leg("P", S * 0.95, -1), ch.leg("P", S * 0.92, 1)],
    }
    if any(None in v for v in ex.values()):
        return None
    names = (("bull_call", "ブル・コール・スプレッド(買い)"),
             ("bear_put", "ベア・プット・スプレッド(買い)"),
             ("bear_call", "ベア・コール・スプレッド(売り)"),
             ("bull_put", "ブル・プット・スプレッド(売り)"))
    blocks = {k: example_block(n, ex[k], ch, chart_payoff(ex[k], ch, f"st_{k}.png", n, img, C))
              for k, n in names}
    n = len(p)
    up5 = int((p["ret"] >= 0.05).sum()) if n else 0
    dn5 = int((p["ret"] <= -0.05).sum()) if n else 0
    in5 = n - up5 - dn5
    body = f"""
<h1>コールスプレッド・プットスプレッドとは — 日経225オプションの4つの形を今日の値段で比べる</h1>
<p>同じ種類のオプションを<b>行使価格を変えて1枚ずつ買いと売りで組む</b>のがスプレッド(バーティカル・スプレッド)です。
買うだけに比べて支払いを減らせる代わりに、利益にも上限ができます。<b>最大損失と最大利益がどちらも決まっている</b>のが特徴です。</p>

<h2>4つの形</h2>
<div class="tbl-wrap"><table>
<thead><tr><th>名前</th><th>組み方</th><th>見通し</th><th>組んだとき</th></tr></thead>
<tbody>
<tr><td>ブル・コール・スプレッド</td><td>低いコールを買い、高いコールを売る</td><td>上昇</td><td>支払い</td></tr>
<tr><td>ベア・プット・スプレッド</td><td>高いプットを買い、低いプットを売る</td><td>下落</td><td>支払い</td></tr>
<tr><td>ベア・コール・スプレッド</td><td>低いコールを売り、高いコールを買う</td><td>上がらない</td><td>受け取り</td></tr>
<tr><td>ブル・プット・スプレッド</td><td>高いプットを売り、低いプットを買う</td><td>下がらない</td><td>受け取り</td></tr>
</tbody></table></div>
<p>「買い」の2つ(デビット・スプレッド)は、思った方向に動けば利益が出ます。
「売り」の2つ(クレジット・スプレッド)は、<b>動かないか逆に動けば</b>受け取った分が残ります。
売りは受け取りから始まるぶん、外れたときの損失が受け取り額より大きくなるのが普通です。</p>

<h2>今日の値段で組んだ例</h2>
<p>ルール: 期近で残り10日以上の限月を使い、買いのスプレッドは「現値に最も近い行使価格」と「±5%」、
売りのスプレッドは「±5%」と「±8%」に最も近い行使価格の組み合わせにしています。</p>
{blocks['bull_call']}{blocks['bear_put']}{blocks['bear_call']}{blocks['bull_put']}

<h2>過去のSQ間で、±5%はどれくらい超えたか</h2>
<p>{_period_note(p)}</p>
<ul>
<li>+5%以上上がったのは<b>{count_line(up5, n)}</b></li>
<li>−5%以上下がったのは<b>{count_line(dn5, n)}</b></li>
<li>±5%の中に収まったのは<b>{count_line(in5, n)}</b></li>
</ul>
<p>買いのスプレッドで最大利益に届くには、SQまでに売った側の行使価格(±5%)を超える必要があります。
売りのスプレッドは±5%の外に出なければ受け取った分が残りますが、外れたときは損失が受け取りを上回ります。
回数だけで有利・不利は決まりません。<b>1回あたりの損益の大きさ</b>と合わせて見る必要があります。</p>

<h2>どのデータを見るか</h2>
<ul>
<li><a href="./#iv">行使価格別のIV</a> — 売る側と買う側のIVの差。下側のプットは上側のコールより高いのが普通です</li>
<li><a href="./#oitable">建玉一覧</a> — 行使価格ごとの建玉。取引が少ない行使価格は約定しにくくなります</li>
<li><a href="nikkei-vi.html">日経VI</a> — 全体のIVの水準</li>
</ul>
<p>関連: <a href="strategies.html">戦略一覧</a> ・ <a href="strategy-ratio-spread.html">レシオ・スプレッド</a></p>
{RISK_NOTE}
"""
    title = "コールスプレッド・プットスプレッドとは｜日経225オプションの買いと売りを今日の値段で比較"
    desc = ("日経225オプションのブル・コール、ベア・プット、ベア・コール、ブル・プットの4つのスプレッドを、"
            "今日の清算値段で組んだ場合の受け渡し・最大損益・損益分岐点で毎日比較。"
            f"過去{n}回のSQ間で±5%を超えた回数も数えています。")
    return title, desc, body


def page_ratio(ch: Chain, p: pd.DataFrame, img, C):
    S = ch.spot
    put_r = [ch.leg("P", S, 1), ch.leg("P", S * 0.95, -2)]
    call_r = [ch.leg("C", S, 1), ch.leg("C", S * 1.05, -2)]
    if None in put_r or None in call_r:
        return None
    ap, ac = analyze(put_r, S), analyze(call_r, S)
    bp = chart_payoff(put_r, ch, "st_put_ratio.png", "プット・レシオ・スプレッド(1:2)", img, C)
    bc = chart_payoff(call_r, ch, "st_call_ratio.png", "コール・レシオ・スプレッド(1:2)", img, C)
    n = len(p)
    lo_be = min(ap["breakevens"]) if ap["breakevens"] else None
    hi_be = max(ac["breakevens"]) if ac["breakevens"] else None
    lo_pct = lo_be / S - 1 if lo_be else None
    hi_pct = hi_be / S - 1 if hi_be else None
    lo_cnt = int((p["ret"] <= lo_pct).sum()) if n and lo_pct is not None else 0
    hi_cnt = int((p["ret"] >= hi_pct).sum()) if n and hi_pct is not None else 0
    worst = float(p["ret"].min()) if n else None
    body = f"""
<h1>プット・レシオ・スプレッド、コール・レシオ・スプレッドとは — 今日の値段と過去のSQで見る</h1>
<p>レシオ・スプレッドは、<b>1枚買って、それより遠い行使価格を2枚売る</b>形です(1:2が代表的)。
売る枚数が多いぶん、組んだときの支払いが小さいか受け取りになりますが、
<b>売った側の外に大きく動くと、損失が限定されません。</b></p>

<h2>プット・レシオ・スプレッド</h2>
<p>現値近くのプットを1枚買い、下のプットを2枚売ります。
緩やかな下落で売ったプットの行使価格の近くに着地すると利益が最も大きくなり、
<b>大きく下落すると、売った2枚のうち1枚分が裸の売りと同じになり損失が膨らみます。</b></p>
{example_block("プット・レシオ・スプレッド(1:2)", put_r, ch, bp)}
<p>今日のIVは、買ったプット({put_r[0].strike:,.0f}円)が{put_r[0].iv * 100:.1f}%、
売ったプット({put_r[1].strike:,.0f}円)が{put_r[1].iv * 100:.1f}%です。
日経225は下側のIVが高い形が普通で、遠いプットを売るこの形は、その高いIVの側を売ることになります。
<a href="./#iv">行使価格別のIV</a>で毎日確認できます。</p>

<h2>コール・レシオ・スプレッド</h2>
<p>現値近くのコールを1枚買い、上のコールを2枚売ります。
緩やかな上昇で売ったコールの近くに着地すると利益が最も大きく、<b>急上昇すると損失が限定されません。</b>
上側はIVが低いことが多く、同じ枚数構成でもプット側より受け取りが小さくなりやすいのが特徴です
(今日は買い{call_r[0].iv * 100:.1f}%・売り{call_r[1].iv * 100:.1f}%)。</p>
{example_block("コール・レシオ・スプレッド(1:2)", call_r, ch, bc)}

<h2>損失側の分岐点を、過去のSQ間で超えた回数</h2>
<p>{_period_note(p)}今日の例の損益分岐点を現値からの変化率に直し、それを超えた回数を数えました。</p>
<ul>
<li>プット・レシオの下側の分岐点は{f"{lo_be:,.0f}円(現値から{_pct(lo_pct)})" if lo_be else "なし"}。
過去にこれ以上下がったのは<b>{count_line(lo_cnt, n)}</b></li>
<li>コール・レシオの上側の分岐点は{f"{hi_be:,.0f}円(現値から{_pct(hi_pct)})" if hi_be else "なし"}。
過去にこれ以上上がったのは<b>{count_line(hi_cnt, n)}</b></li>
<li>この期間のSQ間で最も大きく下げたのは{_pct(worst) if worst is not None else "-"}です</li>
</ul>
<p>回数が少なくても、超えたときの損失は大きくなります。
レシオの売りを持つ場合は、どこで手じまうかを先に決めておく必要があります。</p>
<p>関連: <a href="strategies.html">戦略一覧</a> ・ <a href="strategy-vertical-spread.html">コール/プットスプレッド</a></p>
{RISK_NOTE}
"""
    title = "プットレシオ・コールレシオスプレッドとは｜日経225オプションの今日の値段で損益計算"
    desc = ("プット・レシオ・スプレッドとコール・レシオ・スプレッド(1:2)を日経225オプションの今日の清算値段で組んだ例。"
            "受け渡し・最大利益・損益分岐点、売る側のIV、過去のSQ間で損失側の分岐点を超えた回数を毎日更新。")
    return title, desc, body


def page_straddle(ch: Chain, p: pd.DataFrame, img, C):
    S = ch.spot
    k = ch.near(S)
    ls = [ch.leg("C", k, 1), ch.leg("P", k, 1)]
    ss = [ch.leg("C", k, -1), ch.leg("P", k, -1)]
    lg = [ch.leg("C", S * 1.05, 1), ch.leg("P", S * 0.95, 1)]
    sg = [ch.leg("C", S * 1.05, -1), ch.leg("P", S * 0.95, -1)]
    if any(None in x for x in (ls, ss, lg, sg)):
        return None
    als, alg = analyze(ls, S), analyze(lg, S)
    width_s = (-als["net"]) / S
    width_g = None
    if len(alg["breakevens"]) == 2:
        width_g = (alg["breakevens"][1] - alg["breakevens"][0]) / 2 / S
    n = len(p)
    over_s = int((p["ret"].abs() >= width_s).sum()) if n else 0
    over_g = int((p["ret"].abs() >= width_g).sum()) if n and width_g else 0
    pv = p.dropna(subset=["exp_move"]) if n else p
    over_vi = int(((pv["s1"] - pv["s0"]).abs() >= pv["exp_move"]).sum()) if len(pv) else 0
    blocks = "".join(
        example_block(nm, legs, ch, chart_payoff(legs, ch, f"st_{fn}.png", nm, img, C))
        for nm, legs, fn in (("ストラドルの買い", ls, "long_straddle"),
                             ("ストラドルの売り", ss, "short_straddle"),
                             ("ストラングルの買い", lg, "long_strangle"),
                             ("ストラングルの売り", sg, "short_strangle")))
    g_line = (f"<li>今日のストラングルの損益分岐までの距離は<b>±{width_g * 100:.1f}%</b>。"
              f"過去にそれ以上動いたのは<b>{count_line(over_g, n)}</b></li>") if width_g else ""
    body = f"""
<h1>ストラドル・ストラングルとは — 日経225オプションの買いと売りを、過去のSQで数える</h1>
<p>コールとプットを<b>同時に</b>買う(または売る)形です。方向ではなく<b>動くか・動かないか</b>に賭けます。</p>
<div class="tbl-wrap"><table>
<thead><tr><th>形</th><th>組み方</th><th>利益になるのは</th><th>損失</th></tr></thead>
<tbody>
<tr><td>ストラドルの買い</td><td>同じ行使価格のコールとプットを買う</td><td>どちらかに大きく動いたとき</td><td>支払った分まで</td></tr>
<tr><td>ストラドルの売り</td><td>同じ行使価格のコールとプットを売る</td><td>ほとんど動かなかったとき</td><td><b>限定されない</b></td></tr>
<tr><td>ストラングルの買い</td><td>上のコールと下のプットを買う</td><td>ストラドル以上に大きく動いたとき</td><td>支払った分まで</td></tr>
<tr><td>ストラングルの売り</td><td>上のコールと下のプットを売る</td><td>2つの行使価格の間に収まったとき</td><td><b>限定されない</b></td></tr>
</tbody></table></div>
<p>ストラングルはストラドルより支払い(受け取り)が小さく、そのぶん利益が出るまでの距離が遠くなります。</p>

<h2>今日の値段で組んだ例</h2>
<p>ルール: ストラドルは現値に最も近い行使価格、ストラングルは現値から±5%に最も近い行使価格です。</p>
{blocks}

<h2>過去のSQ間で、どれくらい動いたか</h2>
<p>{_period_note(p)}</p>
<ul>
<li>今日のストラドルの損益分岐までの距離は現値から<b>±{width_s * 100:.1f}%</b>。
過去にそれ以上動いたのは<b>{count_line(over_s, n)}</b></li>
{g_line}
<li>SQの日の<a href="nikkei-vi.html">日経VI</a>から計算した「次のSQまでの想定の値幅(1標準偏差)」を実際の動きが超えたのは
<b>{count_line(over_vi, len(pv))}</b></li>
</ul>
<p>正規分布どおりなら、1標準偏差を超えるのは約3割です。
日経VIは実際の値動きより高めに出る傾向があり(<a href="nikkei-vi.html">日経VIのページ</a>で実測)、
その差が売り手の取り分になります。ただし、超えた回の動きは大きく、
<b>売りは少ない回数の大きな損失で、それまでの受け取りを失う</b>形になりやすい点に注意が必要です。</p>

<h2>買いの場合: 時間との競争</h2>
<p>ストラドルの買いは、動かない日が続くと時間価値が毎日減ります(今日の例のセータを参照)。
動きを待つ代わりに、動いた分をこまめに先物で利益に変える方法が
<a href="strategy-gamma-trading.html">ガンマトレード(デルタヘッジ)</a>です。</p>
<p>関連: <a href="strategies.html">戦略一覧</a></p>
{RISK_NOTE}
"""
    title = "ストラドル・ストラングルとは｜日経225オプションの買いと売り、過去のSQで数えた結果"
    desc = ("日経225オプションのストラドル・ストラングルの買いと売りを、今日の清算値段で組んだ例で比較。"
            f"損益分岐までの距離と、過去{n}回のSQ間でそれを超えた回数、日経VIの想定幅を超えた回数を毎日更新。")
    return title, desc, body


def page_collar(ch: Chain, p: pd.DataFrame, img, C):
    S = ch.spot
    fut = Leg("F", round(S), 1, round(S))
    put = ch.leg("P", S * 0.95, 1)
    call = ch.leg("C", S * 1.05, -1)
    if put is None or call is None:
        return None
    collar = [fut, put, call]
    zc_call = ch.call_matching(put.price, S)
    bc = chart_payoff(collar, ch, "st_collar.png", "カラー(先物買い+プット買い+コール売り)", img, C)
    zb = ""
    if zc_call:
        zero = [fut, put, zc_call]
        zi = chart_payoff(zero, ch, "st_zero_collar.png", "ゼロコストカラー", img, C)
        zb = example_block("ゼロコストカラー", zero, ch, zi,
                           "コールは、買ったプットと清算値段が最も近い行使価格を選んでいます。")
    n = len(p)
    dn = int((p["ret"] <= -0.05).sum()) if n else 0
    up = int((p["ret"] >= 0.05).sum()) if n else 0
    worst = float(p["ret"].min()) if n else None
    body = f"""
<h1>カラー取引・ゼロコストカラーとは — 日経225先物に「下の保険」と「上の上限」を付ける</h1>
<p>カラーは、持っている先物(または株)に対して<b>下のプットを買い、上のコールを売る</b>組み合わせです。
プットで下落の損失に床を作り、その保険料をコールを売った受け取りでまかないます。
代わりに、上昇したときの利益はコールの行使価格で頭打ちになります。</p>
<p>コールの受け取りとプットの支払いがちょうど釣り合うように組んだものを<b>ゼロコストカラー</b>と呼びます。
保険料の持ち出しはありませんが、<b>上昇の利益と引き換え</b>になっている点は同じです。</p>

<h2>今日の値段で組んだ例</h2>
<p>ルール: 先物を現値で1枚買ったとして、プットは現値から−5%、コールは+5%に最も近い行使価格です。
先物は日経225先物(ラージ)を想定し、オプションもラージ1枚で揃えています
(先物ラージ1枚とオプションのラージ1枚は、どちらも指数×1,000円)。</p>
{example_block("カラー", collar, ch, bc)}
{zb}

<h2>過去のSQ間で、床と天井に届いたか</h2>
<p>{_period_note(p)}</p>
<ul>
<li>−5%以上下がって<b>プットの床が効いた</b>のは{count_line(dn, n)}</li>
<li>+5%以上上がって<b>コールの天井で利益が止まった</b>のは{count_line(up, n)}</li>
<li>先物だけを持っていた場合、SQ間の最大の下落は{_pct(worst) if worst is not None else "-"}でした</li>
</ul>
<p>床が効いた回数と天井に当たった回数の両方を見ると、カラーが何と何を交換しているかが分かります。</p>
<p>関連: <a href="strategies.html">戦略一覧</a></p>
{RISK_NOTE}
"""
    title = "カラー取引・ゼロコストカラーとは｜日経225先物+オプションの例を今日の値段で毎日計算"
    desc = ("カラー取引(先物買い+プット買い+コール売り)とゼロコストカラーを日経225の今日の清算値段で組んだ例。"
            f"損益の床と天井、過去{n}回のSQ間でそれぞれに届いた回数を毎日更新しています。")
    return title, desc, body


def page_gamma(ch: Chain, p: pd.DataFrame, img, C, n225, vi_stats):
    """コール1枚+先物でのデルタヘッジを、2日間の具体例で見せる。

    専門用語(ガンマ・セータ)は例のあとで出す。先に「何が起きるか」を数字で追えるようにする。
    先物は日経225mini(ラージの1/10)を使う。オプションのラージ1枚のデルタ0.5は、miniの5枚に当たる。
    """
    from strategies import bs
    S0 = ch.spot
    K = ch.near(S0)
    lg = ch.leg("C", K, 1)
    if lg is None:
        return None
    iv, T0 = lg.iv, ch.T
    move = 1000.0
    day = 1 / 365

    def c(S, T):
        b = bs(S, K, T, iv, "C")
        return float(b["price"]), float(b["delta"])

    C0, d0 = c(S0, T0)
    S1, S2 = S0 + move, S0
    C1, d1 = c(S1, T0 - day)
    C2, d2 = c(S2, T0 - 2 * day)
    n0, n1, n2 = round(d0 * 10), round(d1 * 10), round(d2 * 10)   # miniの売り枚数
    fut1 = -n0 * (S1 - S0) * MINI
    fut2 = -n1 * (S2 - S1) * MINI
    opt = (C2 - C0) * LARGE
    total = opt + fut1 + fut2
    # 動かなかった場合
    Cq, _ = c(S0, T0 - 2 * day)
    quiet = (Cq - C0) * LARGE
    # ヘッジしなかった場合(往復して元に戻る)
    nohedge = opt

    def y(x):
        return f"{x:+,.0f}円"

    table = f"""
<div class="tbl-wrap"><table>
<thead><tr><th></th><th>日経平均</th><th>コールの値段</th><th>コールのデルタ</th><th>その日の操作</th><th>先物の持ち</th></tr></thead>
<tbody>
<tr><td>1日目(買った日)</td><td>{S0:,.0f}円</td><td>{C0:,.0f}</td><td>{d0:.2f}</td>
<td>コールを1枚買い、miniを<b>{n0}枚売る</b></td><td>mini {n0}枚売り</td></tr>
<tr><td>2日目</td><td>{S1:,.0f}円(+{move:,.0f})</td><td>{C1:,.0f}</td><td>{d1:.2f}</td>
<td>デルタが増えたので、miniを<b>さらに{n1 - n0}枚売る</b>(高いところで売る)</td><td>mini {n1}枚売り</td></tr>
<tr><td>3日目</td><td>{S2:,.0f}円(−{move:,.0f})</td><td>{C2:,.0f}</td><td>{d2:.2f}</td>
<td>デルタが戻ったので、miniを<b>{n1 - n2}枚買い戻す</b>(安いところで買う)</td><td>mini {n2}枚売り</td></tr>
</tbody></table></div>
"""
    result = f"""
<div class="tbl-wrap"><table>
<thead><tr><th>2日後(日経平均が元の{S0:,.0f}円に戻ったとき)</th><th>損益</th></tr></thead>
<tbody>
<tr><td>コール(1枚・ラージ)</td><td>{y(opt)}</td></tr>
<tr><td>先物(mini)の売買</td><td>{y(fut1 + fut2)}</td></tr>
<tr><td><b>合計</b></td><td><b>{y(total)}</b></td></tr>
</tbody></table></div>
"""
    recent = ""
    if n225 is not None:
        d = n225["Close"].diff().abs().dropna().tail(60)
        big = int((d >= move).sum())
        recent = (f"<p>参考までに、直近{len(d)}営業日で日経平均の終値が前日から{move:,.0f}円以上動いた日は"
                  f"<b>{len(d)}日中{big}日</b>、1日の平均の変化は{float(d.mean()):,.0f}円でした。</p>")
    vi_block = ""
    if vi_stats and vi_stats.get("rv_n"):
        vi_block = f"""
<h2>結局、どちらが得なのか — 「デルタヘッジは儲からない」と言われる理由</h2>
<p>上の例で分かるとおり、コールを買ってデルタヘッジしたときの損益は
<b>「実際にどれだけ動いたか」</b>と<b>「コールを買った値段(IV)が見込んでいた動きの大きさ」</b>の比べ合いで決まります。
IVが見込んだより大きく動けば買った側、小さければ売った側が得をします。</p>
<p>当サイトの<a href="nikkei-vi.html">日経VIのページ</a>で、各日の日経VIとその後20営業日に実際に動いた大きさを比べると、
<b>{vi_stats['rv_n']}営業日のうち{vi_stats['vi_gt_rv']}日で、日経VIのほうが大きく</b>、差は平均{vi_stats['vi_rv_gap']:.1f}ポイントでした。
オプションは平均すると、実際の動きより少し高い値段がついていたことになります。
買ってデルタヘッジする側が「儲からない」と言われるのはこのためです。</p>
<p>ただし、実際の動きがIVを大きく上回った時期もあり、そこでは買ってヘッジした側が利益を上げています。
売ってヘッジする側は平均では有利でも、急変の局面で大きな損失を抱えます。
<b>どちらかが常に有利ということはありません。</b></p>
"""
    img_path = chart_payoff([lg], ch, "st_gamma.png", f"{K:,.0f}円コールの買い(ヘッジ前)", img, C)
    body = f"""
<h1>デルタヘッジとは — コールを買って先物で打ち消すと何が起きるか(ガンマトレード)</h1>
<p>コールを買うと、日経平均が上がれば得、下がれば損をします。
この<b>「上がるか下がるか」のリスクだけを、先物の売りで打ち消す</b>のがデルタヘッジです。
打ち消したあとに残るのは、<b>「どれだけ動くか」</b>による損益です。
これを狙う取引をガンマトレードと呼びます。</p>

<h2>まず、デルタとは</h2>
<p>デルタは「日経平均が1円動いたとき、コールの値段が何円動くか」です。
現値に近いコールのデルタはだいたい0.5で、日経平均が100円上がるとコールは約50円上がります。
つまり<b>コール1枚を持つのは、先物を半分持っているのと同じ</b>です。</p>
<p>そこで、先物を半分だけ売れば、上がっても下がっても損益がほぼ動かない状態になります。
日経225オプション(ラージ)1枚の半分は、日経225mini(ラージの10分の1)の5枚に当たります。</p>

<h2>例: コールを1枚買って、2日間デルタヘッジする</h2>
<p>{ch.label()}の{K:,.0f}円コールを使います。今日の清算値段は{lg.price:,.0f}で、日経平均は{S0:,.0f}円です
(この値段から逆算したIVは{iv * 100:.1f}%)。
日経平均が1日目から2日目に{move:,.0f}円上がり、3日目に元に戻ったとします(IVは変わらないと仮定)。</p>
{table}
<p>ポイントは2日目と3日目の操作です。<b>上がったときにデルタが増える</b>ので先物を売り足し、
<b>戻ったときにデルタが減る</b>ので買い戻します。
ヘッジを続けるだけで、自然に<b>「高く売って安く買う」</b>ことになります。</p>
{result}
<p>日経平均は元の値段に戻ったのに、先物の売買で{y(fut1 + fut2)}が残りました。
一方、コール自体は2日分の時間が過ぎたぶん{y(opt)}になっています。
<b>ヘッジをしなかった場合</b>は、上がって戻っても、2日間まったく動かなかった場合と同じ{y(nohedge)}で終わります。
ヘッジしたことで、動いた分が{y(fut1 + fut2)}の利益として残ったわけです。</p>
<p>つまりデルタヘッジしたコールの買いは、<b>方向には関係なく「動けば得、動かなければ損」</b>という形に変わります。
下がって戻った場合も、下がったところで買い戻し、戻ったところで売り直すので、同じように利益が残ります。</p>
{recent}

<h2>この性質の名前: ガンマとセータ</h2>
<ul>
<li><b>ガンマ</b> — 日経平均が動いたときに、デルタがどれだけ変わるか。
上の例で、2日目にデルタが{d0:.2f}から{d1:.2f}に増えたのがガンマの働きです。
ガンマがあるから、ヘッジするたびに「高く売って安く買う」が起きます</li>
<li><b>セータ</b> — 時間が1日過ぎるごとに、オプションの値段がどれだけ減るか。
動かなかった場合の{y(quiet)}がこれです</li>
</ul>
<p>デルタヘッジしたコールの買いは、<b>デルタ(方向)を消して、ガンマ(動きの大きさ)を取り、その代わりにセータ(時間)を払う</b>取引です。
1回の動きで残る利益は、おおよそ「½ × ガンマ × 動いた幅の2乗」で、動いた幅が2倍になると利益は4倍になります。</p>

<h2>コールを売ってデルタヘッジすると: すべて逆になる</h2>
<p>コールを1枚売り、先物(mini)を{n0}枚買ってデルタを打ち消すと、損益はちょうど反対になります。</p>
<ul>
<li>上がるとデルタのずれを埋めるために先物を買い足し、戻ると売る。<b>高く買って安く売る</b>ことになります</li>
<li>上の例と同じ動きなら、合計は{y(-total)}</li>
<li>2日間動かなければ、時間が過ぎた分の{y(-quiet)}を受け取れます</li>
</ul>
<p>つまり<b>「動かなければ得、大きく動けば損」</b>です。証券会社などのディーラーはこの側に立つことが多く、
そのヘッジの売買が相場の動きを大きくすることがあります。
当サイトでは、その向きを<a href="guide-gex.html">ガンマエクスポージャー</a>として毎日推定しています。</p>
{vi_block}
<h2>実際にやるときの論点</h2>
<ul>
<li><b>いつヘッジし直すか</b> — 一定の時間ごと、デルタが一定量ずれたとき、などのやり方があります。
こまめにするほど取りこぼしは減りますが、先物の手数料と売買の差(スプレッド)が増えます</li>
<li><b>先物の単位</b> — ラージのオプション1枚に対し、miniなら10分の1単位、マイクロなら100分の1単位で合わせられます</li>
<li><b>IVの変化</b> — 持っている間にIVが下がると、ヘッジとは別にコールの値段が下がります。上の例ではIVを一定にしています</li>
<li><b>コールとプットを両方買う形</b> — 現値のコールとプットを1枚ずつ買う(<a href="strategy-straddle-strangle.html">ストラドル</a>)と、
最初からデルタがほぼゼロなので、先物なしで同じ性質から始められます</li>
</ul>
<img src="{img_path}?v={ch.date}" alt="コールの買いの損益図">
<p class="latest-note">上の図は、ヘッジをしない場合のコールの買いの損益です。
計算はブラック・ショールズ式で、IV・金利は一定、手数料は含みません。</p>
<p>関連: <a href="strategies.html">戦略一覧</a> ・ <a href="strategy-straddle-strangle.html">ストラドル・ストラングル</a></p>
{RISK_NOTE}
"""
    title = "デルタヘッジとは｜コールを買って先物で打ち消すと何が起きるか(ガンマトレード・日経225)"
    desc = ("日経225オプションのコールを1枚買い、miniで2日間デルタヘッジした場合の損益を今日の値段で計算。"
            "方向のリスクを消すと「動けば得、動かなければ損」になる仕組みと、コールを売った場合の逆の形、"
            "「デルタヘッジは儲からない」と言われる理由を実測で説明します。")
    return title, desc, body


PAGES = [
    ("strategy-vertical-spread.html", "コール/プットスプレッド", "方向(上昇・下落)", "限定", "限定"),
    ("strategy-ratio-spread.html", "プット/コールレシオ", "緩やかな方向", "<b>限定されない</b>", "限定"),
    ("strategy-straddle-strangle.html", "ストラドル/ストラングル", "動く・動かない",
     "買い:限定 / 売り:<b>限定されない</b>", "買い:限定されない / 売り:限定"),
    ("strategy-collar.html", "カラー/ゼロコストカラー", "先物の保有+下の保険", "限定", "限定"),
    ("strategy-gamma-trading.html", "デルタヘッジ(ガンマトレード)", "値動きの大きさ",
     "買い:支払い分+ヘッジの費用", "実際の値動き次第"),
]


def page_hub(ch: Chain, built: dict):
    rows = "".join(
        f"<tr><td><a href='{f}'><b>{nm}</b></a></td><td>{view}</td><td>{loss}</td><td>{prof}</td></tr>"
        for f, nm, view, loss, prof in PAGES if f in built)
    body = f"""
<h1>日経225オプションの戦略一覧 — 今日の清算値段で損益を毎日計算</h1>
<p>オプションは組み合わせ方で、<b>方向・値動きの大きさ・時間の経過・IVの変化</b>のどれに賭けるかを変えられます。
このページでは代表的な戦略を整理し、それぞれのページで
<b>今日のJPXの清算値段で組んだ場合の受け渡し・最大損益・損益分岐点</b>と、
<b>過去のSQ間の値動きで数えた事実</b>を毎営業日更新しています。</p>

<h2>戦略の一覧</h2>
<div class="tbl-wrap"><table>
<thead><tr><th>戦略</th><th>何に賭けるか</th><th>損失</th><th>利益</th></tr></thead>
<tbody>{rows}</tbody></table></div>

<h2>4つの軸で考える</h2>
<ul>
<li><b>方向(デルタ)</b> — 上がれば得か、下がれば得か。スプレッドやレシオはここを狙います</li>
<li><b>値動きの大きさ(ガンマ)</b> — 大きく動けば得か、動かなければ得か。ストラドル・ストラングル、ガンマトレード</li>
<li><b>時間(セータ)</b> — 買いは時間とともに価値が減り、売りは時間が味方になります</li>
<li><b>IV(ベガ)</b> — 組んだ後にIVが上がるか下がるか。<a href="nikkei-vi.html">日経VI</a>と<a href="./#iv">行使価格別のIV</a>で確認できます</li>
</ul>
<p>買いと売りは表裏です。オプションを売る側は、買う側が払った保険料を受け取る代わりに、
大きく動いたときの損失を引き受けます。<b>損失が限定されない形があること</b>を、各ページで必ず示しています。</p>

<h2>各ページの「今日の例」の作り方</h2>
<p>特定の行使価格を勧めないように、行使価格は決まったルール(現値に最も近い行使価格、現値から±5%など)で自動的に選んでいます。
使っているのは{ch.label()}の清算値段です。清算値段は取引所が算出した理論上の値段で、実際の約定値段とはずれます。</p>
<p>オプションの基本的な仕組みは<a href="guide-start.html">日経225オプションを始めるには</a>と<a href="glossary.html">用語集</a>にまとめています。</p>
{RISK_NOTE}
"""
    title = "日経225オプションの戦略一覧｜今日の清算値段で損益を毎日計算"
    desc = ("日経225オプションの代表的な戦略(スプレッド、レシオ、ストラドル・ストラングル、カラー、ガンマトレード)を一覧に。"
            "各戦略を今日のJPX清算値段で組んだ場合の損益と、過去のSQ間の値動きで数えた事実を毎日更新しています。")
    return title, desc, body


def build_all(settle: dict, sq_hist: pd.DataFrame, n225, vi, vi_stats, img_dir: str, colors: dict) -> dict:
    """全ページの {fname: (title, desc, body)}。作れなかったページは含めない。"""
    ch = Chain(settle)
    if n225 is not None:
        p = sq_periods(sq_hist, n225, vi)
    else:
        p = pd.DataFrame(columns=["start", "end", "s0", "s1", "ret", "days", "vi", "exp_move"])
    out = {}
    for fname, fn in (("strategy-vertical-spread.html", page_vertical),
                      ("strategy-ratio-spread.html", page_ratio),
                      ("strategy-straddle-strangle.html", page_straddle),
                      ("strategy-collar.html", page_collar)):
        r = fn(ch, p, img_dir, colors)
        if r:
            out[fname] = r
    r = page_gamma(ch, p, img_dir, colors, n225, vi_stats)
    if r:
        out["strategy-gamma-trading.html"] = r
    out["strategies.html"] = page_hub(ch, out)
    return out
