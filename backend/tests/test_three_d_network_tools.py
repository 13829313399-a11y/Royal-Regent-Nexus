import hashlib
import importlib.util
import json
import socket
import ssl
import sys
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

TOOLS = Path(__file__).resolve().parents[2] / "deploy" / "three-d-printing" / "network"
sys.path.insert(0, str(TOOLS))
import network_config


def module(name):
    spec = importlib.util.spec_from_file_location(
        "pr05_" + name, TOOLS / (name + ".py")
    )
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


doctor, render = module("doctor"), module("render")


@pytest.fixture
def config():
    return network_config.load_config(TOOLS / "config.example.json")


@pytest.mark.parametrize(
    "change",
    [
        "public_printer",
        "duplicate",
        "secret",
        "interface_injection",
        "wrong_factory",
        "default_route",
        "path_traversal",
    ],
)
def test_rejects_unsafe_topology(config, change):
    if change == "public_printer":
        config["printers"][0]["ip"] = "8.8.8.8"
    elif change == "duplicate":
        config["printers"][1]["machine_no"] = 1
    elif change == "secret":
        config["printers"][0]["access_code"] = "never-print-this"
    elif change == "interface_injection":
        config["vpn"]["interface"] = "wg0;id"
    elif change == "wrong_factory":
        config["factory_id"] = "huaxing"
    elif change == "default_route":
        config["lan"]["cidr"] = "0.0.0.0/0"
    else:
        config["printers"][0]["credential_ref"] = "../private-key"
    with pytest.raises(ValueError):
        network_config.validate(config)


def test_templates_restrict_exact_printers_without_global_firewall_reset(config):
    files = render.templates(config)
    assert all("flush ruleset;" not in value for value in files.values())
    assert "PrivateKey =" not in files["gateway.wg.conf"]
    assert "PersistentKeepalive = 25" in files["gateway.wg.conf"]
    assert "0.0.0.0/0" not in files["cloud.wg.conf"]
    assert "tcp dport 8883" in files["gateway.nft"]
    assert "ip daddr 10.33.30.0/24 counter drop" in files["gateway.nft"]
    assert "snat to" not in files["gateway.nft"]
    config["lan"]["snat"] = True
    assert "ip saddr 10.250.30.10" in render.templates(config)["gateway.nft"]
    policy = json.loads(files["tailscale-policy.json"])
    assert policy["acls"] == []
    assert policy["grants"] == [
        {
            "src": ["tag:three-d-connector"],
            "dst": [p["ip"] for p in config["printers"]],
            "ip": ["tcp:8883"],
        }
    ]
    assert len(policy["tests"][1]["deny"]) == 11
    assert "--snat-subnet-routes=false" in files["tailscale-commands.txt"]


def test_dnat_audit_checks_other_public_ports_and_fails_closed_on_maps(config):
    assert doctor.exposure_audit({"nftables": []}, config) == "ok"
    nat = {
        "nftables": [
            {"rule": {"expr": [{"dnat": {"addr": "10.33.30.101", "port": 8883}}]}}
        ]
    }
    assert doctor.exposure_audit(nat, config) == "unsafe"
    nat["nftables"][0]["rule"]["expr"][0]["dnat"]["addr"] = {
        "map": "@dynamic-device-map"
    }
    assert doctor.exposure_audit(nat, config) == "unknown"
    assert doctor.exposure_audit({}, config) == "unknown"


def test_validate_is_offline_and_error_output_is_redacted(
    config, tmp_path, monkeypatch, capsys
):
    def no_probe(*args, **kwargs):
        pytest.fail("validate must not access network")

    monkeypatch.setattr(doctor, "report", no_probe)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    assert doctor.main(["--config", str(path)]) == 0
    config["printers"][0]["access_code"] = "PRIVATE-SENTINEL"
    path.write_text(json.dumps(config))
    assert doctor.main(["--config", str(path)]) == 2
    assert "PRIVATE-SENTINEL" not in capsys.readouterr().out


def test_wireguard_collector_never_requests_private_key_dump(config, monkeypatch):
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(
            stdout=config["vpn"]["gateway_public_key"]
            + " "
            + str(int(doctor.time.time()))
            + "\n"
        )

    monkeypatch.setattr(doctor.subprocess, "run", run)
    assert doctor.tunnel_health(config) == "ok"
    assert calls == [["wg", "show", "wg-3d", "latest-handshakes"]]


@pytest.fixture
def mqtt_server(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "local-test-printer")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(minutes=1))
        .not_valid_after(datetime.now(UTC) + timedelta(hours=1))
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(5)
    seen = []

    def serve():
        try:
            raw, _ = listener.accept()
            with context.wrap_socket(raw, server_side=True) as sock:
                sock.settimeout(3)
                header, body = doctor.mqtt_packet(sock)
                seen.append((header, body))
                sock.sendall(b"\x20\x02\x00\x00")
                seen.append(doctor.mqtt_packet(sock))
                sock.sendall(b"\x90\x03\x00\x01\x00")
                seen.append(doctor.mqtt_packet(sock))
        except (OSError, ValueError):
            pass

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield (
        listener.getsockname()[1],
        hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest(),
        seen,
    )
    listener.close()
    thread.join(timeout=6)


@pytest.mark.parametrize(
    "correct_pin,authenticate", [(True, True), (False, True), (True, False)]
)
def test_real_local_tls_mqtt_probe_checks_identity_before_sending_credentials(
    config, tmp_path, monkeypatch, mqtt_server, correct_pin, authenticate
):
    port, pin, seen = mqtt_server
    printer = config["printers"][0]
    printer["cert_sha256"] = pin if correct_pin else "0" * 64
    secret = tmp_path / "printer-01.json"
    secret.write_text(
        json.dumps({"serial": "TEST-DEVICE", "access_code": "test-access-code"})
    )
    secret.chmod(0o600)
    original_socket = socket.socket

    class LocalSocket(original_socket):
        def bind(self, address):
            assert address == (config["vpn"]["connector_ip"], 0)
            return super().bind(("127.0.0.1", 0))

        def connect(self, address):
            assert address == (printer["ip"], 8883)
            return super().connect(("127.0.0.1", port))

    monkeypatch.setattr(
        doctor,
        "socket",
        SimpleNamespace(
            socket=LocalSocket, AF_INET=socket.AF_INET, SOCK_STREAM=socket.SOCK_STREAM
        ),
    )
    monkeypatch.setattr(doctor, "route_ok", lambda *_: True)
    if not authenticate or not correct_pin:
        monkeypatch.setattr(
            doctor, "read_secret", lambda *_: pytest.fail("must not read credentials")
        )
    result = doctor.probe_printer(config, printer, tmp_path, 2, authenticate)
    assert result["tcp"] == "ok"
    if correct_pin and authenticate:
        assert result["tls"] == result["mqtt"] == "ok"
        assert seen[0][0] == 0x10 and seen[1][0] == 0x82
        assert b"device/TEST-DEVICE/report" in seen[1][1]
    elif not correct_pin:
        assert result["tls"] == "failed" and result["mqtt"] == "skipped"
        assert seen == []
    else:
        assert result["tls"] == "ok" and result["mqtt"] == "skipped"
        assert seen == []
    assert "test-access-code" not in json.dumps(result)
    assert all(header >> 4 != 3 for header, _ in seen)  # No PUBLISH/control message.


def test_failed_route_never_opens_tcp(config, monkeypatch):
    monkeypatch.setattr(doctor, "route_ok", lambda *_: False)
    result = doctor.probe_printer(config, config["printers"][0], "unused")
    assert result["route"] == "failed" and result["tcp"] == "skipped"


def test_health_report_preserves_all_eleven_stages_without_secret_material(
    config, monkeypatch
):
    monkeypatch.setattr(
        doctor,
        "probe_printer",
        lambda c, p, *_: {
            "machine_no": p["machine_no"],
            "route": "ok",
            "tcp": "ok",
            "tls": "ok",
            "mqtt": "ok",
            "latency_ms": 1,
        },
    )
    monkeypatch.setattr(doctor, "tunnel_health", lambda *_: "ok")
    value = doctor.report(
        config, "unused", nft_documents=[{"nftables": []}, {"nftables": []}]
    )
    assert len(value["printers"]) == 11 and value["exposure"] == "ok"
    assert "credential_ref" not in json.dumps(
        value
    ) and "cert_sha256" not in json.dumps(value)


def test_upload_refuses_plain_http_before_reading_token():
    with pytest.raises(ValueError, match="https"):
        doctor.upload(
            {}, "http://example.invalid/api/three-d-printing/network/health", "unused"
        )


@pytest.mark.parametrize(
    "state,expected",
    [
        ("state=ESTABLISHED child-sas { printers { state=INSTALLED } }", "ok"),
        ("state=CONNECTING", "failed"),
    ],
)
def test_ipsec_requires_live_sa_not_just_stale_kernel_policy(
    config, monkeypatch, state, expected
):
    config["vpn"]["type"] = "ipsec"
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(stdout=state)

    monkeypatch.setattr(doctor.subprocess, "run", run)
    monkeypatch.setattr(doctor, "run_json", lambda *_: [{"dir": "out", "if_id": 330}])
    assert doctor.tunnel_health(config) == expected
    assert calls == [["swanctl", "--list-sas", "--ike", "heyuan-3d", "--raw"]]
