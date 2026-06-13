"""Binding cache - local memory layer with backend persistence.

Tiered persistence:
- KP QQ -> Campaign: persisted via API to PostgreSQL (campaigns.kp_qq field)
- Group ID -> Campaign: in-memory only (needs re-bind after bot restart)

Flow:
1. User /bind <campaign_id> -> API writes to PostgreSQL + fills local cache
2. Group message -> check local cache for campaign -> API for KP QQ -> notify
"""

from typing import Optional, Dict
from dataclasses import dataclass, field


@dataclass
class BindingStore:
    group_bindings: Dict[str, str] = field(default_factory=dict)
    kp_bindings: Dict[str, str] = field(default_factory=dict)

    def bind_group(self, group_id: str, campaign_id: str):
        self.group_bindings[group_id] = campaign_id

    def get_campaign_for_group(self, group_id: str) -> Optional[str]:
        return self.group_bindings.get(group_id)

    def unbind_group(self, group_id: str):
        self.group_bindings.pop(group_id, None)

    def bind_kp(self, kp_qq: str, campaign_id: str):
        self.kp_bindings[kp_qq] = campaign_id

    def get_campaign_for_kp(self, kp_qq: str) -> Optional[str]:
        return self.kp_bindings.get(kp_qq)

    def unbind_kp(self, kp_qq: str):
        self.kp_bindings.pop(kp_qq, None)

    def get_all_bindings(self) -> dict:
        return {
            "group_bindings": dict(self.group_bindings),
            "kp_bindings": dict(self.kp_bindings),
        }


store = BindingStore()
