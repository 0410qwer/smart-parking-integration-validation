"""Descriptive metrics; no target compliance inferred from a finite virtual sample."""
import math
import statistics

def sampled_file_bytes(paths):
    """WAL/SHM files can disappear between directory enumeration and stat."""
    total=0
    for path in paths:
        try:total+=path.stat().st_size
        except FileNotFoundError:continue
    return total

def distribution(values,attempted=None):
    values=sorted(values);attempted=len(values) if attempted is None else attempted
    return dict(attempted=attempted,successful=len(values),failed=attempted-len(values),
                failure_rate=(attempted-len(values))/attempted if attempted else None,
                minimum_ms=values[0] if values else None,median_ms=statistics.median(values) if values else None,
                p95_ms=values[max(0,math.ceil(.95*len(values))-1)] if values else None,
                maximum_ms=values[-1] if values else None,p95_method='nearest rank')

def process_rss(pid):
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in (
            'PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
            'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]
    kernel=ctypes.WinDLL('kernel32',use_last_error=True);psapi=ctypes.WinDLL('psapi',use_last_error=True)
    kernel.OpenProcess.restype=wintypes.HANDLE;kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
    handle=kernel.OpenProcess(0x410,False,pid)
    if not handle:return None
    try:
        value=Counters();value.cb=ctypes.sizeof(value)
        return value.WorkingSetSize if psapi.GetProcessMemoryInfo(handle,ctypes.byref(value),value.cb) else None
    finally:kernel.CloseHandle(handle)
