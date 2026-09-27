// Host-only: TxFrame.cpp includes the kernel uapi <linux/uio.h>, which clashes with glibc; use <sys/uio.h> instead.
#pragma once
#include <sys/uio.h>
