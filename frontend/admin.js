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

function showError(msg) {
  const box = $("admin-error");
  box.textContent = msg || "";
  box.classList.toggle("hidden", !msg);
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

const LEDGER_TYPE_LABELS = { HOLD: "预扣", SETTLE: "结算", RELEASE: "释放", DIRECT: "直扣", ADJUST: "调账" };

function fmtBytes(bytes) {
  const n = Number(bytes || 0);
  if (n >= 1 << 30) return (n / (1 << 30)).toFixed(1) + " GB";
  if (n >= 1 << 20) return (n / (1 << 20)).toFixed(1) + " MB";
  if (n >= 1 << 10) return (n / (1 << 10)).toFixed(1) + " KB";
  return n + " B";
}

function fmtTime(iso) { return iso ? new Date(iso).toLocaleString() : "-"; }

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
  settings: () => loadSettings(),
};

const PAGE_TITLES = { account: "账号与安全", points: "账单与用量", users: "用户管理", usage: "用量统计", ledger: "积分流水", models: "模型资费", settings: "系统设置" };

/* 页面可见性与导航分组一致：管理组对站长/管理员开放，系统设置仅站长 */
function pageAllowed(page) {
  if (!Object.hasOwn(pageLoaders, page)) return false;
  if (page === "settings") return myRole === "owner";
  if (page === "users" || page === "usage" || page === "ledger" || page === "models") return isStaff;
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

async function loadMyPoints() {
  const me = await api("/api/billing/me");
  const balance = Number(me?.balance ?? 0);
  const big = $("points-big");
  big.textContent = fmtPoints(balance);
  big.classList.toggle("negative", balance < 0);

  const box = $("my-ledger");
  box.innerHTML = "";
  const rows = me?.ledger || [];
  if (!rows.length) {
    box.innerHTML = `<div class="empty-tip">暂无明细</div>`;
    return;
  }
  for (const r of rows) {
    const change = Number(r.change_amount);
    const meta = [fmtTime(r.created_at), r.model_name, r.reason].filter(Boolean).join(" · ");
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
      actions.push(`<button class="admin-btn" data-act="workquota" data-id="${u.user_id}" data-name="${u.username}" data-quota="${u.work_quota_bytes == null ? "" : u.work_quota_bytes}">work上限</button>`);
    }
    // 调账是带流水的交易（非直接改数），仅站长
    if (myRole === "owner" && !isOwnerRow) {
      actions.push(`<button class="admin-btn" data-act="points" data-id="${u.user_id}" data-name="${u.username}">调账</button>`);
      const toAdmin = u.role !== "admin";
      actions.push(`<button class="admin-btn" data-act="role" data-id="${u.user_id}" data-next="${toAdmin ? "admin" : "user"}">${toAdmin ? "设为管理员" : "取消管理员"}</button>`);
    }

    tr.innerHTML = `
      <td title="ID: ${u.user_id}"></td>
      <td><span class="role-badge ${u.role}">${ROLE_LABELS[u.role] || u.role}</span></td>
      <td class="${disabled ? "status-disabled" : "status-active"}">${disabled ? "已禁用" : "正常"}</td>
      <td>${fmtBytes(u.quota_bytes)}</td>
      <td>${u.work_quota_bytes == null ? '<span class="quota-inherit">跟随全局</span>' : fmtBytes(u.work_quota_bytes)}</td>
      <td class="num">${fmtPoints(u.points_balance)}</td>
      <td>${fmtTime(u.created_at)}</td>
      <td><div class="row-actions">${actions.join("")}</div></td>`;
    tr.cells[0].textContent = u.username;
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
        title: "单工作区上限",
        message: `设置「${name}」每个项目目录允许占用的最大空间。`,
        label: "上限",
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
      done = v.trim() === "" ? "已恢复跟随全局" : "单工作区上限已更新";
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
}

async function saveSettings() {
  const mb = Number($("work-max-mb").value);
  if (!Number.isFinite(mb) || mb < 1) { showError("单工作区上限至少 1 MB"); return; }
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
    $("usage-query").onclick = () => loadUsage().catch((e) => showError(e.message));
    $("ledger-query").onclick = () => loadLedger().catch((e) => showError(e.message));
    if (myRole === "owner") {
      $("model-form").addEventListener("submit", onModelFormSubmit);
      $("model-cancel").onclick = () => fillModelForm(null);
      $("settings-save").onclick = saveSettings;
    } else {
      // 资费卡查看对管理员开放，编辑表单与操作仅站长
      $("model-form").remove();
    }
  }

  // 页内链接（如「查看明细」→ #points）与浏览器前进后退都走 hash
  window.addEventListener("hashchange", () => switchPage(pageFromHash()));
  switchPage(pageFromHash());
}

document.addEventListener("DOMContentLoaded", init);
