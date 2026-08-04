# -*- coding: utf-8 -*-
"""解説ページのコンテンツ定義。build.pyのrender_static_pages()が使う。

書き方のルール(strategy準拠):
- 個別の売買推奨をしない。データの読み方・事実・一般的な仕組みに徹する
- アフィリエイトリンクはプレースホルダー(HTMLコメント)。ASP承認後に差し替える
- 広告を含む予定のページには冒頭にPR表記
"""

# 英語ページ {ファイル名: (タイトル, 本文HTML)} — en/ 配下に出力される
EN_GUIDE_PAGES = {
    "guide-participants.html": ("Japan's Hidden COT: JPX Participant Positioning", """
<h1>Japan's Hidden COT — Reading JPX Trading-Participant Positioning</h1>
<p>Most global traders know the CFTC's COT report. Far fewer know that Japan Exchange Group (JPX)
publishes something arguably richer for Nikkei futures: <b>weekly open interest by named trading
participant</b> — Nomura, Goldman Sachs, HSBC, Morgan (MUFG), UBS and others, each with their
net long/short position in Nikkei 225 futures.</p>

<h2>What the data shows</h2>
<p>Every week (first business day), JPX publishes each participant's net open interest in
index futures. Unlike the CFTC report, which aggregates anonymous categories,
this data names the firms. Positions reflect a mix of house books and customer flows cleared
through each firm, so treat them as flow fingerprints rather than pure proprietary bets.</p>

<h2>How this site presents it</h2>
<p>On our <a href="./">main page</a> we chart each major participant's weekly net position
over the past year, with the Nikkei 225 overlaid. Patterns emerge quickly: some firms trend-follow,
some fade rallies, some hold persistent structural shorts (often hedges against structured products).</p>

<h2>Why it matters</h2>
<p>Japan's cash-equity flows are dominated by foreign investors, but Nikkei futures positioning
gives a faster weekly read on how large players lean. Combined with options open interest
("walls") and the CME's Nikkei COT data, it forms a reasonably complete positioning picture
that is hard to find in English anywhere else.</p>

<p><a href="./">→ See the live data (updated weekly)</a></p>
"""),

    "guide-nikkei-options.html": ("Nikkei 225 Options: A Field Guide", """
<h1>Nikkei 225 Options — A Field Guide for Global Traders</h1>
<p>A quick orientation to Japan's benchmark index options market, and the free official data
this site turns into daily charts.</p>

<h2>Contract basics</h2>
<ul>
<li><b>Underlying:</b> Nikkei 225. Regular options multiplier ×1,000 yen; mini options ×100 yen
with weekly expiries.</li>
<li><b>Expiry (SQ):</b> monthly settlement on the second Friday ("SQ day"). March/June/September/December
are "Major SQ" when futures expire together.</li>
<li><b>Session:</b> day session plus a night session that overlaps US hours — Nikkei options react
to US moves in real time.</li>
</ul>

<h2>The data JPX publishes daily (all free)</h2>
<ul>
<li>Open interest by strike for the nearest three expiries — the "walls" we chart daily</li>
<li>Put/call volume — the basis of our Nikkei put/call ratio series</li>
<li>Weekly: open interest by named trading participant (<a href="guide-participants.html">explainer</a>)</li>
</ul>

<h2>Reading the walls</h2>
<p>Strikes with heavy open interest often act as reference levels. A large put wall below spot
marks where hedging demand concentrated; SQ week tends to gravitate toward high-OI strikes.
Combined with the Nikkei VI (Japan's volatility index) you get a quick regime read:
walls close + VI low = pinned market; walls broken + VI spiking = trend risk.</p>

<p><a href="./">→ Live Nikkei dashboard</a> ・ <a href="us.html">→ US markets (COT & SPX gamma)</a></p>
"""),
}

# {ファイル名: (タイトル, 本文HTML)}
GUIDE_PAGES = {
    "glossary.html": ("用語集", """
<h1>用語集 — 当サイトで使うデータ用語</h1>
<p>各用語の詳しい解説は個別記事へのリンクからどうぞ。</p>

<h2>オプション関連</h2>
<ul>
<li><b>建玉(たてぎょく/OI)</b>: 未決済のまま残っている契約の総量。→ <a href="guide-oi.html">建玉分布の見方</a></li>
<li><b>壁</b>: 特定の行使価格に建玉が集中した状態。意識されやすい価格帯の目安</li>
<li><b>Put/Callレシオ(PCR)</b>: プット出来高÷コール出来高。1.0超はプット優勢 → <a href="guide-pcr.html">解説</a></li>
<li><b>SQ</b>: 特別清算指数。毎月第2金曜に算出され、その限月の取引が清算される。3・6・9・12月は先物も同時に満期を迎える「メジャーSQ」</li>
<li><b>IV(インプライド・ボラティリティ)</b>: オプション価格から逆算される将来変動率の織り込み</li>
<li><b>ガンマエクスポージャー</b>: ディーラーのヘッジ売買が相場を増幅するか抑制するかの推定値 → <a href="guide-gex.html">解説</a></li>
<li><b>ガンマフリップ</b>: ガンマエクスポージャーの符号が変わる価格帯</li>
<li><b>レバレッジETFのリバランス</b>: TQQQ・SOXL等が一定倍率を保つため引けに行う売買。上昇日は買い・下落日は売りで値動きを増幅する。オプションのガンマとは別メカニズムで、当サイトでは別指標として掲載(→ <a href="us.html">米国市場</a>)</li>
</ul>

<h2>ポジションデータ関連</h2>
<li><b>取引参加者別建玉</b>: JPXが週次で公表する、証券会社名入りの先物建玉。旧「手口情報」の後継</li>
<li><b>COTレポート</b>: CFTC(米)が週次公表する投資家区分別の先物建玉 → <a href="guide-cot.html">解説</a></li>
<li><b>投資部門別売買状況</b>: JPXが週次公表する、海外投資家・個人などの現物売買金額</li>

<h2>ボラティリティ・マクロ関連</h2>
<ul>
<li><b>日経VI</b>: 日経平均版の恐怖指数。20超で警戒領域、30超は荒れ相場</li>
<li><b>VIX</b>: S&P500版の恐怖指数</li>
<li><b>ブレークイーブン(BEI)</b>: 債券市場が織り込む期待インフレ率</li>
<li><b>Sahmルール</b>: 失業率の変化から景気後退入りを判定する経験則 → <a href="risk.html">リスクモニター</a></li>
</ul>
"""),
    "guide-gex.html": ("ガンマエクスポージャーとは", """
<h1>ガンマエクスポージャー(GEX)とは — 相場の「静と動」を分ける需給</h1>
<p>当サイトの<a href="us.html">米国市場ページ</a>で毎日更新しているガンマエクスポージャーの読み方を解説します。</p>

<h2>ガンマとは</h2>
<p>オプションのデルタ(原資産の値動きに対する感応度)が、原資産価格の変化でどれだけ変わるかを表すのがガンマです。
オプションの売り手(主にマーケットメイカー=ディーラー)は、このデルタの変化を打ち消すために
原資産を売買してヘッジします(デルタヘッジ)。</p>

<h2>ガンマエクスポージャーが示すもの</h2>
<p>市場全体の建玉にガンマを掛けて集計したものがガンマエクスポージャーで、
「ディーラーのヘッジ売買が相場をどちらに増幅するか」の目安になります。</p>
<ul>
<li><b>プラス圏(ポジティブガンマ)</b>: ディーラーは上がれば売り・下がれば買いのヘッジをするため、
<b>値動きを抑える力</b>が働きやすい(レンジ相場になりやすい)</li>
<li><b>マイナス圏(ネガティブガンマ)</b>: 逆に、下がれば売り・上がれば買いを迫られるため、
<b>値動きを増幅する力</b>が働きやすい(急落・急騰が出やすい)</li>
</ul>

<h2>注意点(正直に)</h2>
<p>当サイトを含む一般的なガンマエクスポージャーの数値は、
「ディーラーはコールの買い持ち・プットの売り持ち」という仮定に基づく<b>推定値</b>です。
実際のディーラーポジションは公開されていないため、水準そのものより
「プラス圏かマイナス圏か」「ガンマフリップ(符号が変わる価格帯)がどこか」を
大づかみに見るのが実践的な使い方です。</p>

<h2>あわせて見るもの</h2>
<ul>
<li><a href="us.html">米国市場データ</a> — SPXのガンマエクスポージャーを毎日更新</li>
<li><a href="guide-oi.html">建玉分布の見方</a> — 「壁」との合わせ読み</li>
</ul>
"""),

    "guide-cot.html": ("COTレポートの見方", """
<h1>COTレポートの見方 — ヘッジファンドのポジションを毎週チェックする</h1>
<p>当サイトの<a href="us.html">米国市場ページ</a>で毎週更新しているCOTデータの読み方を解説します。</p>

<h2>COTレポートとは</h2>
<p>米商品先物取引委員会(CFTC)が毎週金曜に公表する「建玉明細報告(Commitments of Traders)」です。
先物市場の建玉を投資家の属性別に集計したもので、
ヘッジファンドなどの投機筋が「どの市場を、どちら向きに、どれだけ持っているか」が分かります。
毎週火曜時点のデータが金曜(米国時間)に公表されます。</p>

<h2>当サイトでの分類</h2>
<ul>
<li><b>株価指数・通貨先物</b>: レバレッジファンド(ヘッジファンド等)のネットポジション</li>
<li><b>金・原油</b>: マネージドマネー(商品ファンド等)のネットポジション</li>
</ul>
<p>ネットポジション=買い建玉−売り建玉。プラスなら買い越し(強気)、マイナスなら売り越し(弱気)です。</p>

<h2>使い方のコツ</h2>
<ul>
<li><b>水準より変化</b>: 「先週から何枚増減したか」が市場の温度変化を示します</li>
<li><b>極端な偏りは逆張りシグナルにも</b>: 投機筋の売り越しが歴史的水準まで積み上がると、
買い戻し(ショートカバー)による急反発の燃料になることがあります</li>
<li><b>日経平均にも使える</b>: CME上場の日経平均先物もCOTの対象です。
海外投機筋の日本株への傾きが週次で追えます</li>
</ul>

<h2>あわせて見るもの</h2>
<ul>
<li><a href="us.html">米国市場データ</a> — ES・NQ・CME日経・円・金・WTIのCOT推移を毎週更新</li>
<li><a href="./">日本市場データ</a> — JPXの取引参加者別建玉(こちらは証券会社名入り)</li>
</ul>
"""),
    "guide-teguchi.html": ("先物の手口の見方", """
<h1>日経225先物の「手口」の見方 — ABNクリアリンやソシエテGは何者か</h1>
<p>毎日夕方、JPXは「取引参加者別取引高(手口上位一覧)」を公表します。
当サイトのトップでも<a href="./#pv">日経225先物・miniの上位</a>を毎営業日更新していますが、
並んでいるのは見慣れない外資系の名前ばかりです。
このデータが何を表していて、どこまで読めるのかを整理します。</p>

<h2>手口とは何か</h2>
<p>手口(取引参加者別取引高)は、<b>どの証券会社を通じて何枚の売買が成立したか</b>を集計したものです。
JPXが平日17時45分ごろに、その日の分を公表します。</p>
<p>混同しやすいものに<b>取引参加者別建玉残高</b>があります。こちらは週次(原則月曜午後)の公表で、
「未決済のポジションが今どれだけ残っているか」を示します。
<b>手口=その日の売買の量、建玉=積み上がった残高</b>と押さえると分かりやすいです。</p>

<h2>常連の顔ぶれと、その性格</h2>
<p>日経225先物の上位には、ほぼ毎日同じ会社が並びます。ただし<b>性格はかなり違います</b>。</p>
<ul>
<li><b>ABNアムロ・クリアリング証券</b> — クリアリング(清算)を専業とする会社で、
主な顧客は海外のプロップファーム(自己資金で運用する短期売買業者)です。
つまり同社の枚数は、<b>同社自身の相場観ではなく、その先にいる短期筋やマーケットメイカーの執行が積み上がったもの</b>と考えられます。
上位に定着しているのは、それだけ短期売買がこの経路を通っているためです</li>
<li><b>ソシエテジェネラル証券・バークレイズ証券・JPモルガン証券など外資系</b> —
海外機関投資家の注文執行が中心です。市場では「海外勢の動きを推し量る手がかり」として見られています</li>
<li><b>サスケハナ</b>などのマーケットメイカー — 値付けのための売買が中心で、
方向性を持ったポジションとは限りません</li>
</ul>

<h2>ラージとミニで参加者層が違う</h2>
<p>同じ日経225先物でも、ラージ(取引単位1,000倍)とミニ(100倍)では顔ぶれが変わります。</p>
<ul>
<li><b>ラージ</b>: 上位はほぼ外資系で占められます</li>
<li><b>ミニ</b>: 上位は同じく外資系ですが、その下に<b>SBI証券・楽天証券・松井証券といった国内のネット証券</b>が入ってきます</li>
</ul>
<p>ミニは取引単位が10分の1で個人が参加しやすいため、国内リテールの売買が可視化されるわけです。
<b>ラージは海外勢の主戦場、ミニは個人も参戦</b>という棲み分けが、手口から読み取れます。</p>

<h2>ここまでしか読めない、という限界</h2>
<p>手口は便利な反面、<b>過大に解釈されがちなデータ</b>でもあります。次の3点は押さえておく必要があります。</p>
<ol>
<li><b>買いか売りかは分かりません</b>。公表されるのは取引高(売買の合計枚数)で、方向は含まれません</li>
<li><b>自己売買と委託(顧客注文)が混ざっています</b>。「A社が買った」ではなく
「A社を通じて売買された」が正しい理解です</li>
<li><b>ポジションの残高ではありません</b>。日中に売って買い戻せば、残高ゼロでも枚数は積み上がります</li>
</ol>
<p>したがって「誰が買った/売った」と読むのは危険で、
<b>どの経路の資金が活発なのかを見る指標</b>として使うのが実際的です。
方向やポジションの偏りを見たい場合は、週次の建玉残高やCOTを併せて確認してください。</p>

<h2>実際の使い方</h2>
<p>日々の枚数そのものより、<b>前日との変化</b>や<b>シェアの偏り</b>を見るほうが示唆があります。
上位数社で全体の6割以上を占める日は、限られた参加者が値動きを主導していた可能性があります。
逆に上位のシェアが下がっている日は、参加者の裾野が広がっているとも読めます。</p>

<h2>あわせて見るもの</h2>
<ul>
<li><a href="./#pv">日経225先物・miniの手口上位</a> — 毎営業日更新(JPX公表は17:45ごろ)</li>
<li><a href="guide-oi.html">建玉分布の見方</a> — 行使価格に積み上がった「壁」の読み方</li>
<li><a href="guide-cot.html">COTレポートの見方</a> — 米国先物での投資家区分別ポジション</li>
</ul>
"""),
    "guide-oi.html": ("建玉分布の見方", """
<h1>建玉分布の見方 — 「壁」はどう読むか</h1>
<p>当サイトのトップに毎日掲載している「行使価格別 建玉分布」の読み方を解説します。</p>

<h2>建玉(たてぎょく)とは</h2>
<p>建玉(Open Interest)は、まだ決済されていないオプション契約の残高です。
出来高が「その日に取引された量」であるのに対し、建玉は「積み上がっているポジションの総量」を表します。
どの行使価格に建玉が集中しているかを見ると、市場参加者が意識している価格帯が浮かび上がります。</p>

<h2>「壁」の考え方</h2>
<p>特定の行使価格に大量の建玉が積み上がっている状態は、俗に「壁」と呼ばれます。</p>
<ul>
<li><b>コール建玉の壁(現値より上)</b>: オプションの売り手にとって、この水準を超えて上昇されると損失が膨らむため、
ヘッジ売買が価格の上値を抑える方向に働くことがある、と解釈されます</li>
<li><b>プット建玉の壁(現値より下)</b>: 同様に、下値の目処として意識されやすい水準です</li>
</ul>
<p>ただし、壁は「必ず止まる水準」ではありません。抜けたときにはヘッジの巻き戻しでかえって動きが加速することもあります。
壁の位置は日々変わるため、当サイトの建玉増減(前日比)とあわせて「壁が育っているのか、崩れているのか」を見るのが実践的です。</p>

<h2>SQに向けた見方</h2>
<p>建玉は限月ごとに集計されます。SQ(特別清算指数の算出日)が近づくと、
その限月の建玉分布が現値の周辺でどう整理されていくかが注目されます。
当サイトでは直近3限月分を毎日更新しているので、限月ごとの偏りも確認できます。</p>

<h2>あわせて見るもの</h2>
<ul>
<li><a href="guide-pcr.html">Put/Callレシオとは</a> — 市場心理の偏りを1つの数字で見る</li>
<li><a href="guide-start.html">日経225オプションを始めるには</a> — 取引環境の整え方</li>
</ul>
"""),

    "guide-pcr.html": ("Put/Callレシオとは", """
<h1>Put/Callレシオとは — 1.0の上下で何が分かるか</h1>
<p>当サイトのトップに毎日掲載しているPut/Callレシオ(PCR)の見方を解説します。</p>

<h2>計算方法</h2>
<p>Put/Callレシオ = プットの出来高 ÷ コールの出来高。
当サイトでは日経225オプション(ラージ)の日通し出来高(JPX公表)から毎日算出しています。</p>

<h2>読み方の基本</h2>
<ul>
<li><b>1.0超(プット優勢)</b>: 下落に備えるヘッジ需要や弱気の見方が強い状態</li>
<li><b>1.0未満(コール優勢)</b>: 上昇を取りにいく動きが優勢な状態</li>
</ul>
<p>注意したいのは、PCRは「逆張り指標」として使われることも多い点です。
プットが極端に買われた状態は、悲観の織り込みが進んだ状態とも解釈でき、
歴史的にはPCRの極端な高まりが相場の転換点付近で観測されることがあります。</p>

<h2>水準よりも「変化」を見る</h2>
<p>PCRは単日の水準だけで判断するとノイズが大きい指標です。
当サイトでは日次の推移をチャートで蓄積しているので、
「普段のレンジからどれだけ外れたか」「急変した日はどんなニュースがあったか」という
変化に注目する使い方をおすすめします。</p>

<h2>あわせて見るもの</h2>
<ul>
<li><a href="guide-oi.html">建玉分布の見方</a> — 価格帯ごとのポジションの偏り</li>
<li><a href="guide-start.html">日経225オプションを始めるには</a></li>
</ul>
"""),

    "guide-start.html": ("日経225オプションを始めるには", """
<p style="font-size:0.8em; color:#4b5563;">※本ページにはプロモーションが含まれる場合があります</p>
<h1>日経225オプションを始めるには — 口座開設から取引開始まで</h1>
<p>当サイトのデータを「見る」だけでなく実際の取引に活かしたい方向けに、
日経225オプションの取引を始める一般的な手順をまとめます。</p>

<h2>必要な口座</h2>
<p>日経225オプション(および先物)の取引には、証券会社の総合口座に加えて
<b>先物・オプション取引口座</b>の開設が必要です。手順は一般に次の流れです。</p>
<ol>
<li>ネット証券で総合口座を開設(無料・ネット完結)</li>
<li>同じ証券会社で先物・オプション口座を申請(投資経験等の審査があります)</li>
<li>証拠金を入金して取引開始</li>
</ol>

<h2>証券会社選びで見るポイント</h2>
<ul>
<li><b>手数料</b>: オプションは1枚あたりの手数料体系。各社で差があります</li>
<li><b>取引ツール</b>: オプションのボード表示・リスク管理機能の使いやすさ</li>
<li><b>ミニ・週次限月への対応</b>: 小さく始めたい場合はミニオプションの取扱い有無</li>
</ul>
<p>主要ネット証券(松井証券、SBI証券、楽天証券など)はいずれも先物・オプション口座を提供しています。
手数料・ツールの詳細は各社公式サイトで最新情報をご確認ください。</p>
<p>たとえば<b>松井証券</b>は先物・オプション取引に対応しており、取引ツールや情報提供も充実しています。
口座開設は無料・ネット完結で、まず総合口座を開いてから先物・オプション口座を申請する流れです。
→ <a href="https://px.a8.net/svt/ejp?a8mat=4B83D5+490F8Y+3XCC+64C3M" rel="nofollow">松井証券の口座開設(公式・PR)</a><img border="0" width="1" height="1" src="https://www17.a8.net/0.gif?a8mat=4B83D5+490F8Y+3XCC+64C3M" alt=""></p>
<div style="text-align:center; margin: 16px 0;">
<a href="https://px.a8.net/svt/ejp?a8mat=4B83D5+490F8Y+3XCC+6HMHT" rel="nofollow">
<img border="0" width="300" height="250" alt="松井証券" src="https://www21.a8.net/svt/bgt?aid=260718089257&wid=001&eno=01&mid=s00000018318001090000&mc=1"></a>
<img border="0" width="1" height="1" src="https://www11.a8.net/0.gif?a8mat=4B83D5+490F8Y+3XCC+6HMHT" alt="">
</div>
<p>なお、現物株・信用取引の口座を手数料重視で選びたい方には次のような選択肢もあります:
<a href="https://px.a8.net/svt/ejp?a8mat=4B83D5+4CL0VM+1WP2+15QHIA" rel="nofollow">日本株を始めるなら【DMM 株】!(PR)</a><img border="0" width="1" height="1" src="https://www17.a8.net/0.gif?a8mat=4B83D5+4CL0VM+1WP2+15QHIA" alt=""></p>

<!-- 【アフィリエイトリンク: SBI証券 口座開設(アクセストレード・提携申請中)】 -->
<!-- 【アフィリエイトリンク: 楽天証券 口座開設(TGアフィリエイト・審査中)】 -->

<h2>オプション以外の選択肢: CFDで日経225を取引する</h2>
<p>「オプションはまだ難しそうだが、日経平均の指数そのものをレバレッジをかけて取引したい」という場合、
<b>CFD(差金決済取引)</b>という選択肢もあります。日経225やNYダウなどの株価指数を、
ほぼ24時間・少額の証拠金から売買でき、売りからも入れます。
当サイトで扱う建玉分布やガンマエクスポージャーの分析は、CFDでの指数トレードにもそのまま活用できます。</p>
<p>CFDの取扱いがある口座の例として、DMM.com証券(DMM CFD)があります。</p>
<div style="text-align:center; margin: 16px 0;">
<a href="https://px.a8.net/svt/ejp?a8mat=4B83D5+4BZL9U+1WP2+NXESX" rel="nofollow">
<img border="0" width="250" height="250" alt="DMM.com証券 CFD" src="https://www21.a8.net/svt/bgt?aid=260718089262&wid=001&eno=01&mid=s00000008903004019000&mc=1"></a>
<img border="0" width="1" height="1" src="https://www19.a8.net/0.gif?a8mat=4B83D5+4BZL9U+1WP2+NXESX" alt="">
</div>
<p><a href="https://px.a8.net/svt/ejp?a8mat=4B83D5+4BZL9U+1WP2+NTRMQ" rel="nofollow">【PR】全銘柄の取引手数料が0円の【DMM CFD】</a><img border="0" width="1" height="1" src="https://www10.a8.net/0.gif?a8mat=4B83D5+4BZL9U+1WP2+NTRMQ" alt=""></p>
<p>※ CFDも証拠金取引であり、相場変動により預託した証拠金を上回る損失が生じるおそれがあります。
取引条件・手数料等の詳細は公式サイトで最新情報をご確認ください。</p>

<h2>始める前に理解しておくべきリスク</h2>
<p>オプション取引は仕組み上、買い方の損失は支払ったプレミアムに限定されますが、
<b>売り方の損失は理論上限定されません</b>。また証拠金取引のためレバレッジがかかります。
少額のミニオプション・買い戦略から始める、証拠金に余裕を持つなど、
リスク管理を最優先にしてください。当サイトは特定の取引を推奨するものではありません。</p>

<h2>データを活かす</h2>
<p>口座の準備ができたら、当サイトの<a href="./">建玉分布・Put/Callレシオ</a>を
日々の分析にお役立てください。毎営業日、JPX公表データで自動更新しています。</p>

<div style="text-align:center; margin: 24px 0; overflow-x:auto;">
<a href="https://px.a8.net/svt/ejp?a8mat=4B83D5+4BZL9U+1WP2+NYHDT" rel="nofollow">
<img border="0" width="728" height="90" alt="DMM.com証券" src="https://www28.a8.net/svt/bgt?aid=260718089262&wid=001&eno=01&mid=s00000008903004024000&mc=1"></a>
<img border="0" width="1" height="1" src="https://www17.a8.net/0.gif?a8mat=4B83D5+4BZL9U+1WP2+NYHDT" alt="">
</div>
"""),
}

# ---------------------------------------------------------------------------
# 解説記事の末尾に置く口座開設への導線
#
# GA4(2026-07-27)の実測: 解説記事は滞在1分超で読まれている一方、
# guide-start.html は滞在11秒で直帰していた。読まれている記事の側に
# 導線を置くほうが自然に届くため、記事末尾にこのブロックを追加する。
# 広告を含むページには冒頭にPR表記を出す(景表法・ステマ規制対応)。
# ---------------------------------------------------------------------------

PR_NOTE = ('<p style="font-size:0.8em; color:#4b5563;">'
           '※本ページにはプロモーションが含まれる場合があります</p>\n')

_A8_MATSUI = "https://px.a8.net/svt/ejp?a8mat=4B83D5+490F8Y+3XCC+64C3M"
_A8_MATSUI_PIXEL = "https://www17.a8.net/0.gif?a8mat=4B83D5+490F8Y+3XCC+64C3M"

CTA_BROKER = f"""
<div style="margin:28px 0 8px; padding:14px 16px; border:1px solid #dfe3e9;
            border-radius:10px; background:#ffffff;">
<p style="margin:0 0 8px;"><b>データを実際の取引に使うには</b></p>
<p style="margin:0 0 10px; font-size:0.95em;">
日経225オプション・先物の売買には、証券会社の総合口座に加えて
<b>先物・オプション取引口座</b>の開設が必要です(無料・ネット完結)。
建玉やPCRを見て「この水準で張ってみたい」と思ったときに、
口座がないと動けないため、先に用意しておくのが一般的です。</p>
<p style="margin:0 0 6px;">→ <a href="{_A8_MATSUI}" rel="nofollow">松井証券の口座開設(公式・PR)</a><img border="0" width="1" height="1" src="{_A8_MATSUI_PIXEL}" alt=""></p>
<p style="margin:0; font-size:0.85em; color:#4b5563;">
証券会社の比較や申込みの流れは
<a href="guide-start.html" style="color:#1f6fd0">始め方ガイド</a>にまとめています。</p>
</div>
"""

# 読まれている解説記事にPR表記+口座開設導線を付与する
for _key in ("guide-oi.html", "guide-pcr.html", "guide-gex.html", "guide-cot.html",
             "guide-teguchi.html"):
    if _key in GUIDE_PAGES:
        _title, _body = GUIDE_PAGES[_key]
        GUIDE_PAGES[_key] = (_title, PR_NOTE + _body + CTA_BROKER)
