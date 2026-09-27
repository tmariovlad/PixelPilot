package com.openipc.pixelpilot;

import java.util.function.IntFunction;

/** What a {@link VmodeSession} needs from the transport ({@link VmodeClient}; a fake in tests). */
interface VmodeSender {
    /** Sends the request built for a fresh seq, with retries. Returns the seq. */
    int request(String verb, IntFunction<String> build);
}
