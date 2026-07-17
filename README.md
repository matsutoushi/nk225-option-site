# nk225-options-site — 日経225オプション データ可視化サイト(再建版)

以前運営していた「オプションデータの収集・可視化サイト」の再建プロジェクト。
毎日自動更新でリピーターを集め、証券口座開設アフィリエイト+AdSenseで収益化する。

## 前回からの改善点

| | 前回 | 今回 |
|---|---|---|
| 基盤 | WordPress(サーバー代あり) | 静的サイト+GitHub Pages(**無料**) |
| 更新 | 自前環境で自動更新 | GitHub Actionsで完全自動(PC電源オフでも動く) |
| 収益 | AdSenseのみ(月500〜2,000円) | 口座開設アフィリエイト(1件約4,000円)を主軸+AdSense |
| 集客 | Twitter | X 9,000フォロワー+毎日更新のリピーター |

## データ源について(重要な経緯)

旧サイトが使っていた**証券会社別の手口データはJPXが公表を廃止**したため復活不可。
代替として、現在もJPXが毎営業日無料公開しているデータで再設計した(取得確認済み・2026-07-17):

| データ | 取得元 | 使い道 |
|---|---|---|
| 行使価格別の建玉残高(日次) | JPX `open_interest.xlsx` | 建玉分布チャート=「壁」の可視化 |
| プット/コール出来高(日次) | JPX `whole_day.xlsx` | Put/Callレシオと推移 |
| 日経平均 | Yahoo Finance | マーケット概況・ATM判定 |

日次データを蓄積すると「建玉の前日比増減」「PCR推移」など時系列コンテンツが自動で増えていく。
将来の拡張候補: J-Quants API(Standard 月3,300円)でIV・清算値の過去データ、日経VI。収益が固定費を超えたら検討。

## アーキテクチャ

```
GitHub Actions (平日20:30 JST、JPXデータ公表後)
  ↓
pipeline/build.py
  1. JPX公式サイトから当日ファイルを発見・取得(pipeline/jpx.py)
  2. PCR算出・建玉パース → data/ に履歴蓄積(Actionsがコミットして永続化)
  3. チャート生成 → site/index.html 出力
  ↓
GitHub Pages へ自動デプロイ(サーバー代0円、PC電源不要、独自ドメイン設定可)
```

## ディレクトリ

- `pipeline/jpx.py` — JPXデータの発見・取得・パース
- `pipeline/build.py` — チャート生成とHTML出力(ローカル実行で動作確認済み)
- `data/` — 日次履歴の蓄積(PCR履歴、建玉スナップショット)
- `site/` — 生成された公開ファイル(自動生成物。手編集しない)
- `.github/workflows/daily-update.yml` — 毎日の自動更新ジョブ
- `docs/monetization.md` — アフィリエイト・AdSenseの配置設計

## セットアップ(ユーザー作業)

1. GitHubリポジトリ作成(Publicを推奨。Pages無料枠のため)
2. このフォルダをプッシュ
3. Settings → Pages → Source: GitHub Actions
4. Actionsタブから daily-update を手動実行(workflow_dispatch)して初回デプロイ
5. 独自ドメインを充てる場合はPages設定でCNAME追加(AdSense申請に必要)

## 収益導線(docs/monetization.md に詳細)

- ヘッダー/サイドに「オプション取引に対応した証券口座」導線(→ 解説ページ → ASPリンク)
- 記事系コンテンツ(finance-blog/articles の口座開設ガイド等)もこのサイト内 `/guide/` に統合
- データページはAdSense、ガイドページはアフィリエイト優先(自動広告除外)
