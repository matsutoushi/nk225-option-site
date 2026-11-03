# -*- coding: utf-8 -*-
"""公開データだけでディーラーの向きを推定する(検証用・非公開)。

【なぜ作るか】
サイトのガンマ推定は「ディーラーはコールを買い持ち・プットを売り持ち」という
一律の仮定で符号を付けている。この仮定が当たっているかは公開データでは分からない。
別手法(建玉×約定の向き)との突き合わせでは、裏付けが取れたのは合計の符号までで、
現値の上下の内訳は一致しなかった。そこで「向きも公開データから推定できないか」を
毎営業日の履歴として積み、あとで較正できるようにしておく。

【考え方】
建玉が増えた行使価格で、同時にIVも上がっていれば、その建玉は
「買いたい人が値を押し上げて作った」=需要主導と見る。ディーラーは売り手なので
ショートガンマ(値動きを増幅する側)。逆にIVが下がっていれば供給主導で、
ディーラーは買い手=ロングガンマ。

  その日・その銘柄(タイプ×限月×行使価格)について
    残差ΔIV = ΔIV − その日の全銘柄のΔIVの中央値     … 市場全体のIV変動を除く
    ΔOI > 0 かつ 残差ΔIV > 0  → 需要主導(ディーラー売り手 / ショートガンマ)
    ΔOI > 0 かつ 残差ΔIV < 0  → 供給主導(ディーラー買い手 / ロングガンマ)
    ΔOI < 0                   → 既存建玉の解消。積み上げた向きを按分して減らす

1日の判定は雑音が多いので、限月ごとに銘柄別の内訳を累積した状態量として扱う。
最新日の建玉に対し、サイトと同じブラック・ショールズのガンマを掛け、
符号だけをこの累積方向(−1〜+1の連続値)で置き換えて合計・上側・下側を出す。

【確からしさ】
  不明分の割合 = 向きを割り当てられていない建玉 ÷ 建玉合計
  清算値段(settle_*.csv)は2026-10-05以降しか無いので、それ以前に作られた建玉は
  「不明」として残る。不明分はガンマに寄与しない(符号0)扱いにしてあるため、
  この割合が大きいうちは金額が小さく出る。履歴の列に入れてあるので必ず見る。

【前提の限界】
  「建玉が増えてIVも上がった = 買い需要が主導した」は仮説にすぎない。
  19日分では需要主導と供給主導がほぼ五分で、信号と雑音の区別がついていない。
  別手法との重なりも3日しかなく、較正も検証もできていない。
  結論を出すためのスクリプトではなく、較正できる日数が溜まるまで記録を続けるためのもの。

【使い方】
  python tools/public_direction.py                 # 全期間を再計算して履歴を更新
  python tools/public_direction.py --quiet         # 履歴の更新だけ(定期実行用)

  出力: private/public_direction_history.csv
  突き合わせ: private/dealer_gamma_history.csv があれば日付で照合して表示する

※出力は private/ に置く。公開サイトには一切出さない(検証が済んでいないため)。
"""
from __future__ import annotations

import argparse
import glob
import os
import re

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT_DIR = os.path.join(ROOT, "private")
HIST = os.path.join(OUT_DIR, "public_direction_history.csv")
DEALER_HIST = os.path.join(OUT_DIR, "dealer_gamma_history.csv")

MULT = 1000          # オプション1枚の取引単位(サイトと同じ)
BAND = 0.10          # 現値±10%。サイトの hedge_pressure と揃える
MAX_DAYS = 45        # 残存45日以内。同上


def available_days() -> list[str]:
    """建玉と清算値段の両方がある日(YYYYMMDD)。清算値段は2026-10-05以降しか無い。"""
    oi = {re.search(r"oi_(\d{8})\.csv$", f).group(1)
          for f in glob.glob(os.path.join(DATA, "oi_*.csv"))}
    st = {re.search(r"settle_(\d{8})\.csv$", f).group(1)
          for f in glob.glob(os.path.join(DATA, "settle_*.csv"))}
    return sorted(oi & st)


def load_oi(date: str) -> pd.DataFrame:
    df = pd.read_csv(os.path.join(DATA, f"oi_{date}.csv"))
    df["expiry"] = df["expiry"].astype(str)
    return df.groupby(["type", "expiry", "strike"], as_index=False)["oi"].sum()


def load_settle(date: str) -> pd.DataFrame:
    df = pd.read_csv(os.path.join(DATA, f"settle_{date}.csv"))
    df["expiry"] = df["expiry"].astype(str)
    return df[df["iv"] > 0]


def spot_from_settle(settle: pd.DataFrame) -> float | None:
    """プット・コール・パリティから現値を推定する。

    清算値段ファイルの原資産価格は settle_*.csv に保存していないので、その代わり。
    同じ行使価格のコールとプットで C − P ≒ S − K なので、S ≒ K + (C − P)。
    金利の割引を無視するため数十円ずれるが、ガンマの重み付けには十分。
    """
    monthly = settle[settle["expiry"].str.len() == 4]
    if not len(monthly):
        return None
    near = monthly[monthly["expiry"] == sorted(monthly["expiry"].unique())[0]]
    c = near[near["type"] == "C"].set_index("strike")["price"]
    p = near[near["type"] == "P"].set_index("strike")["price"]
    k = c.index.intersection(p.index)
    if len(k) < 10:
        return None
    return float((k.to_series() + (c[k] - p[k])).median())


def bs_gamma(spot: float, strike: pd.Series, iv: pd.Series, days: pd.Series) -> pd.Series:
    """サイト(hedge_pressure)と同じブラック・ショールズのガンマ。金利は0とする。"""
    t = days / 365.0
    d1 = (np.log(spot / strike) + iv ** 2 / 2 * t) / (iv * np.sqrt(t))
    return np.exp(-d1 ** 2 / 2) / np.sqrt(2 * np.pi) / (spot * iv * np.sqrt(t))


class Inventory:
    """銘柄(タイプ×限月×行使価格)ごとに、建玉を向き別に積み上げた状態量。

    demand  = 需要主導で作られた建玉(ディーラー売り手 / ショートガンマ)
    supply  = 供給主導で作られた建玉(ディーラー買い手 / ロングガンマ)
    unknown = 向きを割り当てられていない建玉(積み上げ開始前からあった分など)
    """

    def __init__(self) -> None:
        self.demand: dict[tuple, float] = {}
        self.supply: dict[tuple, float] = {}
        self.unknown: dict[tuple, float] = {}

    def seed_unknown(self, oi: pd.DataFrame) -> None:
        for t, e, k, v in oi.itertuples(index=False):
            self.unknown[(t, e, k)] = float(v)

    def _held(self, key: tuple) -> float:
        return (self.demand.get(key, 0.0) + self.supply.get(key, 0.0)
                + self.unknown.get(key, 0.0))

    def apply_day(self, d_oi: pd.DataFrame) -> None:
        """1日分のΔOIと残差ΔIVを当てる。d_oi: [type,expiry,strike,d_oi,resid]"""
        for t, e, k, dq, resid in d_oi.itertuples(index=False):
            key = (t, e, k)
            if dq > 0:
                if pd.isna(resid) or resid == 0:
                    self.unknown[key] = self.unknown.get(key, 0.0) + dq
                elif resid > 0:
                    self.demand[key] = self.demand.get(key, 0.0) + dq
                else:
                    self.supply[key] = self.supply.get(key, 0.0) + dq
            elif dq < 0:
                held = self._held(key)
                if held <= 0:
                    continue
                # 解消は向きの内訳をそのまま薄めるものとして按分する。
                # どの向きの建玉が閉じられたかは公開データからは分からない。
                scale = max(0.0, held + dq) / held
                for book in (self.demand, self.supply, self.unknown):
                    if key in book:
                        book[key] *= scale

    def align(self, oi: pd.DataFrame) -> None:
        """積み上げ合計を実際の建玉に合わせ直す(欠測日や丸めのずれを吸収する)。"""
        actual = {(t, e, k): float(v) for t, e, k, v in oi.itertuples(index=False)}
        keys = set(self.demand) | set(self.supply) | set(self.unknown) | set(actual)
        for key in keys:
            want, held = actual.get(key, 0.0), self._held(key)
            if want <= 0:
                for book in (self.demand, self.supply, self.unknown):
                    book.pop(key, None)
            elif held <= 0:
                self.unknown[key] = want
            elif abs(held - want) > 1e-9:
                scale = want / held
                for book in (self.demand, self.supply, self.unknown):
                    if key in book:
                        book[key] *= scale

    def weights(self) -> pd.DataFrame:
        """銘柄ごとの向き w ∈ [−1, +1] と不明分の割合を返す。

        w > 0 はディーラーのロングガンマ(値動きを抑える向き)。サイトの符号と同じ向き。
        不明分は寄与0として扱うので、|w| は不明分が多いほど小さくなる。
        """
        rows = []
        for key in set(self.demand) | set(self.supply) | set(self.unknown):
            held = self._held(key)
            if held <= 0:
                continue
            dm = self.demand.get(key, 0.0)
            sp = self.supply.get(key, 0.0)
            un = self.unknown.get(key, 0.0)
            rows.append((key[0], key[1], key[2], held, (sp - dm) / held, un / held))
        return pd.DataFrame(rows, columns=["type", "expiry", "strike",
                                           "oi_held", "w", "unknown_frac"])


def gamma_rows(date: str, inv: Inventory) -> dict | None:
    """最新日の建玉にガンマを掛け、新方式の符号とサイトの一律仮定の符号で集計する。"""
    settle, oi = load_settle(date), load_oi(date)
    spot = spot_from_settle(settle)
    if not spot:
        return None
    iv = settle[(settle["days"] > 0) & (settle["days"] <= MAX_DAYS)]
    df = oi.merge(iv[["type", "expiry", "strike", "iv", "days"]],
                  on=["type", "expiry", "strike"], how="inner")
    df = df[(df["strike"] >= spot * (1 - BAND)) & (df["strike"] <= spot * (1 + BAND))]
    if not len(df):
        return None
    df = df.merge(inv.weights()[["type", "expiry", "strike", "w", "unknown_frac"]],
                  on=["type", "expiry", "strike"], how="left")
    df["w"] = df["w"].fillna(0.0)
    df["unknown_frac"] = df["unknown_frac"].fillna(1.0)

    g = bs_gamma(spot, df["strike"], df["iv"], df["days"])
    notional = g * df["oi"] * MULT * spot * spot * 0.01
    df = df.assign(force=notional * df["w"],
                   force_site=notional * df["type"].map({"C": 1, "P": -1}))

    up, dn = df["strike"] > spot, df["strike"] < spot
    held = df["oi"].sum()
    return {
        "date": date,
        "spot": round(spot, 2),
        "total_oku": round(df["force"].sum() / 1e8, 1),
        "above_oku": round(df.loc[up, "force"].sum() / 1e8, 1),
        "below_oku": round(df.loc[dn, "force"].sum() / 1e8, 1),
        "site_total_oku": round(df["force_site"].sum() / 1e8, 1),
        "site_above_oku": round(df.loc[up, "force_site"].sum() / 1e8, 1),
        "site_below_oku": round(df.loc[dn, "force_site"].sum() / 1e8, 1),
        "strikes": int(df["strike"].nunique()),
        "contracts": int(held),
        "unknown_frac": round(float((df["unknown_frac"] * df["oi"]).sum() / held), 3),
        "mean_abs_w": round(float((df["w"].abs() * df["oi"]).sum() / held), 3),
    }


def build_history(days: list[str], quiet: bool = False) -> pd.DataFrame:
    """利用できる全期間を頭から積み上げ、各日の集計を返す。"""
    inv = Inventory()
    prev_oi, prev_iv = load_oi(days[0]), load_settle(days[0])
    inv.seed_unknown(prev_oi)       # 積み上げ開始前の建玉は向きが分からない
    rows = []
    for date in days[1:]:
        oi, iv = load_oi(date), load_settle(date)
        d = oi.merge(prev_oi, on=["type", "expiry", "strike"], how="outer",
                     suffixes=("", "_prev")).fillna({"oi": 0.0, "oi_prev": 0.0})
        d["d_oi"] = d["oi"] - d["oi_prev"]
        div = iv.merge(prev_iv[["type", "expiry", "strike", "iv"]],
                       on=["type", "expiry", "strike"], how="inner", suffixes=("", "_prev"))
        div["d_iv"] = div["iv"] - div["iv_prev"]
        # 市場全体のIV変動(日経VIの上下に相当する平行移動)を中央値で差し引く
        div["resid"] = div["d_iv"] - div["d_iv"].median()
        d = d.merge(div[["type", "expiry", "strike", "resid"]],
                    on=["type", "expiry", "strike"], how="left")
        inv.apply_day(d[["type", "expiry", "strike", "d_oi", "resid"]])
        inv.align(oi)
        row = gamma_rows(date, inv)
        if row:
            rows.append(row)
            if not quiet:
                print(f"{date}  新方式 合計{row['total_oku']:+8.1f} "
                      f"(上{row['above_oku']:+8.1f} 下{row['below_oku']:+8.1f})  "
                      f"一律仮定 合計{row['site_total_oku']:+9.1f} "
                      f"(上{row['site_above_oku']:+8.1f} 下{row['site_below_oku']:+9.1f})  "
                      f"不明分{row['unknown_frac']:.0%}")
        prev_oi, prev_iv = oi, iv
    return pd.DataFrame(rows)


def save_history(hist: pd.DataFrame) -> pd.DataFrame:
    os.makedirs(OUT_DIR, exist_ok=True)
    if os.path.exists(HIST):
        prev = pd.read_csv(HIST, dtype={"date": str})
        hist = pd.concat([prev, hist], ignore_index=True)
    hist = (hist.astype({"date": str})
            .drop_duplicates(subset=["date"], keep="last")
            .sort_values("date"))
    hist.to_csv(HIST, index=False)
    return hist


def compare_with_dealer(hist: pd.DataFrame) -> None:
    """別手法の履歴と日付で突き合わせる。日数が足りないので数字を並べるだけ。"""
    if not os.path.exists(DEALER_HIST):
        print(f"\n{os.path.basename(DEALER_HIST)} が無いため突き合わせは省略します。")
        return
    dealer = pd.read_csv(DEALER_HIST, dtype={"asof": str})
    print("\n" + "=" * 96)
    print("別手法(建玉×約定の向き)との突き合わせ")
    print("=" * 96)
    for mode in sorted(dealer["mode"].unique()):
        sub = dealer[dealer["mode"] == mode].drop_duplicates(subset=["asof"], keep="last")
        m = hist.merge(sub, left_on="date", right_on="asof", how="inner",
                       suffixes=("", "_ref"))
        if not len(m):
            print(f"\n[{mode}] 重なる日がありません。")
            continue
        print(f"\n[{mode}] 重なり {len(m)}日")
        print(f"{'日付':<12}{'新方式計':>10}{'別手法計':>10}{'符号':>6}"
              f"{'新方式上':>10}{'別手法上':>10}{'新方式下':>10}{'別手法下':>10}{'不明分':>8}")
        for r in m.itertuples(index=False):
            same = "一致" if (r.total_oku >= 0) == (r.total_oku_ref >= 0) else "逆"
            print(f"{r.date:<12}{r.total_oku:>10.1f}{r.total_oku_ref:>10.1f}{same:>8}"
                  f"{r.above_oku:>10.1f}{r.above_oku_ref:>10.1f}"
                  f"{r.below_oku:>10.1f}{r.below_oku_ref:>10.1f}"
                  f"{r.unknown_frac:>8.0%}")
        agree = int(((m["total_oku"] >= 0) == (m["total_oku_ref"] >= 0)).sum())
        up_agree = int(((m["above_oku"] >= 0) == (m["above_oku_ref"] >= 0)).sum())
        dn_agree = int(((m["below_oku"] >= 0) == (m["below_oku_ref"] >= 0)).sum())
        print(f"  符号の一致: 合計 {agree}/{len(m)}日 ・ "
              f"上側 {up_agree}/{len(m)}日 ・ 下側 {dn_agree}/{len(m)}日")
        for label, a, b in (("合計", "total_oku", "total_oku_ref"),
                            ("上側", "above_oku", "above_oku_ref"),
                            ("下側", "below_oku", "below_oku_ref")):
            if len(m) >= 2 and m[a].std() > 0 and m[b].std() > 0:
                print(f"  {label}の相関: {m[a].corr(m[b]):+.2f}")
            else:
                print(f"  {label}の相関: 算出不能")
        print(f"  ※{len(m)}日では結論は出せません(符号の一致も偶然で起こる水準)。")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--quiet", action="store_true", help="日別の明細を出さない(定期実行用)")
    args = ap.parse_args()

    days = available_days()
    if len(days) < 2:
        print(f"清算値段と建玉が揃った日が{len(days)}日しかありません。"
              f"ΔIVが取れないので何も計算できません。")
        return
    print(f"対象: {days[0]} 〜 {days[-1]}({len(days)}営業日 / 差分 {len(days) - 1}日)")

    hist = build_history(days, quiet=args.quiet)
    if not len(hist):
        print("集計できた日がありませんでした。")
        return
    hist = save_history(hist)
    print(f"\n履歴: {HIST}({len(hist)}行)")
    compare_with_dealer(hist)
    print("\n※検証用の出力です。公開サイトには出しません。")


if __name__ == "__main__":
    main()
