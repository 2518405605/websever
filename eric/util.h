#ifndef _ERIC_UTIL_H_
#define _ERIC_UTIL_H_

#include <unistd.h>
#include<pthread.h>
#include<sys/types.h>
#include<sys/syscall.h>
#include<stdio.h>
#include<stdint.h>

namespace eric
{

pid_t GetThreadId();
u_int32_t GetFiberId();
} 


#endif