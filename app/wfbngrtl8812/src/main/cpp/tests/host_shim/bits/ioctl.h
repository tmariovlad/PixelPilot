// Host-only: bionic has <bits/ioctl.h>, glibc does not; TxFrame.cpp includes it for ioctl().
#pragma once
#include <sys/ioctl.h>
