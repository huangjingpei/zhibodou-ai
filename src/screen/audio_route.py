# ====================== 播放设备自动设为系统默认 ======================
# scrcpy 4.1 只能把音频送进“Windows 默认播放设备”，没有“按名字选设备”的命令行参数；
# 唯一可靠的做法是：在启动 scrcpy 之前，把用户在 UI 选中的播放设备设为系统默认播放设备。
# 本模块用 Core Audio(MMDeviceEnumerator + IPolicyConfig) 完成这件事，失败安全：
# 任何异常都只返回 False 并交调用方降级处理，绝不抛错中断投屏流程。
import ctypes
from ctypes import POINTER, c_void_p, c_wchar_p, c_int, c_uint32, c_uint16, byref, cast, CFUNCTYPE

try:
    import comtypes
    from comtypes import GUID, IUnknown, COMMETHOD, HRESULT, Structure
    _HAVE_COMTYPES = True
except Exception:
    _HAVE_COMTYPES = False

_CLSID_MMDeviceEnumerator = "{BCDE0395-E52F-467C-8E3D-C4579291692E}"
_IID_IMMDeviceEnumerator = "{A95664D2-9614-4F35-A746-DE8DB63617E6}"
_CLSID_PolicyConfigClient = "{870af99C-171D-4F9E-AF0D-E63DF40C2BC9}"
_IID_IPolicyConfig = "{F8679F50-850A-41CF-9C72-430F290290C8}"
_CLSCTX_ALL = 1 | 4 | 16  # INPROC_SERVER | LOCAL_SERVER | INPROC_HANDLER

# MMDeviceEnumerator / IMMDevice / IPropertyStore 均为稳定且文档完备的接口。
if _HAVE_COMTYPES:
    class PROPERTYKEY(Structure):
        _fields_ = [("fmtid", GUID), ("pid", c_uint32)]

    _PKEY_Device_FriendlyName = PROPERTYKEY(
        GUID("{A45C254E-DF1C-4EFD-8020-67D146A850E0}"), 14
    )

    class PROPVARIANT(Structure):
        _fields_ = [
            ("vt", c_uint32),
            ("wReserved1", c_uint16),
            ("wReserved2", c_uint16),
            ("pwszVal", c_wchar_p),
        ]

    class IPropertyStore(IUnknown):
        _iid_ = GUID("{886D8EEB-8AEC-4DA1-9E8F-9753C00A9243}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetCount", (["out"], POINTER(c_uint32), "cProps")),
            COMMETHOD([], HRESULT, "GetAt", (["in"], c_uint32, "iProp"), (["out"], POINTER(PROPERTYKEY), "pkey")),
            COMMETHOD([], HRESULT, "GetValue", (["in"], POINTER(PROPERTYKEY), "key"), (["out"], POINTER(PROPVARIANT), "pv")),
            COMMETHOD([], HRESULT, "SetValue", (["in"], POINTER(PROPERTYKEY), "key"), (["in"], POINTER(PROPVARIANT), "pv")),
            COMMETHOD([], HRESULT, "Commit"),
        ]

    class IMMDevice(IUnknown):
        _iid_ = GUID("{D666063F-1587-4E43-81F1-B948E807363F}")
        _methods_ = [
            COMMETHOD([], HRESULT, "Activate", (["in"], GUID, "iid"), (["in"], c_int, "dwClsCtx"),
                      (["in"], c_void_p, "pActivationParams"), (["out"], c_void_p, "ppInterface")),
            COMMETHOD([], HRESULT, "OpenPropertyStore", (["in"], c_int, "stgmAccess"),
                      (["out"], POINTER(POINTER(IPropertyStore)), "ppProperties")),
            COMMETHOD([], HRESULT, "GetId", (["out"], POINTER(c_wchar_p), "ppstrId")),
            COMMETHOD([], HRESULT, "GetState", (["out"], POINTER(c_uint32), "pdwState")),
        ]

    class IMMDeviceCollection(IUnknown):
        _iid_ = GUID("{0BD7A1BE-7A1A-44DB-8397-CC5392387B5E}")
        _methods_ = [
            COMMETHOD([], HRESULT, "GetCount", (["out"], POINTER(c_uint32), "pcDevices")),
            COMMETHOD([], HRESULT, "Item", (["in"], c_uint32, "nDevice"),
                      (["out"], POINTER(POINTER(IMMDevice)), "ppDevice")),
        ]

    class IMMDeviceEnumerator(IUnknown):
        _iid_ = GUID(_IID_IMMDeviceEnumerator)
        _methods_ = [
            COMMETHOD([], HRESULT, "EnumAudioEndpoints", (["in"], c_int, "dataFlow"),
                      (["in"], c_int, "dwStateMask"), (["out"], POINTER(POINTER(IMMDeviceCollection)), "ppDevices")),
            COMMETHOD([], HRESULT, "GetDefaultAudioEndpoint", (["in"], c_int, "dataFlow"),
                      (["in"], c_int, "role"), (["out"], POINTER(POINTER(IMMDevice)), "ppEndpoint")),
            COMMETHOD([], HRESULT, "GetDevice", (["in"], c_wchar_p, "pwstrId"),
                      (["out"], POINTER(POINTER(IMMDevice)), "ppDevice")),
            COMMETHOD([], HRESULT, "RegisterEndpointNotificationCallback", (["in"], c_void_p, "pClient")),
            COMMETHOD([], HRESULT, "UnregisterEndpointNotificationCallback", (["in"], c_void_p, "pClient")),
        ]


def _guid_from_str(s: str) -> "GUID":
    return GUID(s)


def _coinit():
    try:
        ctypes.windll.ole32.CoInitialize(None)
    except Exception:
        pass


def _vtbl_call(p_interface, slot, *args):
    """直接调用 COM 接口 vtable 指定槽位。返回 HRESULT(忽略)。"""
    vtable = cast(p_interface, POINTER(POINTER(c_void_p)))
    func_ptr = vtable.contents[slot]
    proto = CFUNCTYPE(HRESULT, c_void_p, *[type(a) for a in args])
    func = cast(func_ptr, proto)
    return func(p_interface, *args)


def _propvariant_to_str(pv: "PROPVARIANT") -> str:
    try:
        if getattr(pv, "vt", 0) == 31 and pv.pwszVal:  # VT_LPWSTR
            return pv.pwszVal
    except Exception:
        pass
    return ""


def find_render_endpoint_id(substr: str) -> str:
    """按友好名(子串匹配, 不区分大小写)查找“播放/渲染”端点的 endpoint ID。找不到返回空串。"""
    if not _HAVE_COMTYPES or not substr:
        return ""
    _coinit()
    enumerator = POINTER(IMMDeviceEnumerator)()
    hr = ctypes.windll.ole32.CoCreateInstance(
        byref(_guid_from_str(_CLSID_MMDeviceEnumerator)),
        None, _CLSCTX_ALL, byref(_guid_from_str(_IID_IMMDeviceEnumerator)), byref(enumerator),
    )
    if hr < 0 or not enumerator:
        return ""
    try:
        collection = POINTER(IMMDeviceCollection)()
        hr = enumerator.EnumAudioEndpoints(0, 1, byref(collection))  # eRender=0, DEVICE_STATE_ACTIVE=1
        if hr < 0 or not collection:
            return ""
        count = c_uint32(0)
        collection.GetCount(byref(count))
        sub = substr.lower()
        for i in range(count.value):
            device = POINTER(IMMDevice)()
            if collection.Item(i, byref(device)) < 0 or not device:
                continue
            store = POINTER(IPropertyStore)()
            if device.OpenPropertyStore(0, byref(store)) < 0 or not store:  # STGM_READ=0
                continue
            pv = PROPVARIANT()
            if store.GetValue(byref(_PKEY_Device_FriendlyName), byref(pv)) < 0:
                continue
            name = _propvariant_to_str(pv)
            if name and sub in name.lower():
                pid = c_wchar_p()
                if device.GetId(byref(pid)) >= 0 and pid:
                    return pid.value
        return ""
    except Exception:
        return ""
    finally:
        try:
            enumerator.Release()
        except Exception:
            pass


def set_default_playback_device(device_name: str) -> bool:
    """把 device_name(友好名子串)对应的播放设备设为 Windows 默认播放设备。
    返回是否成功。失败安全：任何异常都返回 False，不向外抛出。"""
    if not _HAVE_COMTYPES or not device_name:
        return False
    endpoint_id = find_render_endpoint_id(device_name)
    if not endpoint_id:
        return False
    _coinit()
    policy = POINTER(IUnknown)()
    hr = ctypes.windll.ole32.CoCreateInstance(
        byref(_guid_from_str(_CLSID_PolicyConfigClient)),
        None, _CLSCTX_ALL, byref(_guid_from_str(_IID_IPolicyConfig)), byref(policy),
    )
    if hr < 0 or not policy:
        return False
    try:
        # IPolicyConfig::SetDefaultEndpoint 在 vtable 槽位 12（Win10/11 通用）。
        # eRole: eConsole=0, eMultimedia=1, eCommunications=2；三档全置为该设备，覆盖最全。
        ok = False
        for role in (0, 1, 2):
            try:
                _vtbl_call(policy, 12, c_wchar_p(endpoint_id), c_int(role))
                ok = True
            except Exception:
                pass
        return ok
    except Exception:
        return False
    finally:
        try:
            policy.Release()
        except Exception:
            pass


def get_default_playback_device_name() -> str:
    """返回当前 Windows 默认播放设备的友好名；失败返回空串。"""
    if not _HAVE_COMTYPES:
        return ""
    _coinit()
    enumerator = POINTER(IMMDeviceEnumerator)()
    hr = ctypes.windll.ole32.CoCreateInstance(
        byref(_guid_from_str(_CLSID_MMDeviceEnumerator)),
        None, _CLSCTX_ALL, byref(_guid_from_str(_IID_IMMDeviceEnumerator)), byref(enumerator),
    )
    if hr < 0 or not enumerator:
        return ""
    try:
        device = POINTER(IMMDevice)()
        if enumerator.GetDefaultAudioEndpoint(0, 0, byref(device)) < 0 or not device:  # eRender=0, eConsole=0
            return ""
        store = POINTER(IPropertyStore)()
        if device.OpenPropertyStore(0, byref(store)) < 0 or not store:
            return ""
        pv = PROPVARIANT()
        if store.GetValue(byref(_PKEY_Device_FriendlyName), byref(pv)) < 0:
            return ""
        return _propvariant_to_str(pv)
    except Exception:
        return ""
    finally:
        try:
            enumerator.Release()
        except Exception:
            pass
