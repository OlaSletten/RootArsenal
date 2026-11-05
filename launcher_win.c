#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void enable_vt_mode(void) {
    HANDLE hOut = GetStdHandle(STD_OUTPUT_HANDLE);
    if (hOut == INVALID_HANDLE_VALUE) return;
    DWORD dwMode = 0;
    if (!GetConsoleMode(hOut, &dwMode)) return;
    dwMode |= 0x0004; // ENABLE_VIRTUAL_TERMINAL_PROCESSING
    SetConsoleMode(hOut, dwMode);
    SetConsoleOutputCP(65001); // UTF-8
}

int file_exists(const char *path) {
    DWORD dwAttrib = GetFileAttributesA(path);
    return (dwAttrib != INVALID_FILE_ATTRIBUTES && !(dwAttrib & FILE_ATTRIBUTE_DIRECTORY));
}

int main(int argc, char *argv[]) {
    enable_vt_mode();

    char exe_dir[MAX_PATH] = {0};
    GetModuleFileNameA(NULL, exe_dir, MAX_PATH);
    char *last_slash = strrchr(exe_dir, '\\');
    if (last_slash) *last_slash = '\0';

    char adb_path[MAX_PATH] = "adb";
    char local_adb[MAX_PATH];
    snprintf(local_adb, sizeof(local_adb), "%s\\adb.exe", exe_dir);
    if (file_exists(local_adb)) {
        strncpy(adb_path, local_adb, sizeof(adb_path) - 1);
    } else {
        snprintf(local_adb, sizeof(local_adb), "%s\\platform-tools\\adb.exe", exe_dir);
        if (file_exists(local_adb)) {
            strncpy(adb_path, local_adb, sizeof(adb_path) - 1);
        }
    }

    printf("\033[1;36m==============================================================================\033[0m\n");
    printf("\033[1;33m  ⚡ ROOT ARSENAL v2.5 - Windows ADB Client\033[0m\n");
    printf("  Universal Android Root & Shizuku Ecosystem\n");
    printf("\033[1;36m==============================================================================\033[0m\n\n");

    // Check device connection
    printf("[*] Connecting to device via ADB (%s)...\n", adb_path);
    char cmd[1024];
    snprintf(cmd, sizeof(cmd), "\"%s\" start-server >nul 2>nul", adb_path);
    system(cmd);

    // If user passed specific arguments like --telemetry or --search
    char extra_args[1024] = {0};
    if (argc > 1) {
        for (int i = 1; i < argc; i++) {
            strncat(extra_args, " ", sizeof(extra_args) - strlen(extra_args) - 1);
            strncat(extra_args, argv[i], sizeof(extra_args) - strlen(extra_args) - 1);
        }
    }

    // Check if python is available on Windows
    int has_python = (system("python --version >nul 2>nul") == 0);
    char py_script[MAX_PATH];
    snprintf(py_script, sizeof(py_script), "%s\\root_arsenal.py", exe_dir);

    if (has_python && file_exists(py_script)) {
        printf("[+] Found Python on Windows! Running native RootArsenal engine with ADB backend...\n\n");
        if (strlen(extra_args) > 0) {
            snprintf(cmd, sizeof(cmd), "python \"%s\" --adb%s", py_script, extra_args);
        } else {
            snprintf(cmd, sizeof(cmd), "python \"%s\" --adb", py_script);
        }
        return system(cmd);
    }

    // Launch interactive remote session directly via device's Termux environment
    printf("[+] Launching RootArsenal interactive session via ADB remote shell...\n");
    printf("[i] Full color, hardware volume keys, and multi-digit navigation enabled.\n\n");

    if (strlen(extra_args) > 0) {
        snprintf(cmd, sizeof(cmd), "\"%s\" shell -t \"su -c 'PATH=/data/data/com.termux/files/usr/bin:/system/bin:$PATH root-arsenal%s'\"", adb_path, extra_args);
    } else {
        snprintf(cmd, sizeof(cmd), "\"%s\" shell -t \"su -c 'PATH=/data/data/com.termux/files/usr/bin:/system/bin:$PATH root-arsenal'\"", adb_path);
    }
    return system(cmd);
}
