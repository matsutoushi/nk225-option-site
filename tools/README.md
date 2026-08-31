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
