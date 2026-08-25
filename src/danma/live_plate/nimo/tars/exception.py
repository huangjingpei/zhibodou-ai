
class TarsException(Exception): pass


class TarsTarsDecodeRequireNotExist(TarsException):    pass


class TarsTarsDecodeMismatch(TarsException):           pass


class TarsTarsDecodeInvalidValue(TarsException):       pass


class TarsTarsUnsupportType(TarsException):            pass


class TarsNetConnectException(TarsException):         pass


class TarsNetConnectLostException(TarsException):     pass


class TarsNetSocketException(TarsException):          pass


class TarsProxyDecodeException(TarsException):        pass


class TarsProxyEncodeException(TarsException):        pass


class TarsServerEncodeException(TarsException):       pass


class TarsServerDecodeException(TarsException):       pass


class TarsServerNoFuncException(TarsException):       pass


class TarsServerNoServantException(TarsException):    pass


class TarsServerQueueTimeoutException(TarsException): pass


class TarsServerUnknownException(TarsException):      pass


class TarsSyncCallTimeoutException(TarsException):    pass


class TarsRegistryException(TarsException):           pass


class TarsServerResetGridException(TarsException):    pass
