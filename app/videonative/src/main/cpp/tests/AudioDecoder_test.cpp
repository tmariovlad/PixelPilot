#include "AudioDecoder.h"
#include <gtest/gtest.h>
#include <cstdlib>
#include <map>

// Fake AAudio + opus. A closed stream is kept (not freed) and marked closed, so a call on it is counted instead of
// being the use-after-free it is on the device, where AAudioStream_close() releases the stream.
struct AAudioStreamStruct
{
    bool closed = false;
};
struct AAudioStreamBuilderStruct
{
};
struct OpusDecoder
{
};

namespace
{
std::map<AAudioStream*, AAudioStreamStruct*> g_streams;
int                                          g_callsOnClosed = 0;
int                                          g_opened        = 0;
int                                          g_opusCreated   = 0;
int                                          g_opusDestroyed = 0;

aaudio_result_t onStream(AAudioStream* s)
{
    if (s == nullptr) return AAUDIO_ERROR_NULL;
    if (s->closed) ++g_callsOnClosed;
    return AAUDIO_OK;
}

void resetFakes()
{
    for (auto& kv : g_streams) delete kv.second;
    g_streams.clear();
    g_callsOnClosed = 0;
    g_opened        = 0;
    g_opusCreated   = 0;
    g_opusDestroyed = 0;
}

int openStreams()
{
    int n = 0;
    for (auto& kv : g_streams) n += !kv.second->closed;
    return n;
}
}  // namespace

aaudio_result_t AAudio_createStreamBuilder(AAudioStreamBuilder** b)
{
    *b = new AAudioStreamBuilderStruct;
    return AAUDIO_OK;
}
void            AAudioStreamBuilder_setFormat(AAudioStreamBuilder*, aaudio_format_t) {}
void            AAudioStreamBuilder_setChannelCount(AAudioStreamBuilder*, int32_t) {}
void            AAudioStreamBuilder_setSampleRate(AAudioStreamBuilder*, int32_t) {}
void            AAudioStreamBuilder_setBufferCapacityInFrames(AAudioStreamBuilder*, int32_t) {}
aaudio_result_t AAudioStreamBuilder_openStream(AAudioStreamBuilder*, AAudioStream** s)
{
    *s            = new AAudioStreamStruct;
    g_streams[*s] = *s;
    ++g_opened;
    return AAUDIO_OK;
}
aaudio_result_t AAudioStreamBuilder_delete(AAudioStreamBuilder* b)
{
    delete b;
    return AAUDIO_OK;
}
aaudio_result_t AAudioStream_requestStart(AAudioStream* s) { return onStream(s); }
aaudio_result_t AAudioStream_requestStop(AAudioStream* s) { return onStream(s); }
aaudio_result_t AAudioStream_close(AAudioStream* s)
{
    aaudio_result_t r = onStream(s);
    if (s) s->closed = true;
    return r;
}
aaudio_result_t AAudioStream_write(AAudioStream* s, const void*, int32_t n, int64_t)
{
    onStream(s);
    return n;
}

// Like libopus: the state comes from malloc (opus_alloc) and must go back through opus_decoder_destroy().
OpusDecoder* opus_decoder_create(opus_int32, int, int* error)
{
    *error = 0;
    ++g_opusCreated;
    return static_cast<OpusDecoder*>(std::malloc(sizeof(OpusDecoder)));
}
void opus_decoder_destroy(OpusDecoder* st)
{
    if (st) ++g_opusDestroyed;
    std::free(st);
}
int opus_decode(OpusDecoder*, const unsigned char*, opus_int32, opus_int16*, int frame_size, int) { return frame_size; }
int opus_packet_get_samples_per_frame(const unsigned char*, opus_int32) { return 960; }
int opus_packet_get_nb_frames(const unsigned char*, opus_int32) { return 1; }

class AudioDecoderTest : public ::testing::Test
{
  protected:
    void SetUp() override { resetFakes(); }
    void TearDown() override { resetFakes(); }
};

// XrVideoActivity stops the player on every XR_SESSION_STATE_STOPPING and never calls startAudio(), so the second
// session stop runs stopAudio() on a stream the first one already closed (SIGABRT on the Quest, 2026-09-27).
TEST_F(AudioDecoderTest, SecondStopDoesNotTouchTheClosedStream)
{
    AudioDecoder d;
    d.stopAudio();
    d.stopAudio();
    EXPECT_EQ(g_callsOnClosed, 0);
}

TEST_F(AudioDecoderTest, DestructorAfterStopDoesNotTouchTheClosedStream)
{
    {
        AudioDecoder d;
        d.stopAudio();
    }
    EXPECT_EQ(g_callsOnClosed, 0);
}

TEST_F(AudioDecoderTest, StopClosesTheStreamAndClearsInit)
{
    AudioDecoder d;
    EXPECT_TRUE(d.isInit);
    EXPECT_EQ(openStreams(), 1);
    d.stopAudio();
    EXPECT_FALSE(d.isInit);
    EXPECT_EQ(openStreams(), 0);
}

// The 2D activity's path: stop, then startAudio() re-inits because isInit is false.
TEST_F(AudioDecoderTest, InitAfterStopOpensAFreshStream)
{
    AudioDecoder d;
    d.stopAudio();
    d.initAudio();
    EXPECT_TRUE(d.isInit);
    EXPECT_EQ(g_opened, 2);
    EXPECT_EQ(openStreams(), 1);
    d.stopAudio();
    EXPECT_EQ(g_callsOnClosed, 0);
}

// opus.h: a decoder from opus_decoder_create() is freed with opus_decoder_destroy(), not delete.
TEST_F(AudioDecoderTest, DestructorFreesTheOpusDecoderWithOpusDestroy)
{
    {
        AudioDecoder d;
    }
    EXPECT_EQ(g_opusCreated, 1);
    EXPECT_EQ(g_opusDestroyed, 1);
}

// The 2D activity re-inits audio after every stop: that must not leave the previous decoder behind.
TEST_F(AudioDecoderTest, ReinitDoesNotLeakTheOpusDecoder)
{
    {
        AudioDecoder d;
        d.stopAudio();
        d.initAudio();
        d.stopAudio();
        d.initAudio();
        EXPECT_EQ(g_opusCreated - g_opusDestroyed, 1);
    }
    EXPECT_EQ(g_opusCreated, g_opusDestroyed);
}
