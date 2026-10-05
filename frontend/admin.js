/* 管理后台：用户管理 / 用量统计 / 系统设置。token 与角色与主站共用 localStorage（同源）。 */

const $ = (id) => document.getElementById(id);

const TOKEN_KEY = "sh.token";
const USER_KEY = "sh.username";
const ROLE_KEY = "sh.role";
const ROLE_LABELS = { owner: "站长", admin: "管理员", user: "用户" };

const myRole = localStorage.getItem(ROLE_KEY) || "user";
const myName = localStorage.getItem(USER_KEY) || "";

/* ---------- 基础 ---------- */

function showError(msg) {
  const box = $("admin-error");
  box.textContent = msg || "";
  box.classList.toggle("hidden", !msg);
}

/** 统一 API 调用：Bearer + JSON；401 清 token 回首页，其余错误抛出后端 message */
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
    localStorage.removeItem(TOKEN_KEY);
    location.href = "/static/index.html";
    throw new Error("未认证");
  }
  const payload = await r.json().catch(() => null);
  if (!r.ok) {
    throw new Error((payload && payload.message) || `请求失败（${r.status}）`);
  }
  return payload ? payload.data : null;
}

function fmtNum(n) { return n == null ? "0" : Number(n).toLocaleString(); }

function fmtBytes(bytes) {
  const n = Number(bytes || 0);
  if (n >= 1 << 30) return (n / (1 << 30)).toFixed(1) + " GB";
  if (n >= 1 << 20) return (n / (1 << 20)).toFixed(1) + " MB";
  if (n >= 1 << 10) return (n / (1 << 10)).toFixed(1) + " KB";
  return n + " B";
}

function fmtTime(iso) { return iso ? new Date(iso).toLocaleString() : "-"; }

/* ---------- 用户管理 ---------- */

let users = [];

async function loadUsers() {
  users = await api("/api/admin/users") || [];
  renderUsers();
  renderUsageUserOptions();
}

function renderUsers() {
  const tbody = $("user-tbody");
  tbody.innerHTML = "";
  if (!users.length) {
    tbody.innerHTML = `<tr class="empty-row"><td colspan="7">暂无用户</td></tr>`;
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
      actions.push(`<button class="admin-btn ${disabled ? "" : "danger"}" data-act="status" data-id="${u.user_id}" data-next="${disabled ? "active" : "disabled"}">${disabled ? "启用" : "禁用"}</button>`);
    }
    if (operable) {
      actions.push(`<button class="admin-btn" data-act="password" data-id="${u.user_id}" data-name="${u.username}">重置密码</button>`);
      actions.push(`<button class="admin-btn" data-act="quota" data-id="${u.user_id}" data-name="${u.username}" data-quota="${u.quota_bytes}">设配额</button>`);
      actions.push(`<button class="admin-btn" data-act="workquota" data-id="${u.user_id}" data-name="${u.username}" data-quota="${u.work_quota_bytes == null ? "" : u.work_quota_bytes}">work上限</button>`);
    }
    if (myRole === "owner" && !isOwnerRow) {
      const toAdmin = u.role !== "admin";
      actions.push(`<button class="admin-btn" data-act="role" data-id="${u.user_id}" data-next="${toAdmin ? "admin" : "user"}">${toAdmin ? "设为管理员" : "取消管理员"}</button>`);
    }

    tr.innerHTML = `
      <td title="ID: ${u.user_id}"></td>
      <td><span class="role-badge ${u.role}">${ROLE_LABELS[u.role] || u.role}</span></td>
      <td class="${disabled ? "status-disabled" : "status-active"}">${disabled ? "已禁用" : "正常"}</td>
      <td>${fmtBytes(u.quota_bytes)}</td>
      <td>${u.work_quota_bytes == null ? '<span class="quota-inherit">跟随全局</span>' : fmtBytes(u.work_quota_bytes)}</td>
      <td>${fmtTime(u.created_at)}</td>
      <td><div class="row-actions">${actions.join("")}</div></td>`;
    tr.cells[0].textContent = u.username;
    tbody.appendChild(tr);
  }
}

async function onUserAction(btn) {
  const id = btn.dataset.id;
  const act = btn.dataset.act;
  try {
    if (act === "status") {
      const next = btn.dataset.next;
      if (next === "disabled" && !confirm("确定禁用该账号？禁用后立即无法登录与使用。")) return;
      await api(`/api/admin/users/${id}/status`, { method: "POST", body: { status: next } });
    } else if (act === "role") {
      const next = btn.dataset.next;
      await api(`/api/admin/users/${id}/role`, { method: "POST", body: { role: next } });
    } else if (act === "password") {
      const pwd = prompt(`为 ${btn.dataset.name} 设置新密码（至少 6 位）：`);
      if (pwd == null) return;
      if (pwd.length < 6) { alert("密码至少 6 位"); return; }
      await api(`/api/admin/users/${id}/password`, { method: "POST", body: { password: pwd } });
      alert("密码已重置");
    } else if (act === "quota") {
      const currentMb = Math.round(Number(btn.dataset.quota || 0) / (1 << 20));
      const input = prompt(`为 ${btn.dataset.name} 设置存储配额（MB）：`, String(currentMb));
      if (input == null) return;
      const mb = Number(input);
      if (!Number.isFinite(mb) || mb < 0) { alert("请输入非负数字"); return; }
      await api(`/api/admin/users/${id}/quota`, { method: "POST", body: { quotaBytes: Math.round(mb * (1 << 20)) } });
    } else if (act === "workquota") {
      const current = btn.dataset.quota === "" ? "" : String(Math.round(Number(btn.dataset.quota) / (1 << 20)));
      const input = prompt(`为 ${btn.dataset.name} 设置单工作区上限（MB），留空恢复跟随全局：`, current);
      if (input == null) return;
      const trimmed = input.trim();
      if (trimmed === "") {
        await api(`/api/admin/users/${id}/work-quota`, { method: "POST", body: { quotaBytes: null } });
      } else {
        const mb = Number(trimmed);
        if (!Number.isFinite(mb) || mb < 0) { alert("请输入非负数字"); return; }
        await api(`/api/admin/users/${id}/work-quota`, { method: "POST", body: { quotaBytes: Math.round(mb * (1 << 20)) } });
      }
    }
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
  const rows = await api("/api/admin/usage?" + params.toString()) || [];
  const tbody = $("usage-tbody");
  tbody.innerHTML = "";
  if (!rows.length) {
    tbody.innerHTML = `<tr class="empty-row"><td colspan="8">暂无用量记录</td></tr>`;
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

/* ---------- 系统设置（仅站长） ---------- */

async function loadSettings() {
  if (myRole !== "owner") return;
  $("settings-section").classList.remove("hidden");
  const data = await api("/api/admin/settings");
  $("registration-open").checked = !data || data.registrationOpen !== false;
  $("work-max-mb").value = data && data.workMaxBytes != null
    ? Math.round(Number(data.workMaxBytes) / (1 << 20))
    : 20;
}

async function saveSettings() {
  const mb = Number($("work-max-mb").value);
  if (!Number.isFinite(mb) || mb < 1) { showError("单工作区上限至少 1 MB"); return; }
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
    $("settings-tip").textContent = "已保存";
    setTimeout(() => { $("settings-tip").textContent = ""; }, 2000);
  } catch (e) {
    showError(e.message);
  } finally {
    $("settings-save").disabled = false;
  }
}

/* ---------- 启动 ---------- */

function init() {
  if (!localStorage.getItem(TOKEN_KEY)) {
    location.href = "/static/index.html";
    return;
  }
  if (myRole === "user") {
    showError("无权限访问管理后台");
    $("admin-main").querySelectorAll(".admin-section").forEach((el) => el.remove());
    return;
  }
  $("admin-who").textContent = `${myName}（${ROLE_LABELS[myRole] || myRole}）`;
  $("user-tbody").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-act]");
    if (btn) onUserAction(btn);
  });
  $("usage-query").onclick = () => loadUsage().catch((e) => showError(e.message));
  $("settings-save").onclick = saveSettings;
  loadUsers().catch((e) => showError(e.message));
  loadUsage().catch((e) => showError(e.message));
  loadSettings().catch((e) => showError(e.message));
}

document.addEventListener("DOMContentLoaded", init);
