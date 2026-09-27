// Host-only: TxFrame.cpp includes the kernel uapi <linux/in.h>, which clashes with glibc; use <netinet/in.h> instead.
#pragma once
#include <netinet/in.h>
