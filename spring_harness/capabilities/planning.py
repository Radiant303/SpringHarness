import inspect
from collections.abc import Awaitable, Callable

from pydantic_ai_harness import Planning
from pydantic_ai_harness.planning import PlanItem, PlanStore, SqlitePlanStore

PLAN_DB = "plan.db"

OnPlanChange = Callable[[list["PlanItem"]], "None | Awaitable[None]"]


class _ObservableStore:
    """PlanStore 委托包装：写操作完成后回调最新全量 items。"""

    def __init__(self, inner: PlanStore, on_change: OnPlanChange) -> None:
        self._inner = inner
        self._on_change = on_change

    async def _notify(self) -> None:
        result = self._on_change(await self._inner.get_items())
        if inspect.isawaitable(result):
            await result

    async def get_items(self) -> list[PlanItem]:
        return await self._inner.get_items()

    async def get_item(self, item_id: str) -> PlanItem | None:
        return await self._inner.get_item(item_id)

    async def set_items(self, items: list[PlanItem]) -> None:
        await self._inner.set_items(items)
        await self._notify()

    async def add_item(self, item: PlanItem) -> PlanItem:
        item = await self._inner.add_item(item)
        await self._notify()
        return item

    async def update_item(self, item_id: str, **kwargs) -> PlanItem | None:
        item = await self._inner.update_item(item_id, **kwargs)
        await self._notify()
        return item

    async def remove_item(self, item_id: str) -> bool:
        removed = await self._inner.remove_item(item_id)
        await self._notify()
        return removed


def planning(session: str, on_change: OnPlanChange | None = None) -> Planning:
    """加载Plan；on_change 在每次计划变更后收到最新全量 items。"""
    store: PlanStore = SqlitePlanStore(PLAN_DB, session=session)
    if on_change is not None:
        store = _ObservableStore(store, on_change)
    return Planning(store=store)


async def load_plan_items(session: str) -> list[PlanItem]:
    """读某会话已持久化的计划（恢复会话时重建 PlanMessage 用）。"""
    return await SqlitePlanStore(PLAN_DB, session=session).get_items()
