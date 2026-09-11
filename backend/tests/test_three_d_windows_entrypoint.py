"""Exercise the actual Windows menu and child PowerShell process, without networking."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import pytest

pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='Windows PowerShell entrypoint')
SOURCE = Path(__file__).resolve().parents[2] / 'deploy/three-d-printing/network'


@pytest.fixture
def launch_environment(tmp_path):
    package = tmp_path/'wechat_files'/'现场 配置包'
    package.mkdir(parents=True)
    for source,target in [('windows-site.ps1','windows-site.ps1'),('windows-start.ps1','Start.ps1')]:
        shutil.copyfile(SOURCE/source,package/target)
    (package/'Start.cmd').write_text('@echo off\npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start.ps1"\n',encoding='ascii')
    fake_bin=tmp_path/'stub-bin'; fake_bin.mkdir()
    compiler=tmp_path/'compile.ps1'
    compiler.write_text('''param([string]$Target)
Add-Type -OutputType ConsoleApplication -OutputAssembly $Target -TypeDefinition @'
using System;
using System.IO;
public class Program {
    public static int Main(string[] args) {
        File.AppendAllText(Environment.GetEnvironmentVariable("RR_TEST_CALLS"),string.Join(" ",args)+"\\n");
        if(args[0]=="status") Console.WriteLine("{\\"BackendState\\":\\""+Environment.GetEnvironmentVariable("RR_TEST_VPN_STATE")+"\\"}");
        if(args[0]=="ip") Console.WriteLine("100.64.0.2");
        return 0;
    }
}
'@
''',encoding='utf-8')
    subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(compiler),str(fake_bin/'tailscale.exe')],capture_output=True,check=True,timeout=30)
    env={**os.environ,'PATH':str(fake_bin)+os.pathsep+os.environ['PATH'],
         'RR_TEST_CALLS':str(tmp_path/'calls.txt')}
    return package,env


@pytest.mark.parametrize('via_menu',[True,False])
@pytest.mark.parametrize('vpn_state',['NeedsLogin','Running'])
def test_login_from_system32_and_chinese_package_path(launch_environment,via_menu,vpn_state):
    package,env=launch_environment
    env['RR_TEST_VPN_STATE']=vpn_state
    command=(['cmd.exe','/d','/c','call',str(package/'Start.cmd')] if via_menu else
        ['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(package/'windows-site.ps1'),'-Action','Login'])
    result=subprocess.run(command,input=b'3\r\n\r\n' if via_menu else b'',capture_output=True,
        cwd=Path(os.environ['SystemRoot'])/'System32',env=env,timeout=30)
    assert result.returncode==0,result.stderr.decode(errors='replace')
    assert b'Join-Path' not in result.stderr,result.stderr
    calls=Path(env['RR_TEST_CALLS']).read_text().splitlines()
    assert calls[0]=='status --json'
    assert calls[1]==('set --unattended=true' if vpn_state=='Running' else
        'up --unattended --accept-dns=false --timeout=60s')
    assert calls[2]=='ip -4'
