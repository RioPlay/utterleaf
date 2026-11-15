// Read-only native UI Automation inventory for Windows accessibility acceptance.
//
// Build with a Windows C++ compiler and link ole32, oleaut32 and uuid. Example
// with llvm-mingw:
//   g++ -std=c++17 -municode -O2 windows_native_uia_inventory.cpp \
//       -o windows_native_uia_inventory.exe -lole32 -loleaut32 -luuid
//
// The managed UIAutomationClient inventory does not always load Microsoft's
// client-side proxies for standard Win32 controls. CUIAutomation does, so this
// tool is the authority for the native-shell provider gate.

#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#include <windows.h>
#include <uiautomation.h>

#include <iostream>
#include <string>
#include <vector>

enum PatternMask : unsigned {
    Invoke = 1 << 0,
    Toggle = 1 << 1,
    Value = 1 << 2,
    Selection = 1 << 3,
    ExpandCollapse = 1 << 4,
};

struct Observation {
    std::wstring name;
    std::wstring class_name;
    CONTROLTYPEID control_type;
    bool focusable;
    bool offscreen;
    unsigned patterns;
};

struct Expectation {
    const wchar_t* name;
    const wchar_t* class_name;
    CONTROLTYPEID control_type;
    unsigned patterns;
};

static std::wstring bstr_value(BSTR value) {
    if (!value) return L"";
    std::wstring result(value, SysStringLen(value));
    SysFreeString(value);
    return result;
}

static bool supports(IUIAutomationElement* element, PATTERNID pattern_id) {
    IUnknown* pattern = nullptr;
    HRESULT result = element->GetCurrentPattern(pattern_id, &pattern);
    bool supported = SUCCEEDED(result) && pattern != nullptr;
    if (pattern) pattern->Release();
    return supported;
}

static unsigned pattern_mask(IUIAutomationElement* element) {
    unsigned result = 0;
    if (supports(element, UIA_InvokePatternId)) result |= Invoke;
    if (supports(element, UIA_TogglePatternId)) result |= Toggle;
    if (supports(element, UIA_ValuePatternId)) result |= Value;
    if (supports(element, UIA_SelectionPatternId)) result |= Selection;
    if (supports(element, UIA_ExpandCollapsePatternId)) result |= ExpandCollapse;
    return result;
}

static bool verify_native_settings(const std::vector<Observation>& observations) {
    const Expectation expected[] = {
        {L"Dictation", L"Button", UIA_ButtonControlTypeId, Invoke},
        {L"Keyboard shortcut:", L"Edit", UIA_EditControlTypeId, Value},
        {L"Input device:", L"ComboBox", UIA_ComboBoxControlTypeId, Value | ExpandCollapse},
        {L"Stop after speech and a pause", L"Button", UIA_CheckBoxControlTypeId, Invoke | Toggle},
        {L"Reset to defaults", L"Button", UIA_ButtonControlTypeId, Invoke},
        {L"Cancel", L"Button", UIA_ButtonControlTypeId, Invoke},
        {L"Save", L"Button", UIA_ButtonControlTypeId, Invoke},
    };
    bool valid = true;
    for (const auto& item : expected) {
        const Observation* match = nullptr;
        for (const auto& observation : observations) {
            if (observation.name == item.name && observation.class_name == item.class_name) {
                match = &observation;
                break;
            }
        }
        if (!match) {
            std::wcerr << L"missing expected control: " << item.name << L"\n";
            valid = false;
            continue;
        }
        if (match->control_type != item.control_type || !match->focusable || match->offscreen ||
            (match->patterns & item.patterns) != item.patterns) {
            std::wcerr << L"invalid semantics for: " << item.name << L"\n";
            valid = false;
        }
    }

    int visible_app_controls = 0;
    for (const auto& observation : observations) {
        bool app_class = observation.class_name == L"Button" ||
                         observation.class_name == L"Edit" ||
                         observation.class_name == L"ComboBox";
        if (app_class && observation.focusable && !observation.offscreen) {
            ++visible_app_controls;
        }
    }
    if (visible_app_controls != static_cast<int>(sizeof(expected) / sizeof(expected[0]))) {
        std::wcerr << L"unexpected visible interactive-control count: "
                   << visible_app_controls << L"\n";
        valid = false;
    }
    return valid;
}

int wmain(int argc, wchar_t** argv) {
    if (argc < 2 || argc > 3 || (argc == 3 && wcscmp(argv[2], L"--require-native-settings") != 0)) {
        std::wcerr << L"usage: windows_native_uia_inventory.exe <exact window title> "
                      L"[--require-native-settings]\n";
        return 2;
    }
    HWND window = FindWindowW(nullptr, argv[1]);
    if (!window) {
        std::wcerr << L"window not found\n";
        return 3;
    }
    HRESULT initialized = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    if (FAILED(initialized)) return 4;

    IUIAutomation* automation = nullptr;
    HRESULT created = CoCreateInstance(
        CLSID_CUIAutomation,
        nullptr,
        CLSCTX_INPROC_SERVER,
        IID_PPV_ARGS(&automation)
    );
    if (FAILED(created) || !automation) {
        CoUninitialize();
        return 5;
    }

    IUIAutomationElement* root = nullptr;
    IUIAutomationCondition* all = nullptr;
    IUIAutomationElementArray* descendants = nullptr;
    HRESULT result = automation->ElementFromHandle(window, &root);
    if (SUCCEEDED(result)) result = automation->CreateTrueCondition(&all);
    if (SUCCEEDED(result)) {
        result = root->FindAll(TreeScope_Descendants, all, &descendants);
    }
    if (FAILED(result) || !descendants) {
        if (all) all->Release();
        if (root) root->Release();
        automation->Release();
        CoUninitialize();
        return 6;
    }

    int length = 0;
    descendants->get_Length(&length);
    std::vector<Observation> observations;
    std::wcout << L"index\tname\tclass\tcontrol_type\tfocusable\tpatterns\n";
    for (int index = 0; index < length; ++index) {
        IUIAutomationElement* element = nullptr;
        if (FAILED(descendants->GetElement(index, &element)) || !element) continue;
        BSTR name = nullptr;
        BSTR class_name = nullptr;
        CONTROLTYPEID control_type = 0;
        BOOL focusable = FALSE;
        BOOL offscreen = FALSE;
        element->get_CurrentName(&name);
        element->get_CurrentClassName(&class_name);
        element->get_CurrentControlType(&control_type);
        element->get_CurrentIsKeyboardFocusable(&focusable);
        element->get_CurrentIsOffscreen(&offscreen);
        std::wstring name_value = bstr_value(name);
        std::wstring class_value = bstr_value(class_name);
        unsigned patterns = pattern_mask(element);
        observations.push_back({
            name_value,
            class_value,
            control_type,
            focusable != FALSE,
            offscreen != FALSE,
            patterns,
        });
        std::wcout
            << index << L"\t"
            << name_value << L"\t"
            << class_value << L"\t"
            << control_type << L"\t"
            << (focusable ? 1 : 0) << L"\t"
            << ((patterns & Invoke) ? L"invoke," : L"")
            << ((patterns & Toggle) ? L"toggle," : L"")
            << ((patterns & Value) ? L"value," : L"")
            << ((patterns & Selection) ? L"selection," : L"")
            << ((patterns & ExpandCollapse) ? L"expand," : L"")
            << L"\n";
        element->Release();
    }

    bool valid = argc != 3 || verify_native_settings(observations);

    descendants->Release();
    all->Release();
    root->Release();
    automation->Release();
    CoUninitialize();
    return valid ? 0 : 7;
}
