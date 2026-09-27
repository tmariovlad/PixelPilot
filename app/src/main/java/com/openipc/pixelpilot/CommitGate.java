package com.openipc.pixelpilot;

/**
 * When the app may confirm a mode switch to the air unit (docs/xr/presets-design.md, "Safety"): after the air reports
 * the new mode running ({@code phase=pending}), {@link #FRAMES} frames must be decoded at the new mode's size. The
 * size alone is not enough: two modes can share an encode size (848x480), and frames of the old stream would match.
 * UI thread only.
 */
final class CommitGate {
    static final int FRAMES = 30;

    private String token;
    private int width, height;
    private boolean armed;
    private int frames;

    /** An apply was accepted with {@code token}; the new mode decodes at {@code w} x {@code h}. */
    void expect(String token, int w, int h) {
        this.token = token;
        width = w;
        height = h;
        armed = false;
        frames = 0;
    }

    /** The air reported the new mode running and waiting for our commit. */
    void arm() {
        if (token != null) armed = true;
    }

    /** Frames decoded in one stats tick at the current video size. Returns the token once, when the commit is due. */
    String onFrames(int n, int w, int h) {
        if (token == null || !armed || w != width || h != height) return null;
        frames += n;
        if (frames < FRAMES) return null;
        String t = token;
        clear();
        return t;
    }

    void clear() {
        token = null;
        armed = false;
        frames = 0;
    }

    boolean waiting() {
        return token != null;
    }
}
