/* 通用界面组件：自绘对话框（替代浏览器 prompt / confirm / alert）、轻提示、骨架屏辅助函数。
   主站、账户中心、登录页共用，样式见 ui.css；设计规范见 style.md。

   ---- 对话框与提示 ----
   UI.confirm({ title, message, okText, danger, submit })   → Promise<boolean>
   UI.prompt({ title, message, label, value, type, suffix,
               hint, placeholder, validate, submit })        → Promise<string|null>
   UI.dialog({ title, message, fields, okText, danger,
               validate, submit })                           → Promise<values|null>
   UI.toast(message, { type: "error" })

   validate(values) 返回错误文案（或 { name, message } 指明出错字段），框内就地提示；
   submit(values) 为异步提交，抛错时错误显示在框内并保持打开，成功才关闭。

   ---- 骨架屏（参数可传元素或元素 id）----
   骨架块：容器里带 .sk-block 类的直接子元素，真实数据渲染时随容器清空一起消失。
   UI.saveSkeleton(box)              记下 box 里 HTML 首屏骨架块，供之后重新加载时复用
   UI.showSkeleton(box)              用记下的骨架块替换 box 内容
   UI.clearSkeleton(box)             移除 box 里的骨架块（加载失败时用）
   UI.tableSkeleton(tbody, rows=10)  按表头列数铺骨架行，宽度错落、末几行渐隐
   UI.emptyRow(tbody, text)          表体只留一行居中提示（暂无数据 / 加载失败）
   UI.loadTable(tbody, fetcher)      表格加载：无数据时铺骨架，有数据时调淡旧行；失败落成“加载失败”
   UI.settleSkeletons(root)          加载失败时收起 root 内残留的所有骨架

   ---- 表单控件（替代浏览器原生下拉与日期弹层）----
   UI.enhance(root = document)       把 root 内的 <select> 与 <input type="date"> 换成自绘控件
   UI.enhanceSelect(select)          单个下拉框
   UI.enhanceDate(input)             单个日期框（遵守 min / max；data-placeholder 为空值时的提示）
   原生元素保留在 DOM 里（隐藏）并始终是唯一的值来源：读写 .value、监听 change 都照旧，
   代码里直接给 .value 赋值或重建 <option> 时界面会自动同步。 */
(function () {
  "use strict";

  let seq = 0;

  function h(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function dialog(opts) {
    return new Promise((resolve) => {
      const fields = opts.fields || [];
      const prevFocus = document.activeElement;

      const overlay = h("div", "ui-dialog");
      const box = h("form", "ui-dialog-box");
      box.noValidate = true;
      box.tabIndex = -1;  // 点击框内空白处时焦点留在框内，Esc 等按键仍由对话框接管
      box.setAttribute("role", opts.danger ? "alertdialog" : "dialog");
      box.setAttribute("aria-modal", "true");

      const title = h("h3", "ui-dialog-title", opts.title || "");
      title.id = "ui-dialog-title-" + (++seq);
      box.setAttribute("aria-labelledby", title.id);
      box.appendChild(title);
      if (opts.message) box.appendChild(h("p", "ui-dialog-msg", opts.message));

      const inputs = {};
      for (const f of fields) {
        const wrap = h("label", "ui-field");
        if (f.label) wrap.appendChild(h("span", "ui-field-label", f.label));
        const control = h("span", "ui-control");
        const input = h("input", "ui-input");
        input.type = f.type || "text";
        input.name = f.name;
        input.spellcheck = false;
        if (f.value != null) input.value = String(f.value);
        if (f.placeholder) input.placeholder = f.placeholder;
        if (f.autocomplete) input.autocomplete = f.autocomplete;
        if (f.step != null) input.step = String(f.step);
        if (f.min != null) input.min = String(f.min);
        if (f.maxLength) input.maxLength = f.maxLength;
        if (f.inputMode) input.inputMode = f.inputMode;
        control.appendChild(input);
        if (f.suffix) {
          control.classList.add("has-suffix");
          control.appendChild(h("span", "ui-suffix", f.suffix));
        }
        // 字段内嵌按钮（如"获取验证码"）：悬浮在输入框右侧，可交互
        if (f.suffixBtn) {
          control.classList.add("has-suffix-btn");
          const btn = h("button", "ui-suffix-btn", f.suffixBtn.text || "");
          btn.type = "button";
          btn.addEventListener("click", () => f.suffixBtn.onClick(btn, input, inputs));
          control.appendChild(btn);
        }
        wrap.appendChild(control);
        if (f.hint) wrap.appendChild(h("span", "ui-field-hint", f.hint));
        box.appendChild(wrap);
        inputs[f.name] = input;
      }

      const error = h("div", "ui-dialog-error");
      error.setAttribute("role", "alert");
      box.appendChild(error);

      const actions = h("div", "ui-dialog-actions");
      const cancelBtn = h("button", "ui-btn", opts.cancelText || "取消");
      cancelBtn.type = "button";
      const okBtn = h("button", "ui-btn " + (opts.danger ? "ui-btn-danger" : "ui-btn-primary"), opts.okText || "确定");
      okBtn.type = "submit";
      actions.append(cancelBtn, okBtn);
      box.appendChild(actions);
      overlay.appendChild(box);

      let busy = false;
      const readValues = () => Object.fromEntries(Object.entries(inputs).map(([k, el]) => [k, el.value]));
      const showError = (msg, name) => {
        error.textContent = msg || "";
        for (const el of Object.values(inputs)) el.classList.remove("invalid");
        const target = name && inputs[name];
        if (target) { target.classList.add("invalid"); target.focus(); target.select?.(); }
      };
      const setBusy = (on) => {
        busy = on;
        overlay.classList.toggle("is-busy", on);
        okBtn.disabled = on;
        cancelBtn.disabled = on;
      };
      const close = (result) => {
        overlay.remove();
        if (prevFocus && typeof prevFocus.focus === "function" && document.contains(prevFocus)) prevFocus.focus();
        resolve(result);
      };

      // 框内按键不再冒泡到页面级快捷键（Esc 中断运行、Ctrl+K 新建会话等）
      overlay.addEventListener("keydown", (e) => {
        e.stopPropagation();
        if (e.key === "Escape") {
          e.preventDefault();
          if (!busy) close(null);
        } else if (e.key === "Tab") {
          const items = [...box.querySelectorAll("input, button")].filter((el) => !el.disabled);
          if (!items.length) return;
          const first = items[0];
          const last = items[items.length - 1];
          if (e.shiftKey && (document.activeElement === first || document.activeElement === box)) {
            e.preventDefault();
            last.focus();
          } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }
      });

      // 点遮罩关闭；按下与松开都在遮罩上才算，避免在框内拖选文字时误关
      let downOnBackdrop = false;
      overlay.addEventListener("mousedown", (e) => { downOnBackdrop = e.target === overlay; });
      overlay.addEventListener("click", (e) => {
        if (e.target === overlay && downOnBackdrop && !busy) close(null);
      });

      cancelBtn.onclick = () => { if (!busy) close(null); };
      box.addEventListener("input", () => { if (error.textContent) showError(""); });
      box.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (busy) return;
        const values = readValues();
        const invalid = opts.validate ? opts.validate(values) : null;
        if (invalid) {
          if (typeof invalid === "string") showError(invalid);
          else showError(invalid.message, invalid.name);
          return;
        }
        if (opts.submit) {
          setBusy(true);
          try {
            await opts.submit(values);
          } catch (err) {
            setBusy(false);
            showError((err && err.message) || String(err));
            return;
          }
        }
        close(values);
      });

      document.body.appendChild(overlay);
      const firstInput = fields.length ? inputs[fields[0].name] : null;
      if (firstInput) {
        firstInput.focus();
        if (firstInput.value) firstInput.select();
      } else {
        okBtn.focus();
      }
    });
  }

  function confirm(opts) {
    return dialog({ ...opts, fields: [], validate: null }).then((r) => r !== null);
  }

  function prompt(opts) {
    const field = {
      name: "value",
      label: opts.label,
      type: opts.type,
      value: opts.value,
      placeholder: opts.placeholder,
      hint: opts.hint,
      suffix: opts.suffix,
      autocomplete: opts.autocomplete,
      step: opts.step,
      min: opts.min,
      maxLength: opts.maxLength,
      inputMode: opts.inputMode,
    };
    return dialog({
      title: opts.title,
      message: opts.message,
      okText: opts.okText,
      cancelText: opts.cancelText,
      danger: opts.danger,
      fields: [field],
      validate: opts.validate ? (v) => opts.validate(v.value) : null,
      submit: opts.submit ? (v) => opts.submit(v.value) : null,
    }).then((r) => (r === null ? null : r.value));
  }

  function toast(message, opts = {}) {
    let host = document.querySelector(".ui-toasts");
    if (!host) {
      host = h("div", "ui-toasts");
      host.setAttribute("role", "status");
      host.setAttribute("aria-live", "polite");
      document.body.appendChild(host);
    }
    const item = h("div", "ui-toast" + (opts.type === "error" ? " error" : ""), message);
    host.appendChild(item);
    setTimeout(() => {
      item.classList.add("leaving");
      setTimeout(() => item.remove(), 200);
    }, opts.duration || 2400);
  }

  /* ================= 骨架屏 ================= */

  const SK_BLOCK = ":scope > .sk-block";
  /* 骨架条宽度轮换表：同一列各行宽度错开，看起来像长短不一的真实数据 */
  const SK_WIDTHS = [62, 44, 78, 52, 70, 38, 84, 56, 66, 48, 74, 58];
  const skeletonTpl = new WeakMap();

  const resolve = (x) => (typeof x === "string" ? document.getElementById(x) : x);
  const columnHeads = (tbody) => tbody.closest("table").tHead.rows[0].cells;

  /* 骨架样式只在 HTML 里维护一份：页面脚本启动时（真实数据到达前）先记下首屏骨架，
     之后切换项目/会话需要重新加载时克隆复用 */
  function saveSkeleton(box) {
    const el = resolve(box);
    const block = el && el.querySelector(SK_BLOCK);
    if (block) skeletonTpl.set(el, block.cloneNode(true));
  }

  function showSkeleton(box) {
    const el = resolve(box);
    const tpl = el && skeletonTpl.get(el);
    if (tpl) el.replaceChildren(tpl.cloneNode(true));
  }

  function clearSkeleton(box) {
    const el = resolve(box);
    if (el) el.querySelectorAll(SK_BLOCK).forEach((n) => n.remove());
  }

  function tableSkeleton(tbody, rows = 10) {
    const el = resolve(tbody);
    const heads = columnHeads(el);
    el.textContent = "";
    for (let r = 0; r < rows; r++) {
      const tr = h("tr", "sk-tr");
      tr.setAttribute("aria-hidden", "true");
      for (let c = 0; c < heads.length; c++) {
        const td = h("td", heads[c].className);  // 沿用表头对齐（数字列右对齐）
        const bar = h("span", "sk");
        bar.style.setProperty("--w", SK_WIDTHS[(r * 5 + c * 7) % SK_WIDTHS.length] + "%");
        td.appendChild(bar);
        tr.appendChild(td);
      }
      el.appendChild(tr);
    }
  }

  function emptyRow(tbody, text) {
    const el = resolve(tbody);
    const td = h("td", null, text);
    td.colSpan = columnHeads(el).length;
    const tr = h("tr", "empty-row");
    tr.appendChild(td);
    el.replaceChildren(tr);
  }

  /** 表里还没有真实行时铺骨架；已有数据的刷新只把旧行调淡（.table-card.is-loading），
      避免整表跳成骨架再跳回来。返回 fetcher 的结果，渲染由调用方紧接着完成 */
  async function loadTable(tbody, fetcher) {
    const el = resolve(tbody);
    const card = el.closest(".table-card");
    const hasRealRows = !!el.querySelector("tr:not(.sk-tr):not(.empty-row)");
    if (hasRealRows && card) card.classList.add("is-loading");
    else tableSkeleton(el);
    try {
      return await fetcher();
    } catch (e) {
      if (el.querySelector(".sk-tr")) emptyRow(el, "加载失败");
      throw e;
    } finally {
      if (card) card.classList.remove("is-loading");
    }
  }

  /** 表格骨架落成“加载失败”一行，骨架块换成提示，行内骨架条换成“-” */
  function settleSkeletons(root) {
    const el = resolve(root);
    if (!el) return;
    el.querySelectorAll("tbody").forEach((tb) => {
      if (tb.querySelector(".sk-tr")) emptyRow(tb, "加载失败");
    });
    el.querySelectorAll(".sk-block").forEach((n) => n.replaceWith(h("div", "empty-tip", "加载失败")));
    el.querySelectorAll(".sk").forEach((n) => n.replaceWith("-"));
  }

  /* ================= 浮层（下拉菜单、日历共用） ================= */

  const ICONS = {
    caret: '<path d="M6 9l6 6 6-6"/>',
    check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    prev: '<path d="M15 6l-6 6 6 6"/>',
    next: '<path d="M9 6l6 6-6 6"/>',
    calendar: '<rect x="3.5" y="5" width="17" height="15" rx="2.5"/><path d="M3.5 9.5h17M8 3v4M16 3v4"/>',
  };

  function icon(name, className) {
    const box = h("span", className);
    box.setAttribute("aria-hidden", "true");
    box.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ICONS[name]}</svg>`;
    return box;
  }

  let currentPop = null;  // 同一时间只开一个浮层

  /** 在 anchor 下方打开浮层（下方放不下时翻到上方）。挂在 body 上并用 fixed 定位，
      不会被滚动容器裁切；点外部、滚动页面、改变窗口大小都会关闭 */
  function openPopover(anchor, content, onClose) {
    closePopover();
    const pop = h("div", "ui-popover");
    pop.appendChild(content);
    document.body.appendChild(pop);

    const r = anchor.getBoundingClientRect();
    const gap = 6;
    const margin = 8;
    pop.style.minWidth = r.width + "px";
    const w = pop.offsetWidth;
    const ht = pop.offsetHeight;
    let top = r.bottom + gap;
    if (top + ht > innerHeight - margin && r.top - gap - ht >= margin) {
      top = r.top - gap - ht;
      pop.classList.add("above");
    }
    pop.style.top = top + "px";
    pop.style.left = Math.max(margin, Math.min(r.left, innerWidth - w - margin)) + "px";

    const onDown = (e) => {
      if (!pop.contains(e.target) && !anchor.contains(e.target)) closePopover();
    };
    const onScroll = (e) => { if (!pop.contains(e.target)) closePopover(); };
    const onResize = () => closePopover();
    document.addEventListener("pointerdown", onDown, true);
    document.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onResize);

    currentPop = {
      pop,
      close() {
        document.removeEventListener("pointerdown", onDown, true);
        document.removeEventListener("scroll", onScroll, true);
        window.removeEventListener("resize", onResize);
        pop.remove();
        if (onClose) onClose();
      },
    };
    return pop;
  }

  function closePopover() {
    const p = currentPop;
    currentPop = null;
    if (p) p.close();
  }

  /** 拦截元素实例上的 value 赋值：代码里直接写 el.value = … 时也能同步自绘界面 */
  function watchValue(el, proto, onSet) {
    const desc = Object.getOwnPropertyDescriptor(proto, "value");
    Object.defineProperty(el, "value", {
      configurable: true,
      get() { return desc.get.call(this); },
      set(v) { desc.set.call(this, v); onSet(); },
    });
  }

  /** 原生元素原地换成“隐藏原生 + 自绘按钮”，原生元素保留 id，仍是唯一的值来源 */
  function wrapNative(el, wrapClass, btn) {
    const wrap = h("span", wrapClass);
    el.replaceWith(wrap);
    wrap.append(el, btn);
    el.classList.add("ui-native");
    el.tabIndex = -1;
    el.setAttribute("aria-hidden", "true");
    if (el.title) { btn.title = el.title; btn.setAttribute("aria-label", el.title); }
    return wrap;
  }

  function emitChange(el) {
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  /* ================= 下拉框 ================= */

  function enhanceSelect(select) {
    if (select._uiEnhanced || select.multiple || select.size > 1) return;
    select._uiEnhanced = true;

    const btn = h("button", "ui-select-btn");
    btn.type = "button";
    btn.setAttribute("aria-haspopup", "listbox");
    btn.setAttribute("aria-expanded", "false");
    const label = h("span", "ui-select-label");
    btn.append(label, icon("caret", "ui-select-caret"));
    wrapNative(select, "ui-select", btn);

    const sync = () => {
      const opt = select.selectedOptions[0];
      label.textContent = opt ? opt.textContent : (select.dataset.placeholder || "");
      btn.disabled = select.disabled;
    };
    watchValue(select, HTMLSelectElement.prototype, sync);
    // 重建 <option>（如用户列表刷新）后同步显示
    new MutationObserver(sync).observe(select, { childList: true, subtree: true, characterData: true, attributes: true });
    select.addEventListener("change", sync);
    sync();

    const choose = (i) => {
      const changed = i !== select.selectedIndex;
      select.selectedIndex = i;
      sync();
      closePopover();
      btn.focus();
      if (changed) emitChange(select);
    };

    const open = () => {
      const list = h("div", "ui-listbox");
      list.setAttribute("role", "listbox");
      list.tabIndex = -1;
      const opts = [...select.options];
      const items = [];
      // 当前选中项若被禁用（或没有选中项），把键盘起点挪到第一个可选项
      let active = Math.max(0, select.selectedIndex);
      if (!opts[active] || opts[active].disabled) {
        const first = opts.findIndex((o) => !o.disabled);
        active = first >= 0 ? first : 0;
      }

      const setActive = (i, scroll) => {
        items[active]?.classList.remove("active");
        active = i;
        const item = items[active];
        if (!item) return;
        item.classList.add("active");
        list.setAttribute("aria-activedescendant", item.id);
        if (scroll) item.scrollIntoView({ block: "nearest" });
      };
      const step = (from, dir) => {
        for (let i = from + dir; i >= 0 && i < opts.length; i += dir) if (!opts[i].disabled) return i;
        return from;
      };

      opts.forEach((o, i) => {
        const item = h("div", "ui-option");
        item.id = "ui-option-" + (++seq);
        item.setAttribute("role", "option");
        item.setAttribute("aria-selected", String(i === select.selectedIndex));
        if (i === select.selectedIndex) item.classList.add("selected");
        if (o.disabled) { item.classList.add("disabled"); item.setAttribute("aria-disabled", "true"); }
        // 对勾在左侧、位置固定保留（与模型菜单的 .model-check 一致），选中项不靠色块区分
        const check = h("span", "ui-option-check");
        if (i === select.selectedIndex) check.appendChild(icon("check"));
        item.append(check, h("span", "ui-option-label", o.textContent));
        item.addEventListener("mousemove", () => { if (!o.disabled && active !== i) setActive(i); });
        item.addEventListener("click", () => { if (!o.disabled) choose(i); });
        items.push(item);
        list.appendChild(item);
      });

      // 键盘：上下移动、Home/End、Enter/空格选中、Esc 关闭；输入字符跳到对应开头的选项
      let typed = "";
      let typedTimer = null;
      list.addEventListener("keydown", (e) => {
        e.stopPropagation();
        if (e.key === "ArrowDown" || e.key === "ArrowUp") {
          e.preventDefault();
          setActive(step(active, e.key === "ArrowDown" ? 1 : -1), true);
        } else if (e.key === "Home" || e.key === "End") {
          e.preventDefault();
          setActive(e.key === "Home" ? step(-1, 1) : step(opts.length, -1), true);
        } else if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          if (!opts[active]?.disabled) choose(active);
        } else if (e.key === "Escape" || e.key === "Tab") {
          e.preventDefault();
          closePopover();
          btn.focus();
        } else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
          typed += e.key.toLowerCase();
          clearTimeout(typedTimer);
          typedTimer = setTimeout(() => { typed = ""; }, 600);
          // 先找当前项之后的（连续按同一字母可轮换），没有再从头找
          const after = opts.findIndex((o, i) => !o.disabled && i > active && o.textContent.toLowerCase().startsWith(typed));
          const fromTop = opts.findIndex((o) => !o.disabled && o.textContent.toLowerCase().startsWith(typed));
          const target = after >= 0 ? after : fromTop;
          if (target >= 0) setActive(target, true);
        }
      });

      btn.setAttribute("aria-expanded", "true");
      openPopover(btn, list, () => btn.setAttribute("aria-expanded", "false"));
      setActive(active, true);
      list.focus();
    };

    btn.addEventListener("click", () => {
      if (btn.getAttribute("aria-expanded") === "true") closePopover();
      else open();
    });
    btn.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); open(); }
    });
  }

  /* ================= 日期框 ================= */

  const WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"];
  const pad2 = (n) => String(n).padStart(2, "0");
  const toISO = (d) => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
  const fromISO = (s) => {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s || "");
    return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null;
  };
  const addDays = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
  const addMonths = (d, n) => {
    const t = new Date(d.getFullYear(), d.getMonth() + n, 1);
    const last = new Date(t.getFullYear(), t.getMonth() + 1, 0).getDate();
    return new Date(t.getFullYear(), t.getMonth(), Math.min(d.getDate(), last));
  };

  function enhanceDate(input) {
    if (input._uiEnhanced) return;
    input._uiEnhanced = true;

    const btn = h("button", "ui-date-btn");
    btn.type = "button";
    btn.setAttribute("aria-haspopup", "dialog");
    btn.setAttribute("aria-expanded", "false");
    const label = h("span", "ui-date-label");
    btn.append(label, icon("calendar", "ui-date-icon"));
    wrapNative(input, "ui-date", btn);

    const sync = () => {
      const has = !!fromISO(input.value);
      label.textContent = has ? input.value : (input.dataset.placeholder || "选择日期");
      btn.classList.toggle("has-value", has);
      btn.disabled = input.disabled;
    };
    watchValue(input, HTMLInputElement.prototype, sync);
    input.addEventListener("change", sync);
    sync();

    // 只比较 YYYY-MM-DD 字符串即可判断先后
    const allowed = (iso) => (!input.min || iso >= input.min) && (!input.max || iso <= input.max);

    const choose = (iso) => {
      const changed = iso !== input.value;
      input.value = iso;
      closePopover();
      btn.focus();
      if (changed) emitChange(input);
    };

    const open = () => {
      const todayISO = toISO(new Date());
      let focusDate = fromISO(input.value) || fromISO(allowed(todayISO) ? todayISO : (input.min || input.max)) || new Date();

      const cal = h("div", "ui-cal");
      cal.setAttribute("role", "dialog");
      cal.setAttribute("aria-label", btn.title || "选择日期");
      const head = h("div", "ui-cal-head");
      const prev = h("button", "ui-cal-nav");
      prev.type = "button";
      prev.setAttribute("aria-label", "上个月");
      prev.appendChild(icon("prev"));
      const title = h("span", "ui-cal-title");
      title.setAttribute("aria-live", "polite");
      const next = h("button", "ui-cal-nav");
      next.type = "button";
      next.setAttribute("aria-label", "下个月");
      next.appendChild(icon("next"));
      head.append(prev, title, next);

      const grid = h("div", "ui-cal-grid");
      grid.setAttribute("role", "grid");
      const foot = h("div", "ui-cal-foot");
      const clearBtn = h("button", "ui-cal-link", "清除");
      clearBtn.type = "button";
      const todayBtn = h("button", "ui-cal-link", "今天");
      todayBtn.type = "button";
      todayBtn.disabled = !allowed(todayISO);
      foot.append(clearBtn, todayBtn);
      cal.append(head, grid, foot);

      const render = (focus) => {
        const y = focusDate.getFullYear();
        const m = focusDate.getMonth();
        title.textContent = `${y}年${m + 1}月`;
        grid.textContent = "";
        for (const wd of WEEKDAYS) grid.appendChild(h("span", "ui-cal-wd", wd));
        // 周一开头，固定 6 行，切换月份时日历高度不跳
        const first = new Date(y, m, 1);
        const start = addDays(first, -((first.getDay() + 6) % 7));
        const selectedISO = input.value;
        const focusISO = toISO(focusDate);
        for (let i = 0; i < 42; i++) {
          const d = addDays(start, i);
          const iso = toISO(d);
          const day = h("button", "ui-cal-day", String(d.getDate()));
          day.type = "button";
          day.dataset.date = iso;
          day.tabIndex = iso === focusISO ? 0 : -1;
          if (d.getMonth() !== m) day.classList.add("out");
          if (iso === todayISO) day.classList.add("today");
          if (iso === selectedISO) { day.classList.add("selected"); day.setAttribute("aria-pressed", "true"); }
          day.disabled = !allowed(iso);
          day.setAttribute("aria-label", `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`);
          grid.appendChild(day);
        }
        if (focus) grid.querySelector(`[data-date="${focusISO}"]`)?.focus();
      };

      // 移到某天并把焦点落进网格。越出 min/max 就夹到边界那天：既不把焦点丢在禁用格上，
      // 也不会因为整月都不可选而一路翻到很远的地方
      const moveTo = (d) => {
        const iso = toISO(d);
        if (input.min && iso < input.min) d = fromISO(input.min) || d;
        else if (input.max && iso > input.max) d = fromISO(input.max) || d;
        focusDate = d;
        render(true);
      };

      prev.addEventListener("click", () => moveTo(addMonths(focusDate, -1)));
      next.addEventListener("click", () => moveTo(addMonths(focusDate, 1)));
      grid.addEventListener("click", (e) => {
        const day = e.target.closest(".ui-cal-day");
        if (day && !day.disabled) choose(day.dataset.date);
      });
      clearBtn.addEventListener("click", () => choose(""));
      todayBtn.addEventListener("click", () => choose(todayISO));

      // 键盘：方向键按天/周移动，PageUp/PageDown 按月，Home/End 到本周首尾，Enter 选中，Esc 关闭
      cal.addEventListener("keydown", (e) => {
        e.stopPropagation();
        if (e.key === "Escape") {
          e.preventDefault();
          closePopover();
          btn.focus();
          return;
        }
        if (!e.target.classList.contains("ui-cal-day")) return;
        const moves = {
          ArrowLeft: () => addDays(focusDate, -1),
          ArrowRight: () => addDays(focusDate, 1),
          ArrowUp: () => addDays(focusDate, -7),
          ArrowDown: () => addDays(focusDate, 7),
          PageUp: () => addMonths(focusDate, -1),
          PageDown: () => addMonths(focusDate, 1),
          Home: () => addDays(focusDate, -((focusDate.getDay() + 6) % 7)),
          End: () => addDays(focusDate, 6 - ((focusDate.getDay() + 6) % 7)),
        };
        // 回车/空格不在这里处理：日期是 <button>，浏览器会自己触发 click，走上面的选择逻辑
        if (moves[e.key]) {
          e.preventDefault();
          moveTo(moves[e.key]());
        }
      });
      // 焦点停在哪天就记住哪天（鼠标点了某天再用键盘也能接着走）
      grid.addEventListener("focusin", (e) => {
        const d = e.target.dataset && fromISO(e.target.dataset.date);
        if (d) focusDate = d;
      });

      render(false);
      btn.setAttribute("aria-expanded", "true");
      openPopover(btn, cal, () => btn.setAttribute("aria-expanded", "false"));
      // 焦点落在当前选中日；没有选中（或该日不可选）时落到今天，让方向键立刻可用
      const target = grid.querySelector(".ui-cal-day.selected") || grid.querySelector('.ui-cal-day[tabindex="0"]');
      (target && !target.disabled ? target : todayBtn).focus();
    };

    btn.addEventListener("click", () => {
      if (btn.getAttribute("aria-expanded") === "true") closePopover();
      else open();
    });
    btn.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); open(); }
    });
  }

  /** 把 root 内的原生下拉与日期框换成自绘控件；重复调用安全（已增强的会跳过） */
  function enhance(root = document) {
    const el = resolve(root);
    if (!el) return;
    el.querySelectorAll("select").forEach(enhanceSelect);
    el.querySelectorAll('input[type="date"]').forEach(enhanceDate);
  }

  window.UI = {
    dialog, confirm, prompt, toast,
    saveSkeleton, showSkeleton, clearSkeleton,
    tableSkeleton, emptyRow, loadTable, settleSkeletons,
    enhance, enhanceSelect, enhanceDate,
  };
})();
