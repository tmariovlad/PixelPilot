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
