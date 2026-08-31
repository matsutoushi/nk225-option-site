# -*- coding: utf-8 -*-
"""サイトが最新のJPXデータに追いついているかを見て、遅れていればメールで知らせる。

なぜ必要か:
  GitHub Actionsのスケジュール実行はベストエフォートで、混雑時に遅延・スキップされる。
  2026-08-27以降、7〜10時間の遅延が常態化し、当日のデータで投稿できない日が出た。
  ワークフロー側では直せないので、手元から監視して気づけるようにする。

判定の考え方:
  「今日が平日かどうか」では祝日に誤検知する。代わりに
  **JPXが公開している最新日 vs サイトの掲載日** を比べる。
  JPXが今日の分を出しているのにサイトが古ければ、それは本当に遅れている。
  JPXがまだ出していなければ、サイトが古くて当たり前なので何もしない。

使い方:
    python tools/check_freshness.py           # 判定してメール(遅れていれば)
    python tools/check_freshness.py --dry-run # メールを送らず結果だけ表示
    python tools/check_freshness.py --force   # 遅れていなくてもテスト送信

事前設定(パスワードはこのファイルに書かない):
    setx NK225_MAIL_TO       "あなたのGmailアドレス"
    setx NK225_MAIL_PASSWORD "Googleアプリパスワード16桁"
  ※通常のGoogleアカウントのパスワードではなく、2段階認証の「アプリパスワード」。
    GitHub Actions の MAIL_APP_PASSWORD と同じものが使える。
"""

import argparse
import datetime
import io
import json
import os
import re
import smtplib
import sys
import urllib.request
from email.message import EmailMessage

SITE_URL = "https://matsutoushi.github.io/nk225-option-site/"
JPX_INDEX = "https://www.jpx.co.jp/markets/derivatives/trading-volume/index.html"
ACTIONS_URL = "https://github.com/matsutoushi/nk225-option-site/actions/workflows/daily-update.yml"
UA = {"User-Agent": "Mozilla/5.0 (compatible; nk225-options-site freshness check)"}

STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".freshness_state.json")
JST = datetime.timezone(datetime.timedelta(hours=9))


def get(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def jpx_latest_date() -> str | None:
    """JPXが公開している最新の日付(YYYY-MM-DD)。取れなければNone。

    当日取引高ページのファイル名 (例: .../20260831_derivatives_...) から読む。
    Excelは落とさない。ファイル名だけ見れば足りる。
    """
    try:
        html = get(JPX_INDEX)
    except Exception as e:
        print(f"JPXページを取得できませんでした: {e}")
        return None
    dates = re.findall(r"/(\d{8})_derivatives", html)
    if not dates:
        print("JPXページの構成が変わった可能性があります(日付が見つからない)")
        return None
    d = max(dates)
    return f"{d[:4]}-{d[4:6]}-{d[6:]}"


def site_date() -> str | None:
    """サイトが掲載しているデータ基準日(YYYY-MM-DD)。"""
    try:
        html = get(SITE_URL)
    except Exception as e:
        print(f"サイトを取得できませんでした: {e}")
        return None
    m = re.search(r"データ基準日:\s*(\d{4}-\d{2}-\d{2})", html)
    if not m:
        print("サイトから データ基準日 を読み取れませんでした")
        return None
    return m.group(1)


def load_state() -> dict:
    try:
        return json.load(io.open(STATE, encoding="utf-8"))
    except Exception:
        return {}


def save_state(d: dict) -> None:
    io.open(STATE, "w", encoding="utf-8", newline="\n").write(
        json.dumps(d, ensure_ascii=False, indent=2) + "\n")


def send_mail(subject: str, body: str) -> bool:
    to = os.environ.get("NK225_MAIL_TO", "").strip()
    pw = os.environ.get("NK225_MAIL_PASSWORD", "").strip()
    if not (to and pw):
        print("NK225_MAIL_TO / NK225_MAIL_PASSWORD が未設定のため送信しません。")
        print("--- 送るはずだった内容 ---")
        print(subject)
        print(body)
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = to
    msg["To"] = to
    msg.set_content(body)
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
            s.login(to, pw)
            s.send_message(msg)
    except Exception as e:
        print(f"メール送信に失敗しました: {e}")
        return False
    print(f"メールを送信しました → {to}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="メールを送らず結果だけ表示")
    ap.add_argument("--force", action="store_true", help="遅れていなくてもテスト送信")
    args = ap.parse_args()

    now = datetime.datetime.now(JST)
    jpx = jpx_latest_date()
    site = site_date()
    print(f"[{now:%Y-%m-%d %H:%M} JST] JPX公開日={jpx}  サイト掲載日={site}")

    if jpx is None or site is None:
        # 取得自体に失敗したときは黙る。ネットワークの一時的な不調で毎回メールが来ても困る。
        print("判定に必要な情報が揃わなかったため、何もしません。")
        return 0

    stale = site < jpx
    if not stale and not args.force:
        print("サイトは最新です。何もしません。")
        return 0

    state = load_state()
    if state.get("alerted_for") == jpx and not args.force:
        print(f"{jpx} については通知済みです。重複して送りません。")
        return 0

    if stale:
        subject = f"[nk225] サイトが未更新です ({site} → JPXは {jpx})"
        head = "日経225オプションのデータサイトが、JPXの公開に追いついていません。"
        tail = (f"GitHub Actionsのスケジュール実行が遅延・スキップされた可能性があります。\n"
                f"手動実行はこちら:\n  {ACTIONS_URL}\n\n"
                f"Claudeに頼む場合は、次のように伝えてください:\n"
                f"  「サイトが{site}のままなので手動実行して、本日の投稿文を作成してください」\n")
    else:
        # --force のテスト送信。サイトは正常なので、遅延の文面を送ると紛らわしい。
        subject = "[nk225] 更新チェックのテスト送信"
        head = "メール経路の確認です。サイトは正常で、遅延は起きていません。"
        tail = ("この文面が届いていれば設定は完了です。\n"
                "実際に遅延が起きたときは、件名が「サイトが未更新です」になり、\n"
                "手動実行のURLとClaudeへの依頼文が入ります。\n")
    body = (
        f"{head}\n\n"
        f"  JPXが公開している最新日 : {jpx}\n"
        f"  サイトが掲載している日  : {site}\n"
        f"  確認時刻                : {now:%Y-%m-%d %H:%M} JST\n\n"
        f"{tail}"
    )
    if args.dry_run:
        print("--- dry-run: 送信しません ---")
        print(subject)
        print(body)
        return 1

    sent = send_mail(subject, body)
    # 記録するのは本当に遅れていたときだけ。--force のテスト送信で記録してしまうと、
    # 同じ日に本物の遅延が起きても「通知済み」と判定されて黙ってしまう。
    if sent and stale:
        state["alerted_for"] = jpx
        state["alerted_at"] = now.isoformat()
        save_state(state)
    return 1


if __name__ == "__main__":
    sys.exit(main())
