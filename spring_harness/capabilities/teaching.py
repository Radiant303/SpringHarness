from __future__ import annotations

import inspect
import sqlite3
import threading
from collections.abc import Awaitable, Callable
from datetime import datetime
from enum import Enum
from pathlib import Path
from uuid import uuid4

import anyio.to_thread
import yaml
from pydantic import BaseModel, Field
from pydantic_ai.toolsets import FunctionToolset

TEACHING_DB = "teaching.db"
TEACHING_DIR = "teaching"


class Mastery(str, Enum):
    """验收等级：D1 会做 / D2 会讲 / D3 会迁移（严格程度递增，按序比较）。"""

    D1 = "D1"
    D2 = "D2"
    D3 = "D3"


# 给等级配数字，方便比大小（"只升不降"规则要用）
_MASTERY_ORDER = {Mastery.D1: 1, Mastery.D2: 2, Mastery.D3: 3}


class ZoneKind(str, Enum):
    """三区划分：AI 代劳区 / 协作区 / 人类必做区。"""

    agent = "agent"
    cowork = "cowork"
    human = "human"


class UnitStatus(str, Enum):
    active = "active"
    closed = "closed"


class Objective(BaseModel):
    """学习目标：可观察、可验收的能力点。"""

    id: str = Field(description="目标 id，如 OBJ-1")
    text: str = Field(description="能力点描述，须可观察可验收")
    mastery_required: Mastery = Field(description="要求达到的验收等级")
    mastery_achieved: Mastery | None = Field(default=None, description="已达成的验收等级")


class Zone(BaseModel):
    """人机分工边界的一个区域条目。"""

    kind: ZoneKind = Field(description="区域类型")
    scope: str = Field(description="范围：路径/glob 或领域描述，如 src/borrowing/*.rs")
    note: str = Field(default="", description="该区域覆盖什么工作")
    serves: list[str] = Field(default_factory=list, description="该区域服务的 objective id 列表")


class HintEvent(BaseModel):
    """一次提示升级留痕：提示有价，逐级解锁。"""

    objective_id: str
    level: int = Field(description="提示级别 1-3：L1 指方向 / L2 给结构 / L3 给对照")
    attempt: str = Field(description="学习者在当前级的真实尝试记录（升级前提）")
    at: datetime = Field(default_factory=datetime.now)


def _new_id() -> str:
    """生成单元的随机 id（8 位十六进制）。"""
    return uuid4().hex[:8]


class TeachingUnit(BaseModel):
    """一个教学单元：spec 的结构化形态，跨会话存活。"""

    id: str = Field(default_factory=_new_id)
    slug: str = Field(description="文件系统安全标识，如 rust-ownership")
    title: str
    status: UnitStatus = UnitStatus.active
    version: int = 1
    objectives: list[Objective]
    zones: list[Zone]
    hint_max_level: int = Field(default=3, description="本单元允许的最高提示级别（1-3）")
    tests_root: str = Field(default="", description="测试套件所在目录，版本内冻结")
    hints: list[HintEvent] = Field(default_factory=list)
    changelog: list[str] = Field(default_factory=list, description="版本变更记录（改测试的前置审计）")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


# 单元变更回调的形状：吃一个 TeachingUnit、返回 None 或可等待的 None 的函数
OnTeachingChange = Callable[[TeachingUnit], "None | Awaitable[None]"]


def _now() -> datetime:
    return datetime.now()


def _is_slug_char(ch: str, allow_dash: bool) -> bool:
    """判断单个字符是不是 slug 的合法字符（小写字母/数字，可选连字符）。"""
    if "a" <= ch and ch <= "z":
        return True
    if "0" <= ch and ch <= "9":
        return True
    if allow_dash and ch == "-":
        return True
    return False


def _is_valid_slug(slug: str) -> bool:
    """slug 规则：小写字母或数字开头，其余是小写字母/数字/连字符，总长 1-50。"""
    if len(slug) == 0 or len(slug) > 50:
        return False
    if not _is_slug_char(slug[0], allow_dash=False):
        return False
    for ch in slug[1:]:
        if not _is_slug_char(ch, allow_dash=True):
            return False
    return True


def _mastery_value(mastery: Mastery | None) -> str | None:
    """枚举取字符串值，None 原样返回。"""
    if mastery is None:
        return None
    return mastery.value


def _yaml_dump(obj: dict) -> str:
    """字典转 YAML 文本。传入的数据只含 JSON 安全的值（枚举已取 .value、时间已 isoformat）。

    allow_unicode=True：中文不转义；sort_keys=False：保持我们写字段的顺序。
    """
    return yaml.safe_dump(obj, allow_unicode=True, sort_keys=False)


def _find_objective(unit: TeachingUnit, objective_id: str) -> Objective | None:
    """按 id 找目标，找不到返回 None。"""
    for o in unit.objectives:
        if o.id == objective_id:
            return o
    return None


def _used_hint_levels(unit: TeachingUnit, objective_id: str) -> list[int]:
    """某目标已使用过的提示级别列表，如 [1, 1, 2]。"""
    levels = []
    for h in unit.hints:
        if h.objective_id == objective_id:
            levels.append(h.level)
    return levels


def _format_hint_levels(levels: list[int]) -> str:
    """把 [1, 1, 2] 格式化成 "L1×2, L2×1"。"""
    counts = {}
    for level in levels:
        counts[level] = counts.get(level, 0) + 1
    parts = []
    for level in sorted(counts):
        parts.append(f"L{level}×{counts[level]}")
    return ", ".join(parts)


class TeachingStore:
    """SQLite 教学单元存储，按工作区隔离；单元不随会话消亡（跨会话恢复）。

    每次 save_unit 都会把工作区 teaching/<slug>/ 下的 spec.yaml / record.yaml
    镜像重写一遍，保证人可读的档案与库中状态始终一致。
    """

    def __init__(self, workspace: Path | str, *, on_change: OnTeachingChange | None = None) -> None:
        self._workspace = Path(workspace)
        self._database = str(self._workspace / TEACHING_DB)
        self._on_change = on_change
        self._lock = threading.Lock()
        self._ready = False

    def set_on_change(self, on_change: OnTeachingChange | None) -> None:
        self._on_change = on_change

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database)
        if not self._ready:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS teaching_units ("
                "id TEXT PRIMARY KEY, slug TEXT NOT NULL, status TEXT NOT NULL, "
                "data TEXT NOT NULL, updated_at TEXT NOT NULL)"
            )
            connection.commit()
            self._ready = True
        return connection

    # ---- 同步层（锁内执行）----

    def _save_sync(self, unit: TeachingUnit) -> None:
        data = unit.model_dump_json()
        with self._lock:
            connection = self._connect()
            try:
                connection.execute(
                    "INSERT INTO teaching_units (id, slug, status, data, updated_at) VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET slug=excluded.slug, status=excluded.status, "
                    "data=excluded.data, updated_at=excluded.updated_at",
                    (unit.id, unit.slug, unit.status.value, data, unit.updated_at.isoformat()),
                )
                connection.commit()
            finally:
                connection.close()
        self._write_mirrors(unit)

    def _row_to_unit(self, row: tuple) -> TeachingUnit:
        return TeachingUnit.model_validate_json(str(row[0]))

    def _get_active_sync(self) -> TeachingUnit | None:
        with self._lock:
            connection = self._connect()
            try:
                row = connection.execute(
                    "SELECT data FROM teaching_units WHERE status = ? ORDER BY updated_at DESC LIMIT 1",
                    (UnitStatus.active.value,),
                ).fetchone()
            finally:
                connection.close()
        if row is None:
            return None
        return self._row_to_unit(row)

    def _get_unit_sync(self, unit_id: str) -> TeachingUnit | None:
        with self._lock:
            connection = self._connect()
            try:
                row = connection.execute(
                    "SELECT data FROM teaching_units WHERE id = ?", (unit_id,)
                ).fetchone()
            finally:
                connection.close()
        if row is None:
            return None
        return self._row_to_unit(row)

    def _list_units_sync(self) -> list[TeachingUnit]:
        with self._lock:
            connection = self._connect()
            try:
                rows = connection.execute(
                    "SELECT data FROM teaching_units ORDER BY rowid"
                ).fetchall()
            finally:
                connection.close()
        units = []
        for row in rows:
            units.append(self._row_to_unit(row))
        return units

    # ---- 镜像：teaching/<slug>/spec.yaml + record.yaml ----

    def _write_mirrors(self, unit: TeachingUnit) -> None:
        unit_dir = self._workspace / TEACHING_DIR / unit.slug
        unit_dir.mkdir(parents=True, exist_ok=True)

        objectives = []
        for o in unit.objectives:
            objectives.append({
                "id": o.id,
                "text": o.text,
                "mastery_required": o.mastery_required.value,
                "mastery_achieved": _mastery_value(o.mastery_achieved),
            })

        # 一锅 zones 按 kind 分成三组（kind 本身已体现在分组名里，导出时扔掉）
        agent_zone = []
        cowork_zone = []
        human_zone = []
        for z in unit.zones:
            z_data = z.model_dump(mode="json", exclude={"kind"})
            if z.kind is ZoneKind.agent:
                agent_zone.append(z_data)
            elif z.kind is ZoneKind.cowork:
                cowork_zone.append(z_data)
            else:
                human_zone.append(z_data)

        spec = {
            "spec": {
                "title": unit.title,
                "version": unit.version,
                "status": unit.status.value,
                "objectives": objectives,
                "zones": {
                    "agent_zone": agent_zone,
                    "cowork_zone": cowork_zone,
                    "human_zone": human_zone,
                },
                "hint_policy": {"max_level": unit.hint_max_level, "escalation_rule": "逐级解锁，每级升级前须展示当前级尝试"},
                "tests": {"location": unit.tests_root, "authority": "测试集为唯一验收契约；版本内冻结，改动须先升 spec 版本"},
                "changelog": unit.changelog,
            }
        }

        hints = []
        for h in unit.hints:
            hints.append(h.model_dump(mode="json"))

        mastery = {}
        for o in unit.objectives:
            mastery[o.id] = _mastery_value(o.mastery_achieved)

        record = {
            "learning_record": {
                "unit": unit.slug,
                "hints": hints,
                "mastery": mastery,
                "created_at": unit.created_at.isoformat(),
                "updated_at": unit.updated_at.isoformat(),
            }
        }

        (unit_dir / "spec.yaml").write_text(_yaml_dump(spec), encoding="utf-8")
        (unit_dir / "record.yaml").write_text(_yaml_dump(record), encoding="utf-8")

    # ---- 异步公开 API（同步函数扔到后台线程跑，避免卡住事件循环）----

    async def save_unit(self, unit: TeachingUnit) -> TeachingUnit:
        """新建或更新单元（upsert），随后重写镜像并触发 on_change。"""
        unit.updated_at = _now()
        snapshot = unit.model_copy(deep=True)
        await anyio.to_thread.run_sync(self._save_sync, snapshot)
        await self._notify(snapshot)
        return snapshot

    async def get_active(self) -> TeachingUnit | None:
        return await anyio.to_thread.run_sync(self._get_active_sync)

    async def get_unit(self, unit_id: str) -> TeachingUnit | None:
        return await anyio.to_thread.run_sync(self._get_unit_sync, unit_id)

    async def list_units(self) -> list[TeachingUnit]:
        return await anyio.to_thread.run_sync(self._list_units_sync)

    async def _notify(self, unit: TeachingUnit) -> None:
        if self._on_change is None:
            return
        result = self._on_change(unit)
        if inspect.isawaitable(result):
            await result


# ---- store 注册表：工具集与动态指令共享同一实例 ----

_stores: dict[Path, TeachingStore] = {}


def teaching_store_for(workspace: Path | str, on_change: OnTeachingChange | None = None) -> TeachingStore:
    """按工作区取教学 store（不存在则创建）；on_change 非 None 时更新回调。"""
    key = Path(workspace).expanduser().resolve()
    store = _stores.get(key)
    if store is None:
        store = TeachingStore(key, on_change=on_change)
        _stores[key] = store
    elif on_change is not None:
        store.set_on_change(on_change)
    return store


# ---- 渲染：teach_state 与动态指令共用 ----

def render_unit_state(unit: TeachingUnit) -> str:
    """把单元状态渲染成紧凑文本（动态指令与 teach_state 共用）。"""
    lines = [f"Unit: {unit.title} (id={unit.id}, slug={unit.slug}, v{unit.version}, {unit.status.value})"]

    lines.append("Objectives:")
    for o in unit.objectives:
        if o.mastery_achieved is None:
            achieved = "-"
        else:
            achieved = o.mastery_achieved.value
        used = _used_hint_levels(unit, o.id)
        if used:
            hint_text = ", hints used: " + _format_hint_levels(used)
        else:
            hint_text = ", no hints used"
        lines.append(f"  - {o.id} [required {o.mastery_required.value}, achieved {achieved}{hint_text}] {o.text}")

    lines.append("Zones:")
    for z in unit.zones:
        line = f"  - [{z.kind.value}] {z.scope}"
        if z.serves:
            line += " (serves " + ", ".join(z.serves) + ")"
        if z.note:
            line += " — " + z.note
        lines.append(line)

    if unit.tests_root:
        lines.append(f"Tests: {unit.tests_root} (frozen at v{unit.version}; changes require teach_bump_version first)")
    if unit.changelog:
        lines.append("Changelog: " + "; ".join(unit.changelog))
    return "\n".join(lines)


def render_closed_summary(units: list[TeachingUnit]) -> str:
    """最近关闭单元的一行式列表（teach_state 在无活跃单元时展示）。"""
    closed = []
    for u in units:
        if u.status is UnitStatus.closed:
            closed.append(u)
    if not closed:
        return ""
    lines = ["Recently closed units:"]
    for u in closed[-5:]:
        done = 0
        for o in u.objectives:
            if o.mastery_achieved is not None:
                done += 1
        lines.append(f"  - {u.title} (slug={u.slug}, v{u.version}): {done}/{len(u.objectives)} objectives mastered")
    return "\n".join(lines)


# ---- 工具集 ----

def teaching_toolset(store: TeachingStore) -> FunctionToolset:
    """SDT/TDT 教学工具集：spec 生命周期 + 提示台账 + 掌握度认证。

    里面的 6 个函数都是闭包：它们抓住了这里的 store 参数，
    所以 Agent 调用工具时不用（也不应）知道 store 的存在。
    校验失败返回中文错误串（仿 planning 工具风格），由模型自行修正后重试。
    """

    async def teach_create_unit(
        slug: str,
        title: str,
        objectives: list[Objective],
        zones: list[Zone],
        tests_root: str,
        hint_max_level: int = 3,
    ) -> str:
        """创建教学单元（学习者已口头确认 spec 之后调用）。同一工作区同时只能有一个活跃单元。

        Args:
            slug: 文件系统安全标识（小写字母/数字/单连字符），镜像目录名
            title: 单元标题
            objectives: 学习目标列表，id 唯一，各带 mastery_required
            zones: 三区划分；至少包含一个 human 区，serves 引用已存在的 objective id
            tests_root: 测试套件目录（版本内冻结）
            hint_max_level: 允许的最高提示级别（1-3，默认 3）
        """
        if await store.get_active() is not None:
            return "创建失败：已有一个活跃单元。先 teach_close_unit 关闭它，或继续当前单元。"
        if not _is_valid_slug(slug):
            return f"创建失败：slug {slug!r} 不合法（小写字母开头，仅小写字母/数字/单连字符，≤50 字符）。"
        if hint_max_level < 1 or hint_max_level > 3:
            return "创建失败：hint_max_level 必须在 1-3 之间。"
        if not objectives:
            return "创建失败：至少需要一个学习目标。"

        seen_ids = []
        duplicate_ids = []
        for o in objectives:
            if o.id in seen_ids and o.id not in duplicate_ids:
                duplicate_ids.append(o.id)
            seen_ids.append(o.id)
        if duplicate_ids:
            return "创建失败：objective id 重复：" + ", ".join(duplicate_ids) + "。"

        has_human_zone = False
        for z in zones:
            if z.kind is ZoneKind.human:
                has_human_zone = True
        if not has_human_zone:
            return "创建失败：zones 中必须至少有一个 human 区（承载学习目标的区域）。"

        for z in zones:
            unknown = []
            for s in z.serves:
                if s not in seen_ids and s not in unknown:
                    unknown.append(s)
            if unknown:
                return f"创建失败：{z.kind.value} 区 {z.scope!r} 的 serves 引用了不存在的 objective：" + ", ".join(unknown) + "。"

        unit = TeachingUnit(
            slug=slug, title=title, objectives=objectives, zones=zones,
            tests_root=tests_root, hint_max_level=hint_max_level,
        )
        await store.save_unit(unit)
        return (
            f"单元已创建（id={unit.id}）。spec 镜像：teaching/{slug}/spec.yaml；提示与掌握度台账：teaching/{slug}/record.yaml。\n\n"
            "下一步：完成 AI 代劳区脚手架，编写覆盖全部 objective 的测试套件（含边界用例），"
            "运行并确认全部失败（Red），然后把人类必做区交给学习者。\n\n" + render_unit_state(unit)
        )

    async def teach_state() -> str:
        """读取当前教学单元状态（跨会话恢复后先调用它重新对齐）。"""
        unit = await store.get_active()
        if unit is None:
            summary = render_closed_summary(await store.list_units())
            text = "当前没有活跃的教学单元。"
            if summary:
                text += "\n\n" + summary
            return text
        return render_unit_state(unit)

    async def teach_record_hint(objective_id: str, level: int, attempt: str) -> str:
        """记录一次提示升级（唯一被允许的帮助通道）。逐级解锁：首个提示必须是 L1，之后每次只能升一级；
        升级前学习者必须展示当前级的真实尝试（attempt 参数），全部留痕进学习档案。

        Args:
            objective_id: 提示针对的 objective id
            level: 提示级别（1 指方向 / 2 给结构 / 3 给对照示例），不得超过单元的 hint_max_level
            attempt: 学习者在当前级的尝试记录（做了什么、卡在哪），不能为空
        """
        unit = await store.get_active()
        if unit is None:
            return "记录失败：当前没有活跃单元。"
        objective = _find_objective(unit, objective_id)
        if objective is None:
            ids = []
            for o in unit.objectives:
                ids.append(o.id)
            return f"记录失败：objective {objective_id!r} 不存在（现有：" + ", ".join(ids) + "）。"
        if not attempt.strip():
            return "记录失败：attempt 为空。提示有价——升级前学习者必须展示当前级的真实尝试。"
        if level < 1 or level > unit.hint_max_level:
            return f"记录失败：level 须在 1-{unit.hint_max_level} 之间（本单元最高 L{unit.hint_max_level}）。"

        used = _used_hint_levels(unit, objective_id)
        highest = 0
        for lv in used:
            if lv > highest:
                highest = lv
        if level > highest + 1:
            return (
                f"记录失败：禁止跳级。{objective_id} 目前最高用到 L{highest}，"
                f"下一级只能是 L{highest + 1}。请先用 L{highest + 1} 级别的提示。"
            )

        unit.hints.append(HintEvent(objective_id=objective_id, level=level, attempt=attempt.strip()))
        await store.save_unit(unit)

        if level == 1:
            allowance = "L1 指方向：相关概念、文档章节、应思考的问题——不含任何代码。"
        elif level == 2:
            allowance = "L2 给结构：伪代码或步骤分解——不含可运行实现。"
        else:
            allowance = "L3 给对照：同类但不同的已解决示例，要求学习者迁移。"
        all_used = used + [level]
        return (
            f"已记录：{objective_id} 升到 L{level}（该目标累计提示 {_format_hint_levels(all_used)}）。\n"
            "本级别允许的帮助：" + allowance
        )

    async def teach_update_mastery(objective_id: str, achieved: Mastery, evidence: str) -> str:
        """认证某 objective 的掌握等级（评审/讲解/变体任务之后调用）。等级只升不降。
        D1 的硬规则：该目标使用过 L3 提示则不得认证 D1（提示跳水说明没有独立完成）。

        Args:
            objective_id: 目标 id
            achieved: 已达成的等级（D1 会做 / D2 会讲 / D3 会迁移）
            evidence: 认证依据（测试全绿截图要点、讲解要点、变体任务完成情况），不能为空
        """
        unit = await store.get_active()
        if unit is None:
            return "认证失败：当前没有活跃单元。"
        objective = _find_objective(unit, objective_id)
        if objective is None:
            ids = []
            for o in unit.objectives:
                ids.append(o.id)
            return f"认证失败：objective {objective_id!r} 不存在（现有：" + ", ".join(ids) + "）。"
        if not evidence.strip():
            return "认证失败：evidence 为空。记录认证依据（测试结果、讲解要点或变体任务表现）。"

        if objective.mastery_achieved is not None:
            if _MASTERY_ORDER[achieved] < _MASTERY_ORDER[objective.mastery_achieved]:
                return f"认证失败：{objective_id} 已达成 {objective.mastery_achieved.value}，等级只升不降。"

        used = _used_hint_levels(unit, objective_id)
        used_l3 = False
        for lv in used:
            if lv >= 3:
                used_l3 = True
        if achieved is Mastery.D1 and used_l3:
            return (
                f"认证失败：{objective_id} 使用过 L3 提示，按规范不得认证 D1"
                "（D1 = 测试全绿且未使用 L3 及以上提示）。可在讲解后认证 D2。"
            )

        objective.mastery_achieved = achieved
        await store.save_unit(unit)
        return f"已认证：{objective_id} 达成 {achieved.value}（要求 {objective.mastery_required.value}）。依据：{evidence.strip()}"

    async def teach_bump_version(reason: str) -> str:
        """升 spec 版本——修改冻结测试集或调整三区划分的法定前置。全部变更记入 changelog 审计轨迹。

        Args:
            reason: 变更理由（为什么改测试/调边界），不能为空
        """
        unit = await store.get_active()
        if unit is None:
            return "升版失败：当前没有活跃单元。"
        if not reason.strip():
            return "升版失败：reason 为空。记录变更理由（审计轨迹的一部分）。"

        old = unit.version
        unit.version += 1
        now_text = _now().isoformat(timespec="seconds")
        unit.changelog.append(f"v{old}→v{unit.version} ({now_text}): {reason.strip()}")
        await store.save_unit(unit)
        return f"spec 已升到 v{unit.version}。现在可以修改测试或调整边界；旧版断言已归档于 changelog。"

    async def teach_close_unit(summary: str) -> str:
        """关闭当前单元（目标达成或学习者终止）。关闭后负责归档：
        把已掌握的知识点按知识系统工作流蒸馏进 declarative/procedural/conditional。

        Args:
            summary: 单元总结（掌握了什么、哪些点留待下一单元），不能为空
        """
        unit = await store.get_active()
        if unit is None:
            return "关闭失败：当前没有活跃单元。"
        if not summary.strip():
            return "关闭失败：summary 为空。写清掌握了什么、遗留什么。"

        unit.status = UnitStatus.closed
        await store.save_unit(unit)

        mastered_count = 0
        for o in unit.objectives:
            if o.mastery_achieved is not None:
                mastered_count += 1
        return (
            f"单元已关闭：{unit.title}（v{unit.version}，掌握 {mastered_count}/{len(unit.objectives)}）。\n"
            f"档案：teaching/{unit.slug}/（spec.yaml + record.yaml）。\n"
            "收尾职责：把已掌握的知识点蒸馏进知识系统（read_index_knowledge → read_knowledge → edit_knowledge），"
            "并向学习者总结本单元与下一步建议。"
        )

    return FunctionToolset(
        tools=[
            teach_create_unit,
            teach_state,
            teach_record_hint,
            teach_update_mastery,
            teach_bump_version,
            teach_close_unit,
        ],
        id="teaching",
    )
