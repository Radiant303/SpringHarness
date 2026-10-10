/* 独立登录/注册/重置密码页。
   - 地址 #register 进入注册模式，#reset 进入重置密码模式，可直接分享链接
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

  const MODES = {
    login: { title: "登录", switchText: "没有账号？", switchLink: "注册", switchHash: "#register", submit: "登录", busy: "登录中…" },
    register: { title: "注册", switchText: "已有账号？", switchLink: "登录", switchHash: "#login", submit: "注册并登录", busy: "注册中…" },
    reset: { title: "重置密码", switchText: "想起密码了？", switchLink: "登录", switchHash: "#login", submit: "重置密码", busy: "重置中…" },
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
  const inputs = {
    username: $("login-username"),
    password: $("login-password"),
    password2: $("login-password2"),
    email: $("login-email"),
    code: $("login-code"),
    newPassword: $("login-new-password"),
    newPassword2: $("login-new-password2"),
  };
  const sendCodeBtn = $("login-send-code");
  let mode = "login";
  let busy = false;
  let cdTimer = null;  // 重发倒计时定时器
  let mailVerify = false;  // 站长是否开启了邮箱验证码功能（驱动邮箱/验证码字段显隐、校验与忘记密码入口）
  let configLoaded = false;  // register-config 返回前不要把 #reset 误判成"未开启"
  // URL reason 带来的提示不被模式切换清掉；重置成功这类临时提示会被清掉
  let noticePinned = false;

  /** 当前模式是否需要邮箱+验证码字段（注册且站长开启，或重置密码） */
  const needsCode = () => (mode === "register" && mailVerify) || mode === "reset";

  // 拉取注册页公开配置：开启邮箱验证码功能时才显示相关字段与忘记密码入口
  fetch("/api/auth/register-config")
    .then((r) => r.json())
    .then((p) => {
      mailVerify = !!(p && p.data && p.data.mailVerify);
      configLoaded = true;
      // 用户名占位符只在开启邮箱功能时提"邮箱"（支持邮箱登录）
      inputs.username.placeholder = mailVerify ? "请输入用户名或注册邮箱" : "请输入用户名";
      setMode(mode);  // 重新评估字段显隐
    })
    .catch(() => { /* 拉取失败按未开启处理；服务端仍会兜底校验 */ });

  function setMode(m) {
    mode = MODES[m] ? m : "login";
    // 未开启邮箱功能时重置密码模式无意义（发不出验证码），直接回登录模式
    if (mode === "reset" && configLoaded && !mailVerify) {
      history.replaceState(null, "", location.pathname + location.search + "#login");
      mode = "login";
    }
    const conf = MODES[mode];
    form.classList.toggle("is-register", mode === "register");
    form.classList.toggle("is-reset", mode === "reset");
    form.classList.toggle("is-code", needsCode());
    $("login-title").textContent = conf.title;
    $("login-switch-text").textContent = conf.switchText;
    $("login-switch-link").textContent = conf.switchLink;
    $("login-switch-link").setAttribute("href", conf.switchHash);
    $("login-submit").textContent = conf.submit;
    // 忘记密码入口：只在登录模式且邮箱验证码功能开启时出现
    $("login-forgot-link").classList.toggle("hidden", !(mode === "login" && mailVerify));
    inputs.password.autocomplete = mode === "login" ? "current-password" : "new-password";
    document.title = conf.title + " - Spring Harness";
    if (!noticePinned) showNotice("");
    // 切换模式时把已显示的密码收回隐藏状态，避免明文留在屏幕上
    form.querySelectorAll(".login-eye").forEach((btn) => setRevealed(btn, false));
    showError("");
  }

  /* ---- 显示/隐藏密码：隐藏时画带斜杠的眼睛，点一下变明文 ---- */
  const EYE_SVG = (slashed) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"
    stroke-linecap="round" stroke-linejoin="round">${slashed
      ? '<path d="M4 4.5l15.5 15.5"/><path d="M9.8 6A9.9 9.9 0 0 1 12 5.7c5.9 0 9.5 6.3 9.5 6.3a17.5 17.5 0 0 1-3.6 4.2M6.6 7.8A17.6 17.6 0 0 0 2.5 12s3.6 6.3 9.5 6.3c1 0 1.9-.2 2.7-.5"/><path d="M9.7 9.9a2.9 2.9 0 0 0 3.9 3.9"/>'
      : '<path d="M2.5 12S6.1 5.7 12 5.7 21.5 12 21.5 12 17.9 18.3 12 18.3 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="2.9"/>'}</svg>`;

  function setRevealed(btn, show) {
    const input = $(btn.dataset.eye);
    if (!input) return;
    input.type = show ? "text" : "password";
    btn.innerHTML = EYE_SVG(!show);
    btn.setAttribute("aria-pressed", String(show));
    btn.setAttribute("aria-label", show ? "隐藏密码" : "显示密码");
  }

  function showError(msg, field) {
    $("login-error").textContent = msg || "";
    for (const el of Object.values(inputs)) el.classList.remove("invalid");
    if (field && inputs[field]) {
      inputs[field].classList.add("invalid");
      inputs[field].focus();
    }
  }

  function showNotice(msg) {
    $("login-notice").textContent = msg || "";
    $("login-notice").classList.toggle("hidden", !msg);
  }

  function setBusy(on) {
    busy = on;
    const btn = $("login-submit");
    btn.disabled = on;
    btn.textContent = on ? MODES[mode].busy : MODES[mode].submit;
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

  const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  function validate() {
    const username = inputs.username.value.trim();
    const password = inputs.password.value;
    if (mode === "reset") {
      if (!EMAIL_RE.test(inputs.email.value.trim())) return ["请输入正确的邮箱地址", "email"];
      if (!/^\d{6}$/.test(inputs.code.value.trim())) return ["请输入 6 位数字验证码", "code"];
      if (inputs.newPassword.value.length < 6) return ["密码至少 6 位", "newPassword"];
      if (inputs.newPassword.value !== inputs.newPassword2.value) return ["两次输入的密码不一致", "newPassword2"];
      return null;
    }
    if (!username) return ["请输入用户名", "username"];
    if (!password) return ["请输入密码", "password"];
    if (mode === "register") {
      if (username.length < 2 || username.length > 64) return ["用户名长度需 2~64 个字符", "username"];
      if (password.length < 6) return ["密码至少 6 位", "password"];
      if (password !== inputs.password2.value) return ["两次输入的密码不一致", "password2"];
      if (mailVerify) {
        if (!EMAIL_RE.test(inputs.email.value.trim())) return ["请输入正确的邮箱地址", "email"];
        if (!/^\d{6}$/.test(inputs.code.value.trim())) return ["请输入 6 位数字验证码", "code"];
      }
    }
    return null;
  }

  /* ---- 获取验证码：成功一次后按服务端返回的间隔倒计时，期间禁止重发 ---- */
  function startCountdown(seconds) {
    clearInterval(cdTimer);
    let left = seconds;
    sendCodeBtn.disabled = true;
    sendCodeBtn.textContent = left + "s 后重发";
    cdTimer = setInterval(() => {
      left -= 1;
      if (left <= 0) {
        clearInterval(cdTimer);
        cdTimer = null;
        sendCodeBtn.disabled = false;
        sendCodeBtn.textContent = "获取验证码";
      } else {
        sendCodeBtn.textContent = left + "s 后重发";
      }
    }, 1000);
  }

  async function onSendCode() {
    if (sendCodeBtn.disabled) return;
    const email = inputs.email.value.trim();
    if (!EMAIL_RE.test(email)) { showError("请输入正确的邮箱地址", "email"); return; }
    showError("");
    sendCodeBtn.disabled = true;
    sendCodeBtn.textContent = "发送中…";
    try {
      // scene：注册与重置密码的验证码在服务端分命名空间，互不串用
      const data = await post("send-code", { email, scene: mode === "reset" ? "reset" : "register" });
      startCountdown((data && data.resendAfterSeconds) || 60);
      inputs.code.focus();
    } catch (err) {
      sendCodeBtn.disabled = false;
      sendCodeBtn.textContent = "获取验证码";
      showError(err.message);
    }
  }

  async function onSubmit(e) {
    e.preventDefault();
    if (busy) return;
    const invalid = validate();
    if (invalid) { showError(invalid[0], invalid[1]); return; }

    showError("");
    setBusy(true);
    if (mode === "reset") {
      try {
        await post("reset-password", {
          email: inputs.email.value.trim(),
          code: inputs.code.value.trim(),
          newPassword: inputs.newPassword.value,
        });
      } catch (err) {
        setBusy(false);
        showError(err.message);
        return;
      }
      // 重置成功：回登录模式，用户名预填邮箱（支持邮箱登录），密码框等输入
      setBusy(false);
      history.replaceState(null, "", location.pathname + location.search + "#login");
      setMode("login");
      inputs.username.value = inputs.email.value.trim();
      inputs.password.value = "";
      showNotice("密码已重置，请用新密码登录");
      inputs.password.focus();
      return;
    }

    const username = inputs.username.value.trim();
    const password = inputs.password.value;
    const registering = mode === "register";
    try {
      if (registering) {
        const body = { username, password };
        if (mailVerify) {
          body.email = inputs.email.value.trim();
          body.code = inputs.code.value.trim();
        }
        await post("register", body);
      }
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
  sendCodeBtn.addEventListener("click", onSendCode);
  // 验证码只留数字（粘贴也会带上非数字字符）
  inputs.code.addEventListener("input", () => {
    inputs.code.value = inputs.code.value.replace(/\D/g, "").slice(0, 6);
  });
  form.addEventListener("input", () => { if ($("login-error").textContent) showError(""); });
  // 显示/隐藏密码（事件委托：按钮是静态的，但图标在切换时会重画）
  form.addEventListener("click", (e) => {
    const btn = e.target.closest(".login-eye");
    if (btn) setRevealed(btn, btn.getAttribute("aria-pressed") !== "true");
  });
  form.querySelectorAll(".login-eye").forEach((btn) => setRevealed(btn, false));
  // 用户名回车：密码还空着时只跳到密码框，不急着报错
  inputs.username.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !inputs.password.value) {
      e.preventDefault();
      inputs.password.focus();
    }
  });
  window.addEventListener("hashchange", () => {
    setMode(location.hash.slice(1));
    (mode === "reset" ? inputs.email : inputs.username).focus();
  });

  const reason = REASONS[params.get("reason")];
  if (reason) {
    noticePinned = true;
    showNotice(reason);
  }
  setMode(location.hash.slice(1));
  (mode === "reset" ? inputs.email : inputs.username).focus();
})();
