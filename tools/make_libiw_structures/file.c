#include <iwlib.h>

fd_set rfds;
struct iwreq req;
struct timeval tv;
wireless_config wc;
struct iw_event iwe;
struct iw_range range;
struct ether_addr addr;
struct stream_descr stream;
struct iw_scan_req scanreq;
