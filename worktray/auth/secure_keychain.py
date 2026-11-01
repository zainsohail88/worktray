"""Update encrypted macOS Keychain data without deleting the previous credential.

This module loads Apple's Security framework when imported, so only macOS code paths import it.
"""

import ctypes
from ctypes.util import find_library

from keyring.backends.macOS import api
from keyring.errors import KeyringError


_security = ctypes.CDLL(find_library("Security"))
_core = ctypes.CDLL(find_library("CoreFoundation"))
_update_item = _security.SecItemUpdate
_update_item.restype = ctypes.c_int32
_update_item.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
_create_data = _core.CFDataCreate
_create_data.restype = ctypes.c_void_p
_create_data.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long)
_release = _core.CFRelease
_release.restype = None
_release.argtypes = (ctypes.c_void_p,)


def save_password(service: str, account: str, password: str) -> None:
    """Use SecItemUpdate because keyring's macOS setter deletes before adding.

    Apple documents in-place updates with CFData at:
    https://developer.apple.com/documentation/security/updating-and-deleting-keychain-items
    """
    encoded = password.encode("utf-8")
    buffer = ctypes.create_string_buffer(encoded)
    service_value = ctypes.c_void_p(api.create_cf(service))
    account_value = ctypes.c_void_p(api.create_cf(account))
    data = ctypes.c_void_p(_create_data(None, ctypes.cast(buffer, ctypes.c_void_p), len(encoded)))
    identity = {"kSecClass": api.k_("kSecClassGenericPassword"), "kSecAttrService": service_value, "kSecAttrAccount": account_value}
    query = api.create_query(**identity)
    attributes = api.create_query(kSecValueData=data)
    addition = None
    try:
        status = _update_item(query, attributes)
        if status == api.error.item_not_found:
            addition = api.create_query(**identity, kSecValueData=data)
            status = api.SecItemAdd(addition, None)
        api.Error.raise_for_status(status)
    except api.Error as error:
        # Callers handle one error family for every platform's keyring.
        raise KeyringError(str(error)) from error
    finally:
        for value in (addition, attributes, query, data, account_value, service_value):
            if value:
                _release(value)
