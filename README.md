# Nikkei 225 Options & Futures Data

Daily positioning data for Japan's benchmark index, built entirely from free official
sources and published as a static site. No account, no API key, no paywall.

**→ [Live site](https://matsutoushi.github.io/nk225-option-site/)** ·
[English pages](https://matsutoushi.github.io/nk225-option-site/en/)

Updated every business day by GitHub Actions. The charts below are pulled live from the
site, so they show the current data.

![Open interest by strike](https://matsutoushi.github.io/nk225-option-site/img/oi_dist.png)

## What makes this data unusual

Most global traders know the CFTC's Commitments of Traders report, which groups traders
into anonymous categories. Japan Exchange Group publishes something different:

- **Weekly open interest by *named* trading participant** — Nomura, Goldman Sachs, HSBC,
  Morgan Stanley MUFG and others, each with their net Nikkei 225 futures position.
- **Daily trading volume by participant**, published around 17:45 JST.
- **Settlement prices including implied volatility for every strike**, which makes it
  possible to estimate gamma exposure from official data alone — no vendor feed required.

There is no direct US equivalent to the first two, and very little written about them in
English. See [the explainer](https://matsutoushi.github.io/nk225-option-site/en/guide-participants.html)
for how to read the data — including why a firm's persistent short is usually structural
rather than a directional view.

## What the site publishes

| Section | Contents |
|---|---|
| Nikkei options | Open interest by strike with day-over-day change, put/call ratio history, estimated gamma exposure |
| Participants | Weekly net open interest per firm, daily volume rankings for large and mini contracts |
| US markets | CFTC COT positioning with price overlays, CBOE put/call ratios, SPX open interest and gamma, leveraged-ETF assets |
| Risk monitor | High-yield spreads, breakeven inflation, Sahm rule and other macro stress indicators |
| Guides | How to read each dataset, using observed examples rather than textbook definitions |

## Data sources

Everything is public and free.

| Data | Source | Published |
|---|---|---|
| Open interest by strike | JPX `open_interest.xlsx` | ~20:00 JST |
| Put/call volume, turnover | JPX `whole_day.xlsx` | ~16:xx JST |
| Volume by participant | JPX JSON API | ~17:45 JST |
| Open interest by participant | JPX (weekly) | Monday |
| Settlement prices with IV | JPX `rb{YYYYMMDD}.csv` | daily |
| Index prices, ETF data | Yahoo Finance | — |
| COT positioning | CFTC | Friday (Tuesday data) |
| Macro indicators | FRED | varies |

Raw JPX files are not redistributed; only derived charts and aggregates are published.

## How it works

```
GitHub Actions (weekday afternoons/evenings JST)
  │
  ├─ pipeline/jpx.py       discover and fetch the day's JPX files
  ├─ pipeline/us_data.py   CFTC, CBOE, ETF and options-chain data
  ├─ pipeline/fred.py      macro series with local cache fallback
  │
  └─ pipeline/build.py     compute, chart, and render static HTML
        │
        └─ GitHub Pages
```

JPX publishes its files at different times of day, so the build keys off a composite of
the volume, participant and open-interest dates. If any one of them advances, the site
rebuilds — otherwise the run exits without redeploying.

Daily values are appended to `data/` and committed back by the workflow, so time series
accumulate without any external database.

## Running it locally

```bash
pip install -r pipeline/requirements.txt
python pipeline/build.py          # writes to site/
FORCE_BUILD=1 python pipeline/build.py   # rebuild even if no new data
```

Optional environment variables: `FRED_API_KEY` (falls back to a local cache if absent),
`ADSENSE_CLIENT` / `ADSENSE_SLOT` (ads are only emitted when both are set).

## Repository layout

| Path | Purpose |
|---|---|
| `pipeline/jpx.py` | JPX file discovery, download and parsing |
| `pipeline/us_data.py` | CFTC, CBOE, SPX chain, leveraged ETFs |
| `pipeline/fred.py` | FRED series with cache fallback |
| `pipeline/build.py` | Calculations, charts, HTML rendering |
| `pipeline/pages.py` | Guide article content (JA/EN) |
| `pipeline/tools_page.py` | Interactive Plotly page |
| `data/` | Accumulated daily history, committed by CI |
| `site/` | Generated output (not tracked) |
| `docs/` | Internal planning notes |

## 日本語

日経225オプション・先物の建玉や手口を、JPXなどの公表データから毎営業日自動で集計し、
チャートにして公開しています。行使価格別の建玉分布、Put/Callレシオ、取引参加者別の
ポジション、清算値のボラティリティから推定したガンマエクスポージャーなどを扱います。

サイトは[こちら](https://matsutoushi.github.io/nk225-option-site/)。
データの読み方は[解説記事](https://matsutoushi.github.io/nk225-option-site/guide-oi.html)にまとめています。

## Disclaimer

This project is for informational purposes only. It is not investment advice or a
solicitation to trade. Figures labelled as estimates depend on stated assumptions that
cannot be verified from public data — the gamma exposure calculation in particular
assumes a dealer positioning convention that may not hold. Verify anything you rely on
against the original sources.
