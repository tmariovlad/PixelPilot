package com.openipc.xr;

import static org.junit.Assert.*;
import org.junit.Test;

public class PanelTextTest {
    @Test public void shortLinesPassUnchanged() {
        assertArrayEquals(new String[]{"abc", "de"}, PanelText.fit(new String[]{"abc", "de"}, 10));
    }

    @Test public void emptyAndNullLinesAreDropped() {
        assertArrayEquals(new String[]{"a", "b"}, PanelText.fit(new String[]{"a", "", null, "b"}, 10));
    }

    @Test public void longLinesEndInAnEllipsisWithinTheWidth() {
        String[] r = PanelText.fit(new String[]{"0123456789ABCDEF"}, 10);
        assertEquals(10, r[0].length());
        assertEquals("012345678" + PanelText.ELLIPSIS, r[0]);
    }

    @Test public void exactWidthIsNotCut() {
        assertEquals("0123456789", PanelText.fit(new String[]{"0123456789"}, 10)[0]);
    }

    @Test public void degenerateWidthStillReturnsSomething() {
        assertEquals(PanelText.ELLIPSIS, PanelText.fit(new String[]{"abc"}, 0)[0]);
    }
}
