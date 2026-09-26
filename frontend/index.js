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

function updateStick() {
  const box = $("messages");
  stickToBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
  $("scroll-bottom").classList.toggle("hidden", stickToBottom);
}

function maybeScroll() {
  if (stickToBottom) scrollToBottom();
}

/* ================= 全局状态 ================= */

const rpc = new RpcClient();
const AUTO_SOURCES = new Set(["file_monitor", "background_wake"]);

const state = {
  workspace: null,
  models: [],
  model: null,
  sessionId: null,
  connected: false,
  busy: false,
  assistant: null,      // 当前流式正文气泡 {el, answer, text}
  work: null,           // 当前「工作过程」分组（连续的思考 + 工具调用）
  thinking: null,       // 当前流式思考区 {el, body}
  active: null,         // 当前展开的那一项（思考区或工具卡片），渐进式收起用
  tools: new Map(),     // tool_call_id -> 卡片引用
  historyCursor: null,  // 继续向回翻页的 previousCursor
  historyHasMore: false,
};

/* ================= 认证 ================= */

const TOKEN_KEY = "sh.token";
const USER_KEY = "sh.username";
// 页面由网关（8080）托管，聊天 WS 仍直连 Python 引擎（阶段④迁入网关）
const WS_BASE = `${location.protocol === "https:" ? "wss" : "ws"}://${location.hostname}:8001`;

function getToken() { return localStorage.getItem(TOKEN_KEY); }
function clearToken() { localStorage.removeItem(TOKEN_KEY); }

function showUserChip() {
  const name = localStorage.getItem(USER_KEY);
  if (name) {
    $("user-name").textContent = name;
    $("user-chip").classList.remove("hidden");
  }
}

function showLogin(message) {
  $("user-chip").classList.add("hidden");
  $("login-error").textContent = message || "";
  $("login-overlay").classList.remove("hidden");
  setTimeout(() => $("login-username").focus(), 0);
}

function hideLogin() { $("login-overlay").classList.add("hidden"); }

async function doAuth(mode) {
  const username = $("login-username").value.trim();
  const password = $("login-password").value;
  const errBox = $("login-error");
  if (!username || !password) { errBox.textContent = "请输入用户名和密码"; return; }
  $("login-submit").disabled = true;
  $("login-register").disabled = true;
  try {
    const r = await fetch(`/api/auth/${mode}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!r.ok) {
      // 网关统一返回 {code, message, data}，错误详情在 message 里
      let msg = null;
      try { msg = (await r.json()).message; } catch { /* 非 JSON 响应 */ }
      errBox.textContent = msg || `请求失败（${r.status}）`;
      return;
    }
    if (mode === "register") { await doAuth("login"); return; }  // 注册成功直接登录
    const data = (await r.json()).data;
    localStorage.setItem(TOKEN_KEY, data.token);
    localStorage.setItem(USER_KEY, data.username);
    localStorage.removeItem("sh.sessionId");  // 换账号不复用旧会话
    hideLogin();
    showUserChip();
    await connectAndSetup();
  } catch (e) {
    if (getToken()) {
      addSystem("❌ 连接失败：" + (e && e.message || e), true);
      scheduleReconnect();
    } else {
      errBox.textContent = "网络错误：" + (e && e.message || e);
    }
  } finally {
    $("login-submit").disabled = false;
    $("login-register").disabled = false;
  }
}

function bindAuth() {
  $("login-submit").onclick = () => doAuth("login");
  $("login-register").onclick = () => doAuth("register");
  $("login-username").addEventListener("keydown", (e) => {
    if (e.key === "Enter") $("login-password").focus();
  });
  $("login-password").addEventListener("keydown", (e) => {
    if (e.key === "Enter") doAuth("login");
  });
  $("logout-btn").onclick = () => {
    clearToken();
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem("sh.sessionId");
    location.reload();
  };
}

/* ================= 连接 / 会话引导 ================= */

let reconnectTimer = null;
let reconnectDelay = 1000;

function setConnected(ok) {
  state.connected = ok;
  const dot = $("conn-status");
  dot.className = "conn-dot " + (ok ? "connected" : "disconnected");
  dot.title = ok ? "已连接" : "未连接";
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
  $("input-ws-name").textContent = wsName;
  $("input-ws").title = state.workspace;
  const footer = $("workspace-footer");
  footer.textContent = state.workspace;
  footer.title = state.workspace;
  setConnected(true);
  await openSession();
  reconnectDelay = 1000;
}

rpc.onClose = (code) => {
  setConnected(false);
  state.busy = false;
  resetFlow();
  state.tools.clear();
  hideApproval();
  hideQuestion();
  if (code === 4401) {           // 未认证/令牌过期：回登录页，不重连
    clearToken();
    showLogin("登录已过期，请重新登录");
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
      if (!getToken()) return;   // 4401 已弹登录框，停止重连
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
    const r = await rpc.request("session/new", { workspace: state.workspace, model: state.model });
    sid = r.sessionId;
  }
  state.sessionId = sid;
  localStorage.setItem("sh.sessionId", sid);
  clearMessages();
  await loadHistory();
  await loadPlan();
  await refreshSessionList();
}

/* ================= 会话管理 ================= */

async function refreshSessionList() {
  let sessions;
  try {
    const r = await rpc.request("session/list", { workspace: state.workspace });
    sessions = r.sessions || [];
  } catch { return; }
  const list = $("session-list");
  list.textContent = "";
  const active = sessions.find((s) => s.sessionId === state.sessionId);
  $("session-title").textContent = active ? (active.title || "(空会话)") : "";
  for (const s of [...sessions].reverse()) {
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
  clearMessages();
  await loadHistory();
  await loadPlan();
  await refreshSessionList();
}

async function newSession() {
  if (state.busy) { addSystem("运行中，不能新建会话"); return; }
  try {
    const r = await rpc.request("session/new", { workspace: state.workspace, model: state.model });
    state.sessionId = r.sessionId;
    localStorage.setItem("sh.sessionId", r.sessionId);
    clearMessages();
    await refreshSessionList();
  } catch (e) {
    addSystem("❌ 新建会话失败：" + e.message, true);
  }
}

/* ================= 历史 ================= */

function clearMessages() {
  const box = $("messages");
  box.textContent = "";
  resetFlow();
  state.tools.clear();
  state.historyCursor = null;
  state.historyHasMore = false;
  $("plan-panel").classList.add("hidden");
}

async function loadHistory(cursor) {
  const params = { sessionId: state.sessionId, limit: 30, direction: "backward" };
  if (cursor) params.cursor = cursor;
  const page = await rpc.request("session/history", params);
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
  // 连续的思考 + 工具调用收进同一个「工作过程」分组，遇到正文/用户消息等边界时收口
  let group = null;
  const groupFor = () => {
    if (!group) { group = workGroupNode(); frag.appendChild(group.el); }
    return group;
  };
  const endGroup = () => {
    if (group) { refreshWorkSummary(group); group = null; }
  };
  const append = (node) => { endGroup(); frag.appendChild(node); };

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
    if (i > 0) append(systemNode("── 上下文已压缩，以上内容已压缩为摘要 ──"));
    for (const msg of seg) {
      const source = msg.metadata && msg.metadata.source;
      if (msg.kind === "request") {
        for (const part of msg.parts || []) {
          if (part.part_kind === "user-prompt" && typeof part.content === "string") {
            if (source === "background_task") append(noticeNode(part.content));
            else if (!AUTO_SOURCES.has(source)) append(userNode(part.content));
          } else if (part.part_kind === "tool-return" || part.part_kind === "retry-prompt") {
            renderTool(part);
          }
        }
      } else if (msg.kind === "response") {
        // 按 part 顺序渲染：thinking 进工作分组，text 收口分组后落成正文气泡；
        // 有返回值的卡片等 tool-return 出现时再渲染（保持真实时间序），悬挂调用就地渲染
        let text = "";
        let thinking = "";
        const flushThinking = () => {
          if (thinking) addToGroup(groupFor(), thinkingNode(thinking));
          thinking = "";
        };
        const flushText = () => {
          if (text) append(answerNode(text));
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
  endGroup();

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

function setToolTarget(card, target) {
  card.target = target;
  card.targetEl.textContent = target;
  card.targetEl.title = target;
}

function setToolStats(card, stats) {
  card.statsEl.textContent = "";
  if (!stats || (!stats.add && !stats.del)) return;
  card.statsEl.appendChild(el("span", "stat-add", `+${stats.add}`));
  card.statsEl.appendChild(el("span", "stat-del", `−${stats.del}`));
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

function historyToolCard(name, argsText, resultText, isError) {
  const card = buildToolCard(name);
  card.args.textContent = argsText || "";
  const args = parseArgs(argsText);
  setToolTarget(card, targetFromArgs(args));
  setToolStats(card, statsFromArgs(name, args));
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
  body.appendChild(args);
  body.appendChild(diff);
  body.appendChild(result);
  card.appendChild(header);
  card.appendChild(body);
  header.onclick = () => card.classList.toggle("expanded");
  return {
    el: card, id, name, target: "", error: false,
    status, args, diff, result, pending, body, targetEl, statsEl,
  };
}

/* ================= 实时事件 ================= */

function resetFlow() {
  state.assistant = null;
  state.work = null;
  state.thinking = null;
  state.active = null;
}

// 渐进式收起：新元素开始时收起上一个展开项，页面上只保留进行中的那一项展开。
// 出错信号不靠展开保留：卡片行尾的「失败」标记和分组标题里的失败计数始终可见
function setActive(node) {
  const prev = state.active;
  if (prev && prev !== node) prev.classList.remove("expanded");
  state.active = node;
  if (node) node.classList.add("expanded");
}

// 工作过程收口（正文开始、系统消息插入或本轮结束）：分组默认折叠
function closeWork() {
  if (state.work) {
    refreshWorkSummary(state.work);
    state.work.el.classList.remove("live", "expanded");
  }
  state.work = null;
  state.thinking = null;
}

function ensureWork() {
  if (state.work) return state.work;
  $("welcome") && $("welcome").remove();
  state.assistant = null;  // 正文被工作过程打断，后续正文另起气泡
  const group = workGroupNode();
  group.el.classList.add("expanded", "live");
  $("messages").appendChild(group.el);
  state.work = group;
  return group;
}

function ensureAssistant() {
  if (state.assistant) return state.assistant;
  $("welcome") && $("welcome").remove();
  closeWork();
  const wrap = answerNode("");
  $("messages").appendChild(wrap);
  state.assistant = { el: wrap, answer: wrap.querySelector(".answer"), text: "" };
  return state.assistant;
}

function onSessionEvent(sid, event) {
  if (sid !== state.sessionId) return;
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
      state.thinking.querySelector(".thinking-body").textContent += event.text;
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
        if (args && !card.hasDiff) setToolStats(card, statsFromArgs(card.name, args));
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
  state.assistant = null;
  state.tools.clear();
  if (event.cancelled && !event.wake) addSystem("已中断，可继续输入");
  else if (event.error) addSystem("❌ 运行出错：" + event.error, true);
  if (!event.wake) {   // 催醒轮是系统轮次，不占输入锁
    state.busy = false;
    updateInputState();
  }
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
  const panel = $("plan-panel");
  const list = $("plan-items");
  if (!items || !items.length) { panel.classList.add("hidden"); return; }
  panel.classList.remove("hidden");
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
  $("plan-progress").textContent = `${done}/${items.length}`;
  panel.classList.toggle("all-done", done === items.length);
}

function addSystem(text, isError) {
  closeWork();
  state.assistant = null;
  $("messages").appendChild(systemNode(text, isError));
  maybeScroll();
}

function updateUsage(tokens) {
  const model = state.models.find((m) => m.id === state.model);
  const max = model ? model.maxContextSize : 0;
  $("usage").textContent = max
    ? `上下文 ${(tokens / 1000).toFixed(1)}k / ${Math.round(max / 1000)}k`
    : `上下文 ${(tokens / 1000).toFixed(1)}k`;
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
  const task = questionQueue.then(() => new Promise((resolve) => {
    questionResolve = resolve;
    $("question-text").textContent = params.question || "";
    const optionsBox = $("question-options");
    optionsBox.textContent = "";
    for (const opt of params.options || []) {
      const btn = el("button", null, String(opt));
      btn.onclick = () => settleQuestion(String(opt));
      optionsBox.appendChild(btn);
    }
    const customRow = $("question-custom-row");
    customRow.classList.toggle("hidden", !params.allowCustom);
    $("question-custom").value = "";
    $("question-modal").classList.remove("hidden");
    if (params.allowCustom) $("question-custom").focus();
  }));
  questionQueue = task.catch(() => {});
  return task.then((answer) => ({ answer }));
}

function settleQuestion(answer) {
  $("question-modal").classList.add("hidden");
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
  if (method === "session/event") onSessionEvent(params.sessionId, params.event);
};

/* ================= 输入 / 轮次 ================= */

function updateInputState() {
  const send = $("send-btn");
  const stop = $("stop-btn");
  send.classList.toggle("hidden", state.busy);
  stop.classList.toggle("hidden", !state.busy);
  send.disabled = !state.connected;
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
  stickToBottom = true;
  scrollToBottom();
  input.value = "";
  input.style.height = "auto";
  try {
    await rpc.request("turn/start", { sessionId: state.sessionId, input: text });
  } catch (e) {
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
  const select = $("model-select");
  select.textContent = "";
  for (const m of state.models) {
    const opt = el("option", null, m.displayName || m.id);
    opt.value = m.id;
    select.appendChild(opt);
  }
  if (state.model) select.value = state.model;
}

async function onModelChange() {
  const select = $("model-select");
  const picked = select.value;
  if (!picked || picked === state.model) return;
  state.model = picked;
  try {
    if (state.sessionId) await rpc.request("session/set_model", { sessionId: state.sessionId, model: picked });
    addSystem(`已切换到 ${select.options[select.selectedIndex].text}`);
  } catch (e) {
    addSystem("❌ 切换模型失败：" + e.message, true);
  }
}

/* ================= 事件绑定 ================= */

function bind() {
  $("send-btn").onclick = send;
  $("stop-btn").onclick = cancelTurn;
  $("new-session-btn").onclick = newSession;
  $("toggle-sidebar").onclick = () => $("sidebar").classList.toggle("collapsed");
  $("plan-header").onclick = () => $("plan-panel").classList.toggle("collapsed");
  // 计划卡片悬浮在消息区上方：把它的高度写进 --plan-h，消息区底部留出同样空间，最后一条不被遮住
  new ResizeObserver(() => {
    const panel = $("plan-panel");
    const h = panel.classList.contains("hidden") ? 0 : panel.offsetHeight;
    document.documentElement.style.setProperty("--plan-h", h + "px");
    maybeScroll();
  }).observe($("plan-panel"));
  $("model-select").onchange = onModelChange;
  $("messages").addEventListener("scroll", updateStick);
  $("scroll-bottom").onclick = () => {
    stickToBottom = true;
    scrollToBottom();
    updateStick();
  };

  $("approval-approve").onclick = () => settleApproval(true);
  $("approval-reject").onclick = () => settleApproval(false);
  $("question-cancel").onclick = () => settleQuestion(null);
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
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") cancelTurn();
    if ((e.ctrlKey || e.metaKey) && (e.key === "n" || e.key === "N")) {
      e.preventDefault();
      newSession();
    }
  });

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
  bindAuth();
  if (!getToken()) { showLogin(); return; }
  showUserChip();
  try {
    await connectAndSetup();
  } catch (e) {
    if (!getToken()) return;  // 4401：登录框已弹出，不再重连
    addSystem("❌ 初始化失败：" + (e && e.message || e) + "，将自动重连", true);
    scheduleReconnect();
  }
});
