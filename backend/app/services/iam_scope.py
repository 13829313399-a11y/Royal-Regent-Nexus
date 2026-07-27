from typing import Literal


ScopeMode = Literal[
    "own_factory",
    "cross_factory_read",
    "cross_factory_operate",
]
AccessKind = Literal["read", "operate"]

OWN_FACTORY_SCOPE: ScopeMode = "own_factory"
CROSS_FACTORY_READ_SCOPE: ScopeMode = "cross_factory_read"
CROSS_FACTORY_OPERATE_SCOPE: ScopeMode = "cross_factory_operate"
VALID_SCOPE_MODES = {
    OWN_FACTORY_SCOPE,
    CROSS_FACTORY_READ_SCOPE,
    CROSS_FACTORY_OPERATE_SCOPE,
}

READ_ACCESS_KIND: AccessKind = "read"
OPERATE_ACCESS_KIND: AccessKind = "operate"
VALID_ACCESS_KINDS = {READ_ACCESS_KIND, OPERATE_ACCESS_KIND}

# Cross-factory read must never make a newly registered operation available by
# accident. New or unknown permissions therefore default to ``operate`` until
# their read-only contract is explicitly recorded here and in IAM metadata.
READ_PERMISSION_CODES = frozenset(
    {
        "molding_sample:read",
        "molding_sample:cross_factory_read",
        "molding_sample:cross_factory_cost_read",
        "molding_sample:production_read",
        "molding_sample:audit_read",
        "molding_sample:notification_read",
        "carton_mark:read",
        "customer_price:read",
        "customer_price:compare",
        "internal_quote:read",
        "internal_quote:baseline_read",
        "internal_quote:summary_read",
        "internal_quote:timeline_read",
        "system:audit_read",
        "system:permission_catalog_read",
    }
)

# Notification access is read-only, but a cross-factory-read position must not
# inherit another factory's bell feed. Roles that intentionally receive
# cross-factory notifications use ``cross_factory_operate`` instead.
CROSS_FACTORY_READ_LOCAL_ONLY_PERMISSION_CODES = frozenset(
    {"molding_sample:notification_read"}
)

# Every built-in position may inspect the production-task queue at any factory,
# while its role-level scope continues to govern every other permission. Keep
# this allow-list permission-specific so unrelated reads never expand by accident.
SYSTEM_POSITION_CROSS_FACTORY_READ_PERMISSION_CODES = frozenset(
    {"molding_sample:production_read"}
)


def default_permission_access_kind(permission_code: str) -> AccessKind:
    return READ_ACCESS_KIND if permission_code in READ_PERMISSION_CODES else OPERATE_ACCESS_KIND


def scope_mode_expands_access(before: ScopeMode, after: ScopeMode) -> bool:
    rank = {
        OWN_FACTORY_SCOPE: 0,
        CROSS_FACTORY_READ_SCOPE: 1,
        CROSS_FACTORY_OPERATE_SCOPE: 2,
    }
    return rank[after] > rank[before]
