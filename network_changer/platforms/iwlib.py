# -*- coding: utf-8 -*-
#
# TARGET arch is: ['-I/usr/lib/clang/7/include/']
# WORD_SIZE is: 8
# POINTER_SIZE is: 8
# LONGDOUBLE_SIZE is: 16
#
import ctypes


class AsDictMixin:
    @classmethod
    def as_dict(cls, self):
        result = {}
        if not isinstance(self, AsDictMixin):
            # not a structure, assume it's already a python object
            return self
        if not hasattr(cls, "_fields_"):
            return result
        # sys.version_info >= (3, 5)
        # for (field, *_) in cls._fields_:  # noqa
        for field_tuple in cls._fields_:  # noqa
            field = field_tuple[0]
            if field.startswith("PADDING_"):
                continue
            value = getattr(self, field)
            type_ = type(value)
            if hasattr(value, "_length_") and hasattr(value, "_type_"):
                # array
                if not hasattr(type_, "as_dict"):
                    value = [v for v in value]
                else:
                    type_ = type_._type_
                    value = [type_.as_dict(v) for v in value]
            elif hasattr(value, "contents") and hasattr(value, "_type_"):
                # pointer
                try:
                    if not hasattr(type_, "as_dict"):
                        value = value.contents
                    else:
                        type_ = type_._type_
                        value = type_.as_dict(value.contents)
                except ValueError:
                    # nullptr
                    value = None
            elif isinstance(value, AsDictMixin):
                # other structure
                value = type_.as_dict(value)
            result[field] = value
        return result


class Structure(ctypes.Structure, AsDictMixin):
    def __init__(self, *args, **kwds):
        # We don't want to use positional arguments fill PADDING_* fields

        args = dict(zip(self.__class__._field_names_(), args))
        args.update(kwds)
        super(Structure, self).__init__(**args)

    @classmethod
    def _field_names_(cls):
        if hasattr(cls, "_fields_"):
            return (f[0] for f in cls._fields_ if not f[0].startswith("PADDING"))
        else:
            return ()

    @classmethod
    def get_type(cls, field):
        for f in cls._fields_:
            if f[0] == field:
                return f[1]
        return None

    @classmethod
    def bind(cls, bound_fields):
        fields = {}
        for name, type_ in cls._fields_:
            if hasattr(type_, "restype"):
                if name in bound_fields:
                    if bound_fields[name] is None:
                        fields[name] = type_()
                    else:
                        # use a closure to capture the callback from the loop scope
                        fields[name] = type_(
                            (lambda callback: lambda *args: callback(*args))(bound_fields[name])
                        )
                    del bound_fields[name]
                else:
                    # default callback implementation (does nothing)
                    try:
                        default_ = type_(0).restype().value
                    except TypeError:
                        default_ = None
                    fields[name] = type_((lambda default_: lambda *args: default_)(default_))
            else:
                # not a callback function, use default initialization
                if name in bound_fields:
                    fields[name] = bound_fields[name]
                    del bound_fields[name]
                else:
                    fields[name] = type_()
        if len(bound_fields) != 0:
            raise ValueError(
                "Cannot bind the following unknown callback(s) {}.{}".format(
                    cls.__name__, bound_fields.keys()
                )
            )
        return cls(**fields)


class Union(ctypes.Union, AsDictMixin):
    pass


c_int128 = ctypes.c_ubyte * 16
c_uint128 = c_int128
void = None
if ctypes.sizeof(ctypes.c_longdouble) == 16:
    c_long_double_t = ctypes.c_longdouble
else:
    c_long_double_t = ctypes.c_ubyte * 16


def string_cast(char_pointer, encoding="utf-8", errors="strict"):
    value = ctypes.cast(char_pointer, ctypes.c_char_p).value
    if value is not None and encoding is not None:
        value = value.decode(encoding, errors=errors)
    return value


def char_pointer_cast(string, encoding="utf-8"):
    if encoding is not None:
        try:
            string = string.encode(encoding)
        except AttributeError:
            # In Python3, bytes has no encode attribute
            pass
    string = ctypes.c_char_p(string)
    return ctypes.cast(string, ctypes.POINTER(ctypes.c_char))


class struct_c__SA_fd_set(Structure):
    pass


struct_c__SA_fd_set._pack_ = 1  # source:False
struct_c__SA_fd_set._fields_ = [
    ("__fds_bits", ctypes.c_int64 * 16),
]

rfds = struct_c__SA_fd_set  # Variable struct_c__SA_fd_set


class struct_iwreq(Structure):
    pass


class union_iwreq_0(Union):
    pass


union_iwreq_0._pack_ = 1  # source:False
union_iwreq_0._fields_ = [
    ("ifrn_name", ctypes.c_ubyte * 16),
]


class union_iwreq_data(Union):
    pass


class struct_iw_param(Structure):
    pass


struct_iw_param._pack_ = 1  # source:False
struct_iw_param._fields_ = [
    ("value", ctypes.c_int32),
    ("fixed", ctypes.c_ubyte),
    ("disabled", ctypes.c_ubyte),
    ("flags", ctypes.c_uint16),
]


class struct_iw_quality(Structure):
    pass


struct_iw_quality._pack_ = 1  # source:False
struct_iw_quality._fields_ = [
    ("qual", ctypes.c_ubyte),
    ("level", ctypes.c_ubyte),
    ("noise", ctypes.c_ubyte),
    ("updated", ctypes.c_ubyte),
]


class struct_sockaddr(Structure):
    pass


struct_sockaddr._pack_ = 1  # source:False
struct_sockaddr._fields_ = [
    ("sa_family", ctypes.c_uint16),
    ("sa_data", ctypes.c_ubyte * 14),
]


class struct_iw_freq(Structure):
    pass


struct_iw_freq._pack_ = 1  # source:False
struct_iw_freq._fields_ = [
    ("m", ctypes.c_int32),
    ("e", ctypes.c_int16),
    ("i", ctypes.c_ubyte),
    ("flags", ctypes.c_ubyte),
]


class struct_iw_point(Structure):
    pass


struct_iw_point._pack_ = 1  # source:False
struct_iw_point._fields_ = [
    ("pointer", ctypes.POINTER(None)),
    ("length", ctypes.c_uint16),
    ("flags", ctypes.c_uint16),
    ("PADDING_0", ctypes.c_ubyte * 4),
]

union_iwreq_data._pack_ = 1  # source:False
union_iwreq_data._fields_ = [
    ("name", ctypes.c_ubyte * 16),
    ("essid", struct_iw_point),
    ("nwid", struct_iw_param),
    ("freq", struct_iw_freq),
    ("sens", struct_iw_param),
    ("bitrate", struct_iw_param),
    ("txpower", struct_iw_param),
    ("rts", struct_iw_param),
    ("frag", struct_iw_param),
    ("mode", ctypes.c_uint32),
    ("retry", struct_iw_param),
    ("encoding", struct_iw_point),
    ("power", struct_iw_param),
    ("qual", struct_iw_quality),
    ("ap_addr", struct_sockaddr),
    ("addr", struct_sockaddr),
    ("param", struct_iw_param),
    ("data", struct_iw_point),
]

struct_iwreq._pack_ = 1  # source:False
struct_iwreq._fields_ = [
    ("ifr_ifrn", union_iwreq_0),
    ("u", union_iwreq_data),
]

req = struct_iwreq  # Variable struct_iwreq


class struct_timeval(Structure):
    pass


struct_timeval._pack_ = 1  # source:False
struct_timeval._fields_ = [
    ("tv_sec", ctypes.c_int64),
    ("tv_usec", ctypes.c_int64),
]

tv = struct_timeval  # Variable struct_timeval


class struct_wireless_config(Structure):
    pass


struct_wireless_config._pack_ = 1  # source:False
struct_wireless_config._fields_ = [
    ("name", ctypes.c_ubyte * 17),
    ("PADDING_0", ctypes.c_ubyte * 3),
    ("has_nwid", ctypes.c_int32),
    ("nwid", struct_iw_param),
    ("has_freq", ctypes.c_int32),
    ("PADDING_1", ctypes.c_ubyte * 4),
    ("freq", ctypes.c_double),
    ("freq_flags", ctypes.c_int32),
    ("has_key", ctypes.c_int32),
    ("key", ctypes.c_ubyte * 64),
    ("key_size", ctypes.c_int32),
    ("key_flags", ctypes.c_int32),
    ("has_essid", ctypes.c_int32),
    ("essid_on", ctypes.c_int32),
    ("essid", ctypes.c_ubyte * 34),
    ("PADDING_2", ctypes.c_ubyte * 2),
    ("essid_len", ctypes.c_int32),
    ("has_mode", ctypes.c_int32),
    ("mode", ctypes.c_int32),
]

wc = struct_wireless_config  # Variable struct_wireless_config


class struct_iw_event(Structure):
    pass


struct_iw_event._pack_ = 1  # source:False
struct_iw_event._fields_ = [
    ("len", ctypes.c_uint16),
    ("cmd", ctypes.c_uint16),
    ("PADDING_0", ctypes.c_ubyte * 4),
    ("u", union_iwreq_data),
]

iwe = struct_iw_event  # Variable struct_iw_event


class struct_iw_range(Structure):
    pass


struct_iw_range._pack_ = 1  # source:False
struct_iw_range._fields_ = [
    ("throughput", ctypes.c_uint32),
    ("min_nwid", ctypes.c_uint32),
    ("max_nwid", ctypes.c_uint32),
    ("old_num_channels", ctypes.c_uint16),
    ("old_num_frequency", ctypes.c_ubyte),
    ("scan_capa", ctypes.c_ubyte),
    ("event_capa", ctypes.c_uint32 * 6),
    ("sensitivity", ctypes.c_int32),
    ("max_qual", struct_iw_quality),
    ("avg_qual", struct_iw_quality),
    ("num_bitrates", ctypes.c_ubyte),
    ("PADDING_0", ctypes.c_ubyte * 3),
    ("bitrate", ctypes.c_int32 * 32),
    ("min_rts", ctypes.c_int32),
    ("max_rts", ctypes.c_int32),
    ("min_frag", ctypes.c_int32),
    ("max_frag", ctypes.c_int32),
    ("min_pmp", ctypes.c_int32),
    ("max_pmp", ctypes.c_int32),
    ("min_pmt", ctypes.c_int32),
    ("max_pmt", ctypes.c_int32),
    ("pmp_flags", ctypes.c_uint16),
    ("pmt_flags", ctypes.c_uint16),
    ("pm_capa", ctypes.c_uint16),
    ("encoding_size", ctypes.c_uint16 * 8),
    ("num_encoding_sizes", ctypes.c_ubyte),
    ("max_encoding_tokens", ctypes.c_ubyte),
    ("encoding_login_index", ctypes.c_ubyte),
    ("PADDING_1", ctypes.c_ubyte),
    ("txpower_capa", ctypes.c_uint16),
    ("num_txpower", ctypes.c_ubyte),
    ("PADDING_2", ctypes.c_ubyte * 3),
    ("txpower", ctypes.c_int32 * 8),
    ("we_version_compiled", ctypes.c_ubyte),
    ("we_version_source", ctypes.c_ubyte),
    ("retry_capa", ctypes.c_uint16),
    ("retry_flags", ctypes.c_uint16),
    ("r_time_flags", ctypes.c_uint16),
    ("min_retry", ctypes.c_int32),
    ("max_retry", ctypes.c_int32),
    ("min_r_time", ctypes.c_int32),
    ("max_r_time", ctypes.c_int32),
    ("num_channels", ctypes.c_uint16),
    ("num_frequency", ctypes.c_ubyte),
    ("PADDING_3", ctypes.c_ubyte),
    ("freq", struct_iw_freq * 32),
    ("enc_capa", ctypes.c_uint32),
    ("min_pms", ctypes.c_int32),
    ("max_pms", ctypes.c_int32),
    ("pms_flags", ctypes.c_uint16),
    ("PADDING_4", ctypes.c_ubyte * 2),
    ("modul_capa", ctypes.c_int32),
    ("bitrate_capa", ctypes.c_uint32),
]

range = struct_iw_range  # Variable struct_iw_range


class struct_ether_addr(Structure):
    pass


struct_ether_addr._pack_ = 1  # source:True
struct_ether_addr._fields_ = [
    ("ether_addr_octet", ctypes.c_ubyte * 6),
]

addr = struct_ether_addr  # Variable struct_ether_addr


class struct_stream_descr(Structure):
    pass


struct_stream_descr._pack_ = 1  # source:False
struct_stream_descr._fields_ = [
    ("end", ctypes.POINTER(ctypes.c_ubyte)),
    ("current", ctypes.POINTER(ctypes.c_ubyte)),
    ("value", ctypes.POINTER(ctypes.c_ubyte)),
]

stream = struct_stream_descr  # Variable struct_stream_descr


class struct_iw_scan_req(Structure):
    pass


struct_iw_scan_req._pack_ = 1  # source:False
struct_iw_scan_req._fields_ = [
    ("scan_type", ctypes.c_ubyte),
    ("essid_len", ctypes.c_ubyte),
    ("num_channels", ctypes.c_ubyte),
    ("flags", ctypes.c_ubyte),
    ("bssid", struct_sockaddr),
    ("essid", ctypes.c_ubyte * 32),
    ("min_channel_time", ctypes.c_uint32),
    ("max_channel_time", ctypes.c_uint32),
    ("channel_list", struct_iw_freq * 32),
]

scanreq = struct_iw_scan_req  # Variable struct_iw_scan_req
__all__ = [
    "addr",
    "iwe",
    "range",
    "req",
    "rfds",
    "scanreq",
    "stream",
    "struct_c__SA_fd_set",
    "struct_ether_addr",
    "struct_iw_event",
    "struct_iw_freq",
    "struct_iw_param",
    "struct_iw_point",
    "struct_iw_quality",
    "struct_iw_range",
    "struct_iw_scan_req",
    "struct_iwreq",
    "struct_sockaddr",
    "struct_stream_descr",
    "struct_timeval",
    "struct_wireless_config",
    "tv",
    "union_iwreq_0",
    "union_iwreq_data",
    "wc",
]
