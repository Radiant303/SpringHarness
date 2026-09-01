from pydantic_ai_harness import Planning
from pydantic_ai_harness.planning import SqlitePlanStore


def planning(session: str) -> Planning:
    """加载Plan"""
    return Planning(store=SqlitePlanStore('plan.db', session=session))
