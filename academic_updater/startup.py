"""Optional current-user Windows login startup; no administrator access."""
import os
import subprocess
from pathlib import Path
from .network import AppError

KEY=r'Software\Microsoft\Windows\CurrentVersion\Run'
NAME='AcademicUpdater'


def command():
    script=Path(__file__).resolve().parents[1]/'Start.ps1'
    return subprocess.list2cmdline(['powershell.exe','-NoProfile','-WindowStyle','Hidden','-File',str(script),'-NoBrowser'])


def status():
    if os.name!='nt':return {'supported':False,'enabled':False}
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,KEY) as key:value,_=winreg.QueryValueEx(key,NAME)
        return {'supported':True,'enabled':value==command()}
    except FileNotFoundError:return {'supported':True,'enabled':False}


def configure(enabled):
    if os.name!='nt':raise AppError('startup_unavailable')
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,KEY) as key:
        if enabled:winreg.SetValueEx(key,NAME,0,winreg.REG_SZ,command())
        else:
            try:winreg.DeleteValue(key,NAME)
            except FileNotFoundError:pass
    return status()
