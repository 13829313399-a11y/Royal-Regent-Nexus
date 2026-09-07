"""Validated, non-secret topology. This module never changes network settings."""

import ipaddress
import json
import re
from pathlib import Path

PRIVATE = [
    ipaddress.ip_network(c) for c in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
]
TAILNET = ipaddress.ip_network("100.64.0.0/10")


def load_config(path):
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    validate(value)
    return value


def validate(config):
    if set(config) != {
        "version",
        "factory_id",
        "site_id",
        "gateway_key",
        "vpn",
        "lan",
        "printers",
    }:
        raise ValueError("invalid_config_fields")
    if (
        config["version"] != 1
        or config["factory_id"] != "huakang-a"
        or config["site_id"] != "3dsite-huakang-a-heyuan"
    ):
        raise ValueError("invalid_site_scope")
    if not re.fullmatch(r"huakang-a-heyuan-vpn-[a-z0-9-]{1,24}", config["gateway_key"]):
        raise ValueError("invalid_gateway_key")
    vpn, lan = config["vpn"], config["lan"]
    if set(vpn) != {
        "type",
        "interface",
        "connector_ip",
        "gateway_ip",
        "cloud_endpoint",
        "cloud_public_key",
        "gateway_public_key",
    }:
        raise ValueError("invalid_vpn_fields")
    if set(lan) != {"cidr", "interface", "gateway_ip", "snat"}:
        raise ValueError("invalid_lan_fields")
    if vpn["type"] not in {"wireguard", "tailscale", "ipsec"} or not isinstance(
        lan["snat"], bool
    ):
        raise ValueError("invalid_vpn_type")
    for interface in (vpn["interface"], lan["interface"]):
        if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_.-]{0,14}", interface):
            raise ValueError("invalid_interface")
    if vpn["interface"] == lan["interface"]:
        raise ValueError("interfaces_must_differ")
    vlan = ipaddress.ip_network(lan["cidr"], strict=True)
    if (
        vlan.version != 4
        or not 16 <= vlan.prefixlen <= 28
        or not any(vlan.subnet_of(n) for n in PRIVATE)
    ):
        raise ValueError("dedicated_rfc1918_vlan_required")
    connector = ipaddress.ip_address(vpn["connector_ip"])
    gateway = ipaddress.ip_address(vpn["gateway_ip"])
    for addr in (connector, gateway):
        if (
            addr.version != 4
            or not any(addr in n for n in PRIVATE + [TAILNET])
            or addr in vlan
        ):
            raise ValueError("invalid_transit_address")
    if connector == gateway:
        raise ValueError("transit_addresses_must_differ")
    lan_gateway = ipaddress.ip_address(lan["gateway_ip"])
    if lan_gateway not in vlan or lan_gateway in (
        vlan.network_address,
        vlan.broadcast_address,
    ):
        raise ValueError("invalid_lan_gateway")
    if not re.fullmatch(r"[a-zA-Z0-9.-]+:[0-9]{1,5}", vpn["cloud_endpoint"]):
        raise ValueError("invalid_cloud_endpoint")
    if not 1 <= int(vpn["cloud_endpoint"].rsplit(":", 1)[1]) <= 65535:
        raise ValueError("invalid_cloud_port")
    for name in ("cloud_public_key", "gateway_public_key"):
        if (
            not re.fullmatch(r"[A-Za-z0-9+/]{43}=", vpn[name])
            and vpn[name] != "REPLACE_PUBLIC_KEY"
        ):
            raise ValueError("invalid_public_key")
    printers = config["printers"]
    if not isinstance(printers, list) or len(printers) != 11:
        raise ValueError("exactly_11_printers_required")
    ips, numbers = set(), set()
    for printer in printers:
        if set(printer) != {"machine_no", "ip", "credential_ref", "cert_sha256"}:
            raise ValueError("printer_secrets_must_use_references")
        addr = ipaddress.ip_address(printer["ip"])
        if addr not in vlan or addr in (
            vlan.network_address,
            vlan.broadcast_address,
            lan_gateway,
        ):
            raise ValueError("invalid_printer_address")
        if (
            type(printer["machine_no"]) is not int
            or not 1 <= printer["machine_no"] <= 11
        ):
            raise ValueError("invalid_machine_no")
        if printer["ip"] in ips or printer["machine_no"] in numbers:
            raise ValueError("duplicate_printer")
        if not re.fullmatch(r"printer-[0-9]{2}", printer["credential_ref"]):
            raise ValueError("invalid_credential_reference")
        if (
            not re.fullmatch(r"[a-fA-F0-9]{64}", printer["cert_sha256"])
            and printer["cert_sha256"] != "REPLACE_VERIFIED_CERT_SHA256"
        ):
            raise ValueError("verified_certificate_pin_required")
        ips.add(printer["ip"])
        numbers.add(printer["machine_no"])
    return config
