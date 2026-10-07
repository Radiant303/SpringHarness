"use strict";

/* ================= JSON-RPC over WebSocket ================= */

class RpcError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
}

class RpcClient {
  constructor() {
    this.ws = null;
    this.nextId = 1;
    this.pending = new Map();
    this.onNotification = null;   // (method, params) => void
    this.onServerRequest = null;  // (method, params) => Promise<result>
    this.onClose = null;
  }

  connect(url) {
    return new Promise((resolve, reject) => {
      let opened = false;
      const ws = new WebSocket(url);
      this.ws = ws;
      ws.onopen = () => { opened = true; resolve(); };
      ws.onerror = () => { if (!opened) reject(new Error("WebSocket 连接失败")); };
      ws.onclose = (e) => {
        this._failAll(new Error("连接已断开"));
        if (this.onClose) this.onClose(e && e.code);
      };
      ws.onmessage = (e) => this._onMessage(e.data);
    });
  }

  request(method, params) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this._send({ jsonrpc: "2.0", id, method, params: params || {} });
    });
  }

  respond(id, result) {
    this._send({ jsonrpc: "2.0", id, result: result ?? {} });
  }

  respondError(id, message) {
    this._send({ jsonrpc: "2.0", id, error: { code: -32603, message: String(message) } });
  }

  _send(obj) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      throw new Error("连接未就绪");
    }
    this.ws.send(JSON.stringify(obj));
  }

  _failAll(err) {
    for (const p of this.pending.values()) p.reject(err);
    this.pending.clear();
  }

  _onMessage(data) {
    let msg;
    try { msg = JSON.parse(data); } catch { return; }
    if (msg.method !== undefined) {
      if (msg.id !== undefined) {
        // 服务器 → 客户端请求（approval/question），必须应答
        Promise.resolve()
          .then(() => this.onServerRequest(msg.method, msg.params || {}))
          .then((result) => this.respond(msg.id, result))
          .catch((err) => this.respondError(msg.id, err && err.message || err));
      } else if (this.onNotification) {
        this.onNotification(msg.method, msg.params || {});
      }
    } else if (msg.id !== undefined) {
      const p = this.pending.get(msg.id);
      if (!p) return;
      this.pending.delete(msg.id);
      if (msg.error) p.reject(new RpcError(msg.error.code, msg.error.message));
      else p.resolve(msg.result);
    }
  }
}

/* ================= DOM 工具 ================= */

function $(id) { return document.getElementById(id); }

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function scrollToBottom() {
  const box = $("messages");
  box.scrollTop = box.scrollHeight;
}

/* 请求中指示：发送后到首个响应事件前显示，收到任意会话事件即移除 */
function showPending() {
  hidePending();
  const turn = ensureTurn();
  const node = el("div", "pending-indicator", "请求中…");
  node.id = "pending-indicator";
  turn.content.appendChild(node);
}

function hidePending() {
  const node = $("pending-indicator");
  if (node) node.remove();
}

/* 标记元素正在滚动：滚动条显示，停止 0.9s 后由定时器移除。
   用户滚动由全局 scroll 监听触发，程序化滚动（如思考区钉底）按需主动调用 */
function markScrolling(el) {
  el.classList.add("is-scrolling");
  clearTimeout(el._scrollbarTimer);
  el._scrollbarTimer = setTimeout(() => el.classList.remove("is-scrolling"), 900);
}

/* 「最新消息」按钮专用：easeOutCubic 缓动，0.5s 内滚到底。
   不用 behavior:"smooth"——其时长由浏览器按距离决定，长距离会超过 0.5s。
   动画期间用户滚轮/触摸可立即接管（取消动画） */
let smoothScrolling = false;
let smoothScrollCancel = null;

function smoothScrollToBottom() {
  const box = $("messages");
  const start = box.scrollTop;
  const delta = box.scrollHeight - box.clientHeight - start;
  if (delta <= 0) return;
  if (smoothScrollCancel) smoothScrollCancel();
  const DURATION = 500;
  const t0 = performance.now();
  smoothScrolling = true;
  const cancel = () => {
    smoothScrolling = false;
    smoothScrollCancel = null;
    box.removeEventListener("wheel", cancel);
    box.removeEventListener("touchstart", cancel);
    updateStick();
  };
  smoothScrollCancel = cancel;
  box.addEventListener("wheel", cancel);
  box.addEventListener("touchstart", cancel);
  function step(now) {
    if (!smoothScrolling) return;
    const p = Math.min((now - t0) / DURATION, 1);
    box.scrollTop = start + delta * (1 - Math.pow(1 - p, 3));
    if (p < 1) { requestAnimationFrame(step); return; }
    cancel();
  }
  requestAnimationFrame(step);
}

/* ================= Markdown ================= */

marked.setOptions({ breaks: true, gfm: true });

function renderMarkdown(text) {
  return DOMPurify.sanitize(marked.parse(text || ""));
}

function enhanceCodeBlocks(container) {
  for (const pre of container.querySelectorAll("pre")) {
    if (pre.parentElement.classList.contains("code-block")) continue;
    const wrap = document.createElement("div");
    wrap.className = "code-block";
    pre.parentNode.insertBefore(wrap, pre);
    wrap.appendChild(pre);
    wrap.appendChild(el("button", "code-copy", "复制"));
  }
}

function setMarkdown(node, text) {
  node.innerHTML = renderMarkdown(text);
  enhanceCodeBlocks(node);
}

let stickToBottom = true;
let hasNewBelow = false;  // 不在底部时下面又来了新内容：即使只离开一点也提示「最新消息」

function syncScrollBtn() {
  const box = $("messages");
  const dist = box.scrollHeight - box.scrollTop - box.clientHeight;
  const cardOpen = !$("plan-dock").classList.contains("hidden") && !$("plan-panel").classList.contains("hidden");
  // 出现时机：大幅上翻（>320px，在翻历史）才显示；只离开一点（选中文本等）不打扰，
  // 除非此时下面来了新内容；贴着底部跟随流式输出时永远不显示；
  // 计划卡展开时按钮被卡片完全盖住（层级：聊天区 < 按钮 < 计划卡），不露出来
  const show = !cardOpen && !stickToBottom && (dist > 320 || hasNewBelow);
  $("scroll-bottom").classList.toggle("hidden", !show);
}

function updateStick() {
  if (smoothScrolling) return;  // 平滑滚动动画途中不结算 stick 状态，动画结束时统一结算
  const box = $("messages");
  stickToBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
  if (stickToBottom) hasNewBelow = false;
  syncScrollBtn();
}

function maybeScroll(layoutOnly) {
  if (stickToBottom) { scrollToBottom(); return; }
  if (!layoutOnly) hasNewBelow = true;
  syncScrollBtn();
}

/* ================= 全局状态 ================= */

const rpc = new RpcClient();
const AUTO_SOURCES = new Set(["file_monitor", "background_wake"]);

const state = {
  workspace: null,
  models: [],
  model: null,
  sessionId: null,
  workId: localStorage.getItem("sh.workId") || null,
  works: [],
  connected: false,
  busy: false,
  assistant: null,      // 当前流式正文气泡 {el, answer, text}
  work: null,           // 当前「工作过程」分组（连续的思考 + 工具调用）
  turnGroups: [],       // 本轮已创建的分组：进行中平铺，本轮结束统一折叠
  thinking: null,       // 当前流式思考区 {el, body}
  active: null,         // 当前展开的那一项（思考区或工具卡片），渐进式收起用
  tools: new Map(),     // tool_call_id -> 卡片引用
  historyCursor: null,  // 继续向回翻页的 previousCursor
  historyHasMore: false,
  currentTurn: null,    // 当前助手回合容器 {el, content, petBox, canvas, pet}
  lastSeq: {},          // sessionId -> 最后收到的事件流条目 ID（断线续读游标，阶段⑤）
};

/* ================= 认证 ================= */

const TOKEN_KEY = "sh.token";
const USER_KEY = "sh.username";
const ROLE_KEY = "sh.role";
// 页面与聊天 WS 都走网关（8080）：WS 由网关鉴权后 relay 到 Python 引擎（阶段④）
const WS_BASE = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}`;

const ROLE_LABELS = { owner: "站长", admin: "管理员", user: "用户" };

function getToken() { return localStorage.getItem(TOKEN_KEY); }
function clearToken() { localStorage.removeItem(TOKEN_KEY); }
function getRole() { return localStorage.getItem(ROLE_KEY) || "user"; }

function showUserChip() {
  const name = localStorage.getItem(USER_KEY);
  if (name) {
    const el = $("user-name");
    /* 显示完整昵称；放不下时由 CSS 省略号截断，完整名留在悬浮提示 */
    el.textContent = name;
    el.title = name;
    const role = getRole();
    $("user-badge").textContent = ROLE_LABELS[role] || "用户";
    // 用户菜单：管理后台对站长/管理员开放，系统设置仅站长
    $("um-admin").classList.toggle("hidden", role !== "owner" && role !== "admin");
    $("um-settings").classList.toggle("hidden", role !== "owner");
    $("user-chip").classList.remove("hidden");
    $("points-card").classList.remove("hidden");
    refreshPoints();
  }
}

/* 积分余额：登录/打开用户菜单时从网关刷新（不缓存进 localStorage，避免展示过期值） */
async function refreshPoints() {
  const value = $("points-value");
  if (!value || !getToken()) return;
  // 首次加载失败时把骨架条换成占位符，避免骨架一直闪；已有数值则保持旧值
  const settle = () => { if (value.querySelector(".sk")) value.textContent = "积分 -"; };
  try {
    const r = await fetch("/api/billing/me", { headers: { Authorization: "Bearer " + getToken() } });
    if (!r.ok) { settle(); return; }
    const data = (await r.json()).data;
    const v = Number(data?.balance ?? 0);
    value.textContent = "积分 " + parseFloat(v.toFixed(6)).toLocaleString(undefined, { maximumFractionDigits: 6 });
    $("points-card").classList.toggle("negative", v < 0);
  } catch (e) { settle(); /* 网络抖动时保持旧值 */ }
}

function toggleUserMenu(open) {
  const menu = $("user-menu");
  const next = open ?? menu.classList.contains("hidden");
  menu.classList.toggle("hidden", !next);
  $("user-chip").classList.toggle("open", next);
  if (next) refreshPoints();
}

/* 登录/注册是独立页面 login.html。reason 让登录页说明为什么回到这里
   （expired = 登录过期，disabled = 账号被禁用）；登录成功后回到当前页 */
function goLogin(reason) {
  clearToken();
  const q = reason ? "?reason=" + encodeURIComponent(reason) : "";
  location.replace("/static/login.html" + q);
}

function bindAccountMenu() {
  $("logout-btn").onclick = () => {
    clearToken();
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem(ROLE_KEY);
    localStorage.removeItem("sh.sessionId");
    goLogin();
  };
  // 点击用户行弹出账号菜单（账号/账单/管理/退出），点菜单外关闭
  $("user-chip").onclick = (e) => {
    e.stopPropagation();
    toggleUserMenu();
  };
  document.addEventListener("click", (e) => {
    if (!e.target.closest("#user-menu") && !e.target.closest("#user-chip")) toggleUserMenu(false);
  });
}

/* ================= 骨架屏 ================= */

/* 记下 index.html 里的首屏骨架（脚本在 body 末尾执行，此时尚未被真实数据替换），
   切换项目/会话需要重新加载时由 UI.showSkeleton 克隆复用，样式只维护一份 */
UI.saveSkeleton("messages");
UI.saveSkeleton("session-list");

/* ================= 连接 / 会话引导 ================= */

let reconnectTimer = null;
let reconnectDelay = 1000;

function setConnected(ok) {
  state.connected = ok;
  const dot = $("conn-status");
  dot.className = "conn-dot " + (ok ? "connected" : "disconnected");
  dot.title = ok ? "已连接" : "未连接";
  $("conn-text").textContent = ok ? "已连接" : "未连接";
  updateInputState();
}

async function connectAndSetup() {
  await rpc.connect(`${WS_BASE}/ws?token=${encodeURIComponent(getToken())}`);
  const info = await rpc.request("initialize", {});
  state.workspace = info.workspace;
  state.models = info.models || [];
  if (!state.model) state.model = info.defaultModel || null;
  populateModelSelect();
  const wsName = state.workspace.replace(/[\\/]+$/, "").split(/[\\/]/).pop() || state.workspace;
  $("ws-name").textContent = localStorage.getItem(USER_KEY) || wsName;
  $("input-ws").title = state.workspace;
  setConnected(true);
  await loadWorks();   // 项目列表先可见；项目名未加载前托盘里显示骨架条
  await openSession(); // 可能触发默认 work 的自动创建
  await loadWorks();   // 刷新列表与项目名，让自动创建的默认 work 被选中
  reconnectDelay = 1000;
}

/** input-ws-name 显示当前选中项目的名称（workId 本身是不可读 UUID） */
function updateWorkName() {
  const work = state.works.find((w) => w.work_id === state.workId);
  $("input-ws-name").textContent = work ? work.name : "未选择项目";
}

rpc.onClose = (code) => {
  setConnected(false);
  state.busy = false;
  resetFlow();
  state.tools.clear();
  hideApproval();
  hideQuestion();
  if (code === 4401) {           // 未认证/令牌过期：去登录页，不重连
    goLogin("expired");
    return;
  }
  if (code === 4403) {           // 账号被禁用：去登录页并说明原因，不重连
    goLogin("disabled");
    return;
  }
  if (!reconnectTimer) {
    addSystem("连接已断开，正在重连…");
    scheduleReconnect();
  }
};

function scheduleReconnect() {
  reconnectTimer = setTimeout(async () => {
    reconnectTimer = null;
    try {
      await connectAndSetup();
    } catch {
      if (!getToken()) return;   // 4401/4403 已跳转登录页，停止重连
      reconnectDelay = Math.min(reconnectDelay * 2, 15000);
      scheduleReconnect();
    }
  }, reconnectDelay);
}

async function openSession() {
  let sid = localStorage.getItem("sh.sessionId");
  if (sid) {
    try {
      await rpc.request("session/attach", { workspace: state.workspace, sessionId: sid, model: state.model });
    } catch {
      sid = null;
    }
  }
  if (!sid) {
    const r = await rpc.request("session/resume_last", { workspace: state.workspace, model: state.model });
    sid = r.sessionId;
  }
  if (!sid) {
    const r = await rpc.request("session/new", { workspace: state.workspace, model: state.model, workId: state.workId });
    sid = r.sessionId;
  }
  state.sessionId = sid;
  localStorage.setItem("sh.sessionId", sid);
  clearMessages(true);
  await loadHistory();
  await loadPlan();
  await refreshSessionList();
  subscribeStream(sid);
}

/* 订阅会话事件流（阶段⑤）：带上本地已见的最后条目 ID，网关据此续读补发 */
function subscribeStream(sid) {
  rpc.request("stream/subscribe", { sessionId: sid, lastSeq: state.lastSeq[sid] || null })
    .catch(() => { /* 订阅失败只影响实时事件流，重连逻辑会再试 */ });
}

/* ================= 项目管理 ================= */

async function apiFetch(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  const token = getToken();
  if (token) headers["Authorization"] = "Bearer " + token;
  const r = await fetch(path, { ...options, headers });
  if (r.status === 401) {
    goLogin("expired");
    throw new Error("登录已过期");
  }
  return r;
}

function formatSize(bytes) {
  if (bytes >= 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + "MB";
  return Math.max(1, Math.round(bytes / 1024)) + "KB";
}

async function loadWorks() {
  let works;
  try {
    const r = await apiFetch("/api/works");
    if (!r.ok) throw new Error("HTTP " + r.status);
    const body = await r.json();
    works = body.data || [];
  } catch (e) {
    UI.clearSkeleton("works");
    updateWorkName();  // 让托盘里的项目名从骨架条落到“未选择项目”
    addSystem("❌ 项目列表加载失败：" + e.message, true);
    return;
  }
  state.works = works;
  // 选中项失效（被删/不存在）时回退到默认项目，再退到第一个
  const stored = state.workId;
  const found = works.find((w) => w.work_id === stored);
  if (!found) {
    const fallback = works.find((w) => w.default_work) || works[0] || null;
    state.workId = fallback ? fallback.work_id : null;
  }
  if (state.workId) localStorage.setItem("sh.workId", state.workId);
  renderWorks();
  updateWorkName();
}

const FOLDER_SVG = '<svg class="sb-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3.5 7a2 2 0 0 1 2-2h3.8l2 2.2h7.2a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/></svg>';

function renderWorks() {
  const box = $("works");
  box.textContent = "";
  for (const w of state.works) {
    const item = document.createElement("div");
    item.className = "work-item" + (w.work_id === state.workId ? " active" : "");
    item.title = w.name;
    item.insertAdjacentHTML("beforeend", FOLDER_SVG);

    const name = document.createElement("span");
    name.className = "work-name";
    name.textContent = w.name;
    item.appendChild(name);

    if (w.default_work) {
      const badge = document.createElement("span");
      badge.className = "work-badge";
      badge.textContent = "默认";
      item.appendChild(badge);
    }

    const size = document.createElement("span");
    size.className = "work-size";
    size.textContent = formatSize(w.size_bytes || 0);
    item.appendChild(size);

    const del = document.createElement("button");
    del.className = "work-del";
    del.title = "删除项目（连同目录与数据一起删除）";
    del.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M7 7l10 10M17 7L7 17"/></svg>';
    del.onclick = (e) => {
      e.stopPropagation();
      deleteWork(w);
    };
    item.appendChild(del);

    item.onclick = () => selectWork(w.work_id);
    box.appendChild(item);
  }
}

async function selectWork(workId) {
  if (workId === state.workId) return;
  if (state.busy) { addSystem("运行中，不能切换项目"); return; }
  state.workId = workId;
  localStorage.setItem("sh.workId", workId);
  renderWorks();
  updateWorkName();
  // 换项目后当前会话列表失效，清掉记忆重新落会话；加载期间对话与会话列表显示骨架
  state.sessionId = null;
  localStorage.removeItem("sh.sessionId");
  UI.showSkeleton("session-list");
  clearMessages(true);
  try {
    await openSession();
  } catch (e) {
    UI.clearSkeleton("session-list");
    UI.clearSkeleton("messages");
    addSystem("❌ 切换项目失败：" + e.message, true);
    return;
  }
  await refreshSessionList();
}

async function createWork() {
  let created = null;
  const name = await UI.prompt({
    title: "新建项目",
    message: "每个项目拥有独立的工作区目录和会话记录。",
    label: "项目名称",
    placeholder: "例如：my-app",
    okText: "创建",
    validate: (v) => (v.trim() ? null : "请输入项目名称"),
    // 提交在框内完成：失败时错误显示在对话框里，可直接修改重试
    submit: async (v) => {
      const r = await apiFetch("/api/works", {
        method: "POST",
        body: JSON.stringify({ name: v.trim() }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.message || `新建失败（${r.status}）`);
      created = body.data;
    },
  });
  if (name === null || !created) return;
  await loadWorks();
  await selectWork(created.work_id);
}

async function deleteWork(work) {
  const ok = await UI.confirm({
    title: "删除项目",
    message: `确定删除「${work.name}」吗？\n其工作区目录与全部会话数据会被物理删除，不可恢复。`,
    okText: "删除",
    danger: true,
    submit: async () => {
      const r = await apiFetch(`/api/works/${work.work_id}`, { method: "DELETE" });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.message || `删除失败（${r.status}）`);
    },
  });
  if (!ok) return;
  UI.toast(`项目「${work.name}」已删除`);
  await loadWorks();
  if (state.workId) {
    await openSession();
    await refreshSessionList();
  }
}

/* ================= 会话管理 ================= */

async function refreshSessionList() {
  let sessions;
  try {
    const r = await rpc.request("session/list", { workspace: state.workspace, workId: state.workId });
    sessions = r.sessions || [];
  } catch { UI.clearSkeleton("session-list"); return; }
  const list = $("session-list");
  list.textContent = "";
  const active = sessions.find((s) => s.sessionId === state.sessionId);
  $("session-title").textContent = active ? (active.title || "(空会话)") : "";
  /* 按最近更新倒序：新会话排在列表顶部 */
  const sorted = [...sessions].sort((a, b) => {
    const ta = Date.parse(a.updatedAt || a.createdAt || "") || 0;
    const tb = Date.parse(b.updatedAt || b.createdAt || "") || 0;
    return tb - ta;
  });
  for (const s of sorted) {
    const item = el("div", "session-item" + (s.sessionId === state.sessionId ? " active" : ""));
    item.appendChild(el("span", "session-title", s.title || "(空会话)"));
    item.appendChild(el("span", "session-time", formatTime(s.updatedAt || s.createdAt)));
    item.title = s.sessionId;
    item.onclick = () => switchSession(s.sessionId);
    list.appendChild(item);
  }
}

function formatTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return String(iso);
  const min = Math.floor((Date.now() - d.getTime()) / 60000);
  if (min < 1) return "刚刚";
  if (min < 60) return `${min}m`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h}h`;
  const day = Math.floor(h / 24);
  if (day < 30) return `${day}d`;
  return d.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" });
}

async function switchSession(sid) {
  if (sid === state.sessionId) return;
  if (state.busy) { addSystem("运行中，不能切换会话"); return; }
  try {
    await rpc.request("session/attach", { workspace: state.workspace, sessionId: sid, model: state.model });
  } catch (e) {
    addSystem("❌ 切换会话失败：" + e.message, true);
    return;
  }
  state.sessionId = sid;
  localStorage.setItem("sh.sessionId", sid);
  clearMessages(true);
  try {
    await loadHistory();
  } catch (e) {
    addSystem("❌ 加载历史失败：" + e.message, true);
  }
  await loadPlan();
  await refreshSessionList();
  subscribeStream(sid);
}

async function newSession() {
  if (state.busy) { addSystem("运行中，不能新建会话"); return; }
  try {
    const r = await rpc.request("session/new", { workspace: state.workspace, model: state.model, workId: state.workId });
    state.sessionId = r.sessionId;
    localStorage.setItem("sh.sessionId", r.sessionId);
    clearMessages();
    await refreshSessionList();
    subscribeStream(r.sessionId);
  } catch (e) {
    addSystem("❌ 新建会话失败：" + e.message, true);
  }
}

/* ================= 历史 ================= */

/** 清空消息区。loading=true 表示紧接着要拉历史：先放对话骨架占位，
    避免历史返回前被判定为空会话而闪出首页字标 */
function clearMessages(loading = false) {
  const box = $("messages");
  box.textContent = "";
  if (loading) UI.showSkeleton("messages");
  if (typeof SproutManager !== "undefined") {
    SproutManager.clear();
  }
  resetFlow();
  state.tools.clear();
  state.historyCursor = null;
  state.historyHasMore = false;
  $("plan-dock").classList.add("hidden");
}

function createAssistantTurnNode(isDynamic = false) {
  const wrap = el("div", "assistant-turn");
  const petBox = el("div", "turn-pet");
  const canvas = el("canvas", "sprout-pet");
  petBox.appendChild(canvas);
  const content = el("div", "turn-content");
  wrap.appendChild(petBox);
  wrap.appendChild(content);

  let pet = null;
  if (typeof SproutManager !== "undefined") {
    pet = SproutManager.register(canvas, isDynamic);
    wrap._sproutPet = pet;
  }

  return { el: wrap, content, petBox, canvas, pet };
}

function updateLatestPet() {
  if (typeof SproutManager === "undefined") return;
  const turnEls = document.querySelectorAll(".assistant-turn");
  SproutManager.makeAllStatic();
  if (turnEls.length > 0) {
    const last = turnEls[turnEls.length - 1];
    if (last._sproutPet) {
      SproutManager.setActive(last._sproutPet);
    }
  }
}

function ensureTurn() {
  if (state.currentTurn) return state.currentTurn;
  $("welcome") && $("welcome").remove();
  const turn = createAssistantTurnNode(true);
  $("messages").appendChild(turn.el);
  state.currentTurn = turn;
  updateLatestPet();
  return turn;
}

async function loadHistory(cursor) {
  const params = { sessionId: state.sessionId, limit: 30, direction: "backward" };
  if (cursor) params.cursor = cursor;
  let page;
  try {
    page = await rpc.request("session/history", params);
  } finally {
    // 首屏拉取：无论成功失败都撤掉骨架；与下面的渲染同步完成，空会话判定只看最终结果
    if (!cursor) UI.clearSkeleton("messages");
  }
  state.historyCursor = page.previousCursor || null;
  state.historyHasMore = !!page.hasMore;
  renderHistory(page.segments || [], !!cursor);
  updateLoadMore();
}

function updateLoadMore() {
  const old = document.querySelector(".load-more");
  if (old) old.remove();
  if (!state.historyHasMore) return;
  const btn = el("button", "load-more", "加载更早的消息");
  btn.onclick = async () => {
    btn.disabled = true;
    try { await loadHistory(state.historyCursor); }
    catch (e) { addSystem("❌ 加载历史失败：" + e.message, true); }
  };
  $("messages").prepend(btn);
}

function stringifyContent(content) {
  if (typeof content === "string") return content;
  try { return JSON.stringify(content, null, 2); } catch { return String(content); }
}

function renderHistory(segments, prepend) {
  const box = $("messages");
  const calls = new Map();
  const results = new Map();
  for (const seg of segments) {
    for (const msg of seg) {
      for (const part of msg.parts || []) {
        if (part.part_kind === "tool-call") calls.set(part.tool_call_id, part);
        else if ((part.part_kind === "tool-return" || part.part_kind === "retry-prompt") && part.tool_call_id) {
          results.set(part.tool_call_id, part);
        }
      }
    }
  }

  const frag = document.createDocumentFragment();
  let currentTurn = null;
  let group = null;

  const turnFor = () => {
    if (!currentTurn) {
      currentTurn = createAssistantTurnNode(false);
      frag.appendChild(currentTurn.el);
    }
    return currentTurn;
  };

  const endGroup = () => {
    if (group) { refreshWorkSummary(group); group = null; }
  };

  const groupFor = () => {
    if (!group) {
      group = workGroupNode();
      turnFor().content.appendChild(group.el);
    }
    return group;
  };

  const endTurn = () => {
    endGroup();
    currentTurn = null;
  };

  const appendAnswer = (node) => {
    endGroup();
    turnFor().content.appendChild(node);
  };

  const appendRoot = (node) => {
    endTurn();
    frag.appendChild(node);
  };

  const rendered = new Set();
  const renderTool = (part) => {
    const id = part.tool_call_id;
    if (!id || rendered.has(id)) return;
    rendered.add(id);
    const call = calls.get(id);
    const result = results.get(id);
    const card = historyToolCard(
      (call && call.tool_name) || part.tool_name || "tool",
      call ? stringifyContent(call.args) : "",
      result ? stringifyContent(result.content) : null,
      result ? result.part_kind === "retry-prompt" : false,
    );
    addToGroup(groupFor(), card);
  };

  segments.forEach((seg, i) => {
    if (i > 0) appendRoot(systemNode("── 上下文已压缩，以上内容已压缩为摘要 ──"));
    for (const msg of seg) {
      const source = msg.metadata && msg.metadata.source;
      if (msg.kind === "request") {
        for (const part of msg.parts || []) {
          if (part.part_kind === "user-prompt" && typeof part.content === "string") {
            if (source === "background_task") appendRoot(noticeNode(part.content));
            else if (!AUTO_SOURCES.has(source)) appendRoot(userNode(part.content));
          } else if (part.part_kind === "tool-return" || part.part_kind === "retry-prompt") {
            renderTool(part);
          }
        }
      } else if (msg.kind === "response") {
        let text = "";
        let thinking = "";
        const flushThinking = () => {
          if (thinking) addToGroup(groupFor(), thinkingNode(thinking));
          thinking = "";
        };
        const flushText = () => {
          if (text) appendAnswer(answerNode(text));
          text = "";
        };
        for (const part of msg.parts || []) {
          if (part.part_kind === "text") { flushThinking(); text += part.content || ""; }
          else if (part.part_kind === "thinking") { flushText(); thinking += part.content || ""; }
          else if (part.part_kind === "tool-call") {
            flushThinking();
            flushText();
            if (!results.has(part.tool_call_id)) renderTool(part);
          }
        }
        flushThinking();
        flushText();
      }
    }
  });
  endTurn();

  if (prepend) {
    const anchor = document.querySelector(".load-more");
    const oldHeight = box.scrollHeight;
    box.insertBefore(frag, anchor ? anchor.nextSibling : box.firstChild);
    box.scrollTop = box.scrollHeight - oldHeight;  // 保持视口位置
  } else {
    box.appendChild(frag);
    stickToBottom = true;
    scrollToBottom();
  }

  updateLatestPet();
}

/* ================= 消息节点 ================= */

function userNode(text) {
  return el("div", "msg user", text);
}

function noticeNode(text) {
  return el("div", "msg notice", text);
}

function systemNode(text, isError) {
  return el("div", "msg system" + (isError ? " error" : ""), text);
}

function answerNode(text) {
  const wrap = el("div", "msg assistant");
  const answer = el("div", "answer markdown-body");
  if (text) setMarkdown(answer, text);
  wrap.appendChild(answer);
  return wrap;
}

/* ================= 图标 ================= */

// 静态可信 SVG，stroke 跟随 currentColor
const ICONS = {
  bulb: '<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 0-3.6 10.8c.6.5 1 1.2 1 2V16h5.2v-.2c0-.8.4-1.5 1-2A6 6 0 0 0 12 3z"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16v4z"/><path d="M13.5 6.5l4 4"/>',
  file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/>',
  terminal: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9l3 3-3 3M13 15h4"/>',
  question: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14M12 17h.01"/>',
  book: '<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M4 19V5"/>',
  tool: '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L4 17l3 3 5.3-5.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.5-.5-.5-2.5z"/>',
  work: '<circle cx="12" cy="12" r="3"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4L7 17M17 7l1.4-1.4"/>',
  chevron: '<path d="M9 6l6 6-6 6"/>',
  check: '<circle cx="12" cy="12" r="10.875" stroke-width="2.25"/><path d="M7.125 12.6L10.65 16.125L17.025 8.85" stroke-width="2.25"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2.5"/><path d="M16 8V6.5A2.5 2.5 0 0 0 13.5 4h-7A2.5 2.5 0 0 0 4 6.5v7A2.5 2.5 0 0 0 6.5 16H8"/>',
  tick: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
};

function icon(name, className) {
  const span = el("span", "icon" + (className ? " " + className : ""));
  span.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ICONS[name] || ICONS.tool}</svg>`;
  return span;
}

/* ================= 工具摘要 ================= */

// kind 决定分组标题里怎么汇总：edit/read 按去重文件数，其余按次数
const TOOL_META = {
  edit_file: { icon: "edit", verb: "编辑", kind: "edit" },
  write_file: { icon: "edit", verb: "写入", kind: "edit" },
  edit_knowledge: { icon: "book", verb: "编辑知识", kind: "other" },
  create_directory: { icon: "folder", verb: "创建目录", kind: "other" },
  read_file: { icon: "file", verb: "读取", kind: "read" },
  file_info: { icon: "file", verb: "查看", kind: "read" },
  list_directory: { icon: "folder", verb: "列出", kind: "list" },
  search_files: { icon: "search", verb: "搜索", kind: "search" },
  find_files: { icon: "search", verb: "查找", kind: "search" },
  run_command: { icon: "terminal", verb: "运行", kind: "command" },
  start_command: { icon: "terminal", verb: "后台运行", kind: "command" },
  check_command: { icon: "terminal", verb: "查看命令", kind: "other" },
  stop_command: { icon: "terminal", verb: "停止命令", kind: "other" },
  read_knowledge: { icon: "book", verb: "查阅知识", kind: "other" },
  read_index_knowledge: { icon: "book", verb: "查阅知识索引", kind: "other" },
  ask_user: { icon: "question", verb: "提问", kind: "other" },
};

const TARGET_KEYS = ["path", "command", "pattern", "question", "command_id", "type"];

function toolMeta(name) {
  return TOOL_META[name] || { icon: "tool", verb: name, kind: "other" };
}

function parseArgs(text) {
  if (!text) return null;
  try {
    const v = JSON.parse(text);
    return v && typeof v === "object" ? v : null;
  } catch { return null; }
}

function relPath(p) {
  // 统一成正斜杠再比较，Windows 下 / 与 \ 混用也能截成相对路径
  const norm = (s) => s.replace(/\\/g, "/");
  const path = norm(p);
  const ws = state.workspace ? norm(state.workspace).replace(/\/+$/, "") : "";
  if (ws && path.toLowerCase().startsWith(ws.toLowerCase() + "/")) {
    const rest = path.slice(ws.length + 1).replace(/^\/+/, "");
    if (rest) return rest;
  }
  return path;
}

function targetFromArgs(args) {
  if (!args) return "";
  for (const k of TARGET_KEYS) {
    if (args[k] !== undefined && args[k] !== null && args[k] !== "") {
      const v = String(args[k]);
      return k === "path" ? relPath(v) : v.split("\n")[0];
    }
  }
  return "";
}

// 参数还在流式拼接时 JSON 不完整：用正则先抠出目标字段
function targetFromPartial(text) {
  const m = /"(path|command|pattern|question|command_id)"\s*:\s*"((?:[^"\\]|\\.)*)"/.exec(text);
  if (!m) return "";
  let v;
  try { v = JSON.parse(`"${m[2]}"`); } catch { v = m[2]; }
  return m[1] === "path" ? relPath(v) : v.split("\n")[0];
}

function diffStats(diff) {
  let add = 0, del = 0;
  for (const line of String(diff).split("\n")) {
    if (line.startsWith("+") && !line.startsWith("+++")) add++;
    else if (line.startsWith("-") && !line.startsWith("---")) del++;
  }
  return { add, del };
}

// 历史里没有 diff 事件，按参数近似算增删行数（去掉首尾公共行）
function statsFromArgs(name, args) {
  if (!args) return null;
  if (name === "write_file" && typeof args.content === "string") {
    return { add: args.content.replace(/\n$/, "").split("\n").length, del: 0 };
  }
  if (name === "edit_file" && typeof args.old_text === "string" && typeof args.new_text === "string") {
    const a = args.old_text.split("\n");
    const b = args.new_text.split("\n");
    let p = 0;
    while (p < a.length && p < b.length && a[p] === b[p]) p++;
    let s = 0;
    while (s < a.length - p && s < b.length - p && a[a.length - 1 - s] === b[b.length - 1 - s]) s++;
    return { add: b.length - p - s, del: a.length - p - s };
  }
  if (name === "edit_knowledge" && typeof args.diff === "string") return diffStats(args.diff);
  return null;
}

function splitPath(path) {
  const slash = path.lastIndexOf("/");
  return slash >= 0 ? { dir: path.slice(0, slash), name: path.slice(slash + 1) } : { dir: "", name: path };
}

function isFileTool(name) {
  const kind = toolMeta(name).kind;
  return kind === "read" || kind === "edit";
}

// 文件类工具：「文件名 目录 N 行」，文件名深色、其余浅色；其他工具照旧显示整段目标
function renderTarget(card) {
  const t = card.targetEl;
  t.textContent = "";
  t.title = card.target;
  if (!isFileTool(card.name) || !card.target) { t.textContent = card.target; return; }
  t.classList.add("file");
  const { dir, name } = splitPath(card.target);
  t.appendChild(el("span", "tt-name", name));
  if (dir) t.appendChild(el("span", "tt-meta", dir));
  if (card.lineCount) t.appendChild(el("span", "tt-meta", `${card.lineCount} 行`));
}

function setToolTarget(card, target) {
  card.target = target;
  renderTarget(card);
}

// 只显示非零的一侧：+1 或 +7 −1
function setToolStats(card, stats) {
  card.statsEl.textContent = "";
  if (!stats) return;
  if (stats.add) card.statsEl.appendChild(el("span", "stat-add", `+${stats.add}`));
  if (stats.del) card.statsEl.appendChild(el("span", "stat-del", `−${stats.del}`));
}

function setToolStatus(card, status) {
  card.error = status === "error";
  card.status.className = "tool-status " + status;
  card.status.textContent = status === "error" ? "失败" : "";
  card.el.classList.toggle("error", card.error);
}

/* ================= 思考区 / 工作分组 ================= */

function thinkingNode(text) {
  const wrap = el("div", "thinking");
  const header = el("div", "thinking-header");
  header.appendChild(icon("bulb", "thinking-icon"));
  header.appendChild(el("span", "thinking-title", "思考过程"));
  header.appendChild(icon("chevron", "caret"));
  const body = el("div", "thinking-body", text);
  header.onclick = () => wrap.classList.toggle("expanded");
  wrap.appendChild(header);
  wrap.appendChild(body);
  return wrap;
}

function workGroupNode() {
  const wrap = el("div", "work-group");
  const header = el("div", "work-header");
  header.appendChild(icon("work", "work-icon"));
  const summary = el("span", "work-summary", "工作过程");
  header.appendChild(summary);
  header.appendChild(icon("chevron", "caret"));
  const body = el("div", "work-body");
  header.onclick = () => wrap.classList.toggle("expanded");
  wrap.appendChild(header);
  wrap.appendChild(body);
  return { el: wrap, body, summary, items: [] };
}

// item：思考区元素，或 buildToolCard 返回的卡片对象
function addToGroup(group, item) {
  group.items.push(item);
  if (!(item instanceof Element)) item.group = group;
  group.body.appendChild(item instanceof Element ? item : item.el);
  refreshWorkSummary(group);
}

function refreshWorkSummary(group) {
  const files = { edit: new Set(), read: new Set() };
  const counts = { list: 0, search: 0, command: 0, other: 0 };
  let errors = 0;
  let thoughts = 0;
  for (const item of group.items) {
    if (item instanceof Element) { thoughts++; continue; }
    const kind = toolMeta(item.name).kind;
    if (item.error) errors++;
    if (files[kind]) files[kind].add(item.target || item.id);
    else counts[kind]++;
  }
  const parts = [];
  if (files.edit.size) parts.push(`编辑 ${files.edit.size} 个文件`);
  if (files.read.size) parts.push(`读取 ${files.read.size} 个文件`);
  if (counts.list) parts.push(`查看 ${counts.list} 个目录`);
  if (counts.search) parts.push(`搜索 ${counts.search} 次`);
  if (counts.command) parts.push(`运行 ${counts.command} 条命令`);
  if (counts.other) parts.push(`调用 ${counts.other} 个工具`);
  let text = parts.join("、") || (thoughts ? "思考过程" : "工作过程");
  if (errors) text += `，${errors} 项失败`;
  group.summary.textContent = text;
  group.el.classList.toggle("has-error", errors > 0);
}

function colorizeDiff(pre, diff) {
  pre.textContent = "";
  for (const line of String(diff).split("\n")) {
    const span = el("span", null, line + "\n");
    if (line.startsWith("+") && !line.startsWith("+++")) span.className = "diff-add";
    else if (line.startsWith("-") && !line.startsWith("---")) span.className = "diff-del";
    pre.appendChild(span);
  }
}

/* ================= 文件视图（读/写/编辑） ================= */

const FILE_VIEW_MAX_ROWS = 400;

// 统一 diff → 行：{type: add|del|ctx|gap, no, text}；行号取自 @@ 头
function parseUnifiedDiff(diff) {
  const rows = [];
  let oldNo = 1, newNo = 1;
  for (const line of String(diff).split("\n")) {
    if (line === "" || line.startsWith("---") || line.startsWith("+++") || line.startsWith("\\")) continue;
    const hunk = /^@@ -(\d+)(?:,\d+)? \+(\d+)/.exec(line);
    if (hunk) {
      oldNo = +hunk[1] || 1;
      newNo = +hunk[2] || 1;
      if (rows.length) rows.push({ type: "gap" });
      continue;
    }
    const text = line.slice(1);
    if (line[0] === "+") rows.push({ type: "add", no: newNo++, text });
    else if (line[0] === "-") rows.push({ type: "del", no: oldNo++, text });
    else { rows.push({ type: "ctx", no: newNo++, text }); oldNo++; }
  }
  return rows;
}

// 历史里没有 tool_diff 事件：按 old_text/new_text 做一次 LCS 行级 diff
function lineDiff(oldText, newText) {
  const a = oldText.split(/\r?\n/);
  const b = newText.split(/\r?\n/);
  if (a.length * b.length > 250000) {  // 片段过大时不做 LCS，直接整段删 + 整段增
    return [
      ...a.map((text, i) => ({ type: "del", no: i + 1, text })),
      ...b.map((text, i) => ({ type: "add", no: i + 1, text })),
    ];
  }
  const dp = Array.from({ length: a.length + 1 }, () => new Uint16Array(b.length + 1));
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const rows = [];
  let i = 0, j = 0;
  while (i < a.length || j < b.length) {
    if (i < a.length && j < b.length && a[i] === b[j]) { rows.push({ type: "ctx", no: j + 1, text: b[j] }); i++; j++; }
    // 同一位置的替换先删后增，与统一 diff 的阅读顺序一致
    else if (i < a.length && (j >= b.length || dp[i + 1][j] >= dp[i][j + 1])) { rows.push({ type: "del", no: i + 1, text: a[i] }); i++; }
    else { rows.push({ type: "add", no: j + 1, text: b[j] }); j++; }
  }
  return rows;
}

// read_file 结果：首行元信息头 + 「行号\t内容」，末尾可能带续读提示
function parseReadResult(text) {
  const rows = [];
  let note = "";
  // CRLF 文件读出来每行末尾带 \r，按 \r?\n 切分
  for (const line of String(text).split(/\r?\n/)) {
    const m = /^\s*(\d+)\t(.*)$/.exec(line);
    if (m) rows.push({ type: "ctx", no: +m[1], text: m[2] });
    else if (/^\.\.\. \((\d+) more lines/.test(line)) note = `还有 ${/\d+/.exec(line)[0]} 行未读取`;
    else if (line === "(empty file)") note = "空文件";
  }
  return { rows, note };
}

function fileRowsFromArgs(name, args) {
  if (!args) return null;
  if (name === "edit_file" && typeof args.old_text === "string" && typeof args.new_text === "string") {
    return lineDiff(args.old_text, args.new_text);
  }
  if (name === "write_file" && typeof args.content === "string") {
    return args.content.replace(/\n$/, "").split("\n").map((text, i) => ({ type: "add", no: i + 1, text }));
  }
  if (name === "edit_knowledge" && typeof args.diff === "string") return parseUnifiedDiff(args.diff);
  return null;
}

/* ---- 轻量语法高亮：只做注释 / 字符串 / 关键字 / 数字 / 标签 / 属性几类，逐行着色 ---- */

const HL_KEYWORDS = new Set((
  "const let var function return if else for while do switch case break continue new class extends " +
  "import from export default async await try catch finally throw typeof instanceof in of this null " +
  "undefined true false def self None True False elif lambda pass with as yield raise and or not is " +
  "public private protected static void int long boolean package interface implements"
).split(" "));

function hlLang(path) {
  const ext = (/\.([a-z0-9]+)$/i.exec(path || "") || [])[1];
  if (!ext) return "plain";
  const e = ext.toLowerCase();
  if (["html", "htm", "xml", "svg", "vue"].includes(e)) return "markup";
  if (["css", "scss", "less"].includes(e)) return "css";
  if (["py", "toml", "yaml", "yml", "sh", "ini"].includes(e)) return "hash";   // # 注释
  if (["js", "ts", "jsx", "tsx", "mjs", "java", "go", "rs", "c", "cpp", "h", "kt", "json"].includes(e)) return "c";
  return "plain";
}

const HL_RULES = {
  c: /(\/\/.*$|\/\*.*?\*\/)|("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|`(?:[^`\\]|\\.)*`)|\b(\d+(?:\.\d+)?)\b|\b([A-Za-z_$][\w$]*)\b/g,
  hash: /(#.*$)|("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')|\b(\d+(?:\.\d+)?)\b|\b([A-Za-z_][\w]*)\b/g,
  css: /(\/\*.*?\*\/)|("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')|(-?\d+(?:\.\d+)?(?:px|em|rem|%|s|ms|vh|vw|deg)?)\b|([#.][\w-]+(?=[^;{}]*\{))/g,
  markup: /(<!--.*?-->)|("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')|(<\/?[\w-]+|\/?>|<!DOCTYPE)|(\s[\w-]+(?==))/gi,
};

// 返回 DocumentFragment：纯文本节点 + 带类名的 span，全程 textContent，不拼 HTML
function highlightLine(text, lang) {
  const frag = document.createDocumentFragment();
  const re = HL_RULES[lang];
  if (!re) { frag.appendChild(document.createTextNode(text)); return frag; }
  re.lastIndex = 0;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m[0] === "") { re.lastIndex++; continue; }
    let cls = null;
    if (m[1]) cls = "hl-comment";
    else if (m[2]) cls = "hl-string";
    else if (m[3]) cls = lang === "markup" ? "hl-tag" : "hl-number";
    else if (m[4]) {
      if (lang === "markup") cls = "hl-attr";
      else if (lang === "css") cls = "hl-selector";
      else if (HL_KEYWORDS.has(m[4])) cls = "hl-keyword";
    }
    if (!cls) continue;
    if (m.index > last) frag.appendChild(document.createTextNode(text.slice(last, m.index)));
    frag.appendChild(el("span", cls, m[0]));
    last = m.index + m[0].length;
  }
  if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
  return frag;
}

// 代码卡片：头部文件名 + 复制按钮；读取显示行号，编辑/写入只显示 +/− 标记列
function renderFileView(card, rows, note) {
  const view = card.fileView;
  view.textContent = "";
  const mode = card.name === "read_file" ? "read" : "diff";
  view.className = "file-view mode-" + mode;

  const head = el("div", "fv-head");
  const { dir, name } = splitPath(card.target || "");
  if (mode === "diff" && dir) head.appendChild(el("span", "fv-dir", dir + "/"));
  head.appendChild(el("span", "fv-name", name));
  if (mode === "diff") {
    const stats = card.statsEl.cloneNode(true);
    stats.className = "tool-stats fv-stats";
    head.appendChild(stats);
  }
  head.appendChild(el("span", "spacer"));
  const copy = el("button", "fv-copy");
  copy.type = "button";
  copy.title = "复制";
  copy.setAttribute("aria-label", "复制代码");
  copy.appendChild(icon("copy"));
  const shown = rows.slice(0, FILE_VIEW_MAX_ROWS);
  copy.onclick = (e) => {
    e.stopPropagation();
    // 编辑视图复制修改后的内容（跳过删除行），读取视图复制原文
    const text = shown.filter((r) => r.type !== "del" && r.type !== "gap").map((r) => r.text).join("\n");
    navigator.clipboard.writeText(text).then(() => {
      copy.textContent = "";
      copy.appendChild(icon("tick"));
      setTimeout(() => { copy.textContent = ""; copy.appendChild(icon("copy")); }, 1200);
    });
  };
  head.appendChild(copy);
  view.appendChild(head);

  const lang = hlLang(card.target);
  const body = el("div", "fv-body");
  const lines = el("div", "fv-lines");
  for (const row of shown) {
    const r = el("div", "fv-row " + row.type);
    if (mode === "read") r.appendChild(el("span", "fv-no", row.type === "gap" ? "⋯" : String(row.no)));
    else r.appendChild(el("span", "fv-sign", row.type === "add" ? "+" : row.type === "del" ? "−" : row.type === "gap" ? "⋯" : ""));
    const textEl = el("span", "fv-text");
    if (row.type !== "gap") textEl.appendChild(highlightLine(row.text || " ", lang));
    r.appendChild(textEl);
    lines.appendChild(r);
  }
  body.appendChild(lines);
  view.appendChild(body);
  const more = rows.length > FILE_VIEW_MAX_ROWS ? `还有 ${rows.length - FILE_VIEW_MAX_ROWS} 行未显示` : "";
  if (note || more) view.appendChild(el("div", "fv-note", note || more));
  card.el.classList.add("has-file");
}

// read_file 的结果头里带总行数：写回卡片，单行摘要显示「N 行」
function applyReadMeta(card, resultText) {
  const m = /^\[[^\]|]*\|\s*(\d+) lines/.exec(String(resultText || ""));
  if (m) { card.lineCount = +m[1]; renderTarget(card); }
}

function historyToolCard(name, argsText, resultText, isError) {
  const card = buildToolCard(name);
  card.args.textContent = argsText || "";
  const args = parseArgs(argsText);
  setToolTarget(card, targetFromArgs(args));
  setToolStats(card, statsFromArgs(name, args));
  const rows = fileRowsFromArgs(name, args);
  if (rows) renderFileView(card, rows);
  else if (name === "read_file" && resultText && !isError) {
    applyReadMeta(card, resultText);
    const read = parseReadResult(resultText);
    if (read.rows.length || read.note) renderFileView(card, read.rows, read.note);
  }
  if (resultText !== null && resultText !== undefined) {
    card.result.textContent = resultText;
    card.result.classList.remove("hidden");
    card.result.classList.toggle("error", !!isError);
    setToolStatus(card, isError ? "error" : "done");
  } else {
    card.result.remove();
    setToolStatus(card, "done");
  }
  return card;
}

function buildToolCard(name, id) {
  const meta = toolMeta(name);
  const card = el("div", "tool-card");
  const header = el("div", "tool-header");
  const pending = el("span", "tool-pending-label hidden", "等待批准");
  const verb = el("span", "tool-verb", meta.verb);
  verb.title = name;
  const targetEl = el("span", "tool-target");
  const statsEl = el("span", "tool-stats");
  const status = el("span", "tool-status running");
  header.appendChild(icon(meta.icon, "tool-icon"));
  header.appendChild(verb);
  header.appendChild(targetEl);
  header.appendChild(statsEl);
  header.appendChild(pending);
  header.appendChild(status);
  header.appendChild(icon("chevron", "caret"));
  const body = el("div", "tool-body");
  const args = el("pre", "tool-args");
  const diff = el("pre", "tool-diff diff hidden");
  const result = el("pre", "tool-result hidden");
  const fileView = el("div", "file-view hidden");
  body.appendChild(fileView);
  body.appendChild(args);
  body.appendChild(diff);
  body.appendChild(result);
  card.appendChild(header);
  card.appendChild(body);
  header.onclick = () => card.classList.toggle("expanded");
  return {
    el: card, id, name, target: "", error: false,
    status, args, diff, result, pending, body, targetEl, statsEl, fileView,
  };
}

/* ================= 实时事件 ================= */

function resetFlow() {
  foldTurnGroups();
  state.assistant = null;
  state.work = null;
  state.thinking = null;
  state.active = null;
  state.currentTurn = null;
}

// 本轮结束：进行中平铺展示的工作分组统一收成一行摘要
function foldTurnGroups() {
  for (const group of state.turnGroups) {
    refreshWorkSummary(group);
    group.el.classList.remove("live", "expanded");
  }
  state.turnGroups = [];
}

// 渐进式收起：新元素开始时收起上一个展开项，页面上只保留进行中的那一项展开。
// 出错信号不靠展开保留：卡片行尾的「失败」标记和分组标题里的失败计数始终可见
function setActive(node) {
  const prev = state.active;
  if (prev && prev !== node) prev.classList.remove("expanded");
  state.active = node;
  if (node) node.classList.add("expanded");
}

// 工作过程收口（正文开始、系统消息插入）：后续思考/工具另起一组。
// 本轮进行中分组保持平铺（live），等 turn_finished 再统一折叠
function closeWork() {
  if (state.work) refreshWorkSummary(state.work);
  state.work = null;
  state.thinking = null;
}

function ensureWork() {
  if (state.work) return state.work;
  $("welcome") && $("welcome").remove();
  state.assistant = null;  // 正文被工作过程打断，后续正文另起气泡
  const group = workGroupNode();
  group.el.classList.add("expanded", "live");
  const turn = ensureTurn();
  turn.content.appendChild(group.el);
  state.work = group;
  state.turnGroups.push(group);
  return group;
}

function ensureAssistant() {
  if (state.assistant) return state.assistant;
  $("welcome") && $("welcome").remove();
  closeWork();
  const wrap = answerNode("");
  const turn = ensureTurn();
  turn.content.appendChild(wrap);
  state.assistant = { el: wrap, answer: wrap.querySelector(".answer"), text: "" };
  return state.assistant;
}

/* Stream 条目 ID 形如 "毫秒-序号"，按 (毫秒, 序号) 比较先后（阶段⑤去重） */
function seqAfter(a, b) {
  const [am, as] = a.split("-").map(Number);
  const [bm, bs] = b.split("-").map(Number);
  return am > bm || (am === bm && as > bs);
}

function onSessionEvent(sid, event, seq) {
  if (sid !== state.sessionId) return;
  if (seq) {
    const last = state.lastSeq[sid];
    if (last && !seqAfter(seq, last)) return;  // 续读补发的重叠部分，去重
    state.lastSeq[sid] = seq;
  }
  hidePending();  // 任意事件到达都视为响应已开始
  switch (event.kind) {
    case "text_delta": {
      const a = ensureAssistant();
      if (!a.text) setActive(null);  // 正文开始：收起上一个思考区/工具卡片
      a.text += event.text;
      setMarkdown(a.answer, a.text);
      maybeScroll();
      break;
    }
    case "thinking_delta": {
      const group = ensureWork();
      if (!state.thinking) {
        state.thinking = thinkingNode("");
        addToGroup(group, state.thinking);
        setActive(state.thinking);  // 新的思考开始：收起上一项
      }
      const body = state.thinking.querySelector(".thinking-body");
      /* 钉底滚动：追加前贴底才跟随（容忍 40px 取整误差），
         用户上翻即松手，滚回底部后下一片段自动恢复跟随 */
      const atBottom = body.scrollHeight - body.scrollTop - body.clientHeight < 40;
      body.textContent += event.text;
      if (atBottom) {
        body.scrollTop = body.scrollHeight;
        markScrolling(body);  // 流式期间让滚动条可见，提示下面还有内容
      }
      maybeScroll();
      break;
    }
    case "tool_started": {
      const group = ensureWork();
      state.thinking = null;  // 工具打断思考，后续思考另起一段
      const card = buildToolCard(event.tool_name, event.tool_call_id);
      state.tools.set(event.tool_call_id, card);
      addToGroup(group, card);
      setActive(card.el);  // 新工具开始：收起上一项
      maybeScroll();
      break;
    }
    case "tool_args_delta": {
      const card = state.tools.get(event.tool_call_id);
      if (card) {
        card.args.textContent += event.args_chunk;
        const args = parseArgs(card.args.textContent);
        const target = args ? targetFromArgs(args) : targetFromPartial(card.args.textContent);
        if (target && target !== card.target) {
          setToolTarget(card, target);
          if (state.work) refreshWorkSummary(state.work);
        }
        if (args && !card.hasDiff) {
          setToolStats(card, statsFromArgs(card.name, args));
          // 参数完整后立刻渲染代码卡片（edit/write 不必等 tool_diff 或结果）
          const rows = fileRowsFromArgs(card.name, args);
          if (rows) renderFileView(card, rows);
        }
        maybeScroll();
      }
      break;
    }
    case "tool_diff": {
      const card = state.tools.get(event.tool_call_id);
      if (card) {
        card.hasDiff = true;
        card.diff.classList.remove("hidden");
        colorizeDiff(card.diff, event.diff);
        setToolStats(card, diffStats(event.diff));
        const rows = parseUnifiedDiff(event.diff);
        if (rows.length) renderFileView(card, rows);
      }
      break;
    }
    case "tool_pending": {
      const card = state.tools.get(event.tool_call_id);
      if (card) { card.pending.textContent = event.label || "等待批准"; card.pending.classList.remove("hidden"); }
      break;
    }
    case "tool_finished": {
      const card = state.tools.get(event.tool_call_id);
      if (card) {
        card.pending.classList.add("hidden");
        setToolStatus(card, event.is_error ? "error" : "done");
        card.result.textContent = event.result;
        card.result.classList.remove("hidden");
        card.result.classList.toggle("error", !!event.is_error);
        if (card.name === "read_file" && !event.is_error) {
          applyReadMeta(card, event.result);
          const read = parseReadResult(event.result);
          if (read.rows.length || read.note) renderFileView(card, read.rows, read.note);
        }
        if (card.group) refreshWorkSummary(card.group);
        maybeScroll();
      }
      break;
    }
    case "usage": {
      updateUsage(event.context_tokens);
      break;
    }
    case "plan_updated": {
      renderPlan(event.items);
      break;
    }
    case "teaching_updated": {
      const unit = event.unit || {};
      addSystem(`📘 教学单元更新：${unit.title || unit.slug || ""}（${unit.status || ""}）`);
      break;
    }
    case "compaction": {
      addSystem(`上下文已压缩：折叠 ${event.dropped} 条旧消息（约 ${Math.round(event.before / 1000)}k → ${Math.round(event.after / 1000)}k tokens）`);
      break;
    }
    case "background_notification": {
      closeWork();             // 插入独立节点后，后续文本/工具另起气泡和分组
      state.assistant = null;
      $("messages").appendChild(noticeNode(event.text));
      maybeScroll();
      break;
    }
    case "background_task_started": {
      addSystem(`⚙ 后台任务 ${event.task_id} 已开始（${event.tool_name}），完成后会自动汇报`);
      break;
    }
    case "background_task_finished": {
      if (event.cancelled) addSystem(`⚙ 后台任务 ${event.task_id}（${event.tool_name}）已取消`);
      else if (event.is_error) addSystem(`⚙ 后台任务 ${event.task_id}（${event.tool_name}）出错，详情见后续汇报`, true);
      break;
    }
    case "turn_finished": {
      finishTurn(event);
      break;
    }
  }
}

function finishTurn(event) {
  const groups = new Set();
  for (const card of state.tools.values()) {
    card.pending.classList.add("hidden");
    if (card.status.classList.contains("running")) {
      // deferred 工具（ask_user 等）不走 tool_finished，收尾时补 done
      setToolStatus(card, "done");
    }
    if (card.group) groups.add(card.group);
  }
  groups.forEach(refreshWorkSummary);
  setActive(null);
  closeWork();
  foldTurnGroups();
  state.assistant = null;
  state.tools.clear();
  if (state.currentTurn && state.currentTurn.content.children.length === 0) {
    if (typeof SproutManager !== "undefined" && state.currentTurn.pet) {
      SproutManager.unregister(state.currentTurn.pet);
    }
    state.currentTurn.el.remove();
  }
  state.currentTurn = null;
  updateLatestPet();
  if (event.cancelled && !event.wake) addSystem("已中断，可继续输入");
  else if (event.error) addSystem("❌ 运行出错：" + event.error, true);
  if (!event.wake) {   // 催醒轮是系统轮次，不占输入锁
    state.busy = false;
    updateInputState();
  }
  // 结算经 MQ lifecycle 事件落库，比浏览器收到 turn_finished 略晚；稍 delay 再刷余额
  setTimeout(refreshPoints, 1500);
  refreshSessionList();  // 标题/时间可能更新了
}

// 计划持久化在服务端：刷新页面或切换会话后主动拉一次，面板常驻不依赖实时事件
async function loadPlan() {
  const sid = state.sessionId;
  try {
    const r = await rpc.request("session/plan", { sessionId: sid });
    if (sid === state.sessionId) renderPlan(r.items);
  } catch { /* 旧版服务端没有该方法：退化为只靠 plan_updated 事件 */ }
}

function renderPlan(items) {
  const dock = $("plan-dock");
  const panel = $("plan-panel");
  const list = $("plan-items");
  if (!items || !items.length) { dock.classList.add("hidden"); return; }
  dock.classList.remove("hidden");
  list.textContent = "";
  let done = 0;
  for (const item of items) {
    const status = item.status || "pending";
    if (status === "completed") done++;
    const li = el("li", status);
    li.appendChild(status === "completed" ? icon("check", "plan-mark") : el("span", "plan-mark"));
    const text = status === "in_progress" && item.active_form ? item.active_form : item.content || "";
    li.appendChild(el("span", "plan-text", text));
    list.appendChild(li);
  }
  const label = `${done}/${items.length}`;
  $("plan-progress").textContent = label;
  $("plan-pill-count").textContent = label;
  $("plan-pill").setAttribute("aria-label", `当前进度 ${label}`);
  panel.classList.toggle("all-done", done === items.length);
}

function addSystem(text, isError) {
  closeWork();
  state.assistant = null;
  $("messages").appendChild(systemNode(text, isError));
  maybeScroll();
}

const USAGE_RING_LEN = 56.5;  /* 圆环周长 2πr，r=9，与 CSS 中 stroke-dasharray 一致 */

function updateUsage(tokens) {
  const model = state.models.find((m) => m.id === state.model);
  const max = model ? model.maxContextSize : 0;
  const prog = $("usage-ring-prog");
  if (!max) {
    prog.style.strokeDashoffset = String(USAGE_RING_LEN);
    $("usage-tip").textContent = `已使用 ${(tokens / 1000).toFixed(1)}k tokens`;
    return;
  }
  const pct = Math.min(tokens / max, 1);
  prog.style.strokeDashoffset = String(USAGE_RING_LEN * (1 - pct));
  $("usage-tip").textContent = `使用 ${(tokens / 1000).toFixed(1)}k / ${Math.round(max / 1000)}k tokens (${Math.round(pct * 100)}%)`;
}

/* ================= 服务器反向请求：审批 / 提问 ================= */

let approvalResolve = null;
let questionResolve = null;
let approvalQueue = Promise.resolve();
let questionQueue = Promise.resolve();

function handleApprovalRequest(params) {
  // 串行排队，避免多个审批弹窗叠在一起
  const task = approvalQueue.then(() => new Promise((resolve) => {
    approvalResolve = resolve;
    $("approval-tool").textContent = params.toolName || "";
    $("approval-args").textContent = JSON.stringify(params.args ?? {}, null, 2);
    const diffEl = $("approval-diff");
    if (params.diff) {
      diffEl.classList.remove("hidden");
      colorizeDiff(diffEl, params.diff);
    } else {
      diffEl.classList.add("hidden");
      diffEl.textContent = "";
    }
    $("approval-modal").classList.remove("hidden");
  }));
  approvalQueue = task.catch(() => {});
  return task.then((approved) => ({ approved }));
}

function settleApproval(approved) {
  $("approval-modal").classList.add("hidden");
  const resolve = approvalResolve;
  approvalResolve = null;
  if (resolve) resolve(approved);
}

function hideApproval() { if (approvalResolve) settleApproval(false); }

function handleQuestionRequest(params) {
  // 串行排队，避免多个提问叠在一起
  const task = questionQueue.then(() => new Promise((resolve) => {
    questionResolve = resolve;
    $("question-text").textContent = params.question || "";
    const optionsBox = $("question-options");
    optionsBox.textContent = "";
    (params.options || []).forEach((opt, i) => {
      const btn = el("button", "q-option");
      btn.appendChild(el("span", "q-opt-label", String(opt)));
      btn.appendChild(el("span", "q-num", String(i + 1)));
      btn.onclick = () => settleQuestion(String(opt));
      optionsBox.appendChild(btn);
    });
    $("question-custom-row").classList.toggle("hidden", !params.allowCustom);
    $("question-actions").classList.toggle("hidden", !params.allowCustom);
    $("question-custom-num").textContent = String((params.options || []).length + 1);
    $("question-custom").value = "";
    $("input-card").classList.add("hidden");  // 提问卡吞掉输入框
    $("question-card").classList.remove("hidden");
    if (params.allowCustom) $("question-custom").focus();
  }));
  questionQueue = task.catch(() => {});
  return task.then((answer) => ({ answer }));
}

function settleQuestion(answer) {
  $("question-card").classList.add("hidden");
  $("input-card").classList.remove("hidden");
  const resolve = questionResolve;
  questionResolve = null;
  if (resolve) resolve(answer);
}

function hideQuestion() { if (questionResolve) settleQuestion(null); }

rpc.onServerRequest = (method, params) => {
  if (method === "approval/request") return handleApprovalRequest(params);
  if (method === "question/request") return handleQuestionRequest(params);
  throw new Error("未知请求: " + method);
};

rpc.onNotification = (method, params) => {
  if (method === "session/event") onSessionEvent(params.sessionId, params.event, params.seq);
};

/* ================= 输入 / 轮次 ================= */

function updateInputState() {
  const send = $("send-btn");
  const stop = $("stop-btn");
  send.classList.toggle("hidden", state.busy);
  stop.classList.toggle("hidden", !state.busy);
  send.disabled = !state.connected || !$("input").value.trim();
  stop.disabled = !state.connected;
}

async function send() {
  const input = $("input");
  const text = input.value.trim();
  if (!text) return;
  if (!state.connected || !state.sessionId) { addSystem("尚未连接，不能发送消息", true); return; }
  if (state.busy) { addSystem("运行中，不能发送消息"); return; }
  state.busy = true;
  updateInputState();
  $("welcome") && $("welcome").remove();
  resetFlow();
  $("messages").appendChild(userNode(text));
  showPending();
  stickToBottom = true;
  scrollToBottom();
  input.value = "";
  input.style.height = "auto";
  try {
    await rpc.request("turn/start", { sessionId: state.sessionId, input: text });
  } catch (e) {
    hidePending();
    state.busy = false;
    updateInputState();
    addSystem("❌ " + e.message, true);
  }
}

async function cancelTurn() {
  if (!state.busy || !state.sessionId) return;
  try { await rpc.request("turn/cancel", { sessionId: state.sessionId }); }
  catch { /* 断线等情况由重连逻辑兜底 */ }
}

/* ================= 模型 ================= */

function populateModelSelect() {
  const menu = $("model-menu");
  menu.textContent = "";
  for (const m of state.models) {
    const item = el("div", "model-item");
    const check = el("span", "model-check");
    if (m.id === state.model) check.appendChild(icon("tick"));
    item.appendChild(check);
    item.appendChild(el("span", "model-item-name", m.displayName || m.id));
    item.onclick = () => { closeModelMenu(); onModelChange(m.id); };
    menu.appendChild(item);
  }
  const cur = state.models.find((m) => m.id === state.model);
  // 没有匹配项时显示“默认模型”（由服务端决定），不留空，否则 :empty 骨架条会一直显示
  $("model-name").textContent = cur ? (cur.displayName || cur.id) : "默认模型";
}

function closeModelMenu() {
  $("model-menu").classList.add("hidden");
  $("model-pill").classList.remove("open");
}

async function onModelChange(picked) {
  if (!picked || picked === state.model) return;
  state.model = picked;
  populateModelSelect();  // 立即更新按钮文字与选中勾
  try {
    if (state.sessionId) await rpc.request("session/set_model", { sessionId: state.sessionId, model: picked });
    addSystem(`已切换到 ${$("model-name").textContent}`);
  } catch (e) {
    addSystem("❌ 切换模型失败：" + e.message, true);
  }
}

/* ================= 事件绑定 ================= */

function bind() {
  $("send-btn").onclick = send;
  $("stop-btn").onclick = cancelTurn;
  $("new-session-btn").onclick = newSession;
  $("new-work-btn").onclick = createWork;
  const toggleSidebar = () => $("app").classList.toggle("sidebar-collapsed");
  $("toggle-sidebar").onclick = toggleSidebar;
  $("expand-sidebar").onclick = toggleSidebar;

  /* 空会话首页：消息区里还没有用户/助手内容时，#main 进入 is-empty，
     字标 + 输入框居中显示，并露出快捷胶囊；系统提示不算内容；
     对话骨架显示期间（历史尚未返回）不算空，避免首页字标一闪而过 */
  const syncEmpty = () => {
    const hasContent = $("messages").querySelector(".msg-skeleton, .msg:not(.system), .assistant-turn, .work-group, .pending-indicator, .load-more");
    $("main").classList.toggle("is-empty", !hasContent);
  };
  new MutationObserver(syncEmpty).observe($("messages"), { childList: true });
  syncEmpty();
  const togglePlan = () => {
    const collapsed = $("plan-panel").classList.toggle("hidden");
    $("plan-pill").setAttribute("aria-pressed", String(!collapsed));
  };
  $("plan-pill").onclick = togglePlan;
  $("plan-header").onclick = togglePlan;
  // 计划胶囊常驻消息区底部上方：--plan-h 只预留胶囊高度，展开卡片作为浮层盖在消息上；
  // 「最新消息」按钮按 --scroll-b 浮在胶囊/输入区上方（计划卡展开时按钮被卡片盖住，由 syncScrollBtn 隐藏）。
  // 输入区高度（多行输入）和计划层尺寸变化都会触发重算
  const syncChrome = () => {
    const dock = $("plan-dock");
    const dockHidden = dock.classList.contains("hidden");
    const pillH = dockHidden ? 0 : $("plan-pill").offsetHeight;
    document.documentElement.style.setProperty("--plan-h", pillH + "px");
    const inputH = $("input-area").offsetHeight;
    const gap = dockHidden ? 12 : pillH + 10;
    document.documentElement.style.setProperty("--scroll-b", inputH + gap + "px");
    maybeScroll(true);
  };
  const chromeRO = new ResizeObserver(syncChrome);
  chromeRO.observe($("plan-dock"));
  chromeRO.observe($("input-area"));
  $("model-btn").onclick = (e) => {
    e.stopPropagation();  // 防止被下面的 document click 立即关掉
    const open = $("model-menu").classList.toggle("hidden");
    $("model-pill").classList.toggle("open", !open);
  };
  document.addEventListener("click", (e) => {
    if (!e.target.closest("#model-pill")) closeModelMenu();
  });
  $("messages").addEventListener("scroll", updateStick);
  $("scroll-bottom").onclick = () => {
    stickToBottom = true;
    smoothScrollToBottom();
    updateStick();
  };

  $("approval-approve").onclick = () => settleApproval(true);
  $("approval-reject").onclick = () => settleApproval(false);
  $("question-cancel").onclick = () => settleQuestion(null);
  $("question-close").onclick = () => settleQuestion(null);
  $("question-submit").onclick = () => {
    const v = $("question-custom").value.trim();
    if (v) settleQuestion(v);
  };
  $("question-custom").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const v = e.target.value.trim();
      if (v) settleQuestion(v);
    }
  });

  const input = $("input");
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  });
  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 180) + "px";
    updateInputState();
  });
  document.addEventListener("keydown", (e) => {
    /* 提问卡打开期间接管按键：Esc 放弃提问，数字键 1-9 快选选项，
       自定义输入框聚焦时放行字符输入（Enter 提交由输入框自己的监听器处理） */
    if (!$("question-card").classList.contains("hidden")) {
      if (e.key === "Escape") { e.preventDefault(); settleQuestion(null); return; }
      if (e.target === $("question-custom")) return;
      const n = parseInt(e.key, 10);
      const btns = $("question-options").children;
      if (n >= 1 && n <= btns.length) btns[n - 1].click();
      else if (n === btns.length + 1 && !$("question-custom-row").classList.contains("hidden")) $("question-custom").focus();
      return;
    }
    if (e.key === "Escape") { closeModelMenu(); toggleUserMenu(false); cancelTurn(); }
    if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")) {
      e.preventDefault();
      newSession();
    }
  });

  /* 滚动中显示滚动条：scroll 事件不冒泡，用捕获阶段统一监听所有滚动容器。
     只在指针悬停于容器时生效——加载历史、流式输出等程序化滚动不显示
     （思考区钉底是刻意例外，在 thinking_delta 里主动标记） */
  document.addEventListener("scroll", (e) => {
    const el = e.target;
    if (!(el instanceof HTMLElement)) return;
    if (!el.matches(":hover")) return;
    markScrolling(el);
  }, true);

  /* 指针离开滚动容器时立即隐藏滚动条，不等 0.9s 计时结束。
     mouseout 在子元素间移动也会触发，用 contains(relatedTarget) 排除容器内部移动 */
  document.addEventListener("mouseout", (e) => {
    const el = e.target;
    if (!(el instanceof HTMLElement) || !el.classList.contains("is-scrolling")) return;
    if (e.relatedTarget instanceof Node && el.contains(e.relatedTarget)) return;
    clearTimeout(el._scrollbarTimer);
    el.classList.remove("is-scrolling");
  }, true);

  // 代码块复制按钮（事件委托：markdown 重绘后按钮会重建，委托不用重绑）
  $("messages").addEventListener("click", (e) => {
    const btn = e.target.closest(".code-copy");
    if (!btn) return;
    const pre = btn.closest(".code-block").querySelector("pre");
    navigator.clipboard.writeText(pre.innerText).then(() => {
      btn.textContent = "已复制";
      setTimeout(() => { btn.textContent = "复制"; }, 1200);
    });
  });
}

/* ================= 启动 ================= */

window.addEventListener("DOMContentLoaded", async () => {
  bind();
  updateInputState();
  bindAccountMenu();
  if (!getToken()) { goLogin(); return; }  // 正常情况下 index.html 头部脚本已先行跳转
  showUserChip();
  try {
    await connectAndSetup();
  } catch (e) {
    if (!getToken()) return;  // 4401/4403：已跳转登录页，不再重连
    UI.clearSkeleton("messages");
    addSystem("❌ 初始化失败：" + (e && e.message || e) + "，将自动重连", true);
    scheduleReconnect();
  }
});
