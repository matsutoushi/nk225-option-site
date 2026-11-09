# tools/

手元(Windows)から動かす運用スクリプト。サイトの生成には関係しない。

## check_freshness.py — 更新遅れの見張り

GitHub Actionsのスケジュール実行はベストエフォートで、混雑時に遅延・スキップされる。
2026-08-27以降、**7〜10時間の遅延**が常態化し、当日のデータで投稿できない日が出た。

```
作成(UTC)     予定cron(UTC)   遅延
08/28 22:34   08/28 12:37    +10.0時間
08/28 20:10   08/28 12:37    +7.6時間
08/27 22:31   08/27 12:37    +9.9時間
```

ワークフロー側では直せないので、手元から見張って気づけるようにした。

### 判定の考え方

「今日は平日か」で判定すると**祝日に誤検知する**。代わりに

- **JPXが公開している最新日**（当日取引高ページのファイル名から読む）
- **サイトが掲載しているデータ基準日**

の2つを比べる。JPXが出しているのにサイトが古ければ本当に遅れている。
JPXがまだ出していなければ、サイトが古くて当然なので何もしない。
祝日カレンダーを持たずに済む。

同じJPX公開日について**2回以上メールを送らない**（`.freshness_state.json` に記録）。

### 準備

パスワードはスクリプトに書かない。環境変数から読む。

```
setx NK225_MAIL_TO       "自分のGmailアドレス"
setx NK225_MAIL_PASSWORD "Googleアプリパスワード16桁"
```

アプリパスワードは、Googleアカウントの2段階認証を有効にしたうえで
[アプリパスワード](https://myaccount.google.com/apppasswords)から発行する。
通常のログインパスワードでは送信できない。
GitHub Actions の `MAIL_APP_PASSWORD` と同じものが使える。

`setx` で設定した値は**新しく開いたコマンドプロンプトから有効**になる。

### 動作確認

```
python tools\check_freshness.py --dry-run   判定だけ表示（メールを送らない）
python tools\check_freshness.py --force     強制的にテスト送信
python tools\check_freshness.py             通常実行
```

### タスクスケジューラへの登録

`check_freshness.bat` を呼ぶ。実行ログは `tools\check_freshness.log` に上書きで残る。

登録済みの時刻（JST）:

| タスク名 | 時刻 |
|---|---|
| `nk225-freshness-1800` | 毎日 18:00 |
| `nk225-freshness-1900` | 毎日 19:00 |

**なぜ18時台で判定できるのか。** サイトの「データ基準日」は
`discover_files()` が返す**出来高ファイルの日付**で、JPXはこれを16時台に公開する。
最初のcronは16:37なので、正常なら18:00の時点で当日分になっている。
建玉(20:00頃)を待つ必要はない。

ただし**JPXの出来高公開がいつもより遅れた日**は、18:00の時点で
「JPXは当日・サイトは前日」に見えて空振りすることがある。
その場合19:00には解消しているが、同じJPX日付には二度送らない作りなので
撤回のメールは来ない。ログ(`check_freshness.log`)を見れば分かる。

PowerShellから登録し直す場合（タスク名にコロンは使えない）:

```powershell
$bat = "C:\Users\tomo0\Projects\nk225-options-site\tools\check_freshness.bat"
$action  = New-ScheduledTaskAction -Execute $bat -WorkingDirectory (Split-Path $bat -Parent)
$trigger = New-ScheduledTaskTrigger -Daily -At "18:00"
$set     = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "nk225-freshness-1800" -Action $action -Trigger $trigger -Settings $set
```

「ユーザーがログオンしているときのみ実行する」(Interactive) にしてある。
バックグラウンド実行にするとネットワークに出られないことがあるため。

土日祝も動くが、JPXが公開していない日は何も送らないので放置してよい。

### メールが届いたら

本文に手動実行のURLと、Claudeへの依頼文がそのまま書いてある。

> 「サイトが2026-08-28のままなので手動実行して、本日の投稿文を作成してください」

## public_direction.py — 向きを公開データだけで推定する(検証用・非公開)

サイトのガンマ推定は「ディーラーはコールを買い持ち・プットを売り持ち」という
**一律の仮定**で符号を付けている。別手法(建玉×約定の向き)と突き合わせたところ、
裏付けが取れたのは**合計の符号まで**で、現値の上下の内訳は一致しなかった。
そこでトップページは合計を主役にし、内訳は参考値に落とした。

その先として「向きも公開データから推定できないか」を検証するためのスクリプト。
**結果はサイトに出さない**(まだ信号と雑音の区別がついていない)。

### 何をしているか

行使価格ごとに、前営業日からの建玉の増減(ΔOI)と、IVの増減(ΔIV)を取る。
ΔIVはその日の全銘柄のΔIVの**中央値を引いた残差**を使う(市場全体のIV変動を除くため)。

| その日の動き | 読み | ディーラー側 |
|---|---|---|
| ΔOI > 0 かつ 残差ΔIV > 0 | 需要主導(買いたい人が値を押し上げた) | 売り手 = ショートガンマ |
| ΔOI > 0 かつ 残差ΔIV < 0 | 供給主導(売りたい人が値を下げた) | 買い手 = ロングガンマ |
| ΔOI < 0 | 既存建玉の解消 | 積み上げた向きを按分して減らす |

1日の判定は雑音が多いので、**限月ごと・銘柄ごとに累積した状態量**として持つ。
最新日の建玉にサイトと同じブラック・ショールズのガンマを掛け、
**符号だけ**をこの累積方向で置き換えて合計・上側・下側を出す。

**不明分**は必ず見る。清算値段(`data/settle_*.csv`)は2026-10-05以降しか無いので、
それ以前に作られた建玉には向きを割り当てられない。不明分は寄与0にしてあるため、
この割合が高いうちは金額が小さく出る(履歴の `unknown_frac` 列)。

### 入力と出力

入力は `data/settle_YYYYMMDD.csv` と `data/oi_YYYYMMDD.csv` だけ。
出力は `private/public_direction_history.csv`(1行=1営業日)。

`private/dealer_gamma_history.csv` があれば日付で突き合わせ、
符号の一致と相関を表示する。**重なる日数が少ないうちは数字を並べるだけで、結論は出さない。**

### 動作確認

```
python tools\public_direction.py           全期間を再計算して履歴を更新(日別明細つき)
python tools\public_direction.py --quiet   履歴の更新だけ(定期実行用)
```

毎回全期間を頭から積み上げ直すので、何度走らせても結果は同じ(日付で上書き)。

### タスクスケジューラへの登録(※GitHub Actionsでは動かせない)

出力先が `private/` で、`private/` は `.gitignore` 済み=**コミットされない**。
GitHub Actions で走らせても結果がどこにも残らないため、**手元の定期タスクから動かす**。

`public_direction.bat` を呼ぶ。`data/` はGitHub Actionsがコミットする生成物なので、
バットの中で先に `git pull --ff-only` している。実行ログは
`tools\public_direction.log` に上書きで残る。

時刻は**建玉の公表(20:00頃)より後**にする。建玉が当日分になっていないと、
その日のΔOIが取れない。21:30にしてあるのは、デプロイ後のコミットを
`git pull` で取り込めるのを待つため。

```powershell
$bat = "C:\Users\tomo0\Projects\nk225-options-site\tools\public_direction.bat"
$action  = New-ScheduledTaskAction -Execute $bat -WorkingDirectory (Split-Path $bat -Parent)
$trigger = New-ScheduledTaskTrigger -Daily -At "21:30"
$set     = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "nk225-public-direction-2130" -Action $action -Trigger $trigger -Settings $set
```

`check_freshness` と同じく「ユーザーがログオンしているときのみ実行する」(Interactive)にする。
土日祝も動くが、新しいファイルが無い日は前日と同じ結果を上書きするだけなので放置してよい。

---

## 時刻どおりの自動更新(gas_trigger.gs)

### なぜ必要か

GitHub Actions の `schedule` は**落ちているのではなく、大幅に遅れている**。
2026-10-08〜11-06 の全実行を確認した結果:

| | 設定した最初のcron | 実際に走った時刻 |
|---|---|---|
| 2026-10-08〜10-23 | UTC 07:37 | UTC 12:40〜16:56 |
| 2026-10-26〜11-06 | UTC 07:37 | UTC 13:30〜17:23 |

**遅れは毎日5〜10時間**で、1日も欠けていなかった。JSTに直すと深夜0時〜翌朝6時の
ビルドになるため、夕方にサイトを見ると前営業日のままになる。
cronを8本から12本に増やしても、**12本ともまとめて遅れる**ので効果がなかった。

GitHubのスケジューラ自体が遅いので、GitHubの中で対策しても直らない。
時刻の正確な外部スケジューラから叩く。

### 構成

```
Google Apps Script (1時間ごとのトリガー)
        │  JSTの16/18/20/21/22時に
        ▼
GitHub API  POST /repos/.../dispatches  {"event_type":"build"}
        ▼
daily-update.yml の repository_dispatch が発火 → ビルド → デプロイ
```

Google のサーバーで動くので、**PCの電源が入っていなくても実行される**。
新しいデータが無い回はワークフロー側が `NO_NEW_DATA` で即スキップするため、
余分に叩いてもコストはない。既存の `schedule` は、遅れて届く保険として残してある。

### 設置手順

**1. GitHubのトークンを作る**

<https://github.com/settings/personal-access-tokens> →「Generate new token」

| 項目 | 値 |
|---|---|
| Repository access | Only select repositories → `nk225-option-site` |
| Permissions | Repository permissions → **Actions: Read and write** のみ |
| Expiration | 任意(切れると下の失敗メールが届く) |

他の権限は付けない。表示されたトークンはこの画面でしか見られない。

**2. Apps Script プロジェクトを作る**

<https://script.google.com/> →「新しいプロジェクト」
→ `tools/gas_trigger.gs` の中身をまるごと貼り付けて保存。

**3. トークンを登録する**

プロジェクトの設定(歯車)→「スクリプト プロパティ」→ プロパティを追加

| プロパティ | 値 |
|---|---|
| `GITHUB_TOKEN` | 1で作ったトークン |

コードには書かない。スクリプトプロパティはプロジェクトの所有者しか読めない。

**4. 動作確認**

関数 `testDispatch` を選んで実行。初回は Google の認可画面が出るので許可する。
成功すると GitHub の Actions に `repository_dispatch` の実行が現れる。

<https://github.com/matsutoushi/nk225-option-site/actions>

**5. トリガーを作る**

関数 `setupTrigger` を一度だけ実行する。1時間ごとのトリガーが登録される。
以後は何もしなくてよい。

### 監視

- JSTの23時に、公開サイトの「データ基準日」を読む。当日でなければメールが届く
- `repository_dispatch` が 204 以外を返した場合もメールが届く
  (トークンの期限切れ・権限不足が主な原因)

祝日やJPXの休場日は当日のデータが出ないので、23時のメールが届くことがある。
平日なのに前営業日のままなら Actions の実行履歴を見る。

### 叩く時刻を変える

`gas_trigger.gs` の `DISPATCH_HOURS_JST` を書き換えて保存するだけでよい。
トリガーの作り直しは不要(1時間ごとに起きて、その中で時刻を見ている)。
