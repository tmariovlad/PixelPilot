// Host-only: TxFrame.cpp includes the kernel uapi <linux/time.h>, which clashes with glibc; use <sys/time.h> instead.
#pragma once
#include <sys/time.h>
