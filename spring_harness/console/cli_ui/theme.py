"""主题定义：Kimi Code CLI 风格配色 + 透明背景三要素。

对应教程第 11 章：background/surface/panel 用 ansi_default、Theme(ansi=True)、
variables 里补 ansi-background / ansi-foreground，三者缺一不可。
"""

from textual.theme import Theme

ACCENT = "#4a9eff"
# codex 的灰是默认前景 + dim（不硬编码 RGB）。CSS 里没有 dim 颜色，
# 用终端 8 号色（bright_black / ansi_bright_black）等效：跟随终端主题的中性灰。
GRAY = "bright_black"

# Kimi Code CLI 风格配色
KIMI_THEME = Theme(
    name="kimi",
    primary="#4a9eff",      # 主蓝色
    secondary="#2b6cb0",    # 深蓝
    accent="#4a9eff",       # 强调蓝（边框、高亮）
    warning="#e5c07b",      # 警告黄
    error="#e06c75",
    success="#98c379",
    foreground="ansi_default",  # 前景文字跟随终端默认
    background="ansi_default",  # 跟随终端默认背景（透明终端可透出背景）
    surface="ansi_default",     # 面板背景同终端
    panel="ansi_default",
    ansi=True,              # 使用原生 ANSI 颜色（禁用 ANSI→RGB 过滤器，default 才能透传）
    dark=True,
    variables={
        # ansi 主题需要这两个变量（按钮/Toast/内联边框等会引用）
        "ansi-background": "ansi_default",
        "ansi-foreground": "ansi_default",
        # Markdown 标题：主蓝 + 粗体 + 下划线（text-style 可空格组合多个值）
        "markdown-h1-text-style": "bold underline",
        "markdown-h2-text-style": "bold",
        "markdown-h3-text-style": "bold",
        "markdown-h4-text-style": "bold",
        "markdown-h5-text-style": "bold",
        "markdown-h6-text-style": "bold",
        # 颜色用固定主蓝：ansi_default 虽能跟随终端反色，但 bold 打在它上面
        # 在部分终端里是空操作（没有"更亮的默认色"），权衡后选固定色
        "markdown-h1-color": ACCENT,
        "markdown-h2-color": ACCENT,
        "markdown-h3-color": ACCENT,
        "markdown-h4-color": ACCENT,
        "markdown-h5-color": ACCENT,
        "markdown-h6-color": ACCENT,
    },
)
