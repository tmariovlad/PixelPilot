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

    @Test public void statsPanelHangsRightUnderTheVideo() {
        LayerLayout l = LayerLayout.compute(1280, 720, 60f, 2f, false, true);
        float statsTop = l.statsY + l.statsHeightM / 2f;
        assertEquals(-l.videoHeightM / 2f, statsTop, EPS);
        assertEquals(l.statsWidthM / 4f, l.statsHeightM, EPS);   // 1024x256 image aspect
        assertEquals(l.videoWidthM / 2f, l.statsWidthM, EPS);
        assertEquals(l.videoZ, l.statsZ, EPS);
    }

    @Test public void alertPanelSitsInsideTheVideosLowerPart() {
        for (float fov = 40f; fov <= 90f; fov += 10f) {
            for (boolean cyl : new boolean[]{false, true}) {
                LayerLayout l = LayerLayout.compute(1920, 1080, fov, 2f, cyl, true, true);
                float top = l.statsY + l.statsHeightM / 2f, bottom = l.statsY - l.statsHeightM / 2f;
                assertTrue("fov " + fov, bottom > -l.videoHeightM / 2f);   // inside the video, above its edge
                assertTrue("fov " + fov, top < 0f);                        // lower half only
            }
        }
    }

    @Test public void alertPanelIsCloserToTheLineOfSight() {
        for (float fov = 40f; fov <= 90f; fov += 10f) {
            LayerLayout normal = LayerLayout.compute(1920, 1080, fov, 2f, false, true, false);
            LayerLayout alert = LayerLayout.compute(1920, 1080, fov, 2f, false, true, true);
            double normalDeg = Math.toDegrees(Math.atan(-normal.statsY / 2f));
            double alertDeg = Math.toDegrees(Math.atan(-alert.statsY / 2f));
            assertTrue("fov " + fov, alertDeg < normalDeg);
            assertTrue("fov " + fov + ": " + alertDeg, alertDeg < 21.0);
        }
    }

    @Test public void sixArgumentOverloadIsTheNormalPlacement() {
        LayerLayout a = LayerLayout.compute(1280, 720, 60f, 2f, false, true);
        LayerLayout b = LayerLayout.compute(1280, 720, 60f, 2f, false, true, false);
        assertEquals(a.statsY, b.statsY, EPS);
    }
    // The menu layer (docs/xr/menu-design.md §2): right of the video, never past MENU_EDGE_DEG, facing the eye.
    @Test public void menuSitsRightOfTheVideoWithoutOverlapAtTheDefaultFov() {
        LayerLayout l = LayerLayout.compute(1920, 1080, 60f, 2f, false, true);
        float menuLeft = l.menuX - l.menuWidthM / 2f;
        assertTrue("left edge " + menuLeft, menuLeft >= l.videoWidthM / 2f - EPS);
        assertEquals(0f, l.menuY, EPS);
        assertEquals((float) LayerLayout.MENU_IMAGE_H / LayerLayout.MENU_IMAGE_W, l.menuHeightM / l.menuWidthM, 1e-4f);
    }

    @Test public void menuRightEdgeStaysInsideTheViewAtAWideFov() {
        for (boolean cyl : new boolean[]{false, true}) {
            LayerLayout l = LayerLayout.compute(1920, 1080, 100f, 2f, cyl, true);
            double edgeDeg = Math.toDegrees(Math.atan2(l.menuX + l.menuWidthM / 2f, -l.menuZ));
            assertTrue("edge " + edgeDeg, edgeDeg <= LayerLayout.MENU_EDGE_DEG + 0.01);
        }
    }

    @Test public void menuTurnsTowardTheEye() {
        LayerLayout l = LayerLayout.compute(1920, 1080, 60f, 2f, false, true);
        assertTrue(l.menuX > 0);
        assertEquals(-Math.atan2(l.menuX, -l.menuZ), l.menuYawRad, 1e-4);
    }
}
