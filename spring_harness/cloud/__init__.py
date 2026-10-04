"""云端部署包：鉴权用户模型（db.py）、网关会话存储（gateway_store.py）、WS 入口（ws.py / app.py）。

注意：本包 __init__ 保持空——cloud/gateway_store.py 会反向 import spring_harness.cloud.db，
这里 import 任何应用模块都会形成环。
"""
