// sigscan.h: finds code in SanAndreas.exe by byte pattern instead of fixed addresses, so one ASI works on every DE
// build whose code still matches (builds differ by recompiles that shift addresses, e.g. +0x1490 between two
// SanAndreas.exe copies of the same version). Same file in IplActorsDE and DE_LimitAdjuster.
//
// Pattern: hex bytes separated by spaces, "??" = any byte. A pattern must match exactly once in .text: zero or
// several matches mean the code changed, and the caller must refuse to install instead of guessing.
// The patterns are generated from the IDB and checked against every known build (see README "Signatures").
#pragma once
#include <windows.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

struct TextSection { uint8_t* begin = nullptr; size_t size = 0; };

inline TextSection FindText(uint8_t* base) {
    auto* nt = (IMAGE_NT_HEADERS64*)(base + ((IMAGE_DOS_HEADER*)base)->e_lfanew);
    auto* sec = IMAGE_FIRST_SECTION(nt);
    for (unsigned i = 0; i < nt->FileHeader.NumberOfSections; ++i, ++sec)
        if (memcmp(sec->Name, ".text", 6) == 0) return { base + sec->VirtualAddress, sec->Misc.VirtualSize };
    return {};
}

// Address of the single match of `pattern` plus `offset`, or nullptr when it matches 0 or 2+ times.
inline uint8_t* FindUnique(const TextSection& text, const char* pattern, int offset = 0) {
    uint8_t bytes[128];
    bool mask[128];
    size_t n = 0;
    for (const char* p = pattern; *p && n < sizeof(bytes);) {
        if (*p == ' ') { ++p; continue; }
        if (*p == '?') { mask[n] = false; bytes[n++] = 0; p += p[1] == '?' ? 2 : 1; continue; }
        const char hex[3] = { p[0], p[1], 0 };
        bytes[n] = (uint8_t)strtoul(hex, nullptr, 16);
        mask[n++] = true;
        p += 2;
    }
    if (!n || !text.begin || text.size < n) return nullptr;
    uint8_t* found = nullptr;
    for (uint8_t *cur = text.begin, *end = text.begin + text.size - n; cur <= end; ++cur) {
        if (cur[0] != bytes[0]) continue;
        size_t k = 1;
        while (k < n && (!mask[k] || cur[k] == bytes[k])) ++k;
        if (k == n) {
            if (found) return nullptr;
            found = cur;
        }
    }
    return found ? found + offset : nullptr;
}

// Target of a RIP-relative operand: `dispAt` = offset of the disp32 inside the instruction, `len` = instruction length.
inline uint8_t* RipTarget(uint8_t* insn, size_t dispAt, size_t len) {
    return insn + len + *(const int32_t*)(insn + dispAt);
}
