/* ==============================================================
 * 治験ダッシュボード 簡易閲覧パスワードゲート (Plan B)
 * --------------------------------------------------------------
 * パスワードを変更したいときは、このファイル内の
 *     var AUTH_PASSWORD = "..."
 * の値だけを書き換えて push してください。他の箇所は触らなくて OK。
 *
 * 注意: これはあくまで簡易ゲートです。GitHub Pages 上で
 * このファイルは公開されているため、ソースを開けばパスワードは
 * そのまま見えます。完全な保護が必要な場合は GitHub Pro の
 * Private Pages 等を検討してください。
 * ============================================================== */
(function () {
  var AUTH_PASSWORD = "chiken2026spring";   // ← パスワードはここを書き換える
  var AUTH_KEY      = "chiken_dash_auth_v1"; // sessionStorage のキー名

  // --- 0. すでに認証済みなら何もしない（ページをそのまま見せる） ---
  try {
    if (sessionStorage.getItem(AUTH_KEY) === "1") return;
  } catch (e) { /* private mode などで sessionStorage が使えないケース */ }

  // --- 1. 本文を一時非表示にして「中身が一瞬見える」のを防ぐ ---
  var hideStyle = document.createElement("style");
  hideStyle.id = "__authHideStyle";
  hideStyle.textContent =
    "html.__authLocked > body { visibility: hidden !important; } " +
    "html.__authLocked { overflow: hidden !important; }";
  (document.head || document.documentElement).appendChild(hideStyle);
  document.documentElement.classList.add("__authLocked");

  // --- 2. オーバーレイを生成 ---
  function buildGate() {
    var gate = document.createElement("div");
    gate.id = "__authGate";
    gate.setAttribute("style", [
      "position:fixed", "inset:0", "z-index:2147483647",
      "background:radial-gradient(ellipse at top, #102845 0%, #0a1c33 35%, #061325 70%, #030a18 100%)",
      "display:flex", "align-items:center", "justify-content:center",
      "font-family:-apple-system,'SF Pro Display','Hiragino Mincho ProN','Yu Mincho','Yu Gothic',sans-serif",
      "visibility:visible"
    ].join(";"));
    gate.innerHTML = ''
      + '<div style="background:linear-gradient(145deg, rgba(20,38,67,0.95) 0%, rgba(11,24,44,0.98) 100%);'
      +              'border:1px solid rgba(201,165,88,0.4);border-radius:16px;'
      +              'padding:44px 52px;box-shadow:0 24px 60px rgba(0,0,0,0.6);'
      +              'min-width:340px;max-width:90vw;text-align:center;">'
      +   '<div style="font-size:1.35rem;font-weight:300;letter-spacing:0.08em;'
      +                'background:linear-gradient(135deg, #e0bb73 0%, #f1e4c6 50%, #c9a558 100%);'
      +                '-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;'
      +                'margin-bottom:6px;">治験ダッシュボード</div>'
      +   '<div style="color:#a8b8d0;font-size:0.82rem;letter-spacing:0.06em;margin-bottom:24px;">'
      +     '閲覧パスワードを入力してください</div>'
      +   '<input id="__authInput" type="password" autocomplete="off" '
      +     'style="width:100%;padding:12px 16px;background:rgba(8,20,38,0.8);'
      +            'border:1px solid rgba(201,165,88,0.4);border-radius:8px;color:#f1e4c6;'
      +            'font-size:1rem;letter-spacing:0.05em;font-family:inherit;outline:none;text-align:center;" />'
      +   '<div id="__authError" style="color:#f87171;font-size:0.78rem;margin-top:8px;'
      +                                 'min-height:1em;letter-spacing:0.04em;"></div>'
      +   '<button id="__authBtn" type="button" '
      +     'style="margin-top:14px;width:100%;padding:12px 16px;'
      +            'background:linear-gradient(135deg,#c9a558 0%,#8a6f30 100%);'
      +            'border:none;border-radius:8px;color:#0a1c33;font-weight:600;'
      +            'letter-spacing:0.1em;font-size:0.9rem;cursor:pointer;font-family:inherit;">入 室</button>'
      + '</div>';
    return gate;
  }

  function unlock() {
    try { sessionStorage.setItem(AUTH_KEY, "1"); } catch (e) {}
    var g = document.getElementById("__authGate");
    if (g && g.parentNode) g.parentNode.removeChild(g);
    document.documentElement.classList.remove("__authLocked");
    var s = document.getElementById("__authHideStyle");
    if (s && s.parentNode) s.parentNode.removeChild(s);
  }

  function init() {
    // DOMContentLoaded の時点で再チェック（直前タブで認証していた場合）
    try {
      if (sessionStorage.getItem(AUTH_KEY) === "1") { unlock(); return; }
    } catch (e) {}

    var gate  = buildGate();
    document.body.appendChild(gate);
    var input = document.getElementById("__authInput");
    var btn   = document.getElementById("__authBtn");
    var err   = document.getElementById("__authError");

    function check() {
      if (input.value === AUTH_PASSWORD) {
        unlock();
      } else {
        err.textContent = "パスワードが違います";
        input.value = "";
        input.focus();
      }
    }
    btn.addEventListener("click", check);
    input.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); check(); }
    });
    setTimeout(function () { input.focus(); }, 30);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
