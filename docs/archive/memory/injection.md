# 排程 V3 与迁移边界（`b178eb67` 记忆摘录）

原记忆第 579–592 行。涉及版本、机器、发布、岗位和测试的结论以记录发生时为限。现行入口见[生产与质量](../../project-memory/production.md)和[项目记忆](../../../PROJECT_MEMORY.md)。[固定版本原文](https://github.com/13829313399-a11y/Royal-Regent-Nexus/blob/b178eb679edd6b48f23f84d6b194d08aa25edf00/PROJECT_MEMORY.md#L579-L592)

### Injection-Scheduling Center

The production portal and V3 scheduling API retain the four-factory scheduling workbench, factory-scoped orders and equipment, shared mold catalog and original import/export contracts. The four `injection_scheduling:` permissions and `fixed-v33` position definitions remain active. The unpublished injection_ops draft stays outside the runtime. The molding-sample API at `/api/injection` is a separate domain.

The active migration lineage retains the scheduling tables and operating grants at `20261116_0195`. The published destructive revision `20261116_inj_retire` is preserved verbatim under `backend/alembic/archived/`, outside the automatic upgrade graph. A database already marked with that revision requires verified pre-retirement data and authorization recovery in isolation. The startup catalog also rejects a previously applied `fixed-v34` before projecting role grants. The older local engineering BOM revision collision can be inspected independently with `backend/tools/repair_retired_injection_bom.py`.

Migration `20260912_0111` joins the customer PO branch `20260912_0108` and spray allocations `20260911_0110` without rewriting either migration. Database paths and migration states are checkout-specific. Earlier carton-activation documentation refers to a separate repaired SQLite state and must not be used to infer the current configured database. Always inspect the actual database before applying migrations. The published migration chain remains unchanged; divergent historical revision collisions require schema-equivalence checks and restored-copy rehearsal rather than blindly upgrading or stamping. Empty SQLite migration, real IAM/API, Excel round-trip and PostgreSQL DDL compilation have isolated tests.

Production PostgreSQL upgrade from `20260911_0110` to `20260912_0111`, restored-copy startup and old-image service rollback have passed live rehearsal; this does not establish a fresh replay of the entire historical PostgreSQL migration chain.

Migration `20260903_0095` permanently drops both `injection_schedule_*` and `injection_scheduling_*` table families, removes their three generations of permission registrations/grants, invalidates affected authorization previews and removes module IAM seed state. It checks external dependencies before deletion and refuses downgrade because lost records require a verified backup. Historical migration scripts remain immutable for version-chain continuity; they have no dependency on removed application code.

The pre-retirement recovery copies and original source workbooks are independent of the active application database.

Production 3D repairs and hourly telemetry optimization are part of tracked main; current release identities and preservation evidence are maintained in section 7. They address memory-heavy historical statistics, cloud-record inventory classification, analytics timeouts and browser translation of 3D business text. Telemetry summaries must initialize only with a compatible writer. Additive covering indexes and hourly rollups at `20260929_0130` were verified on populated isolated PostgreSQL and SQLite databases, adding no business rows. Reset rollup initialization before reverting to an older telemetry writer so a later redeploy cannot reuse stale cache. API/Web replacement must preserve PostgreSQL and the separate `rr-three-d` printer Connector, private read-only translation models, reconciliation cutoff and production flags.

Routine code rollback must retain the compatible database and never restore an old database over new work. Physical printer commands and inventory adjustments require separate business evidence; an offline dashboard is not proof a physical print stopped.
