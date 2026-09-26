package com.openipc.pixelpilot;

import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.PorterDuff;
import android.graphics.Typeface;
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
        text.setTypeface(Typeface.MONOSPACE);
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
            try {
                surface.unlockCanvasAndPost(canvas);
            } catch (RuntimeException e) {
                // surface abandoned between lock and unlock while the session ends
            }
        }
    }
}
