/**
 * SproutPet - 小芽团子宠物
 * 支持动态交互（呼吸、眨眼、环顾、点击弹跳、爱心粒子）与静态休眠（单帧渲染、零 CPU 占用）
 */

(function (global) {
  const SIZE = 512; // 逻辑坐标基准

  // 配色方案（低饱和、柔和哑光）
  const C = {
    line: '#6f9a50',
    body: '#d4e8be',
    bodyShade: '#c1dba6',
    leaf: '#b0d38c',
    leafShade: '#9dc577',
    eye: '#3d2c22',
    blush: '246,148,162',
    tongue: '#ee9aa6',
    ground: '90,110,70',
  };

  // 共享颗粒噪点图案（磨砂质感），惰性单例
  let grainPattern = null;
  function getGrain(ctx) {
    if (grainPattern) return grainPattern;
    try {
      const n = 128;
      const off = document.createElement('canvas');
      off.width = off.height = n;
      const octx = off.getContext('2d');
      const img = octx.createImageData(n, n);
      for (let i = 0; i < img.data.length; i += 4) {
        const v = 128 + (Math.random() - 0.5) * 80;
        img.data[i] = img.data[i + 1] = img.data[i + 2] = v;
        img.data[i + 3] = 255;
      }
      octx.putImageData(img, 0, 0);
      grainPattern = ctx.createPattern(off, 'repeat');
      return grainPattern;
    } catch {
      return null;
    }
  }

  class SproutPet {
    constructor(canvas, options = {}) {
      this.canvas = canvas;
      this.ctx = canvas.getContext('2d');
      this.isDynamic = false;
      this.rafId = null;

      // 缩放基准配置：角色包围盒大约在 [70, 430]，通过自适应矩阵将团子居中撑满画布
      this.contentSpan = options.contentSpan || 390; 
      this.centerX = 256;
      this.centerY = 254;

      // 动画内部状态
      this.amp = typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches ? 0.3 : 1;
      this.PERIOD = 2.6; // 浮动周期（秒）
      this.lastT = null;
      this.now = 0;
      this.floatY = 0;

      // 眨眼
      this.BLINK = 0.2;
      this.nextBlink = 1.5;
      this.blinkStart = -1;
      this.doubleBlink = false;

      // 看右上角发呆
      this.LOOK_IN = 0.45;
      this.LOOK_HOLD = 1.6;
      this.LOOK_OUT = 0.5;
      this.nextLook = 3.5;
      this.lookStart = -1;
      this.look = 0;
      this.lookVel = 0;

      // 点击弹簧交互
      this.JOY_TIME = 1.0;
      this.MAX_HEARTS = 24;
      this.squash = 0;
      this.squashV = 0;
      this.pokeTime = -10;
      this.joyUntil = -10;
      this.joyLevel = 0;
      this.hearts = [];

      // 绑定指针与生命周期
      this._onPointerDown = this._onPointerDown.bind(this);
      this._onPointerMove = this._onPointerMove.bind(this);
      this._onKeyDown = this._onKeyDown.bind(this);
      this._onResize = this._onResize.bind(this);
      this._frame = this._frame.bind(this);

      this.resize();
      if (typeof ResizeObserver !== 'undefined') {
        this.ro = new ResizeObserver(() => this.resize());
        this.ro.observe(this.canvas);
      } else {
        window.addEventListener('resize', this._onResize);
      }

      if (options.interactive !== false) {
        this.setInteractive(true);
      } else {
        this.renderStatic();
      }
    }

    resize() {
      const dpr = window.devicePixelRatio || 1;
      const rect = this.canvas.getBoundingClientRect();
      const w = Math.round((rect.width || 36) * dpr);
      const h = Math.round((rect.height || 36) * dpr);
      if (w > 0 && h > 0 && (this.canvas.width !== w || this.canvas.height !== h)) {
        this.canvas.width = w;
        this.canvas.height = h;
        if (!this.isDynamic) {
          this.renderStatic();
        }
      }
    }

    _onResize() {
      this.resize();
    }

    setInteractive(interactive) {
      if (this.isDynamic === interactive) return;
      this.isDynamic = interactive;

      if (interactive) {
        this.canvas.tabIndex = 0;
        this.canvas.setAttribute('role', 'button');
        this.canvas.setAttribute('aria-label', '小芽团子，点击戳它一下');
        this.canvas.addEventListener('pointerdown', this._onPointerDown);
        this.canvas.addEventListener('pointermove', this._onPointerMove);
        this.canvas.addEventListener('keydown', this._onKeyDown);
        this.canvas.classList.add('is-active-pet');
        this.canvas.classList.remove('is-static-pet');

        this.lastT = null;
        if (!this.rafId) {
          this.rafId = requestAnimationFrame(this._frame);
        }
      } else {
        this.canvas.removeAttribute('tabIndex');
        this.canvas.removeAttribute('role');
        this.canvas.removeAttribute('aria-label');
        this.canvas.removeEventListener('pointerdown', this._onPointerDown);
        this.canvas.removeEventListener('pointermove', this._onPointerMove);
        this.canvas.removeEventListener('keydown', this._onKeyDown);
        this.canvas.style.cursor = 'default';
        this.canvas.classList.remove('is-active-pet');
        this.canvas.classList.add('is-static-pet');

        if (this.rafId) {
          cancelAnimationFrame(this.rafId);
          this.rafId = null;
        }
        this.renderStatic();
      }
    }

    // ---------- 几何与部件绘制 ----------

    applyGrain(pathFn, strength) {
      const g = getGrain(this.ctx);
      if (!g) return;
      const ctx = this.ctx;
      ctx.save();
      pathFn(ctx);
      ctx.clip();
      ctx.globalCompositeOperation = 'overlay';
      ctx.globalAlpha = strength;
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, SIZE, SIZE);
      ctx.restore();
    }

    bodyPath(ctx) {
      ctx.beginPath();
      ctx.moveTo(256, 172);
      ctx.bezierCurveTo(332, 172, 387, 226, 387, 294);
      ctx.bezierCurveTo(387, 362, 330, 404, 256, 404);
      ctx.bezierCurveTo(182, 404, 125, 362, 125, 294);
      ctx.bezierCurveTo(125, 226, 180, 172, 256, 172);
      ctx.closePath();
    }

    drawBody() {
      const ctx = this.ctx;
      this.bodyPath(ctx);
      const g = ctx.createRadialGradient(236, 262, 0, 236, 262, 176);
      g.addColorStop(0, C.body);
      g.addColorStop(0.7, C.body);
      g.addColorStop(1, C.bodyShade);
      ctx.fillStyle = g;
      ctx.fill();

      ctx.save();
      this.bodyPath(ctx);
      ctx.clip();
      const l = ctx.createRadialGradient(190, 222, 0, 190, 222, 70);
      l.addColorStop(0, 'rgba(255,255,255,0.32)');
      l.addColorStop(1, 'rgba(255,255,255,0)');
      ctx.fillStyle = l;
      ctx.fillRect(110, 160, 170, 140);
      ctx.restore();

      this.applyGrain((c) => this.bodyPath(c), 0.14);

      this.bodyPath(ctx);
      ctx.lineWidth = 4;
      ctx.strokeStyle = C.line;
      ctx.stroke();
    }

    drawStem() {
      const ctx = this.ctx;
      ctx.beginPath();
      ctx.moveTo(240, 182);
      ctx.quadraticCurveTo(235, 166, 238, 150);
      ctx.lineCap = 'round';
      ctx.strokeStyle = C.line;
      ctx.lineWidth = 9;
      ctx.stroke();
      ctx.strokeStyle = C.leaf;
      ctx.lineWidth = 4;
      ctx.stroke();
    }

    leafPath(ctx, len, w) {
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.bezierCurveTo(len * 0.15, -w, len * 0.7, -w, len, 0);
      ctx.bezierCurveTo(len * 0.7, w, len * 0.15, w, 0, 0);
      ctx.closePath();
    }

    drawLeaf(bx, by, tx, ty, w, sway, shadeSide) {
      const ctx = this.ctx;
      const len = Math.hypot(tx - bx, ty - by);
      ctx.save();
      ctx.translate(bx, by);
      ctx.rotate(Math.atan2(ty - by, tx - bx) + sway);

      this.leafPath(ctx, len, w);
      ctx.fillStyle = C.leaf;
      ctx.fill();

      ctx.save();
      this.leafPath(ctx, len, w);
      ctx.clip();
      ctx.fillStyle = C.leafShade;
      ctx.fillRect(0, shadeSide > 0 ? 0 : -w, len, w);
      ctx.restore();

      this.applyGrain((c) => this.leafPath(c, len, w), 0.12);

      this.leafPath(ctx, len, w);
      ctx.lineWidth = 4;
      ctx.lineJoin = 'round';
      ctx.strokeStyle = C.line;
      ctx.stroke();
      ctx.restore();
    }

    drawEye(x, y, closed) {
      const ctx = this.ctx;
      if (closed > 0.8) {
        ctx.beginPath();
        ctx.moveTo(x - 12, y + 3);
        ctx.quadraticCurveTo(x, y + 9, x + 12, y + 3);
        ctx.lineWidth = 4;
        ctx.lineCap = 'round';
        ctx.strokeStyle = C.eye;
        ctx.stroke();
        return;
      }
      ctx.save();
      ctx.translate(x, y + closed * 5);
      ctx.scale(1, 1 - closed);
      ctx.fillStyle = C.eye;
      ctx.beginPath();
      ctx.ellipse(0, 0, 14, 16, 0, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = 'rgba(255,255,255,0.95)';
      ctx.beginPath();
      ctx.arc(-4, -5.5, 4.2, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    drawHappyEye(x, y) {
      const ctx = this.ctx;
      ctx.beginPath();
      ctx.moveTo(x - 12, y + 4);
      ctx.quadraticCurveTo(x, y - 14, x + 12, y + 4);
      ctx.lineWidth = 4.5;
      ctx.lineCap = 'round';
      ctx.strokeStyle = C.eye;
      ctx.stroke();
    }

    drawMouth() {
      const ctx = this.ctx;
      ctx.beginPath();
      ctx.moveTo(240, 281);
      ctx.quadraticCurveTo(246, 292, 254, 284);
      ctx.quadraticCurveTo(262, 292, 268, 281);
      ctx.lineWidth = 3.5;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.strokeStyle = C.eye;
      ctx.stroke();
    }

    openMouthPath(ctx) {
      ctx.beginPath();
      ctx.moveTo(243, 281);
      ctx.quadraticCurveTo(254, 279, 265, 281);
      ctx.quadraticCurveTo(264, 297, 254, 297);
      ctx.quadraticCurveTo(244, 297, 243, 281);
      ctx.closePath();
    }

    drawOpenMouth() {
      const ctx = this.ctx;
      this.openMouthPath(ctx);
      ctx.fillStyle = C.eye;
      ctx.fill();
      ctx.save();
      this.openMouthPath(ctx);
      ctx.clip();
      ctx.fillStyle = C.tongue;
      ctx.beginPath();
      ctx.ellipse(254, 297, 7, 5, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    drawBlush(x, y, alpha) {
      const ctx = this.ctx;
      ctx.save();
      ctx.translate(x, y);
      ctx.scale(1, 0.6);
      const g = ctx.createRadialGradient(0, 0, 0, 0, 0, 22);
      g.addColorStop(0, `rgba(${C.blush},${0.55 * alpha})`);
      g.addColorStop(0.65, `rgba(${C.blush},${0.55 * alpha})`);
      g.addColorStop(1, `rgba(${C.blush},0)`);
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(0, 0, 22, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    drawShadow(k, spread) {
      const ctx = this.ctx;
      const rx = 118 * (1 - 0.12 * k) * spread;
      ctx.save();
      ctx.translate(256, 418);
      ctx.scale(1, 12 / rx);
      const g = ctx.createRadialGradient(0, 0, 0, 0, 0, rx);
      const a = 0.15 - 0.05 * k;
      g.addColorStop(0, `rgba(${C.ground},${a})`);
      g.addColorStop(0.75, `rgba(${C.ground},${a})`);
      g.addColorStop(1, `rgba(${C.ground},0)`);
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(0, 0, rx, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    heartPath(ctx, s) {
      ctx.save();
      ctx.scale(s / 55, s / 55);
      ctx.translate(-75, -72);
      ctx.beginPath();
      ctx.moveTo(75, 40);
      ctx.bezierCurveTo(75, 37, 70, 25, 50, 25);
      ctx.bezierCurveTo(20, 25, 20, 62.5, 20, 62.5);
      ctx.bezierCurveTo(20, 80, 40, 102, 75, 120);
      ctx.bezierCurveTo(110, 102, 130, 80, 130, 62.5);
      ctx.bezierCurveTo(130, 62.5, 130, 25, 100, 25);
      ctx.bezierCurveTo(85, 25, 75, 37, 75, 40);
      ctx.closePath();
      ctx.restore();
    }

    // ---------- 交互与状态更新 ----------

    blinkAmount(t) {
      if (this.blinkStart < 0 && t >= this.nextBlink) this.blinkStart = t;
      if (this.blinkStart < 0) return 0;

      const p = (t - this.blinkStart) / this.BLINK;
      if (p >= 1) {
        this.blinkStart = -1;
        if (this.doubleBlink) {
          this.doubleBlink = false;
          this.nextBlink = t + 0.12;
        } else {
          this.nextBlink = t + 2 + Math.random() * 3.5;
          this.doubleBlink = Math.random() < 0.25;
        }
        return 0;
      }
      return p < 0.35 ? p / 0.35 : 1 - (p - 0.35) / 0.65;
    }

    lookAmount(t) {
      const ease = (x) => x * x * (3 - 2 * x);
      if (this.lookStart < 0 && t >= this.nextLook) this.lookStart = t;
      if (this.lookStart < 0) return 0;

      const p = t - this.lookStart;
      if (p < this.LOOK_IN) return ease(p / this.LOOK_IN);
      if (p < this.LOOK_IN + this.LOOK_HOLD) return 1;
      if (p < this.LOOK_IN + this.LOOK_HOLD + this.LOOK_OUT) {
        return ease(1 - (p - this.LOOK_IN - this.LOOK_HOLD) / this.LOOK_OUT);
      }
      this.lookStart = -1;
      this.nextLook = t + 5 + Math.random() * 4;
      if (this.blinkStart < 0 && Math.random() < 0.5) this.nextBlink = t + 0.1;
      return 0;
    }

    updateSquash(dt) {
      const K = 300, D = 12, steps = 2;
      const h = dt / steps;
      for (let i = 0; i < steps; i++) {
        this.squashV += (-K * this.squash - D * this.squashV) * h;
        this.squash += this.squashV * h;
      }
    }

    spawnHearts() {
      const n = 3 + Math.floor(Math.random() * 3);
      for (let i = 0; i < n && this.hearts.length < this.MAX_HEARTS; i++) {
        const side = i % 2 ? 1 : -1;
        const a = -Math.PI / 2 + side * (0.7 + Math.random() * 0.6);
        const r = 145;
        const speed = 70 + Math.random() * 50;
        this.hearts.push({
          x: 256 + Math.cos(a) * r,
          y: 300 + this.floatY + Math.sin(a) * r,
          vx: Math.cos(a) * speed,
          vy: Math.sin(a) * speed - 30,
          size: 9 + Math.random() * 5,
          rot: (Math.random() - 0.5) * 0.6,
          age: 0,
          life: 1.1 + Math.random() * 0.4,
        });
      }
    }

    updateHearts(dt) {
      for (let i = this.hearts.length - 1; i >= 0; i--) {
        const h = this.hearts[i];
        h.age += dt;
        if (h.age >= h.life) { this.hearts.splice(i, 1); continue; }
        h.x += h.vx * dt;
        h.y += h.vy * dt;
        h.vx *= 1 - dt * 2;
        h.vy *= 1 - dt * 1.2;
      }
    }

    drawHearts() {
      const ctx = this.ctx;
      for (const h of this.hearts) {
        const pop = Math.min(1, h.age / 0.18);
        const scale = pop < 1 ? pop * (1.25 - 0.25 * pop) : 1;
        const fade = Math.min(1, (h.life - h.age) / 0.4);
        ctx.save();
        ctx.translate(h.x, h.y);
        ctx.rotate(h.rot + Math.sin(h.age * 5) * 0.12);
        ctx.globalAlpha = 0.88 * fade;
        this.heartPath(ctx, h.size * scale);
        ctx.fillStyle = `rgb(${C.blush})`;
        ctx.fill();
        ctx.restore();
      }
    }

    poke() {
      const t = this.now || performance.now() / 1000;
      this.squashV = 9 * this.amp;
      this.pokeTime = t;
      this.joyUntil = t + this.JOY_TIME;
      this.spawnHearts();
      this.lookStart = -1;
      this.nextLook = t + 4 + Math.random() * 3;
    }

    toLogical(e) {
      const r = this.canvas.getBoundingClientRect();
      const scale = this.contentSpan / Math.min(r.width, r.height);
      const px = e.clientX - r.left;
      const py = e.clientY - r.top;
      return {
        x: this.centerX + (px - r.width / 2) * scale,
        y: this.centerY + (py - r.height / 2) * scale,
      };
    }

    hitTest(pos) {
      const y = pos.y - this.floatY;
      const dx = (pos.x - 256) / 136;
      const dy = (y - 288) / 120;
      if (dx * dx + dy * dy <= 1.05) return true;
      return pos.x > 140 && pos.x < 305 && y > 80 && y < 185;
    }

    _onPointerDown(e) {
      if (this.hitTest(this.toLogical(e))) {
        this.poke();
      }
    }

    _onPointerMove(e) {
      if (this.hitTest(this.toLogical(e))) {
        this.canvas.style.cursor = 'pointer';
      } else {
        this.canvas.style.cursor = 'default';
      }
    }

    _onKeyDown(e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        this.poke();
      }
    }

    applyViewTransform() {
      const ctx = this.ctx;
      const w = this.canvas.width;
      const h = this.canvas.height;
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, w, h);

      // 自适应居中缩放：让 390 的内容跨度优雅填充 avatar
      const scale = Math.min(w, h) / this.contentSpan;
      ctx.translate(w / 2, h / 2);
      ctx.scale(scale, scale);
      ctx.translate(-this.centerX, -this.centerY);
    }

    /**
     * 核心渲染管线：无论静态帧还是动态帧，共享完全一致的身体与部件绘制逻辑
     */
    _drawScene(state) {
      const {
        floatY = 0,
        look = 0,
        sx = 1,
        sy = 1,
        sway = 0,
        joy = false,
        blink = 0,
        joyLevel = 0,
        shadowK = 0.5,
        shadowSpread = 1,
      } = state;

      this.applyViewTransform();
      this.drawShadow(shadowK, shadowSpread);

      const ctx = this.ctx;
      ctx.save();
      ctx.translate(256, 404 + floatY);
      ctx.rotate(look * 0.045 * this.amp);
      ctx.scale(sx, sy);
      ctx.translate(-256, -404);

      // 小芽
      ctx.save();
      ctx.translate(240, 178);
      ctx.rotate(sway);
      ctx.translate(-240, -178);
      this.drawStem();
      this.drawLeaf(236, 152, 150, 128, 29, (Math.sin(2.1) * 0.05) * this.amp, -1);
      this.drawLeaf(240, 150, 298, 90, 24, (Math.sin(3.1) * 0.06) * this.amp, 1);
      ctx.restore();

      // 身体
      this.drawBody();

      // 五官
      const lx = look * 10;
      const ly = -look * 7;
      const blushAlpha = 0.95 * (1 + 0.6 * joyLevel);
      this.drawBlush(178 + lx * 0.6, 296 + ly * 0.6, blushAlpha);
      this.drawBlush(330 + lx * 0.6, 296 + ly * 0.6, blushAlpha);

      if (joy) {
        this.drawHappyEye(207 + lx, 268 + ly);
        this.drawHappyEye(299 + lx, 268 + ly);
      } else {
        this.drawEye(207 + lx, 268 + ly, blink);
        this.drawEye(299 + lx, 268 + ly, blink);
      }

      ctx.save();
      ctx.translate(lx * 0.75, ly * 0.75);
      if (joy) this.drawOpenMouth(); else this.drawMouth();
      ctx.restore();

      ctx.restore();

      if (this.hearts.length > 0) {
        this.drawHearts();
      }
    }

    /**
     * 静态帧渲染：中立舒展姿态，单次绘制，无持续动画损耗
     */
    renderStatic() {
      if (!this.canvas.width || !this.canvas.height) this.resize();
      if (!this.canvas.width || !this.canvas.height) return;

      this._drawScene({
        floatY: 0,
        look: 0,
        sx: 1,
        sy: 1,
        sway: 0,
        joy: false,
        blink: 0,
        joyLevel: 0,
        shadowK: 0.5,
        shadowSpread: 1,
      });
    }

    /**
     * 动态主循环
     */
    _frame(ms) {
      if (!this.isDynamic) return;

      const t = ms / 1000;
      const dt = this.lastT === null ? 0 : Math.min(t - this.lastT, 1 / 30);
      this.lastT = t;
      this.now = t;

      this.updateSquash(dt);
      this.updateHearts(dt);
      const joy = t < this.joyUntil;
      this.joyLevel += ((joy ? 1 : 0) - this.joyLevel) * Math.min(1, dt * 10);

      const prevLook = this.look;
      this.look += (this.lookAmount(t) - this.look) * Math.min(1, dt * 12);
      this.lookVel = dt > 0 ? (this.look - prevLook) / dt : 0;

      const w = (Math.PI * 2) / this.PERIOD;
      const ph = Math.sin(t * w);
      this.floatY = -ph * 9 * this.amp;
      const breath = Math.sin(t * w - 0.5);
      const sx = 1 - breath * 0.03 * this.amp + this.squash * 0.16;
      const sy = 1 + breath * 0.035 * this.amp - this.squash * 0.16 + this.look * 0.015;

      const since = t - this.pokeTime;
      const wiggle = since < 1.5 ? Math.exp(-since * 4) * Math.sin(since * 22) * 0.22 : 0;
      const lag = Math.max(-0.12, Math.min(0.12, -this.lookVel * 0.05));
      const sway = (Math.sin(t * w - 1.2) * 0.07 + wiggle + lag) * this.amp;

      this._drawScene({
        floatY: this.floatY,
        look: this.look,
        sx,
        sy,
        sway,
        joy,
        blink: this.blinkAmount(t),
        joyLevel: this.joyLevel,
        shadowK: (ph + 1) / 2,
        shadowSpread: 1 + this.squash * 0.12,
      });

      this.rafId = requestAnimationFrame(this._frame);
    }

    destroy() {
      this.setInteractive(false);
      if (this.ro) {
        this.ro.disconnect();
      } else {
        window.removeEventListener('resize', this._onResize);
      }
    }
  }

  // 全局管理器：管理所有消息气泡中的宠物实例，保证同一时刻仅有“最新一条”为动态可交互
  const SproutManager = {
    _pets: new Set(),
    _activePet: null,

    register(canvas, isDynamic = false) {
      const pet = new SproutPet(canvas, { interactive: isDynamic });
      this._pets.add(pet);
      if (isDynamic) {
        this.setActive(pet);
      }
      return pet;
    },

    setActive(pet) {
      if (this._activePet && this._activePet !== pet) {
        this._activePet.setInteractive(false);
      }
      this._activePet = pet;
      if (pet && !pet.isDynamic) {
        pet.setInteractive(true);
      }
    },

    makeAllStatic() {
      for (const pet of this._pets) {
        pet.setInteractive(false);
      }
      this._activePet = null;
    },

    unregister(pet) {
      if (this._activePet === pet) {
        this._activePet = null;
      }
      this._pets.delete(pet);
      pet.destroy();
    },

    clear() {
      for (const pet of this._pets) {
        pet.destroy();
      }
      this._pets.clear();
      this._activePet = null;
    }
  };

  global.SproutPet = SproutPet;
  global.SproutManager = SproutManager;
})(typeof window !== 'undefined' ? window : this);
