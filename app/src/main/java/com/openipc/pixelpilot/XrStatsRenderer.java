package com.openipc.pixelpilot;

import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.PorterDuff;
import android.graphics.Typeface;
import android.view.Surface;

import com.openipc.xr.PanelText;

/**
 * Draws the stats panel into its compositor-owned surface with a hardware canvas. When the video is not OK the
 * first line is a large headline on a coloured band (NO SIGNAL, WRONG KEY, ...), so a frozen last frame cannot pass
 * for live video. Runs on the UI thread at the stats tick rate, never on the video path.
 */
final class XrStatsRenderer {
    // Sized for the 1024x256 panel image (LayerLayout.STATS_IMAGE_*): ~60 columns, 6 lines under a headline.
    private static final float TEXT_PX = 28f;
    private static final float LINE_PX = 33f;
    private static final float HEADLINE_PX = 40f;
    private static final float HEADLINE_BAND_PX = 54f;
    private static final float MARGIN_PX = 12f;
    private static final int ALERT_RED = 0xE0C62828;
    private static final int ALERT_AMBER = 0xE0B26A00;
    private final Surface surface;
    private final Paint text = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint headline = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint band = new Paint();

    XrStatsRenderer(Surface surface) {
        this.surface = surface;
        text.setColor(Color.WHITE);
        text.setTextSize(TEXT_PX);
        text.setTypeface(Typeface.MONOSPACE);
        headline.setColor(Color.WHITE);
        headline.setTextSize(HEADLINE_PX);
        headline.setTypeface(Typeface.create(Typeface.MONOSPACE, Typeface.BOLD));
    }

    /** @param alert headline, empty when the video is OK; @param severe red (act now) instead of amber */
    void draw(String alert, boolean severe, String[] lines) {
        if (surface == null || !surface.isValid()) return;
        Canvas canvas;
        try {
            canvas = surface.lockHardwareCanvas();
        } catch (RuntimeException e) {
            return; // surface abandoned while the session ends
        }
        try {
            canvas.drawColor(0xB0000000, PorterDuff.Mode.SRC);
            float y = 0;
            if (alert != null && !alert.isEmpty()) {
                band.setColor(severe ? ALERT_RED : ALERT_AMBER);
                canvas.drawRect(0, 0, canvas.getWidth(), HEADLINE_BAND_PX, band);
                String h = PanelText.fit(new String[]{alert}, columns(canvas, headline))[0];
                canvas.drawText(h, MARGIN_PX, HEADLINE_BAND_PX - 14f, headline);
                y = HEADLINE_BAND_PX;
            }
            y += LINE_PX;
            for (String line : PanelText.fit(lines, columns(canvas, text))) {
                if (y > canvas.getHeight()) break;   // lowest-priority lines are last
                canvas.drawText(line, MARGIN_PX, y, text);
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

    private static int columns(Canvas canvas, Paint paint) {
        return (int) ((canvas.getWidth() - 2 * MARGIN_PX) / paint.measureText("M"));
    }
}
