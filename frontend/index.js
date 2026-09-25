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
  assistant: null,      // 当前流式助手气泡 {el, answer, thinkingWrap, thinkingBody}
  tools: new Map(),     // tool_call_id -> 卡片引用
  historyCursor: null,  // 继续向回翻页的 previousCursor
  historyHasMore: false,
};

/* ================= 认证 ================= */

const TOKEN_KEY = "sh.token";
const USER_KEY = "sh.username";

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
      errBox.textContent =
        r.status === 401 ? "用户名或密码错误"
        : r.status === 409 ? "用户名已被注册"
        : r.status === 422 ? "用户名需 2~64 个字符，密码至少 6 位"
        : `请求失败（${r.status}）`;
      return;
    }
    if (mode === "register") { await doAuth("login"); return; }  // 注册成功直接登录
    const data = await r.json();
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
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  await rpc.connect(`${scheme}://${location.host}/ws?token=${encodeURIComponent(getToken())}`);
  const info = await rpc.request("initialize", {});
  state.workspace = info.workspace;
  state.models = info.models || [];
  if (!state.model) state.model = info.defaultModel || null;
  populateModelSelect();
  const wsName = state.workspace.replace(/[\\/]+$/, "").split(/[\\/]/).pop() || state.workspace;
  $("ws-name").textContent = localStorage.getItem(USER_KEY) || wsName;
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
  state.assistant = null;
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
  state.assistant = null;
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
  const rendered = new Set();
  const renderTool = (part) => {
    const id = part.tool_call_id;
    if (!id || rendered.has(id)) return;
    rendered.add(id);
    const call = calls.get(id);
    const result = results.get(id);
    frag.appendChild(historyToolCard(
      (call && call.tool_name) || part.tool_name || "tool",
      call ? stringifyContent(call.args) : "",
      result ? stringifyContent(result.content) : null,
      result ? result.part_kind === "retry-prompt" : false,
    ));
  };

  segments.forEach((seg, i) => {
    if (i > 0) frag.appendChild(systemNode("── 上下文已压缩，以上内容已压缩为摘要 ──"));
    for (const msg of seg) {
      const source = msg.metadata && msg.metadata.source;
      if (msg.kind === "request") {
        for (const part of msg.parts || []) {
          if (part.part_kind === "user-prompt" && typeof part.content === "string") {
            if (source === "background_task") frag.appendChild(noticeNode(part.content));
            else if (!AUTO_SOURCES.has(source)) frag.appendChild(userNode(part.content));
          } else if (part.part_kind === "tool-return" || part.part_kind === "retry-prompt") {
            renderTool(part);
          }
        }
      } else if (msg.kind === "response") {
        // 按 part 顺序渲染：text/thinking 攒进当前气泡，遇到 tool-call 先把气泡落地，
        // 有返回值的卡片等 tool-return 出现时再渲染（保持真实时间序），悬挂调用就地渲染
        let text = "";
        let thinking = "";
        const flush = () => {
          if (text || thinking) frag.appendChild(assistantHistoryNode(text, thinking));
          text = thinking = "";
        };
        for (const part of msg.parts || []) {
          if (part.part_kind === "text") text += part.content || "";
          else if (part.part_kind === "thinking") thinking += part.content || "";
          else if (part.part_kind === "tool-call") {
            flush();
            if (!results.has(part.tool_call_id)) renderTool(part);
          }
        }
        flush();
      }
    }
  });

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

function assistantHistoryNode(text, thinking) {
  const wrap = el("div", "msg assistant");
  if (thinking) wrap.appendChild(thinkingNode(thinking, false));
  const answer = el("div", "answer markdown-body");
  if (text) setMarkdown(answer, text);
  wrap.appendChild(answer);
  return wrap;
}

function thinkingNode(text, expanded) {
  const wrap = el("div", "thinking" + (expanded ? " expanded" : ""));
  const header = el("div", "thinking-header", "思考过程");
  const body = el("div", "thinking-body", text);
  header.onclick = () => wrap.classList.toggle("expanded");
  wrap.appendChild(header);
  wrap.appendChild(body);
  return wrap;
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
  if (resultText !== null && resultText !== undefined) {
    card.result.textContent = resultText;
    card.result.classList.remove("hidden");
    card.result.classList.toggle("error", !!isError);
    card.status.textContent = isError ? "✗" : "✓";
    card.status.className = "tool-status " + (isError ? "error" : "done");
  } else {
    card.result.parentElement && card.result.remove();
    card.status.textContent = "—";
    card.status.className = "tool-status done";
  }
  return card.el;
}

function buildToolCard(name) {
  const card = el("div", "tool-card");
  const header = el("div", "tool-header");
  const caret = el("span", "tool-caret");
  const status = el("span", "tool-status running", "●");
  const nameEl = el("span", "tool-name", name);
  const pending = el("span", "tool-pending-label hidden", "等待批准");
  header.appendChild(caret);
  header.appendChild(status);
  header.appendChild(nameEl);
  header.appendChild(pending);
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
  return { el: card, status, args, diff, result, pending, body };
}

/* ================= 实时事件 ================= */

function collapseOpenTools() {
  // 新元素开始时收起已展开的工具卡片：状态点仍保留，不丢完成/出错信号
  for (const card of state.tools.values()) {
    card.el.classList.remove("expanded");
  }
}

function ensureAssistant() {
  if (state.assistant) return state.assistant;
  $("welcome") && $("welcome").remove();
  const wrap = el("div", "msg assistant");
  const thinkingWrap = el("div", "thinking expanded hidden");
  const thinkingHeader = el("div", "thinking-header", "思考过程");
  const thinkingBody = el("div", "thinking-body");
  thinkingHeader.onclick = () => thinkingWrap.classList.toggle("expanded");
  thinkingWrap.appendChild(thinkingHeader);
  thinkingWrap.appendChild(thinkingBody);
  const answer = el("div", "answer markdown-body");
  wrap.appendChild(thinkingWrap);
  wrap.appendChild(answer);
  $("messages").appendChild(wrap);
  state.assistant = { el: wrap, answer, thinkingWrap, thinkingBody, text: "" };
  return state.assistant;
}

function onSessionEvent(sid, event) {
  if (sid !== state.sessionId) return;
  switch (event.kind) {
    case "text_delta": {
      collapseOpenTools();  // 正文开始：上一个元素（工具卡片）收起
      const a = ensureAssistant();
      if (!a.text) {
        a.thinkingWrap.classList.remove("expanded");  // 本气泡的思考同时收起
      }
      a.text += event.text;
      setMarkdown(a.answer, a.text);
      maybeScroll();
      break;
    }
    case "thinking_delta": {
      collapseOpenTools();  // 新的思考开始：上一个元素（工具卡片）收起
      const a = ensureAssistant();
      a.thinkingWrap.classList.remove("hidden");
      a.thinkingBody.textContent += event.text;
      maybeScroll();
      break;
    }
    case "tool_started": {
      collapseOpenTools();  // 新工具开始：上一张卡片收起
      if (state.assistant) {
        state.assistant.thinkingWrap.classList.remove("expanded");  // 思考同时收起
      }
      const card = buildToolCard(event.tool_name);
      card.el.classList.add("expanded");
      state.tools.set(event.tool_call_id, card);
      // 闭合当前文本气泡：后续 text/thinking 另起新气泡，渲染顺序与事件顺序一致
      state.assistant = null;
      $("messages").appendChild(card.el);
      maybeScroll();
      break;
    }
    case "tool_args_delta": {
      const card = state.tools.get(event.tool_call_id);
      if (card) { card.args.textContent += event.args_chunk; maybeScroll(); }
      break;
    }
    case "tool_diff": {
      const card = state.tools.get(event.tool_call_id);
      if (card) { card.diff.classList.remove("hidden"); colorizeDiff(card.diff, event.diff); }
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
        card.status.textContent = event.is_error ? "✗" : "✓";
        card.status.className = "tool-status " + (event.is_error ? "error" : "done");
        card.result.textContent = event.result;
        card.result.classList.remove("hidden");
        card.result.classList.toggle("error", !!event.is_error);
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
      state.assistant = null;  // 插入独立节点后，后续文本另起气泡
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
  state.assistant = null;
  // 一轮可能有多个气泡/多张卡片：收尾时全部对齐 TUI 的收起行为
  document.querySelectorAll("#messages .thinking.expanded").forEach((t) => t.classList.remove("expanded"));
  for (const card of state.tools.values()) {
    card.pending.classList.add("hidden");
    if (card.status.classList.contains("running")) {
      // deferred 工具（ask_user 等）不走 tool_finished，收尾时补 done
      card.status.textContent = "✓";
      card.status.className = "tool-status done";
    }
    if (!card.status.classList.contains("error")) {
      card.el.classList.remove("expanded");
    }
  }
  state.tools.clear();
  if (event.cancelled && !event.wake) addSystem("已中断，可继续输入");
  else if (event.error) addSystem("❌ 运行出错：" + event.error, true);
  if (!event.wake) {   // 催醒轮是系统轮次，不占输入锁
    state.busy = false;
    updateInputState();
  }
  refreshSessionList();  // 标题/时间可能更新了
}

function renderPlan(items) {
  const panel = $("plan-panel");
  const list = $("plan-items");
  if (!items || !items.length) { panel.classList.add("hidden"); return; }
  panel.classList.remove("hidden");
  list.textContent = "";
  for (const item of items) {
    const li = el("li", item.status || "pending", item.content || "");
    if (item.status === "in_progress" && item.active_form) li.textContent = item.active_form;
    list.appendChild(li);
  }
}

function addSystem(text, isError) {
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
  state.assistant = null;
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
