// meter_layer.cpp -- the Tune-o-matiC frame meter: an OpenXR API layer that clocks every frame a VR game sends to
// the headset and writes them down, for any OpenXR game (UEVR, REFramework, Cemu's BetterVR, ...). It changes
// nothing in the game's calls; it only notes the time around xrWaitFrame and xrEndFrame.
//
// Acts only when lanes_tune_meter.txt beside the DLL says "on = 1" and names this game's exe ("exe = *" for all).
// Writes, per session, in %LOCALAPPDATA%\Lanes\tune\meter\ (or "out = <folder>"):
//   <YYYY-MM-DD_HH-MM-SS>_<exe>.frametime.csv   one row per frame (meter_core.h says what each column is)
//   <exe>.live.json                             the last two seconds, rewritten twice a second, for the live guard
// Its shell is the one Flickers BeG0nE and VR Bench use (negotiate, fetch the next functions, hand the calls on).
#include "meter_core.h"

#include <openxr/openxr_loader_negotiation.h>
#include <windows.h>

#include <atomic>
#include <cstring>
#include <ctime>
#include <string>
#include <thread>

namespace {

constexpr DWORD FLUSH_EVERY_MS = 500;

PFN_xrGetInstanceProcAddr g_next_gipa = nullptr;
PFN_xrWaitFrame g_next_wait = nullptr;
PFN_xrEndFrame g_next_end = nullptr;
PFN_xrCreateSession g_next_create_session = nullptr;
PFN_xrDestroySession g_next_destroy_session = nullptr;
bool g_enabled = false;
tm_meter::Meter g_meter;
std::string g_out_dir, g_exe_stem;
std::thread g_writer;
std::atomic<bool> g_writing{false};
LARGE_INTEGER g_freq{};

double now_ms() {
    LARGE_INTEGER c;
    QueryPerformanceCounter(&c);
    return double(c.QuadPart) * 1000.0 / double(g_freq.QuadPart);
}

std::string dll_dir() {
    HMODULE self = nullptr;
    GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                       (LPCSTR)&dll_dir, &self);
    char p[MAX_PATH] = {};
    GetModuleFileNameA(self, p, MAX_PATH);
    std::string s(p);
    const size_t cut = s.find_last_of("\\/");
    return cut == std::string::npos ? std::string(".") : s.substr(0, cut);
}

std::string read_file(const std::string& path) {
    std::string text;
    FILE* f = nullptr;
    if (fopen_s(&f, path.c_str(), "rb") == 0 && f) {
        char buf[4096];
        size_t n;
        while ((n = fread(buf, 1, sizeof buf, f)) > 0) text.append(buf, n);
        fclose(f);
    }
    return text;
}

std::string default_out_dir() {
    char local[MAX_PATH] = {};
    DWORD n = GetEnvironmentVariableA("LOCALAPPDATA", local, MAX_PATH);
    std::string base = (n > 0 && n < MAX_PATH) ? std::string(local) : std::string(".");
    return base + "\\Lanes\\tune\\meter";
}

void make_dirs(const std::string& dir) {
    for (size_t i = 3; i <= dir.size(); i++)
        if (i == dir.size() || dir[i] == '\\' || dir[i] == '/') CreateDirectoryA(dir.substr(0, i).c_str(), nullptr);
}

void write_live(const std::string& path) {
    const std::string tmp = path + ".tmp";
    FILE* f = nullptr;
    if (fopen_s(&f, tmp.c_str(), "wb") != 0 || !f) return;
    const std::string j = tm_meter::live_json(g_meter.live(), g_exe_stem.c_str(), double(time(nullptr)));
    fwrite(j.data(), 1, j.size(), f);
    fclose(f);
    MoveFileExA(tmp.c_str(), path.c_str(), MOVEFILE_REPLACE_EXISTING);
}

// One writer thread per session: the frame calls only push rows into memory, the disk is touched here.
void writer_loop(std::string csv_path, std::string live_path) {
    FILE* f = nullptr;
    if (fopen_s(&f, csv_path.c_str(), "wb") != 0) f = nullptr;
    if (f) {
        char exe[MAX_PATH] = {};
        GetModuleFileNameA(nullptr, exe, MAX_PATH);
        fprintf(f, "# Tune-o-matiC frame meter 1; exe=%s; started=%lld\n", exe, (long long)time(nullptr));
        fputs(tm_meter::csv_header(), f);
    }
    bool last = false;
    while (!last) {
        last = !g_writing.load();
        if (!last) Sleep(FLUSH_EVERY_MS);
        const auto rows = g_meter.take_rows();
        if (f && !rows.empty()) {
            std::string chunk;
            chunk.reserve(rows.size() * 48);
            for (const auto& r : rows) chunk += tm_meter::csv_line(r);
            fwrite(chunk.data(), 1, chunk.size(), f);
            fflush(f);
        }
        write_live(live_path);
    }
    if (f) fclose(f);
}

void start_writer() {
    if (g_writing.load()) return;
    make_dirs(g_out_dir);
    char stamp[32];
    const time_t t = time(nullptr);
    tm lt{};
    localtime_s(&lt, &t);
    strftime(stamp, sizeof stamp, "%Y-%m-%d_%H-%M-%S", &lt);
    g_meter.reset();
    g_writing = true;
    g_writer = std::thread(writer_loop, g_out_dir + "\\" + stamp + "_" + g_exe_stem + ".frametime.csv",
                           g_out_dir + "\\" + g_exe_stem + ".live.json");
}

void stop_writer() {
    if (!g_writing.exchange(false)) return;
    if (g_writer.joinable()) g_writer.join();
}

XRAPI_ATTR XrResult XRAPI_CALL tm_xrWaitFrame(XrSession s, const XrFrameWaitInfo* info, XrFrameState* state) {
    g_meter.wait_begin(now_ms());
    const XrResult r = g_next_wait(s, info, state);
    if (XR_SUCCEEDED(r) && state) g_meter.wait_end(now_ms(), state->predictedDisplayPeriod);
    return r;
}

XRAPI_ATTR XrResult XRAPI_CALL tm_xrEndFrame(XrSession s, const XrFrameEndInfo* info) {
    g_meter.frame_end(now_ms());
    return g_next_end(s, info);
}

XRAPI_ATTR XrResult XRAPI_CALL tm_xrCreateSession(XrInstance inst, const XrSessionCreateInfo* info, XrSession* s) {
    const XrResult r = g_next_create_session(inst, info, s);
    if (XR_SUCCEEDED(r)) start_writer();
    return r;
}

XRAPI_ATTR XrResult XRAPI_CALL tm_xrDestroySession(XrSession s) {
    stop_writer();
    return g_next_destroy_session(s);
}

template <typename T> void get(XrInstance inst, const char* name, T& slot) {
    PFN_xrVoidFunction f = nullptr;
    if (XR_SUCCEEDED(g_next_gipa(inst, name, &f)) && f) slot = reinterpret_cast<T>(f);
}

XRAPI_ATTR XrResult XRAPI_CALL tm_xrGetInstanceProcAddr(XrInstance instance, const char* name, PFN_xrVoidFunction* function) {
    const XrResult r = g_next_gipa(instance, name, function);
    if (!g_enabled || XR_FAILED(r) || !function || !*function || !name) return r;
    struct Hook { const char* name; PFN_xrVoidFunction ours; };
    static const Hook hooks[] = {
        {"xrWaitFrame", (PFN_xrVoidFunction)tm_xrWaitFrame},
        {"xrEndFrame", (PFN_xrVoidFunction)tm_xrEndFrame},
        {"xrCreateSession", (PFN_xrVoidFunction)tm_xrCreateSession},
        {"xrDestroySession", (PFN_xrVoidFunction)tm_xrDestroySession},
    };
    for (const auto& h : hooks)
        if (std::strcmp(name, h.name) == 0) { *function = h.ours; break; }
    return r;
}

XRAPI_ATTR XrResult XRAPI_CALL tm_xrCreateApiLayerInstance(const XrInstanceCreateInfo* info, const XrApiLayerCreateInfo* layer_info, XrInstance* instance) {
    if (!layer_info || !layer_info->nextInfo) return XR_ERROR_INITIALIZATION_FAILED;
    g_next_gipa = layer_info->nextInfo->nextGetInstanceProcAddr;
    XrApiLayerCreateInfo next_info = *layer_info;   // the next layer down gets the chain one step further on
    next_info.nextInfo = layer_info->nextInfo->next;
    const XrResult r = layer_info->nextInfo->nextCreateApiLayerInstance(info, &next_info, instance);
    if (XR_FAILED(r) || !instance) return r;
    const std::string dir = dll_dir();
    const tm_meter::Settings s = tm_meter::parse_settings(read_file(dir + "\\lanes_tune_meter.txt"));
    char exe[MAX_PATH] = {};
    GetModuleFileNameA(nullptr, exe, MAX_PATH);
    g_enabled = s.on >= 1 && tm_meter::exe_matches(s, exe);
    if (!g_enabled) return r;
    get(*instance, "xrWaitFrame", g_next_wait);
    get(*instance, "xrEndFrame", g_next_end);
    get(*instance, "xrCreateSession", g_next_create_session);
    get(*instance, "xrDestroySession", g_next_destroy_session);
    if (!g_next_wait || !g_next_end || !g_next_create_session || !g_next_destroy_session) {
        g_enabled = false;   // something below us is missing a core call: stay out of the way
        return r;
    }
    QueryPerformanceFrequency(&g_freq);
    g_out_dir = s.out.empty() ? default_out_dir() : s.out;
    std::string e(exe);
    const size_t cut = e.find_last_of("\\/");
    e = cut == std::string::npos ? e : e.substr(cut + 1);
    const size_t dot = e.find_last_of('.');
    g_exe_stem = dot == std::string::npos ? e : e.substr(0, dot);
    return r;
}

}  // namespace

extern "C" __declspec(dllexport) XrResult XRAPI_CALL xrNegotiateLoaderApiLayerInterface(const XrNegotiateLoaderInfo* loader_info, const char* /*layer_name*/, XrNegotiateApiLayerRequest* request) {
    if (!loader_info || !request || loader_info->structType != XR_LOADER_INTERFACE_STRUCT_LOADER_INFO ||
        request->structType != XR_LOADER_INTERFACE_STRUCT_API_LAYER_REQUEST ||
        loader_info->minInterfaceVersion > XR_CURRENT_LOADER_API_LAYER_VERSION ||
        loader_info->maxInterfaceVersion < XR_CURRENT_LOADER_API_LAYER_VERSION) {
        return XR_ERROR_INITIALIZATION_FAILED;
    }
    request->layerInterfaceVersion = XR_CURRENT_LOADER_API_LAYER_VERSION;
    request->layerApiVersion = loader_info->maxApiVersion < XR_CURRENT_API_VERSION ? loader_info->maxApiVersion : XR_CURRENT_API_VERSION;
    request->getInstanceProcAddr = tm_xrGetInstanceProcAddr;
    request->createApiLayerInstance = tm_xrCreateApiLayerInstance;
    return XR_SUCCESS;
}
