"""Run the field collector in Windows PowerShell using synthetic config only."""
import base64
import csv
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import threading

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, hmac, padding, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asymmetric_padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='Windows PowerShell field collector')
SOURCE = Path(__file__).resolve().parents[2] / 'deploy/three-d-printing/network/collect-studio-devices.ps1'
TARGETS = [(6, '10.33.30.106', 'printer-12'), (7, '10.33.30.107', 'printer-13'),
           (8, '10.33.30.108', 'printer-14'), (15, '10.33.30.115', 'printer-15'),
           (16, '10.33.30.116', 'printer-16')]


@pytest.fixture
def case(tmp_path):
    root = tmp_path / '现场 配置包'
    root.mkdir()
    inventory = root/'printers.csv'
    with inventory.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['machine_no', 'ip', 'credential_ref'])
        writer.writerows(TARGETS)
    private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    numbers = private.public_key().public_numbers()
    def b64(number):
        return base64.b64encode(number.to_bytes((number.bit_length()+7)//8, 'big')).decode()
    public = root/'recipient-public.xml'
    public.write_text(f'<RSAKeyValue><Modulus>{b64(numbers.n)}</Modulus><Exponent>{b64(numbers.e)}</Exponent></RSAKeyValue>')
    runner = root/'run.ps1'
    runner.write_text('''param([string]$Source,[string]$CaseFile)
$case=Get-Content -LiteralPath $CaseFile -Raw | ConvertFrom-Json
$extra=@{}
if ($case.discovery) { $extra.DiscoverCertificates=$true; $extra.CertificatePorts=[int[]]@($case.ports); $extra.ProbeTimeoutMs=500; $extra.MachineNumbers=[int[]]@($case.machines) }
& $Source -PrinterFile $case.inventory -OutputDirectory $case.output -PublicKeyFile $case.public -ConfigPath @($case.configs) @extra
''', encoding='utf-8-sig')
    return root, inventory, public, runner, private


def execute(case, configs, **options):
    root, inventory, public, runner, _ = case
    paths = []
    for i, config in enumerate(configs):
        path = root/f'config-{i}.conf'
        if config is not None:
            with path.open('w', encoding='utf-8-sig', newline='') as handle:
                handle.write(config if isinstance(config, str) else json.dumps(config))
        paths.append(path)
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.exists()}
    output = root/'collected'
    manifest = root/'case.json'
    manifest.write_text(json.dumps(dict(inventory=str(inventory), public=str(public), output=str(output), configs=[str(p) for p in paths], **options)), encoding='utf-8-sig')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
        str(runner), str(SOURCE), str(manifest)], cwd=Path(os.environ['SystemRoot'])/'System32',
        capture_output=True, timeout=40)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in before} == before
    reports = list(output.glob('*/collection-report.json'))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text(encoding='utf-8'))
    assert report['plaintext_credentials_written'] is False
    assert report['mqtt_authenticated'] is False
    assert report['files_uploaded'] is False
    raw_outputs = result.stdout + result.stderr + b''.join(p.read_bytes() for p in output.rglob('*') if p.is_file())
    return report, reports[0].parent, raw_outputs


def unseal(path, private):
    envelope = json.loads(path.read_text(encoding='utf-8'))
    assert envelope['algorithm'] == 'RSA-OAEP-SHA1+AES-256-CBC+HMAC-SHA256'
    wrapped, iv, ciphertext, tag = (base64.b64decode(envelope[k], validate=True) for k in ('wrapped_key','iv','ciphertext','tag'))
    keys = private.decrypt(wrapped, asymmetric_padding.OAEP(mgf=asymmetric_padding.MGF1(hashes.SHA1()), algorithm=hashes.SHA1(), label=None))
    assert len(keys) == 64
    check = hmac.HMAC(keys[32:], hashes.SHA256())
    check.update(wrapped + iv + ciphertext)
    check.verify(tag)
    decryptor = Cipher(algorithms.AES(keys[:32]), modes.CBC(iv)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpad = padding.PKCS7(128).unpadder()
    return json.loads(unpad.update(padded) + unpad.finalize())


def config(ip='10.33.30.106', serial='TESTSN06', code='SyntheticCode06'):
    return {'app': {'slicer_uuid':'isolated-slicer-id'},
            'user_access_dev_ip': {serial:ip}, 'user_access_code': {serial:code}}


def test_targeted_encrypted_export_decodes_current_and_legacy_ips_without_account_data(case):
    # Fixed vector independently generated with NumPy RandomState (MT19937),
    # seed FNV-1a('isolated-slicer-id')=249673849; plaintext 10.33.30.106.
    source = config(ip='840fa40f91d91520ce566256')
    source['user_access_dev_ip'].update(TESTSN07='10.33.30.107', UNRELATED_SN='10.33.30.200')
    source['access_code'] = {'TESTSN06':'OlderWrongCode', 'TESTSN07':'FallbackCode07', 'UNRELATED_SN':'UnrelatedPrinterSecret'}
    source['app']['access_token'] = 'NeverExportCloudAccountToken'
    report, output, raw = execute(case, [source])
    payload = unseal(output/report['encrypted_export'], case[-1])
    assert [(p['machine_no'], p['serial'], p['access_code'], p['credential_ref']) for p in payload['printers']] == [
        (6, 'TESTSN06', 'SyntheticCode06', 'printer-12'), (7, 'TESTSN07', 'FallbackCode07', 'printer-13')]
    assert all(p['mqtt_authenticated'] is False for p in payload['printers'])
    for secret in ('TESTSN06','TESTSN07','SyntheticCode06','FallbackCode07','OlderWrongCode','UNRELATED_SN','UnrelatedPrinterSecret','NeverExportCloudAccountToken'):
        assert secret.encode() not in raw
    assert 'NeverExportCloudAccountToken' not in json.dumps(payload)
    assert 'UnrelatedPrinterSecret' not in json.dumps(payload)
    assert len(list(output.iterdir())) == 2


@pytest.mark.parametrize('source,expected', [
    (None, 'not_found'),
    ('{"access_token":"SensitiveMalformedToken",', 'unreadable_or_unsupported'),
    ({'access_code':{'TESTSN06':'OnlyCodeNoIP'}}, 'no_saved_ip_mapping'),
])
def test_missing_or_unsupported_config_never_guesses_machine_from_serial_order(case, source, expected):
    report, output, raw = execute(case, [source])
    assert any(c['status'] == expected for c in report['config_sources'])
    assert report['encrypted_export'] == ''
    target_state = 'saved_ip_mapping_unavailable' if expected == 'no_saved_ip_mapping' else 'configuration_unavailable'
    assert all(p['status'] == target_state for p in report['targets'])
    if expected == 'unreadable_or_unsupported':
        assert report['config_sources'][0]['read_stage'] == 'parse_json'
        assert report['config_sources'][0]['issue_code'] == 'json_parse_or_root_unsupported'
    assert len(list(output.iterdir())) == 1
    assert b'SensitiveMalformedToken' not in raw and b'OnlyCodeNoIP' not in raw


@pytest.mark.parametrize('second', [
    config(code='syntheticCode06'),  # Case changes in a secret are a real conflict.
    config(serial='OTHER_TARGET_SN'),
    config(ip='10.33.30.107'),  # One physical serial cannot identify two target IPs.
])
def test_conflicting_cache_entries_are_not_exported(case, second):
    report, _, raw = execute(case, [config(), second])
    assert report['encrypted_export'] == ''
    assert report['targets'][0]['status'] == 'ambiguous_saved_identity_or_code'
    assert b'SyntheticCode06' not in raw and b'OTHER_TARGET_SN' not in raw


def test_identical_configs_deduplicate_without_overwriting(case):
    report, output, _ = execute(case, [config(), config()])
    payload = unseal(output/report['encrypted_export'], case[-1])
    assert len(payload['printers']) == 1


def test_missing_access_code_is_reported_without_plain_serial(case):
    report, _, raw = execute(case, [config(code='')])
    assert report['targets'][0]['status'] == 'access_code_missing_or_invalid'
    assert report['encrypted_export'] == '' and b'TESTSN06' not in raw


@pytest.mark.parametrize('newline', ['\n', '\r\n'])
def test_windows_checksum_trailer_is_supported_without_editing_source(case, newline):
    body = json.dumps(config(ip='840fa40f91d91520ce566256'), indent=4).replace('\n', newline)
    checksum = hashlib.md5(body.encode()).hexdigest().upper()
    source = body + newline + '# MD5 checksum ' + checksum + newline
    report, output, raw = execute(case, [source])
    assert report['collector_version'] == 3
    assert report['config_sources'][0]['format'] == 'json_with_windows_checksum'
    assert report['config_sources'][0]['checksum'] == 'present_not_verified'
    assert report['config_sources'][0]['mapping_entries'] == 1
    assert report['config_sources'][0]['matched_target_entries'] == 1
    payload = unseal(output/report['encrypted_export'], case[-1])
    assert payload['printers'][0]['serial'] == 'TESTSN06'
    assert payload['printers'][0]['access_code'] == 'SyntheticCode06'
    assert b'SyntheticCode06' not in raw and b'TESTSN06' not in raw


@pytest.mark.parametrize('tail', ['\n# MD5 checksum not-a-checksum\n', '\nTRAILER_ACCOUNT_SECRET', '\n{"access_token":"TRAILER_ACCOUNT_SECRET"}'])
def test_arbitrary_trailing_data_is_not_silently_stripped_or_exposed(case, tail):
    report, _, raw = execute(case, [json.dumps(config()) + tail])
    assert report['encrypted_export'] == ''
    assert report['targets'][0]['status'] == 'configuration_unavailable'
    assert report['config_sources'][0]['issue_code'] == 'json_parse_or_root_unsupported'
    assert b'TRAILER_ACCOUNT_SECRET' not in raw and b'SyntheticCode06' not in raw


@contextmanager
def certificate_peer(root, serial='TESTSN06', stalled=False, address='127.0.0.1'):
    """A real TLS endpoint records any application data sent by the collector."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, serial)])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=1))
            .sign(key, hashes.SHA256()))
    label = str(cert.serial_number)
    cert_path, key_path = root/f'{label}.crt', root/f'{label}.key'
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert_path, key_path)
    listener = socket.socket()
    listener.bind((address, 0))
    listener.listen()
    listener.settimeout(10)
    received, errors = [], []
    def serve():
        try:
            conn, _ = listener.accept()
            with conn:
                conn.settimeout(3)
                if stalled:
                    # Accept TCP and consume the ClientHello without answering.
                    while conn.recv(16384):
                        pass
                else:
                    with context.wrap_socket(conn, server_side=True) as stream:
                        received.append(stream.recv(4096))
        except OSError as exc:
            errors.append(type(exc).__name__)
    worker = threading.Thread(target=serve, daemon=True)
    worker.start()
    try:
        yield listener.getsockname()[1], cert.fingerprint(hashes.SHA256()).hex(), received
    finally:
        listener.close()
        worker.join(timeout=4)
        assert not worker.is_alive()
        assert not errors, errors


def local_inventory(case, pin='', rows=None):
    with case[1].open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['machine_no','ip','credential_ref','observed_cert_sha256'])
        writer.writerows(rows or [(6,'127.0.0.1','printer-12',pin)])


def test_certificate_discovery_matches_saved_code_without_ip_mapping(case):
    with certificate_peer(case[0]) as (port, pin, received):
        local_inventory(case, pin)
        source = {'access_code': {'TESTSN06':'CertificateMatchedCode', 'UNRELATED_SN':'UnrelatedSecret'},
                  'app': {'access_token':'PrivateCloudToken'}}
        report, output, raw = execute(case, [source], discovery=True, ports=[port], machines=[6])
    assert received == [b'']  # TLS handshake only; no MQTT, password or FTPS commands.
    assert report['targets'][0]['status'] == 'saved_credentials_collected_not_authenticated'
    assert report['config_sources'][0]['access_code_entries'] == 2
    discovery = report['certificate_discovery'][0]
    assert discovery['pin_status'] == 'matches_previous_observation'
    payload = unseal(output/report['encrypted_export'],case[-1])
    record = payload['printers'][0]
    assert (record['machine_no'],record['serial'],record['access_code'],record['credential_ref']) == (6,'TESTSN06','CertificateMatchedCode','printer-12')
    assert record['identity_source'] == 'tls_certificate_name_and_saved_code'
    assert record['observed_cert_sha256'] == pin
    assert record['physical_identity_verified'] is False
    for secret in ('TESTSN06','CertificateMatchedCode','UnrelatedSecret','PrivateCloudToken'):
        assert secret.encode() not in raw
    assert 'PrivateCloudToken' not in json.dumps(payload)


def test_certificate_probe_timeout_falls_back_to_second_port(case):
    with certificate_peer(case[0],stalled=True) as (first, _, _), certificate_peer(case[0]) as (second, _, received):
        local_inventory(case)
        report, output, _ = execute(case,[{'access_code':{'TESTSN06':'FallbackSavedCode'}}],discovery=True,ports=[first,second],machines=[6])
    assert received == [b'']
    assert [a['status'] for a in report['certificate_discovery'][0]['attempts']] == ['tls_timeout','certificate_observed']
    record = unseal(output/report['encrypted_export'],case[-1])['printers'][0]
    assert record['certificate_port'] == second
    assert record['pin_status'] == 'first_observation_not_verified'


@pytest.mark.parametrize('problem', ['pin_mismatch','identity_conflict','code_conflict','case_mismatch','missing_code','unsupported_name'])
def test_certificate_discovery_refuses_mismatches_without_exposing_secrets(case, problem):
    serial='Not A Device SN' if problem=='unsupported_name' else 'TESTSN06'
    with certificate_peer(case[0],serial=serial) as (port,pin,received):
        local_inventory(case,'0'*64 if problem=='pin_mismatch' else pin)
        source={'access_code':{'TESTSN06':'SavedDeviceSecret'}}
        configs=[source]
        expected='ambiguous_saved_identity_or_code'
        if problem=='pin_mismatch':
            source.update(user_access_dev_ip={'TESTSN06':'127.0.0.1'})
            expected='certificate_pin_mismatch'
        elif problem=='identity_conflict':
            source.update(user_access_dev_ip={'OLD_SN':'127.0.0.1'})
            source['access_code']['OLD_SN']='OldSavedCode'
        elif problem=='code_conflict':
            configs.append({'access_code':{'TESTSN06':'DifferentCode'}})
        elif problem in ('case_mismatch','missing_code'):
            source['access_code']={'testsn06':'SavedDeviceSecret'} if problem=='case_mismatch' else {}
            expected='access_code_missing_or_invalid'
        elif problem=='unsupported_name':
            expected='saved_ip_mapping_unavailable'
        report,_,raw=execute(case,configs,discovery=True,ports=[port],machines=[6])
    assert received==[b'']
    assert report['encrypted_export']==''
    assert report['targets'][0]['status']==expected
    for secret in ('TESTSN06','SavedDeviceSecret','OLD_SN','OldSavedCode','DifferentCode','Not A Device SN'):
        assert secret.encode() not in raw
