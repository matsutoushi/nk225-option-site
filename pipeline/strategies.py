# -*- coding: utf-8 -*-
"""オプション戦略のページ群。

戦略の説明だけのページはどこにでもあるので、2つの「実データ」を柱にする。

  1. 今日の清算値段で組んだらどうなるか
     JPXの清算値段CSV(rbYYYYMMDD.csv)にある全行使価格の値段とIVを使い、
     決まったルールで行使価格を選んで、支払い/受け取り・最大損益・損益分岐点を出す。
     特定の行使価格を勧める形にしないため、選び方はルール(現値から±5%など)で固定する。

  2. 過去のSQ間の値動きで数えた事実
     日経平均の公式データ(2023年〜)とSQ値から、SQからSQまでの値動きを並べ、
     「±5%を超えた回数」「日経VIが織り込んだ幅を超えた回数」などを数える。

書き方の約束:
  - 売買を勧めない。「勝てる」「稼げる」は使わない
  - 損失が限定されない形には必ずそう書く
  - 数字は毎回データから計算する。本文に手で数字を書かない
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

LARGE = 1000   # 日経225オプション(ラージ)の乗数
MINI = 100     # 日経225ミニオプションの乗数


# ---------------------------------------------------------------------------
# 価格モデル
# ---------------------------------------------------------------------------

def _ncdf(x):
    return 0.5 * (1.0 + np.vectorize(math.erf)(np.asarray(x) / math.sqrt(2.0)))


def _npdf(x):
    x = np.asarray(x)
    return np.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def bs(S, K, T, iv, kind, r=0.0):
    """ブラック・ショールズの価格とギリシャ指標(1単位あたり・指数ポイント)。

    theta は1日あたり(暦日)。T<=0 のときは本質的価値のみ。"""
    S = np.asarray(S, dtype=float)
    if T <= 0 or iv <= 0:
        intr = np.maximum(S - K, 0) if kind == "C" else np.maximum(K - S, 0)
        delta = np.where(S > K, 1.0, 0.0) if kind == "C" else np.where(S < K, -1.0, 0.0)
        return {"price": intr, "delta": delta, "gamma": np.zeros_like(S),
                "theta": np.zeros_like(S), "vega": np.zeros_like(S)}
    sq = iv * math.sqrt(T)
    d1 = (np.log(S / K) + (r + 0.5 * iv * iv) * T) / sq
    d2 = d1 - sq
    if kind == "C":
        price = S * _ncdf(d1) - K * math.exp(-r * T) * _ncdf(d2)
        delta = _ncdf(d1)
    else:
        price = K * math.exp(-r * T) * _ncdf(-d2) - S * _ncdf(-d1)
        delta = _ncdf(d1) - 1.0
    gamma = _npdf(d1) / (S * sq)
    theta = -(S * _npdf(d1) * iv) / (2 * math.sqrt(T)) / 365.0
    vega = S * _npdf(d1) * math.sqrt(T) / 100.0          # IV 1ポイントあたり
    return {"price": price, "delta": delta, "gamma": gamma, "theta": theta, "vega": vega}


def implied_vol(price: float, S: float, K: float, T: float, kind: str) -> float | None:
    """清算値段から、このページの計算条件(残り日数・金利0)でのIVを逆算する。

    JPXのIV列は残り日数や金利の置き方が違うため、そのまま使うと
    ブラック・ショールズで計算した値段が清算値段と1割ほどずれる。
    図の「今日の時点の評価」が現値でゼロから出発するよう、値段に合わせたIVを使う。"""
    if T <= 0 or price <= 0:
        return None
    intr = max(S - K, 0) if kind == "C" else max(K - S, 0)
    if price <= intr:
        return None
    lo, hi = 0.01, 3.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if float(bs(S, K, T, mid, kind)["price"]) > price:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


# ---------------------------------------------------------------------------
# 脚(レッグ)と戦略
# ---------------------------------------------------------------------------

@dataclass
class Leg:
    kind: str        # "C" / "P" / "F"(先物)
    strike: float    # 先物は建値
    qty: int         # +買い / -売り
    price: float     # 清算値段(ポイント)。先物は建値
    iv: float = 0.0

    def label(self) -> str:
        side = "買い" if self.qty > 0 else "売り"
        n = abs(self.qty)
        cnt = f"{n}枚" if n > 1 else "1枚"
        if self.kind == "F":
            return f"先物 {side} {cnt}({self.strike:,.0f}円)"
        nm = "コール" if self.kind == "C" else "プット"
        return f"{self.strike:,.0f}円{nm} {side} {cnt}(清算値段 {self.price:,.0f})"


def payoff_at_expiry(legs: list[Leg], S):
    S = np.asarray(S, dtype=float)
    total = np.zeros_like(S)
    for lg in legs:
        if lg.kind == "F":
            total += lg.qty * (S - lg.strike)
        elif lg.kind == "C":
            total += lg.qty * (np.maximum(S - lg.strike, 0) - lg.price)
        else:
            total += lg.qty * (np.maximum(lg.strike - S, 0) - lg.price)
    return total


def value_now(legs: list[Leg], S, T):
    """今日の時点での評価損益(IVは各脚の清算値段のIVで固定)。"""
    S = np.asarray(S, dtype=float)
    total = np.zeros_like(S)
    for lg in legs:
        if lg.kind == "F":
            total += lg.qty * (S - lg.strike)
        else:
            total += lg.qty * (bs(S, lg.strike, T, lg.iv, lg.kind)["price"] - lg.price)
    return total


def greeks(legs: list[Leg], S: float, T: float) -> dict:
    g = {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
    for lg in legs:
        if lg.kind == "F":
            g["delta"] += lg.qty
            continue
        b = bs(S, lg.strike, T, lg.iv, lg.kind)
        for k in g:
            g[k] += lg.qty * float(b[k])
    return g


def analyze(legs: list[Leg], spot: float) -> dict:
    """満期の損益から、最大利益・最大損失・損益分岐点を求める。

    上下の端で傾きが残る(=価格が動くほど損益が増え続ける)ときは「限定されない」とする。"""
    lo, hi = int(max(spot * 0.4, 1000)) // 5 * 5, int(spot * 1.6) // 5 * 5
    ks = [lg.strike for lg in legs]
    grid = np.unique(np.concatenate([np.arange(lo, hi, 5.0), np.array(ks, dtype=float)]))
    pnl = payoff_at_expiry(legs, grid)
    slope_hi = pnl[-1] - pnl[-2]
    slope_lo = pnl[1] - pnl[0]
    unlimited_profit = slope_hi > 1e-6 or slope_lo < -1e-6
    unlimited_loss = slope_hi < -1e-6 or slope_lo > 1e-6
    # 下側の損失は指数0までで有限だが、実務上は「大きく膨らむ」ので限定されない扱いにする
    be = []
    for i in range(1, len(grid)):
        a, b = pnl[i - 1], pnl[i]
        if a == 0:
            be.append(grid[i - 1])
        elif a * b < 0:
            be.append(grid[i - 1] + (grid[i] - grid[i - 1]) * (-a) / (b - a))
    net = sum(-lg.qty * lg.price for lg in legs if lg.kind != "F")
    return {"max_profit": None if unlimited_profit else float(pnl.max()),
            "max_loss": None if unlimited_loss else float(pnl.min()),
            "breakevens": sorted(set(round(x) for x in be)),
            "net": float(net)}        # +受け取り / -支払い(ポイント)


# ---------------------------------------------------------------------------
# 今日の清算値段から脚を選ぶ
# ---------------------------------------------------------------------------

class Chain:
    """1つの限月の清算値段。行使価格はルールで選ぶ。"""

    def __init__(self, settle: dict, min_days: int = 10):
        df = settle["data"]
        self.spot = float(settle["spot"])
        self.date = settle["date"]
        # 週次限月(YYMMDD)も同じファイルに入っている。月次限月(YYMM)だけを使う
        exps = sorted(e for e in df["expiry"].unique() if len(str(e)) == 4)
        chosen = None
        for e in exps:
            g = df[df["expiry"] == e]
            if int(g["days"].iloc[0]) >= min_days and len(g) > 40:
                chosen = e
                break
        if chosen is None:
            chosen = exps[0]
        self.expiry = chosen
        self.df = df[df["expiry"] == chosen]
        self.days = int(self.df["days"].iloc[0])
        self.T = self.days / 365.0
        # 125円刻みの行使価格(申請で立った半端な行使価格は避ける)
        k = self.df[self.df["strike"] % 125 == 0]
        self.strikes = sorted(k["strike"].unique())

    def label(self) -> str:
        return f"20{self.expiry[:2]}年{int(self.expiry[2:])}月限(残り{self.days}日)"

    def near(self, target: float) -> int:
        return int(min(self.strikes, key=lambda k: abs(k - target)))

    def row(self, kind: str, strike: int):
        g = self.df[(self.df["type"] == kind) & (self.df["strike"] == strike)]
        return None if not len(g) else g.iloc[0]

    def leg(self, kind: str, target: float, qty: int) -> Leg | None:
        k = self.near(target)
        r = self.row(kind, k)
        if r is None or not (r["price"] > 0):
            return None
        iv = implied_vol(float(r["price"]), self.spot, k, self.T, kind)
        if iv is None:
            iv = float(r["iv"]) if float(r["iv"]) > 0.02 else 0.2
        return Leg(kind, float(k), qty, float(r["price"]), iv)

    def call_matching(self, price: float, above: float) -> Leg | None:
        """指定の値段に一番近いコール(ゼロコストカラー用)。above より上の行使価格に限る。"""
        c = self.df[(self.df["type"] == "C") & (self.df["strike"] > above)
                    & (self.df["strike"] % 125 == 0) & (self.df["price"] > 0)]
        if not len(c):
            return None
        r = c.iloc[(c["price"] - price).abs().argsort()[:1]].iloc[0]
        iv = implied_vol(float(r["price"]), self.spot, float(r["strike"]), self.T, "C") or float(r["iv"])
        return Leg("C", float(r["strike"]), -1, float(r["price"]), iv)


# ---------------------------------------------------------------------------
# 過去のSQ間の値動き
# ---------------------------------------------------------------------------

def sq_periods(sq_hist: pd.DataFrame, n225: pd.DataFrame, vi: pd.Series | None) -> pd.DataFrame:
    """SQの日の終値から、次のSQ値までの動きを並べる。

    「SQの日に次の限月で組み、次のSQで清算した」場合の原資産の動きに相当する。"""
    h = sq_hist.copy()
    h["sq_date"] = pd.to_datetime(h["sq_date"])
    h = h.sort_values("sq_date")
    rows = []
    for a, b in zip(h.iloc[:-1].itertuples(), h.iloc[1:].itertuples()):
        if a.sq_date not in n225.index:
            continue
        s0 = float(n225.loc[a.sq_date, "Close"])
        s1 = float(b.sq_value)
        days = (b.sq_date - a.sq_date).days
        v0 = float(vi.loc[a.sq_date]) if vi is not None and a.sq_date in vi.index else None
        exp_move = s0 * v0 / 100 * math.sqrt(days / 365) if v0 else None
        rows.append({"start": a.sq_date, "end": b.sq_date, "s0": s0, "s1": s1,
                     "ret": s1 / s0 - 1, "days": days, "vi": v0, "exp_move": exp_move})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 図
# ---------------------------------------------------------------------------

def chart_payoff(legs: list[Leg], chain: Chain, fname: str, title: str,
                 img_dir: str, colors: dict) -> str:
    S = chain.spot
    grid = np.linspace(S * 0.85, S * 1.15, 400)
    exp = payoff_at_expiry(legs, grid) * LARGE / 1e4
    now = value_now(legs, grid, chain.T) * LARGE / 1e4
    fig, ax = plt.subplots(figsize=(9, 3.6))
    ax.axhline(0, color=colors["ink2"], linewidth=0.8)
    ax.plot(grid, exp, color=colors["accent"], linewidth=2.0, label="SQ(満期)での損益")
    ax.plot(grid, now, color=colors["ink2"], linewidth=1.2, linestyle="--", label="今日の時点の評価")
    ax.fill_between(grid, exp, 0, where=exp >= 0, color=colors["accent"], alpha=0.10)
    ax.fill_between(grid, exp, 0, where=exp < 0, color=colors["down"], alpha=0.10)
    ax.axvline(S, color=colors["ink"], linestyle=":", linewidth=1.0)
    ax.text(S, ax.get_ylim()[1], f" 現値 {S:,.0f}", fontsize=8, va="top", color=colors["ink"])
    for lg in legs:
        if lg.kind != "F":
            ax.axvline(lg.strike, color=colors["line"], linewidth=0.8)
    ax.set_xlabel("SQ値(日経平均)", fontsize=9)
    ax.set_ylabel("損益(万円・ラージ1枚あたり)", fontsize=9)
    ax.set_title(title, fontsize=10)
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8, loc="best")
    fig.tight_layout()
    os.makedirs(img_dir, exist_ok=True)
    fig.savefig(os.path.join(img_dir, fname), dpi=110)
    plt.close(fig)
    return f"img/{fname}"


# ---------------------------------------------------------------------------
# HTML部品
# ---------------------------------------------------------------------------

def yen(points: float, mult: int = LARGE) -> str:
    return f"{points * mult:+,.0f}円"


def example_block(name: str, legs: list[Leg], chain: Chain, img: str, note: str = "") -> str:
    """「今日の清算値段で組んだ例」の表と図。"""
    a = analyze(legs, chain.spot)
    g = greeks(legs, chain.spot, chain.T)
    net = a["net"]
    net_txt = ("<b>受け渡しなし(0ポイント)</b>" if abs(net) < 0.5 else
               f"<b>受け取り {net:,.0f}ポイント</b>(ラージ {net * LARGE:,.0f}円・ミニ {net * MINI:,.0f}円)"
               if net > 0 else
               f"<b>支払い {-net:,.0f}ポイント</b>(ラージ {-net * LARGE:,.0f}円・ミニ {-net * MINI:,.0f}円)")
    mp = "限定されない" if a["max_profit"] is None else \
        f"{a['max_profit']:,.0f}ポイント(ラージ {a['max_profit'] * LARGE:,.0f}円)"
    ml = "<b>限定されない</b>" if a["max_loss"] is None else \
        f"{-a['max_loss']:,.0f}ポイント(ラージ {-a['max_loss'] * LARGE:,.0f}円)"
    be = "・".join(f"{x:,.0f}円" for x in a["breakevens"]) or "なし"
    legs_html = "".join(f"<li>{lg.label()}</li>" for lg in legs)
    return f"""
<div class="latest">
<h3>{name}: {chain.date[4:6].lstrip('0')}月{chain.date[6:].lstrip('0')}日の清算値段で組んだ例</h3>
<p>{chain.label()}・現値 {chain.spot:,.0f}円。行使価格は下の決まったルールで自動的に選んでいます。</p>
<ul>{legs_html}</ul>
<div class="tbl-wrap"><table>
<tbody>
<tr><th>組んだときの受け渡し</th><td>{net_txt}</td></tr>
<tr><th>SQでの最大利益</th><td>{mp}</td></tr>
<tr><th>SQでの最大損失</th><td>{ml}</td></tr>
<tr><th>損益分岐点(SQ値)</th><td>{be}</td></tr>
<tr><th>今日のデルタ / ガンマ</th><td>{g['delta']:+.2f} / {g['gamma'] * 1000:+.3f}(1,000円動いたときのデルタの変化)</td></tr>
<tr><th>1日(暦日)あたりの時間価値の変化(セータ)</th><td>{g['theta']:+,.1f}ポイント(ラージ {g['theta'] * LARGE:+,.0f}円)</td></tr>
<tr><th>IVが1ポイント上がると(ベガ)</th><td>{g['vega']:+,.1f}ポイント(ラージ {g['vega'] * LARGE:+,.0f}円)</td></tr>
</tbody></table></div>
<img src="{img}?v={chain.date}" alt="{name}の損益図">
<p class="latest-note">手数料・証拠金の金利は含みません。清算値段は取引所が算出した理論上の値段で、
実際に約定する値段とはずれます。{note}</p>
</div>
"""


def count_line(n: int, total: int) -> str:
    return f"{total}回中{n}回"
