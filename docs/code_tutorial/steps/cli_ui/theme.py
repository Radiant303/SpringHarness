"""主题定义：Kimi Code CLI 风格配色 + 透明背景三要素。

对应教程第 11 章：background/surface/panel 用 ansi_default、Theme(ansi=True)、
variables 里补 ansi-background / ansi-foreground，三者缺一不可。
"""

from textual.theme import Theme

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
    },
)

ACCENT = "#4a9eff"
GRAY = "#7a8391"
