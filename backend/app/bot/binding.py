"""团体绑定管理 — 维护群/KP 与跑团项目的映射关系

Phase 1 使用内存存储（进程重启后需要重新绑定）。
Phase 2 可改为 Redis 持久化。

绑定关系：
- group_id → campaign_id（哪个群跑哪个团）
- kp_qq → campaign_id（KP 管理哪个团）
"""

from typing import Optional, Dict
from dataclasses import dataclass, field


@dataclass
class BindingStore:
    """绑定存储（内存版）"""
    # 群号 → 跑团项目 ID
    group_bindings: Dict[str, str] = field(default_factory=dict)
    # KP QQ → 跑团项目 ID
    kp_bindings: Dict[str, str] = field(default_factory=dict)

    def bind_group(self, group_id: str, campaign_id: str):
        """绑定群到跑团项目"""
        self.group_bindings[group_id] = campaign_id

    def get_campaign_for_group(self, group_id: str) -> Optional[str]:
        """获取群绑定的跑团项目 ID"""
        return self.group_bindings.get(group_id)

    def unbind_group(self, group_id: str):
        """解除群绑定"""
        self.group_bindings.pop(group_id, None)

    def bind_kp(self, kp_qq: str, campaign_id: str):
        """绑定 KP 到跑团项目"""
        self.kp_bindings[kp_qq] = campaign_id

    def get_campaign_for_kp(self, kp_qq: str) -> Optional[str]:
        """获取 KP 管理的跑团项目 ID"""
        return self.kp_bindings.get(kp_qq)

    def unbind_kp(self, kp_qq: str):
        """解除 KP 绑定"""
        self.kp_bindings.pop(kp_qq, None)

    def get_all_bindings(self) -> dict:
        """获取所有绑定关系（用于调试）"""
        return {
            "group_bindings": dict(self.group_bindings),
            "kp_bindings": dict(self.kp_bindings),
        }


# 全局单例
store = BindingStore()
