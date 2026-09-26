package com.openipc.pixelpilot;

import android.content.Context;
import android.content.SharedPreferences;
import android.util.Base64;
import android.util.Log;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

/**
 * The wfb-ng ground-station key: kept in prefs, seeded from assets, and written to the app's files
 * dir where the native link reads it. Shared by every activity that starts a link.
 */
public final class GsKeyStore {
    private static final String TAG = "pixelpilot";
    private static final String PREFS = "general";
    private static final String KEY = "gs.key";

    private GsKeyStore() {}

    /** Seeds the prefs from the bundled default key if none was imported yet. */
    public static void ensureDefault(Context context) {
        if (get(context).length > 0) {
            Log.d(TAG, "gs.key already saved in preferences.");
            return;
        }
        try (InputStream in = context.getAssets().open(KEY)) {
            Log.d(TAG, "Importing default gs.key...");
            set(context, in);
        } catch (IOException e) {
            Log.e(TAG, "Failed to import default gs.key");
        }
    }

    public static byte[] get(Context context) {
        String pref = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY, "");
        return Base64.decode(pref, Base64.DEFAULT);
    }

    public static void set(Context context, InputStream inputStream) throws IOException {
        ByteArrayOutputStream result = new ByteArrayOutputStream();
        byte[] buffer = new byte[1024];
        int length;
        while ((length = inputStream.read(buffer)) != -1) {
            result.write(buffer, 0, length);
        }
        SharedPreferences.Editor editor = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit();
        editor.putString(KEY, Base64.encodeToString(result.toByteArray(), Base64.DEFAULT));
        editor.apply();
    }

    /** Writes the key where the native wfb-ng link reads it (Context.getFilesDir()/gs.key). */
    public static void copyToFiles(Context context) {
        File file = new File(context.getApplicationContext().getFilesDir(), KEY);
        byte[] keyBytes = get(context);
        Log.d(TAG, "Using gs.key:" + VideoActivity.bytesToHex(keyBytes) + "; Copying to" + file.getAbsolutePath());
        try (OutputStream out = new FileOutputStream(file)) {
            out.write(keyBytes, 0, keyBytes.length);
        } catch (IOException e) {
            Log.e(TAG, "Failed to copy gs.key", e);
        }
    }
}
