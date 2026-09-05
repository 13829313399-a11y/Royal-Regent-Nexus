"""Generate reviewable VPN/ACL files; never install, apply or reload them."""

import argparse
import json
from pathlib import Path

from network_config import load_config


def templates(config):
    vpn, lan = config["vpn"], config["lan"]
    peers = ", ".join(p["ip"] for p in config["printers"])
    routes = ", ".join(p["ip"] + "/32" for p in config["printers"])
    connector, gateway = vpn["connector_ip"], vpn["gateway_ip"]
    iface, vlan_if = vpn["interface"], lan["interface"]
    cloud_wg = f"""# Review addresses and replace public keys before activation.
[Interface]
Address = {connector}/32
ListenPort = {vpn["cloud_endpoint"].rsplit(":", 1)[1]}
PostUp = wg set %i private-key /run/secrets/three-d-wg-cloud.key

[Peer]
PublicKey = {vpn["gateway_public_key"]}
AllowedIPs = {gateway}/32, {routes}
"""
    gateway_wg = f"""[Interface]
Address = {gateway}/32
PostUp = wg set %i private-key /run/secrets/three-d-wg-gateway.key

[Peer]
PublicKey = {vpn["cloud_public_key"]}
Endpoint = {vpn["cloud_endpoint"]}
AllowedIPs = {connector}/32
PersistentKeepalive = 25
"""
    gateway_nft = f'''# Dedicated 3D table only. No flush ruleset. Existing firewall must also permit this path.
table inet rr_3d_gateway {{
  set printers {{ type ipv4_addr; elements = {{ {peers} }}; }}
  chain forward {{
    type filter hook forward priority -20; policy accept;
    iifname "{iface}" oifname "{vlan_if}" ip saddr {connector} ip daddr @printers tcp dport 8883 ct state new,established counter accept
    iifname "{vlan_if}" oifname "{iface}" ip saddr @printers ip daddr {connector} ct state established,related counter accept
    ip daddr {lan["cidr"]} counter drop
    ip saddr {lan["cidr"]} counter drop
    oifname "{vlan_if}" counter drop
    iifname "{vlan_if}" counter drop
  }}
  chain output {{
    type filter hook output priority -20; policy accept;
    ip daddr {lan["cidr"]} counter drop
    oifname "{vlan_if}" counter drop
  }}
}}
'''
    if lan["snat"]:
        gateway_nft += f'''table ip rr_3d_snat {{
  chain postrouting {{
    type nat hook postrouting priority srcnat; policy accept;
    iifname "{iface}" oifname "{vlan_if}" ip saddr {connector} ip daddr {{ {peers} }} tcp dport 8883 snat to {lan["gateway_ip"]}
  }}
}}
'''
    cloud_nft = f'''table inet rr_3d_cloud {{
  chain output {{
    type filter hook output priority -20; policy accept;
    oifname "{iface}" ip saddr {connector} ip daddr {{ {peers} }} tcp dport 8883 counter accept
    ip daddr {lan["cidr"]} counter drop
  }}
  chain forward {{
    type filter hook forward priority -20; policy accept;
    ip daddr {lan["cidr"]} counter drop
  }}
}}
'''
    policy = {
        "tagOwners": {
            "tag:three-d-connector": ["autogroup:admin"],
            "tag:heyuan-3d-router": ["autogroup:admin"],
            "tag:non-connector-test": ["autogroup:admin"],
        },
        "acls": [],
        "grants": [
            {
                "src": ["tag:three-d-connector"],
                "dst": [p["ip"] for p in config["printers"]],
                "ip": ["tcp:8883"],
            }
        ],
        "autoApprovers": {"routes": {lan["cidr"]: ["tag:heyuan-3d-router"]}},
        "tests": [
            {
                "src": "tag:three-d-connector",
                "accept": [p["ip"] + ":8883" for p in config["printers"]],
                "deny": [
                    config["printers"][0]["ip"] + ":22",
                    config["printers"][0]["ip"] + ":21",
                ],
            },
            {
                "src": "tag:non-connector-test",
                "deny": [p["ip"] + ":8883" for p in config["printers"]],
            },
        ],
    }
    tailscale = f"""# Review and run on the indicated dedicated hosts, after installing Tailscale.
# Gateway: do NOT accept the route it advertises; disable blanket Tailscale SNAT.
tailscale up --advertise-tags=tag:heyuan-3d-router --advertise-routes={lan["cidr"]} --snat-subnet-routes=false --accept-routes=false --accept-dns=false
# Cloud Connector host:
tailscale up --advertise-tags=tag:three-d-connector --accept-routes=true --accept-dns=false
# Apply reviewed full-tailnet policy in the admin console and verify its tests.
# Render interface=tailscale0 and the actual Tailscale IPs. Optional SNAT is the narrow nft rule only.
"""

    # XFRM route-based IPsec uses the same dedicated interface ACLs. Certificate files stay outside Git.
    def ipsec(cloud):
        local, remote = ("cloud", "gateway") if cloud else ("gateway", "cloud")
        local_ts, remote_ts = (
            (connector + "/32", routes) if cloud else (routes, connector + "/32")
        )
        remote_addr = "%any" if cloud else vpn["cloud_endpoint"].rsplit(":", 1)[0]
        return f"""connections {{
  heyuan-3d {{
    version = 2
    remote_addrs = {remote_addr}
    local {{
      auth = pubkey
      certs = {local}.crt
      id = {local}.three-d.internal
    }}
    remote {{
      auth = pubkey
      id = {remote}.three-d.internal
    }}
    children {{ printers {{
      local_ts = {local_ts}
      remote_ts = {remote_ts}
      if_id_in = 330
      if_id_out = 330
      start_action = {"none" if cloud else "start"}
      dpd_action = restart
    }} }}
    dpd_delay = 30s
    mobike = no
  }}
}}
# Install CA/certs and private key via swanctl credential directories; never paste keys here.
"""

    return {
        "cloud.wg.conf": cloud_wg,
        "gateway.wg.conf": gateway_wg,
        "gateway.nft": gateway_nft,
        "cloud.nft": cloud_nft,
        "tailscale-policy.json": json.dumps(policy, indent=2),
        "tailscale-commands.txt": tailscale,
        "cloud.swanctl.conf": ipsec(True),
        "gateway.swanctl.conf": ipsec(False),
        "gateway-sysctl.conf": "net.ipv4.ip_forward = 1\n",
        "routes.txt": f"""# Pure routing: on the printer VLAN default router (not the cloud):
ip route add {connector}/32 via {lan["gateway_ip"]}
# XFRM mode only, both hosts: create reviewed interface bound to the real underlay.
ip link add {iface} type xfrm dev REPLACE_UNDERLAY if_id 330
ip link set {iface} up
# Cloud only: assign the Connector source and route the exact printer hosts via XFRM.
ip address add {connector}/32 dev {iface}
"""
        + "\n".join(
            f"ip route add {p['ip']}/32 dev {iface} src {connector}"
            for p in config["printers"]
        )
        + f"\n# IPsec gateway return route:\nip route add {connector}/32 dev {iface}\n",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    try:
        files = templates(load_config(args.config))
        out = Path(args.output_dir)
        out.mkdir(parents=True, exist_ok=False)
        for name, content in files.items():
            (out / name).write_text(content + "\n", encoding="utf-8")
        print(json.dumps({"status": "rendered_not_applied", "file_count": len(files)}))
        return 0
    except (ValueError, KeyError, TypeError, OSError):
        print('{"status":"error","code":"invalid_config_or_output_exists"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
