/* 独立登录/注册页。
   - 地址 #register 进入注册模式，可直接分享注册链接
   - ?reason=expired|disabled：从主站/账户中心被动跳转时说明原因
   - ?next=/static/...：登录成功后回到来源页（仅允许本站 /static/ 下的页面，防开放重定向）
   token、用户名、角色与主站共用 localStorage（同源）。 */
(function () {
  "use strict";

  const TOKEN_KEY = "sh.token";
  const USER_KEY = "sh.username";
  const ROLE_KEY = "sh.role";
  const DEFAULT_NEXT = "/static/index.html";

  const REASONS = {
    expired: "登录已过期，请重新登录",
    disabled: "账号已被禁用，请联系管理员",
  };

  const $ = (id) => document.getElementById(id);
  const params = new URLSearchParams(location.search);

  /** 只接受同源、/static/ 下且不是登录页本身的地址，其余一律回主站 */
  function safeNext(raw) {
    if (!raw) return DEFAULT_NEXT;
    try {
      const url = new URL(raw, location.origin);
      if (url.origin !== location.origin) return DEFAULT_NEXT;
      if (!url.pathname.startsWith("/static/") || url.pathname.startsWith("/static/login")) return DEFAULT_NEXT;
      return url.pathname + url.search + url.hash;
    } catch {
      return DEFAULT_NEXT;
    }
  }

  const next = safeNext(params.get("next"));

  // 已登录直接去目标页（例如在新标签页打开了登录页）
  try {
    if (localStorage.getItem(TOKEN_KEY)) {
      location.replace(next);
      return;
    }
  } catch { /* 存储不可用时留在登录页，提交时会提示 */ }

  const form = $("login-form");
  const card = form;
  const inputs = { username: $("login-username"), password: $("login-password"), password2: $("login-password2") };
  let mode = "login";
  let busy = false;

  function setMode(m) {
    mode = m === "register" ? "register" : "login";
    const reg = mode === "register";
    card.classList.toggle("is-register", reg);
    $("login-title").textContent = reg ? "注册新账号" : "登录 Spring Harness";
    $("login-sub").textContent = reg ? "注册后将自动登录" : "登录后即可开始与 Agent 协作";
    $("login-submit").textContent = reg ? "注册并登录" : "登录";
    $("login-switch-text").textContent = reg ? "已有账号？" : "没有账号？";
    $("login-switch-link").textContent = reg ? "返回登录" : "注册新账号";
    $("login-switch-link").setAttribute("href", reg ? "#login" : "#register");
    inputs.password.autocomplete = reg ? "new-password" : "current-password";
    document.title = (reg ? "注册" : "登录") + " - Spring Harness";
    showError("");
  }

  function showError(msg, field) {
    $("login-error").textContent = msg || "";
    for (const el of Object.values(inputs)) el.classList.remove("invalid");
    if (field && inputs[field]) {
      inputs[field].classList.add("invalid");
      inputs[field].focus();
    }
  }

  function setBusy(on) {
    busy = on;
    const btn = $("login-submit");
    btn.disabled = on;
    if (on) btn.textContent = mode === "register" ? "注册中…" : "登录中…";
    else btn.textContent = mode === "register" ? "注册并登录" : "登录";
  }

  /** POST 认证接口；网关统一返回 {code, message, data}，错误详情在 message 里 */
  async function post(path, body) {
    let r;
    try {
      r = await fetch(`/api/auth/${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    } catch {
      throw new Error("网络错误，请检查连接后重试");
    }
    const payload = await r.json().catch(() => null);
    if (!r.ok) throw new Error((payload && payload.message) || `请求失败（${r.status}）`);
    return payload ? payload.data : null;
  }

  function validate(username, password) {
    if (!username) return ["请输入用户名", "username"];
    if (!password) return ["请输入密码", "password"];
    if (mode === "register") {
      if (username.length < 2 || username.length > 64) return ["用户名长度需 2~64 个字符", "username"];
      if (password.length < 6) return ["密码至少 6 位", "password"];
      if (password !== inputs.password2.value) return ["两次输入的密码不一致", "password2"];
    }
    return null;
  }

  async function onSubmit(e) {
    e.preventDefault();
    if (busy) return;
    const username = inputs.username.value.trim();
    const password = inputs.password.value;
    const invalid = validate(username, password);
    if (invalid) { showError(invalid[0], invalid[1]); return; }

    showError("");
    setBusy(true);
    const registering = mode === "register";
    try {
      if (registering) await post("register", { username, password });
    } catch (err) {
      setBusy(false);
      showError(err.message);
      return;
    }
    try {
      const data = await post("login", { username, password });
      localStorage.setItem(TOKEN_KEY, data.token);
      localStorage.setItem(USER_KEY, data.username);
      localStorage.setItem(ROLE_KEY, data.role || "user");
      localStorage.removeItem("sh.sessionId");  // 换账号不复用旧会话
      location.replace(next);
    } catch (err) {
      setBusy(false);
      if (registering) {
        // 账号已建好，只是自动登录没成功：切回登录模式，保留已填的用户名密码
        // （replaceState 改地址不触发 hashchange，避免刚显示的错误被清掉）
        history.replaceState(null, "", location.pathname + location.search + "#login");
        setMode("login");
        showError("注册成功，但自动登录失败：" + err.message);
      } else {
        showError(err.message);
      }
    }
  }

  form.addEventListener("submit", onSubmit);
  form.addEventListener("input", () => { if ($("login-error").textContent) showError(""); });
  // 用户名回车：密码还空着时只跳到密码框，不急着报错
  inputs.username.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !inputs.password.value) {
      e.preventDefault();
      inputs.password.focus();
    }
  });
  window.addEventListener("hashchange", () => {
    setMode(location.hash === "#register" ? "register" : "login");
    inputs.username.focus();
  });

  const reason = REASONS[params.get("reason")];
  if (reason) {
    $("login-notice").textContent = reason;
    $("login-notice").classList.remove("hidden");
  }
  setMode(location.hash === "#register" ? "register" : "login");
  inputs.username.focus();
})();
