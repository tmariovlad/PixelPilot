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
