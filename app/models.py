"""数据模型：供应商与模型行。"""
from dataclasses import dataclass, field


@dataclass
class ModelRow:
    id: str
    display_name: str = ""
    manual: bool = False          # 手动添加的行，获取模型时不冲掉
    api_meta: dict = field(default_factory=dict)   # /models 返回里能嗅探到的字段
    meta_over: dict = field(default_factory=dict)  # 手动覆盖 {"ctx":int|None,"mod":list|None}
    result: dict | None = None    # 最近一次 TTFT 结果（持久化）

    @property
    def name(self) -> str:
        return self.display_name or self.id


@dataclass
class Provider:
    id: str
    name: str
    base_url: str
    api_key: str
    protocol: str                 # openai | anthropic | gemini | zhipu
    note: str = ""
    enabled: bool = True
    models: list = field(default_factory=list)     # [ModelRow]
    last_conn: dict | None = None # 最近一次连通结果（不持久化）
    history: list = field(default_factory=list)    # 最近的 TTFT 历史记录

    def model_by_id(self, mid: str) -> ModelRow | None:
        for m in self.models:
            if m.id == mid:
                return m
        return None
