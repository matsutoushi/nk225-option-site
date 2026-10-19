# -*- coding: utf-8 -*-
"""日付つき解説記事(content/posts/*.md)の読み込みと、最小限のMarkdown変換。

このサイトの本体はJPX公表データから毎営業日自動生成するデータページだが、
それとは別に「人が書いた、日付の入った記事」を積む層をここで扱う。

Markdownライブラリは入れていない。pipeline/requirements.txt を増やすと
GitHub Actionsの依存解決が増えるだけなので、記事で実際に使う記法
(見出し・段落・箇条書き・番号つき・表・引用・強調・リンク・コード)
だけを自前で処理する。想定外の記法は素のテキストとしてそのまま出る。
"""

import html
import os
import re

# 1記事1ファイル。ファイル名がそのまま公開日とURLになる。
FNAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")

_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_CODE = re.compile(r"`([^`]+)`")


def _inline(text: str) -> str:
    """段落・セル・項目の中身を変換する。先にエスケープしてからタグを足す。"""
    out = html.escape(text.strip())
    # エスケープ済みなので、リンクURLに含まれる & は &amp; になっている。属性値としては正しい。
    out = _CODE.sub(r"<code>\1</code>", out)
    out = _BOLD.sub(r"<b>\1</b>", out)
    out = _LINK.sub(r'<a href="\2">\1</a>', out)
    return out


def _table(rows: list) -> str:
    """|で区切った行の塊を表にする。1行目が見出し、2行目が区切り(---)なら捨てる。"""
    def cells(line):
        return [c for c in line.strip().strip("|").split("|")]
    body = rows[1:]
    if len(rows) > 1 and set(rows[1].replace("|", "").replace(":", "").strip()) <= {"-", " "}:
        body = rows[2:]
    head = "".join(f"<th>{_inline(c)}</th>" for c in cells(rows[0]))
    trs = "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in cells(r)) + "</tr>"
                  for r in body)
    return f'<div class="tbl-wrap"><table><thead><tr>{head}</tr></thead><tbody>{trs}</tbody></table></div>'


def md_to_html(text: str) -> str:
    """記事本文のMarkdownをHTMLにする。対応記法はモジュールのdocstringのとおり。"""
    out = []
    buf = []          # 書きかけの段落
    items = []        # 書きかけのリスト項目
    list_tag = ""     # ul / ol
    tbl = []          # 書きかけの表の行
    quote = []        # 書きかけの引用

    def flush_para():
        # 連続した行は1つの段落にまとめる(段落の区切りは空行)。日本語なので
        # 行をつなぐときに空白は入れない。原稿側で好きな位置に改行を入れられる。
        if buf:
            out.append("<p>" + "".join(_inline(b) for b in buf) + "</p>")
            buf.clear()

    def flush_list():
        nonlocal list_tag
        if items:
            lis = "".join(f"<li>{_inline(i)}</li>" for i in items)
            out.append(f"<{list_tag}>{lis}</{list_tag}>")
            items.clear()
            list_tag = ""

    def flush_tbl():
        if tbl:
            out.append(_table(list(tbl)))
            tbl.clear()

    def flush_quote():
        if quote:
            out.append("<blockquote>" + "".join(f"<p>{_inline(q)}</p>" for q in quote)
                       + "</blockquote>")
            quote.clear()

    def flush_all():
        flush_para()
        flush_list()
        flush_tbl()
        flush_quote()

    for raw in text.split("\n"):
        line = raw.rstrip()
        s = line.strip()
        if not s:
            flush_all()
            continue
        if s.startswith("|") and s.endswith("|"):
            flush_para()
            flush_list()
            flush_quote()
            tbl.append(s)
            continue
        flush_tbl()
        m = re.match(r"^(#{2,4})\s+(.*)$", s)
        if m:
            flush_all()
            lv = len(m.group(1))
            out.append(f"<h{lv}>{_inline(m.group(2))}</h{lv}>")
            continue
        if s.startswith("> "):
            flush_para()
            flush_list()
            quote.append(s[2:])
            continue
        flush_quote()
        m = re.match(r"^[-*]\s+(.*)$", s)
        if m:
            flush_para()
            if list_tag and list_tag != "ul":
                flush_list()
            list_tag = "ul"
            items.append(m.group(1))
            continue
        m = re.match(r"^\d+[.)]\s+(.*)$", s)
        if m:
            flush_para()
            if list_tag and list_tag != "ol":
                flush_list()
            list_tag = "ol"
            items.append(m.group(1))
            continue
        flush_list()
        buf.append(s)
    flush_all()
    return "\n".join(out)


def parse_post(path: str) -> dict:
    """1ファイルを読んで {date, slug, title, desc, body_md, html} にする。

    先頭の --- で囲んだ範囲を `キー: 値` として読む。title は必須、
    date はファイル名を既定値にする(ファイル名とズレたら front matter を優先)。
    """
    fname = os.path.basename(path)
    m = FNAME_RE.match(fname)
    if not m:
        raise ValueError(f"記事のファイル名はYYYY-MM-DD.md: {fname}")
    with open(path, encoding="utf-8") as f:
        text = f.read().replace("\r\n", "\n").lstrip("﻿")
    meta = {}
    body = text
    if text.startswith("---\n"):
        head, _, body = text[4:].partition("\n---")
        body = body.lstrip("\n")
        for line in head.split("\n"):
            k, sep, v = line.partition(":")
            if sep and k.strip():
                meta[k.strip().lower()] = v.strip().strip('"')
    title = meta.get("title", "").strip()
    if not title:
        raise ValueError(f"title が無い: {fname}")
    desc = (meta.get("description") or meta.get("desc") or "").strip()
    date = meta.get("date", "").strip() or m.group(1)
    return {
        "date": date,
        "slug": m.group(1),
        "title": title,
        "desc": desc,
        "body_md": body,
        "html": md_to_html(body),
    }


def load_posts(posts_dir: str) -> list:
    """content/posts/ の記事を新しい順に返す。ディレクトリが無ければ空リスト。"""
    if not os.path.isdir(posts_dir):
        return []
    out = []
    for fname in sorted(os.listdir(posts_dir)):
        if not FNAME_RE.match(fname):
            continue
        out.append(parse_post(os.path.join(posts_dir, fname)))
    out.sort(key=lambda p: p["slug"], reverse=True)
    return out


def date_ja(slug: str) -> str:
    """2026-10-19 → 2026年10月19日。"""
    y, m, d = slug.split("-")
    return f"{int(y)}年{int(m)}月{int(d)}日"
