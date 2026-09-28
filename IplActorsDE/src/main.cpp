// IplActorsDE: lets map mods add props to GTA San Andreas - The Definitive Edition through text IPLs.
//
// DE draws map props with cooked Unreal actors (AIPLMapActor). CFileLoader::LoadObjectInstance sets entity +0x34
// bit 3 on every IPL instance, and CEntity::CreateRwObject (0x14112DF90) then only links the entity to a cooked
// actor with the same (IplIndex, model) - which a new placement never has, so it stays invisible. With the bit clear,
// CreateRwObject spawns an actor for the model at runtime (ModelInfo vtable +0x60), like it does for script objects.
//
// Convention for mods: an `inst` line whose 12th column (DE's per-file instance index) is -1 gets a runtime actor.
// DE's own IPLs never use a negative index, so stock placements are untouched. Only lines read by
// CFileLoader::LoadScene count (not stream IPLs). Details: ../README.md.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <intrin.h>
#include <share.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../minhook/MinHook.h"
#include "sigscan.h"

// Signatures (see sigscan.h). Verified unique in SanAndreas.exe ed7545eb… and cf677214… (README "Signatures").
// CFileLoader::LoadObjectInstance(const char* line, int* index), text form: function head.
static const char kLoadInstanceSig[] = "4C 8B DC 53 48 81 EC C0 00 00 00 48 8B 05 ?? ?? ?? ?? 48 33 C4 48 89 84 24 B8 00 00 00";
// Its call in CFileLoader::LoadScene: `call LoadObjectInstance; movsxd rbx, [rbp-80h]; mov rsi, rax`.
static const char kLoadSceneCallSig[] = "E8 ?? ?? ?? ?? 48 63 5D 80 48 8B F0";
// Layout check: the instance builder LoadObjectInstance calls resets the link flag: `and dword [rbx+34h], ~8`.
static const char kLinkFlagSig[] = "83 63 34 F7 F3 0F 10 15 ?? ?? ?? ??";
constexpr size_t kEntityFlags = 0x34;  // CEntity flags; bit 3 = link to a cooked IPL actor

static uint8_t* g_loadSceneRet = nullptr;  // return address of the LoadScene call: only those lines are ours to mark
static uint8_t* (*g_orig)(const char*, int*) = nullptr;
static FILE* g_log = nullptr;
static long g_marked = 0;

static void Log(const char* fmt, ...) {
    if (!g_log) return;
    va_list ap;
    va_start(ap, fmt);
    vfprintf(g_log, fmt, ap);
    va_end(ap);
    fputc('\n', g_log);
    fflush(g_log);
}

// LoadScene has already turned the commas into spaces: "id name interior x y z qx qy qz qw lod index".
static bool WantsRuntimeActor(const char* line) {
    int n = 0;
    const char* last = nullptr;
    for (const char* p = line; *p;) {
        while (*p && (unsigned char)*p <= ' ') ++p;
        if (!*p) break;
        last = p;
        ++n;
        while ((unsigned char)*p > ' ') ++p;
    }
    return n == 12 && strncmp(last, "-1", 2) == 0 && (unsigned char)last[2] <= ' ';
}

static uint8_t* LoadInstanceDetour(const char* line, int* index) {
    uint8_t* entity = g_orig(line, index);
    if (entity && _ReturnAddress() == g_loadSceneRet && WantsRuntimeActor(line)) {
        entity[kEntityFlags] &= ~0x08;
        if (++g_marked % 1000 == 1) Log("runtime actors: %ld placements so far (latest: %.60s)", g_marked, line);
    }
    return entity;
}

// Resolves everything first and installs nothing unless every signature matched exactly once and they agree.
static void Install(uint8_t* base) {
    const TextSection text = FindText(base);
    uint8_t* target = FindUnique(text, kLoadInstanceSig);
    uint8_t* call = FindUnique(text, kLoadSceneCallSig);
    uint8_t* flag = FindUnique(text, kLinkFlagSig);
    Log("LoadObjectInstance +0x%llX, LoadScene call +0x%llX, link flag write +0x%llX",
        target ? (unsigned long long)(target - base) : 0ull, call ? (unsigned long long)(call - base) : 0ull,
        flag ? (unsigned long long)(flag - base) : 0ull);
    if (!target || !call || !flag || RipTarget(call, 1, 5) != target) {
        Log("unsupported SanAndreas.exe (code not found or changed): nothing installed, remove map mods that need IplActorsDE");
        return;
    }
    g_loadSceneRet = call + 5;
    const MH_STATUS init = MH_Initialize();
    if ((init != MH_OK && init != MH_ERROR_ALREADY_INITIALIZED) || MH_CreateHook(target, (void*)&LoadInstanceDetour, (void**)&g_orig) != MH_OK ||
        MH_EnableHook(target) != MH_OK) {
        Log("hooking LoadObjectInstance failed");
        return;
    }
    Log("hooked LoadObjectInstance");
}

BOOL APIENTRY DllMain(HMODULE module, DWORD reason, LPVOID) {
    if (reason != DLL_PROCESS_ATTACH) return TRUE;
    DisableThreadLibraryCalls(module);
    char path[MAX_PATH];
    GetModuleFileNameA(module, path, MAX_PATH);
    if (char* dot = strrchr(path, '.')) strcpy(dot, ".log");
    g_log = _fsopen(path, "w", _SH_DENYWR);
    Log("IplActorsDE 1.1");
    Install((uint8_t*)GetModuleHandleA(nullptr));
    return TRUE;
}
