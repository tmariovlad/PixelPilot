package com.openipc.pixelpilot;

import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.PorterDuff;
import android.graphics.Typeface;
import android.view.Surface;

import com.openipc.xr.menu.MenuLine;

import java.util.List;

/**
 * Draws the menu's lines (MenuRenderer) into the menu layer's compositor-owned surface (1024x640,
 * LayerLayout.MENU_IMAGE_*): a title band, a highlight bar on the selected line, greyed-out unavailable lines and an
 * amber hint line. UI thread, only while the menu is open; never on the video path.
 */
final class XrMenuSurfaceRenderer {
    private static final float TEXT_PX = 28f;
    private static final float LINE_PX = 36f;
    private static final float MARGIN_PX = 16f;
    private static final int BACKGROUND = 0xD0101418;
    private static final int TITLE_BAND = 0xFF263238;
    private static final int HIGHLIGHT_BAND = 0xFF37474F;
    private static final int TITLE_TEXT = 0xFF80DEEA;
    private static final int DISABLED_TEXT = 0xFF7A7A7A;
    private static final int HINT_TEXT = 0xFFFFC107;
    private final Surface surface;
    private final Paint text = new Paint(Paint.ANTI_ALIAS_FLAG);
    private final Paint band = new Paint();

    XrMenuSurfaceRenderer(Surface surface) {
        this.surface = surface;
        text.setTextSize(TEXT_PX);
        text.setTypeface(Typeface.MONOSPACE);
    }

    void draw(List<MenuLine> lines) {
        if (surface == null || !surface.isValid()) return;
        Canvas canvas;
        try {
            canvas = surface.lockHardwareCanvas();
        } catch (RuntimeException e) {
            return; // surface abandoned while the session ends
        }
        try {
            canvas.drawColor(BACKGROUND, PorterDuff.Mode.SRC);
            float top = MARGIN_PX / 2f;
            for (MenuLine line : lines) {
                if (top + LINE_PX > canvas.getHeight()) break;
                int bandColor = line.style == MenuLine.Style.TITLE ? TITLE_BAND
                        : line.style == MenuLine.Style.HIGHLIGHT ? HIGHLIGHT_BAND : 0;
                if (bandColor != 0) {
                    band.setColor(bandColor);
                    canvas.drawRect(0, top, canvas.getWidth(), top + LINE_PX, band);
                }
                text.setColor(color(line.style));
                text.setTypeface(line.style == MenuLine.Style.TITLE || line.style == MenuLine.Style.HIGHLIGHT
                        ? Typeface.create(Typeface.MONOSPACE, Typeface.BOLD) : Typeface.MONOSPACE);
                canvas.drawText(line.text, MARGIN_PX, top + LINE_PX - 10f, text);
                top += LINE_PX;
            }
        } finally {
            try {
                surface.unlockCanvasAndPost(canvas);
            } catch (RuntimeException e) {
                // surface abandoned between lock and unlock while the session ends
            }
        }
    }

    private static int color(MenuLine.Style s) {
        switch (s) {
            case TITLE: return TITLE_TEXT;
            case DISABLED: return DISABLED_TEXT;
            case HINT: return HINT_TEXT;
            default: return Color.WHITE;
        }
    }
}
