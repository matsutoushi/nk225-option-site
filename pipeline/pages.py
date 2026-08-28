# -*- coding: utf-8 -*-
"""解説ページのコンテンツ定義。build.pyのrender_static_pages()が使う。

書き方のルール(strategy準拠):
- 個別の売買推奨をしない。データの読み方・事実・一般的な仕組みに徹する
- アフィリエイトリンクはプレースホルダー(HTMLコメント)。ASP承認後に差し替える
- 広告を含む予定のページには冒頭にPR表記
"""

# 英語ページの meta description。
# 検索結果のスニペットになるほか、AIアシスタントがページの主題を判断する材料にもなる。
# 「JPXは証券会社名まで公表する」「日経の建玉・ガンマは公式データだけで組める」という、
# 英語圏でほとんど書かれていない事実を先頭に置いている。
EN_GUIDE_DESC = {
    "guide-participants.html":
        "JPX publishes weekly Nikkei 225 futures open interest by named trading participant — "
        "Nomura, Goldman Sachs, HSBC and others — unlike the CFTC's anonymous COT categories. "
        "How to read it, and why a firm's short is usually structural, not bearish.",
    "guide-nikkei-options.html":
        "Nikkei 225 options explained for global traders: contract specs, SQ settlement, "
        "open interest walls, put/call ratio and gamma exposure, all built from free official "
        "JPX data and updated every business day.",
    "guide-gamma-exposure.html":
        "Gamma exposure for the Nikkei 225, estimated from JPX settlement files that publish "
        "implied volatility for every strike — plus SPX GEX from CBOE chains. What the number "
        "can and cannot tell you, and the two errors that inflate almost every published estimate.",
    "guide-sq.html":
        "Nikkei 225 SQ explained: how the settlement price is calculated, why it differs from "
        "the index open, and the counterintuitive fact that open interest climbs into expiry "
        "and then vanishes in a single session — 156,105 contracts on 14 August 2026.",
    "guide-put-call-ratio.html":
        "The Nikkei 225 put/call ratio falls on some of the worst down days. Why the denominator "
        "matters as much as the numerator, why the large-contract ratio averages 1.57 while mini "
        "averages 0.91, and how to read the two together.",
    "glossary.html":
        "Glossary of Japanese index-derivatives terms for global traders: SQ, genkyoku, "
        "tategyoku, teguchi, large vs mini vs micro contracts, Nikkei VI, and the JPX data "
        "files each one comes from.",
}

# 英語ページ {ファイル名: (タイトル, 本文HTML)} — en/ 配下に出力される
EN_GUIDE_PAGES = {
    "guide-participants.html": ("Japan's Hidden COT: JPX Participant Positioning", """
<h1>Japan's Hidden COT — Reading JPX Trading-Participant Positioning</h1>
<p>Most global traders know the CFTC's Commitments of Traders report. Far fewer know that
Japan Exchange Group (JPX) publishes something arguably richer for Nikkei 225 futures:
<b>weekly open interest by named trading participant</b> — Nomura, Goldman Sachs, HSBC,
Morgan Stanley MUFG, SMBC Nikko and others, each with their net long/short position.</p>
<p>The CFTC aggregates traders into anonymous categories. JPX names the firms.
This page explains what the data is, how to read it correctly, and — importantly —
the mistake that makes it useless if you get it wrong.</p>

<h2>What JPX publishes</h2>
<ul>
<li><b>Weekly open interest by participant</b> (released the first business day of each week):
net position held through each clearing firm in Nikkei 225 futures and mini futures.</li>
<li><b>Daily trading volume by participant</b> (released around 17:45 JST): how much was
traded through each firm that day. Volume only — <b>no direction</b>.</li>
</ul>
<p>Both are free and official. Neither has a direct equivalent in US markets.</p>

<h2>The mistake that ruins this data</h2>
<p>The obvious reading — "Firm X is net short, so foreign institutions are bearish" —
<b>does not work</b>. Here is what our own dataset shows.</p>
<p>We aggregated 52 weeks of participant open interest in Nikkei 225 futures
(August 2025 to July 2026) and measured how often each firm's net position kept the same sign:</p>
<table>
<thead><tr><th>Participant</th><th>Average net</th><th>Same sign</th></tr></thead>
<tbody>
<tr><td>HSBC</td><td>−31,604 contracts</td><td><b>52 of 52 weeks short</b></td></tr>
<tr><td>SMBC Nikko</td><td>+4,927</td><td><b>52 of 52 weeks long</b></td></tr>
<tr><td>Morgan Stanley MUFG</td><td>−14,029</td><td>98% short</td></tr>
<tr><td>Nomura</td><td>+18,065</td><td>92% long</td></tr>
<tr><td>Société Générale</td><td>+19,106</td><td>90% long</td></tr>
</tbody>
</table>
<p>The Nikkei moved substantially in both directions over this period.
<b>These firms did not change sides.</b> If you had read HSBC's short as a bearish signal,
you would have been bearish every single week for a year.</p>
<p>The reason is structural, not directional. A clearing firm's position reflects
hedges against structured products it has issued, the other side of client flow,
index arbitrage against cash equities, and market-making inventory.
<b>These generate persistent one-way positions regardless of any house view.</b></p>

<h2>How to read it correctly</h2>
<p>Compare each firm against <b>its own normal</b>, not against zero.</p>
<ul>
<li><b>Wrong:</b> "HSBC is short, so they are bearish."</li>
<li><b>Right:</b> "HSBC's short is 20,000 contracts smaller than usual — that is buying pressure."</li>
</ul>
<p>If HSBC's baseline is −31,604 and this week reads −5,000, the firm has effectively
covered a large short even though the sign is still negative.
The same logic applies to daily volume: 50,000 contracts means nothing for a firm that
always trades 50,000, but means a great deal for one that usually trades 10,000.</p>

<h2>Large vs mini: two different crowds</h2>
<p>Nikkei 225 futures come in large (¥1,000 multiplier) and mini (¥100).
The participant mix differs: large contracts are dominated by foreign institutions,
while mini rankings include Japanese online brokers (SBI, Rakuten, Matsui) — that is,
domestic retail. When the two disagree, professionals and retail are positioned differently.</p>

<h2>How this site presents it</h2>
<p>On our <a href="./">main dashboard</a> we chart each major participant's weekly net position
over the past year with the Nikkei 225 overlaid, and publish the daily volume rankings for
both large and mini contracts every business day, sourced entirely from JPX.</p>

<h2>Why it matters</h2>
<p>Japanese equity flows are dominated by foreign investors, and futures positioning gives a
faster read than cash-market statistics. Combined with options open interest ("walls"),
estimated gamma exposure, and the CME's Nikkei COT data, it forms a positioning picture
that is difficult to assemble in English anywhere else.</p>
<p>Just remember what the data is not: it contains no direction for volume, no separation of
house and client, and no proprietary view. <b>It is a flow fingerprint, not a forecast.</b></p>

<p><a href="./">→ See the live data (updated every business day)</a></p>
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
<li>Daily settlement prices including <b>implied volatility for every strike</b> — this is what
lets us estimate gamma exposure from official data alone</li>
</ul>

<h2>Reading the walls</h2>
<p>Strikes with heavy open interest often act as reference levels. A large put wall below spot
marks where hedging demand concentrated; SQ week tends to gravitate toward high-OI strikes.
Combined with the Nikkei VI (Japan's volatility index) you get a quick regime read:
walls close + VI low = pinned market; walls broken + VI spiking = trend risk.</p>

<h2>Do not use the largest open interest as the wall</h2>
<p>This is the most common error, and Nikkei options make it easy to commit.</p>
<p>In early August 2026, the single largest open interest in the entire Nikkei options chain
was the <b>30,000 put, at roughly 5,600 contracts</b>. The Nikkei was trading near 65,600 —
so that strike sat <b>53% below spot</b>. Over eight sessions the position moved from
5,592 to 5,623 contracts: essentially dead. It is legacy or deep tail protection,
and it has nothing to do with current price action.</p>
<p>Meanwhile the 70,000 call, about 6% above spot, moved from 4,490 to 4,910 contracts
in the same window. Smaller, but alive and reachable. That is the strike that matters.</p>
<p>For this reason we restrict "walls" to strikes <b>within ±10% of spot</b>: the highest
call open interest above spot, and the highest put open interest below it.</p>

<h2>Two Nikkei-specific quirks worth knowing</h2>
<p><b>1. The back month can be larger than the front month.</b>
On 7 August 2026, one week before the August expiry, August open interest stood at
169,955 contracts while <b>September held 189,160</b>. September is a Major SQ
(futures expire alongside options), so quarterly hedges concentrate there.
Looking only at the front month will misread where the market's attention is.</p>
<p><b>2. Open interest rises into expiry rather than winding down.</b>
The same August series went from 137,311 contracts on 17 July to 169,955 on 7 August —
<b>up 24% in three weeks</b>. Short-dated options are cheap and responsive, so short-term
flow concentrates into them. The position does not decay away; it accumulates and then
vanishes at SQ, which is why the supply-demand picture changes abruptly around expiry.</p>

<h2>Put/call ratio: read the numerator and denominator</h2>
<p>The Nikkei put/call ratio normally sits <b>above 1.0</b> — our measured average is 1.57
for large contracts — because institutional put hedging is structural. Judge it against
its own range, not against 1.0.</p>
<p>Mini contracts behave differently: the same period averaged <b>0.91</b>, consistently
below the large-contract ratio. Large is institutional hedging; mini carries more retail
upside-seeking flow. The gap between them is itself informative.</p>

<p><a href="./">→ Live Nikkei dashboard</a> ・ <a href="us.html">→ US markets (COT & SPX gamma)</a>
・ <a href="guide-participants.html">→ Participant positioning explained</a></p>
"""),

    "guide-gamma-exposure.html": ("Gamma Exposure, Honestly", """
<h1>Gamma Exposure — What It Measures, and Where Published Numbers Go Wrong</h1>
<p>Gamma exposure ("GEX") tries to answer one question: <b>when the index moves, does dealer
hedging push it further, or pull it back?</b> The idea is sound. Most published numbers are
built on assumptions that are rarely stated, and on at least one arithmetic error that is easy
to make and hard to notice.</p>
<p>This page explains how we compute it for the Nikkei 225 and the S&amp;P 500, what the number
is worth, and the two mistakes we found in our own implementation.</p>

<h2>The mechanism</h2>
<p>A dealer who is short options must hedge. If they are short gamma, hedging means
<b>selling into declines and buying into rallies</b> — the hedge amplifies the move.
If they are long gamma, they do the opposite and dampen it.</p>
<p>Gamma is largest near the strike and near expiry, so the effect concentrates around
heavily traded strikes in the front month. Aggregate gamma across every strike, sign it by
assumed dealer positioning, and you get a single number: yen (or dollars) of hedging flow
per 1% move in the index.</p>

<h2>Why the Nikkei is unusually well suited to this</h2>
<p>Most gamma estimates need an options pricing model, which needs implied volatility, which
usually means paying for data. JPX removes that step: its <b>daily settlement price file
publishes an implied volatility for every single strike</b>, along with days to expiry and
the reference index level. Black-Scholes gamma follows directly from official data.</p>
<p>We compute gamma per strike, weight it by open interest and the contract multiplier
(¥1,000 for large, ¥100 for mini), and sum across the nearest expiries within ±10% of spot.</p>

<h2>The number is directional, not absolute</h2>
<p>Here is the honest limitation, stated plainly: <b>dealer positioning is not public.</b>
Every GEX calculation, ours included, substitutes a convention — dealers are assumed long
calls and short puts. Nobody publishes whether that is true on any given day.</p>
<p>It is also incomplete by construction. Structured products hedged over the counter never
appear in listed open interest. In the US, covered-call funds illustrate the scale of the gap:
JEPI runs roughly $45bn largely through OTC equity-linked notes, invisible to any
exchange-data calculation, while listed-option funds like QYLD (~$8.4bn) are visible.
The same asymmetry exists in Japan through structured notes.</p>
<p>So treat the output as a <b>sign and a shape</b>, not a quantity. Is hedging flow
amplifying or dampening? Where does it flip relative to spot? Those survive the assumptions.
The absolute yen figure does not.</p>

<h2>The shape matters more than the total</h2>
<p>The aggregate hides the useful part. Our Nikkei readings for 21 August 2026:</p>
<table>
<thead><tr><th>Region</th><th>Gamma per 1% move</th><th>Effect</th></tr></thead>
<tbody>
<tr><td>Above spot</td><td>+¥39.5bn</td><td>dampening</td></tr>
<tr><td>Below spot</td><td>−¥58.4bn</td><td>amplifying</td></tr>
<tr><td><b>Net</b></td><td><b>−¥18.8bn</b></td><td>amplifying</td></tr>
</tbody>
</table>
<p>The signs are opposite. Hedging flow would cushion a rally and accelerate a decline —
a market that grinds up and drops fast. A single net figure of −¥18.8bn tells you none of that,
which is why we chart the profile across strikes rather than publishing one number.</p>
<p>The shape is also more stable than the level. On 20 August the same readings were
+¥42.5bn above and −¥57.9bn below. The Nikkei moved +890 yen that day and −200 the next,
yet the downside figure changed by less than ¥1bn. Net gamma has been on the amplifying
side since 19 August (−¥44.0bn, then −¥15.4bn, then −¥18.8bn) even as the Nikkei
Volatility Index drifted down from 29.7 to 28.4.</p>

<h2>Mistake 1: expired contracts</h2>
<p>Options chains from most sources include contracts that have already expired. If you filter
only by "days to expiry ≤ N" without also requiring expiry ≥ today, negative day counts pass
through and contribute gamma that no longer exists.</p>
<p>We had this bug in our SPX calculation. Adding a single condition — expiry must be today or
later — moved published SPX gamma exposure from <b>$178.1bn to $87.1bn</b>.
The original figure was overstated by 51%. If a published GEX number looks large,
this is the first thing to check.</p>

<h2>Mistake 2: assuming weeklies are the missing piece</h2>
<p>Nikkei mini options expire weekly, and it is natural to assume that omitting them
understates gamma badly. We assumed exactly that, then measured it.</p>
<p>About 85% of mini open interest already sits on the monthly SQ expiry and was
being captured. Adding every weekly expiry contributed <b>571 large-equivalent contracts —
roughly 0.3% of the total</b>. The intuition was wrong, and we would not have known
without checking.</p>
<p>One detail worth recording if you build this yourself: JPX labels mini open interest by
<b>last trading day</b>, while the settlement file labels the same series by <b>SQ day</b>.
They differ by exactly one calendar day. Join on the raw code and the weekly series
silently disappears.</p>

<h2>What we publish</h2>
<p>Every business day, for both markets:</p>
<ul>
<li><b>Nikkei 225:</b> gamma profile by strike, split above and below spot, from JPX
settlement and open interest files</li>
<li><b>S&amp;P 500:</b> SPX gamma from CBOE chains including daily and weekly expiries,
with the flip level where the sign changes</li>
</ul>
<p>Both are labelled as estimates, with the dealer-positioning assumption stated on the page.</p>

<p><a href="./">→ Live Nikkei gamma profile</a> ・ <a href="us.html">→ SPX gamma and COT</a>
・ <a href="guide-nikkei-options.html">→ Nikkei options field guide</a></p>
"""),

    "guide-sq.html": ("Nikkei SQ Explained", """
<h1>SQ — How Nikkei 225 Options Actually Expire</h1>
<p>SQ ("Special Quotation") is the settlement price for expiring Nikkei 225 options and futures.
It is simple to define and easy to misunderstand, and the open interest behaviour around it
runs opposite to most people's intuition.</p>

<h2>The mechanics</h2>
<ul>
<li><b>When:</b> the second Friday of each month. March, June, September and December are
"Major SQ", when futures expire alongside options and volume concentrates.</li>
<li><b>How:</b> the SQ value is computed from the <b>opening prices of all 225 constituents</b>
on that morning, each stock taken at its own opening auction.</li>
<li><b>Mini options</b> expire weekly, so most Fridays carry an expiry of some size.</li>
</ul>

<h2>SQ is not the Nikkei's opening price</h2>
<p>This trips people up constantly. The Nikkei 225 index opens using whatever prices exist at
09:00, including the previous close for any constituent that has not yet opened. The SQ value
instead waits for each stock's actual opening auction.</p>
<p>On a volatile morning, slow-opening large caps can push the two apart by several hundred yen.
Contracts settle at the SQ value — not at the index print you saw on screen.</p>

<h2>Open interest rises into expiry, then vanishes</h2>
<p>The intuition is that positions get unwound as expiry approaches and open interest drains
away. The data says otherwise.</p>
<p>The August 2026 series went from <b>137,311 contracts on 17 July to 169,955 on 7 August</b>
— up 24% in three weeks, one week before expiry. Short-dated options are cheap and responsive,
so short-term flow concentrates into them rather than leaving.</p>
<p>Then it disappears at once. On <b>14 August 2026, SQ day, total open interest fell by
156,105 contracts in a single session</b> (calls −53,942, puts −102,163). Nothing decayed;
it accumulated and was extinguished.</p>
<p>This is why the supply-demand picture changes abruptly around expiry rather than gradually.
Gamma concentrated at nearby strikes is there one day and gone the next, and hedging flows
that were pinning the index simply stop.</p>

<h2>The rebuild starts immediately</h2>
<p>The week after the August expiry, total Nikkei options open interest went from
<b>272,499 contracts on 17 August to 291,911 on 21 August</b> — up 7.1% in five sessions,
with puts adding 13,222 and calls 6,190. Three weeks before the September SQ, the position
was already being rebuilt.</p>
<p>A practical consequence: the front month is not always the biggest. On 7 August 2026,
one week before the August expiry, August held 169,955 contracts while <b>September held
189,160</b>. September is a Major SQ, so quarterly hedges concentrate there. Looking only at
the nearest expiry will point you at the wrong strikes.</p>

<h2>What to watch around SQ</h2>
<ul>
<li><b>Where open interest sits</b> in the expiring series — heavy strikes tend to attract
the index during expiry week</li>
<li><b>Whether the next month is already larger</b>, which tells you where hedging has moved</li>
<li><b>The gamma profile</b> before and after: the amplifying or dampening effect of dealer
hedging can invert overnight when a large series settles
(<a href="guide-gamma-exposure.html">explainer</a>)</li>
<li><b>Major SQ months</b> (Mar/Jun/Sep/Dec), where futures expire too and the effect is larger</li>
</ul>

<h2>Where the data comes from</h2>
<p>JPX publishes open interest by strike for the nearest three expiries every business day,
free. We chart the distribution, the daily change, and the totals by expiry, so the
accumulate-then-vanish cycle is visible without assembling the files yourself.</p>

<p><a href="./">→ Live open interest by expiry</a> ・
<a href="guide-gamma-exposure.html">→ Gamma exposure explained</a> ・
<a href="guide-nikkei-options.html">→ Nikkei options field guide</a></p>
"""),

    "guide-put-call-ratio.html": ("The Put/Call Ratio Trap", """
<h1>The Put/Call Ratio — Why It Falls on Bad Days</h1>
<p>The put/call ratio divides put volume by call volume. Higher is supposed to mean more fear.
It is one of the most widely quoted sentiment gauges, and one of the easiest to read backwards.</p>

<h2>A worked example that inverts the signal</h2>
<p>On 28 July 2026 the Nikkei 225 fell <b>3.95%</b>. The put/call ratio fell too —
from 1.995 to <b>1.387</b>. Read naively, the market became less fearful during a sharp
sell-off.</p>
<p>The components explain it:</p>
<table>
<thead><tr><th></th><th>Prior day</th><th>28 July</th><th>Change</th></tr></thead>
<tbody>
<tr><td>Put volume</td><td>21,148</td><td>35,728</td><td>×1.69</td></tr>
<tr><td>Call volume</td><td>10,603</td><td>25,764</td><td><b>×2.43</b></td></tr>
<tr><td>Ratio</td><td>1.995</td><td>1.387</td><td>−0.61</td></tr>
</tbody>
</table>
<p>Put activity rose sharply. Call activity rose <b>more</b>. In a fast decline, traders take
profit on puts they already own, buy cheap calls for a bounce, and close calls that are now
far out of the money — all of which lift call volume. The ratio fell while hedging demand
was rising.</p>
<p><b>A ratio moves on its denominator as readily as its numerator.</b> Without both raw
volumes you can read the day exactly backwards, which is why we publish put and call volume
next to the ratio rather than the ratio alone.</p>

<h2>1.0 is not the neutral line for the Nikkei</h2>
<p>Textbooks treat 1.0 as balance. For Nikkei 225 large-contract options, our measured
average is <b>1.57</b>. Institutional downside hedging is structural and permanent, so the
ratio lives above 1.0 in calm markets and tells you nothing by being there.</p>
<p>Judge it against its own recent range instead. Readings from the week of 17 August 2026
show how wide that range is: 1.956, 1.818, 2.279, 1.017, 1.384. A single print carries
very little information.</p>

<h2>Large and mini are two different crowds</h2>
<p>Nikkei options trade in large (×1,000 yen) and mini (×100 yen) sizes. Over the same
sample, large averaged <b>1.57</b> and mini averaged <b>0.91</b> — mini frequently sits
below 1.0.</p>
<p>Large contracts are dominated by institutions buying downside protection. Mini carries a
much higher share of retail flow, which leans toward upside. The two ratios measure different
populations, and the <b>gap between them</b> is more informative than either alone.
When mini rises toward large, retail is hedging too.</p>

<h2>Open interest sometimes says it more cleanly</h2>
<p>Volume counts activity; open interest counts commitment. Occasionally the second is
much clearer.</p>
<p>On 20 August 2026, Nikkei call open interest went from 101,116 to 101,103 contracts —
a net change of <b>13 contracts</b>. Puts added 1,721 the same day. Across the previous month
call open interest had risen by 1,000 to 6,000 contracts on a typical day, so this was not a
quiet session in general; it was a session where <b>only the upside stopped being built</b>.
The put/call volume ratio that day was 1.017, which looks perfectly balanced and says
nothing about it.</p>

<h2>Practical reading</h2>
<ul>
<li>Always look at put and call volume separately before reading the ratio</li>
<li>Compare against the recent range, not against 1.0</li>
<li>Check large against mini — divergence is the signal</li>
<li>Cross-check against open interest changes, which are harder to distort</li>
<li>On big down days, expect the ratio to behave strangely; that is normal, not a signal</li>
</ul>

<p><a href="./">→ Live put/call ratio and volumes</a> ・
<a href="guide-nikkei-options.html">→ Nikkei options field guide</a> ・
<a href="guide-gamma-exposure.html">→ Gamma exposure explained</a></p>
"""),

    "glossary.html": ("Glossary", """
<h1>Glossary — Japanese Index Derivatives for Global Traders</h1>
<p>Terms that appear on this site, and the official file each one comes from.
Japanese readings are given where you are likely to meet them in JPX documents.</p>

<h2>Contracts and expiry</h2>
<ul>
<li><b>SQ (Special Quotation)</b> — the settlement price for expiring options and futures,
calculated from the opening prices of all 225 constituents on the second Friday of the month.
Not the same as the index open.
<a href="guide-sq.html">Full explanation</a></li>
<li><b>Major SQ</b> — March, June, September and December, when futures expire alongside
options.</li>
<li><b>Genkyoku (限月)</b> — contract month. JPX codes these as YYMM, for example 2609
for September 2026.</li>
<li><b>Large / mini / micro</b> — Nikkei futures and options in three sizes. Multipliers are
¥1,000, ¥100 and ¥10 respectively. To compare volume across them, convert to
large-equivalents by dividing mini by 10 and micro by 100.</li>
<li><b>Night session</b> — an evening trading session overlapping US hours, so Japanese
index derivatives react to US moves before the Tokyo cash market reopens.</li>
</ul>

<h2>Positioning</h2>
<ul>
<li><b>Tategyoku (建玉)</b> — open interest. Contracts still outstanding, as opposed to
volume, which counts activity.</li>
<li><b>Wall</b> — a strike carrying unusually heavy open interest, often treated as a
reference level. Restrict candidates to strikes near spot: the largest open interest in the
chain is frequently a deep out-of-the-money legacy position.
<a href="guide-nikkei-options.html">Why</a></li>
<li><b>Teguchi (手口)</b> — trading-participant data. JPX publishes daily volume and weekly
open interest <b>by named firm</b>, with no US equivalent.
<a href="guide-participants.html">How to read it</a></li>
<li><b>COT</b> — the CFTC's Commitments of Traders report, covering CME-listed Nikkei futures.
Anonymous categories, weekly, useful alongside the JPX participant data.</li>
</ul>

<h2>Volatility and flow</h2>
<ul>
<li><b>Nikkei VI</b> — Japan's implied volatility index, the local equivalent of the VIX.</li>
<li><b>Put/call ratio</b> — put volume divided by call volume. For Nikkei large contracts the
measured average is 1.57, so 1.0 is not neutral.
<a href="guide-put-call-ratio.html">Full explanation</a></li>
<li><b>Gamma exposure (GEX)</b> — an estimate of how much dealer hedging amplifies or dampens
index moves, expressed per 1% move. Depends on an unpublished assumption about dealer
positioning. <a href="guide-gamma-exposure.html">Full explanation</a></li>
<li><b>Implied volatility by strike</b> — published by JPX in the daily settlement file,
which is what makes gamma estimation possible from free data alone.</li>
</ul>

<h2>Data sources used on this site</h2>
<ul>
<li><b>JPX</b> — open interest by strike, put and call volume, participant volume and
positions, daily settlement prices including per-strike implied volatility</li>
<li><b>CFTC</b> — Commitments of Traders, weekly</li>
<li><b>CBOE</b> — put/call ratios and SPX option chains</li>
<li><b>FRED</b> — rates, credit spreads and inflation expectations</li>
</ul>
<p>All are public. We publish aggregates and estimates rather than redistributing raw
exchange data.</p>

<p><a href="./">→ Live Nikkei dashboard</a> ・ <a href="us.html">→ US markets</a></p>
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
<li><b>SQ</b>: 特別清算指数。毎月第2金曜に算出され、その限月の取引が清算される。3・6・9・12月は先物も同時に満期を迎える「メジャーSQ」→ <a href="guide-sq.html">解説</a></li>
<li><b>IV(インプライド・ボラティリティ)</b>: オプション価格から逆算される将来変動率の織り込み</li>
<li><b>ガンマエクスポージャー</b>: ディーラーのヘッジ売買が相場を増幅するか抑制するかの推定値 → <a href="guide-gex.html">解説</a></li>
<li><b>デルタヘッジ</b>: オプションの売り手が、値動きのリスクを打ち消すために先物などを売買すること。
この売買が相場を動かす一因になる → <a href="guide-gex.html">解説</a></li>
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
<h1>ガンマエクスポージャーとは — 相場の「静と動」を分ける需給</h1>
<p>当サイトのトップページ(日経225)と<a href="us.html">米国市場ページ</a>で毎日更新している
ガンマエクスポージャーの読み方を解説します。
前提となる仮定とその限界まで、できるだけ正直に説明します。</p>

<h2>まずデルタヘッジから</h2>
<p>オプションを売った側(多くは証券会社=ディーラー)は、価格変動リスクを抱えたままにできません。
そこで<b>先物などを売買してリスクを打ち消します</b>。これがデルタヘッジです。</p>
<p>デルタとは、原資産が1動いたときにオプション価格がどれだけ動くかという感応度です。
たとえばデルタ0.5のコールを100枚売っているディーラーは、
先物を50枚分買っておけば、当面の値動きの影響を打ち消せます。</p>

<h2>ガンマとは — デルタが動くから、ヘッジも動く</h2>
<p>厄介なのは、<b>デルタ自体が原資産価格とともに変化する</b>ことです。
このデルタの変化率がガンマです。</p>
<p>先ほどの例で日経平均が上昇すると、コールのデルタは0.5から0.6へと上がります。
すると必要なヘッジは50枚から60枚に増え、<b>ディーラーは追加で先物を10枚買わなければなりません</b>。
つまり<b>相場が動くたびに、ディーラーは機械的な売買を強いられます</b>。
この強制的な売買が市場に流れ込むため、ガンマの大きさと向きが値動きの性質を左右します。</p>

<h2>プラス圏とマイナス圏</h2>
<p>市場全体の建玉にガンマを掛けて集計したものがガンマエクスポージャーです。
符号によってヘッジ売買の向きが正反対になります。</p>
<ul>
<li><b>プラス圏</b>: ディーラーは<b>上がれば売り・下がれば買い</b>のヘッジをする。
値動きを打ち消す方向に注文が出るため、<b>相場は落ち着きやすく、レンジになりやすい</b></li>
<li><b>マイナス圏</b>: 逆に<b>上がれば買い・下がれば売り</b>を迫られる。
値動きと同じ方向に注文が出るため、<b>動き出すと止まりにくく、急落・急騰が出やすい</b></li>
</ul>
<p>「同じニュースなのに、ある日は無風で、ある日は大きく動く」という現象の一因がこれです。
指標の絶対値より、<b>いまどちらの圏にいるか、そして符号が変わる価格がどこか</b>を見るのが実践的です。</p>

<h2>【核心】この数字は「仮定」の上に成り立っている</h2>
<p>ここが最も重要な注意点です。<b>ディーラーが実際にどちら側のポジションを持っているかは公開されていません。</b>
そのため一般的な計算では、次の仮定を置きます。</p>
<ul>
<li>ディーラーは<b>コールを買い持ち</b>している</li>
<li>ディーラーは<b>プットを売り持ち</b>している</li>
</ul>
<p>当サイトの数値もこの仮定に基づく<b>推定値</b>です。なぜこの仮定が使われるのでしょうか。</p>

<h2>仮定の根拠 — カバードコールETFの膨張</h2>
<p>近年この仮定を支えている大きな要因が、米国の<b>カバードコール型ETF</b>の急拡大です。</p>
<p>カバードコール戦略とは、株式を保有しながらコールオプションを売って
プレミアム収入を得る手法です。高い分配金利回りを求める資金が流入し、
このカテゴリーの残高は<b>合計800億ドルを超える規模</b>に達しています
(代表例としてJEPIが約450億ドル、QYLDが約84億ドル)。</p>
<p>これらのETFは仕組み上<b>コールを継続的に売り続けます</b>。
その反対側でコールを買っているのがディーラーです。
つまり<b>市場構造として、ディーラーがコールの買い持ちに傾きやすい</b>状況が生まれています。
これが「コール買い持ち」仮定の現実的な裏付けです。</p>

<h2>【限界】仮定が崩れることもある</h2>
<p>ただし、この仮定は万能ではありません。少なくとも次の限界があります。</p>
<ul>
<li><b>店頭(OTC)取引が見えない</b>: 大手のカバードコールETFの一部は、
上場オプションではなくELN(仕組債)を通じてコールを売っています。
上場データだけを集計する計算では、<b>この分がまったく捕捉できません</b></li>
<li><b>証券会社の試算と符号が逆になることがある</b>: 実際の顧客フローを見ている大手証券の推計と、
公開データからの推定が食い違うことは珍しくありません。
どちらかが間違いというより、<b>見えている範囲が違う</b>ためです</li>
<li><b>日経225では根拠が弱まる</b>: 上記のカバードコールETFは主に米国株を対象としたものです。
日経225について同じ仮定を置くことは慣行として行われていますが、
<b>米国ほど明確な裏付けがあるわけではありません</b></li>
</ul>
<p>したがって<b>数値の絶対水準を強く信じるべきではありません</b>。
「プラス圏かマイナス圏か」「符号が変わる価格が現値の上か下か」という
大づかみな読み方にとどめるのが安全です。</p>

<h2>当サイトの計算方法</h2>
<p>推定値である以上、計算過程は開示しておくべきと考えています。日経225については以下の通りです。</p>
<ul>
<li><b>建玉</b>: JPXが公表する行使価格別建玉残高(ミニは1/10のラージ換算で合算)</li>
<li><b>ボラティリティ</b>: JPXが日々公表する清算値段データに含まれる<b>行使価格ごとの数値</b>を使用
(一律の値ではなく、実際の値を行使価格ごとに反映しています)</li>
<li><b>対象</b>: 残存45日以内の直近3限月。期先は影響が小さいため除外</li>
<li><b>計算式</b>: ブラック・ショールズ式のガンマに建玉・取引単位・指数水準を掛けて集計</li>
</ul>
<p>すべてJPXの公式公表データのみで完結させています。</p>

<h2>使い方のまとめ</h2>
<ul>
<li>絶対値ではなく<b>符号</b>を見る</li>
<li><b>符号が変わる価格</b>と現値の位置関係を見る(上か下かで相場の性格が変わる)</li>
<li><a href="guide-oi.html">建玉分布</a>の「壁」と重ねて見る(壁の近くで影響が強まる)</li>
<li>SQが近づくほど反応が鋭くなる(残存期間が短いとガンマが大きくなるため)</li>
<li><b>単独では売買判断に使わない</b>。あくまで「動きやすい地合いか否か」の背景情報</li>
</ul>

<h2>あわせて見るもの</h2>
<ul>
<li><a href="us.html">米国市場データ</a> — S&amp;P500のガンマエクスポージャーを毎日更新</li>
<li><a href="guide-oi.html">建玉分布の見方</a> — 「壁」との合わせ読み</li>
<li><a href="guide-sq.html">SQとは</a> — 満期に向けて反応が鋭くなる仕組み</li>
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
<p>ネットポジション=買い建玉−売り建玉。教科書的には、プラスなら買い越し(強気)、
マイナスなら売り越し(弱気)と説明されます。<b>ただし、これを額面通りに受け取ると大きく間違えます。</b></p>

<h2>【最重要】S&amp;P500は「常に売り越し」</h2>
<p>当サイトが蓄積した直近56週(約1年)のデータを見てください。</p>
<ul>
<li><b>S&amp;P500(ES)先物: 56週すべてが売り越し。プラスになった週は一度もありません</b>
(直近は約−30万枚)</li>
<li>ナスダック100(NQ)先物: 56週中50週が売り越し</li>
</ul>
<p>この1年、米国株は基調として上昇しました。
それでもレバレッジファンドは<b>一貫して売り越しのまま</b>でした。
つまり「投機筋が売り越し=弱気だから下がる」という読み方をしていたら、
<b>1年間ずっと外し続けていた</b>ことになります。</p>
<p>なぜこうなるのか。レバレッジファンドの先物売りの多くは<b>相場観ではなくヘッジや裁定</b>だからです。
現物株を買って先物を売る、オプションのポジションを先物で打ち消す、
現物と先物の価格差を取る——こうした取引は、方向感と無関係に恒常的な先物売りを生みます。
<b>COTのネットポジションは「強気/弱気の投票結果」ではありません。</b></p>

<h2>正しい読み方 — 自分自身の過去と比べる</h2>
<p>ではどう使うか。<b>ゼロと比べるのをやめ、その市場自身の過去レンジのどこにいるかで見ます。</b></p>
<p>ESが−30万枚と聞くと大変な弱気に思えますが、
直近1年のレンジは−51.5万枚〜−23.3万枚です。この中で−29.7万枚は<b>上位96パーセンタイル</b>、
つまり<b>1年で最も売り越しが少ない部類=実質的にかなり強気に傾いた状態</b>です。
符号だけを見ていては、まったく逆の結論になります。</p>
<p>同じ考え方を各市場に当てはめると、同じ週でも状況はまるで違って見えます。</p>
<ul>
<li><b>WTI原油</b>: 100パーセンタイル。1年で最も売り越しが小さい(過去最も強気寄り)</li>
<li><b>ユーロ</b>: 1.8パーセンタイル。1年で最も弱気に傾いている</li>
<li><b>円</b>: 3.6パーセンタイル。売り越しが歴史的水準に積み上がった状態</li>
</ul>

<h2>極端な偏りは「燃料」になる</h2>
<p>ポジションが一方向に偏りきると、それ自体が反対方向への燃料になります。
売り越しが極端に積み上がった状態で相場が逆に動き出すと、
<b>買い戻し(ショートカバー)を強いられ、値動きが加速する</b>ためです。</p>
<p>上の例では、円の売り越しが歴史的水準にあります。
これは「円安が続く」というより、<b>何かのきっかけで急激な円高が起きうる状態</b>と読むほうが実用的です。
逆張りのタイミングを計る道具ではありませんが、<b>どちら側にリスクが溜まっているか</b>は掴めます。</p>

<h2>株価と重ねて見る</h2>
<p>当サイトの各パネルには<b>価格の推移を灰色の線で重ねて表示</b>しています。
ポジションと値動きを同じ図で見ると、両者の関係が読み取れます。</p>
<ul>
<li><b>価格が上がり、売り越しも増えている</b> → 戻り売りが積まれている。上昇が続けば踏み上げの燃料に</li>
<li><b>価格が上がり、売り越しが減っている</b> → 買い戻しが上昇を後押ししている。
ただし買い戻しが一巡すると勢いが落ちやすい</li>
<li><b>価格が下がり、買い越しが減らない</b> → 投げがまだ出ていない。下値余地が残っている可能性</li>
</ul>

<h2>3日遅れのデータであることを忘れない</h2>
<p>COTは<b>火曜時点</b>のポジションを<b>金曜(米国時間)</b>に公表します。
つまり手元で見られるのは<b>最短でも3日前の姿</b>です。
火曜から金曜の間に大きなニュースがあれば、実際のポジションはすでに変わっています。
<b>短期売買のシグナルには使えません。</b>数週間〜数か月の資金の傾きを掴む道具と考えてください。</p>

<h2>日経平均にも使える</h2>
<p>CME上場の日経平均先物もCOTの対象です。海外投機筋の日本株への傾きが週次で追えます。
ただし規模はES(数十万枚)に対して日経は数千枚と<b>桁が2つ違う</b>ため、
少数の参加者の動きで数字が振れやすい点に注意してください。
なお日経については、JPXが公表する<a href="guide-teguchi.html">取引参加者別のデータ</a>のほうが
情報量が多く、しかも証券会社名まで分かります。</p>

<h2>あわせて見るもの</h2>
<ul>
<li><a href="us.html">米国市場データ</a> — ES・NQ・CME日経・円・金・WTIのCOT推移を毎週更新</li>
<li><a href="guide-teguchi.html">先物の手口の見方</a> — 日本市場版の「誰が売買しているか」</li>
<li><a href="./">日本市場データ</a> — JPXの取引参加者別建玉(こちらは証券会社名入り)</li>
</ul>
"""),
    "guide-sq.html": ("SQとは", """
<h1>SQとは — 日経225オプションの満期に何が起きるか</h1>
<p>毎月第2金曜になると「SQ」という言葉を目にします。
当サイトのトップにも<a href="./">次回SQまでの日数</a>を表示していますが、
そもそもSQとは何で、なぜ相場の節目として意識されるのかを整理します。</p>

<h2>SQ = 満期の決済価格</h2>
<p>SQ(Special Quotation・特別清算指数)は、
<b>先物やオプションを満期で清算するために使われる特別な価格</b>です。
日経225オプションでは<b>毎月第2金曜日</b>がSQ算出日にあたります。</p>
<p>注意したいのは<b>取引最終日はSQ日ではなく、その前営業日</b>だという点です。
第2金曜がSQなら、木曜が最後に売買できる日になります。
金曜の朝に決まるSQ値で、残った建玉が自動的に清算されます。</p>

<h2>SQ値は「日経平均の始値」ではない</h2>
<p>もっとも誤解されやすいのがここです。
SQ値は<b>日経225採用銘柄それぞれの寄り付き価格を集計して算出</b>されます。</p>
<p>一方、日経平均株価の始値は「その時点で値が付いている銘柄」で計算されるため、
両者は一致しません。寄り付きが遅れる銘柄があると差が開き、
SQ値が日経平均の始値より高くなることも安くなることもあります。
「SQ値」と「当日の日経平均始値」は別物、と覚えておくと混乱しません。</p>

<h2>権利行使される・されないの境目</h2>
<p>満期時点でイン・ザ・マネー(ITM)の買い建玉は権利行使され、差額が受け取れます。
コールなら次の計算です。</p>
<p style="padding:10px 14px; border-left:3px solid #0f8a5f; background:#ffffff;">
(SQ値 − 権利行使価格) × 枚数 × 1,000</p>
<p>プットは逆に(権利行使価格 − SQ値)です。
アウト・オブ・ザ・マネー(OTM)のまま満期を迎えたオプションは、価値ゼロで消滅します。
<b>SQ値が権利行使価格をわずかに上回るか下回るかで、損益が大きく変わる</b>——
これがSQ前に売買が集中する理由のひとつです。</p>

<h2>なぜSQ前に相場が動きやすいと言われるのか</h2>
<p>断定はできませんが、次のような需給が重なりやすいことが背景として挙げられます。</p>
<ul>
<li><b>建玉の手仕舞い</b>: 満期を持ち越さず決済する動きが増え、売買が膨らみます</li>
<li><b>ヘッジの巻き戻し</b>: オプションを売っている側は、満期が近づくほど
ヘッジのための先物売買が細かくなり、値動きに影響しやすくなります
(→ <a href="guide-gex.html">ガンマエクスポージャーとは</a>)</li>
<li><b>建玉が厚い価格帯の意識</b>: 多くの建玉が残る権利行使価格の周辺では、
その水準を挟んだ攻防になりやすいと見られています
(→ <a href="guide-oi.html">建玉分布の見方</a>)</li>
</ul>
<p>ただし「SQ前は必ず荒れる」わけではありません。
実際には静かに通過する月もあります。</p>

<h2>メジャーSQとマイナーSQ</h2>
<ul>
<li><b>メジャーSQ(3月・6月・9月・12月)</b>: オプションに加えて<b>先物も同時に満期</b>を迎えます。
清算される金額が大きくなるため、より注目されます</li>
<li><b>マイナーSQ(それ以外の月)</b>: オプションのみの満期です</li>
</ul>

<h2>【実データ】期近より期先のほうが建玉が多いことがある</h2>
<p>「直近の限月がいちばん活発なはず」と思いがちですが、実際には違います。
2026年8月7日(8月SQの1週間前)時点の建玉合計を見てください。</p>
<ul>
<li>8月限(マイナーSQ・残り1週間): <b>169,955枚</b></li>
<li>9月限(メジャーSQ・残り約5週間): <b>189,160枚</b></li>
<li>10月限: 29,792枚</li>
</ul>
<p><b>満期が遠い9月限のほうが、期近の8月限より約2万枚も多い</b>状態です。
これはメジャーSQである9月に、四半期単位のヘッジや長めのポジションが集まるためと考えられます。
四半期末の決算・配当・機関投資家の期間設定が9月に寄ることも影響します。</p>
<p><b>「期近だけ見ていると市場の関心を見誤る」</b>ということです。
当サイトが直近3限月を並べて表示しているのは、この偏りを確認できるようにするためです。</p>

<h2>【実データ】建玉はSQ直前まで「増える」</h2>
<p>もうひとつの誤解が「SQが近づくと建玉は整理されて減っていく」というものです。
同じ8月限の建玉推移を追うと、実際は逆でした。</p>
<ul>
<li>7月17日(SQの約4週間前): 137,311枚</li>
<li>7月31日(約2週間前): 161,895枚</li>
<li>8月7日(約1週間前): <b>169,955枚</b></li>
</ul>
<p>3週間で<b>24%増加</b>しています。満期が近いオプションは価格が安く反応も鋭いため、
むしろ直前になるほど短期の売買が集まるのです。</p>
<p>建玉が実際に消えるのは<b>SQを通過した瞬間</b>です。
つまり「じわじわ減っていく」のではなく、<b>直前まで積み上がり、一気に消滅する</b>という形になります。
だからこそSQ前後で需給の景色が急に変わります。</p>

<h2>ミニオプションは毎週SQがある</h2>
<p>見落とされがちですが、<b>日経225ミニオプションには週次の満期(ウィークリー)があります</b>。
第2金曜の月次SQに加えて、他の週の金曜にも満期が訪れます。</p>
<p>そのため、月次SQでない週でも<b>満期に伴う需給は毎週発生しています</b>。
ミニは取引単位がラージの1/10で個人が参加しやすく、
短期の値動きに対する影響は無視できません。
当サイトではミニの建玉分布も別途掲載しているので、
月次SQ以外の週も満期の偏りを確認できます。</p>

<h2>当サイトでの見方</h2>
<p>トップページに<b>次回SQまでの日数</b>を表示しているほか、
<a href="./#oi">行使価格別の建玉分布</a>を毎営業日更新しています。
SQが近づくにつれて、現値の周辺にどれだけ建玉が残っているか、
どの価格帯が厚いままなのかを追うと、満期に向けた地合いが掴みやすくなります。</p>

<h2>あわせて見るもの</h2>
<ul>
<li><a href="guide-oi.html">建玉分布の見方</a> — 「壁」はどう読むか</li>
<li><a href="guide-pcr.html">Put/Callレシオとは</a> — 市場心理の偏りを見る</li>
<li><a href="glossary.html">用語集</a> — SQ・限月・デルタなどの基本用語</li>
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

<h2>【実データ】同じ会社が、1年間ずっと同じ側にいる</h2>
<p>週次の建玉残高を1年分(52週)集計すると、
手口を「相場観」と読んではいけない理由がはっきり見えてきます。
2025年8月〜2026年7月の日経225先物・miniで、各社のネット(買い建玉−売り建玉)の平均と、
その符号が変わらなかった週の割合を調べた結果です。</p>
<ul>
<li><b>HSBC証券</b>: 平均 −31,604枚 / <b>52週すべて売り越し(100%)</b></li>
<li><b>SMBC日興証券</b>: 平均 +4,927枚 / <b>52週すべて買い越し(100%)</b></li>
<li><b>モルガンMUFG証券</b>: 平均 −14,029枚 / 98%が売り越し</li>
<li><b>野村証券</b>: 平均 +18,065枚 / 92%が買い越し</li>
<li><b>ソシエテG証券</b>: 平均 +19,106枚 / 90%が買い越し</li>
</ul>
<p>この1年、日経平均は大きく上下しました。<b>それでも各社の向きはほとんど変わっていません。</b></p>
<p>もし「HSBCの売り越し=外資が弱気」と読んでいたら、
<b>1年間ずっと弱気と判定し続けていた</b>ことになります。
これは相場観ではなく、<b>その会社のビジネスの形</b>から来る構造的な偏りです。
現物株や他のデリバティブとの組み合わせ、顧客注文の裏側で持つポジション、
裁定取引に伴うヘッジなどが、恒常的に同じ方向のポジションを生みます。</p>

<h2>正しい読み方 — 「平常値からのズレ」を見る</h2>
<p>そこで実用的なのは、<b>ゼロと比べるのではなく、その会社の平常値と比べる</b>ことです。</p>
<p>たとえばHSBCの平常が−31,604枚なのですから、
ある週に−5,000枚しかなければ、<b>絶対値では売り越しでも、実質的には大きく買い戻した週</b>です。
逆に−50,000枚まで膨らめば、平常より積極的に売った週と読めます。</p>
<ul>
<li><b>×</b> 「A社が売り越しているから弱気」</li>
<li><b>○</b> 「A社の売り越しが、いつもより2万枚少ない」</li>
</ul>
<p>同じ理屈で、日々の手口(取引高)も<b>その会社の普段の枚数</b>と比べてください。
普段5万枚の会社の5万枚に情報はありませんが、普段1万枚の会社が5万枚出していれば異常です。</p>

<h2>実際の使い方</h2>
<p>まとめると、次の順に見るのが実際的です。</p>
<ol>
<li><b>上位のシェア</b>を見る。上位数社で全体の6割以上を占める日は、
限られた参加者が値動きを主導していた可能性があります。
逆に上位のシェアが下がっている日は、参加者の裾野が広がっているとも読めます</li>
<li><b>各社の平常値からのズレ</b>を見る。普段と違う会社が上位に来ていないか</li>
<li><b>ラージとミニを比べる</b>。ラージ(海外勢中心)とミニ(個人も参加)で
上位の顔ぶれが食い違う日は、プロと個人の見方が割れているサインかもしれません</li>
<li><b>方向を知りたいときは他のデータへ</b>。手口に方向は含まれないので、
週次の建玉残高や<a href="guide-cot.html">COT</a>、
<a href="guide-pcr.html">Put/Callレシオ</a>で補います</li>
</ol>

<h2>あわせて見るもの</h2>
<ul>
<li><a href="./#pv">日経225先物・miniの手口上位</a> — 毎営業日更新(JPX公表は17:45ごろ)</li>
<li><a href="guide-oi.html">建玉分布の見方</a> — 行使価格に積み上がった「壁」の読み方</li>
<li><a href="guide-cot.html">COTレポートの見方</a> — 米国先物での投資家区分別ポジション</li>
<li><a href="guide-pcr.html">Put/Callレシオとは</a> — 市場心理の偏りを見る</li>
</ul>
"""),
    "guide-oi.html": ("建玉分布の見方", """
<h1>建玉分布の見方 — 「壁」はどう読むか</h1>
<p>当サイトのトップに毎日掲載している「行使価格別 建玉分布」の読み方を解説します。
実際に当サイトで観測されたデータを例に、よくある誤読も含めて説明します。</p>

<h2>建玉(たてぎょく)とは</h2>
<p>建玉(Open Interest)は、まだ決済されずに残っているオプション契約の残高です。
出来高が「その日に取引された量」であるのに対し、建玉は「積み上がっているポジションの総量」を表します。</p>
<ul>
<li><b>出来高</b>: その日1日だけの取引量。翌日には0にリセットされる</li>
<li><b>建玉</b>: 過去からの累積。決済されるまで残り続ける</li>
</ul>
<p>同じ1枚の売買でも、建玉が増えるか減るかは<b>売り手と買い手それぞれが新規なのか決済なのか</b>で決まります。</p>
<ul>
<li>新規買い × 新規売り → <b>建玉は+1</b>(新しい契約が生まれた)</li>
<li>決済売り × 決済買い → <b>建玉は−1</b>(契約が消滅した)</li>
<li>新規買い × 決済売り(またはその逆) → <b>建玉は変わらない</b>(持ち手が入れ替わっただけ)</li>
</ul>
<p>つまり「出来高が多いのに建玉が増えていない」日は、新しいポジションが積まれたのではなく
<b>既存ポジションの手仕舞いや入れ替えが中心だった</b>可能性が高い、と読めます。
当サイトが出来高と建玉の両方を並べて掲載しているのはこのためです。</p>

<h2>「壁」の考え方 — なぜ建玉が値動きに影響するのか</h2>
<p>特定の行使価格に大量の建玉が積み上がっている状態は、俗に「壁」と呼ばれます。
壁が意識される理由は、心理的なものだけではなく<b>オプションを売った側のヘッジ売買</b>にあります。</p>
<p>オプションの売り手(多くは証券会社=ディーラー)は、価格変動リスクを抱えたままにはできないので、
先物などで打ち消す売買(デルタヘッジ)を行います。
現値が大きな建玉のある行使価格に近づくと、この調整売買の量が増えるため、
その価格帯で値動きの性質が変わりやすくなります。</p>
<ul>
<li><b>コール建玉の壁(現値より上)</b>: 上値が重くなりやすい水準と解釈されます</li>
<li><b>プット建玉の壁(現値より下)</b>: 下値の目処として意識されやすい水準です</li>
</ul>

<h2>【重要】「最大建玉=壁」ではない</h2>
<p>最も多い誤読が、<b>全体で建玉が最大の行使価格を、そのまま壁とみなしてしまうこと</b>です。</p>
<p>実例を挙げます。2026年8月上旬、日経225オプションで<b>建玉が最も多かったのはプット30,000円で約5,600枚</b>でした。
しかし当時の日経平均は66,000円前後。<b>現値の約半分(−53%)という、まず到達しない水準</b>です。
この建玉は8日間で5,592枚→5,623枚とほとんど動いておらず、
恐らく長期の保険や過去の残骸で、<b>足元の値動きとはほぼ無関係</b>です。</p>
<p>一方、同じ時期の<b>コール70,000円は4,490枚→4,910枚と明確に増減していました</b>。
枚数では30,000円プットに負けますが、現値から+6%程度で<b>実際に到達しうる水準</b>であり、
売買も活発です。壁として意味があるのはこちらです。</p>
<p>そこで当サイトでは、<b>現値から上下10%以内</b>に範囲を限定し、
その中でコール建玉が最大の行使価格を「上の壁」、プット建玉が最大の行使価格を「下の壁」としています。
遠い行使価格の巨大建玉に引きずられないようにするためです。</p>

<h2>「育っているか、崩れているか」を見る</h2>
<p>壁の位置そのものより、<b>前日からどう変化したか</b>の方が情報量があります。</p>
<ul>
<li><b>壁が育っている(建玉が増加)</b>: その水準を意識する参加者が増えている</li>
<li><b>壁が崩れている(建玉が減少)</b>: ポジションが手仕舞われ、抑える力が弱まっている可能性</li>
</ul>
<p>当サイトでは行使価格別の前日比増減を毎日掲載しているので、この変化を追えます。</p>

<h2>壁は「必ず止まる水準」ではない</h2>
<p>むしろ<b>抜けたときの方が動きが速くなることがあります</b>。
壁を前提に積まれていたヘッジポジションが一斉に巻き戻されるためで、
「上の壁を上抜けたら上放れが加速する」といった動きはこれで説明されます。
壁は「止まる保証」ではなく、<b>値動きの性質が変わりやすいポイント</b>として見るのが実践的です。</p>

<h2>ミニオプションの扱い</h2>
<p>日経225オプションにはラージ(取引単位1,000倍)とミニ(100倍)があります。
当サイトでは<b>ミニの建玉を1/10してラージ換算で合算</b>し、市場全体の分布として掲載しています。
ミニだけの分布も別途掲載しているので、参加者層による偏りの違いも確認できます。</p>

<h2>SQに向けた見方</h2>
<p>建玉は限月ごとに集計されます。SQ(特別清算指数の算出日)が近づくと、
残存期間が短くなるぶんヘッジ調整の反応が鋭くなり、<b>現値付近の建玉の影響が大きくなります</b>。
逆にSQ通過後は建玉が一度リセットされ、翌限月に積み直されていきます。
当サイトでは直近3限月分を毎日更新しているので、限月ごとの偏りも確認できます。</p>

<h2>やりがちな誤読まとめ</h2>
<ul>
<li><b>遠い行使価格の巨大建玉を壁と見てしまう</b> → 現値±10%程度に絞って見る</li>
<li><b>建玉の多さ=売り手が多い、と決めつける</b> → 建玉は売り買い両方の合計で、どちらが主体かは分からない</li>
<li><b>壁で必ず反転すると考える</b> → 抜けたときはむしろ加速しやすい</li>
<li><b>限月をまたいで合計する</b> → 期近と期先では影響力がまったく違う</li>
</ul>

<h2>あわせて見るもの</h2>
<ul>
<li><a href="guide-pcr.html">Put/Callレシオとは</a> — 市場心理の偏りを1つの数字で見る</li>
<li><a href="guide-gex.html">ガンマエクスポージャーとは</a> — ヘッジ売買が値動きを増幅するか抑えるか</li>
<li><a href="guide-sq.html">SQとは</a> — 満期の決済価格と、建玉が整理される仕組み</li>
<li><a href="guide-start.html">日経225オプションを始めるには</a> — 取引環境の整え方</li>
</ul>
"""),

    "guide-pcr.html": ("Put/Callレシオとは", """
<h1>Put/Callレシオとは — 1.0の上下で何が分かるか</h1>
<p>当サイトのトップに毎日掲載しているPut/Callレシオ(PCR)の見方を解説します。
教科書的な説明だけでなく、<b>実際のデータで裏切られた例</b>も含めて紹介します。</p>

<h2>計算方法</h2>
<p>Put/Callレシオ = プットの出来高 ÷ コールの出来高。
当サイトでは日経225オプションの日通し出来高(JPX公表)から毎日算出しています。
ラージとミニをそれぞれ計算し、ミニは1/10のラージ換算で合算した全体値も掲載しています。</p>

<h2>読み方の基本</h2>
<ul>
<li><b>1.0超(プット優勢)</b>: 下落に備えるヘッジ需要や弱気の見方が強い状態</li>
<li><b>1.0未満(コール優勢)</b>: 上昇を取りにいく動きが優勢な状態</li>
</ul>
<p>ただし日経225オプションは<b>常時1.0を超えているのが普通</b>です。
機関投資家の下落ヘッジ(プット買い)が恒常的に入るためで、
2026年7〜8月の実測でもラージのPCRは平均1.57、多くの日で1.2〜2.3のレンジにありました。
<b>「1.0を超えたから弱気」ではなく、「普段のレンジから外れたか」で見る必要があります。</b></p>

<h2>【落とし穴1】出来高に売り買いの区別はない</h2>
<p>これが最も重要な限界です。<b>出来高は「取引が成立した量」であって、買いか売りかの情報を含みません。</b></p>
<p>PCRが上がったとき、実際に起きている可能性は少なくとも4通りあります。</p>
<ul>
<li>新たにプットが<b>買われた</b>(弱気・ヘッジ) ← 一般に想定される解釈</li>
<li>プットが<b>売られた</b>(プレミアム収入狙い・強気の可能性すらある)</li>
<li>既存のプットが<b>利益確定で手仕舞われた</b></li>
<li>コールの取引が単に減っただけで、プットは変わっていない</li>
</ul>
<p>PCRは「オプション市場が活発に動いた方向」を示すだけで、<b>方向感そのものを示す指標ではありません。</b></p>

<h2>【落とし穴2】暴落した日にPCRが下がることがある</h2>
<p>実例です。2026年7月28日、日経平均は<b>−3.95%の急落</b>となりました。
「暴落したのだからプットが買われ、PCRは跳ね上がったはず」と考えたくなります。
しかし実際は逆でした。</p>
<ul>
<li>7月27日: プット21,148 / コール10,603 → <b>PCR 1.995</b></li>
<li>7月28日(−3.95%): プット35,728 / コール25,764 → <b>PCR 1.387</b></li>
</ul>
<p>プット出来高は確かに1.7倍に増えました。しかし<b>コール出来高が2.4倍に急増した</b>ため、
比率としてはむしろ低下したのです。</p>
<p>急落局面では、①保有プットの利益確定、②反発を狙った安いコールの買い、
③下落で不要になったコールの処分、が同時に起こります。
結果として<b>コール側の出来高が跳ね上がり、PCRを押し下げます</b>。
「PCRが下がった=強気になった」と読むと、完全に事実を取り違えることになります。</p>

<h2>【落とし穴3】同じ2.0でも中身はまったく違う</h2>
<p>PCRは比率なので、<b>分子が増えても分母が減っても上がります</b>。同じ水準でも意味が正反対になりえます。</p>
<ul>
<li>7月21日: プット<b>33,485</b> / コール15,796 → PCR 2.12<br>
→ プット出来高そのものが急増。<b>活発な下落ヘッジが入った「厚い」2.1</b></li>
<li>7月23日: プット<b>16,662</b> / コール8,446 → PCR 1.97<br>
→ プット出来高は逆に半減。<b>コールが消えたことによる「薄い」2.0</b></li>
</ul>
<p>数字上はほぼ同じですが、前者は活発なヘッジ需要、後者は市場全体の閑散を示しています。
<b>PCRを見るときは必ず、分子と分母の絶対量もセットで確認してください。</b>
当サイトがプット出来高・コール出来高を併記しているのはこのためです。</p>

<h2>ミニとラージは別の市場と考える</h2>
<p>当サイトではラージとミニのPCRを別々に計算しています。すると明確な差が出ます。</p>
<ul>
<li>ラージのPCR: 平均<b>1.57</b>(2026年7月末〜8月上旬)</li>
<li>ミニのPCR: 平均<b>0.91</b>(同期間)</li>
</ul>
<p>ほぼ一貫して<b>ミニの方が低く、しばしば1.0を割ります</b>。同じ日経225オプションでこれだけ差が出るのは、
参加者層が違うためと考えられます。ラージは取引単位が大きく機関投資家のヘッジ(プット買い)が中心、
ミニは相対的に個人が多く、上昇を取りにいくコール売買の比重が高い、という構図です。</p>
<p><b>「市場は弱気か」を見るならラージ、「個人の温度感」を見るならミニ</b>、という使い分けができます。
両者の差が急に縮まる・逆転する局面は、どちらかの層の見方が変わったサインとして注目できます。</p>

<h2>逆張り指標としての使い方と限界</h2>
<p>PCRは逆張り指標として使われることも多い指標です。
プットが極端に買われた状態は悲観の織り込みが進んだ状態とも解釈でき、
歴史的にPCRの極端な高まりが相場の転換点付近で観測されることがあります。</p>
<p>ただし<b>「極端」の基準は市場や時期によって変わります</b>。
日経225で1.5は平常運転ですが、別の市場では異常値かもしれません。
絶対水準を他所から借りてこず、<b>その市場自身の過去レンジと比べる</b>ことが必要です。</p>

<h2>水準よりも「変化」を見る</h2>
<p>PCRは単日の水準だけで判断するとノイズが大きい指標です。
当サイトでは日次の推移をチャートで蓄積しているので、
「普段のレンジからどれだけ外れたか」「急変した日は何があったか」という
変化に注目する使い方をおすすめします。
建玉分布と併せて見ると、<b>出来高(その日の動き)とポジション残高(積み上がり)</b>の両面から確認できます。</p>

<h2>あわせて見るもの</h2>
<ul>
<li><a href="guide-oi.html">建玉分布の見方</a> — 価格帯ごとのポジションの偏り</li>
<li><a href="guide-teguchi.html">先物の手口の見方</a> — 誰が売買しているかを見る</li>
<li><a href="guide-start.html">日経225オプションを始めるには</a></li>
</ul>
"""),

    "guide-start.html": ("日経225オプションを始めるには", """
<p style="font-size:0.8em; color:#4b5563;">※本ページにはプロモーションが含まれる場合があります</p>
<h1>日経225オプションを始めるには — 最初の1枚を建てるまでに知っておくこと</h1>
<p>当サイトのデータを見て「実際に触ってみたい」と思った方向けのページです。
口座の作り方より先に、<b>いくら必要で、何が起きるのか</b>を実際の価格データで確認します。
知らずに始めると高い授業料になる部分から順に説明します。</p>

<h2>いくらから買えるのか — 実際の価格で見る</h2>
<p>オプションの値段(プレミアム)は、行使価格と満期までの日数で大きく変わります。
2026年8月7日の清算値(残り7日の8月限、日経平均65,607円)を例に、
実際に必要な金額を計算してみます。</p>
<p><b>必要額 = 清算値 × 取引単位</b>です。ラージは1,000倍、ミニは100倍。</p>
<div class="tbl-wrap"><table>
<thead><tr><th>買うもの</th><th>清算値</th><th>ラージ(×1,000)</th><th>ミニ(×100)</th></tr></thead>
<tbody>
<tr><td>コール 66,000円(現値のすぐ上)</td><td>890円</td><td>890,000円</td><td>89,000円</td></tr>
<tr><td>コール 67,000円</td><td>500円</td><td>500,000円</td><td>50,000円</td></tr>
<tr><td>コール 68,000円</td><td>278円</td><td>278,000円</td><td>27,800円</td></tr>
<tr><td>コール 70,000円</td><td>71円</td><td>71,000円</td><td><b>7,100円</b></td></tr>
<tr><td>プット 60,000円</td><td>59円</td><td>59,000円</td><td><b>5,900円</b></td></tr>
</tbody>
</table></div>
<p>同じ市場でも、選ぶ行使価格と取引単位で<b>必要額は100倍以上違います</b>。
現値近くのラージを買えば89万円ですが、<b>ミニで遠い行使価格なら1万円を切ります</b>。
「オプションは大金がないとできない」は正しくありません。</p>

<h2>【重要】安いオプションは「当たりにくいから安い」</h2>
<p>ここが最初につまずくところです。
7,100円で買えるコール70,000円は割安に見えますが、<b>安いのには理由があります</b>。</p>
<p>同じ清算値データに含まれるボラティリティから、
満期時に権利行使価格を超えている確率を計算すると次のようになります。</p>
<ul>
<li>コール70,000円(7,100円): <b>約6%</b></li>
<li>コール68,000円(27,800円): 約18%</li>
<li>コール67,000円(50,000円): 約29%</li>
<li>プット60,000円(5,900円): <b>約5%</b></li>
</ul>
<p>つまり<b>7,100円のオプションは、9割以上の確率で価値ゼロになって消えます</b>。
市場は「当たる確率」を織り込んで値段を付けているので、
安いものほど当たらないというだけの話です。
<b>安さで選ぶと、ほぼ確実に負けます。</b></p>
<p>逆に言えば、<b>買いの損失は支払った金額が上限</b>です。
7,100円を払ったなら、どれだけ相場が逆に行っても損失は7,100円で確定します。
この性質を理解したうえで金額を決めることが出発点になります。</p>

<h2>買いと売りは、まったく別の取引</h2>
<p>同じオプションでも、買い手と売り手ではリスクの形が正反対です。
<b>ここを混同するのが最も危険です。</b></p>
<div class="tbl-wrap"><table>
<thead><tr><th></th><th>買い</th><th>売り</th></tr></thead>
<tbody>
<tr><td>支払い/受取</td><td>プレミアムを支払う</td><td>プレミアムを受け取る</td></tr>
<tr><td>証拠金</td><td><b>不要</b>(代金のみ)</td><td><b>必要</b></td></tr>
<tr><td>最大利益</td><td>理論上は青天井</td><td>受け取ったプレミアムまで</td></tr>
<tr><td>最大損失</td><td><b>支払った金額まで</b></td><td><b>理論上は無限</b></td></tr>
<tr><td>勝ちやすさ</td><td>外れることが多い</td><td>当たることが多い</td></tr>
</tbody>
</table></div>
<p>売りは「当たることが多い」代わりに、<b>まれに起きる大損失で全部を失う</b>形です。
毎月コツコツ利益が出ていても、一度の急変動で退場することが起こりえます。
<b>始めるなら買いから</b>、というのはこの非対称性が理由です。</p>

<h2>証拠金の考え方</h2>
<p>オプションを<b>売る</b>場合と先物を取引する場合には証拠金が必要です。</p>
<p>金額は固定ではありません。JPXが定める計算方式に基づき、
<b>相場の変動が大きくなるほど必要額が増える</b>仕組みになっています。
さらに証券会社が独自に上乗せすることもあります。</p>
<p>実務上おさえておくべきなのは次の点です。</p>
<ul>
<li><b>必要額は日々変わる</b>。持っている間に増えることがあります</li>
<li><b>足りなくなると追加入金を求められる</b>(追証)。期限までに入れられないと強制的に決済されます</li>
<li><b>相場が荒れた時ほど必要額が上がる</b>。つまり最も苦しい局面で資金を要求されます</li>
</ul>
<p>正確な金額は取引する証券会社の画面で必ず確認してください。
<b>買いだけなら証拠金は不要</b>で、この心配はありません。</p>

<h2>最初に決める3つのこと</h2>
<p>実際に注文を出すときは、次の3つを選ぶことになります。</p>
<ol>
<li><b>限月(いつ満期か)</b> — 期近は安いが時間の減りが速い。
迷うなら残存の短すぎないものを。→ <a href="guide-sq.html">SQとは</a></li>
<li><b>行使価格(どの水準か)</b> — 現値に近いほど高く当たりやすい。
建玉が厚い水準は意識されやすい。→ <a href="guide-oi.html">建玉分布の見方</a></li>
<li><b>枚数</b> — <b>最大損失=プレミアム×枚数</b>。失っても困らない額に収める</li>
</ol>
<p>当サイトのトップでは、この判断に使う建玉分布・Put/Callレシオ・
ガンマエクスポージャーを毎営業日更新しています。</p>

<h2>始める前に理解しておくべきリスク</h2>
<p>オプション取引は仕組み上、買い方の損失は支払ったプレミアムに限定されますが、
<b>売り方の損失は理論上限定されません</b>。また証拠金取引のためレバレッジがかかります。
少額のミニオプション・買い戦略から始める、証拠金に余裕を持つなど、
リスク管理を最優先にしてください。当サイトは特定の取引を推奨するものではありません。</p>

<h2>取引口座を用意する</h2>
<p>ここまでの内容を踏まえて実際に取引したい場合、
証券会社の総合口座に加えて<b>先物・オプション取引口座</b>の開設が必要です。</p>
<ol>
<li>ネット証券で総合口座を開設(無料・ネット完結)</li>
<li>同じ証券会社で先物・オプション口座を申請(投資経験等の審査があります)</li>
<li>入金して取引開始</li>
</ol>
<p>証券会社を選ぶときは次の点を見てください。</p>
<ul>
<li><b>ミニオプションを扱っているか</b> — 上の表のとおり、必要額が10分の1になります。
小さく始めたいなら最も重要な条件です</li>
<li><b>手数料</b> — オプションは1枚あたりの体系。各社で差があります</li>
<li><b>取引ツール</b> — オプションのボード表示やリスク管理機能の使いやすさ</li>
</ul>
<p>主要ネット証券の先物・オプション取引は、条件が同じではありません。
とくに<b>ミニオプションは扱っていない会社があります</b>。各社の公表値をまとめました。</p>
<div class="tbl-wrap"><table>
<thead><tr><th>証券会社</th><th>日経225<br>ミニオプション</th><th>日経225<br>オプション</th><th>225先物<br>(ラージ)</th><th>225mini</th><th>マイクロ<br>先物</th></tr></thead>
<tbody>
<tr><td>SBI証券</td><td><b>取扱いあり</b><br>0.22%(最低19.8円)</td><td>0.22%<br>(最低220円)</td><td>275円</td><td>38.5円</td><td>11円</td></tr>
<tr><td>三菱UFJ eスマート証券<br>(旧auカブコム証券)</td><td><b>取扱いあり</b><br>19.8円</td><td>0.22%<br>(最低220円)</td><td>275円</td><td>38.5円</td><td>11円</td></tr>
<tr><td>松井証券</td><td><b>取扱いなし</b></td><td>0.22%<br>(最低220円)</td><td><b>220円</b></td><td>38.5円</td><td>11円</td></tr>
</tbody>
</table></div>
<p style="font-size:.9em;color:#666">手数料は1枚あたり・税込。2026年8月22日に各社公式サイトで確認した値です。
手数料と取扱商品は変更されることがあるため、口座開設の前に必ず各社公式サイトで最新の条件をご確認ください。</p>

<p>この表から読み取れることを整理します。</p>
<ul>
<li><b>1万円以下から試したいなら、ミニオプションを扱う会社を選ぶ</b> —
上の価格表のとおり、ミニなら遠い行使価格で1万円を切ります。
扱っていない会社では、この選択肢そのものがありません</li>
<li><b>ラージ先物中心なら松井証券が安い</b> — 220円で3社中最安です。
松井証券には返済期限をその日のセッション内に限る「一日先物取引」もあり、
日中で完結させる使い方ならさらに低コストになります</li>
<li><b>マイクロ先物は3社とも11円で横並び</b> — 日経225miniのさらに10分の1の単位で、
金額を絞って先物の値動きに慣れたい場合の入口になります</li>
</ul>
<p>なお松井証券のオプションは<b>取扱限月が直近4限月に限られます</b>。
先の限月を建てたい場合は、この点も確認してください。</p>

<p><b>松井証券</b>はラージ先物・マイクロ先物・一日先物を低コストで扱い、取引ツールや情報提供も充実しています。
口座開設は無料・ネット完結で、まず総合口座を開いてから先物・オプション口座を申請する流れです。
→ <a href="https://px.a8.net/svt/ejp?a8mat=4B83D5+490F8Y+3XCC+64C3M" rel="nofollow">松井証券の口座開設(公式・PR)</a><img border="0" width="1" height="1" src="https://www17.a8.net/0.gif?a8mat=4B83D5+490F8Y+3XCC+64C3M" alt=""></p>
<div style="text-align:center; margin: 16px 0;">
<a href="https://px.a8.net/svt/ejp?a8mat=4B83D5+490F8Y+3XCC+6HMHT" rel="nofollow">
<img border="0" width="300" height="250" alt="松井証券" src="https://www21.a8.net/svt/bgt?aid=260718089257&wid=001&eno=01&mid=s00000018318001090000&mc=1"></a>
<img border="0" width="1" height="1" src="https://www11.a8.net/0.gif?a8mat=4B83D5+490F8Y+3XCC+6HMHT" alt="">
</div>
<p><b>SBI証券</b>は上の表でミニオプションを扱う2社のうちの一つです。
日経225先物・オプションの専用ページに、取扱商品と手数料がまとまっています。
総合口座を開いたうえで、先物・オプション取引口座を別途申し込む流れです。
(PR) <a href="https://h.accesstrade.net/sp/cc?rk=010030jl00ovxn" rel="nofollow" referrerpolicy="no-referrer-when-downgrade">SBI証券の日経225<img src="https://h.accesstrade.net/sp/rr?rk=010030jl00ovxn" width="1" height="1" border="0" alt=""></a></p>

<p><b>三菱UFJ eスマート証券</b>(旧auカブコム証券)も、上の表でミニオプションを扱う2社のうちの一つです。
ただし手数料の体系がSBI証券と違います。SBI証券のミニオプションが「売買代金の0.22%・最低19.8円」なのに対し、
こちらは<b>1枚あたり19.8円の定額</b>です。</p>
<p>ミニオプションは指数1ポイント＝100円なので、プレミアムが90ポイント(売買代金9,000円)を超えたところで
0.22%が19.8円を上回ります。<b>ATM付近や期近の、プレミアムが高いミニオプションを建てるほど定額のほうが安くなる</b>
という関係です。逆に、遠い行使価格を数百円で買うような使い方なら、どちらも19.8円で差はつきません。</p>
<p>先物では<b>先物SOR</b>で約定した場合、日経225先物(ラージ)が220円、日経225miniが27.5円になります。
通常の立会は表のとおり275円・38.5円なので、ラージ中心の使い方ならSORの成立次第で松井証券の220円と並ぶ水準まで下がります。
口座開設は、総合口座を開いたうえで先物・オプション取引口座を別途申し込む流れです。</p>
<!-- 【アフィリエイトリンク: 三菱UFJ eスマート証券】
     アクセストレード(952022)で2026-08-28に提携承認済み。ただし広告主による
     「リンク設置前の最終チェック」が条件なので、まだ貼らない。
     掲載面(この段落)を完成させてASPに連絡 → 最終チェック通過 → ここに設置する。 -->

<p>なお、現物株・信用取引の口座を手数料重視で選びたい方には次のような選択肢もあります:
<a href="https://px.a8.net/svt/ejp?a8mat=4B83D5+4CL0VM+1WP2+15QHIA" rel="nofollow">日本株を始めるなら【DMM 株】!(PR)</a><img border="0" width="1" height="1" src="https://www17.a8.net/0.gif?a8mat=4B83D5+4CL0VM+1WP2+15QHIA" alt=""></p>

<!-- 提携状況(2026-08-21に各ASPの管理画面で実際に確認した内容)。
     承認されたものからここに広告リンクを差し替える。

     アクセストレード 申請中:
       IG証券 8,790円 / GMOクリック証券CFD 9,524円 / 岡三オンライン くりっく株365 953円
       インヴァスト証券 トライオートFX 19,500円 / トライオートCFD 12,000円 / アイネットFX 7,619円
     A8.net 申込中:
       GMOクリック証券 証券取引口座 3,000円 / サクソバンク証券CFD 5,530円 / サクソバンク証券 外国株式 3,160円

     アクセストレード 提携却下 → 再申請の結果:
       却下分は管理画面から再申請できない(お問い合わせ区分[提携>再申請]が必要)。
       2026-08-21に依頼し、2026-08-22にASPから回答。
       いずれも「広告主による掲載面チェックあり・当該サービスに関する記事提出が必須」。
       掲載面として、上の「取引口座を用意する」に3社の手数料比較表を追加した(2026-08-22)。
       → SBI証券 300円: **2026-08-26に提携承認。** 上の比較表の直後に、
         広告素材(140673)「SBI証券の日経225」のテキストリンクを設置済み。
         リンクコードは改変禁止(パートナー利用規約第15条)なのでアンカー文言は原文のまま。
         PR表記はアンカーの外に置いている。
       → 三菱UFJ eスマート証券 3,000円: **2026-08-28に提携承認。**
         ただし「アフィリエイトリンク設置前の最終チェック」が条件についている。
         掲載面としてSBI証券の段落の直後に解説を追加した(2026-08-29)。手数料体系の
         違い(定額19.8円 対 0.22%最低19.8円)と先物SORを、公式の手数料ページで
         確認して書いている。ASPに連絡して最終チェックを通してからリンクを貼る。
       → イデコSBI証券: 見送る。iDeCoでは先物・オプションを扱えず、
         このページの読者の目的と重ならない。審査を通すためだけの記事は書かない。
       SBI証券本体はA8に出稿が無いため、この経路以外に手段が無かった。

     楽天証券(TGアフィリエイト)の申請状況は未確認。 -->
<!-- 【アフィリエイトリンク: 楽天証券 口座開設】 -->

<h2>オプションと併用される指数CFD</h2>
<p>オプションを触っていると、<b>オプションでは対応しにくい場面</b>に必ず当たります。
そこを埋める手段として、株価指数のCFD(差金決済取引)を併用する人がいます。
具体的にどういう場面かを挙げます。</p>

<p><b>1. 夜間に動いたとき</b><br>
日経225オプションの取引時間には限りがありますが、指数CFDはほぼ24時間動きます。
実例として2026年8月12日、日中終値67,524円だった日経平均は、
その日の夜間取引で<b>68,700円台まで1,200円近く上昇</b>しました。
翌朝まで何もできない時間帯に手当てできるかどうかは、実務上の差になります。</p>

<p><b>2. 満期を気にせず持ちたいとき</b><br>
オプションには必ずSQがあり、期日が来れば強制的に決済されます。
時間が経つだけで価値が減る性質もあります。CFDには満期がないので、
<b>相場観の時間軸と商品の期限がずれる問題</b>が起きません。</p>

<p><b>3. 細かく量を調整したいとき</b><br>
オプションはミニでも取引単位が決まっています。CFDは建玉の量をより細かく刻めるため、
<b>ヘッジの量を微調整する</b>用途に向きます。</p>

<p><b>4. 単純に下を取りたいとき</b><br>
下落に備える方法はプット買いだけではありません。プットは
<a href="guide-gex.html">ボラティリティの水準</a>に価格が左右されますが、
CFDの売りは指数の値動きにほぼ素直に連動します。
<b>「オプションのどの要素で損益が決まるか」を分けて考えられる</b>のが利点です。</p>

<p>当サイトの建玉分布やガンマエクスポージャーの分析は、
どの水準が意識されやすいかを見るものなので、<b>CFDでの指数トレードにもそのまま使えます</b>。</p>

<p><b>ただし性質の違いは理解しておく必要があります。</b>
店頭CFDは取引所取引ではなく<b>業者との相対取引</b>で、価格やスプレッドは業者が提示します。
建玉を持ち越すと金利や配当に相当する調整額が発生し、
<b>長く持つほどコストが積み上がる</b>場合があります。オプションとは損益の決まり方が違う商品です。</p>

<p>CFDの取扱いがある口座の例として、DMM.com証券(DMM CFD)があります。</p>
<div style="text-align:center; margin: 16px 0;">
<a href="https://px.a8.net/svt/ejp?a8mat=4B83D5+4BZL9U+1WP2+NXESX" rel="nofollow">
<img border="0" width="250" height="250" alt="DMM.com証券 CFD" src="https://www21.a8.net/svt/bgt?aid=260718089262&wid=001&eno=01&mid=s00000008903004019000&mc=1"></a>
<img border="0" width="1" height="1" src="https://www19.a8.net/0.gif?a8mat=4B83D5+4BZL9U+1WP2+NXESX" alt="">
</div>
<p><a href="https://px.a8.net/svt/ejp?a8mat=4B83D5+4BZL9U+1WP2+NTRMQ" rel="nofollow">【PR】全銘柄の取引手数料が0円の【DMM CFD】</a><img border="0" width="1" height="1" src="https://www10.a8.net/0.gif?a8mat=4B83D5+4BZL9U+1WP2+NTRMQ" alt=""></p>
<p>※ CFDも証拠金取引であり、相場変動により預託した証拠金を上回る損失が生じるおそれがあります。
取引条件・手数料等の詳細は公式サイトで最新情報をご確認ください。</p>

<h2>データを活かす</h2>
<p>準備ができたら、当サイトの<a href="./">建玉分布・Put/Callレシオ</a>を
日々の分析にお役立てください。毎営業日、JPX公表データで自動更新しています。</p>
<ul>
<li><a href="guide-oi.html">建玉分布の見方</a> — 意識される価格帯を読む</li>
<li><a href="guide-pcr.html">Put/Callレシオとは</a> — 市場の偏りを見る</li>
<li><a href="guide-sq.html">SQとは</a> — 満期に何が起きるか</li>
<li><a href="glossary.html">用語集</a> — 分からない言葉が出てきたら</li>
</ul>
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
             "guide-teguchi.html", "guide-sq.html"):
    if _key in GUIDE_PAGES:
        _title, _body = GUIDE_PAGES[_key]
        GUIDE_PAGES[_key] = (_title, PR_NOTE + _body + CTA_BROKER)
