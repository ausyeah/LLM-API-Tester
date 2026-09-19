"""把两组测试供应商预置进本机配置（Key 走 DPAPI 加密落盘）。

Key 从环境变量读取：LLMTEST_OPENAI_KEY / LLMTEST_ANTHROPIC_KEY。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import config
from app.models import ModelRow


def main():
    providers = []
    key = os.environ.get("LLMTEST_OPENAI_KEY", "").strip()
    if key:
        p = config.new_provider(name="示例中转站", protocol="openai",
                                base_url="https://example.com/v1",
                                api_key=key, note="联调测试")
        p.models = [ModelRow(id="grok-4.6")]
        providers.append(p)
    key = os.environ.get("LLMTEST_ANTHROPIC_KEY", "").strip()
    if key:
        p = config.new_provider(name="GLM", protocol="anthropic",
                                base_url="https://api.z.ai/api/anthropic",
                                api_key=key, note="联调测试")
        for mid, dname in [("glm-5.3-flash", "GLM-5.3-Flash"),
                           ("glm-4.7", "GLM-4.7"),
                           ("glm-5.2", "GLM-5.2")]:
            p.models.append(ModelRow(id=mid, display_name=dname))
        providers.append(p)
    if not providers:
        sys.exit("未设置 LLMTEST_OPENAI_KEY / LLMTEST_ANTHROPIC_KEY， Nothing to seed")
    settings = config.default_settings()
    settings["last_provider"] = providers[-1].id
    config.save(providers, settings)
    print(f"已预置 {len(providers)} 个供应商到 {config.CONFIG_PATH}")


if __name__ == "__main__":
    main()
