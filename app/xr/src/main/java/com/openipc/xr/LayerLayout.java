package com.openipc.xr;

/**
 * Pure geometry of the head-locked layers: the video (quad or cylinder), the stats panel, and the menu (shown only
 * while it is open).
 * Angular size comes from the FOV preference; the panel keeps the stats image aspect.
 *
 * <p>Normally the panel hangs right under the video. While the video is not OK ({@code alert}), it moves up over
 * the lower part of the video, so a NO SIGNAL headline sits where the pilot is looking and a frozen last frame
 * cannot pass for live video (audit X10/X11, docs/xr/research/2026-09-27-xr-ux-audit.md).
 */
public final class LayerLayout {
    // 1024 px wide at 28 px monospace fits ~60 columns (512 px at 21 px fitted ~39, which clipped most lines)
    public static final int STATS_IMAGE_W = 1024;
    public static final int STATS_IMAGE_H = 256;
    public static final float DEFAULT_DISTANCE_M = 2f;
    private static final int FALLBACK_W = 1280;
    private static final int FALLBACK_H = 720;
    private static final float STATS_WIDTH_FRACTION = 0.5f;
    /** Alert placement: the panel's bottom edge this far (fraction of the video height) above the video's bottom. */
    private static final float ALERT_LIFT_FRACTION = 0.06f;
    /** The menu layer (docs/xr/menu-design.md): 1024 px wide at 28 px monospace = the renderer's 56 columns, ~16 lines. */
    public static final int MENU_IMAGE_W = 1024;
    public static final int MENU_IMAGE_H = 640;
    /** Menu width per metre of distance (0.9 m at 2 m, ~25 deg): at the default 60 deg FOV it then fits between the video and MENU_EDGE_DEG. */
    private static final float MENU_WIDTH_PER_M = 0.45f;
    /** Gap between the video's right edge and the menu, per metre of distance. */
    private static final float MENU_GAP_PER_M = 0.02f;
    /** The menu's right edge never goes further right than this from straight ahead, so it stays in view. */
    public static final float MENU_EDGE_DEG = 47f;

    public final boolean cylinder;
    public final boolean flip;
    public final float videoWidthM, videoHeightM, videoZ;
    public final float cylRadius, cylAngleRad, cylAspect;
    public final float statsWidthM, statsHeightM, statsY, statsZ;
    /** The menu quad: size, centre, and the yaw that turns it toward the eye. */
    public final float menuWidthM, menuHeightM, menuX, menuY, menuZ, menuYawRad;
    public final int imageW, imageH;

    private LayerLayout(boolean cylinder, boolean flip, float videoWidthM, float videoHeightM, float videoZ,
                        float cylRadius, float cylAngleRad, float cylAspect, float statsWidthM,
                        float statsHeightM, float statsY, float statsZ, float menuWidthM, float menuHeightM,
                        float menuX, float menuZ, int imageW, int imageH) {
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
        this.menuWidthM = menuWidthM;
        this.menuHeightM = menuHeightM;
        this.menuX = menuX;
        this.menuY = 0f;
        this.menuZ = menuZ;
        this.menuYawRad = (float) -Math.atan2(menuX, -menuZ);
        this.imageW = imageW;
        this.imageH = imageH;
    }

    public static LayerLayout compute(int videoW, int videoH, float fovDeg, float distanceM,
                                      boolean cylinder, boolean flip) {
        return compute(videoW, videoH, fovDeg, distanceM, cylinder, flip, false);
    }

    public static LayerLayout compute(int videoW, int videoH, float fovDeg, float distanceM,
                                      boolean cylinder, boolean flip, boolean alert) {
        final int w = (videoW > 0 && videoH > 0) ? videoW : FALLBACK_W;
        final int h = (videoW > 0 && videoH > 0) ? videoH : FALLBACK_H;
        final float aspect = (float) w / (float) h;
        final float fovRad = (float) Math.toRadians(fovDeg);
        final float width = cylinder ? distanceM * fovRad : 2f * distanceM * (float) Math.tan(fovRad / 2f);
        final float height = width / aspect;
        final float statsW = width * STATS_WIDTH_FRACTION;
        final float statsH = statsW * STATS_IMAGE_H / STATS_IMAGE_W;
        final float statsY = alert
                ? -height / 2f + height * ALERT_LIFT_FRACTION + statsH / 2f   // over the video's lower part
                : -(height / 2f + statsH / 2f);                               // right under the video
        // Menu: right of the video's right edge (for a cylinder, the arc's x extent), clamped so its right edge stays
        // within MENU_EDGE_DEG; at wide FOVs it then overlaps the video's right edge rather than leaving the view.
        final float videoHalfX = cylinder ? distanceM * (float) Math.sin(Math.min(fovRad, (float) Math.PI) / 2f) : width / 2f;
        final float menuW = MENU_WIDTH_PER_M * distanceM;
        final float menuH = menuW * MENU_IMAGE_H / MENU_IMAGE_W;
        final float edgeX = distanceM * (float) Math.tan(Math.toRadians(MENU_EDGE_DEG));
        final float menuX = Math.min(videoHalfX + MENU_GAP_PER_M * distanceM + menuW / 2f, edgeX - menuW / 2f);
        return new LayerLayout(cylinder, flip, width, height, -distanceM, distanceM, fovRad, aspect,
                statsW, statsH, statsY, -distanceM, menuW, menuH, menuX, -distanceM, w, h);
    }
}
