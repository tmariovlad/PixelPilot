// Host-only stand-in for the NDK AAudio header: only the declarations AudioDecoder uses, so it compiles in gtest
// builds. The test that includes AudioDecoder provides the definitions (a fake that tracks stream state).
#ifndef PIXELPILOT_HOST_SHIM_AAUDIO_H
#define PIXELPILOT_HOST_SHIM_AAUDIO_H

#include <cstdint>

typedef int32_t aaudio_result_t;
typedef int32_t aaudio_format_t;

enum
{
    AAUDIO_OK         = 0,
    AAUDIO_ERROR_NULL = -883,
};
enum
{
    AAUDIO_FORMAT_PCM_I16 = 1,
};

typedef struct AAudioStreamStruct        AAudioStream;
typedef struct AAudioStreamBuilderStruct AAudioStreamBuilder;

aaudio_result_t AAudio_createStreamBuilder(AAudioStreamBuilder** builder);
void            AAudioStreamBuilder_setFormat(AAudioStreamBuilder* builder, aaudio_format_t format);
void            AAudioStreamBuilder_setChannelCount(AAudioStreamBuilder* builder, int32_t channelCount);
void            AAudioStreamBuilder_setSampleRate(AAudioStreamBuilder* builder, int32_t sampleRate);
void            AAudioStreamBuilder_setBufferCapacityInFrames(AAudioStreamBuilder* builder, int32_t numFrames);
aaudio_result_t AAudioStreamBuilder_openStream(AAudioStreamBuilder* builder, AAudioStream** stream);
aaudio_result_t AAudioStreamBuilder_delete(AAudioStreamBuilder* builder);
aaudio_result_t AAudioStream_requestStart(AAudioStream* stream);
aaudio_result_t AAudioStream_requestStop(AAudioStream* stream);
aaudio_result_t AAudioStream_close(AAudioStream* stream);
aaudio_result_t AAudioStream_write(AAudioStream* stream, const void* buffer, int32_t numFrames, int64_t timeoutNanos);

#endif  // PIXELPILOT_HOST_SHIM_AAUDIO_H
