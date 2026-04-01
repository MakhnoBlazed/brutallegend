// buddha_mod.cpp - Brutal Legend Mod Loader DLL
// Hooks GSysFile::Open (via CreateFileA/W IAT hook) to redirect file
// requests to <game_dir>/Win/Mods/<original_path>
//
// Build: g++ -shared -O2 -Wall buddha_mod.cpp -o buddha_mod.dll -nostdlib
//        or use Visual Studio Developer Command Prompt: cl /LD /EHsc buddha_mod.cpp

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string.h>

#pragma comment(linker, "/EXPORT:DllMain=DllMain_hook")

// -----------------------------------------------------------------------
// Configuration
// -----------------------------------------------------------------------
static const char  MOD_SUB_DIR[]  = "Win\\Mods\\";
static const wchar_t MOD_SUB_DIR_W[] = L"Win\\Mods\\";

// -----------------------------------------------------------------------
// Trampoline storage for hooked CreateFileA / CreateFileW
// -----------------------------------------------------------------------
typedef HANDLE (WINAPI *PFN_CreateFileA)(
    LPCSTR lpFileName, DWORD dwDesiredAccess, DWORD dwShareMode,
    LPSECURITY_ATTRIBUTES lpSecurityAttributes, DWORD dwCreationDisposition,
    DWORD dwFlagsAndAttributes, HANDLE hTemplateFile);

typedef HANDLE (WINAPI *PFN_CreateFileW)(
    LPCWSTR lpFileName, DWORD dwDesiredAccess, DWORD dwShareMode,
    LPSECURITY_ATTRIBUTES lpSecurityAttributes, DWORD dwCreationDisposition,
    DWORD dwFlagsAndAttributes, HANDLE hTemplateFile);

static PFN_CreateFileA  orig_CreateFileA  = NULL;
static PFN_CreateFileW  orig_CreateFileW  = NULL;

// -----------------------------------------------------------------------
// Utility: build the mod-path version of a file path
// Returns true  -> modPath buffer contains the redirected path
// Returns false -> file not under game root (should use original)
// -----------------------------------------------------------------------
static bool build_mod_path(LPCSTR origPath, char modPath[MAX_PATH])
{
    // Get the directory the game executable lives in
    char gameDir[MAX_PATH];
    if (!GetModuleFileNameA(NULL, gameDir, MAX_PATH))
        return false;

    // Strip filename, keep trailing backslash
    char* lastSep = strrchr(gameDir, '\\');
    if (!lastSep) return false;
    lastSep[1] = '\0';

    // Check that origPath is under Win\Packs\ or similar game data
    // We only redirect if it starts with "Win\" or "Data\"
    // (this prevents redirecting random DLL loads)
    if (_strnicmp(origPath, "Win\\", 4) != 0 && _strnicmp(origPath, "Data\\", 5) != 0)
        return false;

    // Build <gameDir>Win\Mods\<origPath>
    strcpy_s(modPath, MAX_PATH, gameDir);
    strcat_s(modPath, MAX_PATH, MOD_SUB_DIR);
    strcat_s(modPath, MAX_PATH, origPath);
    return true;
}

static bool build_mod_path_w(LPCWSTR origPath, wchar_t modPath[MAX_PATH])
{
    char gameDir[MAX_PATH];
    if (!GetModuleFileNameA(NULL, gameDir, MAX_PATH))
        return false;

    char* lastSep = strrchr(gameDir, '\\');
    if (!lastSep) return false;
    lastSep[1] = '\0';

    // Only redirect Win\* and Data\* paths
    if (_wcsnicmp(origPath, L"Win\\", 4) != 0 && _wcsnicmp(origPath, L"Data\\", 5) != 0)
        return false;

    modPath[0] = L'\0';
    MultiByteToWideChar(CP_ACP, 0, gameDir, -1, modPath, MAX_PATH);
    wcscat_s(modPath, MAX_PATH, MOD_SUB_DIR_W);

    // Append the rest of origPath after "Win\" or "Data\"
    const wchar_t* remaining = NULL;
    if (_wcsnicmp(origPath, L"Win\\", 4) == 0)
        remaining = origPath + 4;
    else if (_wcsnicmp(origPath, L"Data\\", 5) == 0)
        remaining = origPath + 5;

    if (remaining)
        wcscat_s(modPath, MAX_PATH, remaining);
    return true;
}

// -----------------------------------------------------------------------
// Hooked CreateFileA / CreateFileW
// -----------------------------------------------------------------------
static HANDLE WINAPI hooked_CreateFileA(
    LPCSTR lpFileName, DWORD dwDesiredAccess, DWORD dwShareMode,
    LPSECURITY_ATTRIBUTES lpSecurityAttributes, DWORD dwCreationDisposition,
    DWORD dwFlagsAndAttributes, HANDLE hTemplateFile)
{
    if (lpFileName && (GetFileAttributesA(lpFileName) != INVALID_FILE_ATTRIBUTES))
    {
        // File exists - check if there's a mod override
        char modPath[MAX_PATH];
        if (build_mod_path(lpFileName, modPath))
        {
            if (GetFileAttributesA(modPath) != INVALID_FILE_ATTRIBUTES)
            {
                // Mod override exists - redirect
                return orig_CreateFileA(modPath, dwDesiredAccess, dwShareMode,
                    lpSecurityAttributes, dwCreationDisposition,
                    dwFlagsAndAttributes, hTemplateFile);
            }
        }
    }

    // Fall through to original
    return orig_CreateFileA(lpFileName, dwDesiredAccess, dwShareMode,
        lpSecurityAttributes, dwCreationDisposition,
        dwFlagsAndAttributes, hTemplateFile);
}

static HANDLE WINAPI hooked_CreateFileW(
    LPCWSTR lpFileName, DWORD dwDesiredAccess, DWORD dwShareMode,
    LPSECURITY_ATTRIBUTES lpSecurityAttributes, DWORD dwCreationDisposition,
    DWORD dwFlagsAndAttributes, HANDLE hTemplateFile)
{
    if (lpFileName && (GetFileAttributesW(lpFileName) != INVALID_FILE_ATTRIBUTES))
    {
        wchar_t modPath[MAX_PATH];
        if (build_mod_path_w(lpFileName, modPath))
        {
            if (GetFileAttributesW(modPath) != INVALID_FILE_ATTRIBUTES)
            {
                return orig_CreateFileW(modPath, dwDesiredAccess, dwShareMode,
                    lpSecurityAttributes, dwCreationDisposition,
                    dwFlagsAndAttributes, hTemplateFile);
            }
        }
    }

    return orig_CreateFileW(lpFileName, dwDesiredAccess, dwShareMode,
        lpSecurityAttributes, dwCreationDisposition,
        dwFlagsAndAttributes, hTemplateFile);
}

// -----------------------------------------------------------------------
// IAT hook helper
// -----------------------------------------------------------------------
static PIMAGE_IMPORT_DESCRIPTOR find_import_desc(HMODULE module)
{
    PIMAGE_DOS_HEADER dos = (PIMAGE_DOS_HEADER)module;
    if (dos->e_magic != IMAGE_DOS_SIGNATURE) return NULL;
    PIMAGE_NT_HEADERS nt = (PIMAGE_NT_HEADERS)((BYTE*)dos + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE) return NULL;
    DWORD rva = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT].VirtualAddress;
    if (!rva) return NULL;
    return (PIMAGE_IMPORT_DESCRIPTOR)((BYTE*)dos + rva);
}

static bool iat_hook_module(HMODULE module)
{
    PIMAGE_IMPORT_DESCRIPTOR desc = find_import_desc(module);
    if (!desc) return false;

    bool hooked = false;
    for (; desc->Name; ++desc)
    {
        const char* dllName = (const char*)((BYTE*)module + desc->Name);
        if (_stricmp(dllName, "KERNEL32.dll") != 0)
            continue;

        // Walk the IAT
        PIMAGE_THUNK_DATA iat = (PIMAGE_THUNK_DATA)((BYTE*)module + desc->FirstChunkRVA);
        PIMAGE_THUNK_DATA iat_end = (PIMAGE_THUNK_DATA)((BYTE*)module + desc->FirstChunkRVA + desc->ChunkSize);

        for (; iat < iat_end && iat->u1.Function; ++iat)
        {
            FARPROC* funcPtr = (FARPROC*)&iat->u1.Function;

            // Skip ordinals and forwarded exports
            if (IMAGE_SNAP_BY_ORDINAL(iat->u1.Ordinal))
                continue;

            PIMAGE_IMPORT_BY_NAME name = (PIMAGE_IMPORT_BY_NAME)((BYTE*)module + (DWORD)iat->u1.AddressOfData);
            if (!name || !name->Name)
                continue;

            if (strcmp((const char*)name->Name, "CreateFileA") == 0)
            {
                DWORD oldProt;
                VirtualProtect(funcPtr, sizeof(FARPROC), PAGE_READWRITE, &oldProt);
                orig_CreateFileA = (PFN_CreateFileA)*funcPtr;
                *funcPtr = (FARPROC)hooked_CreateFileA;
                VirtualProtect(funcPtr, sizeof(FARPROC), oldProt, &oldProt);
                hooked = true;
            }
            else if (strcmp((const char*)name->Name, "CreateFileW") == 0)
            {
                DWORD oldProt;
                VirtualProtect(funcPtr, sizeof(FARPROC), PAGE_READWRITE, &oldProt);
                orig_CreateFileW = (PFN_CreateFileW)*funcPtr;
                *funcPtr = (FARPROC)hooked_CreateFileW;
                VirtualProtect(funcPtr, sizeof(FARPROC), oldProt, &oldProt);
                hooked = true;
            }
        }
    }
    return hooked;
}

// -----------------------------------------------------------------------
// DLL entry point
// -----------------------------------------------------------------------
static HANDLE g_modsDirHandle = NULL;

BOOL WINAPI DllMain_hook(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpvReserved)
{
    if (fdwReason == DLL_PROCESS_ATTACH)
    {
        // Create the Win/Mods directory if it doesn't exist
        char gameDir[MAX_PATH];
        if (GetModuleFileNameA(NULL, gameDir, MAX_PATH))
        {
            char* lastSep = strrchr(gameDir, '\\');
            if (lastSep) {
                lastSep[1] = '\0';
                strcat_s(gameDir, MAX_PATH, MOD_SUB_DIR);
                CreateDirectoryA(gameDir, NULL);
            }
        }

        // Hook the current process
        HMODULE kernel = GetModuleHandleA("KERNEL32.dll");
        if (kernel)
            iat_hook_module(GetModuleHandleA(NULL));

        char logPath[MAX_PATH];
        GetModuleFileNameA(NULL, logPath, MAX_PATH);
        char* lastSep = strrchr(logPath, '\\');
        if (lastSep) lastSep[1] = '\0';
        strcat_s(logPath, MAX_PATH, "buddha_mod.log");

        FILE* f = NULL;
        fopen_s(&f, logPath, "w");
        if (f)
        {
            fprintf(f, "buddha_mod loaded (PID=%lu)\n", GetCurrentProcessId());
            fprintf(f, "Game dir: ");
            GetModuleFileNameA(NULL, logPath, MAX_PATH);
            lastSep = strrchr(logPath, '\\');
            if (lastSep) lastSep[1] = '\0';
            fprintf(f, "%s\n", logPath);
            fprintf(f, "Mod dir:  %s" MOD_SUB_DIR "\n", logPath);
            fprintf(f, "GSysFile::Open hooking requires Ghidra analysis to find vtable offset.\n");
            fprintf(f, "Currently using CreateFileA/W IAT hook as fallback.\n");
            fclose(f);
        }

        DisableThreadLibraryCalls((HMODULE)hinstDLL);
    }
    else if (fdwReason == DLL_PROCESS_DETACH)
    {
        // Nothing to clean up - trampolines are self-contained
    }
    return TRUE;
}

// -----------------------------------------------------------------------
// Exports for optional manual trigger
// -----------------------------------------------------------------------
extern "C" {

__declspec(dllexport)
const char* BUDDHA_MOD_VERSION = "0.1.0";

__declspec(dllexport)
int BUDDHA_MOD_INIT(void)
{
    // Already initialized via DllMain, this is a no-op
    return 0;
}

} // extern "C"
