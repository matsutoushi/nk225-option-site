/**
 * nk225-option.com を時刻どおりに自動更新するための外部トリガー(Google Apps Script)。
 *
 * なぜ必要か
 *   GitHub Actions の schedule は「落ちる」のではなく「大幅に遅れる」。
 *   実測(2026-10-08〜11-06)では、最初の cron(UTC 07:37)に対して実際の実行は
 *   UTC 12:40〜17:23 で、遅れは5〜10時間あった。JSTでは深夜〜翌朝にあたるため、
 *   夕方のうちにサイトが更新されない。
 *   Google 側の時刻トリガーはほぼ定刻で動くので、そこから GitHub の
 *   repository_dispatch を叩いてビルドを起こす。
 *
 * 端末は関係ない
 *   このスクリプトは Google のサーバーで動く。PCの電源が入っていなくても実行される。
 *
 * 必要なもの
 *   GitHub のファイングレインド個人アクセストークン(このリポジトリのみ・
 *   Actions の Read and write だけ)。値はスクリプトプロパティに入れる。
 *   コードには書かない。
 *
 * 置き換える必要はない定数
 *   OWNER / REPO / EVENT_TYPE は daily-update.yml の repository_dispatch に対応する。
 */

var OWNER = 'matsutoushi';
var REPO = 'nk225-option-site';
var EVENT_TYPE = 'build';     // daily-update.yml の repository_dispatch.types と合わせる
var SITE_URL = 'https://nk225-option.com/';

// JSTで叩く時刻(時)。JPXの公表に合わせる。
//   16時台: 出来高・価格
//   17-18時台: 手口(17:45頃)
//   20-22時台: 建玉残高(20:00頃)
// 新しいデータが無い回はワークフロー側が NO_NEW_DATA で即スキップするので、
// 余分に叩いても実質コストはない。
var DISPATCH_HOURS_JST = [16, 18, 20, 21, 22];

// サイトが古いままなら知らせる時刻(JST)。1日1回。
var STALE_CHECK_HOUR_JST = 23;


/** 1時間ごとのトリガーから呼ばれる入口。 */
function tick() {
  var now = nowJst();
  var day = now.getDay();          // 0=日, 6=土
  if (day === 0 || day === 6) return;

  var hour = now.getHours();
  if (DISPATCH_HOURS_JST.indexOf(hour) >= 0) {
    dispatchBuild();
  }
  if (hour === STALE_CHECK_HOUR_JST) {
    warnIfStale();
  }
}


/** GitHub にビルドを依頼する。 */
function dispatchBuild() {
  var token = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
  if (!token) {
    throw new Error('スクリプトプロパティ GITHUB_TOKEN が未設定です');
  }
  var res = UrlFetchApp.fetch(
    'https://api.github.com/repos/' + OWNER + '/' + REPO + '/dispatches',
    {
      method: 'post',
      contentType: 'application/json',
      headers: {
        Authorization: 'Bearer ' + token,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28'
      },
      payload: JSON.stringify({ event_type: EVENT_TYPE }),
      muteHttpExceptions: true
    });
  var code = res.getResponseCode();
  // 204 No Content が成功。それ以外はログに残す(トリガーの実行履歴から追える)。
  Logger.log('dispatch -> ' + code + ' ' + res.getContentText().slice(0, 200));
  if (code !== 204) {
    MailApp.sendEmail(Session.getEffectiveUser().getEmail(),
      '[nk225] ビルド依頼が失敗しました (' + code + ')',
      'repository_dispatch が ' + code + ' を返しました。\n\n'
      + res.getContentText().slice(0, 500)
      + '\n\nトークンの期限切れか、権限(Actions: Read and write)の不足が疑われます。');
  }
}


/**
 * 公開中のサイトのデータ基準日を読み、当日ぶんが出ていなければメールで知らせる。
 * ビルドが起きなかったことに気づけないのがいちばん困るので、最後の砦として置く。
 */
function warnIfStale() {
  var html = UrlFetchApp.fetch(SITE_URL, { muteHttpExceptions: true }).getContentText();
  var m = html.match(/データ基準日:\s*(\d{4})-(\d{2})-(\d{2})/);
  if (!m) {
    Logger.log('データ基準日が読み取れませんでした');
    return;
  }
  var siteDate = m[1] + m[2] + m[3];
  var today = Utilities.formatDate(nowJst(), 'Asia/Tokyo', 'yyyyMMdd');
  if (siteDate === today) return;

  MailApp.sendEmail(Session.getEffectiveUser().getEmail(),
    '[nk225] サイトが当日のデータになっていません',
    'サイトのデータ基準日: ' + m[1] + '-' + m[2] + '-' + m[3] + '\n'
    + '今日(JST): ' + today + '\n\n'
    + 'JPXが休場だった日や、祝日の翌営業日は正常です。\n'
    + '平日なのに前営業日のままなら、Actions の実行履歴を確認してください。\n'
    + 'https://github.com/' + OWNER + '/' + REPO + '/actions');
}


/** 日本時間の現在時刻。スクリプトのタイムゾーン設定に依存しないようにする。 */
function nowJst() {
  var s = Utilities.formatDate(new Date(), 'Asia/Tokyo', 'yyyy/MM/dd HH:mm:ss');
  return new Date(s);
}


/** 一度だけ実行して、1時間ごとのトリガーを作る。 */
function setupTrigger() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'tick') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('tick').timeBased().everyHours(1).create();
  Logger.log('1時間ごとのトリガーを作成しました');
}


/** 手で叩いて動作確認するためのもの。 */
function testDispatch() {
  dispatchBuild();
}
