# Spring Harness 前端设计规范

写给以后在这个仓库里写页面/组件的人（和 AI）。目标：新写的东西放进现有页面里看不出是后加的。

规范里的数值都取自现有代码（`index.css`、`ui.css`、`admin.css`、`login.css`）。规范与代码不一致时以代码为准，并顺手修正本文。

---

## 1. 一句话风格

**暖白底 + 白色圆角主卡片，黑白灰为主，颜色只用来表达含义，不做装饰。** 风格参考 Kimi：安静、留白多、层级靠灰度和字重区分，而不是靠颜色、边框和阴影。

判断标准：截图转成黑白后，界面层级依然清楚。如果只能靠颜色才看得出层级，说明设计错了。

## 2. 禁止清单（最容易写出"AI 感"的地方）

| 不要 | 改成 |
|---|---|
| 彩色小圆点表示状态（绿点在线、红点断开） | 直接写文字："已连接 / 未连接 / 连接中…" |
| 渐变背景、渐变按钮、渐变文字 | 纯色。主按钮纯黑 `#111` |
| 发光阴影、彩色阴影、大面积投影 | 只用很淡的黑色阴影，且只用于浮层（菜单、对话框） |
| 处处加边框、卡片套卡片 | 分组用灰底卡片 `#f7f7f7`，不加边框；只有表格卡片和主卡片有 1px 极淡描边 |
| 大色块提示条（蓝底白字、绿底白字） | 浅色底 + 深色字：错误 `#fdecea` + 红字，提醒 `--notice-bg` + `--warn` |
| **双层框**：同一个元素上既有边框/内圈又有焦点轮廓 | 焦点只留一圈：要么"换边框色 + 白底"，要么"一圈 outline"，两者不同时出现 |
| 在密集网格（日历格）上画轮廓表示光标/选中 | 用底色：悬停 `--hover-bg`、光标 `--sb-active`、选中 `#111` 白字，不画线 |
| 用浏览器原生控件外观（原生下拉弹层、日期面板、数字步进箭头） | 用 §6.12 的自绘控件 |
| UI 里放 emoji 当图标 | 内联 SVG 线性图标（见 §6.10） |
| 浏览器 `alert / confirm / prompt` | `UI.dialog / UI.confirm / UI.prompt / UI.toast`（见 §6.6） |
| 登录用弹窗盖在页面上 | 独立页面 `login.html` |
| 加载时显示转圈或"加载中…"，数据到了再跳成内容 | 骨架屏，形状与真实内容一致（见 §6.8） |
| 用户名等截断成固定字数（`name.slice(0,4)+"…"`） | 显示全名，CSS 省略号截断，完整名放 `title` |
| 一个区域里放多个黑色主按钮 | 每个区域最多一个主按钮，其余用灰色次按钮或蓝色文字按钮 |
| 紫色、青色等"科技感"配色 | 只用 §3 里的颜色 |

> 现有系统消息里的 `❌`（`addSystem("❌ …")`）是历史遗留，新代码不要再加 emoji。

## 3. 颜色

只用下面这些颜色。已有 CSS 变量的直接用变量（定义在 `index.css` 的 `:root`）。

### 底色与表面

| 用途 | 值 | 变量 |
|---|---|---|
| 页面底（应用外壳的侧栏与主区背景） | `#f9f8f6` 暖白 | `--ground` |
| 主卡片、对话框、菜单 | `#ffffff` | `--bg` / `--panel` |
| 输入框、次按钮 | `#f2f2f2`（hover `#ebebeb`） | — |
| 分组卡片（设置页） | `#f7f7f7`（hover `#efefef`） | `--admin-card` |
| 浅灰表面（用户气泡、输入托盘、代码块） | `#f5f5f5` | `--surface` |
| 悬停 | `rgba(0,0,0,0.04)` | `--hover-bg` / `--sb-hover` |
| 选中 | `rgba(0,0,0,0.06)` | `--sb-active` |
| 骨架条 | `rgba(0,0,0,0.05)` | — |
| 对话框遮罩 | `rgba(0,0,0,0.32)` | — |

### 文字（三级灰度，用来区分层级）

| 级别 | 值 | 变量 | 用于 |
|---|---|---|---|
| 主文字 | `rgba(0,0,0,0.9)` | `--text` | 正文、标题、列表项 |
| 次文字 | `rgba(0,0,0,0.6)` | `--text-dim` | 说明、对话框正文、次要按钮 |
| 弱文字 | `rgba(0,0,0,0.45)` | `--text-faint` | 分组小标题、表头、提示、时间 |

### 线

| 用途 | 值 |
|---|---|
| 主卡片描边 | `1px solid rgba(0,0,0,0.05)` |
| 卡片内分隔线 | `rgba(0,0,0,0.06)`（`--admin-line`） |
| 表格卡片 / 菜单描边 | `rgba(0,0,0,0.06 ~ 0.08)`（`--border`、`--admin-border`） |
| 输入框聚焦描边 | `rgba(0,0,0,0.16)` |
| 输入框校验失败 | `rgba(192,57,43,0.45)` |

### 有含义的颜色（只在需要表达含义时用）

| 含义 | 值 | 用法 |
|---|---|---|
| 主操作 | `#111`（hover `#000`） | 主按钮底色。旧代码 `.btn-primary`、`.round-btn` 用 `--accent: #1f1f1f`，视觉上等同 |
| 链接 / 文字操作 | `#1783ff` | `--link`；表格里的操作按钮、"查看明细"、"注册新账号" |
| 危险 | `#c0392b` | `--danger`；文字、删除确认按钮。浅底用 `#fdecea` |
| 正向（入账、正常） | `#2fb36d` | `--admin-green`；**只用于文字**，不做色块 |
| 提醒 | `#a9610a` + 底 `rgba(169,97,10,0.06)` | `--warn` / `--notice-bg`；登录页的"登录已过期"提示条 |

## 4. 字体与字号

```css
font-family: -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
```

| 字号 | 字重 | 用于 |
|---|---|---|
| 46px | 800 | 只用于首页字标 `SPRING HARNESS`（`#hero`），别处不用 |
| 24px / 32px 行高 | 600 | 独立页面（登录/注册）的主标题：页面上唯一的大标题，用了它就别再加别的层级 |
| 20px / 28px 行高 | 600 | 页面标题（`.page-title`）、账号名 |
| 17px / 24px | 600 | 对话框标题 |
| 16px | 400 | 聊天正文、聊天输入框（`--fs-*` 变量） |
| 15px | 400 | 大号主按钮（登录按钮） |
| 14px | 400 | **界面默认字号**：列表项、按钮、表格内容、菜单项、设置行 |
| 13px | 400 | 分组小标题、表头、托盘信息、表单标签、错误提示 |
| 12px | 400 | 字段提示、徽章、快捷键 `kbd`、行内说明 |

- 字重只用 400 / 500 / 600。500 只用于导航选中项和金额数字。
- 数字列加 `font-variant-numeric: tabular-nums`（`.num`），表格里数字右对齐。
- 标题不要加粗到 700+，也不要放大到 24px+（首页字标除外）。

## 5. 尺寸、圆角、间距

### 控件高度（同类控件高度统一）

| 高度 | 控件 |
|---|---|
| 28px | 表格内蓝色文字按钮（`.admin-btn`） |
| 32px | 图标按钮（`.sb-icon-btn`）、圆形发送按钮 |
| 34–36px | 普通按钮、筛选栏控件、快捷胶囊、对话框按钮（36） |
| 36px | 侧栏列表行（项目、会话） |
| 40px | 对话框输入框、导航项、菜单项、"新建会话"按钮 |
| 44px | 登录页输入框和主按钮、整宽按钮（`.wide-btn`）、底部用户行 |
| 52px | 设置分组行最小高度、顶栏 |

### 圆角（越大的容器圆角越大）

| 圆角 | 用于 |
|---|---|
| 4–5px | 徽章、`kbd` |
| 8px | 图标按钮、小文字按钮、菜单内条目 |
| 10px | 按钮、输入框、列表行、导航项 |
| 12px | 主卡片、分组卡片、表格卡片、积分卡、大号输入框 |
| 16px | 对话框、底部用户菜单、提问卡 |
| 18px | 用户消息气泡 |
| 20px | 计划面板 |
| 24px | 聊天输入卡片 |
| 999px | 胶囊：快捷提示、"最新消息"按钮、骨架条 |

### 内容宽度

| 宽度 | 用于 |
|---|---|
| 780px | 聊天内容与输入框（`--content-max`） |
| 600px | 设置类页面（账号、积分、系统设置） |
| 1080px | 宽表格页（`.admin-page.wide`） |
| 420px | 对话框 |
| 380px | 登录/注册这类独立页面的表单栏 |
| 240px | 侧栏 / 左侧导航 |

### 间距

- 基本按 4px 递增：列表内 2px，控件内间距 8–10px，组件之间 14–18px，分组之间 28px。
- 主卡片内边距：设置页 `48px 32px 72px`；对话框 `24px 24px 20px`。
- 宁可多留白，不要用分隔线把东西隔开。

## 6. 组件

### 6.1 页面骨架

所有登录后的页面都是同一个结构：**暖白底 + 240px 侧栏（无边框、无分隔线） + 右侧白色主卡片**。

```css
#app { display: flex; height: 100vh; background: var(--ground); }
#sidebar { width: 240px; flex-shrink: 0; padding: 0 8px; }
#main {
  flex: 1; min-width: 0;
  margin: 8px 8px 8px 0;              /* 主卡片四周留出底色 */
  border: 1px solid rgba(0, 0, 0, 0.05);
  border-radius: 12px;
  background: #fff;
}
```

- 侧栏顶部：28px 圆形 Logo（`/static/assets/images/log.png`）+ 收起按钮，高 56px。
- 侧栏分组小标题：13px 弱文字，`padding: 16px 8px 4px`。
- 侧栏列表行：36px 高、圆角 10px、hover `.04`、选中 `.06`。次要信息（大小、时间、删除按钮）**只在悬停时出现**，平时一行干净的名称。
- 侧栏可滚动区底部用 `mask-image` 渐隐 40px，不加分隔线。
- 设置类页面：主卡片内居中 600px 窄栏，依次是页面标题 → 分组小标题（`.section-caption`）→ 灰色分组卡片。

**独立页面**（登录/注册这类不在应用外壳里的页面）：**不套主卡片，直接是"页面"**——白底一整页，
品牌标钉在**左上角**当页头，表单是页面中间一条 380px 窄栏（只做水平居中），栏内全部**左对齐**；
没有白底面板、没有圆角、没有阴影。

```css
body.login-page { display: flex; flex-direction: column; min-height: 100vh; background: var(--bg); }
.login-topbar { display: flex; flex: 0 0 auto; align-items: center; gap: 10px; padding: 20px 24px; }
/* 表单从顶部固定距离开始往下排，不垂直居中：居中时登录 2 个字段、注册 3 个字段，
   切换模式标题会上下跳。17vh 让标题落在页面高度约 24% 处（参考图的比例），
   矮屏 64px 保底、高屏 200px 封顶 */
.login-wrap { flex: 1; padding: clamp(64px, 17vh, 200px) 24px 80px; }
.login-form { width: 100%; max-width: 380px; margin: 0 auto; text-align: left; }
```

顺序固定：页头（Logo 28px + 品牌名 16px/600）→ 24px 主标题 → "没有账号？注册"一行（弱文字 + 蓝色链接）→
字段（13px 标签在输入框**上方**）→ 错误位（预留高度，出错时按钮不跳）→ 整宽黑色主按钮。

- 字段的格式要求直接写进 placeholder（如"请输入用户名（2~64 个字符）"），不要另外加一行提示文字。

- 密码框右侧放显示/隐藏按钮（`.login-eye`，30px 方形图标按钮，隐藏时画带斜杠的眼睛）；
  切换登录/注册时把已显示的密码收回隐藏态。
- 表单独占一栏，主按钮 `display: block; width: 100%` —— 把表单从 flex 改回块级时容易漏掉这条。

### 6.2 按钮

| 类型 | 样式 | 何时用 |
|---|---|---|
| 主按钮 | 底 `#111`、白字、圆角 10px（大号 12px） | 每个区域最多一个：提交、保存、创建 |
| 次按钮 | 底 `#f2f2f2`、主文字、hover `#ebebeb` | 取消、查询以外的普通操作 |
| 文字按钮 | 透明底、`--link` 蓝字、hover `rgba(23,131,255,0.08)` | 表格行内操作（重置密码、设配额…） |
| 危险文字按钮 | 透明底、`--danger` 红字、hover `rgba(192,57,43,0.08)` | 表格行内的禁用、删除 |
| 危险实心按钮 | 底 `--danger`、白字 | **只用在**删除/禁用确认对话框的确认键 |
| 图标按钮 | 透明底、32×32、圆角 8px、`--text-dim`，hover 底 `.04` | 收起侧栏、关闭 |

- **按钮不加边框**（`button { border: 1px solid transparent }`，任何状态都不要把它显出来）、没有阴影、没有渐变。
  悬停/选中只变底色；"已打开"这类状态也用底色表达（如 `[aria-expanded="true"]`）。
- 键盘焦点给按钮画**一圈** `:focus-visible` outline（`2px solid rgba(23,131,255,0.4)`，`outline-offset: 1px`，与 `input.switch` 一致）；
  鼠标点击不显示焦点样式。不要用"边框变色 + 底变白"来表示按钮焦点——那是输入框的做法，会叠成双层框。
- 禁用状态 `opacity: 0.5 ~ 0.55`。

### 6.3 输入框

```css
.input {
  height: 40px;                         /* 登录页 44px */
  padding: 0 12px;
  border: 1px solid transparent;        /* 预留描边位置，聚焦时不跳动 */
  border-radius: 10px;                  /* 登录页 12px */
  background: #f2f2f2;
  font-size: 14px;
  outline: none;
  transition: border-color 0.15s, background-color 0.15s;
}
.input::placeholder { color: var(--text-faint); }
.input:focus   { border-color: rgba(0, 0, 0, 0.16); background: #fff; }
.input.invalid { border-color: rgba(192, 57, 43, 0.45); background: #fff; }
```

- 灰底、无边框。聚焦态按所在底色分两种写法，**两者不叠加**：
  - 输入框直接放在暖白/灰色背景上（登录页、对话框）：聚焦把灰底**加深一档**（`#f2f2f2` → `#ebebeb`），不画线。
  - 输入框放在灰色分组卡片里（设置页）：卡片内本来就是白底，聚焦改成白底 + `1px solid rgba(0,0,0,0.16)` 描边。
- **不要**用蓝色聚焦环或发光阴影。
- 放在灰色分组卡片里的输入框反过来用白底（`.group-card .settings-number { background: #fff }`）。
- 有单位的输入框在右侧放单位文字（MB、tokens），13px 弱文字。
- 开关用 `input.switch`：关闭时灰底 `rgba(0,0,0,0.15)`，打开时 `#111`。不要用绿色开关。
- 数字输入框不要原生步进箭头（`index.css` 里已全局去掉）。
- 下拉框和日期框不要用原生控件，见 §6.12。

### 6.4 卡片与列表

- **分组卡片**（设置项）：底 `#f7f7f7`、圆角 12px、左右 16px 内边距、无边框。行最小高 52px，行间分隔线 `rgba(0,0,0,0.06)`，分隔线跟随左右内边距内缩。左边是标签（14px 主文字，可带 12px 弱文字说明），右边是值、控件或蓝色链接。
- **表格卡片**：白底、`1px solid rgba(0,0,0,0.08)`、圆角 12px、横向可滚动。表头 13px 弱文字、字重 400；单元格 `padding: 13px 16px`，行线 `.06`，最后一行无线，hover 底 `rgba(0,0,0,0.015)`。
- **空状态**：表格里一行居中弱文字（"暂无用户"），`padding: 40px 16px`；列表里用 `.empty-tip`。用 `UI.emptyRow(tbody, text)`，不要手写 `colspan`。

### 6.5 徽章

12px 字、`line-height: 20px`、`padding: 0 6px`、圆角 4px。

- 站长：黑底白字 `#111`
- 管理员：浅蓝底 `rgba(23,131,255,0.1)` + 蓝字
- 普通用户 / "默认"：浅灰底 `rgba(0,0,0,0.05)` + 次文字

### 6.6 对话框与轻提示（`ui.js` + `ui.css`）

**所有需要输入或确认的地方都用 `UI.*`，禁止浏览器原生弹窗。**

```js
// 确认（危险操作）
const ok = await UI.confirm({
  title: "删除项目",
  message: `确定删除「${name}」吗？\n其工作区目录与全部会话数据会被物理删除，不可恢复。`,
  okText: "删除",
  danger: true,
  submit: () => api(`/api/works/${id}`, { method: "DELETE" }),  // 在框内提交，失败时错误显示在框内
});
if (!ok) return;
UI.toast("项目已删除");

// 单个输入
const value = await UI.prompt({
  title: "存储配额", message: "…", label: "配额", value: 1024, suffix: "MB",
  inputMode: "decimal",
  validate: (s) => (parseNonNegative(s) == null ? "请输入非负数字" : null),
  submit: (s) => post("quota", { quotaBytes: … }),
});
if (value === null) return;               // 用户取消

// 多个输入
const v = await UI.dialog({
  title: "重置密码",
  fields: [
    { name: "pwd",  label: "新密码",     type: "password", autocomplete: "new-password", hint: "至少 6 位" },
    { name: "pwd2", label: "确认新密码", type: "password", autocomplete: "new-password" },
  ],
  validate: (f) => f.pwd !== f.pwd2 ? { name: "pwd2", message: "两次输入的密码不一致" } : null,
  submit: (f) => post("password", { password: f.pwd }),
});
```

规则：

- **请求放进 `submit`**：失败时对话框不关，错误显示在框内，可以直接改了重试；成功才关闭。
- **校验放进 `validate`**：返回 `{ name, message }` 时对应输入框标红并获得焦点。
- 一次操作需要多个输入时放在**同一个**对话框里，不要连弹两次。
- 标题用动词短语（"删除项目"、"重置密码"）；正文说明后果，涉及对象用「」括起来；确认键写具体动作（"删除"、"创建"、"保存"），不写"确定"。
- 只有删除、禁用这类不可逆操作用 `danger: true`。
- 成功反馈用 `UI.toast("…")`（顶部居中白色胶囊，2.4 秒消失），失败反馈用 `UI.toast(msg, { type: "error" })`。不要把成功提示塞进聊天消息里。
- 对话框里按键不会冒泡到页面（Esc 不会触发"中断运行"，Ctrl+K 不会新建会话），新增页面级快捷键时不用另做判断。

### 6.7 浮层菜单

用户菜单、模型菜单这类弹出层：

```css
.menu {
  padding: 6px;
  background: #fff;
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 16px;                  /* 小菜单 12px */
  box-shadow: 0 10px 32px rgba(0, 0, 0, 0.1), 0 1px 3px rgba(0, 0, 0, 0.04);
  animation: pop-in 0.14s ease-out;
}
.menu-item:hover { background: rgba(0, 0, 0, 0.04); }
```

行高按用途分两档：

| 行高 | 圆角 | 用于 |
|---|---|---|
| 40px | 10px | 账号菜单（导航性质的几个入口） |
| 34px | 8px | 选项列表：模型菜单、下拉框选项（`.ui-option`） |

点击外部关闭；选中项前面用对勾图标，不用高亮色块。

### 6.8 骨架屏（样式 `ui.css` 的 `.sk`，辅助函数 `ui.js` 的 `UI.*`）

**凡是需要等接口的内容，都先用骨架占位，避免数据到达时布局跳动。**

```html
<span class="sk" style="--w:64%"></span>                       <!-- 默认 14px 高的胶囊条 -->
<span class="sk" style="--w:150px;--h:30px;--r:10px"></span>   <!-- 大数字 -->
<span class="sk" style="--w:36px;--h:36px;--r:50%"></span>     <!-- 头像 -->

<!-- 列表骨架：容器的直接子元素带 .sk-block，真实数据渲染时随容器清空一起消失 -->
<div id="my-list">
  <div class="sk-block sk-list sk-fade" aria-hidden="true">
    <div class="sk-row"><span class="sk" style="--w:72%"></span></div>
    <div class="sk-row"><span class="sk" style="--w:58%"></span></div>
    <div class="sk-row"><span class="sk" style="--w:44%"></span></div>
  </div>
</div>
```

```js
// 列表 / 区块：首屏骨架写在 HTML 里，脚本启动时记下，之后重新加载时复用
UI.saveSkeleton("my-list");       // 在真实数据到达前调用一次
UI.showSkeleton("my-list");       // 重新加载前：换回骨架
UI.clearSkeleton("my-list");      // 加载失败：移除骨架

// 表格：骨架按表头列数自动生成（10 行、宽度错落、数字列右对齐、末几行渐隐）
const rows = await UI.loadTable("user-tbody", () => api("/api/admin/users")) || [];
if (!rows.length) UI.emptyRow("user-tbody", "暂无用户");

// 页面加载失败：收起该页残留的所有骨架
loader().catch((e) => { UI.settleSkeletons(section); showError(e.message); });
```

| 函数 | 作用 |
|---|---|
| `UI.saveSkeleton(box)` | 记下 box 里的首屏骨架块（`:scope > .sk-block`） |
| `UI.showSkeleton(box)` | 用记下的骨架块替换 box 的内容 |
| `UI.clearSkeleton(box)` | 移除 box 里的骨架块 |
| `UI.tableSkeleton(tbody, rows = 10)` | 按表头列数铺骨架行 |
| `UI.emptyRow(tbody, text)` | 表体只留一行居中提示，自动计算 `colspan` |
| `UI.loadTable(tbody, fetcher)` | 表格加载：没有真实行时铺骨架，有数据时调淡旧行，失败时落成"加载失败"；返回 fetcher 的结果 |
| `UI.settleSkeletons(root)` | 表格骨架变成"加载失败"一行，骨架块换成提示，行内骨架条换成"-" |

参数都可以传元素或元素 id。

- 外观：浅灰 `rgba(0,0,0,0.05)` 圆角胶囊条，1.6 秒呼吸动画（`sk-pulse`），用户开启"减少动态效果"时不动。不要用扫光（shimmer）效果。
- **形状跟真实内容一致**：表格保留真实表头；侧栏行同样 36px 高（`.sk-row`）；消息区用户气泡靠右、助手段落左侧留头像位。
- 末尾几行渐隐：列表容器加 `.sk-fade`，表格骨架行是 `.sk-tr`（最后 3 行透明度分别为 0.75 / 0.5 / 0.28）。
- 骨架块必须带 `.sk-block` 并且是容器的**直接子元素**，`UI.*` 只认这个标记，不认页面专属的类名。
- 首屏骨架**直接写在 HTML 里**，JS 执行前就能显示；样式只在 HTML 维护一份，JS 通过 `saveSkeleton / showSkeleton` 克隆复用，不要在 JS 里再拼一份骨架。
- **刷新已有数据时不要整块换成骨架**，只把旧内容调淡（`.table-card.is-loading tbody { opacity: .5 }`，`UI.loadTable` 已处理）。
- **加载失败要收起骨架**，不能让骨架一直闪。
- 判断"是否为空"的逻辑要把骨架算作有内容（`syncEmpty` 的选择器包含 `.msg-skeleton`），否则加载中会先闪出空状态。
- 文字型占位（项目名、模型名）可以用 `:empty::before` 画骨架条，此时 JS 永远不能把它写成空字符串，没有值时写兜底文案（"未选择项目"、"默认模型"）。

### 6.9 状态与提示

- 状态用**文字**表达。需要颜色时只给文字上色：正常 / 入账用绿字，禁用 / 扣减用红字。不用圆点、不用色块。
- 页面级错误：顶部浅红条 `background: #fdecea; color: var(--danger); border-radius: 12px`（`#admin-error`）。
- 表单内错误：输入框下方 13px 红字，并把对应输入框标红。
- 中性提醒（如"登录已过期"）：`--notice-bg` 浅暖底 + `--warn` 字，圆角 10px。不要做得和输入框一样灰，否则会被当成输入框。

### 6.10 图标

- 内联 SVG，`viewBox="0 0 24 24"`，`fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"`；箭头这类小图标 `stroke-width="1.8"`。
- 尺寸：列表/菜单 16–18px，顶栏图标按钮 20px。颜色继承文字，列表行首图标用 `rgba(0,0,0,0.75)`。
- 线性风格，不用填充色块图标，不用 emoji，不引入图标库。

### 6.11 动效

| 场景 | 动效 |
|---|---|
| 悬停背景 | `transition: background-color 0.15s` |
| 输入框聚焦 | `border-color, background-color 0.15s` |
| 菜单弹出 | `pop-in 0.14s ease-out` |
| 对话框 | 遮罩 `ui-fade 0.16s`，卡片 `ui-pop 0.18s`（上移 6px + 缩放 0.98 → 1） |
| 切换页面 | `page-in 0.2s`（上移 4px 淡入） |
| 骨架 | `sk-pulse 1.6s` 呼吸 |

动效要短（≤ 0.3s）、位移小（≤ 6px），不要弹跳、旋转入场或视差。唯一的装饰性动效是"新建会话"按钮悬停时加号转 90°，不要再加别的。

### 6.12 下拉框与日期框（自绘，`UI.enhance`）

**不要直接用原生 `<select>` 和 `<input type="date">`**：它们的弹层由浏览器绘制，风格和页面完全对不上。
在 HTML 里照常写原生元素，然后在页面初始化时调一次 `UI.enhance()`，`ui.js` 会把它们换成自绘控件：

```html
<select id="usage-user" title="按用户筛选"><option value="">全部用户</option></select>
<input type="date" id="usage-from" title="起始日期（含）" data-placeholder="起始日期">
```

```js
UI.enhance();                      // 换成 root 内所有 select 与 input[type=date]，可重复调用
UI.enhanceSelect(sel);             // 只换一个下拉
UI.enhanceDate(inp);               // 只换一个日期框
```

- **原生元素留在 DOM 里，并且始终是唯一的值来源**：`el.value` 可读可写、`change` / `input` 事件照常触发、`innerHTML` 重建 `<option>` 后界面自动同步。所以页面代码不用改，也不会有两份状态。
- 下拉：点按钮或按 ↑/↓ 打开；方向键移动、Home/End 到首尾、输入字符定位、回车/空格选中、Esc 关闭并把焦点还给按钮。选中项在**左侧**用对勾标记，位置固定保留 16px，文字不会左右跳。
- 日期：遵守 `min` / `max`（越界的格子禁用，键盘和翻月会夹到边界那天），每周一开头、固定 6 行（翻月时高度不跳），底部「清除 / 今天」。方向键按天/周、PageUp/PageDown 按月、Home/End 到本周首尾，回车选中。
  日历格**只用底色**表达状态，不画轮廓线：悬停 `--hover-bg`、键盘光标 `--sb-active`、今天加粗、选中 `#111` 白字；禁用格子用 `--text-faint` + `opacity: .5`。
- 未选日期时显示 `data-placeholder`，否则显示 `YYYY-MM-DD`；未选状态文字压暗一档（`--text-faint`）。
- 浮层挂在 body 上用 `fixed` 定位，不会被滚动容器裁切；下方放不下时自动翻到上方；点外部、滚动页面、改变窗口大小都会关闭。
- 浮层里按 Esc 和方向键不会冒泡到页面（不会触发"中断运行"等快捷键）。
- 层级：页面浮层 10–60 < `.modal` 100 < 下拉/日历浮层 250 < 对话框 300 < 轻提示 400。
- 新增别的原生控件（多选、时间选择等）时，按同样的方式在 `ui.js` 里加增强函数并挂到 `window.UI`，不要在页面脚本里各写一份。

## 7. 交互约定

- **登录**：独立页面 `login.html`（`#register` 进入注册模式）。需要登录的页面在 `<head>` 里先检查 token，没有就 `location.replace` 到登录页，避免先闪出页面内容（见 §9 模板）。
- **被动登出**：接口 401 / WebSocket 4401 → `login.html?reason=expired`；4403 → `?reason=disabled`。需要回到原页面时带 `next=当前路径+hash`，登录页只接受本站 `/static/` 下的地址。
- **退出登录**：清除 `sh.token`、`sh.username`、`sh.role`、`sh.sessionId` 后跳登录页。
- **账户中心分页**：用 `#hash` 定位（`admin.html#points`），可以直接链接到某一页。
- **键盘**：Esc 关闭对话框 / 菜单；Enter 提交表单；对话框内 Tab 循环聚焦。
- **长文本**：单行省略号截断（`overflow: hidden; text-overflow: ellipsis; white-space: nowrap`），完整内容放 `title`。
- **响应式**：主站断点 760px，账户中心 820px（导航改为顶部横向滚动），登录页 480px。新组件至少在 400px 宽度下不溢出。

## 8. 代码约定

- **技术栈**：原生 HTML / CSS / JS，不引入框架和构建工具。页面由网关以 `/static/` 路径提供，所有资源用绝对路径 `/static/...`。
- **样式文件**：
  - `index.css`：设计变量 + 主站样式，**所有页面都要引入**
  - `ui.css` + `ui.js`：通用组件（对话框、轻提示、骨架屏、自绘下拉与日期），所有页面都要引入；
    新页面调一次 `UI.enhance()` 就能去掉原生控件外观；新的通用逻辑也放这里，不要在页面脚本里各写一份
  - `admin.css`、`login.css`：各页面专属样式
  - 新页面新建自己的 `xxx.css`，不要往 `index.css` 里堆页面专属样式
- **颜色**：优先用变量；必须写死时只用 §3 表里的值。
- **显隐**：用 `.hidden` 类（`display: none !important`）切换，不直接改 `style.display`。
- **用户数据**一律用 `textContent` 插入，不拼进 `innerHTML`（防 XSS）。对话框的 `title` / `message` 内部已用 `textContent`，可以直接传用户名。
- **注释**：中文，写"为什么"而不是"做了什么"（例："replaceState 改地址不触发 hashchange，避免刚显示的错误被清掉"）。
- **localStorage 键**：`sh.token`、`sh.username`、`sh.role`、`sh.sessionId`、`sh.workId`，与主站共用，不要另起名字。

## 9. 新页面模板

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>页面名 - Spring Harness</title>
  <script>
    /* 未登录先去登录页，登录后带回当前页 */
    try {
      if (!localStorage.getItem("sh.token")) {
        location.replace("/static/login.html?next=" + encodeURIComponent(location.pathname + location.hash));
      }
    } catch (e) { /* 存储不可用时交给页面脚本处理 */ }
  </script>
  <link rel="stylesheet" href="/static/index.css">
  <link rel="stylesheet" href="/static/ui.css">
  <link rel="stylesheet" href="/static/xxx.css">
</head>
<body>
  <div id="xxx-app"><!-- 暖白底 + 240px 侧栏 + 白色主卡片，见 §6.1 --></div>
  <script src="/static/ui.js"></script>
  <script src="/static/xxx.js"></script>
</body>
</html>
```

## 10. 交付前自检

- [ ] 没有彩色圆点、渐变、发光阴影、emoji 图标
- [ ] 没有双层框：焦点态要么只有一圈 outline，要么只有边框变色 + 白底，不叠加
- [ ] 没有浏览器原生控件外观：下拉/日期走 `UI.enhance`，数字框没有步进箭头
- [ ] 颜色都来自 §3；转成黑白截图后层级依然清楚
- [ ] 每个区域最多一个黑色主按钮
- [ ] 没有 `alert / confirm / prompt`，确认和输入都走 `UI.*`，请求放在 `submit` 里
- [ ] 需要等接口的内容都有骨架；骨架形状与真实内容一致；失败时骨架会收起；刷新不整块闪
- [ ] 数据到达前后布局不跳动（宽高相近）
- [ ] 用户输入的内容用 `textContent` 插入
- [ ] 1440px 和 400px 宽度下截图检查过：不溢出、不挤压、长文本有省略号
- [ ] Esc 能关掉新加的浮层，Tab 顺序合理
- [ ] 中文注释写清楚了"为什么"
