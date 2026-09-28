"""Process helpers for the E2E test: find the game, read its memory, focus its window.
Set GTASA_DE_WIN64 to your Gameface\\Binaries\\Win64 folder if it isn't the default below."""
import ctypes, ctypes.wintypes as W, os, re, subprocess

GAME = os.environ.get("GTASA_DE_WIN64", r"D:\GTA SA\GTA San Andreas - Definitive Edition\Gameface\Binaries\Win64")
u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
k32.OpenProcess.restype = W.HANDLE


def pid_of(name):
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    m = re.search(r'"%s","(\d+)"' % re.escape(name), out)
    return int(m.group(1)) if m else 0


def module_base(pid):
    class ME(ctypes.Structure):
        _fields_ = [("dwSize", W.DWORD), ("th32ModuleID", W.DWORD), ("th32ProcessID", W.DWORD), ("GlblcntUsage", W.DWORD),
                    ("ProccntUsage", W.DWORD), ("modBaseAddr", ctypes.c_void_p), ("modBaseSize", W.DWORD), ("hModule", W.HMODULE),
                    ("szModule", ctypes.c_char * 256), ("szExePath", ctypes.c_char * 260)]
    k32.CreateToolhelp32Snapshot.restype = W.HANDLE
    snap = k32.CreateToolhelp32Snapshot(0x18, pid)  # TH32CS_SNAPMODULE | SNAPMODULE32
    me = ME(); me.dwSize = ctypes.sizeof(ME)
    ok = k32.Module32First(W.HANDLE(snap), ctypes.byref(me))
    k32.CloseHandle(W.HANDLE(snap))
    return me.modBaseAddr if ok else 0


def read(h, addr, n):
    buf = ctypes.create_string_buffer(n); got = ctypes.c_size_t()
    ok = k32.ReadProcessMemory(W.HANDLE(h), ctypes.c_void_p(addr), buf, n, ctypes.byref(got))
    return buf.raw if ok else None


def focus(pid):
    hw = []
    cb = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)(lambda w, l: (hw.append(w) if u32.IsWindowVisible(w) and _pid(w) == pid else None) or True)
    u32.EnumWindows(cb, 0)
    if hw:
        u32.keybd_event(0x12, 0, 0, 0); u32.keybd_event(0x12, 0, 2, 0)  # Alt tap lets SetForegroundWindow succeed
        u32.SetForegroundWindow(hw[0])
    return hw[0] if hw else None


def _pid(w):
    p = W.DWORD(); u32.GetWindowThreadProcessId(w, ctypes.byref(p)); return p.value
