"""云端入口：uvicorn 托管 create_app()，监听地址取自 cloud 配置。"""

import uvicorn

from spring_harness.cloud.app import create_app
from spring_harness.core.config.settings import config
from spring_harness.core.log import logger


def main() -> None:
    cloud = config.cloud
    logger.info("云端服务启动: http://{}:{}", cloud.host, cloud.port)
    uvicorn.run(create_app(), host=cloud.host, port=cloud.port)


if __name__ == "__main__":
    main()
