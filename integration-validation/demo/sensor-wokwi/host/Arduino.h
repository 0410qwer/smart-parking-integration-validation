#pragma once
// Host-only GPIO/clock test double. Never use as Wokwi sensor evidence.
#include <cstdint>
#include <cstdio>
#include <vector>
constexpr int HIGH=1, LOW=0, OUTPUT=1, INPUT=0;
inline uint32_t clockMs=0, suppliedPulse=580, lastTimeout=0;
inline std::vector<int> writes;
inline uint32_t millis(){return clockMs;}
inline void delay(uint32_t ms){clockMs+=ms;}
inline void delayMicroseconds(uint32_t){}
inline void pinMode(int,int){}
inline void digitalWrite(int pin,int value){writes.push_back(pin*10+value);}
inline uint32_t pulseIn(int pin,int level,uint32_t timeout){lastTimeout=timeout;return suppliedPulse;}
struct SerialStub{
 void begin(int){}
 template<class... Args>int printf(const char* format,Args... args){return std::printf(format,args...);}
 void println(const char* text){std::puts(text);}
};
inline SerialStub Serial;
