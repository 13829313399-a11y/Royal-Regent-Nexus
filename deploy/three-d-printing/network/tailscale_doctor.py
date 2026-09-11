"""Cloud-side Tailscale probes; Windows gateway needs no Linux VLAN/firewall files."""
import argparse
import ipaddress
import json
import re
from pathlib import Path
import doctor


def from_site_report(site):
    ips = (site.get('tailscale') or {}).get('ip') or []
    gateway = next((str(ipaddress.IPv4Address(ip)) for ip in ips if ':' not in ip), None)
    if not gateway or ipaddress.ip_address(gateway) not in ipaddress.ip_network('100.64.0.0/10'):
        raise ValueError('现场电脑尚未登录 Tailscale')
    printers=[]
    for p in site['printers']:
        if p['tcp']!='ok' or p['tls']!='observed' or not re.fullmatch('[a-fA-F0-9]{64}',p['observed_cert_sha256']):
            raise ValueError(f"机台 {p['machine_no']} 尚未完成现场 TLS 检测")
        printers.append({'machine_no':p['machine_no'],'ip':p['ip'],
            'credential_ref':f"printer-{int(p['machine_no']):02}",
            'cert_sha256':p['observed_cert_sha256']})
    result={'gateway_ip':gateway,'printers':printers}
    validate(result)
    return result


def validate(data):
    gateway=ipaddress.ip_address(data['gateway_ip'])
    if gateway not in ipaddress.ip_network('100.64.0.0/10'):
        raise ValueError('Expected Windows gateway Tailscale IPv4')
    rows=data['printers']
    if len(rows)!=11 or {int(p['machine_no']) for p in rows}!=set(range(1,12)):
        raise ValueError('Expected machines 1 to 11')
    addresses=set()
    for p in rows:
        ip=ipaddress.IPv4Address(p['ip'])
        if not any(ip in ipaddress.ip_network(n) for n in ['10.0.0.0/8','172.16.0.0/12','192.168.0.0/16']) or str(ip) in addresses:
            raise ValueError('Expected distinct printer LAN IPv4 addresses')
        addresses.add(str(ip))
        if not re.fullmatch('[a-fA-F0-9]{64}',p['cert_sha256']):
            raise ValueError('Missing onsite certificate hash')


def probe(data):
    validate(data)
    status=doctor.run_json(['tailscale','status','--json'])
    source=next((ip for ip in status.get('TailscaleIPs',[]) if ':' not in ip),None)
    if status.get('BackendState')!='Running' or not source:
        raise ValueError('Cloud Tailscale is not connected')
    config={'factory_id':'huakang-a','site_id':'3dsite-huakang-a-heyuan',
        'gateway_key':'huakang-a-heyuan-vpn-windows',
        'vpn':{'type':'tailscale','interface':'tailscale0','connector_ip':source,'gateway_ip':data['gateway_ip']},
        'printers':data['printers']}
    # Exposure remains unknown; TCP/TLS results are measured, never fabricated.
    # DERP relay round trips can exceed the LAN probe's three-second timeout.
    return doctor.report(config,None,timeout=10,authenticate=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True)
    parser.add_argument('--site-report',help='Build config from an onsite report after matching physical machine identities')
    parser.add_argument('--report-url')
    parser.add_argument('--token-file')
    args=parser.parse_args()
    if args.site_report:
        data=from_site_report(json.loads(Path(args.site_report).read_text(encoding='utf-8-sig')))
        Path(args.config).write_text(json.dumps(data,indent=2),encoding='utf-8')
        print('Prepared Windows gateway and eleven printer endpoints. No sessions started.')
        return 0
    result=probe(json.loads(Path(args.config).read_text(encoding='utf-8-sig')))
    if args.report_url: doctor.upload(result,args.report_url,args.token_file)
    print(json.dumps(result))
    return 0 if result['tunnel']=='ok' and all(p['tls']=='ok' for p in result['printers']) else 1


if __name__=='__main__': raise SystemExit(main())
