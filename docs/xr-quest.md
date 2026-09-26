# Quest native XR mode (experimental)

A second activity, `XrVideoActivity`, shows the stream **inside an OpenXR session** instead of as a flat
2D panel. MediaCodec decodes straight into a compositor-owned Android surface
(`XR_KHR_android_surface_swapchain`) shown as a head-locked layer, so there is no app render pass and no
Android window compositing between the decoder and the headset compositor.

Design and reasoning: [spec](superpowers/specs/2026-09-26-quest-openxr-viewer-design.md) ·
[implementation plan](superpowers/plans/2026-09-26-quest-openxr-viewer.md).

> Status (2026-09-26): builds and passes its unit tests. **Not yet run on a headset** — nothing below about
> behaviour on Quest is verified until the smoke checklist has been done.

## Build and install

```bash
export JAVA_HOME='C:\Program Files\Java\jdk-17'      # JDK 17; newer JDKs break AGP 8.5
# local.properties: sdk.dir=C:/Users/<you>/AppData/Local/Android/Sdk   (forward slashes)
./gradlew assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

Host unit tests for the decoder helpers (`AccessUnitAssembler`, `DecoderLevers`, `BufferedPacketQueue`)
need a Linux toolchain with CMake ≥ 3.14, e.g. WSL:

```bash
cmake -S app/videonative/src/main/cpp/tests -B /tmp/ppxr-tests && cmake --build /tmp/ppxr-tests -j8 \
  && (cd /tmp/ppxr-tests && ctest --output-on-failure)
```

JVM tests: `./gradlew :app:videonative:testDebugUnitTest :app:xr:testDebugUnitTest`.

## Use

1. Start PixelPilot normally once (2D) so the VPN permission and `gs.key` are in place.
2. Plug the RTL8812AU into the Quest's USB-C.
3. Menu → **Video → Launch XR (Quest)**. The 2D activity pauses (it releases the adapter), the XR
   activity takes it over.
4. Video appears as a head-locked screen with a stats panel below it. Leave with the Meta button.

Everything tunable lives in **Video → Latency experiments** (single source:
`app/videonative/.../LatencyExperiments.java`):

| Item | Pref key | Default | Applies |
|---|---|---|---|
| Decoder: decode order (qti) | `dec_picture_order` | off | app restart (2D and XR) |
| Decoder: max operating rate | `dec_operating_rate` | off | app restart |
| Decoder: low-latency component | `dec_prefer_low_latency_component` | off | app restart |
| Decoder: whole access units | `au_aggregation` | off | app restart |
| XR refresh | `xr_refresh_hz` | 120 | next XR start |
| XR size | `xr_fov_deg` | 60° | next XR start |
| XR: curved layer | `xr_layer_shape` | quad | next XR start |
| XR: present by timestamp | `xr_use_timestamps` | off | next XR start |
| XR: CPU/GPU sustained high | `xr_perf_sustained_high` | on | next XR start |
| XR: flip image vertically | `xr_flip_vertical` | on | next XR start |

The existing **Low latency** item (`low_latency_decoder`, default on) is unchanged.
A decoder that rejects the extra decoder keys is reconfigured with the base set; the stats panel line
`dec:` shows the codec name and the levers it actually accepted.

## Smoke checklist (first run on a headset)

`adb logcat -s PixelPilotXr pixelpilot-xr pixelpilot`:

- [ ] `OpenXR ready: N extensions enabled` — if instead `OpenXR runtime lacks XR_KHR_android_surface_swapchain`, the XR mode cannot work on this runtime.
- [ ] `requested 120 Hz -> 120 Hz` and the panel's first line shows `XR 120.0 Hz`.
- [ ] `session state … -> 5` (FOCUSED) followed by `video attached to the compositor surface`.
- [ ] Video visible, **right way up** (if upside-down or mirrored: toggle *XR: flip image vertically*).
- [ ] Stats panel updates (~4 Hz), `dec:` line shows a codec name.
- [ ] Meta button → `video detached` before the session ends; back in → `video attached` again.
- [ ] Unplug / replug the adapter: panel shows the link status, video resumes.
- [ ] Exit and relaunch from the 2D menu twice (no crash, no "already started").

## Measuring (the point of this mode)

The ESP32 + LDR G2G rig does **not** work through HMD optics (the backlight flashes ~1 ms per frame).
Use a fast photodiode (BPW34 / OPT101) at the lens + scope, or native 480 fps slow motion. Protocol and
background: `c:/xampp/htdocs/ev300d/tasks/quest2-research-2026-09-26/01-latency-numbers-and-measurement.md`.

Matrix, same air unit and stream, N ≥ 25 per point, order shuffled:

- presentation: PixelPilot 2D vs XR
- refresh: 72 / 90 / 120 Hz (XR)
- each decoder lever on/off (one at a time, then the combination of the ones that helped)
- `xr_use_timestamps` on/off

Keep a lever's default on only after a measurement shows it helps; record results next to this file.

## Open questions (to settle on the device)

- Does the Horizon compositor treat the surface swapchain as replace-latest (mailbox) when
  `USE_TIMESTAMPS` is off, as the spec implies?
- Is the Android surface image upside-down without the vertical flip on current Horizon OS (CitraVR says yes)?
- Does the XR2 expose `c2.qti.{avc,hevc}.decoder.low_latency`, and does its Codec2 HAL honour
  `vendor.qti-ext-dec-picture-order.enable`? (The `dec:` line shows which component was created.)
- Do the Meta performance-metric paths return values on Quest 2 (`n/a` on the panel means no)?
