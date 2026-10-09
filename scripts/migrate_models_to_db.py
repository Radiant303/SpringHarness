"""一次性迁移：把 ~/.springharness/config.toml 的 [providers]/[models]/default_model 灌进数据库。

模型配置改为站长在管理后台维护（model_providers / model_definitions / system_settings.default_model），
本脚本只做数据搬运，跑完后可删除。api_key 只入库，不回显（输出只打名称）。
"""

from __future__ import annotations

from spring_harness.cloud.db import (
    ModelDefinitionRow,
    ModelProviderRow,
    SystemSettingRow,
    get_sessionmaker,
    utc_now,
)
from spring_harness.core.config.settings import config

KEY_DEFAULT_MODEL = "default_model"


def main() -> None:
    with get_sessionmaker()() as s:
        for name, p in config.providers.items():
            row = s.get(ModelProviderRow, name)
            if row is None:
                row = ModelProviderRow(name=name, type=p.type, api_key=p.api_key,
                                       base_url=p.base_url, updated_at=utc_now())
                s.add(row)
            else:
                row.type, row.api_key, row.base_url, row.updated_at = p.type, p.api_key, p.base_url, utc_now()

        for mid, m in config.models.items():
            row = s.get(ModelDefinitionRow, mid)
            if row is None:
                row = ModelDefinitionRow(id=mid, created_at=utc_now())
                s.add(row)
            row.provider = m.provider
            row.model = m.model
            row.display_name = m.display_name
            row.max_context_size = m.max_context_size
            row.max_output_size = m.max_output_size
            row.capabilities = ",".join(m.capabilities)
            row.support_efforts = ",".join(m.support_efforts)
            row.default_effort = m.default_effort
            row.reasoning_key = m.reasoning_key
            row.enabled = True
            row.updated_at = utc_now()

        setting = s.get(SystemSettingRow, KEY_DEFAULT_MODEL)
        if setting is None:
            s.add(SystemSettingRow(setting_key=KEY_DEFAULT_MODEL,
                                   setting_value=config.default_model, updated_at=utc_now()))
        else:
            setting.setting_value = config.default_model
            setting.updated_at = utc_now()
        s.commit()

    print(f"providers={len(config.providers)} models={len(config.models)} default={config.default_model}")


if __name__ == "__main__":
    main()
