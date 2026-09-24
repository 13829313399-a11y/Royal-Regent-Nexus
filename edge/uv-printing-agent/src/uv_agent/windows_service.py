"""PyInstaller entrypoint: service session zero, no interactive UI dependency."""
import sys
import threading
from pathlib import Path
import servicemanager
import win32service
import win32serviceutil
from uv_agent.service import Agent, load_config, main


class UvAgentService(win32serviceutil.ServiceFramework):
    _svc_name_ = "RRUvAgent"
    _svc_display_name_ = "Royal Regent UV Read-only Agent"
    _svc_description_ = "Durable outbound UV evidence collection; no native printer commands."

    def __init__(self, args):
        super().__init__(args)
        self.stop = threading.Event()

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.stop.set()

    def SvcDoRun(self):
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\RoyalRegent\UVAgent") as key:
            config_path, _ = winreg.QueryValueEx(key, "ConfigPath")
        self.ReportServiceStatus(win32service.SERVICE_RUNNING)
        try:
            Agent(load_config(config_path)).run(self.stop)
        except Exception as error:
            # Do not write tokens, config paths or raw data to the event log.
            servicemanager.LogErrorMsg("UV agent stopped: "+type(error).__name__)
            raise


if __name__ == "__main__":
    if "--config" in sys.argv or "--help" in sys.argv:
        main()
    elif len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(UvAgentService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(UvAgentService)
