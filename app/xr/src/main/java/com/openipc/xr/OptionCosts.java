package com.openipc.xr;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * The measured cost of each option the headset menu offers (res/raw/option_costs.json, canonical; the table for humans,
 * docs/xr/option-costs.md, is generated from it). One place per number: the G2G/FOV of the presets the air unit lists
 * (VMODE1 {@code list}) live only there, so an entry for such a preset may not carry them. The menu joins by a stable
 * key: the preset id, a lever's pref name, or a link combination. How an option is applied (live, relaunch, air) is the
 * menu's own registry, not this file. Parse once; immutable.
 */
public final class OptionCosts {
    public static final int SCHEMA = 1;
    public static final Set<String> GROUPS = Collections.unmodifiableSet(new HashSet<>(Arrays.asList(
            "mode", "bitrate", "link", "mcs", "fec", "streams", "txpower", "channel", "lever", "codec")));
    public static final Set<String> TAGS = Collections.unmodifiableSet(new HashSet<>(Arrays.asList(
            "PROVEN", "INFERRED", "SPECULATION")));
    static final Set<String> COST_FIELDS = Collections.unmodifiableSet(new HashSet<>(Arrays.asList(
            "g2g_ms", "fov", "delta_ms", "fps", "post_fec_pct", "range_note")));
    public static final int NOTE_MAX = 24;
    private static final Pattern DATE = Pattern.compile("\\d{4}-\\d{2}-\\d{2}");

    /** A measured value: one number (lo == hi) or the spread [lo, hi] over runs. Unknown = both NaN. */
    public static final class Range {
        static final Range NONE = new Range(Double.NaN, Double.NaN);
        public final double lo, hi;

        Range(double lo, double hi) {
            this.lo = lo;
            this.hi = hi;
        }

        public boolean known() {
            return !Double.isNaN(lo);
        }

        /** A number, a [lo, hi] array, or absent. */
        static Range of(Object v, String what) throws JSONException {
            if (v == null) return NONE;
            if (v instanceof Number) {
                double d = ((Number) v).doubleValue();
                return new Range(d, d);
            }
            if (v instanceof JSONArray) {
                JSONArray a = (JSONArray) v;
                require(a.length() == 2, what + ": a range is [lo, hi], got " + a);
                double lo = a.getDouble(0), hi = a.getDouble(1);
                require(lo <= hi, what + ": range [lo, hi] needs lo <= hi, got " + a);
                return new Range(lo, hi);
            }
            throw new IllegalArgumentException(what + ": expected a number or a range [lo, hi], got " + v);
        }
    }

    /** One option. Values not measured are {@link Range#NONE}; texts not given are empty. */
    public static final class Option {
        public final String id, group, label, key, conditions, note, tag, source, measured;
        public final Range g2g;                        // total glass-to-glass, ms
        public final String fov;                       // sensor share, e.g. "99x98"
        public final Range deltaMean, deltaP95;        // latency against deltaVs, ms
        public final String deltaVs;                   // the option id the delta is measured against
        public final Range fps, fpsOff, fpsOn;         // decoded fps; off/on for a lever
        public final Range postFec, postFecOff, postFecOn;  // post-FEC packet loss, %
        public final String rangeNote;

        Option(JSONObject o) throws JSONException {
            id = o.getString("id");
            group = o.getString("group");
            label = o.getString("label");
            key = o.getString("key");
            conditions = o.optString("conditions", "");
            note = o.optString("note", "");
            tag = o.getString("tag");
            source = o.getString("source");
            measured = o.getString("measured");
            JSONObject c = o.getJSONObject("costs");
            g2g = Range.of(c.opt("g2g_ms"), id + " g2g_ms");
            fov = c.optString("fov", "");
            JSONObject d = c.optJSONObject("delta_ms");
            deltaMean = d == null ? Range.NONE : Range.of(d.opt("mean"), id + " delta_ms.mean");
            deltaP95 = d == null ? Range.NONE : Range.of(d.opt("p95"), id + " delta_ms.p95");
            deltaVs = d == null ? "" : d.optString("vs", "");
            JSONObject f = c.optJSONObject("fps");
            fps = f == null ? Range.of(c.opt("fps"), id + " fps") : Range.NONE;
            fpsOff = f == null ? Range.NONE : Range.of(f.opt("off"), id + " fps.off");
            fpsOn = f == null ? Range.NONE : Range.of(f.opt("on"), id + " fps.on");
            JSONObject p = c.optJSONObject("post_fec_pct");
            postFec = p == null ? Range.of(c.opt("post_fec_pct"), id + " post_fec_pct") : Range.NONE;
            postFecOff = p == null ? Range.NONE : Range.of(p.opt("off"), id + " post_fec_pct.off");
            postFecOn = p == null ? Range.NONE : Range.of(p.opt("on"), id + " post_fec_pct.on");
            rangeNote = c.optString("range_note", "");
        }

        /** Carries a number the air unit's list owns for its presets. */
        public boolean hasListOwnedCost() {
            return g2g.known() || !fov.isEmpty();
        }

        boolean hasAnyValue() {
            for (Range r : new Range[]{g2g, deltaMean, deltaP95, fps, fpsOff, fpsOn, postFec, postFecOff, postFecOn}) {
                if (r.known()) return true;
            }
            return !fov.isEmpty() || !rangeNote.isEmpty();
        }
    }

    private final List<Option> options;
    private final List<String> listPresets;
    private final Map<String, Option> byId;

    private OptionCosts(List<Option> options, List<String> listPresets) {
        this.options = Collections.unmodifiableList(options);
        this.listPresets = Collections.unmodifiableList(listPresets);
        Map<String, Option> m = new LinkedHashMap<>();
        for (Option o : options) m.put(o.id, o);
        byId = m;
    }

    /** Parses and validates; IllegalArgumentException names the first rule broken. */
    public static OptionCosts parse(String json) {
        try {
            JSONObject root = new JSONObject(json);
            require(root.getInt("schema") == SCHEMA, "schema " + root.getInt("schema") + " != " + SCHEMA);
            List<String> presets = new ArrayList<>();
            JSONArray lp = root.getJSONArray("list_presets");
            for (int i = 0; i < lp.length(); i++) presets.add(lp.getString(i));
            List<Option> out = new ArrayList<>();
            Set<String> ids = new HashSet<>();
            JSONArray arr = root.getJSONArray("options");
            for (int i = 0; i < arr.length(); i++) {
                JSONObject raw = arr.getJSONObject(i);
                Option o = new Option(raw);
                validate(o, raw.getJSONObject("costs"), presets);
                require(ids.add(o.id), "duplicate id " + o.id);
                out.add(o);
            }
            return new OptionCosts(out, presets);
        } catch (JSONException e) {
            throw new IllegalArgumentException("bad option_costs json: " + e.getMessage(), e);
        }
    }

    private static void validate(Option o, JSONObject costs, List<String> presets) {
        require(GROUPS.contains(o.group), o.id + ": unknown group " + o.group);
        require(o.id.startsWith(o.group + "."), o.id + ": id must start with its group " + o.group);
        require(!o.label.isEmpty() && !o.key.isEmpty(), o.id + ": label and key are required");
        require(TAGS.contains(o.tag), o.id + ": tag " + o.tag + " not in " + TAGS);
        require(!o.source.trim().isEmpty(), o.id + ": source is required");
        require(DATE.matcher(o.measured).matches(), o.id + ": measured must be YYYY-MM-DD, got " + o.measured);
        require(o.note.length() <= NOTE_MAX, o.id + ": note longer than " + NOTE_MAX);
        for (Iterator<String> it = costs.keys(); it.hasNext(); ) {
            String k = it.next();
            require(COST_FIELDS.contains(k), o.id + ": unknown cost field " + k);
        }
        require(o.hasAnyValue(), o.id + ": no measured value");
        if (o.group.equals("mode") && presets.contains(o.key)) {
            require(!o.hasListOwnedCost(), o.id + ": g2g/fov of " + o.key + " belong to the air's list, not here");
        }
    }

    private static void require(boolean ok, String why) {
        if (!ok) throw new IllegalArgumentException(why);
    }

    public List<Option> options() {
        return options;
    }

    /** Preset ids whose G2G/FOV come from the air unit's list (never from this table). */
    public List<String> listPresets() {
        return listPresets;
    }

    public Option byId(String id) {
        return byId.get(id);
    }

    /** The option of a group with this key (a preset id, a lever's pref name, a link combination), or null. */
    public Option byKey(String group, String key) {
        for (Option o : options) if (o.group.equals(group) && o.key.equals(key)) return o;
        return null;
    }
}
