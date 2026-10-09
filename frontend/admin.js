/* 管理页：左侧导航 + 分页（账号/我的积分对所有角色开放，管理与系统分组按角色显隐）。
   token 与角色与主站共用 localStorage（同源）。 */

const $ = (id) => document.getElementById(id);

const TOKEN_KEY = "sh.token";
const USER_KEY = "sh.username";
const ROLE_KEY = "sh.role";
const ROLE_LABELS = { owner: "站长", admin: "管理员", user: "用户" };

const myRole = localStorage.getItem(ROLE_KEY) || "user";
const myName = localStorage.getItem(USER_KEY) || "";
const isStaff = myRole === "owner" || myRole === "admin";

/* ---------- 基础 ---------- */

/* 提示类信息统一走悬浮轻提示（UI.toast）；空串为清空语义，无需发提示 */
function showError(msg) {
  if (msg) UI.toast(msg, { type: "error" });
}

/** 去独立登录页；带上当前页（含 #hash 分页），登录后回到这里 */
function goLogin(reason) {
  localStorage.removeItem(TOKEN_KEY);
  const q = new URLSearchParams();
  if (reason) q.set("reason", reason);
  q.set("next", location.pathname + location.hash);
  location.replace("/static/login.html?" + q.toString());
}

/** 统一 API 调用：Bearer + JSON；401 清 token 去登录页，其余错误抛出后端 message */
async function api(path, options = {}) {
  const r = await fetch(path, {
    method: options.method || "GET",
    headers: {
      "Content-Type": "application/json",
      "Authorization": "Bearer " + localStorage.getItem(TOKEN_KEY),
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  if (r.status === 401) {
    goLogin("expired");
    throw new Error("未认证");
  }
  const payload = await r.json().catch(() => null);
  if (!r.ok) {
    throw new Error((payload && payload.message) || `请求失败（${r.status}）`);
  }
  return payload ? payload.data : null;
}

function fmtNum(n) { return n == null ? "0" : Number(n).toLocaleString(); }

/* 积分展示：最多 6 位小数并去掉尾零（DECIMAL(20,6) 序列化带尾零） */
function fmtPoints(n) {
  const v = Number(n ?? 0);
  return parseFloat(v.toFixed(6)).toLocaleString(undefined, { maximumFractionDigits: 6 });
}

const LEDGER_TYPE_LABELS = { HOLD: "预扣", SETTLE: "结算", RELEASE: "释放", DIRECT: "直扣", ADJUST: "调账", REDEEM: "兑换" };

function fmtBytes(bytes) {
  const n = Number(bytes || 0);
  if (n >= 1 << 30) return (n / (1 << 30)).toFixed(1) + " GB";
  if (n >= 1 << 20) return (n / (1 << 20)).toFixed(1) + " MB";
  if (n >= 1 << 10) return (n / (1 << 10)).toFixed(1) + " KB";
  return n + " B";
}

function fmtTime(iso) { return iso ? new Date(iso).toLocaleString() : "-"; }

/** 紧凑时间：YYYY-MM-DD HH:mm（补齐零、无秒），管理表格用 */
function fmtDT(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/** 解析非负数字输入；空串或非法返回 null（Number("") 为 0，需单独排除） */
function parseNonNegative(text) {
  const s = String(text ?? "").trim();
  if (s === "") return null;
  const n = Number(s);
  return Number.isFinite(n) && n >= 0 ? n : null;
}

/* ---------- 导航 ---------- */

const pageLoaders = {
  account: loadAccount,
  points: loadMyPoints,
  users: () => loadUsers(),
  usage: () => ensureUsers().then(() => loadUsage()),
  ledger: () => ensureUsers().then(() => loadLedger()),
  models: () => loadModels(),
  "model-config": () => loadModelConfig(),
  redeem: () => ensureUsers().then(() => loadRedeemCodes()),
  settings: () => loadSettings(),
};

const PAGE_TITLES = { account: "账号与安全", points: "账单与用量", users: "用户管理", usage: "用量统计", ledger: "积分流水", models: "模型资费", "model-config": "模型配置", redeem: "兑换码", settings: "系统设置" };

/* 页面可见性与导航分组一致：管理组对站长/管理员开放，系统组仅站长 */
function pageAllowed(page) {
  if (!Object.hasOwn(pageLoaders, page)) return false;
  if (page === "settings" || page === "model-config") return myRole === "owner";
  if (page === "users" || page === "usage" || page === "ledger" || page === "models" || page === "redeem") return isStaff;
  return true;
}

/** 从地址栏 #hash 解析目标页；无权限或未知页回落到账号页 */
function pageFromHash() {
  const page = decodeURIComponent(location.hash.slice(1));
  return pageAllowed(page) ? page : "account";
}

function switchPage(page) {
  if (!pageAllowed(page)) page = "account";
  document.querySelectorAll("#admin-nav .nav-item").forEach((el) =>
    el.classList.toggle("active", el.dataset.page === page));
  document.querySelectorAll(".admin-page").forEach((el) =>
    el.classList.toggle("active", el.dataset.page === page));
  document.title = (PAGE_TITLES[page] || "账户中心") + " - Spring Harness";
  // 同步地址栏，刷新或分享链接时停留在当前页（replaceState 不触发 hashchange）
  if (location.hash !== "#" + page) history.replaceState(null, "", "#" + page);
  $("admin-main").scrollTop = 0;
  showError("");
  const loader = pageLoaders[page];
  const section = document.querySelector(`.admin-page[data-page="${page}"]`);
  // 首次进入时表格先铺骨架（用量/流水页要先等用户列表，期间也不留空白表头）
  section?.querySelectorAll("tbody").forEach((tb) => { if (!tb.rows.length) UI.tableSkeleton(tb); });
  if (loader) {
    loader().catch((e) => {
      if (section) UI.settleSkeletons(section);
      showError(e.message);
    });
  }
}

/* ---------- 账号与安全 ---------- */

async function loadAccount() {
  const me = await api("/api/billing/me");
  const balance = Number(me?.balance ?? 0);
  const el = $("account-points");
  el.textContent = fmtPoints(balance);
  el.classList.toggle("points-out", balance < 0);
}

/* ---------- 我的积分 ---------- */

/* 兑换所得组合文案：跳过 0 项（granted_* 字段命名通用） */
function grantedPartsText(g) {
  const parts = [];
  if (Number(g.granted_points) > 0) parts.push("+" + fmtPoints(g.granted_points) + " 积分");
  if (Number(g.granted_storage_bytes) > 0) parts.push("+" + fmtBytes(g.granted_storage_bytes) + " 存储配额");
  if (Number(g.granted_work_quota_bytes) > 0) parts.push("+" + fmtBytes(g.granted_work_quota_bytes) + " work 配额");
  return parts.join(" · ");
}

async function loadMyPoints() {
  const me = await api("/api/billing/me");
  const balance = Number(me?.balance ?? 0);
  const big = $("points-big");
  big.textContent = fmtPoints(balance);
  big.classList.toggle("negative", balance < 0);
  $("quota-storage").textContent = me
    ? fmtBytes(me.storage_used_bytes) + " / " + fmtBytes(me.quota_bytes)
    : "-";
  $("quota-work").textContent = me ? fmtBytes(me.work_quota_bytes) : "-";

  const reds = await api("/api/billing/redemptions");
  const redBox = $("my-redemptions");
  redBox.innerHTML = "";
  if (!reds || !reds.length) {
    redBox.innerHTML = `<div class="empty-tip">暂无兑换记录</div>`;
  } else {
    for (const r of reds) {
      const chips = [];
      if (Number(r.granted_points) > 0) chips.push(`<span class="red-chip">+${fmtPoints(r.granted_points)} 积分</span>`);
      if (Number(r.granted_storage_bytes) > 0) chips.push(`<span class="red-chip">+${fmtBytes(r.granted_storage_bytes)} 存储配额</span>`);
      if (Number(r.granted_work_quota_bytes) > 0) chips.push(`<span class="red-chip">+${fmtBytes(r.granted_work_quota_bytes)} work 配额</span>`);
      const div = document.createElement("div");
      div.className = "red-item";
      div.innerHTML = `
        <svg class="red-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="8" width="18" height="4" rx="1"/><path d="M5 12v8a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-8M12 8v13M12 8s-1.5-5-4.5-5a2 2 0 0 0 0 4M12 8s1.5-5 4.5-5a2 2 0 0 1 0 4"/></svg>
        <div class="red-main">
          <div class="red-chips">${chips.join("")}</div>
          <div class="red-meta">${fmtDT(r.redeemed_at)} · ${r.code}</div>
        </div>`;
      redBox.appendChild(div);
    }
  }

  const box = $("my-ledger");
  box.innerHTML = "";
  const rows = me?.ledger || [];
  if (!rows.length) {
    box.innerHTML = `<div class="empty-tip">暂无明细</div>`;
    return;
  }
  for (const r of rows) {
    const change = Number(r.change_amount);
    const meta = [fmtDT(r.created_at), r.model_name, r.reason].filter(Boolean).join(" · ");
    const div = document.createElement("div");
    div.className = "ledger-row";
    div.innerHTML = `
      <div>
        <div class="ledger-type">${LEDGER_TYPE_LABELS[r.type] || r.type}</div>
        <div class="ledger-meta"></div>
      </div>
      <div class="ledger-change num ${change >= 0 ? "points-in" : "points-out"}">${change >= 0 ? "+" : ""}${fmtPoints(r.change_amount)}</div>`;
    div.querySelector(".ledger-meta").textContent = meta;
    box.appendChild(div);
  }
}

/* ---------- 用户管理 ---------- */

let users = [];
let usersLoaded = false;

async function ensureUsers() {
  if (!usersLoaded) await loadUsers();
}

async function loadUsers() {
  users = await UI.loadTable("user-tbody", () => api("/api/admin/users")) || [];
  usersLoaded = true;
  renderUsers();
  renderUsageUserOptions();
  renderLedgerUserOptions();
}

function renderUsers() {
  const tbody = $("user-tbody");
  tbody.innerHTML = "";
  if (!users.length) {
    UI.emptyRow(tbody, "暂无用户");
    return;
  }
  for (const u of users) {
    const tr = document.createElement("tr");
    const isOwnerRow = u.role === "owner";
    // 管理员只能操作普通用户；站长可操作任何人（站长行的禁用/角色按钮另有限制）
    const operable = myRole === "owner" || (myRole === "admin" && u.role === "user");
    const disabled = u.status === "disabled";

    const actions = [];
    if (operable && !isOwnerRow) {
      actions.push(`<button class="admin-btn ${disabled ? "" : "danger"}" data-act="status" data-id="${u.user_id}" data-name="${u.username}" data-next="${disabled ? "active" : "disabled"}">${disabled ? "启用" : "禁用"}</button>`);
    }
    if (operable) {
      actions.push(`<button class="admin-btn" data-act="password" data-id="${u.user_id}" data-name="${u.username}">重置密码</button>`);
      actions.push(`<button class="admin-btn" data-act="quota" data-id="${u.user_id}" data-name="${u.username}" data-quota="${u.quota_bytes}">设配额</button>`);
      actions.push(`<button class="admin-btn" data-act="workquota" data-id="${u.user_id}" data-name="${u.username}" data-quota="${u.work_quota_bytes == null ? "" : u.work_quota_bytes}">work配额</button>`);
    }
    // 调账是带流水的交易（非直接改数），仅站长
    if (myRole === "owner" && !isOwnerRow) {
      actions.push(`<button class="admin-btn" data-act="points" data-id="${u.user_id}" data-name="${u.username}">调账</button>`);
      const toAdmin = u.role !== "admin";
      actions.push(`<button class="admin-btn" data-act="role" data-id="${u.user_id}" data-next="${toAdmin ? "admin" : "user"}">${toAdmin ? "设为管理员" : "取消管理员"}</button>`);
    }

    tr.innerHTML = `
      <td title="ID: ${u.user_id}"></td>
      <td class="user-email"></td>
      <td><span class="role-badge ${u.role}">${ROLE_LABELS[u.role] || u.role}</span></td>
      <td class="${disabled ? "status-disabled" : "status-active"}">${disabled ? "已禁用" : "正常"}</td>
      <td>${fmtBytes(u.quota_bytes)}</td>
      <td>${u.work_quota_bytes == null ? '<span class="quota-inherit">跟随全局</span>' : fmtBytes(u.work_quota_bytes)}</td>
      <td class="num">${fmtPoints(u.points_balance)}</td>
      <td>${fmtTime(u.created_at)}</td>
      <td><div class="row-actions">${actions.join("")}</div></td>`;
    tr.cells[0].textContent = u.username;
    tr.cells[1].textContent = u.email || "-";
    tbody.appendChild(tr);
  }
}

async function onUserAction(btn) {
  const id = btn.dataset.id;
  const act = btn.dataset.act;
  const name = btn.dataset.name || "";
  const post = (path, body) => api(`/api/admin/users/${id}/${path}`, { method: "POST", body });
  const MB = 1 << 20;
  try {
    // 需要输入/确认的操作走自绘对话框：提交在框内完成，失败时错误就地显示、可直接修改重试；
    // 返回 null/false 表示用户取消
    let done;
    if (act === "status") {
      const next = btn.dataset.next;
      if (next === "disabled") {
        const ok = await UI.confirm({
          title: "禁用账号",
          message: `确定禁用「${name}」吗？\n禁用后该账号立即无法登录与使用。`,
          okText: "禁用",
          danger: true,
          submit: () => post("status", { status: next }),
        });
        if (!ok) return;
        done = `已禁用「${name}」`;
      } else {
        await post("status", { status: next });
        done = `已启用「${name}」`;
      }
    } else if (act === "role") {
      const next = btn.dataset.next;
      await post("role", { role: next });
      done = next === "admin" ? "已设为管理员" : "已取消管理员";
    } else if (act === "password") {
      const v = await UI.dialog({
        title: "重置密码",
        message: `为「${name}」设置一个新的登录密码。`,
        fields: [
          { name: "pwd", label: "新密码", type: "password", autocomplete: "new-password", hint: "至少 6 位" },
          { name: "pwd2", label: "确认新密码", type: "password", autocomplete: "new-password" },
        ],
        okText: "重置密码",
        validate: (f) => {
          if (f.pwd.length < 6) return { name: "pwd", message: "密码至少 6 位" };
          if (f.pwd !== f.pwd2) return { name: "pwd2", message: "两次输入的密码不一致" };
          return null;
        },
        submit: (f) => post("password", { password: f.pwd }),
      });
      if (!v) return;
      done = "密码已重置";
    } else if (act === "quota") {
      const currentMb = Math.round(Number(btn.dataset.quota || 0) / MB);
      const v = await UI.prompt({
        title: "存储配额",
        message: `设置「${name}」可使用的总存储空间。`,
        label: "配额",
        value: currentMb,
        inputMode: "decimal",
        suffix: "MB",
        okText: "保存",
        validate: (s) => (parseNonNegative(s) == null ? "请输入非负数字" : null),
        submit: (s) => post("quota", { quotaBytes: Math.round(parseNonNegative(s) * MB) }),
      });
      if (v === null) return;
      done = "存储配额已更新";
    } else if (act === "workquota") {
      const current = btn.dataset.quota === "" ? "" : String(Math.round(Number(btn.dataset.quota) / MB));
      const v = await UI.prompt({
        title: "单工作区配额",
        message: `设置「${name}」每个项目目录允许占用的最大空间。`,
        label: "配额",
        value: current,
        placeholder: "跟随全局",
        inputMode: "decimal",
        suffix: "MB",
        hint: "留空则恢复跟随全局设置",
        okText: "保存",
        validate: (s) => (s.trim() === "" || parseNonNegative(s) != null ? null : "请输入非负数字，或留空"),
        submit: (s) => post("work-quota", {
          quotaBytes: s.trim() === "" ? null : Math.round(parseNonNegative(s) * MB),
        }),
      });
      if (v === null) return;
      done = v.trim() === "" ? "已恢复跟随全局" : "单工作区配额已更新";
    } else if (act === "points") {
      const v = await UI.dialog({
        title: "调账",
        message: `调整「${name}」的积分余额，记入积分流水备查。`,
        fields: [
          { name: "delta", label: "变动数额", inputMode: "decimal", placeholder: "例如 100 或 -50", hint: "正数为充值，负数为扣减" },
          { name: "reason", label: "事由", placeholder: "必填，记账备查" },
        ],
        okText: "确认调账",
        validate: (f) => {
          const delta = Number(f.delta.trim());
          if (f.delta.trim() === "" || !Number.isFinite(delta) || delta === 0) return { name: "delta", message: "请输入非零数字" };
          if (!f.reason.trim()) return { name: "reason", message: "事由不能为空" };
          return null;
        },
        submit: (f) => post("points", { delta: Number(f.delta.trim()), reason: f.reason.trim() }),
      });
      if (!v) return;
      done = "调账完成";
    }
    if (done) UI.toast(done);
    await loadUsers();
  } catch (e) {
    showError(e.message);
  }
}

/* ---------- 用量统计 ---------- */

function renderUsageUserOptions() {
  const sel = $("usage-user");
  const current = sel.value;
  sel.innerHTML = `<option value="">全部用户</option>`;
  for (const u of users) {
    const opt = document.createElement("option");
    opt.value = u.user_id;
    opt.textContent = u.username;
    sel.appendChild(opt);
  }
  sel.value = current;
}

async function loadUsage() {
  const params = new URLSearchParams();
  if ($("usage-user").value) params.set("userId", $("usage-user").value);
  if ($("usage-from").value) params.set("from", $("usage-from").value);
  // 截止日期按"不含次日零点"换算，让选择器语义是"含当天"
  if ($("usage-to").value) {
    const end = new Date($("usage-to").value + "T00:00:00");
    end.setDate(end.getDate() + 1);
    params.set("to", end.toISOString().slice(0, 10));
  }
  const rows = await UI.loadTable("usage-tbody", () => api("/api/admin/usage?" + params.toString())) || [];
  const tbody = $("usage-tbody");
  tbody.innerHTML = "";
  if (!rows.length) {
    UI.emptyRow(tbody, "暂无用量记录");
    return;
  }
  for (const r of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td></td>
      <td>${r.modelName || "-"}</td>
      <td class="num">${fmtNum(r.turns)}</td>
      <td class="num">${fmtNum(r.requests)}</td>
      <td class="num">${fmtNum(r.inputTokens)}</td>
      <td class="num">${fmtNum(r.cacheReadTokens)}</td>
      <td class="num">${fmtNum(r.cacheWriteTokens)}</td>
      <td class="num">${fmtNum(r.outputTokens)}</td>`;
    tr.cells[0].textContent = r.username || r.userId;
    tbody.appendChild(tr);
  }
}

/* ---------- 模型资费（写操作仅站长） ---------- */

let models = [];
let editingModelId = null;  // 非 null 表示表单处于编辑模式

async function loadModels() {
  models = await UI.loadTable("model-tbody", () => api("/api/admin/models")) || [];
  renderModels();
}

function renderModels() {
  const tbody = $("model-tbody");
  tbody.innerHTML = "";
  if (!models.length) {
    UI.emptyRow(tbody, "暂无资费卡");
    return;
  }
  for (const m of models) {
    const tr = document.createElement("tr");
    const isDefault = m.model_name === "default";
    const actions = [];
    if (myRole === "owner") {
      actions.push(`<button class="admin-btn" data-act="edit" data-id="${m.id}">编辑</button>`);
      if (!isDefault) {
        actions.push(`<button class="admin-btn danger" data-act="delete" data-id="${m.id}" data-name="${m.model_name}">删除</button>`);
      }
    }
    tr.innerHTML = `
      <td>${m.model_name}${isDefault ? ' <span class="settings-hint">(兜底卡)</span>' : ""}</td>
      <td class="num">${fmtPoints(m.input_points)}</td>
      <td class="num">${fmtPoints(m.cache_read_points)}</td>
      <td class="num">${fmtPoints(m.cache_write_points)}</td>
      <td class="num">${fmtPoints(m.output_points)}</td>
      <td class="${m.enabled ? "status-active" : "status-disabled"}">${m.enabled ? "启用" : "停用"}</td>
      <td>${fmtTime(m.updated_at)}</td>
      <td><div class="row-actions">${actions.join("")}</div></td>`;
    tbody.appendChild(tr);
  }
}

function fillModelForm(m) {
  $("model-name").value = m ? m.model_name : "";
  $("model-input").value = m ? Number(m.input_points) : "";
  $("model-cache-read").value = m ? Number(m.cache_read_points) : "";
  $("model-cache-write").value = m ? Number(m.cache_write_points) : "";
  $("model-output").value = m ? Number(m.output_points) : "";
  $("model-enabled").checked = m ? !!m.enabled : true;
  $("model-submit").textContent = m ? "保存修改" : "新增资费卡";
  $("model-cancel").classList.toggle("hidden", !m);
  editingModelId = m ? m.id : null;
}

async function onModelFormSubmit(e) {
  e.preventDefault();
  const body = {
    modelName: $("model-name").value.trim(),
    inputPoints: Number($("model-input").value),
    cacheReadPoints: Number($("model-cache-read").value),
    cacheWritePoints: Number($("model-cache-write").value),
    outputPoints: Number($("model-output").value),
    enabled: $("model-enabled").checked,
  };
  if (!body.modelName) { showError("模型名不能为空"); return; }
  for (const key of ["inputPoints", "cacheReadPoints", "cacheWritePoints", "outputPoints"]) {
    if (!Number.isFinite(body[key]) || body[key] < 0) { showError("费率必须是非负数字"); return; }
  }
  try {
    const editing = !!editingModelId;
    if (editing) {
      await api(`/api/admin/models/${editingModelId}`, { method: "POST", body });
    } else {
      await api("/api/admin/models", { method: "POST", body });
    }
    fillModelForm(null);
    UI.toast(editing ? "资费卡已更新" : "资费卡已新增");
    await loadModels();
  } catch (err) {
    showError(err.message);
  }
}

async function onModelAction(btn) {
  const id = btn.dataset.id;
  try {
    if (btn.dataset.act === "edit") {
      fillModelForm(models.find((m) => m.id === id) || null);
      $("model-name").focus();
    } else if (btn.dataset.act === "delete") {
      const ok = await UI.confirm({
        title: "删除资费卡",
        message: `确定删除「${btn.dataset.name}」吗？\n删除后该模型按兜底卡计费。`,
        okText: "删除",
        danger: true,
        submit: () => api(`/api/admin/models/${id}/delete`, { method: "POST" }),
      });
      if (!ok) return;
      if (editingModelId === id) fillModelForm(null);
      UI.toast("资费卡已删除");
      await loadModels();
    }
  } catch (err) {
    showError(err.message);
  }
}

/* ---------- 模型配置（仅站长）：Provider / 模型定义 / 默认模型 ---------- */

let modelConfig = { providers: [], models: [], defaultModel: "" };
let editingProviderName = null;   // 非 null 表示 Provider 表单处于编辑模式
let editingModelDefId = null;     // 非 null 表示模型表单处于编辑模式

async function loadModelConfig() {
  const data = await api("/api/admin/model-config");
  modelConfig = data || { providers: [], models: [], defaultModel: "" };
  renderMcDefault();
  renderMcProviders();
  renderMcModels();
}

/* 默认模型下拉：只列启用项；无默认时给出未设置占位 */
function renderMcDefault() {
  const sel = $("mc-default");
  sel.innerHTML = "";
  const enabled = modelConfig.models.filter((m) => m.enabled);
  if (!modelConfig.defaultModel) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "未设置";
    sel.appendChild(opt);
  }
  for (const m of enabled) {
    const opt = document.createElement("option");
    opt.value = m.id;
    opt.textContent = `${m.display_name}（${m.id}）`;
    sel.appendChild(opt);
  }
  sel.value = modelConfig.defaultModel;
  UI.enhance();
}

function renderMcProviders() {
  const tbody = $("mc-provider-tbody");
  tbody.innerHTML = "";
  if (!modelConfig.providers.length) {
    UI.emptyRow(tbody, "暂无 Provider");
    return;
  }
  for (const p of modelConfig.providers) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td></td>
      <td>${p.type}</td>
      <td class="mc-ellipsis"></td>
      <td>${p.api_key_configured ? "已配置" : '<span class="status-disabled">未配置</span>'}</td>
      <td>${fmtTime(p.updated_at)}</td>
      <td><div class="row-actions">
        <button class="admin-btn" data-act="edit" data-name="${p.name}">编辑</button>
        <button class="admin-btn danger" data-act="delete" data-name="${p.name}">删除</button>
      </div></td>`;
    tr.cells[0].textContent = p.name;
    tr.cells[2].textContent = p.base_url || "-";
    if (p.base_url) tr.cells[2].title = p.base_url;
    tbody.appendChild(tr);
  }
}

function fillMcProviderForm(p) {
  $("mc-p-name").value = p ? p.name : "";
  $("mc-p-name").disabled = !!p;  // 名称即主键，编辑时锁定
  $("mc-p-type").value = p ? p.type : "openai";
  $("mc-p-key").value = "";
  $("mc-p-key").placeholder = p
    ? (p.api_key_configured ? "已配置，留空保持不变" : "未配置，请填写")
    : "API Key（必填）";
  $("mc-p-url").value = p ? (p.base_url || "") : "";
  $("mc-p-submit").textContent = p ? "保存修改" : "新增 Provider";
  $("mc-p-cancel").classList.toggle("hidden", !p);
  editingProviderName = p ? p.name : null;
  UI.enhance();
}

async function onMcProviderSubmit(e) {
  e.preventDefault();
  const body = {
    name: $("mc-p-name").value.trim(),
    type: $("mc-p-type").value,
    apiKey: $("mc-p-key").value.trim(),
    baseUrl: $("mc-p-url").value.trim(),
  };
  if (!body.name) { showError("Provider 名不能为空"); return; }
  if (!editingProviderName && !body.apiKey) { showError("新建 Provider 必须填写 API Key"); return; }
  try {
    await api("/api/admin/model-config/providers", { method: "POST", body });
    fillMcProviderForm(null);
    UI.toast("Provider 已保存");
    await loadModelConfig();
  } catch (err) {
    showError(err.message);
  }
}

async function onMcProviderAction(btn) {
  const name = btn.dataset.name;
  try {
    if (btn.dataset.act === "edit") {
      fillMcProviderForm(modelConfig.providers.find((p) => p.name === name) || null);
      $("mc-p-key").focus();
    } else if (btn.dataset.act === "delete") {
      const ok = await UI.confirm({
        title: "删除 Provider",
        message: `确定删除 Provider「${name}」吗？`,
        okText: "删除",
        danger: true,
        submit: () => api(`/api/admin/model-config/providers/${encodeURIComponent(name)}/delete`, { method: "POST" }),
      });
      if (!ok) return;
      if (editingProviderName === name) fillMcProviderForm(null);
      UI.toast("Provider 已删除");
      await loadModelConfig();
    }
  } catch (err) {
    showError(err.message);
  }
}

function renderMcModels() {
  const tbody = $("mc-model-tbody");
  tbody.innerHTML = "";
  // Provider 下拉跟随最新列表
  const sel = $("mc-m-provider");
  const prev = sel.value;
  sel.innerHTML = "";
  for (const p of modelConfig.providers) {
    const opt = document.createElement("option");
    opt.value = p.name;
    opt.textContent = p.name;
    sel.appendChild(opt);
  }
  if (modelConfig.providers.some((p) => p.name === prev)) sel.value = prev;
  UI.enhance();

  if (!modelConfig.models.length) {
    UI.emptyRow(tbody, "暂无模型");
    return;
  }
  for (const m of modelConfig.models) {
    const tr = document.createElement("tr");
    const actions = [
      `<button class="admin-btn" data-act="edit" data-id="${m.id}">编辑</button>`,
    ];
    if (!m.is_default) {
      actions.push(`<button class="admin-btn danger" data-act="delete" data-id="${m.id}">删除</button>`);
    }
    tr.innerHTML = `
      <td class="mc-ellipsis"></td>
      <td>${m.provider}</td>
      <td class="mc-ellipsis"></td>
      <td class="mc-ellipsis"></td>
      <td class="num">${Math.round(m.max_context_size / 1024)}K</td>
      <td class="mc-ellipsis"></td>
      <td class="${m.enabled ? "status-active" : "status-disabled"}">${m.enabled ? "启用" : "停用"}</td>
      <td><div class="row-actions">${actions.join("")}</div></td>`;
    tr.cells[0].textContent = m.id;
    tr.cells[0].title = m.id;
    tr.cells[2].textContent = m.model;
    tr.cells[2].title = m.model;
    tr.cells[3].textContent = m.display_name;
    tr.cells[3].title = m.display_name;
    tr.cells[5].textContent = m.capabilities.join(", ") || "-";
    if (m.capabilities.length) tr.cells[5].title = m.capabilities.join(", ");
    tbody.appendChild(tr);
  }
}

function fillMcModelForm(m) {
  $("mc-m-id").value = m ? m.id : "";
  $("mc-m-id").disabled = !!m;  // ID 即主键，编辑时锁定
  if (m) $("mc-m-provider").value = m.provider;
  $("mc-m-model").value = m ? m.model : "";
  $("mc-m-display").value = m ? m.display_name : "";
  $("mc-m-context").value = m ? m.max_context_size : "";
  $("mc-m-output").value = m ? m.max_output_size : "";
  $("mc-m-caps").value = m ? m.capabilities.join(",") : "";
  $("mc-m-efforts").value = m ? m.support_efforts.join(",") : "";
  $("mc-m-effort").value = m ? (m.default_effort || "") : "";
  $("mc-m-reasoning").value = m ? (m.reasoning_key || "") : "";
  $("mc-m-enabled").checked = m ? !!m.enabled : true;
  $("mc-m-submit").textContent = m ? "保存修改" : "新增模型";
  $("mc-m-cancel").classList.toggle("hidden", !m);
  editingModelDefId = m ? m.id : null;
}

/** 逗号分隔输入 → 数组（去空白去空项） */
function csvToList(raw) {
  return raw.split(",").map((s) => s.trim()).filter(Boolean);
}

async function onMcModelSubmit(e) {
  e.preventDefault();
  const body = {
    id: $("mc-m-id").value.trim(),
    provider: $("mc-m-provider").value,
    model: $("mc-m-model").value.trim(),
    displayName: $("mc-m-display").value.trim(),
    maxContextSize: Number($("mc-m-context").value),
    maxOutputSize: Number($("mc-m-output").value || 0),
    capabilities: csvToList($("mc-m-caps").value),
    supportEfforts: csvToList($("mc-m-efforts").value),
    defaultEffort: $("mc-m-effort").value.trim(),
    reasoningKey: $("mc-m-reasoning").value.trim(),
    enabled: $("mc-m-enabled").checked,
  };
  if (!body.id || !body.provider || !body.model || !body.displayName) { showError("模型 ID / Provider / 实际模型名 / 展示名 必填"); return; }
  if (!Number.isFinite(body.maxContextSize) || body.maxContextSize < 1) { showError("上下文窗口必须为正数"); return; }
  try {
    await api("/api/admin/model-config/models", { method: "POST", body });
    fillMcModelForm(null);
    UI.toast("模型已保存");
    await loadModelConfig();
  } catch (err) {
    showError(err.message);
  }
}

async function onMcModelAction(btn) {
  const id = btn.dataset.id;
  try {
    if (btn.dataset.act === "edit") {
      fillMcModelForm(modelConfig.models.find((m) => m.id === id) || null);
      $("mc-m-model").focus();
    } else if (btn.dataset.act === "delete") {
      const ok = await UI.confirm({
        title: "删除模型",
        message: `确定删除模型「${id}」吗？\n存量会话若仍引用它将无法继续对话。`,
        okText: "删除",
        danger: true,
        submit: () => api("/api/admin/model-config/models/delete", { method: "POST", body: { modelId: id } }),
      });
      if (!ok) return;
      if (editingModelDefId === id) fillMcModelForm(null);
      UI.toast("模型已删除");
      await loadModelConfig();
    }
  } catch (err) {
    showError(err.message);
  }
}

async function onMcDefaultChange() {
  const modelId = $("mc-default").value;
  if (!modelId || modelId === modelConfig.defaultModel) return;
  try {
    await api("/api/admin/model-config/default", { method: "POST", body: { modelId } });
    modelConfig.defaultModel = modelId;
    renderMcModels();
    UI.toast("默认模型已切换");
  } catch (err) {
    showError(err.message);
    await loadModelConfig();
  }
}

/* ---------- 兑换码 ---------- */

/* 状态用着色文字表达（§6.9），不用底色徽章 */
function redeemStatusHtml(row) {
  if (row.status === "REDEEMED") return `<span class="face-zero">已使用</span>`;
  if (row.status === "REVOKED") return `<span class="status-disabled">已作废</span>`;
  if (row.expired) return `<span class="status-warn">已过期</span>`;
  return `<span class="status-active">待使用</span>`;
}

/* 面值单元格：0 显示为淡色占位，数值与类型分列 */
function faceCell(value, fmt) {
  const n = Number(value);
  return n > 0 ? fmt(n) : `<span class="face-zero">–</span>`;
}

async function loadRedeemCodes() {
  const params = new URLSearchParams();
  if ($("redeem-status").value) params.set("status", $("redeem-status").value);
  const rows = await UI.loadTable("redeem-tbody", () => api("/api/admin/redeem-codes?" + params.toString())) || [];
  const nameOf = Object.fromEntries(users.map((u) => [u.user_id, u.username]));
  const tbody = $("redeem-tbody");
  tbody.innerHTML = "";
  if (!rows.length) {
    UI.emptyRow(tbody, "暂无兑换码");
    return;
  }
  for (const row of rows) {
    const tr = document.createElement("tr");
    const actions = [`<button class="admin-btn" data-act="copy" data-code="${row.code}">复制</button>`];
    if (myRole === "owner" && row.status === "ACTIVE") {
      actions.push(`<button class="admin-btn danger" data-act="revoke" data-id="${row.id}">作废</button>`);
    }
    const redeemedBy = row.redeemed_by ? (nameOf[row.redeemed_by] || row.redeemed_by) : null;
    tr.innerHTML = `
      <td><code class="redeem-code">${row.code}</code></td>
      <td class="num">${faceCell(row.points, fmtPoints)}</td>
      <td class="num">${faceCell(row.storage_delta_bytes, fmtBytes)}</td>
      <td class="num">${faceCell(row.work_quota_delta_bytes, fmtBytes)}</td>
      <td>${redeemStatusHtml(row)}</td>
      <td class="time-cell">${row.expires_at ? fmtDT(row.expires_at) : '<span class="face-zero">永久</span>'}</td>
      <td></td>
      <td class="time-cell">${fmtDT(row.created_at)}</td>
      <td><div class="row-actions">${actions.join("")}</div></td>`;
    tr.cells[6].innerHTML = redeemedBy
      ? `${redeemedBy}<div class="cell-sub">${fmtDT(row.redeemed_at)}</div>`
      : `<span class="face-zero">–</span>`;
    tbody.appendChild(tr);
  }
}

/* 生成兑换码：右上角主按钮弹出的对话框；校验/提交都在框内，失败可改了重试 */
async function openRedeemGen() {
  const numOrZero = (s) => {
    const t = String(s ?? "").trim();
    if (t === "") return 0;
    const n = Number(t);
    return Number.isFinite(n) && n >= 0 ? n : null;
  };
  const v = await UI.dialog({
    title: "生成兑换码",
    okText: "生成",
    fields: [
      { name: "count", label: "数量", value: "1", inputMode: "numeric", hint: "一次最多 100 个" },
      { name: "points", label: "积分", placeholder: "0", inputMode: "decimal" },
      { name: "storageMb", label: "存储配额", suffix: "MB", placeholder: "0", inputMode: "numeric" },
      { name: "workQuotaMb", label: "单工作区配额", suffix: "MB", placeholder: "0", inputMode: "numeric" },
      { name: "expires", label: "有效期", suffix: "小时", placeholder: "永久", inputMode: "numeric" },
    ],
    validate: (f) => {
      const count = Number(f.count);
      if (!Number.isInteger(count) || count < 1 || count > 100) {
        return { name: "count", message: "数量必须是 1-100 的整数" };
      }
      const points = numOrZero(f.points);
      const storageMb = numOrZero(f.storageMb);
      const workQuotaMb = numOrZero(f.workQuotaMb);
      if (points === null) return { name: "points", message: "面值必须是非负数字（留空按 0 计）" };
      if (storageMb === null) return { name: "storageMb", message: "面值必须是非负数字（留空按 0 计）" };
      if (workQuotaMb === null) return { name: "workQuotaMb", message: "面值必须是非负数字（留空按 0 计）" };
      if (String(f.expires).trim() !== "") {
        const hours = Number(f.expires);
        if (!Number.isInteger(hours) || hours < 1) {
          return { name: "expires", message: "有效小时必须是正整数（留空 = 永久有效）" };
        }
      }
      if (points === 0 && storageMb === 0 && workQuotaMb === 0) {
        return { name: "points", message: "三项面值至少一项大于 0" };
      }
      return null;
    },
    submit: (f) => {
      const body = {
        count: Number(f.count),
        points: numOrZero(f.points),
        storage_mb: numOrZero(f.storageMb),
        work_quota_mb: numOrZero(f.workQuotaMb),
      };
      if (String(f.expires).trim() !== "") body.expires_in_hours = Number(f.expires);
      return api("/api/admin/redeem-codes", { method: "POST", body });
    },
  });
  if (v === null) return;
  UI.toast(`已生成 ${v.count} 个兑换码`);
  await loadRedeemCodes();
}

async function onRedeemAction(btn) {
  try {
    if (btn.dataset.act === "copy") {
      await navigator.clipboard.writeText(btn.dataset.code);
      UI.toast("兑换码已复制");
    } else if (btn.dataset.act === "revoke") {
      const ok = await UI.confirm({
        title: "作废兑换码",
        message: "确定作废该兑换码吗？作废后无法兑换。",
        okText: "作废",
        danger: true,
        submit: () => api(`/api/admin/redeem-codes/${btn.dataset.id}/revoke`, { method: "POST" }),
      });
      if (!ok) return;
      UI.toast("兑换码已作废");
      await loadRedeemCodes();
    }
  } catch (err) {
    showError(err.message);
  }
}

/* 用户侧兑换（账单与用量页）：成功/失败都走轻提示 */
async function onUserRedeem() {
  const input = $("user-redeem-input");
  const code = input.value.trim();
  if (!code) { showError("请输入兑换码"); return; }
  $("user-redeem-btn").disabled = true;
  try {
    const granted = await api("/api/billing/redeem", { method: "POST", body: { code } });
    UI.toast("兑换成功：" + grantedPartsText(granted));
    input.value = "";
    await loadMyPoints();
  } catch (err) {
    showError(err.message);
  } finally {
    $("user-redeem-btn").disabled = false;
  }
}

/* ---------- 积分流水（管理侧） ---------- */

function renderLedgerUserOptions() {
  const sel = $("ledger-user");
  const current = sel.value;
  sel.innerHTML = `<option value="">全部用户</option>`;
  for (const u of users) {
    const opt = document.createElement("option");
    opt.value = u.user_id;
    opt.textContent = u.username;
    sel.appendChild(opt);
  }
  sel.value = current;
}

async function loadLedger() {
  const params = new URLSearchParams();
  if ($("ledger-user").value) params.set("userId", $("ledger-user").value);
  const rows = await UI.loadTable("ledger-tbody", () => api("/api/admin/points/ledger?" + params.toString())) || [];
  const nameOf = Object.fromEntries(users.map((u) => [u.user_id, u.username]));
  const tbody = $("ledger-tbody");
  tbody.innerHTML = "";
  if (!rows.length) {
    UI.emptyRow(tbody, "暂无流水");
    return;
  }
  for (const r of rows) {
    const tr = document.createElement("tr");
    const change = Number(r.change_amount);
    tr.innerHTML = `
      <td>${fmtTime(r.created_at)}</td>
      <td></td>
      <td>${LEDGER_TYPE_LABELS[r.type] || r.type}</td>
      <td class="num ${change >= 0 ? "points-in" : "points-out"}">${change >= 0 ? "+" : ""}${fmtPoints(r.change_amount)}</td>
      <td class="num">${fmtPoints(r.balance_after)}</td>
      <td>${r.model_name || "-"}</td>
      <td class="ref-cell" title="${r.ref_id || ""}">${r.ref_id || "-"}</td>
      <td>${r.reason || "-"}</td>`;
    tr.cells[1].textContent = nameOf[r.user_id] || r.user_id;
    tbody.appendChild(tr);
  }
}

/* ---------- 系统设置（仅站长） ---------- */

async function loadSettings() {
  if (myRole !== "owner") return;
  // 数据返回前输入框呈骨架态（无文字、脉动、不可编辑），保存按钮禁用，避免先看到空值或默认值
  const section = document.querySelector('.admin-page[data-page="settings"]');
  section.classList.add("is-loading");
  $("settings-save").disabled = true;
  let data;
  try {
    data = await api("/api/admin/settings");
  } finally {
    section.classList.remove("is-loading");
    $("settings-save").disabled = false;
  }
  $("registration-open").checked = !data || data.registrationOpen !== false;
  $("work-max-mb").value = data && data.workMaxBytes != null
    ? Math.round(Number(data.workMaxBytes) / (1 << 20))
    : 20;
  $("est-cache-read").value = data?.billingEstCacheReadTokens ?? 90000;
  $("est-input").value = data?.billingEstInputTokens ?? 10000;
  $("est-output").value = data?.billingEstOutputTokens ?? 20000;
  $("mail-enabled").checked = !!data && data.mailRegisterEnabled === true;
  $("mail-username").value = data?.mailUsername ?? "";
  // 授权码只写不读：不回显原值，留空表示保持不变
  $("mail-auth-code").value = "";
  $("mail-auth-code").placeholder = data && data.mailAuthCodeConfigured ? "已配置，留空保持不变" : "未配置";
  $("mail-resend-interval").value = data?.mailResendIntervalSeconds ?? 60;
  $("mail-code-ttl").value = data?.mailCodeTtlSeconds ?? 300;
}

async function saveSettings() {
  const mb = Number($("work-max-mb").value);
  if (!Number.isFinite(mb) || mb < 1) { showError("单工作区配额至少 1 MB"); return; }
  const estCacheRead = Number($("est-cache-read").value);
  const estInput = Number($("est-input").value);
  const estOutput = Number($("est-output").value);
  if (![estCacheRead, estInput, estOutput].every((v) => Number.isFinite(v) && v >= 0)) {
    showError("预扣档位必须是非负数字");
    return;
  }
  $("settings-save").disabled = true;
  try {
    await api("/api/admin/settings/registration", {
      method: "POST",
      body: { open: $("registration-open").checked },
    });
    await api("/api/admin/settings/work-max-bytes", {
      method: "POST",
      body: { bytes: Math.round(mb * (1 << 20)) },
    });
    await api("/api/admin/settings/billing-est", {
      method: "POST",
      body: { cacheReadTokens: Math.round(estCacheRead), inputTokens: Math.round(estInput), outputTokens: Math.round(estOutput) },
    });
    // 邮箱验证码注册：邮箱/授权码留空 = 保持不变（后端按生效值校验开启条件）
    const mailResend = Number($("mail-resend-interval").value);
    const mailTtl = Number($("mail-code-ttl").value);
    if (!Number.isFinite(mailResend) || mailResend < 10 || !Number.isFinite(mailTtl) || mailTtl < 60) {
      throw new Error("重发间隔至少 10 秒，验证码有效期至少 60 秒");
    }
    await api("/api/admin/settings/mail", {
      method: "POST",
      body: {
        enabled: $("mail-enabled").checked,
        username: $("mail-username").value.trim(),
        authCode: $("mail-auth-code").value.trim(),
        resendIntervalSeconds: Math.round(mailResend),
        codeTtlSeconds: Math.round(mailTtl),
      },
    });
    $("settings-tip").textContent = "";
    UI.toast("设置已保存");
  } catch (e) {
    showError(e.message);
  } finally {
    $("settings-save").disabled = false;
  }
}

/* ---------- 启动 ---------- */

function init() {
  if (!localStorage.getItem(TOKEN_KEY)) {
    goLogin();  // 正常情况下 admin.html 头部脚本已先行跳转
    return;
  }

  // 分组显隐：管理组对站长/管理员开放，系统组仅站长
  if (isStaff) $("nav-group-admin").classList.remove("hidden");
  if (myRole === "owner") $("nav-group-system").classList.remove("hidden");

  document.querySelectorAll("#admin-nav .nav-item").forEach((el) => {
    el.onclick = () => switchPage(el.dataset.page);
  });

  // 下拉框与日期框换成自绘控件（原生元素仍在 DOM 里，读写 .value、监听 change 都不变）
  UI.enhance();

  // 账号页静态信息
  $("account-name").textContent = myName;
  $("account-username").textContent = myName;
  $("account-role").textContent = ROLE_LABELS[myRole] || myRole;
  $("account-role").classList.add(myRole);
  $("account-role-text").textContent = ROLE_LABELS[myRole] || myRole;
  $("account-logout").onclick = () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem(ROLE_KEY);
    localStorage.removeItem("sh.sessionId");
    location.replace("/static/login.html");
  };

  if (isStaff) {
    $("user-tbody").addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-act]");
      if (btn) onUserAction(btn);
    });
    $("model-tbody").addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-act]");
      if (btn) onModelAction(btn);
    });
    $("redeem-tbody").addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-act]");
      if (btn) onRedeemAction(btn);
    });
    $("usage-query").onclick = () => loadUsage().catch((e) => showError(e.message));
    $("ledger-query").onclick = () => loadLedger().catch((e) => showError(e.message));
    // 兑换码列表：切换状态筛选即刷新（自绘下拉会派发原生 change）
    $("redeem-status").addEventListener("change", () => loadRedeemCodes().catch((e) => showError(e.message)));
    if (myRole === "owner") {
      $("model-form").addEventListener("submit", onModelFormSubmit);
      $("model-cancel").onclick = () => fillModelForm(null);
      $("settings-save").onclick = saveSettings;
      $("redeem-open-gen").onclick = openRedeemGen;
      // 模型配置页（Provider / 模型定义 / 默认模型）
      $("mc-provider-form").addEventListener("submit", onMcProviderSubmit);
      $("mc-p-cancel").onclick = () => fillMcProviderForm(null);
      $("mc-provider-tbody").addEventListener("click", (e) => {
        const btn = e.target.closest("button[data-act]");
        if (btn) onMcProviderAction(btn);
      });
      $("mc-model-form").addEventListener("submit", onMcModelSubmit);
      $("mc-m-cancel").onclick = () => fillMcModelForm(null);
      $("mc-model-tbody").addEventListener("click", (e) => {
        const btn = e.target.closest("button[data-act]");
        if (btn) onMcModelAction(btn);
      });
      $("mc-default").addEventListener("change", onMcDefaultChange);
    } else {
      // 资费卡查看与兑换码列表对管理员开放，编辑表单与生成/作废仅站长
      $("model-form").remove();
      $("redeem-open-gen").remove();
    }
  }

  // 用户侧兑换（账单与用量页，所有角色可用）
  $("user-redeem-btn").onclick = onUserRedeem;
  $("user-redeem-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") onUserRedeem();
  });

  // 页内链接（如「查看明细」→ #points）与浏览器前进后退都走 hash
  window.addEventListener("hashchange", () => switchPage(pageFromHash()));
  switchPage(pageFromHash());
}

document.addEventListener("DOMContentLoaded", init);
