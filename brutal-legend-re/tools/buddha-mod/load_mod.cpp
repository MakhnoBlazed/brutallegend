// load_mod.cpp - Brutal Legend Mod Loader Injector
// Injects buddha_mod.dll into the Brutal Legend process via CreateRemoteThread + LoadLibrary
//
// Build: g++ -O2 -Wall load_mod.cpp -o load_mod.exe
//        or: cl /EHsc load_mod.cpp
//
// Usage: load_mod.exe [path_to_BrutalLegend.exe]
//        If no path given, uses the default Steam path.

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string.h>

// Resolved at runtime from registry — no hardcoded paths
static char g_defaultGamePath[MAX_PATH] = {0};

static void resolve_default_game_path(void)
{
    // Try Steam registry first
    HKEY hKey;
    if (RegOpenKeyExA(HKEY_LOCAL_MACHINE,
        "SOFTWARE\\WOW6432Node\\Valve\\Steam",
        0, KEY_READ, &hKey) == ERROR_SUCCESS)
    {
        char steamPath[MAX_PATH];
        DWORD len = sizeof(steamPath);
        if (RegQueryValueExA(hKey, "InstallPath", NULL, NULL, (LPBYTE)steamPath, &len) == ERROR_SUCCESS)
        {
            strcat_s(steamPath, MAX_PATH, "\\steamapps\\common\\BrutalLegend\\BrutalLegend.exe");
            if (GetFileAttributesA(steamPath) != INVALID_FILE_ATTRIBUTES)
            {
                strcpy_s(g_defaultGamePath, MAX_PATH, steamPath);
                RegCloseKey(hKey);
                return;
            }
        }
        RegCloseKey(hKey);
    }

    // Try common paths
    const char* commonPaths[] = {
        "C:\\Program Files (x86)\\Steam\\steamapps\\common\\BrutalLegend\\BrutalLegend.exe",
        "C:\\Program Files\\Steam\\steamapps\\common\\BrutalLegend\\BrutalLegend.exe",
        "D:\\Steam\\steamapps\\common\\BrutalLegend\\BrutalLegend.exe"
    };

    for (int i = 0; i < 3; i++)
    {
        if (GetFileAttributesA(commonPaths[i]) != INVALID_FILE_ATTRIBUTES)
        {
            strcpy_s(g_defaultGamePath, MAX_PATH, commonPaths[i]);
            return;
        }
    }
}

static const char* MOD_DLL_NAME = "buddha_mod.dll";

static void print_error(const char* msg, DWORD err)
{
    char buf[256];
    FormatMessageA(FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS,
        NULL, err, 0, buf, sizeof(buf), NULL);
    fprintf(stderr, "[load_mod] %s: %s\n", msg, buf);
}

static BOOL is_running_x86(HANDLE hProcess)
{
    BOOL wow64 = FALSE;
    IsWow64Process(hProcess, &wow64);
    // If we're on x64 and the target is x86 (not wow64), it's x86
    // If we're on x86, the target is x86
    SYSTEM_INFO si;
    GetSystemInfo(&si);
    if (si.wProcessorArchitecture == PROCESSOR_ARCHITECTURE_AMD64 && wow64)
        return TRUE; // target is x86
    if (si.wProcessorArchitecture == PROCESSOR_ARCHITECTURE_INTEL)
        return TRUE; // we're x86, target must match
    return FALSE;
}

static int inject_dll(HANDLE hProcess, const char* dllPath, BOOL x86_target)
{
    SIZE_T pathLen = strlen(dllPath) + 1;

    // Allocate memory in the target process
    LPVOID remotePath = VirtualAllocEx(hProcess, NULL, pathLen, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!remotePath)
    {
        print_error("VirtualAllocEx failed", GetLastError());
        return -1;
    }

    // Write the DLL path
    if (!WriteProcessMemory(hProcess, remotePath, dllPath, pathLen, NULL))
    {
        print_error("WriteProcessMemory failed", GetLastError());
        VirtualFreeEx(hProcess, remotePath, 0, MEM_RELEASE);
        return -1;
    }

    // Get LoadLibraryA address (same in x86 and x64)
    LPVOID loadLibAddr = (LPVOID)GetProcAddress(GetModuleHandleA("kernel32.dll"), "LoadLibraryA");
    if (!loadLibAddr)
    {
        print_error("GetProcAddress for LoadLibraryA failed", GetLastError());
        VirtualFreeEx(hProcess, remotePath, 0, MEM_RELEASE);
        return -1;
    }

    // Create remote thread
    HANDLE hThread = CreateRemoteThread(hProcess, NULL, 0,
        (LPTHREAD_START_ROUTINE)loadLibAddr, remotePath, 0, NULL);
    if (!hThread)
    {
        print_error("CreateRemoteThread failed", GetLastError());
        VirtualFreeEx(hProcess, remotePath, 0, MEM_RELEASE);
        return -1;
    }

    // Wait for the thread to complete the LoadLibrary call
    DWORD wait = WaitForSingleObject(hThread, 15000);
    if (wait == WAIT_TIMEOUT)
    {
        print_error("CreateRemoteThread timed out", 0);
        TerminateThread(hThread, 1);
        CloseHandle(hThread);
        VirtualFreeEx(hProcess, remotePath, 0, MEM_RELEASE);
        return -1;
    }

    DWORD exitCode = 0;
    GetExitCodeThread(hThread, &exitCode);

    if (exitCode == 0)
    {
        // LoadLibrary returned NULL - DLL not found or entry point error
        fprintf(stderr, "[load_mod] LoadLibrary returned NULL. Is %s next to BrutalLegend.exe?\n", MOD_DLL_NAME);
        VirtualFreeEx(hProcess, remotePath, 0, MEM_RELEASE);
        CloseHandle(hThread);
        return -1;
    }

    printf("[load_mod] DLL loaded at 0x%p\n", (void*)exitCode);

    CloseHandle(hThread);
    VirtualFreeEx(hProcess, remotePath, 0, MEM_RELEASE);
    return 0;
}

static BOOL reloc_needed_x64_to_x86(void)
{
    SYSTEM_INFO si;
    GetSystemInfo(&si);
    BOOL wow64 = FALSE;
    IsWow64Process(GetCurrentProcess(), &wow64);
    // We're x64, targeting x86 process -> need to check if we can inject
    return (si.wProcessorArchitecture == PROCESSOR_ARCHITECTURE_AMD64);
}

int main(int argc, char* argv[])
{
    printf("=== Buddha Mod Loader Injector v0.1.0 ===\n\n");

    resolve_default_game_path();

    if (g_defaultGamePath[0] == '\0')
    {
        fprintf(stderr, "[load_mod] Could not find BrutalLegend.exe.\n");
        fprintf(stderr, "Install Steam and Brutal Legend, or provide path as argument:\n");
        fprintf(stderr, "  load_mod.exe \"<path>\\BrutalLegend.exe\"\n");
        return 1;
    }

    const char* gamePath = (argc > 1) ? argv[1] : g_defaultGamePath;

    // Resolve the DLL path: <exe_dir>\buddha_mod.dll
    char dllPath[MAX_PATH];
    strcpy_s(dllPath, MAX_PATH, gamePath);
    char* lastSep = strrchr(dllPath, '\\');
    if (!lastSep)
    {
        fprintf(stderr, "[load_mod] Invalid game path: %s\n", gamePath);
        return 1;
    }
    lastSep[1] = '\0';
    strcat_s(dllPath, MAX_PATH, MOD_DLL_NAME);

    // Verify DLL exists
    if (GetFileAttributesA(dllPath) == INVALID_FILE_ATTRIBUTES)
    {
        fprintf(stderr, "[load_mod] buddha_mod.dll not found at: %s\n", dllPath);
        fprintf(stderr, "\nPlace buddha_mod.dll next to BrutalLegend.exe before running this injector.\n");
        return 1;
    }

    printf("Game executable: %s\n", gamePath);
    printf("Mod DLL:         %s\n\n", dllPath);

    // Open the game process
    DWORD pid = 0;
    HANDLE hSnap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (hSnap == INVALID_HANDLE_VALUE)
    {
        print_error("CreateToolhelp32Snapshot failed", GetLastError());
        return 1;
    }

    // Find the process by name
    PROCESSENTRY32W pe = { sizeof(PROCESSENTRY32W) };
    WCHAR gameNameW[MAX_PATH];
    MultiByteToWideChar(CP_ACP, 0, gamePath, -1, gameNameW, MAX_PATH);
    PWSTR filePart = wcsrchr(gameNameW, L'\\');
    if (filePart) ++filePart; else filePart = gameNameW;

    BOOL found = FALSE;
    for (BOOL ok = Process32FirstW(hSnap, &pe); ok; ok = Process32NextW(hSnap, &pe))
    {
        if (_wcsicmp(pe.szExeFile, filePart) == 0)
        {
            pid = pe.th32ProcessID;
            found = TRUE;
            break;
        }
    }
    CloseHandle(hSnap);

    if (!found)
    {
        fprintf(stderr, "[load_mod] Brutal Legend is not running.\n");
        fprintf(stderr, "Start the game first, then run this injector.\n");
        fprintf(stderr, "Alternatively, launch the game with: load_mod.exe\n");
        return 1;
    }

    printf("Found process PID: %lu\n", pid);

    HANDLE hProcess = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_CREATE_THREAD | PROCESS_VM_OPERATION | PROCESS_VM_WRITE,
        FALSE, pid);
    if (!hProcess)
    {
        print_error("OpenProcess failed (try running as Administrator)", GetLastError());
        return 1;
    }

    printf("Injecting mod DLL...\n");
    int result = inject_dll(hProcess, dllPath, TRUE);

    if (result == 0)
    {
        printf("\n[load_mod] Success! Mod loader is active.\n");
        printf("Check Win/Mods/ in the game directory for mod bundles.\n");
    }
    else
    {
        printf("\n[load_mod] Injection failed (code %d).\n", result);
    }

    CloseHandle(hProcess);
    return result;
}
