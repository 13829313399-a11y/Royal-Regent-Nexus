"""Persist bounded collector evidence and project freshness; never settle print jobs."""

import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select

from app.models.three_d_printing import (
    ThreeDPrintingAuditEvent,
    ThreeDPrintingNetworkGateway,
    ThreeDPrintingSite,
)
from app.services.three_d_consistency import atomic_write

SITE_ID = "3dsite-huakang-a-heyuan"
FRESH_SECONDS = 90
Check = Literal["ok", "failed", "skipped"]


class PrinterProbe(BaseModel):
    model_config = ConfigDict(extra="forbid")
    machine_no: int = Field(ge=1, le=11)
    route: Check
    tcp: Check
    tls: Check
    mqtt: Check
    latency_ms: float | None = Field(default=None, ge=0, le=60000, allow_inf_nan=False)

    @model_validator(mode="after")
    def stages_are_ordered(self):
        for previous, current in zip(
            (self.route, self.tcp, self.tls), (self.tcp, self.tls, self.mqtt)
        ):
            if previous != "ok" and current != "skipped":
                raise ValueError("later_probe_requires_successful_previous_stage")
        return self


class NetworkHealthReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    factory_id: Literal["huakang-a"]
    site_id: Literal["3dsite-huakang-a-heyuan"]
    gateway_key: str = Field(pattern=r"^huakang-a-heyuan-vpn-[a-z0-9-]{1,24}$")
    vpn_type: Literal["wireguard", "tailscale", "ipsec"]
    probe_level: Literal["network", "mqtt"] = "mqtt"
    observed_at: datetime
    tunnel: Literal["ok", "failed", "unknown"]
    exposure: Literal["ok", "unsafe", "unknown"]
    printers: list[PrinterProbe] = Field(min_length=11, max_length=11)

    @field_validator("observed_at")
    @classmethod
    def aware_time(cls, value):
        if value.tzinfo is None:
            raise ValueError("timezone_required")
        return value.astimezone(UTC)

    @field_validator("printers")
    @classmethod
    def all_printers(cls, value):
        if {p.machine_no for p in value} != set(range(1, 12)):
            raise ValueError("unique_11_printers_required")
        return sorted(value, key=lambda p: p.machine_no)


def _status(payload):
    if payload.tunnel != "ok":
        return "unreachable"
    if payload.exposure != "ok" or any(
        getattr(p, "mqtt" if payload.probe_level == "mqtt" else "tls") != "ok"
        for p in payload.printers
    ):
        return "degraded"
    return "healthy"


def _latest(db, gateway_key=None):
    statement = select(ThreeDPrintingAuditEvent).where(
        ThreeDPrintingAuditEvent.factory_id == "huakang-a",
        ThreeDPrintingAuditEvent.entity_type == "network_health",
    )
    if gateway_key:
        statement = statement.where(ThreeDPrintingAuditEvent.entity_id == gateway_key)
    return db.scalar(
        statement.order_by(
            ThreeDPrintingAuditEvent.created_at.desc(),
            ThreeDPrintingAuditEvent.id.desc(),
        ).limit(1)
    )


@atomic_write
def store_network_health(db, payload: NetworkHealthReport):
    now = datetime.now(UTC)
    age = (now - payload.observed_at).total_seconds()
    if not -5 <= age <= FRESH_SECONDS:
        raise HTTPException(409, "网络探测时间已过期或超前，请检查NTP")
    if db.get(ThreeDPrintingSite, payload.site_id) is None:
        raise HTTPException(409, "请先完成0098站点初始化")
    # One selected active path per site in PR-05; HA ownership is a later cutover gate.
    latest = _latest(db)
    encoded = json.dumps(
        payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )
    if latest:
        previous = NetworkHealthReport.model_validate_json(latest.detail_json)
        if payload.observed_at <= previous.observed_at:
            if encoded != latest.detail_json:
                raise HTTPException(409, "拒绝乱序或冲突的网络健康报告")
            return db.scalar(
                select(ThreeDPrintingNetworkGateway).where(
                    ThreeDPrintingNetworkGateway.gateway_key == payload.gateway_key,
                    ThreeDPrintingNetworkGateway.factory_id == payload.factory_id,
                )
            )
    gateway = db.scalar(
        select(ThreeDPrintingNetworkGateway).where(
            ThreeDPrintingNetworkGateway.factory_id == payload.factory_id,
            ThreeDPrintingNetworkGateway.gateway_key == payload.gateway_key,
        )
    )
    if gateway is None:
        gateway = ThreeDPrintingNetworkGateway(
            id="3dgw-" + sha256(payload.gateway_key.encode()).hexdigest()[:32],
            factory_id=payload.factory_id,
            site_id=payload.site_id,
            gateway_key=payload.gateway_key,
            vpn_type=payload.vpn_type,
        )
        db.add(gateway)
    gateway.status = _status(payload)
    gateway.vpn_type = payload.vpn_type
    latencies = [p.latency_ms for p in payload.printers if p.latency_ms is not None]
    gateway.latency_ms = sum(latencies) / len(latencies) if latencies else 0
    # Do not pretend TCP failure ratio is ICMP loss or report time is a VPN handshake.
    gateway.last_error = (
        "" if gateway.status == "healthy" else "network_probe_incomplete"
    )
    db.add(
        ThreeDPrintingAuditEvent(
            id="3dnet-" + sha256(encoded.encode()).hexdigest(),
            factory_id=payload.factory_id,
            entity_type="network_health",
            entity_id=payload.gateway_key,
            action=gateway.status,
            detail_json=encoded,
            actor_id="network-doctor",
            actor_name="站点网络诊断",
            actor_type="network_collector",
            request_id="",
            created_at=payload.observed_at.isoformat(),
        )
    )
    from app.services.three_d_connector import notify
    notify(db, "network_health", gateway.id)
    return gateway


def network_health_snapshot(db):
    latest = _latest(db)
    if latest is None:
        return {
            "configured": False,
            "status": "unconfigured",
            "observed_at": "",
            "failed_machine_numbers": [],
            "message": "站点VPN尚未接入健康采集，当前仍使用旧Edge链路",
        }
    payload = NetworkHealthReport.model_validate_json(latest.detail_json)
    age = (datetime.now(UTC) - payload.observed_at).total_seconds()
    status = _status(payload) if -5 <= age <= FRESH_SECONDS else "stale"
    return {
        "configured": True,
        "status": status,
        "observed_at": payload.observed_at.isoformat(),
        "failed_machine_numbers": [
            p.machine_no
            for p in payload.printers
            if getattr(p, "mqtt" if payload.probe_level == "mqtt" else "tls") != "ok"
        ],
        "message": {
            "healthy": "站点探测正常；设备实时状态仍按各自时间判断",
            "degraded": "站点探测不完整或存在公网映射风险，请检查诊断结果",
            "unreachable": "站点VPN不可达，暂停远程指令，开放任务等待对账",
            "stale": "站点健康采集已过期，暂停远程指令，开放任务等待对账",
        }[status],
    }


def network_blocks_control(db):
    state = network_health_snapshot(db)
    return state["configured"] and state["status"] != "healthy"
