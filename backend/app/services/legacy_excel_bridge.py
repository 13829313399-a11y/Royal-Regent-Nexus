from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from urllib.parse import quote
from uuid import uuid4
import os
import shutil
import subprocess


LEGACY_XLS_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")
CONVERSION_TIMEOUT_SECONDS = 120
_CONVERSION_LOCK = Lock()


class LegacyExcelConversionError(ValueError):
    pass


def is_legacy_xls_workbook(content: bytes) -> bool:
    return content.startswith(LEGACY_XLS_MAGIC)


def convert_legacy_xls_to_xlsx(content: bytes) -> bytes:
    return _convert_workbook(
        content,
        source_suffix=".xls",
        target_suffix=".xlsx",
        output_password=None,
    )


def convert_xlsx_to_legacy_xls(
    content: bytes,
    *,
    output_password: str | None,
) -> bytes:
    return _convert_workbook(
        content,
        source_suffix=".xlsx",
        target_suffix=".xls",
        output_password=output_password,
    )


def _convert_workbook(
    content: bytes,
    *,
    source_suffix: str,
    target_suffix: str,
    output_password: str | None,
) -> bytes:
    with _CONVERSION_LOCK, TemporaryDirectory(prefix="customer-order-xls-") as temp_dir:
        work_dir = Path(temp_dir)
        input_path = work_dir / f"source{source_suffix}"
        output_path = work_dir / f"converted{target_suffix}"
        input_path.write_bytes(content)

        if os.name == "nt":
            _run_windows_excel(
                input_path=input_path,
                output_path=output_path,
                output_password=output_password,
            )
        else:
            _run_libreoffice(
                input_path=input_path,
                output_path=output_path,
                output_password=output_password,
                work_dir=work_dir,
            )

        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise LegacyExcelConversionError("旧版 Excel 转换完成后没有生成有效文件")
        return output_path.read_bytes()


def _run_windows_excel(
    *,
    input_path: Path,
    output_path: Path,
    output_password: str | None,
) -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "convert_excel_workbook.ps1"
    if not powershell or not script_path.is_file():
        raise LegacyExcelConversionError(
            "服务器缺少旧版 Excel 转换组件，暂时无法处理 .xls 排期"
        )
    mode = "to-xls" if output_path.suffix.lower() == ".xls" else "to-xlsx"
    _run_command(
        [
            powershell,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            "-Mode",
            mode,
            "-InputPath",
            str(input_path),
            "-OutputPath",
            str(output_path),
            "-Password",
            output_password or "",
        ],
        missing_component_message=(
            "本机无法调用 Microsoft Excel 转换旧版 .xls 排期，请确认已安装 Excel"
        ),
    )


def _run_libreoffice(
    *,
    input_path: Path,
    output_path: Path,
    output_password: str | None,
    work_dir: Path,
) -> None:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    system_python = Path("/usr/bin/python3")
    script_path = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "convert_libreoffice_workbook.py"
    )
    if not soffice or not system_python.is_file() or not script_path.is_file():
        raise LegacyExcelConversionError(
            "服务器缺少 LibreOffice 旧版 Excel 转换组件，暂时无法处理 .xls 排期"
        )

    pipe_name = f"customer_order_{uuid4().hex}"
    connection = f"uno:pipe,name={pipe_name};urp;StarOffice.ComponentContext"
    profile_path = work_dir / "libreoffice-profile"
    profile_url = "file:///" + quote(profile_path.as_posix().lstrip("/"))
    office_process = subprocess.Popen(
        [
            soffice,
            "--headless",
            "--nologo",
            "--nodefault",
            "--nofirststartwizard",
            "--nolockcheck",
            f"-env:UserInstallation={profile_url}",
            f"--accept=pipe,name={pipe_name};urp;StarOffice.ServiceManager",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        mode = "to-xls" if output_path.suffix.lower() == ".xls" else "to-xlsx"
        _run_command(
            [
                str(system_python),
                str(script_path),
                "--connection",
                connection,
                "--mode",
                mode,
                "--input",
                str(input_path),
                "--output",
                str(output_path),
                "--password",
                output_password or "",
            ],
            missing_component_message=(
                "LibreOffice 无法转换旧版 .xls 排期，请检查服务端转换组件"
            ),
        )
    finally:
        office_process.terminate()
        try:
            office_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            office_process.kill()
            office_process.wait(timeout=5)


def _run_command(command: list[str], *, missing_component_message: str) -> None:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=CONVERSION_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LegacyExcelConversionError(missing_component_message) from exc
    if completed.returncode == 0:
        return
    detail = (completed.stderr or completed.stdout or "").strip()
    if len(detail) > 600:
        detail = detail[-600:]
    raise LegacyExcelConversionError(
        f"{missing_component_message}"
        + (f"：{detail}" if detail else "")
    )
