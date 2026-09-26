# Quest OpenXR low-latency viewer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a native OpenXR activity to PixelPilot that shows the decoded FPV stream on a compositor-owned Android surface (head-locked layer, 120 Hz) plus switchable latency levers in the decoder.

**Architecture:** A new Gradle module `app/xr` (C++ OpenXR runtime on its own thread + Java `XrBridge`) creates two `XR_KHR_android_surface_swapchain` surfaces. `XrVideoActivity` hands the video surface to the unchanged-in-principle `VideoPlayer`, so MediaCodec renders straight into the compositor. `LatencyExperiments` (videonative) is the single source of truth for every lever; the decoder gains picture-order / operating-rate / low-latency-component / access-unit-aggregation levers, all default off.

**Tech Stack:** Android (Java 17, AGP 8.5.2, compileSdk 34, minSdk 26), NDK 26.1.10909125, CMake 3.22.1, Khronos OpenXR loader AAR `org.khronos.openxr:openxr_loader_for_android:1.1.63` (prefab), JUnit 4.13.2, GoogleTest 1.14 (host, WSL Ubuntu-22.04).

**Spec:** `docs/superpowers/specs/2026-09-26-quest-openxr-viewer-design.md`

## Global Constraints

- Build with JDK 17: `export JAVA_HOME='C:\Program Files\Java\jdk-17'`; `local.properties` = `sdk.dir=C:/Users/vlad_/AppData/Local/Android/Sdk` (forward slashes — backslashes are escape chars in .properties).
- `ndkVersion '26.1.10909125'`, CMake `3.22.1`, `compileSdk 34`, `minSdk 26`, Java 17 source/target — same as the existing modules.
- New decoder levers default **off**; `low_latency_decoder` keeps its existing key and default **true**.
- No silent fallback to a slower presentation path: if the surface swapchain is unavailable, the XR activity finishes with a message.
- Never write to the XR video surface outside session states VISIBLE/FOCUSED (spec `XR_KHR_android_surface_swapchain`).
- Every pref key lives only in `LatencyExperiments` (SSoT); callers use its constants.
- Host gtests run in WSL: `MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-22.04 -- bash -lc 'cmake -S /mnt/c/xampp/htdocs/pixelpilot-xr/app/videonative/src/main/cpp/tests -B /tmp/ppxr-tests && cmake --build /tmp/ppxr-tests -j8 && cd /tmp/ppxr-tests && ctest --output-on-failure'`
- Android build: `cd /c/xampp/htdocs/pixelpilot-xr && ./gradlew --no-daemon assembleDebug` (retry once on the Windows "Could not move temporary workspace" cache race).
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; `git add` only the task's files.

## Review Focus

1. A lost RTP marker (last packet of a frame dropped) must not merge two pictures into one decoder buffer — pinned in Task 2 (`LostMarkerSplitsOnNextFirstSlice`).
2. A decoder that rejects the new keys must still play video (retry without extras) — covered structurally in Task 3 (`onlyBase`) and by the configure retry code.
3. Leaving the app / taking the headset off (session STOPPING or drop to SYNCHRONIZED) must stop the decoder writing before `xrEndSession`, and must not deadlock with `onDestroy` — Task 6 (`destroying` flag + latch with timeout).
4. Unknown / out-of-range stored prefs (e.g. refresh 144, FOV NaN) must fall back to defaults — pinned in Task 1.
5. Zero video size before the first SPS must not produce a zero/NaN layer size — pinned in Task 5 (`zeroSizeFallsBackTo16by9`).

---

### Task 1: `LatencyExperiments` — single source of truth for the levers

**Files:**
- Create: `app/videonative/src/main/java/com/openipc/videonative/LatencyExperiments.java`
- Create: `app/videonative/src/test/java/com/openipc/videonative/LatencyExperimentsTest.java`
- Modify: `gradle/libs.versions.toml` (add junit), `app/videonative/build.gradle` (testImplementation)
- Modify: `app/src/main/java/com/openipc/pixelpilot/VideoActivity.java:171-174,753-754` (use the constant/loader)

**Interfaces:**
- Produces: `LatencyExperiments.load(Context)`, `LatencyExperiments.from(PrefSource)`, public final fields `lowLatencyDecoder, decPictureOrder, decOperatingRate, decPreferLowLatencyComponent, auAggregation, xrRefreshHz (int), xrUseTimestamps, xrLayerShape (LayerShape), xrPerfSustainedHigh, xrFovDeg (float), xrFlipVertical`; key constants `KEY_*`, `PREFS_NAME = "general"`; `summary()`.

- [ ] **Step 1: add JUnit to the version catalog and videonative**

`gradle/libs.versions.toml` — under `[versions]` add `junit = "4.13.2"`; under `[libraries]` add
`junit = { group = "junit", name = "junit", version.ref = "junit" }`.
`app/videonative/build.gradle` — in `dependencies { }` add `testImplementation(libs.junit)`.

- [ ] **Step 2: write the failing test**

```java
package com.openipc.videonative;

import static org.junit.Assert.*;

import java.util.HashMap;
import java.util.Map;
import org.junit.Test;

public class LatencyExperimentsTest {
    private static final class MapPrefs implements LatencyExperiments.PrefSource {
        final Map<String, Object> m = new HashMap<>();
        MapPrefs put(String k, Object v) { m.put(k, v); return this; }
        public boolean getBoolean(String k, boolean d) { Object v = m.get(k); return v instanceof Boolean ? (Boolean) v : d; }
        public int getInt(String k, int d) { Object v = m.get(k); return v instanceof Integer ? (Integer) v : d; }
        public float getFloat(String k, float d) { Object v = m.get(k); return v instanceof Float ? (Float) v : d; }
        public String getString(String k, String d) { Object v = m.get(k); return v instanceof String ? (String) v : d; }
    }

    @Test public void defaultsMatchSpec() {
        LatencyExperiments e = LatencyExperiments.from(new MapPrefs());
        assertTrue(e.lowLatencyDecoder);
        assertFalse(e.decPictureOrder);
        assertFalse(e.decOperatingRate);
        assertFalse(e.decPreferLowLatencyComponent);
        assertFalse(e.auAggregation);
        assertEquals(120, e.xrRefreshHz);
        assertFalse(e.xrUseTimestamps);
        assertEquals(LatencyExperiments.LayerShape.QUAD, e.xrLayerShape);
        assertTrue(e.xrPerfSustainedHigh);
        assertEquals(60f, e.xrFovDeg, 0f);
        assertTrue(e.xrFlipVertical);
    }

    @Test public void storedValuesAreRead() {
        MapPrefs p = new MapPrefs()
                .put(LatencyExperiments.KEY_LOW_LATENCY_DECODER, false)
                .put(LatencyExperiments.KEY_DEC_PICTURE_ORDER, true)
                .put(LatencyExperiments.KEY_AU_AGGREGATION, true)
                .put(LatencyExperiments.KEY_XR_REFRESH_HZ, 90)
                .put(LatencyExperiments.KEY_XR_LAYER_SHAPE, "cylinder")
                .put(LatencyExperiments.KEY_XR_FOV_DEG, 80f);
        LatencyExperiments e = LatencyExperiments.from(p);
        assertFalse(e.lowLatencyDecoder);
        assertTrue(e.decPictureOrder);
        assertTrue(e.auAggregation);
        assertEquals(90, e.xrRefreshHz);
        assertEquals(LatencyExperiments.LayerShape.CYLINDER, e.xrLayerShape);
        assertEquals(80f, e.xrFovDeg, 0f);
    }

    @Test public void unsupportedRefreshFallsBackToDefault() {
        assertEquals(120, LatencyExperiments.from(new MapPrefs().put(LatencyExperiments.KEY_XR_REFRESH_HZ, 144)).xrRefreshHz);
        assertEquals(120, LatencyExperiments.from(new MapPrefs().put(LatencyExperiments.KEY_XR_REFRESH_HZ, 0)).xrRefreshHz);
    }

    @Test public void fovIsClampedAndNaNIsDefault() {
        assertEquals(LatencyExperiments.MAX_FOV_DEG, LatencyExperiments.from(new MapPrefs().put(LatencyExperiments.KEY_XR_FOV_DEG, 500f)).xrFovDeg, 0f);
        assertEquals(LatencyExperiments.MIN_FOV_DEG, LatencyExperiments.from(new MapPrefs().put(LatencyExperiments.KEY_XR_FOV_DEG, 1f)).xrFovDeg, 0f);
        assertEquals(LatencyExperiments.DEFAULT_FOV_DEG, LatencyExperiments.from(new MapPrefs().put(LatencyExperiments.KEY_XR_FOV_DEG, Float.NaN)).xrFovDeg, 0f);
    }

    @Test public void unknownShapeIsQuad() {
        assertEquals(LatencyExperiments.LayerShape.QUAD, LatencyExperiments.from(new MapPrefs().put(LatencyExperiments.KEY_XR_LAYER_SHAPE, "sphere")).xrLayerShape);
    }

    @Test public void summaryListsOnlyEnabledLevers() {
        assertEquals("LL | 120Hz quad perf flip", LatencyExperiments.from(new MapPrefs()).summary());
        MapPrefs p = new MapPrefs().put(LatencyExperiments.KEY_LOW_LATENCY_DECODER, false)
                .put(LatencyExperiments.KEY_XR_PERF_SUSTAINED_HIGH, false)
                .put(LatencyExperiments.KEY_XR_FLIP_VERTICAL, false);
        assertEquals("stock | 120Hz quad", LatencyExperiments.from(p).summary());
    }
}
```

- [ ] **Step 3: run it — expect compile failure**

Run: `cd /c/xampp/htdocs/pixelpilot-xr && ./gradlew --no-daemon :app:videonative:testDebugUnitTest`
Expected: FAIL, `cannot find symbol class LatencyExperiments`.

- [ ] **Step 4: implement**

```java
package com.openipc.videonative;

import android.content.Context;
import android.content.SharedPreferences;

/**
 * Single source of truth for every latency lever: pref keys, defaults and validation.
 * The 2D activity, the XR activity and the decoder all read it; nothing else names these keys.
 * An instance is an immutable snapshot of the prefs at load time.
 */
public final class LatencyExperiments {
    public static final String PREFS_NAME = "general";

    public static final String KEY_LOW_LATENCY_DECODER = "low_latency_decoder";
    public static final String KEY_DEC_PICTURE_ORDER = "dec_picture_order";
    public static final String KEY_DEC_OPERATING_RATE = "dec_operating_rate";
    public static final String KEY_DEC_PREFER_LOW_LATENCY_COMPONENT = "dec_prefer_low_latency_component";
    public static final String KEY_AU_AGGREGATION = "au_aggregation";
    public static final String KEY_XR_REFRESH_HZ = "xr_refresh_hz";
    public static final String KEY_XR_USE_TIMESTAMPS = "xr_use_timestamps";
    public static final String KEY_XR_LAYER_SHAPE = "xr_layer_shape";
    public static final String KEY_XR_PERF_SUSTAINED_HIGH = "xr_perf_sustained_high";
    public static final String KEY_XR_FOV_DEG = "xr_fov_deg";
    public static final String KEY_XR_FLIP_VERTICAL = "xr_flip_vertical";

    /** Refresh rates Quest 2 offers to OpenXR apps (60 Hz is media-only). */
    public static final int[] SUPPORTED_REFRESH_HZ = {72, 80, 90, 120};
    public static final int DEFAULT_REFRESH_HZ = 120;
    public static final float DEFAULT_FOV_DEG = 60f;
    public static final float MIN_FOV_DEG = 20f;
    public static final float MAX_FOV_DEG = 110f;

    public enum LayerShape {
        QUAD, CYLINDER;

        static LayerShape parse(String value) {
            return "cylinder".equalsIgnoreCase(value) ? CYLINDER : QUAD;
        }

        public String prefValue() {
            return this == CYLINDER ? "cylinder" : "quad";
        }
    }

    /** Read-only key/value source, so the parsing is testable without Android. */
    public interface PrefSource {
        boolean getBoolean(String key, boolean def);
        int getInt(String key, int def);
        float getFloat(String key, float def);
        String getString(String key, String def);
    }

    public final boolean lowLatencyDecoder;
    public final boolean decPictureOrder;
    public final boolean decOperatingRate;
    public final boolean decPreferLowLatencyComponent;
    public final boolean auAggregation;
    public final int xrRefreshHz;
    public final boolean xrUseTimestamps;
    public final LayerShape xrLayerShape;
    public final boolean xrPerfSustainedHigh;
    public final float xrFovDeg;
    public final boolean xrFlipVertical;

    private LatencyExperiments(PrefSource p) {
        lowLatencyDecoder = p.getBoolean(KEY_LOW_LATENCY_DECODER, true);
        decPictureOrder = p.getBoolean(KEY_DEC_PICTURE_ORDER, false);
        decOperatingRate = p.getBoolean(KEY_DEC_OPERATING_RATE, false);
        decPreferLowLatencyComponent = p.getBoolean(KEY_DEC_PREFER_LOW_LATENCY_COMPONENT, false);
        auAggregation = p.getBoolean(KEY_AU_AGGREGATION, false);
        xrRefreshHz = validRefresh(p.getInt(KEY_XR_REFRESH_HZ, DEFAULT_REFRESH_HZ));
        xrUseTimestamps = p.getBoolean(KEY_XR_USE_TIMESTAMPS, false);
        xrLayerShape = LayerShape.parse(p.getString(KEY_XR_LAYER_SHAPE, LayerShape.QUAD.prefValue()));
        xrPerfSustainedHigh = p.getBoolean(KEY_XR_PERF_SUSTAINED_HIGH, true);
        xrFovDeg = clamp(p.getFloat(KEY_XR_FOV_DEG, DEFAULT_FOV_DEG), MIN_FOV_DEG, MAX_FOV_DEG, DEFAULT_FOV_DEG);
        xrFlipVertical = p.getBoolean(KEY_XR_FLIP_VERTICAL, true);
    }

    public static LatencyExperiments from(PrefSource source) {
        return new LatencyExperiments(source);
    }

    public static LatencyExperiments load(Context context) {
        final SharedPreferences sp = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        return from(new PrefSource() {
            public boolean getBoolean(String k, boolean d) { return sp.getBoolean(k, d); }
            public int getInt(String k, int d) { return sp.getInt(k, d); }
            public float getFloat(String k, float d) { return sp.getFloat(k, d); }
            public String getString(String k, String d) { return sp.getString(k, d); }
        });
    }

    static int validRefresh(int hz) {
        for (int supported : SUPPORTED_REFRESH_HZ) {
            if (supported == hz) return hz;
        }
        return DEFAULT_REFRESH_HZ;
    }

    static float clamp(float value, float lo, float hi, float def) {
        if (Float.isNaN(value)) return def;
        return Math.max(lo, Math.min(hi, value));
    }

    /** Compact description of the active levers, for the stats panel and measurement logs. */
    public String summary() {
        StringBuilder dec = new StringBuilder();
        if (lowLatencyDecoder) dec.append("LL ");
        if (decPictureOrder) dec.append("PO ");
        if (decOperatingRate) dec.append("OR ");
        if (decPreferLowLatencyComponent) dec.append("LLC ");
        if (auAggregation) dec.append("AU ");
        String decoder = dec.length() == 0 ? "stock" : dec.toString().trim();
        StringBuilder xr = new StringBuilder();
        xr.append(xrRefreshHz).append("Hz ").append(xrLayerShape.prefValue());
        if (xrUseTimestamps) xr.append(" TS");
        if (xrPerfSustainedHigh) xr.append(" perf");
        if (xrFlipVertical) xr.append(" flip");
        return decoder + " | " + xr;
    }
}
```

- [ ] **Step 5: run the tests — expect PASS**

Run: `./gradlew --no-daemon :app:videonative:testDebugUnitTest` → `BUILD SUCCESSFUL`, 6 tests passed.

- [ ] **Step 6: point VideoActivity at the SSoT**

In `VideoActivity.java` replace the body of `getLowLatencySetting` with
`return LatencyExperiments.load(context).lowLatencyDecoder;` and in `setupVideoSubMenu` replace
`getSharedPreferences("general", MODE_PRIVATE).edit().putBoolean("low_latency_decoder", enabled).commit();` with
`getSharedPreferences(LatencyExperiments.PREFS_NAME, MODE_PRIVATE).edit().putBoolean(LatencyExperiments.KEY_LOW_LATENCY_DECODER, enabled).commit();`
and add `import com.openipc.videonative.LatencyExperiments;`.

- [ ] **Step 7: build + commit**

Run: `./gradlew --no-daemon assembleDebug` → `BUILD SUCCESSFUL`.
```bash
git add gradle/libs.versions.toml app/videonative/build.gradle app/videonative/src/main/java/com/openipc/videonative/LatencyExperiments.java app/videonative/src/test/java/com/openipc/videonative/LatencyExperimentsTest.java app/src/main/java/com/openipc/pixelpilot/VideoActivity.java
git commit -m "feat(videonative): LatencyExperiments as single source of truth for latency levers"
```

---

### Task 2: RTP marker propagation + `AccessUnitAssembler`

**Files:**
- Create: `app/videonative/src/main/cpp/AccessUnitAssembler.h`
- Create: `app/videonative/src/main/cpp/tests/AccessUnitAssembler_test.cpp`
- Modify: `app/videonative/src/main/cpp/tests/CMakeLists.txt` (add test target)
- Modify: `app/videonative/src/main/cpp/NALU/NALU.hpp` (ctor param + member + NALUBuffer copy)
- Modify: `app/videonative/src/main/cpp/parser/ParseRTP.h`, `parser/ParseRTP.cpp` (marker into callback)
- Modify: `app/videonative/src/main/cpp/parser/H26XParser.h`, `parser/H26XParser.cpp` (4-arg callback)

**Interfaces:**
- Produces: `NALU::endOfAccessUnit` (bool); `au::startCodeSize`, `au::nalType`, `au::isFirstSliceOfPicture`, `au::classify(data,size,h265,endOfAu,time) -> NaluInfo`; `AccessUnitAssembler{push(const NaluInfo&, const Emit&), flush(const Emit&), reset(), pendingBytes()}`; `Emit = void(const uint8_t*, size_t, time_point firstNaluTime, bool isConfig)`.

- [ ] **Step 1: failing host test** — `tests/AccessUnitAssembler_test.cpp`

```cpp
#include "AccessUnitAssembler.h"
#include <gtest/gtest.h>
#include <vector>

namespace {
using Clock = std::chrono::steady_clock;
using Bytes = std::vector<uint8_t>;

Bytes h264(uint8_t type, bool firstSlice)
{
    // 4-byte start code, NAL header (nri=3), then one payload byte whose MSB is the
    // ue(v) of first_mb_in_slice (1 == value 0 == first slice)
    return {0, 0, 0, 1, static_cast<uint8_t>(0x60 | type), static_cast<uint8_t>(firstSlice ? 0x88 : 0x40), 0x11};
}

Bytes h265(uint8_t type, bool firstSlice)
{
    return {0, 0, 0, 1, static_cast<uint8_t>(type << 1), 0x01, static_cast<uint8_t>(firstSlice ? 0x80 : 0x00), 0x22};
}

struct Out
{
    Bytes              data;
    Clock::time_point  t;
    bool               cfg;
};

struct Fixture : ::testing::Test
{
    AccessUnitAssembler asmb;
    std::vector<Out>    out;
    AccessUnitAssembler::Emit emit = [this](const uint8_t* d, size_t n, Clock::time_point t, bool cfg)
    { out.push_back({Bytes(d, d + n), t, cfg}); };

    void push(const Bytes& b, bool h265Stream, bool marker, Clock::time_point t = Clock::time_point{})
    {
        asmb.push(au::classify(b.data(), b.size(), h265Stream, marker, t), emit);
    }
};

Bytes cat(std::initializer_list<Bytes> parts)
{
    Bytes r;
    for (const auto& p : parts) r.insert(r.end(), p.begin(), p.end());
    return r;
}
}  // namespace

TEST(AuHelpers, StartCodeSize)
{
    const uint8_t four[] = {0, 0, 0, 1, 0x65};
    const uint8_t three[] = {0, 0, 1, 0x65};
    const uint8_t none[] = {1, 2, 3, 4};
    EXPECT_EQ(4u, au::startCodeSize(four, sizeof(four)));
    EXPECT_EQ(3u, au::startCodeSize(three, sizeof(three)));
    EXPECT_EQ(0u, au::startCodeSize(none, sizeof(none)));
}

TEST(AuHelpers, FirstSliceBits)
{
    auto a = h264(1, true), b = h264(1, false), c = h265(1, true), d = h265(1, false);
    EXPECT_TRUE(au::isFirstSliceOfPicture(a.data(), a.size(), false));
    EXPECT_FALSE(au::isFirstSliceOfPicture(b.data(), b.size(), false));
    EXPECT_TRUE(au::isFirstSliceOfPicture(c.data(), c.size(), true));
    EXPECT_FALSE(au::isFirstSliceOfPicture(d.data(), d.size(), true));
}

TEST(AuHelpers, Classify)
{
    auto sps = h264(7, false), aud = h264(9, false), idr = h264(5, true);
    auto i = au::classify(sps.data(), sps.size(), false, false, {});
    EXPECT_TRUE(i.isConfig);
    EXPECT_FALSE(i.isVcl);
    EXPECT_TRUE(au::classify(aud.data(), aud.size(), false, false, {}).isAud);
    auto v = au::classify(idr.data(), idr.size(), false, true, {});
    EXPECT_TRUE(v.isVcl);
    EXPECT_TRUE(v.isFirstSlice);
    EXPECT_TRUE(v.endOfAu);
    auto vps = h265(32, false), aud5 = h265(35, false), trail = h265(1, true);
    EXPECT_TRUE(au::classify(vps.data(), vps.size(), true, false, {}).isConfig);
    EXPECT_TRUE(au::classify(aud5.data(), aud5.size(), true, false, {}).isAud);
    EXPECT_TRUE(au::classify(trail.data(), trail.size(), true, false, {}).isVcl);
}

TEST_F(Fixture, MarkerClosesAccessUnit)
{
    auto sei = h264(6, false), slice = h264(1, true);
    push(sei, false, false);
    EXPECT_TRUE(out.empty());
    push(slice, false, true);
    ASSERT_EQ(1u, out.size());
    EXPECT_EQ(cat({sei, slice}), out[0].data);
    EXPECT_FALSE(out[0].cfg);
    EXPECT_EQ(0u, asmb.pendingBytes());
}

TEST_F(Fixture, MultiSliceJoinedUntilMarker)
{
    auto s1 = h265(1, true), s2 = h265(1, false);
    push(s1, true, false);
    push(s2, true, true);
    ASSERT_EQ(1u, out.size());
    EXPECT_EQ(cat({s1, s2}), out[0].data);
}

TEST_F(Fixture, ConfigNalusPassAloneAsConfig)
{
    auto sps = h264(7, false), pps = h264(8, false), idr = h264(5, true);
    push(sps, false, false);
    push(pps, false, false);
    push(idr, false, true);
    ASSERT_EQ(3u, out.size());
    EXPECT_TRUE(out[0].cfg);
    EXPECT_TRUE(out[1].cfg);
    EXPECT_FALSE(out[2].cfg);
    EXPECT_EQ(idr, out[2].data);
}

TEST_F(Fixture, LostMarkerSplitsOnNextFirstSlice)
{
    auto a = h264(1, true), b = h264(1, true);
    push(a, false, false);  // its marker packet was lost
    push(b, false, true);
    ASSERT_EQ(2u, out.size());
    EXPECT_EQ(a, out[0].data);
    EXPECT_EQ(b, out[1].data);
}

TEST_F(Fixture, AudStartsNewAccessUnit)
{
    auto a = h264(1, true), aud = h264(9, false), b = h264(1, true);
    push(a, false, false);
    push(aud, false, false);
    push(b, false, true);
    ASSERT_EQ(2u, out.size());
    EXPECT_EQ(a, out[0].data);
    EXPECT_EQ(cat({aud, b}), out[1].data);
}

TEST_F(Fixture, OversizeNaluPassesThroughAlone)
{
    AccessUnitAssembler small(8);
    std::vector<Out> o;
    AccessUnitAssembler::Emit e = [&o](const uint8_t* d, size_t n, Clock::time_point t, bool c)
    { o.push_back({Bytes(d, d + n), t, c}); };
    auto big = h265(1, true);  // 8 bytes, not larger than 8
    Bytes huge = big;
    huge.push_back(0x33);      // 9 bytes > 8
    small.push(au::classify(huge.data(), huge.size(), true, false, {}), e);
    ASSERT_EQ(1u, o.size());
    EXPECT_EQ(huge, o[0].data);
    EXPECT_EQ(0u, small.pendingBytes());
}

TEST_F(Fixture, EmitCarriesFirstNaluTime)
{
    const auto t1 = Clock::time_point{} + std::chrono::milliseconds(5);
    const auto t2 = Clock::time_point{} + std::chrono::milliseconds(9);
    push(h265(39, false), true, false, t1);  // SEI prefix
    push(h265(1, true), true, true, t2);
    ASSERT_EQ(1u, out.size());
    EXPECT_EQ(t1, out[0].t);
}

TEST_F(Fixture, FlushEmitsPendingAndResets)
{
    auto a = h264(1, true);
    push(a, false, false);
    asmb.flush(emit);
    ASSERT_EQ(1u, out.size());
    asmb.flush(emit);
    EXPECT_EQ(1u, out.size());
}
```

Add to `tests/CMakeLists.txt` after the existing `gtest_discover_tests(queue_test)`:

```cmake
add_executable(au_test AccessUnitAssembler_test.cpp)
target_include_directories(au_test PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/../)
target_link_libraries(au_test GTest::gtest_main)
gtest_discover_tests(au_test)
```

- [ ] **Step 2: run — expect compile failure** (WSL command from Global Constraints) → `AccessUnitAssembler.h: No such file`.

- [ ] **Step 3: implement `AccessUnitAssembler.h`**

```cpp
#ifndef PIXELPILOT_ACCESSUNITASSEMBLER_H
#define PIXELPILOT_ACCESSUNITASSEMBLER_H

#include <chrono>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <vector>

// What the assembler needs to know about one Annex-B NALU (start code included).
struct NaluInfo
{
    const uint8_t*                        data         = nullptr;
    size_t                                size         = 0;
    bool                                  isVcl        = false;
    bool                                  isConfig     = false;
    bool                                  isAud        = false;
    bool                                  isFirstSlice = false;
    bool                                  endOfAu      = false;  // RTP marker of the packet that completed it
    std::chrono::steady_clock::time_point creationTime{};
};

// Pure bit-level helpers, no allocation, host-testable.
namespace au
{
inline size_t startCodeSize(const uint8_t* d, size_t n)
{
    if (n >= 4 && d[0] == 0 && d[1] == 0 && d[2] == 0 && d[3] == 1) return 4;
    if (n >= 3 && d[0] == 0 && d[1] == 0 && d[2] == 1) return 3;
    return 0;
}

inline int nalType(const uint8_t* d, size_t n, bool h265)
{
    const size_t sc = startCodeSize(d, n);
    if (sc == 0 || n <= sc) return -1;
    return h265 ? (d[sc] & 0x7E) >> 1 : d[sc] & 0x1F;
}

// First slice of a new picture: H.264 first_mb_in_slice == 0 (ue(v) coded as a single '1' bit),
// H.265 first_slice_segment_in_pic_flag. Both are the MSB of the first byte after the NAL header.
inline bool isFirstSliceOfPicture(const uint8_t* d, size_t n, bool h265)
{
    const size_t sc  = startCodeSize(d, n);
    const size_t hdr = h265 ? 2 : 1;
    if (sc == 0 || n <= sc + hdr) return false;
    return (d[sc + hdr] & 0x80) != 0;
}

inline NaluInfo classify(
    const uint8_t* d, size_t n, bool h265, bool endOfAu, std::chrono::steady_clock::time_point t)
{
    NaluInfo i;
    i.data         = d;
    i.size         = n;
    i.endOfAu      = endOfAu;
    i.creationTime = t;
    const int type = nalType(d, n, h265);
    if (h265)
    {
        i.isVcl    = type >= 0 && type <= 31;
        i.isConfig = type == 32 || type == 33 || type == 34;  // VPS, SPS, PPS
        i.isAud    = type == 35;
    }
    else
    {
        i.isVcl    = type >= 1 && type <= 5;
        i.isConfig = type == 7 || type == 8;  // SPS, PPS
        i.isAud    = type == 9;
    }
    i.isFirstSlice = i.isVcl && isFirstSliceOfPicture(d, n, h265);
    return i;
}
}  // namespace au

// Joins the NALUs of one access unit so the decoder receives a whole picture per input buffer
// and never has to wait for the next picture to learn that this one is complete.
// The AU is closed by the RTP marker on its last VCL NALU. If that packet was lost, the AU is
// closed when the next picture visibly starts (AUD, parameter set, or a first slice while a slice
// is already pending), so a lost marker costs one late frame instead of merging two pictures.
class AccessUnitAssembler
{
  public:
    using Emit = std::function<void(
        const uint8_t* data, size_t size, std::chrono::steady_clock::time_point firstNaluTime, bool isConfig)>;

    explicit AccessUnitAssembler(size_t maxBytes = 1024 * 1024) : mMaxBytes(maxBytes) { mBuf.reserve(256 * 1024); }

    void push(const NaluInfo& n, const Emit& emit)
    {
        if (n.isConfig)
        {
            flush(emit);
            emit(n.data, n.size, n.creationTime, true);
            return;
        }
        if (n.isAud || (n.isVcl && n.isFirstSlice && mHasVcl))
        {
            flush(emit);
        }
        if (mBuf.size() + n.size > mMaxBytes)
        {
            flush(emit);
        }
        if (n.size > mMaxBytes)
        {
            emit(n.data, n.size, n.creationTime, false);
            return;
        }
        if (mBuf.empty())
        {
            mFirstTime = n.creationTime;
        }
        mBuf.insert(mBuf.end(), n.data, n.data + n.size);
        mHasVcl = mHasVcl || n.isVcl;
        if (n.isVcl && n.endOfAu)
        {
            flush(emit);
        }
    }

    void flush(const Emit& emit)
    {
        if (!mBuf.empty())
        {
            emit(mBuf.data(), mBuf.size(), mFirstTime, false);
        }
        reset();
    }

    void reset()
    {
        mBuf.clear();
        mHasVcl = false;
    }

    size_t pendingBytes() const { return mBuf.size(); }

  private:
    const size_t                          mMaxBytes;
    std::vector<uint8_t>                  mBuf;
    bool                                  mHasVcl = false;
    std::chrono::steady_clock::time_point mFirstTime{};
};

#endif  // PIXELPILOT_ACCESSUNITASSEMBLER_H
```

- [ ] **Step 4: run host tests — expect PASS** (queue_test + au_test).

- [ ] **Step 5: carry the RTP marker into `NALU`**

`NALU/NALU.hpp` — constructor gains a last defaulted param and a member:
```cpp
    NALU(
        const uint8_t*                              data1,
        size_t                                      data_len1,
        const bool                                  IS_H265_PACKET1  = false,
        const std::chrono::steady_clock::time_point creationTime     = std::chrono::steady_clock::now(),
        const bool                                  endOfAccessUnit1 = false)
        : m_data(data1),
          m_data_len(data_len1),
          IS_H265_PACKET(IS_H265_PACKET1),
          creationTime{creationTime},
          endOfAccessUnit(endOfAccessUnit1)
```
and after `const std::chrono::steady_clock::time_point creationTime;` add
```cpp
    // RTP marker bit of the packet that completed this NALU: set on the last NALU of an access unit.
    const bool endOfAccessUnit;
```
In `NALUBuffer(const NALU& nalu)` pass `nalu.endOfAccessUnit` as the 5th argument.

`parser/ParseRTP.h` — callback type:
```cpp
typedef std::function<void(
    const std::chrono::steady_clock::time_point creation_time,
    const uint8_t*                              nalu_data,
    const int                                   nalu_data_size,
    const bool                                  end_of_access_unit)>
    RTP_FRAME_DATA_CALLBACK;
```
and a private member next to `m_total_n_fragments_for_current_fu`: `bool m_current_packet_marker = false;`.

`parser/ParseRTP.cpp` — in both `parseRTPH264toNALU` and `parseRTPH265toNALU`, directly after the
`if (!validateRTPPacket(rtpPacket.header)) { return; }` block add
`m_current_packet_marker = rtpPacket.header.marker;`; in `forwardNALU` change the call to
`m_cb(timePointStartOfReceivingNALU, p, m_nalu_data_length, m_current_packet_marker);`; in `reset()` add
`m_current_packet_marker = false;`. (STAP/aggregation packets give every contained NALU the packet's marker;
only VCL NALUs close an AU, and aggregation packets carry parameter sets in practice.)

`parser/H26XParser.h/.cpp` — `onNewNaluDataExtracted` gains `const bool end_of_access_unit`, the
`std::bind` gets `std::placeholders::_4`, and the NALU is built as
`NALU nalu(nalu_data, nalu_data_size, IS_H265, creation_time, end_of_access_unit);`.

- [ ] **Step 6: build + host tests + commit**

Run the WSL gtest command (both pass) and `./gradlew --no-daemon assembleDebug` (SUCCESS).
```bash
git add app/videonative/src/main/cpp/AccessUnitAssembler.h app/videonative/src/main/cpp/tests/AccessUnitAssembler_test.cpp app/videonative/src/main/cpp/tests/CMakeLists.txt app/videonative/src/main/cpp/NALU/NALU.hpp app/videonative/src/main/cpp/parser/ParseRTP.h app/videonative/src/main/cpp/parser/ParseRTP.cpp app/videonative/src/main/cpp/parser/H26XParser.h app/videonative/src/main/cpp/parser/H26XParser.cpp
git commit -m "feat(videonative): carry RTP marker per NALU and add AccessUnitAssembler"
```

---

### Task 3: Decoder levers (keys, low-latency component, AU aggregation, configure retry)

**Files:**
- Create: `app/videonative/src/main/cpp/DecoderLevers.h`
- Create: `app/videonative/src/main/cpp/tests/DecoderLevers_test.cpp`
- Modify: `app/videonative/src/main/cpp/tests/CMakeLists.txt`
- Modify: `app/videonative/src/main/cpp/helper/AndroidMediaFormatHelper.h` (replace `writeAndroidPerformanceParams`)
- Modify: `app/videonative/src/main/cpp/VideoDecoder.h`, `VideoDecoder.cpp`
- Modify: `app/videonative/src/main/cpp/VideoPlayer.h`, `VideoPlayer.cpp` (JNI)
- Modify: `app/videonative/src/main/java/com/openipc/videonative/VideoPlayer.java`
- Modify: `app/src/main/java/com/openipc/pixelpilot/VideoActivity.java` (`initializeVideoPlayers`, `setupVideoSubMenu`)

**Interfaces:**
- Consumes: `LatencyExperiments` fields (Task 1), `AccessUnitAssembler`, `au::classify`, `NALU::endOfAccessUnit` (Task 2).
- Produces: `DecoderLevers{lowLatency, pictureOrder, operatingRate, preferLowLatencyComponent, auAggregation; onlyBase(); hasExtras()}`, `decoderFormatKeys(const DecoderLevers&) -> std::vector<FormatKey>`, `lowLatencyComponentName(bool h265)`, `leversSummary(const DecoderLevers&)`; Java `VideoPlayer.setDecoderLevers(LatencyExperiments)`, `VideoPlayer.getDecoderSummary() -> String`. Removes `VideoPlayer.setLowLatency` / `nativeSetLowLatency` (one path only).

- [ ] **Step 1: failing host test** — `tests/DecoderLevers_test.cpp`

```cpp
#include "DecoderLevers.h"
#include <gtest/gtest.h>
#include <string>

namespace {
std::vector<std::pair<std::string, int32_t>> flat(const DecoderLevers& l)
{
    std::vector<std::pair<std::string, int32_t>> r;
    for (const auto& k : decoderFormatKeys(l)) r.emplace_back(k.key, k.value);
    return r;
}
}  // namespace

TEST(DecoderLevers, DefaultIsExactlyTheUpstreamKeySet)
{
    // Pins the pre-existing writeAndroidPerformanceParams() behaviour (PixelPilot #113).
    const std::vector<std::pair<std::string, int32_t>> expected = {
        {"low-latency", 1},
        {"vendor.low-latency.enable", 1},
        {"vendor.qti-ext-dec-low-latency.enable", 1},
        {"vendor.hisi-ext-low-latency-video-dec.video-scene-for-low-latency-req", 1},
        {"vendor.rtc-ext-dec-low-latency.enable", 1},
        {"priority", 0},
    };
    EXPECT_EQ(expected, flat(DecoderLevers{}));
}

TEST(DecoderLevers, AllOffIsEmpty)
{
    DecoderLevers l;
    l.lowLatency = false;
    EXPECT_TRUE(decoderFormatKeys(l).empty());
}

TEST(DecoderLevers, PictureOrderAddsQtiKey)
{
    DecoderLevers l;
    l.pictureOrder = true;
    auto f = flat(l);
    EXPECT_EQ((std::pair<std::string, int32_t>{"vendor.qti-ext-dec-picture-order.enable", 1}), f.back());
}

TEST(DecoderLevers, OperatingRateReplacesPriority)
{
    DecoderLevers l;
    l.operatingRate = true;
    auto f = flat(l);
    for (const auto& kv : f) EXPECT_NE("priority", kv.first);
    EXPECT_EQ((std::pair<std::string, int32_t>{"operating-rate", 32767}), f.back());
}

TEST(DecoderLevers, OnlyBaseKeepsLowLatencyDropsExtras)
{
    DecoderLevers l;
    l.pictureOrder = l.operatingRate = l.preferLowLatencyComponent = l.auAggregation = true;
    EXPECT_TRUE(l.hasExtras());
    DecoderLevers b = l.onlyBase();
    EXPECT_TRUE(b.lowLatency);
    EXPECT_FALSE(b.hasExtras());
    EXPECT_TRUE(b.auAggregation);  // not a codec key, cannot make configure() fail
}

TEST(DecoderLevers, ComponentNamesAndSummary)
{
    EXPECT_STREQ("c2.qti.hevc.decoder.low_latency", lowLatencyComponentName(true));
    EXPECT_STREQ("c2.qti.avc.decoder.low_latency", lowLatencyComponentName(false));
    DecoderLevers l;
    EXPECT_EQ("LL", leversSummary(l));
    l.pictureOrder = l.auAggregation = true;
    EXPECT_EQ("LL PO AU", leversSummary(l));
    l.lowLatency = l.pictureOrder = l.auAggregation = false;
    EXPECT_EQ("stock", leversSummary(l));
}
```

Add to `tests/CMakeLists.txt`:
```cmake
add_executable(levers_test DecoderLevers_test.cpp)
target_include_directories(levers_test PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/../)
target_link_libraries(levers_test GTest::gtest_main)
gtest_discover_tests(levers_test)
```

- [ ] **Step 2: run — expect compile failure** (`DecoderLevers.h: No such file`).

- [ ] **Step 3: implement `DecoderLevers.h`**

```cpp
#ifndef PIXELPILOT_DECODERLEVERS_H
#define PIXELPILOT_DECODERLEVERS_H

#include <cstdint>
#include <string>
#include <vector>

// Decoder-side latency levers. Mirrors LatencyExperiments (Java), which owns the pref keys/defaults.
struct DecoderLevers
{
    bool lowLatency                = true;
    bool pictureOrder              = false;
    bool operatingRate             = false;
    bool preferLowLatencyComponent = false;
    bool auAggregation             = false;

    // Codec-facing extras are the ones a decoder can reject in configure().
    bool hasExtras() const { return pictureOrder || operatingRate || preferLowLatencyComponent; }

    DecoderLevers onlyBase() const
    {
        DecoderLevers b;
        b.lowLatency    = lowLatency;
        b.auAggregation = auAggregation;
        return b;
    }
};

struct FormatKey
{
    const char* key;
    int32_t     value;
};

// The AMediaFormat keys a set of levers stands for. Free of NDK types so the mapping is host-testable.
inline std::vector<FormatKey> decoderFormatKeys(const DecoderLevers& l)
{
    std::vector<FormatKey> k;
    if (l.lowLatency)
    {
        // AMEDIAFORMAT_KEY_LOW_LATENCY (API 30+): output a frame as soon as it is decoded.
        k.push_back({"low-latency", 1});
        // Vendor equivalents for codecs that ignore the AOSP key (Qualcomm covers the XR2 headsets).
        k.push_back({"vendor.low-latency.enable", 1});
        k.push_back({"vendor.qti-ext-dec-low-latency.enable", 1});
        k.push_back({"vendor.hisi-ext-low-latency-video-dec.video-scene-for-low-latency-req", 1});
        k.push_back({"vendor.rtc-ext-dec-low-latency.enable", 1});
        // Realtime priority. Not combined with a maximum operating rate: Qualcomm decoders can fail when
        // they cannot honour both (moonlight-android MediaCodecHelper.decoderSupportsMaxOperatingRate).
        if (!l.operatingRate) k.push_back({"priority", 0});
    }
    // Output in decode order: OpenIPC streams have no B-frames, so this removes any reorder hold.
    if (l.pictureOrder) k.push_back({"vendor.qti-ext-dec-picture-order.enable", 1});
    // Keep the codec clocked up; Short.MAX_VALUE as moonlight-android uses on Qualcomm.
    if (l.operatingRate) k.push_back({"operating-rate", 32767});
    return k;
}

// Qualcomm ships separate low-latency Codec2 components on some SoCs (moonlight-android MediaCodecHelper).
inline const char* lowLatencyComponentName(bool h265)
{
    return h265 ? "c2.qti.hevc.decoder.low_latency" : "c2.qti.avc.decoder.low_latency";
}

inline std::string leversSummary(const DecoderLevers& l)
{
    std::string s;
    auto add = [&s](const char* t)
    {
        if (!s.empty()) s += ' ';
        s += t;
    };
    if (l.lowLatency) add("LL");
    if (l.pictureOrder) add("PO");
    if (l.operatingRate) add("OR");
    if (l.preferLowLatencyComponent) add("LLC");
    if (l.auAggregation) add("AU");
    return s.empty() ? "stock" : s;
}

#endif  // PIXELPILOT_DECODERLEVERS_H
```

- [ ] **Step 4: run host tests — expect PASS** (queue_test, au_test, levers_test).

- [ ] **Step 5: `AndroidMediaFormatHelper.h`** — delete `writeAndroidPerformanceParams` and add (with `#include "../DecoderLevers.h"`):

```cpp
// Writes the keys a set of levers stands for. Unknown keys are ignored by MediaCodec.
static void applyDecoderLevers(AMediaFormat* format, const DecoderLevers& levers)
{
    for (const auto& k : decoderFormatKeys(levers))
    {
        AMediaFormat_setInt32(format, k.key, k.value);
    }
}
```

- [ ] **Step 6: `VideoDecoder.h`** — replace `setLowLatency`/`mLowLatency` with levers and add AU state:

```cpp
#include <mutex>
#include <string>
#include "AccessUnitAssembler.h"
#include "DecoderLevers.h"
...
    // Applied the next time the decoder is configured, not to a running decoder.
    void setDecoderLevers(const DecoderLevers& levers)
    {
        std::lock_guard<std::mutex> lock(mLeversMutex);
        mLevers = levers;
    }

    // Codec name + levers that the running decoder actually accepted.
    std::string getDecoderSummary()
    {
        std::lock_guard<std::mutex> lock(mLeversMutex);
        return mAppliedSummary;
    }
  private:
    // Creates, configures (not starts) the codec for idx with the given levers. False on failure.
    bool tryConfigure(int idx, const DecoderLevers& levers);
    // Wait for an input buffer and queue one buffer (a NALU or a whole access unit)
    void feedDecoder(const uint8_t* data, size_t size, std::chrono::steady_clock::time_point creationTime,
                     bool codecConfig, int idx);
    void feedBoth(const uint8_t* data, size_t size, std::chrono::steady_clock::time_point creationTime,
                  bool codecConfig);
    std::mutex          mLeversMutex;
    DecoderLevers       mLevers{};
    std::string         mAppliedSummary = "not configured";
    // Snapshot taken at configure time; only the NALU thread reads it afterwards.
    bool                mAuAggregationActive = false;
    AccessUnitAssembler mAssembler;
```
Remove the old `feedDecoder(const NALU&, int)` declaration and `mLowLatency`.

- [ ] **Step 7: `VideoDecoder.cpp`**

In `setOutputSurface` null-branch next to `mKeyFrameFinder.reset();` add `mAssembler.reset();`.

Replace the body of `interpretNALU`'s configured branch (`feedDecoder(nalu, 0); feedDecoder(nalu, 1);`) with:
```cpp
        if (mAuAggregationActive)
        {
            mAssembler.push(
                au::classify(nalu.getData(), nalu.getSize(), IS_H265, nalu.endOfAccessUnit, nalu.creationTime),
                [this](const uint8_t* d, size_t n, std::chrono::steady_clock::time_point t, bool cfg)
                { feedBoth(d, n, t, IS_H265 && cfg); });
        }
        else
        {
            feedBoth(nalu.getData(), nalu.getSize(), nalu.creationTime,
                     IS_H265 && (nalu.isSPS() || nalu.isPPS() || nalu.isVPS()));
        }
```
Replace `configureStartDecoder` with:
```cpp
void VideoDecoder::configureStartDecoder(int idx)
{
    if (decoder.window[idx] == nullptr) return;
    DecoderLevers wanted;
    {
        std::lock_guard<std::mutex> lock(mLeversMutex);
        wanted = mLevers;
    }
    if (!tryConfigure(idx, wanted) && wanted.hasExtras())
    {
        MLOGE << "Decoder rejected levers [" << leversSummary(wanted) << "], retrying without the extras";
        tryConfigure(idx, wanted.onlyBase());
    }
    if (decoder.codec[idx] == nullptr)
    {
        MLOGD << "Cannot configure decoder";
        return;
    }
    mAuAggregationActive = wanted.auAggregation;
    mAssembler.reset();
    AMediaCodec_start(decoder.codec[idx]);
    mCheckOutputThread[idx] = std::make_unique<std::thread>(&VideoDecoder::checkOutputLoop, this, idx);
    NDKThreadHelper::setName(mCheckOutputThread[idx]->native_handle(), "LLDCheckOutput");
    decoder.configured[idx] = true;
}

bool VideoDecoder::tryConfigure(int idx, const DecoderLevers& levers)
{
    const std::string MIME = IS_H265 ? "video/hevc" : "video/avc";
    std::string       name = "default " + MIME;
    decoder.codec[idx]     = nullptr;
    if (levers.preferLowLatencyComponent)
    {
        decoder.codec[idx] = AMediaCodec_createCodecByName(lowLatencyComponentName(IS_H265));
        if (decoder.codec[idx] != nullptr) name = lowLatencyComponentName(IS_H265);
    }
    if (decoder.codec[idx] == nullptr)
    {
        decoder.codec[idx] = AMediaCodec_createDecoderByType(MIME.c_str());
    }
    if (decoder.codec[idx] == nullptr) return false;

    AMediaFormat* format = AMediaFormat_new();
    AMediaFormat_setString(format, AMEDIAFORMAT_KEY_MIME, MIME.c_str());
    if (IS_H265)
    {
        h265_configureAMediaFormat(mKeyFrameFinder, format);
    }
    else
    {
        h264_configureAMediaFormat(mKeyFrameFinder, format);
    }
    applyDecoderLevers(format, levers);
    MLOGD << "Configuring decoder " << name << ": " << AMediaFormat_toString(format);
    const auto status = AMediaCodec_configure(decoder.codec[idx], format, decoder.window[idx], nullptr, 0);
    AMediaFormat_delete(format);
    if (status != AMEDIA_OK)
    {
        MLOGE << "AMediaCodec_configure failed: " << (int) status;
        AMediaCodec_delete(decoder.codec[idx]);
        decoder.codec[idx] = nullptr;
        return false;
    }
    std::lock_guard<std::mutex> lock(mLeversMutex);
    mAppliedSummary = name + " | " + leversSummary(levers);
    return true;
}

void VideoDecoder::feedBoth(
    const uint8_t* data, size_t size, std::chrono::steady_clock::time_point creationTime, bool codecConfig)
{
    feedDecoder(data, size, creationTime, codecConfig, 0);
    feedDecoder(data, size, creationTime, codecConfig, 1);
}
```
Change `feedDecoder` to the new signature: `if (!decoder.codec[idx]) return;`, `const auto deltaParsing = now - creationTime;`, size check `if (size > inputBufferSize)`, `const int flag = codecConfig ? AMEDIACODEC_BUFFER_FLAG_CODEC_CONFIG : 0;`, `std::memcpy(buf, data, size);`, queue `size`. Everything else in the loop stays.

- [ ] **Step 8: JNI + Java**

`VideoPlayer.h`: replace `void setLowLatency(bool enabled) { videoDecoder.setLowLatency(enabled); }` with
```cpp
    void setDecoderLevers(const DecoderLevers& levers) { videoDecoder.setDecoderLevers(levers); }
    std::string getDecoderSummary() { return videoDecoder.getDecoderSummary(); }
```
`VideoPlayer.cpp`: replace the `nativeSetLowLatency` JNI method with
```cpp
    JNI_METHOD(void, nativeSetDecoderLevers)
    (JNIEnv* env, jclass jclass1, jlong nativeInstance, jboolean lowLatency, jboolean pictureOrder,
     jboolean operatingRate, jboolean preferLowLatencyComponent, jboolean auAggregation)
    {
        VideoPlayer* p = native(nativeInstance);
        if (p)
        {
            DecoderLevers l;
            l.lowLatency                = lowLatency;
            l.pictureOrder              = pictureOrder;
            l.operatingRate             = operatingRate;
            l.preferLowLatencyComponent = preferLowLatencyComponent;
            l.auAggregation             = auAggregation;
            p->setDecoderLevers(l);
        }
    }

    JNI_METHOD(jstring, nativeGetDecoderSummary)
    (JNIEnv* env, jclass jclass1, jlong nativeInstance)
    {
        VideoPlayer* p = native(nativeInstance);
        return env->NewStringUTF(p ? p->getDecoderSummary().c_str() : "");
    }
```
`VideoPlayer.java`: replace `nativeSetLowLatency` + `setLowLatency` with
```java
    public static native void nativeSetDecoderLevers(long nativeInstance, boolean lowLatency, boolean pictureOrder,
                                                     boolean operatingRate, boolean preferLowLatencyComponent,
                                                     boolean auAggregation);

    public static native String nativeGetDecoderSummary(long nativeInstance);

    /** Decoder levers from the single source of truth. Applied when the codec is next configured. */
    public void setDecoderLevers(LatencyExperiments e) {
        nativeSetDecoderLevers(nativeVideoPlayer, e.lowLatencyDecoder, e.decPictureOrder, e.decOperatingRate,
                e.decPreferLowLatencyComponent, e.auAggregation);
    }

    /** Codec name and the levers it accepted, e.g. "default video/hevc | LL PO". */
    public String getDecoderSummary() {
        return nativeGetDecoderSummary(nativeVideoPlayer);
    }
```

`VideoActivity.initializeVideoPlayers`: replace `videoPlayer.setLowLatency(getLowLatencySetting(this));` with
`videoPlayer.setDecoderLevers(LatencyExperiments.load(this));`.

`VideoActivity.setupVideoSubMenu`: after the "Low latency" item add a restart-on-toggle helper and the four levers:
```java
        SubMenu experiments = videoMenu.addSubMenu("Latency experiments");
        LatencyExperiments ex = LatencyExperiments.load(this);
        addRestartingToggle(experiments, "Decoder: decode order (qti)", LatencyExperiments.KEY_DEC_PICTURE_ORDER, ex.decPictureOrder);
        addRestartingToggle(experiments, "Decoder: max operating rate", LatencyExperiments.KEY_DEC_OPERATING_RATE, ex.decOperatingRate);
        addRestartingToggle(experiments, "Decoder: low-latency component", LatencyExperiments.KEY_DEC_PREFER_LOW_LATENCY_COMPONENT, ex.decPreferLowLatencyComponent);
        addRestartingToggle(experiments, "Decoder: whole access units", LatencyExperiments.KEY_AU_AGGREGATION, ex.auAggregation);
```
and the helper (the existing low-latency item uses the same commit + resetApp pattern — see its comment):
```java
    /** A checkable item bound to a boolean lever; decoder levers apply at configure time, so it restarts the app. */
    private void addRestartingToggle(SubMenu menu, String title, String key, boolean current) {
        MenuItem item = menu.add(title);
        item.setCheckable(true);
        item.setChecked(current);
        item.setOnMenuItemClickListener(i -> {
            boolean enabled = !i.isChecked();
            i.setChecked(enabled);
            getSharedPreferences(LatencyExperiments.PREFS_NAME, MODE_PRIVATE).edit().putBoolean(key, enabled).commit();
            resetApp();
            return false;
        });
    }
```

- [ ] **Step 9: build + host tests + commit**

Run the WSL gtest command (3 test binaries pass) and `./gradlew --no-daemon assembleDebug` (SUCCESS).
```bash
git add app/videonative/src/main/cpp/DecoderLevers.h app/videonative/src/main/cpp/tests/DecoderLevers_test.cpp app/videonative/src/main/cpp/tests/CMakeLists.txt app/videonative/src/main/cpp/helper/AndroidMediaFormatHelper.h app/videonative/src/main/cpp/VideoDecoder.h app/videonative/src/main/cpp/VideoDecoder.cpp app/videonative/src/main/cpp/VideoPlayer.h app/videonative/src/main/cpp/VideoPlayer.cpp app/videonative/src/main/java/com/openipc/videonative/VideoPlayer.java app/src/main/java/com/openipc/pixelpilot/VideoActivity.java
git commit -m "feat(videonative): switchable decoder latency levers with configure retry"
```

---

### Task 4: Decouple `WfbLinkManager` from the 2D UI (`LinkStatusListener`) + shared VPN control

**Files:**
- Create: `app/src/main/java/com/openipc/pixelpilot/LinkStatusListener.java`
- Create: `app/src/main/java/com/openipc/pixelpilot/WfbServiceControl.java`
- Modify: `app/src/main/java/com/openipc/pixelpilot/WfbLinkManager.java`
- Modify: `app/src/main/java/com/openipc/pixelpilot/VideoActivity.java` (`initializeWfbNg`, `startVpnService`, `onPause`, `registerReceivers`)

**Interfaces:**
- Produces: `LinkStatusListener{onLinkStatus(String), onUdpFallbackAddress(String)}`; `WfbLinkManager(Context, LinkStatusListener, WfbNgLink)`; `WfbLinkManager.usbIntentFilter()`; `WfbServiceControl.startVpn(Activity) -> boolean started`, `WfbServiceControl.stopVpn(Context)`.

- [ ] **Step 1: create the interface and the helper**

```java
package com.openipc.pixelpilot;

/** Where WfbLinkManager reports link state, so it does not depend on a particular UI. */
public interface LinkStatusListener {
    /** One-line status, e.g. "Starting wfb-ng channel 161 with [0BDA:8812]". */
    void onLinkStatus(String message);

    /** No usable adapter; a stream can still be pushed over wifi to this udp:// address. */
    void onUdpFallbackAddress(String udpUrl);
}
```

```java
package com.openipc.pixelpilot;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.net.VpnService;

/** Starts/stops the wfb-ng VPN service the same way from every activity. */
public final class WfbServiceControl {
    public static final int VPN_REQUEST_CODE = 100;

    private WfbServiceControl() {}

    /**
     * Starts the service if VPN permission is granted; otherwise asks for it (the activity gets
     * onActivityResult with VPN_REQUEST_CODE). Returns true if the service was started now.
     */
    public static boolean startVpn(Activity activity, boolean askIfMissing) {
        Intent consent = VpnService.prepare(activity);
        if (consent != null) {
            if (askIfMissing) activity.startActivityForResult(consent, VPN_REQUEST_CODE);
            return false;
        }
        activity.startService(new Intent(activity, WfbNgVpnService.class));
        return true;
    }

    public static void stopVpn(Context context) {
        Intent intent = new Intent(context, WfbNgVpnService.class);
        intent.setAction("STOP_SERVICE");
        context.startService(intent);
    }
}
```

- [ ] **Step 2: WfbLinkManager** — replace field/ctor param `ActivityVideoBinding binding` with `LinkStatusListener status`, drop the binding and `View` imports, and replace:
  - `binding.tvMessage.setVisibility(View.VISIBLE); binding.tvMessage.setText(X);` → `status.onLinkStatus(X);` (lines 146-147, 197-198, 236-239)
  - `binding.tvMessage.setText("Could not open wifi adapter " + ...)` → `status.onLinkStatus("Could not open wifi adapter " + ...)`
  - `binding.wifiMessage.setText(local); binding.wifiMessage.setVisibility(View.VISIBLE);` → `status.onUdpFallbackAddress(local);`
  Add:
```java
    /** The broadcasts this receiver handles; register it with exactly this filter. */
    public static IntentFilter usbIntentFilter() {
        IntentFilter f = new IntentFilter();
        f.addAction(UsbManager.ACTION_USB_DEVICE_ATTACHED);
        f.addAction(UsbManager.ACTION_USB_DEVICE_DETACHED);
        f.addAction(ACTION_USB_PERMISSION);
        return f;
    }
```
(import `android.content.IntentFilter`).

- [ ] **Step 3: VideoActivity** —
  - add a field
```java
    private final LinkStatusListener linkStatusToUi = new LinkStatusListener() {
        @Override public void onLinkStatus(String message) {
            binding.tvMessage.setVisibility(View.VISIBLE);
            binding.tvMessage.setText(message);
        }
        @Override public void onUdpFallbackAddress(String udpUrl) {
            binding.wifiMessage.setText(udpUrl);
            binding.wifiMessage.setVisibility(View.VISIBLE);
        }
    };
```
  - `initializeWfbNg`: `wfbLinkManager = new WfbLinkManager(this, linkStatusToUi, wfbLink);`
  - `startVpnService()` body → `WfbServiceControl.startVpn(this, true);`
  - `onPause`: replace the three STOP_SERVICE lines with `WfbServiceControl.stopVpn(this);`
  - `registerReceivers`: `IntentFilter usbFilter = WfbLinkManager.usbIntentFilter();` (remove the three addAction lines).
  - the `onActivityResult` branch that starts `WfbNgVpnService` after consent (line ~1455) stays as is.

- [ ] **Step 4: build + commit**

Run: `./gradlew --no-daemon assembleDebug` → SUCCESS; `grep -n "binding" app/src/main/java/com/openipc/pixelpilot/WfbLinkManager.java` → no matches.
```bash
git add app/src/main/java/com/openipc/pixelpilot/LinkStatusListener.java app/src/main/java/com/openipc/pixelpilot/WfbServiceControl.java app/src/main/java/com/openipc/pixelpilot/WfbLinkManager.java app/src/main/java/com/openipc/pixelpilot/VideoActivity.java
git commit -m "refactor: decouple WfbLinkManager from the 2D UI via LinkStatusListener"
```

---

### Task 5: `app/xr` module — OpenXR runtime, layers, JNI, `XrBridge`, `LayerLayout`

**Files:**
- Modify: `settings.gradle` (`include(":app:xr")`), `gradle/libs.versions.toml` (openxr loader)
- Create: `app/xr/build.gradle`, `app/xr/consumer-rules.pro`, `app/xr/src/main/AndroidManifest.xml`
- Create: `app/xr/src/main/cpp/CMakeLists.txt`, `XrIncludes.h`, `EglContext.h/.cpp`, `XrLayers.h/.cpp`, `XrRuntime.h/.cpp`, `xr_jni.cpp`
- Create: `app/xr/src/main/java/com/openipc/xr/XrBridge.java`, `LayerLayout.java`
- Test: `app/xr/src/test/java/com/openipc/xr/LayerLayoutTest.java`

**Interfaces:**
- Produces (Java): `XrBridge(Listener)`, `String start(Activity, int refreshHz, boolean useTimestamps, boolean perfSustainedHigh)` (null = ok, else error), `Surface videoSurface()`, `Surface statsSurface()`, `setLayout(LayerLayout)`, `Info info()`, `stop()`; `XrBridge.Listener.onSessionEvent(XrBridge.SessionEvent)` with `ACTIVE, INACTIVE, EXITING` (called on the XR thread; INACTIVE must return only after the producer stopped writing); `XrBridge.Info{refreshHz, requestedHz, compositorGpuMs, droppedFrames, motionToPhotonMs}` (negative = n/a);
  `LayerLayout.compute(int videoW, int videoH, float fovDeg, float distanceM, boolean cylinder, boolean flip) -> LayerLayout` with public final fields `cylinder, flip, videoWidthM, videoHeightM, videoZ, cylRadius, cylAngleRad, cylAspect, statsWidthM, statsHeightM, statsY, statsZ, imageW, imageH`; constants `STATS_IMAGE_W=512, STATS_IMAGE_H=256, DEFAULT_DISTANCE_M=2f`.

- [ ] **Step 1: failing JVM test** — `LayerLayoutTest.java`

```java
package com.openipc.xr;

import static org.junit.Assert.*;
import org.junit.Test;

public class LayerLayoutTest {
    private static final float EPS = 1e-4f;

    @Test public void quadSizeFromFovAndDistance() {
        LayerLayout l = LayerLayout.compute(1280, 720, 60f, 2f, false, true);
        assertFalse(l.cylinder);
        assertEquals(2.309401f, l.videoWidthM, EPS);          // 2 * 2m * tan(30deg)
        assertEquals(2.309401f * 720f / 1280f, l.videoHeightM, EPS);
        assertEquals(-2f, l.videoZ, EPS);
        assertEquals(1280, l.imageW);
        assertEquals(720, l.imageH);
        assertTrue(l.flip);
    }

    @Test public void cylinderUsesArc() {
        LayerLayout l = LayerLayout.compute(1920, 1080, 90f, 2f, true, false);
        assertTrue(l.cylinder);
        assertEquals(2f, l.cylRadius, EPS);
        assertEquals((float) Math.toRadians(90), l.cylAngleRad, EPS);
        assertEquals(1920f / 1080f, l.cylAspect, EPS);
        assertEquals(2f * (float) Math.toRadians(90) / (1920f / 1080f), l.videoHeightM, EPS);
    }

    @Test public void zeroSizeFallsBackTo16by9() {
        LayerLayout l = LayerLayout.compute(0, 0, 60f, 2f, false, true);
        assertEquals(1280, l.imageW);
        assertEquals(720, l.imageH);
        assertTrue(l.videoHeightM > 0f && !Float.isNaN(l.videoHeightM));
    }

    @Test public void statsPanelSitsBelowVideoWithGap() {
        LayerLayout l = LayerLayout.compute(1280, 720, 60f, 2f, false, true);
        float statsTop = l.statsY + l.statsHeightM / 2f;
        assertTrue(statsTop < -l.videoHeightM / 2f);
        assertEquals(l.statsWidthM / 2f, l.statsHeightM, EPS);   // 512x256 image aspect
        assertEquals(l.videoZ, l.statsZ, EPS);
    }
}
```

- [ ] **Step 2: Gradle wiring**

`settings.gradle`: append `include(":app:xr")`.
`gradle/libs.versions.toml`: `[versions] openxrLoader = "1.1.63"`; `[libraries] openxr-loader = { group = "org.khronos.openxr", name = "openxr_loader_for_android", version.ref = "openxrLoader" }`.
`app/xr/build.gradle`:
```groovy
plugins {
    alias(libs.plugins.androidLibrary)
}

android {
    namespace = "com.openipc.xr"
    compileSdk = 34

    defaultConfig {
        minSdk = 26
        consumerProguardFiles "consumer-rules.pro"
        ndk {
            abiFilters.add("arm64-v8a")
            abiFilters.add("armeabi-v7a")
        }
    }

    buildFeatures {
        prefab = true
    }

    externalNativeBuild {
        cmake {
            path("src/main/cpp/CMakeLists.txt")
            version = "3.22.1"
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    ndkVersion '26.1.10909125'
}

dependencies {
    implementation(libs.openxr.loader)
    testImplementation(libs.junit)
}
```
`app/xr/consumer-rules.pro`:
```
# Called from native code (xr_jni.cpp) by name.
-keep class com.openipc.xr.XrBridge { *; }
```
`app/xr/src/main/AndroidManifest.xml`:
```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <!-- Khronos OpenXR loader: runtime discovery on Android 11+ -->
    <uses-permission android:name="org.khronos.openxr.permission.OPENXR" />
    <uses-permission android:name="org.khronos.openxr.permission.OPENXR_SYSTEM" />
    <queries>
        <provider android:authorities="org.khronos.openxr.runtime_broker;org.khronos.openxr.system_runtime_broker" />
        <intent>
            <action android:name="org.khronos.openxr.OpenXRRuntimeService" />
        </intent>
        <intent>
            <action android:name="org.khronos.openxr.OpenXRApiLayerService" />
        </intent>
    </queries>
    <uses-feature android:name="android.hardware.vr.headtracking" android:required="false" android:version="1" />
</manifest>
```
`app/build.gradle`: `implementation(project(":app:xr"))`.

- [ ] **Step 3: `LayerLayout.java`**

```java
package com.openipc.xr;

/**
 * Pure geometry of the two head-locked layers: the video (quad or cylinder) and the stats panel
 * below it. Angular size comes from the FOV preference; the panel keeps the stats image aspect.
 */
public final class LayerLayout {
    public static final int STATS_IMAGE_W = 512;
    public static final int STATS_IMAGE_H = 256;
    public static final float DEFAULT_DISTANCE_M = 2f;
    private static final int FALLBACK_W = 1280;
    private static final int FALLBACK_H = 720;
    private static final float STATS_WIDTH_FRACTION = 0.35f;
    private static final float GAP_FRACTION = 0.05f;

    public final boolean cylinder;
    public final boolean flip;
    public final float videoWidthM, videoHeightM, videoZ;
    public final float cylRadius, cylAngleRad, cylAspect;
    public final float statsWidthM, statsHeightM, statsY, statsZ;
    public final int imageW, imageH;

    private LayerLayout(boolean cylinder, boolean flip, float videoWidthM, float videoHeightM, float videoZ,
                        float cylRadius, float cylAngleRad, float cylAspect, float statsWidthM,
                        float statsHeightM, float statsY, float statsZ, int imageW, int imageH) {
        this.cylinder = cylinder;
        this.flip = flip;
        this.videoWidthM = videoWidthM;
        this.videoHeightM = videoHeightM;
        this.videoZ = videoZ;
        this.cylRadius = cylRadius;
        this.cylAngleRad = cylAngleRad;
        this.cylAspect = cylAspect;
        this.statsWidthM = statsWidthM;
        this.statsHeightM = statsHeightM;
        this.statsY = statsY;
        this.statsZ = statsZ;
        this.imageW = imageW;
        this.imageH = imageH;
    }

    public static LayerLayout compute(int videoW, int videoH, float fovDeg, float distanceM,
                                      boolean cylinder, boolean flip) {
        final int w = (videoW > 0 && videoH > 0) ? videoW : FALLBACK_W;
        final int h = (videoW > 0 && videoH > 0) ? videoH : FALLBACK_H;
        final float aspect = (float) w / (float) h;
        final float fovRad = (float) Math.toRadians(fovDeg);
        final float width = cylinder ? distanceM * fovRad : 2f * distanceM * (float) Math.tan(fovRad / 2f);
        final float height = width / aspect;
        final float statsW = width * STATS_WIDTH_FRACTION;
        final float statsH = statsW * STATS_IMAGE_H / STATS_IMAGE_W;
        final float statsY = -(height / 2f + height * GAP_FRACTION + statsH / 2f);
        return new LayerLayout(cylinder, flip, width, height, -distanceM, distanceM, fovRad, aspect,
                statsW, statsH, statsY, -distanceM, w, h);
    }
}
```

- [ ] **Step 4: run JVM test** — `./gradlew --no-daemon :app:xr:testDebugUnitTest` → 4 tests PASS.

- [ ] **Step 5: native sources**

`app/xr/src/main/cpp/CMakeLists.txt`:
```cmake
cmake_minimum_required(VERSION 3.22.1)
project(PixelPilotXr CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(OpenXR REQUIRED CONFIG)

add_library(PixelPilotXr SHARED
    EglContext.cpp
    XrLayers.cpp
    XrRuntime.cpp
    xr_jni.cpp)

target_link_libraries(PixelPilotXr
    OpenXR::headers
    OpenXR::openxr_loader
    android
    log
    EGL
    GLESv3)
```

`XrIncludes.h`:
```cpp
#ifndef PIXELPILOT_XRINCLUDES_H
#define PIXELPILOT_XRINCLUDES_H

// One place that sets the platform/graphics macros before the OpenXR headers.
#include <EGL/egl.h>
#include <jni.h>
#define XR_USE_PLATFORM_ANDROID
#define XR_USE_GRAPHICS_API_OPENGL_ES
#include <openxr/openxr.h>
#include <openxr/openxr_platform.h>

#endif  // PIXELPILOT_XRINCLUDES_H
```

`EglContext.h`:
```cpp
#ifndef PIXELPILOT_EGLCONTEXT_H
#define PIXELPILOT_EGLCONTEXT_H

#include <EGL/egl.h>

// Minimal pbuffer EGL context. OpenXR's GLES binding needs one to create a session, even though
// nothing renders with GL here: video and stats are Android surfaces the compositor samples.
class EglContext
{
  public:
    // Creates the context and makes it current on the calling thread.
    bool create();
    void destroy();
    EGLDisplay display() const { return mDisplay; }
    EGLConfig  config() const { return mConfig; }
    EGLContext context() const { return mContext; }

  private:
    EGLDisplay mDisplay = EGL_NO_DISPLAY;
    EGLConfig  mConfig  = nullptr;
    EGLContext mContext = EGL_NO_CONTEXT;
    EGLSurface mSurface = EGL_NO_SURFACE;
};

#endif  // PIXELPILOT_EGLCONTEXT_H
```

`EglContext.cpp`:
```cpp
#include "EglContext.h"
#include <EGL/eglext.h>

bool EglContext::create()
{
    mDisplay = eglGetDisplay(EGL_DEFAULT_DISPLAY);
    if (mDisplay == EGL_NO_DISPLAY || eglInitialize(mDisplay, nullptr, nullptr) != EGL_TRUE) return false;
    const EGLint attribs[] = {EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8,
                              EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT_KHR, EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
                              EGL_NONE};
    EGLint n = 0;
    if (eglChooseConfig(mDisplay, attribs, &mConfig, 1, &n) != EGL_TRUE || n < 1) return false;
    const EGLint ctxAttribs[] = {EGL_CONTEXT_CLIENT_VERSION, 3, EGL_NONE};
    mContext = eglCreateContext(mDisplay, mConfig, EGL_NO_CONTEXT, ctxAttribs);
    if (mContext == EGL_NO_CONTEXT) return false;
    const EGLint pbuffer[] = {EGL_WIDTH, 16, EGL_HEIGHT, 16, EGL_NONE};
    mSurface = eglCreatePbufferSurface(mDisplay, mConfig, pbuffer);
    if (mSurface == EGL_NO_SURFACE) return false;
    return eglMakeCurrent(mDisplay, mSurface, mSurface, mContext) == EGL_TRUE;
}

void EglContext::destroy()
{
    if (mDisplay == EGL_NO_DISPLAY) return;
    eglMakeCurrent(mDisplay, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
    if (mSurface != EGL_NO_SURFACE) eglDestroySurface(mDisplay, mSurface);
    if (mContext != EGL_NO_CONTEXT) eglDestroyContext(mDisplay, mContext);
    eglTerminate(mDisplay);
    mDisplay = EGL_NO_DISPLAY;
    mConfig  = nullptr;
    mContext = EGL_NO_CONTEXT;
    mSurface = EGL_NO_SURFACE;
}
```

`XrLayers.h`:
```cpp
#ifndef PIXELPILOT_XRLAYERS_H
#define PIXELPILOT_XRLAYERS_H

#include "XrIncludes.h"

// Mirrors com.openipc.xr.LayerLayout (which owns the math).
struct LayerConfig
{
    bool  cylinder     = false;
    bool  flip         = true;
    float videoWidthM  = 2.31f;
    float videoHeightM = 1.30f;
    float videoZ       = -2.f;
    float cylRadius    = 2.f;
    float cylAngleRad  = 1.047f;
    float cylAspect    = 16.f / 9.f;
    float statsWidthM  = 0.81f;
    float statsHeightM = 0.40f;
    float statsY       = -0.92f;
    float statsZ       = -2.f;
    int   imageW       = 1280;
    int   imageH       = 720;
    int   statsImageW  = 512;
    int   statsImageH  = 256;
};

// Builds the two head-locked layers for one xrEndFrame. The structs live here so the pointers
// handed to xrEndFrame stay valid until it returns.
class XrLayers
{
  public:
    void build(const LayerConfig& c, XrSpace viewSpace, XrSwapchain video, XrSwapchain stats,
               bool imageLayoutEnabled, bool cylinderEnabled);
    const XrCompositionLayerBaseHeader* const* layers() const { return mPtrs; }
    uint32_t                                   count() const { return mCount; }

  private:
    XrCompositionLayerQuad              mVideoQuad{XR_TYPE_COMPOSITION_LAYER_QUAD};
    XrCompositionLayerCylinderKHR       mVideoCylinder{XR_TYPE_COMPOSITION_LAYER_CYLINDER_KHR};
    XrCompositionLayerQuad              mStatsQuad{XR_TYPE_COMPOSITION_LAYER_QUAD};
    XrCompositionLayerImageLayoutFB     mFlip{XR_TYPE_COMPOSITION_LAYER_IMAGE_LAYOUT_FB};
    const XrCompositionLayerBaseHeader* mPtrs[2]{};
    uint32_t                            mCount = 0;
};

#endif  // PIXELPILOT_XRLAYERS_H
```

`XrLayers.cpp`:
```cpp
#include "XrLayers.h"

namespace
{
XrPosef pose(float x, float y, float z)
{
    XrPosef p{};
    p.orientation.w = 1.f;
    p.position      = {x, y, z};
    return p;
}

XrSwapchainSubImage subImage(XrSwapchain swapchain, int w, int h)
{
    XrSwapchainSubImage s{};
    s.swapchain       = swapchain;
    s.imageRect       = {{0, 0}, {w, h}};
    s.imageArrayIndex = 0;
    return s;
}
}  // namespace

void XrLayers::build(const LayerConfig& c, XrSpace viewSpace, XrSwapchain video, XrSwapchain stats,
                     bool imageLayoutEnabled, bool cylinderEnabled)
{
    // Android surfaces arrive top-down; negative subImage heights no longer work on current Horizon OS
    // (CitraVR utils/Common.h), so the flip goes through XR_FB_composition_layer_image_layout.
    mFlip.flags      = XR_COMPOSITION_LAYER_IMAGE_LAYOUT_VERTICAL_FLIP_BIT_FB;
    const void* next = (imageLayoutEnabled && c.flip) ? &mFlip : nullptr;

    if (c.cylinder && cylinderEnabled)
    {
        mVideoCylinder.next          = next;
        mVideoCylinder.layerFlags    = 0;
        mVideoCylinder.space         = viewSpace;
        mVideoCylinder.eyeVisibility = XR_EYE_VISIBILITY_BOTH;
        mVideoCylinder.subImage      = subImage(video, c.imageW, c.imageH);
        mVideoCylinder.pose          = pose(0.f, 0.f, 0.f);
        mVideoCylinder.radius        = c.cylRadius;
        mVideoCylinder.centralAngle  = c.cylAngleRad;
        mVideoCylinder.aspectRatio   = c.cylAspect;
        mPtrs[0] = reinterpret_cast<const XrCompositionLayerBaseHeader*>(&mVideoCylinder);
    }
    else
    {
        mVideoQuad.next          = next;
        mVideoQuad.layerFlags    = 0;
        mVideoQuad.space         = viewSpace;
        mVideoQuad.eyeVisibility = XR_EYE_VISIBILITY_BOTH;
        mVideoQuad.subImage      = subImage(video, c.imageW, c.imageH);
        mVideoQuad.pose          = pose(0.f, 0.f, c.videoZ);
        mVideoQuad.size          = {c.videoWidthM, c.videoHeightM};
        mPtrs[0] = reinterpret_cast<const XrCompositionLayerBaseHeader*>(&mVideoQuad);
    }

    mStatsQuad.next          = next;
    mStatsQuad.layerFlags    = XR_COMPOSITION_LAYER_BLEND_TEXTURE_SOURCE_ALPHA_BIT;
    mStatsQuad.space         = viewSpace;
    mStatsQuad.eyeVisibility = XR_EYE_VISIBILITY_BOTH;
    mStatsQuad.subImage      = subImage(stats, c.statsImageW, c.statsImageH);
    mStatsQuad.pose          = pose(0.f, c.statsY, c.statsZ);
    mStatsQuad.size          = {c.statsWidthM, c.statsHeightM};
    mPtrs[1]                 = reinterpret_cast<const XrCompositionLayerBaseHeader*>(&mStatsQuad);
    mCount                   = 2;
}
```

`XrRuntime.h`:
```cpp
#ifndef PIXELPILOT_XRRUNTIME_H
#define PIXELPILOT_XRRUNTIME_H

#include <atomic>
#include <functional>
#include <future>
#include <mutex>
#include <set>
#include <string>
#include <thread>
#include "EglContext.h"
#include "XrIncludes.h"
#include "XrLayers.h"

// Matches XrBridge.SessionEvent ordinals.
enum class SessionEvent : int
{
    Active   = 0,  // session VISIBLE/FOCUSED: surfaces may be written
    Inactive = 1,  // leaving VISIBLE or stopping: the producer must stop before this returns
    Exiting  = 2,  // runtime asked the app to quit
};

struct XrStartConfig
{
    float refreshHz         = 120.f;
    bool  useTimestamps     = false;
    bool  perfSustainedHigh = true;
};

// Values < 0 mean "not available".
struct XrRuntimeInfo
{
    float refreshHz          = -1.f;
    float requestedHz        = -1.f;
    float compositorGpuMs    = -1.f;
    float droppedFrames      = -1.f;
    float motionToPhotonMs   = -1.f;
};

// Owns the OpenXR instance, session and frame loop on its own thread (the EGL context lives there).
// Video and stats are Android surface swapchains: the compositor consumes whatever their producers
// queue, independently of this loop, which only re-submits the two layers every frame.
class XrRuntime
{
  public:
    using Listener = std::function<void(SessionEvent)>;

    ~XrRuntime();
    // Takes ownership of the global ref `activity`. Blocks until the session and both surfaces
    // exist (true) or setup failed (false, see error()).
    bool start(JavaVM* vm, jobject activityGlobalRef, const XrStartConfig& cfg, Listener listener);
    // Ends the session (Inactive is delivered first if needed) and joins the loop thread.
    void stop();

    jobject       videoSurface() const { return mVideoSurface; }
    jobject       statsSurface() const { return mStatsSurface; }
    void          setLayerConfig(const LayerConfig& c);
    XrRuntimeInfo info();
    std::string   error();

  private:
    void     threadMain(JavaVM* vm, XrStartConfig cfg, std::promise<bool> ready);
    bool     setup(JNIEnv* env);
    bool     fail(const std::string& what);
    bool     enabled(const char* ext) const { return mEnabled.count(ext) != 0; }
    void     loadFunctions();
    jobject  createSurface(JNIEnv* env, int w, int h, bool useTimestamps, XrSwapchain& out);
    void     loop();
    void     pollEvents();
    void     onStateChanged(XrSessionState state);
    void     setVideoAllowed(bool allowed);
    void     renderFrame();
    void     endSession();
    void     applyRefreshRate();
    void     applyPerformanceHints();
    void     enableMetrics();
    void     readMetrics();
    float    queryMetric(XrPath path);
    void     teardown(JNIEnv* env);

    std::thread       mThread;
    std::atomic<bool> mExit{false};
    Listener          mListener;
    XrStartConfig     mCfg;
    JavaVM*           mVm       = nullptr;
    jobject           mActivity = nullptr;

    std::mutex    mMutex;  // guards mError, mLayerConfig, mResizePending, mInfo
    std::string   mError;
    LayerConfig   mLayerConfig;
    bool          mResizePending = false;
    XrRuntimeInfo mInfo;

    std::set<std::string> mEnabled;
    EglContext            mEgl;
    XrInstance            mInstance     = XR_NULL_HANDLE;
    XrSystemId            mSystemId     = XR_NULL_SYSTEM_ID;
    XrSession             mSession      = XR_NULL_HANDLE;
    XrSpace               mViewSpace    = XR_NULL_HANDLE;
    XrSwapchain           mVideoChain   = XR_NULL_HANDLE;
    XrSwapchain           mStatsChain   = XR_NULL_HANDLE;
    jobject               mVideoSurface = nullptr;
    jobject               mStatsSurface = nullptr;
    XrSessionState        mState        = XR_SESSION_STATE_UNKNOWN;
    bool                  mRunning      = false;
    bool                  mVideoAllowed = false;
    bool                  mRuntimeExit  = false;
    uint64_t              mFrames       = 0;
    XrLayers              mLayers;

    PFN_xrCreateSwapchainAndroidSurfaceKHR   pfnCreateSurface     = nullptr;
    PFN_xrEnumerateDisplayRefreshRatesFB     pfnEnumerateRates    = nullptr;
    PFN_xrRequestDisplayRefreshRateFB        pfnRequestRate       = nullptr;
    PFN_xrGetDisplayRefreshRateFB            pfnGetRate           = nullptr;
    PFN_xrPerfSettingsSetPerformanceLevelEXT pfnPerfLevel         = nullptr;
    PFN_xrSetAndroidApplicationThreadKHR     pfnSetThread         = nullptr;
    PFN_xrUpdateSwapchainFB                  pfnUpdateSwapchain   = nullptr;
    PFN_xrSetPerformanceMetricsStateMETA     pfnSetMetricsState   = nullptr;
    PFN_xrQueryPerformanceMetricsCounterMETA pfnQueryMetric       = nullptr;
    XrPath                                   mPathCompositorGpu   = XR_NULL_PATH;
    XrPath                                   mPathDroppedFrames   = XR_NULL_PATH;
    XrPath                                   mPathMotionToPhoton  = XR_NULL_PATH;
};

#endif  // PIXELPILOT_XRRUNTIME_H
```

`XrRuntime.cpp`:
```cpp
#include "XrRuntime.h"
#include <android/log.h>
#include <sys/prctl.h>
#include <unistd.h>
#include <algorithm>
#include <cstring>
#include <vector>

#define XR_TAG "PixelPilotXr"
#define XLOGI(...) __android_log_print(ANDROID_LOG_INFO, XR_TAG, __VA_ARGS__)
#define XLOGE(...) __android_log_print(ANDROID_LOG_ERROR, XR_TAG, __VA_ARGS__)

namespace
{
template <typename T>
bool loadFn(XrInstance instance, const char* name, T& fn)
{
    fn = nullptr;
    return XR_SUCCEEDED(xrGetInstanceProcAddr(instance, name, reinterpret_cast<PFN_xrVoidFunction*>(&fn))) &&
           fn != nullptr;
}

XrPosef identityPose()
{
    XrPosef p{};
    p.orientation.w = 1.f;
    return p;
}
}  // namespace

XrRuntime::~XrRuntime() { stop(); }

bool XrRuntime::start(JavaVM* vm, jobject activityGlobalRef, const XrStartConfig& cfg, Listener listener)
{
    if (mThread.joinable())
    {
        return fail("already started");
    }
    mActivity = activityGlobalRef;
    mListener = std::move(listener);
    mExit     = false;
    std::promise<bool> ready;
    auto               result = ready.get_future();
    mThread                   = std::thread(&XrRuntime::threadMain, this, vm, cfg, std::move(ready));
    if (result.wait_for(std::chrono::seconds(10)) != std::future_status::ready)
    {
        fail("OpenXR setup timed out");
        stop();
        return false;
    }
    const bool ok = result.get();
    if (!ok) stop();
    return ok;
}

void XrRuntime::stop()
{
    mExit = true;
    if (mThread.joinable()) mThread.join();
}

void XrRuntime::setLayerConfig(const LayerConfig& c)
{
    std::lock_guard<std::mutex> lock(mMutex);
    mResizePending = mResizePending || c.imageW != mLayerConfig.imageW || c.imageH != mLayerConfig.imageH;
    mLayerConfig   = c;
}

XrRuntimeInfo XrRuntime::info()
{
    std::lock_guard<std::mutex> lock(mMutex);
    return mInfo;
}

std::string XrRuntime::error()
{
    std::lock_guard<std::mutex> lock(mMutex);
    return mError;
}

bool XrRuntime::fail(const std::string& what)
{
    XLOGE("%s", what.c_str());
    std::lock_guard<std::mutex> lock(mMutex);
    mError = what;
    return false;
}

void XrRuntime::threadMain(JavaVM* vm, XrStartConfig cfg, std::promise<bool> ready)
{
    prctl(PR_SET_NAME, "PixelPilotXr");
    mVm          = vm;
    mCfg         = cfg;
    JNIEnv* env  = nullptr;
    vm->AttachCurrentThread(&env, nullptr);
    const bool ok = setup(env);
    ready.set_value(ok);
    if (ok) loop();
    teardown(env);
    vm->DetachCurrentThread();
}

bool XrRuntime::setup(JNIEnv* env)
{
    PFN_xrInitializeLoaderKHR initLoader = nullptr;
    if (!loadFn(XR_NULL_HANDLE, "xrInitializeLoaderKHR", initLoader)) return fail("xrInitializeLoaderKHR missing");
    XrLoaderInitInfoAndroidKHR loaderInfo{XR_TYPE_LOADER_INIT_INFO_ANDROID_KHR};
    loaderInfo.applicationVM      = mVm;
    loaderInfo.applicationContext = mActivity;
    if (XR_FAILED(initLoader(reinterpret_cast<const XrLoaderInitInfoBaseHeaderKHR*>(&loaderInfo))))
        return fail("OpenXR loader init failed");

    uint32_t count = 0;
    xrEnumerateInstanceExtensionProperties(nullptr, 0, &count, nullptr);
    std::vector<XrExtensionProperties> props(count, {XR_TYPE_EXTENSION_PROPERTIES});
    xrEnumerateInstanceExtensionProperties(nullptr, count, &count, props.data());
    std::set<std::string> available;
    for (const auto& p : props) available.insert(p.extensionName);

    const char* required[] = {XR_KHR_ANDROID_CREATE_INSTANCE_EXTENSION_NAME, XR_KHR_OPENGL_ES_ENABLE_EXTENSION_NAME,
                              XR_KHR_ANDROID_SURFACE_SWAPCHAIN_EXTENSION_NAME};
    const char* optional[] = {XR_FB_ANDROID_SURFACE_SWAPCHAIN_CREATE_EXTENSION_NAME,
                              XR_FB_DISPLAY_REFRESH_RATE_EXTENSION_NAME,
                              XR_EXT_PERFORMANCE_SETTINGS_EXTENSION_NAME,
                              XR_KHR_ANDROID_THREAD_SETTINGS_EXTENSION_NAME,
                              XR_FB_COMPOSITION_LAYER_IMAGE_LAYOUT_EXTENSION_NAME,
                              XR_KHR_COMPOSITION_LAYER_CYLINDER_EXTENSION_NAME,
                              XR_META_PERFORMANCE_METRICS_EXTENSION_NAME,
                              XR_FB_SWAPCHAIN_UPDATE_STATE_EXTENSION_NAME,
                              XR_FB_SWAPCHAIN_UPDATE_STATE_ANDROID_SURFACE_EXTENSION_NAME};
    std::vector<const char*> exts;
    for (const char* e : required)
    {
        if (!available.count(e)) return fail(std::string("OpenXR runtime lacks ") + e);
        exts.push_back(e);
        mEnabled.insert(e);
    }
    for (const char* e : optional)
    {
        if (!available.count(e)) continue;
        exts.push_back(e);
        mEnabled.insert(e);
    }

    XrInstanceCreateInfoAndroidKHR androidInfo{XR_TYPE_INSTANCE_CREATE_INFO_ANDROID_KHR};
    androidInfo.applicationVM       = mVm;
    androidInfo.applicationActivity = mActivity;
    XrInstanceCreateInfo createInfo{XR_TYPE_INSTANCE_CREATE_INFO};
    createInfo.next = &androidInfo;
    std::strncpy(createInfo.applicationInfo.applicationName, "PixelPilot XR", XR_MAX_APPLICATION_NAME_SIZE - 1);
    std::strncpy(createInfo.applicationInfo.engineName, "PixelPilot", XR_MAX_ENGINE_NAME_SIZE - 1);
    createInfo.applicationInfo.applicationVersion = 1;
    createInfo.applicationInfo.apiVersion         = XR_API_VERSION_1_0;
    createInfo.enabledExtensionCount              = static_cast<uint32_t>(exts.size());
    createInfo.enabledExtensionNames              = exts.data();
    if (XR_FAILED(xrCreateInstance(&createInfo, &mInstance))) return fail("xrCreateInstance failed");

    XrSystemGetInfo systemInfo{XR_TYPE_SYSTEM_GET_INFO};
    systemInfo.formFactor = XR_FORM_FACTOR_HEAD_MOUNTED_DISPLAY;
    if (XR_FAILED(xrGetSystem(mInstance, &systemInfo, &mSystemId))) return fail("xrGetSystem failed (no HMD)");

    PFN_xrGetOpenGLESGraphicsRequirementsKHR glesRequirements = nullptr;
    if (!loadFn(mInstance, "xrGetOpenGLESGraphicsRequirementsKHR", glesRequirements))
        return fail("xrGetOpenGLESGraphicsRequirementsKHR missing");
    XrGraphicsRequirementsOpenGLESKHR requirements{XR_TYPE_GRAPHICS_REQUIREMENTS_OPENGL_ES_KHR};
    glesRequirements(mInstance, mSystemId, &requirements);  // mandatory before xrCreateSession
    if (!mEgl.create()) return fail("EGL context creation failed");

    XrGraphicsBindingOpenGLESAndroidKHR binding{XR_TYPE_GRAPHICS_BINDING_OPENGL_ES_ANDROID_KHR};
    binding.display = mEgl.display();
    binding.config  = mEgl.config();
    binding.context = mEgl.context();
    XrSessionCreateInfo sessionInfo{XR_TYPE_SESSION_CREATE_INFO};
    sessionInfo.next     = &binding;
    sessionInfo.systemId = mSystemId;
    if (XR_FAILED(xrCreateSession(mInstance, &sessionInfo, &mSession))) return fail("xrCreateSession failed");

    XrReferenceSpaceCreateInfo spaceInfo{XR_TYPE_REFERENCE_SPACE_CREATE_INFO};
    spaceInfo.referenceSpaceType   = XR_REFERENCE_SPACE_TYPE_VIEW;  // head-locked: never reprojected
    spaceInfo.poseInReferenceSpace = identityPose();
    if (XR_FAILED(xrCreateReferenceSpace(mSession, &spaceInfo, &mViewSpace))) return fail("VIEW space failed");

    loadFunctions();
    if (!pfnCreateSurface) return fail("xrCreateSwapchainAndroidSurfaceKHR missing");
    LayerConfig initial;
    {
        std::lock_guard<std::mutex> lock(mMutex);
        initial = mLayerConfig;
    }
    mVideoSurface = createSurface(env, initial.imageW, initial.imageH, mCfg.useTimestamps, mVideoChain);
    if (!mVideoSurface) return fail("video surface swapchain creation failed");
    mStatsSurface = createSurface(env, initial.statsImageW, initial.statsImageH, false, mStatsChain);
    if (!mStatsSurface) return fail("stats surface swapchain creation failed");
    enableMetrics();
    XLOGI("OpenXR ready: %zu extensions enabled", mEnabled.size());
    return true;
}

void XrRuntime::loadFunctions()
{
    loadFn(mInstance, "xrCreateSwapchainAndroidSurfaceKHR", pfnCreateSurface);
    if (enabled(XR_FB_DISPLAY_REFRESH_RATE_EXTENSION_NAME))
    {
        loadFn(mInstance, "xrEnumerateDisplayRefreshRatesFB", pfnEnumerateRates);
        loadFn(mInstance, "xrRequestDisplayRefreshRateFB", pfnRequestRate);
        loadFn(mInstance, "xrGetDisplayRefreshRateFB", pfnGetRate);
    }
    if (enabled(XR_EXT_PERFORMANCE_SETTINGS_EXTENSION_NAME))
        loadFn(mInstance, "xrPerfSettingsSetPerformanceLevelEXT", pfnPerfLevel);
    if (enabled(XR_KHR_ANDROID_THREAD_SETTINGS_EXTENSION_NAME))
        loadFn(mInstance, "xrSetAndroidApplicationThreadKHR", pfnSetThread);
    if (enabled(XR_FB_SWAPCHAIN_UPDATE_STATE_ANDROID_SURFACE_EXTENSION_NAME))
        loadFn(mInstance, "xrUpdateSwapchainFB", pfnUpdateSwapchain);
    if (enabled(XR_META_PERFORMANCE_METRICS_EXTENSION_NAME))
    {
        loadFn(mInstance, "xrSetPerformanceMetricsStateMETA", pfnSetMetricsState);
        loadFn(mInstance, "xrQueryPerformanceMetricsCounterMETA", pfnQueryMetric);
    }
}

jobject XrRuntime::createSurface(JNIEnv* env, int w, int h, bool useTimestamps, XrSwapchain& out)
{
    XrSwapchainCreateInfo info{XR_TYPE_SWAPCHAIN_CREATE_INFO};
    XrAndroidSurfaceSwapchainCreateInfoFB fbInfo{XR_TYPE_ANDROID_SURFACE_SWAPCHAIN_CREATE_INFO_FB};
    if (enabled(XR_FB_ANDROID_SURFACE_SWAPCHAIN_CREATE_EXTENSION_NAME))
    {
        // Never SYNCHRONOUS: the default BufferQueue replaces the pending buffer (mailbox), which is
        // what keeps a late frame from queueing behind an older one.
        fbInfo.createFlags = useTimestamps ? XR_ANDROID_SURFACE_SWAPCHAIN_USE_TIMESTAMPS_BIT_FB : 0;
        info.next          = &fbInfo;
    }
    info.usageFlags  = XR_SWAPCHAIN_USAGE_SAMPLED_BIT | XR_SWAPCHAIN_USAGE_COLOR_ATTACHMENT_BIT;
    info.width       = static_cast<uint32_t>(w);
    info.height      = static_cast<uint32_t>(h);
    // format, sampleCount, faceCount, arraySize, mipCount must be zero for this extension.
    jobject surface  = nullptr;
    if (XR_FAILED(pfnCreateSurface(mSession, &info, &out, &surface)) || surface == nullptr) return nullptr;
    // Own a global ref regardless of what the runtime handed back; only free what was local.
    jobject global = env->NewGlobalRef(surface);
    if (env->GetObjectRefType(surface) == JNILocalRefType) env->DeleteLocalRef(surface);
    return global;
}

void XrRuntime::loop()
{
    while (!mExit && !mRuntimeExit)
    {
        pollEvents();
        if (!mRunning)
        {
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
            continue;
        }
        renderFrame();
    }
    if (mRunning) endSession();
}

void XrRuntime::pollEvents()
{
    XrEventDataBuffer event{XR_TYPE_EVENT_DATA_BUFFER};
    while (xrPollEvent(mInstance, &event) == XR_SUCCESS)
    {
        if (event.type == XR_TYPE_EVENT_DATA_SESSION_STATE_CHANGED)
        {
            const auto& changed = reinterpret_cast<const XrEventDataSessionStateChanged&>(event);
            onStateChanged(changed.state);
        }
        else if (event.type == XR_TYPE_EVENT_DATA_INSTANCE_LOSS_PENDING)
        {
            mRuntimeExit = true;
            if (mListener) mListener(SessionEvent::Exiting);
        }
        event = {XR_TYPE_EVENT_DATA_BUFFER};
    }
}

void XrRuntime::onStateChanged(XrSessionState state)
{
    XLOGI("session state %d -> %d", mState, state);
    mState = state;
    switch (state)
    {
        case XR_SESSION_STATE_READY:
        {
            XrSessionBeginInfo begin{XR_TYPE_SESSION_BEGIN_INFO};
            begin.primaryViewConfigurationType = XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO;
            if (XR_FAILED(xrBeginSession(mSession, &begin)))
            {
                fail("xrBeginSession failed");
                break;
            }
            mRunning = true;
            applyRefreshRate();
            applyPerformanceHints();
            break;
        }
        case XR_SESSION_STATE_VISIBLE:
        case XR_SESSION_STATE_FOCUSED:
            setVideoAllowed(true);
            break;
        case XR_SESSION_STATE_SYNCHRONIZED:
            setVideoAllowed(false);  // dropped out of VISIBLE: writing is undefined from here on
            break;
        case XR_SESSION_STATE_STOPPING:
            endSession();
            break;
        case XR_SESSION_STATE_EXITING:
        case XR_SESSION_STATE_LOSS_PENDING:
            mRuntimeExit = true;
            if (mListener) mListener(SessionEvent::Exiting);
            break;
        default:
            break;
    }
}

void XrRuntime::setVideoAllowed(bool allowed)
{
    if (allowed == mVideoAllowed) return;
    mVideoAllowed = allowed;
    if (mListener) mListener(allowed ? SessionEvent::Active : SessionEvent::Inactive);
}

void XrRuntime::endSession()
{
    setVideoAllowed(false);  // the producer has stopped when this returns (spec: before xrEndSession)
    xrEndSession(mSession);
    mRunning = false;
}

void XrRuntime::renderFrame()
{
    XrFrameWaitInfo waitInfo{XR_TYPE_FRAME_WAIT_INFO};
    XrFrameState    frameState{XR_TYPE_FRAME_STATE};
    if (XR_FAILED(xrWaitFrame(mSession, &waitInfo, &frameState))) return;
    XrFrameBeginInfo beginInfo{XR_TYPE_FRAME_BEGIN_INFO};
    if (XR_FAILED(xrBeginFrame(mSession, &beginInfo))) return;

    LayerConfig config;
    bool        resize = false;
    {
        std::lock_guard<std::mutex> lock(mMutex);
        config         = mLayerConfig;
        resize         = mResizePending;
        mResizePending = false;
    }
    if (resize && pfnUpdateSwapchain)
    {
        XrSwapchainStateAndroidSurfaceDimensionsFB dims{XR_TYPE_SWAPCHAIN_STATE_ANDROID_SURFACE_DIMENSIONS_FB};
        dims.width  = static_cast<uint32_t>(config.imageW);
        dims.height = static_cast<uint32_t>(config.imageH);
        pfnUpdateSwapchain(mVideoChain, reinterpret_cast<const XrSwapchainStateBaseHeaderFB*>(&dims));
    }

    XrFrameEndInfo endInfo{XR_TYPE_FRAME_END_INFO};
    endInfo.displayTime          = frameState.predictedDisplayTime;
    endInfo.environmentBlendMode = XR_ENVIRONMENT_BLEND_MODE_OPAQUE;
    if (frameState.shouldRender)
    {
        mLayers.build(config, mViewSpace, mVideoChain, mStatsChain,
                      enabled(XR_FB_COMPOSITION_LAYER_IMAGE_LAYOUT_EXTENSION_NAME),
                      enabled(XR_KHR_COMPOSITION_LAYER_CYLINDER_EXTENSION_NAME));
        endInfo.layerCount = mLayers.count();
        endInfo.layers     = mLayers.layers();
    }
    xrEndFrame(mSession, &endInfo);
    if (++mFrames % 30 == 0) readMetrics();
}

void XrRuntime::applyRefreshRate()
{
    {
        std::lock_guard<std::mutex> lock(mMutex);
        mInfo.requestedHz = mCfg.refreshHz;
    }
    if (!pfnEnumerateRates || !pfnRequestRate) return;
    uint32_t n = 0;
    pfnEnumerateRates(mSession, 0, &n, nullptr);
    std::vector<float> rates(n);
    pfnEnumerateRates(mSession, n, &n, rates.data());
    float best = -1.f;
    for (float r : rates)
        if (r <= mCfg.refreshHz + 0.5f && r > best) best = r;  // highest supported <= requested
    if (best < 0.f && !rates.empty()) best = *std::min_element(rates.begin(), rates.end());
    if (best > 0.f)
    {
        const XrResult r = pfnRequestRate(mSession, best);
        XLOGI("requested %.0f Hz -> %.0f Hz (result %d)", mCfg.refreshHz, best, r);
    }
}

void XrRuntime::applyPerformanceHints()
{
    if (pfnSetThread) pfnSetThread(mSession, XR_ANDROID_THREAD_TYPE_RENDERER_MAIN_KHR, gettid());
    if (!mCfg.perfSustainedHigh || !pfnPerfLevel) return;
    pfnPerfLevel(mSession, XR_PERF_SETTINGS_DOMAIN_CPU_EXT, XR_PERF_SETTINGS_LEVEL_SUSTAINED_HIGH_EXT);
    pfnPerfLevel(mSession, XR_PERF_SETTINGS_DOMAIN_GPU_EXT, XR_PERF_SETTINGS_LEVEL_SUSTAINED_HIGH_EXT);
}

void XrRuntime::enableMetrics()
{
    if (!pfnSetMetricsState || !pfnQueryMetric) return;
    XrPerformanceMetricsStateMETA state{XR_TYPE_PERFORMANCE_METRICS_STATE_META};
    state.enabled = XR_TRUE;
    pfnSetMetricsState(mSession, &state);
    xrStringToPath(mInstance, "/perfmetrics_meta/compositor/gpu_frametime", &mPathCompositorGpu);
    xrStringToPath(mInstance, "/perfmetrics_meta/compositor/dropped_frame_count", &mPathDroppedFrames);
    xrStringToPath(mInstance, "/perfmetrics_meta/app/motion_to_photon_latency", &mPathMotionToPhoton);
}

float XrRuntime::queryMetric(XrPath path)
{
    if (!pfnQueryMetric || path == XR_NULL_PATH) return -1.f;
    XrPerformanceMetricsCounterMETA counter{XR_TYPE_PERFORMANCE_METRICS_COUNTER_META};
    if (XR_FAILED(pfnQueryMetric(mSession, path, &counter))) return -1.f;
    if (counter.counterFlags & XR_PERFORMANCE_METRICS_COUNTER_FLOAT_VALUE_VALID_BIT_META) return counter.floatValue;
    if (counter.counterFlags & XR_PERFORMANCE_METRICS_COUNTER_UINT_VALUE_VALID_BIT_META)
        return static_cast<float>(counter.uintValue);
    return -1.f;
}

void XrRuntime::readMetrics()
{
    float hz = -1.f;
    if (pfnGetRate) pfnGetRate(mSession, &hz);
    const float gpu     = queryMetric(mPathCompositorGpu);
    const float dropped = queryMetric(mPathDroppedFrames);
    const float m2p     = queryMetric(mPathMotionToPhoton);
    std::lock_guard<std::mutex> lock(mMutex);
    mInfo.refreshHz        = hz;
    mInfo.compositorGpuMs  = gpu;
    mInfo.droppedFrames    = dropped;
    mInfo.motionToPhotonMs = m2p;
}

void XrRuntime::teardown(JNIEnv* env)
{
    if (mVideoChain != XR_NULL_HANDLE) xrDestroySwapchain(mVideoChain);
    if (mStatsChain != XR_NULL_HANDLE) xrDestroySwapchain(mStatsChain);
    if (mViewSpace != XR_NULL_HANDLE) xrDestroySpace(mViewSpace);
    if (mSession != XR_NULL_HANDLE) xrDestroySession(mSession);
    mEgl.destroy();
    if (mInstance != XR_NULL_HANDLE) xrDestroyInstance(mInstance);
    if (mVideoSurface) env->DeleteGlobalRef(mVideoSurface);
    if (mStatsSurface) env->DeleteGlobalRef(mStatsSurface);
    if (mActivity) env->DeleteGlobalRef(mActivity);
    mVideoChain = mStatsChain = XR_NULL_HANDLE;
    mViewSpace                = XR_NULL_HANDLE;
    mSession                  = XR_NULL_HANDLE;
    mInstance                 = XR_NULL_HANDLE;
    mVideoSurface = mStatsSurface = mActivity = nullptr;
    mRunning = mVideoAllowed = false;
}
```

`xr_jni.cpp`:
```cpp
#include <jni.h>
#include "XrRuntime.h"

namespace
{
struct Handle
{
    XrRuntime runtime;
    jobject   bridge = nullptr;  // global ref to the XrBridge
};

Handle* handle(jlong h) { return reinterpret_cast<Handle*>(h); }
}  // namespace

#define XR_JNI(ret, name) extern "C" JNIEXPORT ret JNICALL Java_com_openipc_xr_XrBridge_##name

XR_JNI(jlong, nativeCreate)(JNIEnv* env, jobject thiz)
{
    auto* h   = new Handle();
    h->bridge = env->NewGlobalRef(thiz);
    return reinterpret_cast<jlong>(h);
}

XR_JNI(jboolean, nativeStart)
(JNIEnv* env, jobject, jlong h, jobject activity, jfloat refreshHz, jboolean useTimestamps, jboolean perfHigh)
{
    Handle* p = handle(h);
    JavaVM* vm = nullptr;
    env->GetJavaVM(&vm);
    jclass    cls   = env->GetObjectClass(p->bridge);
    jmethodID onEvt = env->GetMethodID(cls, "onNativeSessionEvent", "(I)V");
    jobject   bridge = p->bridge;
    XrStartConfig cfg;
    cfg.refreshHz         = refreshHz;
    cfg.useTimestamps     = useTimestamps;
    cfg.perfSustainedHigh = perfHigh;
    // Called on the XR thread, which is attached for its whole life.
    auto listener = [vm, bridge, onEvt](SessionEvent e)
    {
        JNIEnv* threadEnv = nullptr;
        if (vm->GetEnv(reinterpret_cast<void**>(&threadEnv), JNI_VERSION_1_6) != JNI_OK) return;
        threadEnv->CallVoidMethod(bridge, onEvt, static_cast<jint>(e));
        if (threadEnv->ExceptionCheck()) threadEnv->ExceptionClear();
    };
    return p->runtime.start(vm, env->NewGlobalRef(activity), cfg, listener) ? JNI_TRUE : JNI_FALSE;
}

XR_JNI(jstring, nativeError)(JNIEnv* env, jobject, jlong h)
{
    return env->NewStringUTF(handle(h)->runtime.error().c_str());
}

XR_JNI(jobject, nativeVideoSurface)(JNIEnv*, jobject, jlong h) { return handle(h)->runtime.videoSurface(); }

XR_JNI(jobject, nativeStatsSurface)(JNIEnv*, jobject, jlong h) { return handle(h)->runtime.statsSurface(); }

XR_JNI(void, nativeSetLayout)
(JNIEnv* env, jobject, jlong h, jboolean cylinder, jboolean flip, jfloatArray values, jint imageW, jint imageH)
{
    jfloat v[11];
    env->GetFloatArrayRegion(values, 0, 11, v);
    LayerConfig c;
    c.cylinder     = cylinder;
    c.flip         = flip;
    c.videoWidthM  = v[0];
    c.videoHeightM = v[1];
    c.videoZ       = v[2];
    c.cylRadius    = v[3];
    c.cylAngleRad  = v[4];
    c.cylAspect    = v[5];
    c.statsWidthM  = v[6];
    c.statsHeightM = v[7];
    c.statsY       = v[8];
    c.statsZ       = v[9];
    c.statsImageW  = static_cast<int>(v[10]);
    c.statsImageH  = c.statsImageW / 2;
    c.imageW       = imageW;
    c.imageH       = imageH;
    handle(h)->runtime.setLayerConfig(c);
}

XR_JNI(jfloatArray, nativeInfo)(JNIEnv* env, jobject, jlong h)
{
    const XrRuntimeInfo i   = handle(h)->runtime.info();
    const jfloat        v[] = {i.refreshHz, i.requestedHz, i.compositorGpuMs, i.droppedFrames, i.motionToPhotonMs};
    jfloatArray         out = env->NewFloatArray(5);
    env->SetFloatArrayRegion(out, 0, 5, v);
    return out;
}

XR_JNI(void, nativeDestroy)(JNIEnv* env, jobject, jlong h)
{
    Handle* p = handle(h);
    p->runtime.stop();
    env->DeleteGlobalRef(p->bridge);
    delete p;
}
```

- [ ] **Step 6: `XrBridge.java`**

```java
package com.openipc.xr;

import android.app.Activity;
import android.view.Surface;

/**
 * Java face of the native OpenXR runtime. start() creates the session and two compositor-owned
 * surfaces; the caller feeds videoSurface() with MediaCodec and draws the stats into statsSurface().
 */
public final class XrBridge {
    static {
        System.loadLibrary("PixelPilotXr");
    }

    public enum SessionEvent { ACTIVE, INACTIVE, EXITING }

    /**
     * Called on the XR thread. ACTIVE: the video surface may be fed. INACTIVE: stop feeding it
     * before returning (the runtime ends the session right after). EXITING: finish the activity.
     */
    public interface Listener {
        void onSessionEvent(SessionEvent event);
    }

    /** Negative values mean "not reported by the runtime". */
    public static final class Info {
        public final float refreshHz, requestedHz, compositorGpuMs, droppedFrames, motionToPhotonMs;

        Info(float[] v) {
            refreshHz = v[0];
            requestedHz = v[1];
            compositorGpuMs = v[2];
            droppedFrames = v[3];
            motionToPhotonMs = v[4];
        }
    }

    private final Listener listener;
    private long handle;

    public XrBridge(Listener listener) {
        this.listener = listener;
        handle = nativeCreate();
    }

    /** Returns null on success, otherwise a human-readable reason. */
    public String start(Activity activity, int refreshHz, boolean useTimestamps, boolean perfSustainedHigh) {
        if (nativeStart(handle, activity, refreshHz, useTimestamps, perfSustainedHigh)) return null;
        String error = nativeError(handle);
        return error.isEmpty() ? "OpenXR start failed" : error;
    }

    public Surface videoSurface() {
        return (Surface) nativeVideoSurface(handle);
    }

    public Surface statsSurface() {
        return (Surface) nativeStatsSurface(handle);
    }

    public void setLayout(LayerLayout l) {
        float[] v = {l.videoWidthM, l.videoHeightM, l.videoZ, l.cylRadius, l.cylAngleRad, l.cylAspect,
                l.statsWidthM, l.statsHeightM, l.statsY, l.statsZ, LayerLayout.STATS_IMAGE_W};
        nativeSetLayout(handle, l.cylinder, l.flip, v, l.imageW, l.imageH);
    }

    public Info info() {
        return new Info(nativeInfo(handle));
    }

    /** Ends the session and frees everything. Stop feeding the video surface before calling. */
    public void stop() {
        if (handle == 0) return;
        nativeDestroy(handle);
        handle = 0;
    }

    @SuppressWarnings("unused") // called from xr_jni.cpp
    private void onNativeSessionEvent(int event) {
        listener.onSessionEvent(SessionEvent.values()[event]);
    }

    private native long nativeCreate();
    private native boolean nativeStart(long h, Activity activity, float refreshHz, boolean useTimestamps, boolean perfHigh);
    private native String nativeError(long h);
    private native Object nativeVideoSurface(long h);
    private native Object nativeStatsSurface(long h);
    private native void nativeSetLayout(long h, boolean cylinder, boolean flip, float[] values, int imageW, int imageH);
    private native float[] nativeInfo(long h);
    private native void nativeDestroy(long h);
}
```

- [ ] **Step 7: build + tests + commit**

Run: `./gradlew --no-daemon :app:xr:testDebugUnitTest assembleDebug` → SUCCESS;
`unzip -l app/build/outputs/apk/debug/app-debug.apk | grep -E "libPixelPilotXr|libopenxr_loader"` → both present for arm64-v8a.
```bash
git add settings.gradle gradle/libs.versions.toml app/build.gradle app/xr
git commit -m "feat(xr): OpenXR runtime with Android surface swapchains and head-locked layers"
```

---

### Task 6: `XrVideoActivity`, stats panel, manifest, "Launch XR" + XR experiment menu

**Files:**
- Create: `app/src/main/java/com/openipc/pixelpilot/XrVideoActivity.java`
- Create: `app/src/main/java/com/openipc/pixelpilot/XrStatsRenderer.java`
- Modify: `app/src/main/AndroidManifest.xml`
- Modify: `app/src/main/java/com/openipc/pixelpilot/VideoActivity.java` (`setupVideoSubMenu`)

**Interfaces:**
- Consumes: `XrBridge`, `LayerLayout` (Task 5), `LatencyExperiments` (Task 1), `VideoPlayer.setDecoderLevers/getDecoderSummary` (Task 3), `WfbLinkManager(Context, LinkStatusListener, WfbNgLink)`, `WfbLinkManager.usbIntentFilter()`, `WfbServiceControl` (Task 4), `VideoActivity.getChannel/getBandwidth` (existing statics).

- [ ] **Step 1: `XrStatsRenderer.java`**

```java
package com.openipc.pixelpilot;

import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.PorterDuff;
import android.view.Surface;

/** Draws the stats panel into its compositor-owned surface with a hardware canvas. */
final class XrStatsRenderer {
    private static final float TEXT_PX = 21f;
    private static final float LINE_PX = 26f;
    private final Surface surface;
    private final Paint text = new Paint(Paint.ANTI_ALIAS_FLAG);

    XrStatsRenderer(Surface surface) {
        this.surface = surface;
        text.setColor(Color.WHITE);
        text.setTextSize(TEXT_PX);
        text.setTypeface(android.graphics.Typeface.MONOSPACE);
    }

    void draw(String[] lines) {
        if (surface == null || !surface.isValid()) return;
        Canvas canvas;
        try {
            canvas = surface.lockHardwareCanvas();
        } catch (RuntimeException e) {
            return; // surface abandoned while the session ends
        }
        try {
            canvas.drawColor(0xB0000000, PorterDuff.Mode.SRC);
            float y = LINE_PX;
            for (String line : lines) {
                canvas.drawText(line, 10f, y, text);
                y += LINE_PX;
            }
        } finally {
            surface.unlockCanvasAndPost(canvas);
        }
    }
}
```

- [ ] **Step 2: `XrVideoActivity.java`**

```java
package com.openipc.pixelpilot;

import android.app.Activity;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.WindowManager;
import android.widget.Toast;

import com.openipc.videonative.DecodingInfo;
import com.openipc.videonative.IVideoParamsChanged;
import com.openipc.videonative.LatencyExperiments;
import com.openipc.videonative.VideoPlayer;
import com.openipc.wfbngrtl8812.WfbNGStats;
import com.openipc.wfbngrtl8812.WfbNGStatsChanged;
import com.openipc.wfbngrtl8812.WfbNgLink;
import com.openipc.xr.LayerLayout;
import com.openipc.xr.XrBridge;

import java.util.Locale;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/**
 * Immersive viewer: MediaCodec renders straight into a compositor-owned surface shown as a
 * head-locked layer. The OpenXR session state is the only owner of video start/stop, so the
 * decoder never writes while the session is not VISIBLE/FOCUSED.
 */
public class XrVideoActivity extends Activity implements IVideoParamsChanged, WfbNGStatsChanged,
        XrBridge.Listener, LinkStatusListener {
    private static final String TAG = "pixelpilot-xr";
    private static final long STATS_PERIOD_MS = 250;
    private static final long INACTIVE_TIMEOUT_MS = 2000;

    private final Handler ui = new Handler(Looper.getMainLooper());
    private LatencyExperiments experiments;
    private XrBridge xr;
    private XrStatsRenderer stats;
    private VideoPlayer videoPlayer;
    private WfbNgLink wfbLink;
    private WfbLinkManager wfbLinkManager;
    private boolean videoAttached;
    private volatile boolean destroying;
    private volatile DecodingInfo lastDecoding;
    private volatile WfbNGStats lastLink;
    private volatile String linkStatus = "";
    private volatile int videoW, videoH;

    private final Runnable statsTick = new Runnable() {
        @Override public void run() {
            if (stats != null) stats.draw(statsLines());
            ui.postDelayed(this, STATS_PERIOD_MS);
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        experiments = LatencyExperiments.load(this);

        xr = new XrBridge(this);
        String error = xr.start(this, experiments.xrRefreshHz, experiments.xrUseTimestamps,
                experiments.xrPerfSustainedHigh);
        if (error != null) {
            Log.e(TAG, "XR unavailable: " + error);
            Toast.makeText(this, "XR mode unavailable: " + error, Toast.LENGTH_LONG).show();
            xr.stop();
            xr = null;
            finish();
            return;
        }
        applyLayout();
        stats = new XrStatsRenderer(xr.statsSurface());

        videoPlayer = new VideoPlayer(this);
        videoPlayer.setIVideoParamsChanged(this);
        videoPlayer.setDecoderLevers(experiments);

        wfbLink = new WfbNgLink(this);
        wfbLink.SetWfbNGStatsChanged(this);
        wfbLinkManager = new WfbLinkManager(this, this, wfbLink);
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (xr == null) return;
        if (Build.VERSION.SDK_INT >= 33) {
            registerReceiver(wfbLinkManager, WfbLinkManager.usbIntentFilter(), RECEIVER_NOT_EXPORTED);
        } else {
            registerReceiver(wfbLinkManager, WfbLinkManager.usbIntentFilter());
        }
        wfbLinkManager.setChannel(VideoActivity.getChannel(this));
        wfbLinkManager.setBandwidth(VideoActivity.getBandwidth(this));
        wfbLinkManager.refreshAdapters();
        wfbLinkManager.startAdapters();
        if (!WfbServiceControl.startVpn(this, false)) {
            onLinkStatus("VPN not granted - start PixelPilot in 2D once to allow it");
        }
        ui.post(statsTick);
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (xr == null) return;
        ui.removeCallbacks(statsTick);
        try {
            unregisterReceiver(wfbLinkManager);
        } catch (IllegalArgumentException ignored) {
        }
        wfbLinkManager.stopAdapters();
        WfbServiceControl.stopVpn(this);
    }

    @Override
    protected void onDestroy() {
        destroying = true;
        detachVideo();          // stop writing before the session ends (no callback round-trip)
        if (xr != null) xr.stop();
        super.onDestroy();
    }

    // ---- XR session (XR thread) ------------------------------------------------------------

    @Override
    public void onSessionEvent(XrBridge.SessionEvent event) {
        switch (event) {
            case ACTIVE:
                ui.post(this::attachVideo);
                break;
            case INACTIVE:
                if (destroying) return; // onDestroy already detached; the UI thread is joining us
                CountDownLatch done = new CountDownLatch(1);
                ui.post(() -> {
                    detachVideo();
                    done.countDown();
                });
                try {
                    if (!done.await(INACTIVE_TIMEOUT_MS, TimeUnit.MILLISECONDS)) {
                        Log.w(TAG, "video detach timed out before xrEndSession");
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
                break;
            case EXITING:
                ui.post(this::finish);
                break;
        }
    }

    private void attachVideo() {
        if (videoAttached || destroying || xr == null) return;
        videoPlayer.addAndStartDecoderReceiver(xr.videoSurface(), 0);
        videoPlayer.start();
        videoAttached = true;
        Log.i(TAG, "video attached to the compositor surface");
    }

    private void detachVideo() {
        if (!videoAttached) return;
        videoPlayer.stopAndRemoveReceiverDecoder(0);
        videoAttached = false;
        Log.i(TAG, "video detached");
    }

    private void applyLayout() {
        xr.setLayout(LayerLayout.compute(videoW, videoH, experiments.xrFovDeg, LayerLayout.DEFAULT_DISTANCE_M,
                experiments.xrLayerShape == LatencyExperiments.LayerShape.CYLINDER, experiments.xrFlipVertical));
    }

    // ---- callbacks from the player / link (background threads) ------------------------------

    @Override
    public void onVideoRatioChanged(int w, int h) {
        videoW = w;
        videoH = h;
        ui.post(() -> {
            if (xr != null) applyLayout();
        });
    }

    @Override
    public void onDecodingInfoChanged(DecodingInfo decodingInfo) {
        lastDecoding = decodingInfo;
    }

    @Override
    public void onWfbNgStatsChanged(WfbNGStats data) {
        lastLink = data;
    }

    @Override
    public void onLinkStatus(String message) {
        linkStatus = message;
    }

    @Override
    public void onUdpFallbackAddress(String udpUrl) {
        linkStatus = "No adapter - push RTP to " + udpUrl;
    }

    private String[] statsLines() {
        XrBridge.Info info = xr.info();
        DecodingInfo d = lastDecoding;
        WfbNGStats l = lastLink;
        return new String[]{
                String.format(Locale.US, "XR %s Hz (req %.0f)  comp GPU %s ms  drop %s",
                        num(info.refreshHz), info.requestedHz, num(info.compositorGpuMs), num(info.droppedFrames)),
                d == null ? "video: waiting for stream"
                        : String.format(Locale.US, "%dx%d  %.0f fps  %.1f Mbit/s", videoW, videoH, d.currentFPS,
                        d.currentKiloBitsPerSecond / 1000f),
                d == null ? "" : String.format(Locale.US, "decode %.2f ms  parse %.2f ms  wait %.2f ms",
                        d.avgTotalDecodingTime_ms, d.avgParsingTime_ms, d.avgWaitForInputBTime_ms),
                "dec: " + videoPlayer.getDecoderSummary(),
                "exp: " + experiments.summary(),
                l == null ? "link: no stats" : String.format(Locale.US, "link: rssi %d  lost %d  fec %d  bad %d",
                        l.avg_rssi, l.count_p_lost, l.count_p_fec_recovered, l.count_p_bad),
                linkStatus,
        };
    }

    private static String num(float v) {
        return v < 0 ? "n/a" : String.format(Locale.US, "%.1f", v);
    }
}
```

- [ ] **Step 3: manifest** — inside `<application>` of `app/src/main/AndroidManifest.xml`:
```xml
        <meta-data android:name="com.oculus.supportedDevices" android:value="quest2|questpro|quest3|quest3s" />

        <activity
            android:name=".XrVideoActivity"
            android:exported="true"
            android:launchMode="singleInstance"
            android:taskAffinity="com.openipc.pixelpilot.xr"
            android:screenOrientation="landscape"
            android:configChanges="density|keyboard|keyboardHidden|navigation|orientation|screenLayout|screenSize|uiMode"
            android:theme="@android:style/Theme.Black.NoTitleBar.Fullscreen">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="org.khronos.openxr.intent.category.IMMERSIVE_HMD" />
                <category android:name="com.oculus.intent.category.VR" />
            </intent-filter>
            <meta-data android:name="com.oculus.vr.application.type" android:value="openxr" />
        </activity>
```

- [ ] **Step 4: 2D menu** — in `VideoActivity.setupVideoSubMenu`, before the "Latency experiments" submenu:
```java
        MenuItem launchXr = videoMenu.add("Launch XR (Quest)");
        launchXr.setOnMenuItemClickListener(item -> {
            Intent xr = new Intent(this, XrVideoActivity.class);
            xr.setAction(Intent.ACTION_MAIN);
            xr.addCategory("org.khronos.openxr.intent.category.IMMERSIVE_HMD");
            startActivity(xr);
            return true;
        });
```
and inside the "Latency experiments" submenu after the decoder toggles:
```java
        SubMenu refresh = experiments.addSubMenu("XR refresh: " + ex.xrRefreshHz + " Hz");
        for (int hz : LatencyExperiments.SUPPORTED_REFRESH_HZ) {
            refresh.add(hz + " Hz").setOnMenuItemClickListener(i -> {
                putXrPref(e -> e.putInt(LatencyExperiments.KEY_XR_REFRESH_HZ, hz));
                return true;
            });
        }
        SubMenu fov = experiments.addSubMenu("XR size: " + Math.round(ex.xrFovDeg) + " deg");
        for (int deg : new int[]{40, 50, 60, 70, 80, 90}) {
            fov.add(deg + " deg").setOnMenuItemClickListener(i -> {
                putXrPref(e -> e.putFloat(LatencyExperiments.KEY_XR_FOV_DEG, deg));
                return true;
            });
        }
        addXrToggle(experiments, "XR: curved layer", ex.xrLayerShape == LatencyExperiments.LayerShape.CYLINDER,
                on -> e -> e.putString(LatencyExperiments.KEY_XR_LAYER_SHAPE,
                        (on ? LatencyExperiments.LayerShape.CYLINDER : LatencyExperiments.LayerShape.QUAD).prefValue()));
        addXrToggle(experiments, "XR: present by timestamp", ex.xrUseTimestamps,
                on -> e -> e.putBoolean(LatencyExperiments.KEY_XR_USE_TIMESTAMPS, on));
        addXrToggle(experiments, "XR: CPU/GPU sustained high", ex.xrPerfSustainedHigh,
                on -> e -> e.putBoolean(LatencyExperiments.KEY_XR_PERF_SUSTAINED_HIGH, on));
        addXrToggle(experiments, "XR: flip image vertically", ex.xrFlipVertical,
                on -> e -> e.putBoolean(LatencyExperiments.KEY_XR_FLIP_VERTICAL, on));
```
with helpers (XR prefs are read when the XR activity starts, so no restart):
```java
    private void putXrPref(java.util.function.Consumer<SharedPreferences.Editor> write) {
        SharedPreferences.Editor e = getSharedPreferences(LatencyExperiments.PREFS_NAME, MODE_PRIVATE).edit();
        write.accept(e);
        e.apply();
    }

    private void addXrToggle(SubMenu menu, String title, boolean current,
                             java.util.function.Function<Boolean, java.util.function.Consumer<SharedPreferences.Editor>> writer) {
        MenuItem item = menu.add(title);
        item.setCheckable(true);
        item.setChecked(current);
        item.setOnMenuItemClickListener(i -> {
            boolean on = !i.isChecked();
            i.setChecked(on);
            putXrPref(writer.apply(on));
            return true;
        });
    }
```

- [ ] **Step 5: build + lint + commit**

Run: `./gradlew --no-daemon assembleDebug lintDebug` → SUCCESS (no new lint errors in the touched files).
```bash
git add app/src/main/java/com/openipc/pixelpilot/XrVideoActivity.java app/src/main/java/com/openipc/pixelpilot/XrStatsRenderer.java app/src/main/AndroidManifest.xml app/src/main/java/com/openipc/pixelpilot/VideoActivity.java
git commit -m "feat(xr): immersive XrVideoActivity with stats panel and latency experiment menu"
```

---

### Task 7: Docs, spec sync, measurement runbook, push

**Files:**
- Create: `docs/xr-quest.md` (build, install, smoke checklist, measurement matrix, known unknowns)
- Modify: `README.md` (short "Quest native XR mode (experimental)" section linking `docs/xr-quest.md`)
- Modify: `docs/superpowers/specs/2026-09-26-quest-openxr-viewer-design.md` (layout math lives in `app/xr` `LayerLayout`; distance fixed at 2 m, `xr_distance_m` dropped; session-state mapping VISIBLE/FOCUSED)

- [ ] **Step 1:** write `docs/xr-quest.md` with: build command (Global Constraints), `adb install -r app/build/outputs/apk/debug/app-debug.apk`, smoke checklist (spec §5), `adb logcat -s PixelPilotXr pixelpilot-xr pixelpilot` expectations ("OpenXR ready", "requested 120 Hz -> 120 Hz", "video attached"), measurement matrix {2D, XR} × {72, 90, 120} × each decoder lever, N ≥ 25, photodiode+OWON (not the LDR rig), and the open questions (does Horizon honour USE_TIMESTAMPS off = mailbox; is the image upside-down with flip off; does `c2.qti.*.low_latency` exist on XR2).
- [ ] **Step 2:** README section + spec sync edits.
- [ ] **Step 3:** full verification: WSL gtests, `./gradlew --no-daemon test assembleDebug lintDebug`.
- [ ] **Step 4:** commit docs; `git push -u origin xr-native` (fork `tmariovlad/PixelPilot`; no PR to OpenIPC).

---

## Self-review notes

- Spec coverage: §2 units → Tasks 1–6 (XrLayout moved into `app/xr` as `LayerLayout`, recorded in Task 7 spec sync); §3 lifecycle/errors → Task 5 (states, no fallback, refresh fallback, resize, flip) + Task 6 (activity, INACTIVE latch, destroy ordering); §4 levers → Tasks 1, 3, 6 (menu); §5 tests → Tasks 1, 2, 3, 5 + Task 7 docs; §6 risks → Task 7 docs.
- Type consistency checked: `LatencyExperiments.xrRefreshHz` is `int` and `XrBridge.start(..., int refreshHz, ...)` widens to `float` for the native call; `SessionEvent` ordinals match between `XrRuntime.h` and `XrBridge.java`; `nativeSetLayout` array length 11 matches `XrBridge.setLayout`.
