# -*- coding: utf-8 -*-
"""Kill zombie python/camoufox processes < 5MB, keep big ones (hermes)."""
import subprocess, re

def get_procs():
    r = subprocess.run(['tasklist', '/fo', 'csv'], capture_output=True)
    raw = r.stdout
    if b'\x00' in raw[:10]:
        txt = raw.decode('utf-16', 'ignore')
    else:
        txt = raw.decode('cp866', 'ignore')
    return txt

txt = get_procs()
lines = txt.splitlines()
targets = []
for line in lines:
    low = line.lower()
    if 'python.exe' in low or 'camoufox' in low or 'firefox' in low:
        parts = [p.strip('"').strip() for p in line.split('","')]
        if len(parts) >= 5:
            pid = parts[1]
            mems = re.sub(r'[^\d]', '', parts[4].replace('\xa0', ''))
            try:
                mem = int(mems) if mems else 0
            except Exception:
                mem = 0
            if mem < 5000:
                targets.append((parts[0], pid, mem))

print('candidates:', len(targets))
for name, pid, mem in targets:
    subprocess.run(['taskkill', '/F', '/PID', pid], capture_output=True)
print('killed attempts:', len(targets))

txt2 = get_procs()
print('python left:', txt2.lower().count('python.exe'))
print('camoufox left:', txt2.lower().count('camoufox'))

# memory
import ctypes
class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
m = MEMORYSTATUSEX()
m.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
print(f'mem: avail {m.ullAvailPhys//2**20}MB / total {m.ullTotalPhys//2**20}MB (load {m.dwMemoryLoad}%)')
