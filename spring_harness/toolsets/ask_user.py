from pydantic_ai import CallDeferred, FunctionToolset


def ask_user(
    question: str,
    options: list[str] | None = None,
    allow_custom: bool = True,
) -> str:
    """向用户提问并等待回答。

    - options 为 None：纯文本输入
    - options 有值且 allow_custom=False：只能从选项中选择
    - options 有值且 allow_custom=True：可选择，也可自定义回答

    需求含糊、存在多个合理走向、或需要用户做选择时调用。
    每次只问最关键的一两个问题；能自己推断的不要问。
    用户的回答会以字符串形式作为本工具的返回值。

    Args:
        question: 要问用户的问题
        options: 候选答案列表
        allow_custom: 有候选答案时是否允许用户自由输入
    """
    raise CallDeferred()


ask_user_toolset = FunctionToolset(tools=[ask_user])
