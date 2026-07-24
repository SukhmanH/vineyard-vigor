"""HTML/CSS/JS template for the interactive dashboard (see webdash.py).

Kept apart from the data-prep so webdash.py stays readable. render_page takes
the JSON payload and returns the full self-contained page. The charts are
hand-rolled SVG + vanilla JS (no external hosts, no server).

Look and feel: the H.B. Bro's Vineyards site theme (bone grounds, vine greens,
clay/gold accents, Fraunces display + Karla text, squared corners) - tokens
mirror hbwebsite's src/styles/global.css. Chart SERIES colors stay the
CVD-validated dataviz categorical theme (brand greens/golds cannot form a
colorblind-safe 7-slot palette); both series palettes and the green ordinal
zone ramps were re-validated against the bone-50 and vine-950 chart surfaces.
Fonts load from a relative fonts/ folder with Georgia/system fallbacks, so the
page still renders self-contained when the woff2 files are absent.
"""

from __future__ import annotations

# Data-labels come from parquet/CSV headers; the JS inserts every one via
# textContent, never innerHTML, per the dataviz "labels are untrusted" rule.

_CSS = """
@font-face {
  font-family:"Fraunces Variable";
  src:url("fonts/fraunces-latin-opsz-normal.woff2") format("woff2-variations");
  font-weight:100 900; font-style:normal; font-display:swap;
}
@font-face {
  font-family:"Karla Variable";
  src:url("fonts/karla-latin-wght-normal.woff2") format("woff2-variations");
  font-weight:200 800; font-style:normal; font-display:swap;
}
:root {
  /* H.B. Bro's tokens - benchland bone, vine canopy, clay + gold accents */
  --ink:#2b2a22; --heading:#2e3a2c; --muted:#4a4839; --faint:#87927a;
  --surface:#f6f1e4; --plane:#ede6d6;
  --hairline:rgba(46,58,44,0.16); --baseline:#a3ac95;
  --clay:#b4552d; --clay-deep:#9a4523; --gold:#c9a24b;
  --accent:#2a78d6; --critical:#d03b3b; --good:#0ca30c; --warn:#eb6834;
  --success-text:#006300;
  --band:rgba(42,120,214,0.10);
  --crit-tint:rgba(208,59,59,0.10); --good-tint:rgba(12,99,12,0.10);
  --warn-tint:rgba(180,85,45,0.12); --mute-tint:rgba(107,122,94,0.12);
  --shadow:0 1px 2px rgba(32,41,32,0.06);
  --font-display:"Fraunces Variable",Georgia,"Times New Roman",serif;
  --font-sans:"Karla Variable","Segoe UI",system-ui,sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root {
    --ink:#f6f1e4; --heading:#ede6d6; --muted:#d3c4a3; --faint:#a3ac95;
    --surface:#202920; --plane:#171d17;
    --hairline:rgba(246,241,228,0.14); --baseline:#6b7a5e;
    --clay:#dcbd6f; --clay-deep:#c9a24b; --gold:#dcbd6f;
    --accent:#3987e5; --critical:#e66767; --good:#0ca30c; --warn:#d95926;
    --success-text:#0ca30c;
    --band:rgba(57,135,229,0.16);
    --crit-tint:rgba(230,103,103,0.14); --good-tint:rgba(12,163,12,0.14);
    --warn-tint:rgba(217,89,38,0.16); --mute-tint:rgba(163,172,149,0.14);
    --shadow:none;
  }
}
* { box-sizing:border-box; }
::selection { background:var(--gold); color:#202920; }
:focus-visible { outline:2px solid var(--clay); outline-offset:3px; }
body {
  margin:0; background:var(--plane); color:var(--ink);
  font-family:var(--font-sans); line-height:1.55; font-size:15px;
  -webkit-font-smoothing:antialiased;
}
h1, h2, h3 {
  font-family:var(--font-display); color:var(--heading);
  font-variation-settings:"SOFT" 40, "WONK" 0; line-height:1.12;
}
header { border-bottom:1px solid var(--hairline); background:var(--surface); }
.brandbar {
  display:flex; align-items:center; justify-content:space-between; gap:12px;
  max-width:1180px; margin:0 auto; padding:14px 32px;
  border-bottom:1px solid var(--hairline);
}
.wordmark { display:flex; align-items:baseline; gap:8px; text-decoration:none; }
.wordmark .wm-name {
  font-family:var(--font-display); font-size:21px; font-weight:600;
  letter-spacing:-0.01em; color:var(--heading);
  font-variation-settings:"opsz" 60, "SOFT" 40;
}
.wordmark .wm-sub {
  font-size:10px; font-weight:700; text-transform:uppercase;
  letter-spacing:0.24em; color:var(--faint);
}
.backlink {
  font-size:11.5px; font-weight:700; text-transform:uppercase; letter-spacing:0.14em;
  color:var(--muted); text-decoration:none; border:1px solid var(--hairline);
  border-radius:2px; padding:7px 14px; transition:border-color .15s, color .15s;
}
.backlink:hover { border-color:var(--heading); color:var(--heading); }
.masthead {
  display:flex; flex-wrap:wrap; gap:10px 18px; align-items:end;
  justify-content:space-between; max-width:1180px; margin:0 auto;
  padding:24px 32px 20px;
}
.eyebrow {
  font-size:11px; font-weight:700; letter-spacing:0.22em; text-transform:uppercase;
  color:var(--clay); margin-bottom:6px;
}
.masthead h1 {
  margin:0; font-size:clamp(26px, 3.4vw, 34px); font-weight:500;
  font-variation-settings:"opsz" 100, "SOFT" 40, "WONK" 0; letter-spacing:-0.01em;
}
.masthead .meta { color:var(--muted); font-size:13px; margin-top:6px; }
main { max-width:1180px; margin:0 auto; padding:22px 32px 48px; }
footer {
  max-width:1180px; margin:0 auto; padding:6px 32px 40px;
  color:var(--faint); font-size:12px;
}

.chip {
  display:inline-flex; align-items:center; gap:7px; font-size:11.5px; font-weight:700;
  text-transform:uppercase; letter-spacing:0.1em;
  padding:8px 14px; border-radius:2px; border:1px solid var(--hairline);
}
.chip.alert { color:var(--critical); background:var(--crit-tint); border-color:transparent; }
.chip.ok    { color:var(--success-text); background:var(--good-tint); border-color:transparent; }
.chip.mute  { color:var(--muted); background:var(--mute-tint); border-color:transparent; }

section {
  background:var(--surface); border:1px solid var(--hairline);
  border-radius:3px; padding:22px 24px; margin:18px 0; box-shadow:var(--shadow);
}
h2 { margin:0 0 4px; font-size:21px; font-weight:540;
     font-variation-settings:"opsz" 72, "SOFT" 40, "WONK" 0; }
h3 { margin:18px 0 6px; font-size:16px; font-weight:560; }
.caption { color:var(--muted); font-size:13px; margin:2px 0 14px; max-width:72ch; }
.sub { color:var(--muted); font-weight:400; font-size:13px; font-family:var(--font-sans); }

/* block overview cards (also the block switcher) */
.cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(250px,1fr)); gap:14px; margin:2px 0 4px; }
.card {
  text-align:left; font:inherit; color:inherit; cursor:pointer; display:block; width:100%;
  background:var(--surface); border:1px solid var(--hairline); border-radius:3px;
  padding:14px 16px 12px; box-shadow:var(--shadow); transition:border-color .15s;
}
.card:hover { border-color:var(--baseline); }
.card[aria-pressed="true"] { border-color:var(--clay); box-shadow:0 0 0 1px var(--clay); }
.card .toprow { display:flex; align-items:center; justify-content:space-between; gap:8px; }
.card .name { font-weight:700; font-size:15px; }
.card .subline { color:var(--muted); font-size:12px; margin-top:1px; }
.card .bottomrow { display:flex; align-items:flex-end; justify-content:space-between; gap:10px; margin-top:10px; }
.card .big {
  font-family:var(--font-display); font-size:27px; font-weight:520; line-height:1.05;
  font-variation-settings:"opsz" 72, "SOFT" 40, "WONK" 0; color:var(--heading);
}
.card .big .u { font-family:var(--font-sans); font-size:10px; color:var(--faint); font-weight:700;
  letter-spacing:0.1em; margin-left:4px; }
.card .deltaline { font-size:12px; margin-top:3px; color:var(--muted); }

.pill {
  display:inline-flex; align-items:center; gap:5px; font-size:10px; font-weight:700;
  text-transform:uppercase; letter-spacing:0.08em;
  padding:3px 8px; border-radius:2px; white-space:nowrap;
}
.pill.crit { color:var(--critical); background:var(--crit-tint); }
.pill.warn { color:var(--warn); background:var(--warn-tint); }
.pill.good { color:var(--success-text); background:var(--good-tint); }
.pill.mute { color:var(--muted); background:var(--mute-tint); }

.up { color:var(--success-text); } .down { color:var(--critical); }

/* triage banner */
.banner { border-left:4px solid var(--good); }
.banner.alert { border-left-color:var(--critical); }
.reading { margin:2px 0 10px; font-size:14px; }
.flagline { display:flex; align-items:baseline; gap:8px; margin:6px 0; font-size:14px; }
.flagline .glyph { color:var(--critical); font-weight:700; flex:0 0 auto; }
.flagline b { font-weight:650; }
.flagline .detail { color:var(--muted); font-size:13px; }

/* KPI tiles */
.kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; }
.kpi { border:1px solid var(--hairline); border-radius:2px; padding:13px 16px; background:var(--plane); }
.kpi .label { color:var(--faint); font-size:10.5px; font-weight:700;
  text-transform:uppercase; letter-spacing:.14em; }
.kpi .value {
  font-family:var(--font-display); font-size:27px; font-weight:520; margin-top:4px;
  line-height:1.1; font-variation-settings:"opsz" 72, "SOFT" 40, "WONK" 0;
  color:var(--heading);
}
.kpi .sub2 { font-size:12px; color:var(--muted); margin-top:3px; }
.kpi.alert .value { color:var(--critical); }
.kpi.ok .value { color:var(--success-text); }

/* legend / toggles */
.legend { display:flex; flex-wrap:wrap; gap:4px 10px; margin:2px 0 8px; }
.legend button, .legend .item {
  display:inline-flex; align-items:center; gap:6px; border:0; background:none;
  color:var(--ink); font-size:13px; padding:3px 6px; border-radius:6px;
  font-variant-numeric:tabular-nums;
}
.legend button { cursor:pointer; }
.legend button:hover { background:var(--plane); }
.legend button[aria-pressed="false"] { color:var(--faint); }
.legend .swatch { width:16px; height:3px; border-radius:2px; flex:0 0 auto; }
.legend .dotswatch { width:9px; height:9px; border-radius:50%; flex:0 0 auto; }
.legend .bandswatch { width:16px; height:10px; border-radius:2px; flex:0 0 auto; }
.legend button[aria-pressed="false"] .swatch { opacity:.35; }
.legend .item { color:var(--muted); }

/* charts */
.chart { position:relative; width:100%; }
svg { display:block; width:100%; height:auto; overflow:visible; }
.axis text { fill:var(--faint); font-size:11px; }
.gridline { stroke:var(--hairline); stroke-width:1; }
.tooltip {
  position:absolute; pointer-events:none; background:var(--surface); color:var(--ink);
  border:1px solid var(--hairline); border-radius:2px; padding:8px 10px; font-size:12px;
  box-shadow:0 6px 18px rgba(32,41,32,.18); min-width:120px; opacity:0; transition:opacity .08s;
  z-index:5; font-variant-numeric:tabular-nums;
}
.tooltip .tt-x { color:var(--muted); font-size:11px; margin-bottom:5px; }
.tooltip .tt-row { display:flex; align-items:center; gap:7px; margin:2px 0; }
.tooltip .tt-key { width:14px; height:3px; border-radius:2px; flex:0 0 auto; }
.tooltip .tt-name { color:var(--muted); }
.tooltip .tt-val { margin-left:auto; font-weight:650; }
.crosshair { stroke:var(--baseline); stroke-width:1; stroke-dasharray:3 3; }

/* zone maps */
.zonewrap { display:grid; grid-template-columns:repeat(auto-fill,minmax(215px,1fr)); gap:14px; }
.curzone-wrap { max-width:440px; }
.curzone-wrap .zonecell { padding:12px; }
.curzone-wrap .zonecell svg { width:100%; }
.zonecell { border:1px solid var(--hairline); border-radius:2px; padding:8px 10px 6px; background:var(--plane); position:relative; }
.zonecell .yr { font-size:13px; font-weight:700; margin-bottom:2px; }
.zonelegend { display:flex; gap:14px; font-size:12px; color:var(--muted); margin:2px 0 10px; flex-wrap:wrap; }
.zonelegend span { display:inline-flex; align-items:center; gap:6px; }
.zonelegend i { width:11px; height:11px; border-radius:2px; display:inline-block; }

/* tables */
table { border-collapse:collapse; width:100%; font-size:14px; font-variant-numeric:tabular-nums; }
th,td { text-align:left; padding:7px 12px; border-bottom:1px solid var(--hairline); }
th { color:var(--faint); font-weight:700; white-space:nowrap; font-size:11px;
     text-transform:uppercase; letter-spacing:0.1em; }
th.sortable { cursor:pointer; user-select:none; }
th.num, td.num { text-align:right; }
th[aria-sort]:after { content:" \\2195"; color:var(--faint); }
th[aria-sort="ascending"]:after { content:" \\2191"; color:var(--accent); }
th[aria-sort="descending"]:after { content:" \\2193"; color:var(--accent); }
.overflow { overflow-x:auto; }

/* toolbar / buttons - squared, farm-utilitarian, like the site's btn-ghost */
.toolbar { display:flex; gap:10px; margin-top:16px; flex-wrap:wrap; }
.btn {
  font-family:var(--font-sans); font-size:11.5px; font-weight:700; letter-spacing:0.12em;
  text-transform:uppercase; color:var(--heading); cursor:pointer;
  background:none; border:1px solid var(--hairline); border-radius:2px; padding:10px 18px;
  transition:border-color .15s, background-color .15s;
}
.btn:hover { border-color:var(--heading); background:var(--mute-tint); }

.note { color:var(--muted); font-size:13px; margin-top:12px; max-width:72ch; }
code { background:var(--plane); border:1px solid var(--hairline); padding:1px 5px;
       border-radius:2px; font-size:12px; }

.langtoggle {
  display:inline-flex; border:1px solid var(--hairline); border-radius:2px; overflow:hidden;
}
.langtoggle button {
  font-family:var(--font-sans); font-size:11px; font-weight:700; letter-spacing:0.06em;
  color:var(--muted); background:none; border:0; cursor:pointer; padding:7px 12px;
  transition:background-color .15s, color .15s;
}
.langtoggle button[aria-pressed="true"] { background:var(--clay); color:#fff8ee; }
.langtoggle button:not([aria-pressed="true"]):hover { background:var(--mute-tint); color:var(--heading); }
"""

# The whole chart engine + page wiring. Palette mirrors the CSS custom props;
# the 8-slot categorical order is the validated dataviz theme in both modes
# (years and blocks are identities). Slot 8 (red) is held back for series so
# it never collides with the critical/freeze red. Zones use the sequential
# blue ordinal ramp (steps 250/400/600 - legal on both surfaces).
_JS = r"""
const DATA = __DATA__;
const $ = (s, r=document) => r.querySelector(s);

/* ---- i18n: English / Punjabi toggle ---- */
const STRINGS = {
  en: {
    back_to_site: "← Back to the site", eyebrow: "Field data · Vineyard Vigor Dashboard",
    title: "How the blocks are growing",
    building_baselines: "building baselines", blocks_flagged: "of {n} blocks flagged", all_on_track: "all blocks on track",
    sentinel_label: "Sentinel-2 NDVI/NDRE", data_to: "data to {d}", south_okanagan: "South Okanagan",
    status_active: "below baseline", status_flagged: "flagged, recovered", status_ok: "on track", status_no_baseline: "building baseline",
    planted: "planted {y}",
    this_season_h: "This season", this_season_cap: "A block is flagged when two consecutive readings sit under the 10th percentile of its own prior seasons at that time of year.",
    stress_log_h: "Stress log", stress_log_sub: "every below-baseline run on record",
    still_below: " · still below as of {d}", recovered_by: " · recovered by {d}",
    low_readings_txt: "{n} low readings, {a} – {b}, season-low NDVI {v}",
    col_year: "year", col_block: "block", col_first_low: "first low", col_last_low: "last low", col_low_readings: "low readings", col_season_low: "season-low NDVI",
    glance_h: "At a glance", glance_cap: "Latest reading and this season’s headline numbers for the selected block.",
    kpi_latest_ndvi: "Latest NDVI", kpi_latest_ndre: "Latest NDRE", kpi_canopy: "canopy chlorophyll · 20 m",
    kpi_peak_so_far: "{y} peak so far", kpi_typical_peak: "typical full-season peak {v}", kpi_no_baseline: "no baseline seasons yet",
    kpi_greenup: "Green-up", kpi_on_schedule: "on typical schedule", kpi_days_later: "{n} days later than typical", kpi_days_earlier: "{n} days earlier than typical",
    kpi_first_leaf: "first leaf detected in NDVI", kpi_low_vigor: "Low-vigor readings", kpi_this_season: "this season · {s}",
    vs_baseline: " vs baseline · {d}", kpi_vs_baseline_short: "vs baseline",
    curves_h: "Season curves", curves_cap: "Every season on a shared April–October axis, outlier-screened and smoothed (Savitzky–Golay) so residual cloud and smoke spikes don’t read as vine stress. Toggle years in the legend (it drives both charts); hover for values and dates. The freeze year is red; exact scene readings live in the baseline chart and the CSVs.",
    ndvi_h: "NDVI", ndvi_sub: "vine vigor · 10 m", ndre_h: "NDRE", ndre_sub: "canopy chlorophyll · 20 m · watch for late-season nutrient stress",
    year_freeze: "{y} (freeze)", year_this_season: "{y} (this season)",
    cur_vs_base_h: "Current season vs baseline", cur_vs_base_sub: "{y} season vs prior-season baseline",
    cur_vs_base_cap: "The latest season against its own prior-season, day-of-year baseline. Red dots mark flagged (two-in-a-row below the 10th percentile) readings.",
    no_baseline_yet: "no baseline yet (needs prior vine seasons)",
    leg_prior_iqr: "prior-season IQR", leg_baseline_median: "baseline median", leg_10th_pct: "10th percentile", leg_this_season: "this season", leg_flagged: "flagged reading",
    outlook_h: "Season outlook", outlook_sub: "machine-learned projection",
    outlook_cap: "A Gaussian-process model trained on this block’s prior vine seasons (plus the season so far) projects NDVI through October. The shaded band is the model’s 80% range — it reflects how much past seasons varied, and it cannot see weather ahead. With only a season or two of vine history, treat it as provisional.",
    leg_observed: "observed so far", leg_projected: "projected (dashed)", leg_80range: "80% range",
    observed_label: "observed {y}", projected_label: "projected",
    stat_proj_peak: "Projected peak NDVI", stat_range80: "{a} – {b} · 80% range",
    stat_proj_integral: "Projected May–Sep integral", stat_approx: "{a} – {b} · approximate",
    stat_model_history: "Model history", stat_season: "season", stat_seasons: "seasons",
    stat_provisional: "vine seasons · provisional", stat_prior_seasons: "prior vine seasons",
    analog_intro: "Most similar past seasons so far: ", analog_item: "{y} · {b}{pre} (Δ {d})", analog_pre: " (pre-planting)",
    analog_outro: ". Δ is the mean NDVI gap on shared days — smaller reads more alike.",
    cmp_h: "This season across blocks", cmp_cap: "All blocks together, smoothed like the season curves: if every curve dips at once the cause is shared (weather, heat, smoke); one curve dipping alone points at that block (irrigation, virus, damage).",
    curzone_h: "Current vigor zone", curzone_sub: "{y} · latest full map",
    curzone_cap: "The most recent complete-season vigor map for the selected block, one square per 10 m pixel. Zoning needs a full April–October season, so a new map appears here once each season ends. Low-vigor zones are where the vine was weakest — check those rows first on the next walk. Hover a pixel for its season-mean NDVI.",
    curzone_share: "{low}% low · {med}% medium · {high}% high vigor",
    curzone_none: "No zone map for this block yet — the first appears once a full season is on record.",
    zones_none: "No zone data for this block yet.",
    day_label: "day {n}",
    zones_h: "Vigor zones by season", zones_cap: "Within-block zones on the real block outline, one square per 10 m pixel. Zones that hold their shape across years read as soil or rootstock; one-off zones read as management, irrigation, or damage. Hover a pixel for its season-mean NDVI.",
    zone_low: "low vigor", zone_medium: "medium", zone_high: "high vigor",
    landsat_h: "Long-term history", landsat_sub: "Landsat 8/9 · 30 m · since 2014",
    landsat_cap: "Growing-season (May–September) mean NDVI per year from Landsat — a different satellite at coarser resolution, so compare shapes across years rather than exact values against the Sentinel charts above. Years before the 2024 planting show the previous ground cover; the 2021 heat dome and the 2024 freeze year sit in this record. Hover a point for the number of clear scenes behind it.",
    landsat_point_label: "{y} · {n} scenes",
    features_h: "Season features", features_cap: "Peak NDVI, its day of year, the May–September integral (NDVI·days), and green-up date. Click a header to sort.",
    col_peak_ndvi: "peak NDVI", col_peak_doy: "peak DOY", col_integral: "May–Sep integral", col_greenup: "green-up",
    dl_features: "Download features CSV", dl_flags: "Download flagged readings CSV",
    planted_note: "Blocks planted in 2024, so seasons before then reflect the previous ground cover; baselines and “typical” comparisons respect each block’s <code>baseline_start</code>. Read early-season flags as provisional until more vine history accrues.",
    footer: "Sentinel-2 L2A (harmonized) · Cloud Score+ mask (cs_cdf ≥ 0.60) · observations with ≥80% clear pixels · NDVI 10 m, NDRE 20 m · generated {g}",
  },
  pa: {
    back_to_site: "← ਵੈੱਬਸਾਈਟ ਤੇ ਵਾਪਸ ਜਾਓ", eyebrow: "ਖੇਤ ਦਾ ਡਾਟਾ · ਵਾਈਨਯਾਰਡ ਵਿਗਰ ਡੈਸ਼ਬੋਰਡ",
    title: "ਬਲਾਕ ਕਿਵੇਂ ਵਧ ਰਹੇ ਹਨ",
    building_baselines: "ਬੇਸਲਾਈਨ ਬਣ ਰਹੀ ਹੈ", blocks_flagged: "ਵਿੱਚੋਂ {n} ਬਲਾਕ ਨਿਸ਼ਾਨਬੱਧ", all_on_track: "ਸਾਰੇ ਬਲਾਕ ਠੀਕ ਹਨ",
    sentinel_label: "Sentinel-2 NDVI/NDRE", data_to: "{d} ਤੱਕ ਦਾ ਡਾਟਾ", south_okanagan: "ਸਾਊਥ ਓਕਾਨਾਗਨ",
    status_active: "ਬੇਸਲਾਈਨ ਤੋਂ ਹੇਠਾਂ", status_flagged: "ਨਿਸ਼ਾਨਬੱਧ, ਠੀਕ ਹੋ ਗਿਆ", status_ok: "ਠੀਕ ਚੱਲ ਰਿਹਾ ਹੈ", status_no_baseline: "ਬੇਸਲਾਈਨ ਬਣ ਰਹੀ ਹੈ",
    planted: "{y} ਵਿੱਚ ਲਾਇਆ",
    this_season_h: "ਇਸ ਸੀਜ਼ਨ", this_season_cap: "ਜਦੋਂ ਲਗਾਤਾਰ ਦੋ ਰੀਡਿੰਗਾਂ ਪਿਛਲੇ ਸੀਜ਼ਨਾਂ ਦੇ ਉਸੇ ਸਮੇਂ ਦੇ 10ਵੇਂ ਪ੍ਰਤੀਸ਼ਤ ਤੋਂ ਹੇਠਾਂ ਆਉਣ ਤਾਂ ਬਲਾਕ ਨਿਸ਼ਾਨਬੱਧ ਹੁੰਦਾ ਹੈ।",
    stress_log_h: "ਤਣਾਅ ਲਾਗ", stress_log_sub: "ਰਿਕਾਰਡ ਵਿੱਚ ਹਰ ਹੇਠਲਾ ਦੌਰ",
    still_below: " · {d} ਤੱਕ ਅਜੇ ਵੀ ਹੇਠਾਂ", recovered_by: " · {d} ਤੱਕ ਠੀਕ ਹੋ ਗਿਆ",
    low_readings_txt: "{n} ਹੇਠਲੀਆਂ ਰੀਡਿੰਗਾਂ, {a} – {b}, ਸੀਜ਼ਨ ਦੀ ਸਭ ਤੋਂ ਘੱਟ NDVI {v}",
    col_year: "ਸਾਲ", col_block: "ਬਲਾਕ", col_first_low: "ਪਹਿਲੀ ਹੇਠਲੀ", col_last_low: "ਆਖਰੀ ਹੇਠਲੀ", col_low_readings: "ਹੇਠਲੀਆਂ ਰੀਡਿੰਗਾਂ", col_season_low: "ਸੀਜ਼ਨ ਦੀ ਸਭ ਤੋਂ ਘੱਟ NDVI",
    glance_h: "ਇੱਕ ਨਜ਼ਰ ਵਿੱਚ", glance_cap: "ਚੁਣੇ ਹੋਏ ਬਲਾਕ ਲਈ ਤਾਜ਼ਾ ਰੀਡਿੰਗ ਅਤੇ ਇਸ ਸੀਜ਼ਨ ਦੇ ਮੁੱਖ ਅੰਕੜੇ।",
    kpi_latest_ndvi: "ਤਾਜ਼ਾ NDVI", kpi_latest_ndre: "ਤਾਜ਼ਾ NDRE", kpi_canopy: "ਛਤਰੀ ਕਲੋਰੋਫਿਲ · 20 ਮੀ",
    kpi_peak_so_far: "{y} ਦਾ ਹੁਣ ਤੱਕ ਦਾ ਸਿਖਰ", kpi_typical_peak: "ਆਮ ਪੂਰੇ-ਸੀਜ਼ਨ ਦਾ ਸਿਖਰ {v}", kpi_no_baseline: "ਅਜੇ ਕੋਈ ਬੇਸਲਾਈਨ ਸੀਜ਼ਨ ਨਹੀਂ",
    kpi_greenup: "ਹਰਿਆਲੀ ਦੀ ਸ਼ੁਰੂਆਤ", kpi_on_schedule: "ਆਮ ਸਮੇਂ ਅਨੁਸਾਰ", kpi_days_later: "ਆਮ ਨਾਲੋਂ {n} ਦਿਨ ਦੇਰੀ ਨਾਲ", kpi_days_earlier: "ਆਮ ਨਾਲੋਂ {n} ਦਿਨ ਪਹਿਲਾਂ",
    kpi_first_leaf: "NDVI ਵਿੱਚ ਪਹਿਲਾ ਪੱਤਾ ਦੇਖਿਆ ਗਿਆ", kpi_low_vigor: "ਘੱਟ-ਵਿਗਰ ਰੀਡਿੰਗਾਂ", kpi_this_season: "ਇਸ ਸੀਜ਼ਨ · {s}",
    vs_baseline: " ਬੇਸਲਾਈਨ ਦੇ ਮੁਕਾਬਲੇ · {d}", kpi_vs_baseline_short: "ਬੇਸਲਾਈਨ ਦੇ ਮੁਕਾਬਲੇ",
    curves_h: "ਸੀਜ਼ਨ ਵਕਰ", curves_cap: "ਹਰ ਸੀਜ਼ਨ ਇੱਕ ਸਾਂਝੇ ਅਪ੍ਰੈਲ–ਅਕਤੂਬਰ ਧੁਰੇ ਉੱਤੇ, ਬਾਹਰਲੇ ਅੰਕੜੇ ਹਟਾ ਕੇ ਅਤੇ ਸਮੂਥ (Savitzky–Golay) ਕੀਤਾ ਗਿਆ ਹੈ ਤਾਂ ਜੋ ਬੱਦਲ ਜਾਂ ਧੂੰਏਂ ਦੀਆਂ ਗੜਬੜੀਆਂ ਵੇਲ ਦੇ ਤਣਾਅ ਵਾਂਗ ਨਾ ਦਿਖਣ। ਲੀਜੈਂਡ ਵਿੱਚ ਸਾਲ ਟੌਗਲ ਕਰੋ (ਇਹ ਦੋਵੇਂ ਚਾਰਟ ਬਦਲਦਾ ਹੈ); ਮੁੱਲ ਅਤੇ ਤਾਰੀਖ਼ਾਂ ਲਈ ਹੋਵਰ ਕਰੋ। ਫ੍ਰੀਜ਼ ਵਾਲਾ ਸਾਲ ਲਾਲ ਹੈ; ਸਹੀ ਰੀਡਿੰਗਾਂ ਬੇਸਲਾਈਨ ਚਾਰਟ ਅਤੇ CSV ਵਿੱਚ ਮਿਲਣਗੀਆਂ।",
    ndvi_h: "NDVI", ndvi_sub: "ਵੇਲ ਦਾ ਵਿਗਰ · 10 ਮੀ", ndre_h: "NDRE", ndre_sub: "ਛਤਰੀ ਕਲੋਰੋਫਿਲ · 20 ਮੀ · ਸੀਜ਼ਨ ਦੇ ਅਖੀਰ ਦੇ ਪੋਸ਼ਕ ਤਣਾਅ ਲਈ ਦੇਖੋ",
    year_freeze: "{y} (ਫ੍ਰੀਜ਼)", year_this_season: "{y} (ਇਹ ਸੀਜ਼ਨ)",
    cur_vs_base_h: "ਮੌਜੂਦਾ ਸੀਜ਼ਨ ਬਨਾਮ ਬੇਸਲਾਈਨ", cur_vs_base_sub: "{y} ਸੀਜ਼ਨ ਬਨਾਮ ਪਿਛਲੇ ਸੀਜ਼ਨ ਦੀ ਬੇਸਲਾਈਨ",
    cur_vs_base_cap: "ਤਾਜ਼ਾ ਸੀਜ਼ਨ ਦੀ ਤੁਲਨਾ ਇਸ ਦੇ ਆਪਣੇ ਪਿਛਲੇ ਸੀਜ਼ਨ ਦੀ, ਦਿਨ-ਮੁਤਾਬਕ ਬੇਸਲਾਈਨ ਨਾਲ। ਲਾਲ ਬਿੰਦੀਆਂ ਨਿਸ਼ਾਨਬੱਧ (ਲਗਾਤਾਰ ਦੋ ਵਾਰ 10ਵੇਂ ਪ੍ਰਤੀਸ਼ਤ ਤੋਂ ਹੇਠਾਂ) ਰੀਡਿੰਗਾਂ ਦਿਖਾਉਂਦੀਆਂ ਹਨ।",
    no_baseline_yet: "ਅਜੇ ਕੋਈ ਬੇਸਲਾਈਨ ਨਹੀਂ (ਪਿਛਲੇ ਵੇਲ ਸੀਜ਼ਨ ਚਾਹੀਦੇ ਹਨ)",
    leg_prior_iqr: "ਪਿਛਲੇ ਸੀਜ਼ਨ ਦਾ IQR", leg_baseline_median: "ਬੇਸਲਾਈਨ ਮੱਧਮਾਨ", leg_10th_pct: "10ਵਾਂ ਪ੍ਰਤੀਸ਼ਤ", leg_this_season: "ਇਹ ਸੀਜ਼ਨ", leg_flagged: "ਨਿਸ਼ਾਨਬੱਧ ਰੀਡਿੰਗ",
    outlook_h: "ਸੀਜ਼ਨ ਦਾ ਅਨੁਮਾਨ", outlook_sub: "ਮਸ਼ੀਨ-ਸਿੱਖਿਆ ਪ੍ਰੋਜੈਕਸ਼ਨ",
    outlook_cap: "ਇਸ ਬਲਾਕ ਦੇ ਪਿਛਲੇ ਵੇਲ ਸੀਜ਼ਨਾਂ (ਅਤੇ ਹੁਣ ਤੱਕ ਦੇ ਇਸ ਸੀਜ਼ਨ) ਉੱਤੇ ਸਿਖਲਾਈ ਪ੍ਰਾਪਤ ਇੱਕ ਗਾਊਸੀਅਨ-ਪ੍ਰੋਸੈੱਸ ਮਾਡਲ ਅਕਤੂਬਰ ਤੱਕ NDVI ਦਾ ਅਨੁਮਾਨ ਲਾਉਂਦਾ ਹੈ। ਛਾਂ ਵਾਲੀ ਪੱਟੀ ਮਾਡਲ ਦੀ 80% ਰੇਂਜ ਹੈ — ਇਹ ਦਿਖਾਉਂਦੀ ਹੈ ਕਿ ਪਿਛਲੇ ਸੀਜ਼ਨ ਕਿੰਨੇ ਬਦਲਦੇ ਰਹੇ, ਅਤੇ ਇਹ ਅੱਗੇ ਦਾ ਮੌਸਮ ਨਹੀਂ ਦੇਖ ਸਕਦੀ। ਸਿਰਫ਼ ਇੱਕ ਜਾਂ ਦੋ ਸੀਜ਼ਨ ਦੇ ਇਤਿਹਾਸ ਨਾਲ, ਇਸ ਨੂੰ ਆਰਜ਼ੀ ਸਮਝੋ।",
    leg_observed: "ਹੁਣ ਤੱਕ ਦੇਖਿਆ ਗਿਆ", leg_projected: "ਅਨੁਮਾਨਿਤ (ਡੈਸ਼ਡ)", leg_80range: "80% ਰੇਂਜ",
    observed_label: "{y} ਦੇਖਿਆ ਗਿਆ", projected_label: "ਅਨੁਮਾਨਿਤ",
    stat_proj_peak: "ਅਨੁਮਾਨਿਤ ਸਿਖਰ NDVI", stat_range80: "{a} – {b} · 80% ਰੇਂਜ",
    stat_proj_integral: "ਅਨੁਮਾਨਿਤ ਮਈ–ਸਤੰਬਰ ਇੰਟੈਗਰਲ", stat_approx: "{a} – {b} · ਲਗਭਗ",
    stat_model_history: "ਮਾਡਲ ਇਤਿਹਾਸ", stat_season: "ਸੀਜ਼ਨ", stat_seasons: "ਸੀਜ਼ਨ",
    stat_provisional: "ਵੇਲ ਸੀਜ਼ਨ · ਆਰਜ਼ੀ", stat_prior_seasons: "ਪਿਛਲੇ ਵੇਲ ਸੀਜ਼ਨ",
    analog_intro: "ਹੁਣ ਤੱਕ ਦੇ ਸਭ ਤੋਂ ਮਿਲਦੇ-ਜੁਲਦੇ ਪਿਛਲੇ ਸੀਜ਼ਨ: ", analog_item: "{y} · {b}{pre} (Δ {d})", analog_pre: " (ਲਾਉਣ ਤੋਂ ਪਹਿਲਾਂ)",
    analog_outro: "। Δ ਸਾਂਝੇ ਦਿਨਾਂ ਵਿੱਚ ਔਸਤ NDVI ਦਾ ਫ਼ਰਕ ਹੈ — ਛੋਟਾ ਹੋਣ ਦਾ ਮਤਲਬ ਵਧੇਰੇ ਮਿਲਦਾ-ਜੁਲਦਾ।",
    cmp_h: "ਇਹ ਸੀਜ਼ਨ ਸਾਰੇ ਬਲਾਕਾਂ ਵਿੱਚ", cmp_cap: "ਸਾਰੇ ਬਲਾਕ ਇਕੱਠੇ, ਸੀਜ਼ਨ ਵਕਰਾਂ ਵਾਂਗ ਸਮੂਥ ਕੀਤੇ: ਜੇ ਹਰ ਵਕਰ ਇੱਕੋ ਵੇਲੇ ਡਿੱਗੇ ਤਾਂ ਕਾਰਨ ਸਾਂਝਾ ਹੈ (ਮੌਸਮ, ਗਰਮੀ, ਧੂੰਆਂ); ਜੇ ਇੱਕੱਲਾ ਵਕਰ ਡਿੱਗੇ ਤਾਂ ਇਹ ਉਸੇ ਬਲਾਕ ਵੱਲ ਇਸ਼ਾਰਾ ਕਰਦਾ ਹੈ (ਸਿੰਚਾਈ, ਵਾਇਰਸ, ਨੁਕਸਾਨ)।",
    curzone_h: "ਮੌਜੂਦਾ ਵਿਗਰ ਜ਼ੋਨ", curzone_sub: "{y} · ਤਾਜ਼ਾ ਪੂਰਾ ਨਕਸ਼ਾ",
    curzone_cap: "ਚੁਣੇ ਹੋਏ ਬਲਾਕ ਲਈ ਸਭ ਤੋਂ ਤਾਜ਼ਾ ਪੂਰੇ-ਸੀਜ਼ਨ ਦਾ ਵਿਗਰ ਨਕਸ਼ਾ, ਹਰ 10 ਮੀ ਪਿਕਸਲ ਲਈ ਇੱਕ ਵਰਗ। ਜ਼ੋਨ ਬਣਾਉਣ ਲਈ ਪੂਰਾ ਅਪ੍ਰੈਲ–ਅਕਤੂਬਰ ਸੀਜ਼ਨ ਚਾਹੀਦਾ ਹੈ, ਇਸ ਲਈ ਨਵਾਂ ਨਕਸ਼ਾ ਹਰ ਸੀਜ਼ਨ ਖਤਮ ਹੋਣ ਤੋਂ ਬਾਅਦ ਇੱਥੇ ਆਉਂਦਾ ਹੈ। ਘੱਟ-ਵਿਗਰ ਜ਼ੋਨ ਉਹ ਥਾਂਵਾਂ ਹਨ ਜਿੱਥੇ ਵੇਲ ਸਭ ਤੋਂ ਕਮਜ਼ੋਰ ਸੀ — ਅਗਲੀ ਗੇੜੀ ਵੇਲੇ ਉਹ ਕਤਾਰਾਂ ਪਹਿਲਾਂ ਦੇਖੋ। ਸੀਜ਼ਨ ਦੀ ਔਸਤ NDVI ਲਈ ਪਿਕਸਲ ਉੱਤੇ ਹੋਵਰ ਕਰੋ।",
    curzone_share: "{low}% ਘੱਟ · {med}% ਦਰਮਿਆਨਾ · {high}% ਵੱਧ ਵਿਗਰ",
    curzone_none: "ਇਸ ਬਲਾਕ ਲਈ ਅਜੇ ਕੋਈ ਜ਼ੋਨ ਨਕਸ਼ਾ ਨਹੀਂ — ਪਹਿਲਾ ਨਕਸ਼ਾ ਪੂਰਾ ਸੀਜ਼ਨ ਰਿਕਾਰਡ ਹੋਣ ਤੋਂ ਬਾਅਦ ਆਵੇਗਾ।",
    zones_none: "ਇਸ ਬਲਾਕ ਲਈ ਅਜੇ ਕੋਈ ਜ਼ੋਨ ਡਾਟਾ ਨਹੀਂ।",
    day_label: "ਦਿਨ {n}",
    zones_h: "ਸੀਜ਼ਨ ਮੁਤਾਬਕ ਵਿਗਰ ਜ਼ੋਨ", zones_cap: "ਅਸਲ ਬਲਾਕ ਦੀ ਰੂਪਰੇਖਾ ਉੱਤੇ ਅੰਦਰੂਨੀ ਜ਼ੋਨ, ਹਰ 10 ਮੀ ਪਿਕਸਲ ਲਈ ਇੱਕ ਵਰਗ। ਜੋ ਜ਼ੋਨ ਸਾਲਾਂ ਦੌਰਾਨ ਆਪਣੀ ਸ਼ਕਲ ਬਣਾਈ ਰੱਖਦੇ ਹਨ ਉਹ ਮਿੱਟੀ ਜਾਂ ਜੜ੍ਹ ਦਾ ਸੰਕੇਤ ਹਨ; ਇੱਕ-ਵਾਰੀ ਜ਼ੋਨ ਪ੍ਰਬੰਧਨ, ਸਿੰਚਾਈ, ਜਾਂ ਨੁਕਸਾਨ ਦਾ ਸੰਕੇਤ ਹਨ। ਸੀਜ਼ਨ ਦੀ ਔਸਤ NDVI ਲਈ ਪਿਕਸਲ ਉੱਤੇ ਹੋਵਰ ਕਰੋ।",
    zone_low: "ਘੱਟ ਵਿਗਰ", zone_medium: "ਦਰਮਿਆਨਾ", zone_high: "ਵੱਧ ਵਿਗਰ",
    landsat_h: "ਲੰਬੇ ਸਮੇਂ ਦਾ ਇਤਿਹਾਸ", landsat_sub: "Landsat 8/9 · 30 ਮੀ · 2014 ਤੋਂ",
    landsat_cap: "Landsat ਤੋਂ ਹਰ ਸਾਲ ਦੀ ਵਧਣ-ਸੀਜ਼ਨ (ਮਈ–ਸਤੰਬਰ) ਦੀ ਔਸਤ NDVI — ਇੱਕ ਵੱਖਰਾ ਸੈਟੇਲਾਈਟ, ਘੱਟ ਰੈਜ਼ੋਲਿਊਸ਼ਨ ਨਾਲ, ਇਸ ਲਈ ਉੱਪਰਲੇ Sentinel ਚਾਰਟਾਂ ਦੇ ਸਹੀ ਮੁੱਲਾਂ ਦੀ ਬਜਾਏ ਸਾਲਾਂ ਵਿਚਲੀ ਸ਼ਕਲ ਦੀ ਤੁਲਨਾ ਕਰੋ। 2024 ਦੀ ਲਾਈ ਤੋਂ ਪਹਿਲਾਂ ਦੇ ਸਾਲ ਪਿਛਲੀ ਜ਼ਮੀਨੀ ਹਰਿਆਲੀ ਦਿਖਾਉਂਦੇ ਹਨ; 2021 ਦਾ ਹੀਟ ਡੋਮ ਅਤੇ 2024 ਦਾ ਫ੍ਰੀਜ਼ ਸਾਲ ਇਸ ਰਿਕਾਰਡ ਵਿੱਚ ਹਨ। ਪਿੱਛੇ ਦੇ ਸਾਫ਼ ਸੀਨਾਂ ਦੀ ਗਿਣਤੀ ਲਈ ਬਿੰਦੂ ਉੱਤੇ ਹੋਵਰ ਕਰੋ।",
    landsat_point_label: "{y} · {n} ਸੀਨ",
    features_h: "ਸੀਜ਼ਨ ਵਿਸ਼ੇਸ਼ਤਾਵਾਂ", features_cap: "ਸਿਖਰ NDVI, ਇਸ ਦਾ ਦਿਨ, ਮਈ–ਸਤੰਬਰ ਇੰਟੈਗਰਲ (NDVI·ਦਿਨ), ਅਤੇ ਹਰਿਆਲੀ ਦੀ ਸ਼ੁਰੂਆਤ ਦੀ ਤਾਰੀਖ਼। ਕ੍ਰਮਬੱਧ ਕਰਨ ਲਈ ਸਿਰਲੇਖ ਉੱਤੇ ਕਲਿੱਕ ਕਰੋ।",
    col_peak_ndvi: "ਸਿਖਰ NDVI", col_peak_doy: "ਸਿਖਰ ਦਿਨ", col_integral: "ਮਈ–ਸਤੰਬਰ ਇੰਟੈਗਰਲ", col_greenup: "ਹਰਿਆਲੀ ਦੀ ਸ਼ੁਰੂਆਤ",
    dl_features: "ਵਿਸ਼ੇਸ਼ਤਾਵਾਂ CSV ਡਾਊਨਲੋਡ ਕਰੋ", dl_flags: "ਨਿਸ਼ਾਨਬੱਧ ਰੀਡਿੰਗਾਂ CSV ਡਾਊਨਲੋਡ ਕਰੋ",
    planted_note: "ਬਲਾਕ 2024 ਵਿੱਚ ਲਾਏ ਗਏ ਸਨ, ਇਸ ਲਈ ਉਸ ਤੋਂ ਪਹਿਲਾਂ ਦੇ ਸੀਜ਼ਨ ਪਿਛਲੀ ਜ਼ਮੀਨੀ ਹਰਿਆਲੀ ਦਰਸਾਉਂਦੇ ਹਨ; ਬੇਸਲਾਈਨ ਅਤੇ “ਆਮ” ਤੁਲਨਾਵਾਂ ਹਰ ਬਲਾਕ ਦੀ <code>baseline_start</code> ਦਾ ਧਿਆਨ ਰੱਖਦੀਆਂ ਹਨ। ਸੀਜ਼ਨ ਦੀ ਸ਼ੁਰੂਆਤ ਦੇ ਨਿਸ਼ਾਨਾਂ ਨੂੰ ਹੋਰ ਵੇਲ ਇਤਿਹਾਸ ਇਕੱਠਾ ਹੋਣ ਤੱਕ ਆਰਜ਼ੀ ਸਮਝੋ।",
    footer: "Sentinel-2 L2A (harmonized) · Cloud Score+ ਮਾਸਕ (cs_cdf ≥ 0.60) · ≥80% ਸਾਫ਼ ਪਿਕਸਲ ਵਾਲੀਆਂ ਰੀਡਿੰਗਾਂ · NDVI 10 ਮੀ, NDRE 20 ਮੀ · ਤਿਆਰ ਕੀਤਾ {g}",
  },
};
let lang = (() => { try { return localStorage.getItem("vigor-lang") || "en"; } catch (e) { return "en"; } })();
const t = (key, vars) => {
  let s = (STRINGS[lang] && STRINGS[lang][key]) ?? STRINGS.en[key] ?? key;
  if (vars) for (const k in vars) s = s.replaceAll("{" + k + "}", vars[k]);
  return s;
};
function applyStaticI18n() {
  document.documentElement.lang = lang === "pa" ? "pa" : "en";
  document.querySelectorAll("[data-i18n]").forEach(nd => { nd.textContent = t(nd.getAttribute("data-i18n")); });
  document.querySelectorAll("[data-i18n-html]").forEach(nd => { nd.innerHTML = t(nd.getAttribute("data-i18n-html")); });
  document.title = t("title") + " · H.B. Bro’s";
  const foot = $("#footer");
  if (foot) foot.textContent = t("footer", { g: foot.dataset.generated });
}
function wireLangToggle() {
  const wrap = $("#lang-toggle"); if (!wrap) return;
  wrap.querySelectorAll("button").forEach(b => {
    b.setAttribute("aria-pressed", b.dataset.lang === lang ? "true" : "false");
    b.onclick = () => {
      if (lang === b.dataset.lang) return;
      lang = b.dataset.lang;
      try { localStorage.setItem("vigor-lang", lang); } catch (e) {}
      wrap.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", x.dataset.lang === lang ? "true" : "false"));
      applyStaticI18n(); renderHeader(); renderAll();
    };
  });
}

const el = (t, cls) => { const e = document.createElement(t); if (cls) e.className = cls; return e; };
const cssVar = n => getComputedStyle(document.body).getPropertyValue(n).trim();
const NS = "http://www.w3.org/2000/svg";
const svg = (t, a={}) => { const e = document.createElementNS(NS, t); for (const k in a) e.setAttribute(k, a[k]); return e; };

const THEME_LIGHT = ["#2a78d6","#008300","#e87ba4","#eda100","#1baf7a","#eb6834","#4a3aa7"];
const THEME_DARK  = ["#3987e5","#008300","#d55181","#c98500","#199e70","#d95926","#9085e9"];
// low -> high vigor: brand vine-green ordinal ramps, validated per surface
const ZONE_LIGHT = ["#a3ac95","#5b7046","#2e3a2c"];
const ZONE_DARK  = ["#4b5d3a","#87927a","#c3cdb2"];
const MONTHS = [[91,"Apr"],[121,"May"],[152,"Jun"],[182,"Jul"],[213,"Aug"],[244,"Sep"],[274,"Oct"],[305,""]];
const MN = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

const mqDark = window.matchMedia("(prefers-color-scheme: dark)");
const theme = () => mqDark.matches ? THEME_DARK : THEME_LIGHT;
const zoneRamp = () => mqDark.matches ? ZONE_DARK : ZONE_LIGHT;
const LY = String(DATA.latest_year);

let state = { block: DATA.blocks[0], hiddenYears: new Set(), hiddenBlocks: new Set() };

const fmt3 = v => v.toFixed(3);
const fmtDelta = v => (v > 0 ? "+" : "−").concat(Math.abs(v).toFixed(3));
const fdate = iso => { if (!iso) return "—"; const p = iso.split("-"); return MN[+p[1]-1] + " " + (+p[2]); };

const HIST_FLOOR = DATA.history_floor || 2019;
function yearColor(year, blockId) {
  if (+year === DATA.freeze_year) return cssVar("--critical");
  // Pre-floor seasons (thin archive, previous ground cover) are gray context;
  // identity hues stay reserved for the seasons that can hold a palette slot.
  if (+year < HIST_FLOOR) return cssVar("--baseline");
  const years = Object.keys(DATA.timeseries[blockId || state.block] || {})
    .filter(y => +y !== DATA.freeze_year && +y >= HIST_FLOOR).sort();
  return theme()[years.indexOf(year) % theme().length];
}
const blockColor = b => theme()[DATA.blocks.indexOf(b) % theme().length];

/* ---- status vocabulary (icon + label, never color alone) ---- */
function statusMeta(st) {
  return {
    active:        { glyph: "⚠", label: t("status_active"), cls: "crit" },
    flagged:       { glyph: "⚠", label: t("status_flagged"), cls: "warn" },
    ok:            { glyph: "✓", label: t("status_ok"), cls: "good" },
    "no-baseline": { glyph: "○", label: t("status_no_baseline"), cls: "mute" },
  }[st] || { glyph: "○", label: st, cls: "mute" };
}

/* ---- generic line chart with crosshair + one-tooltip-every-series ---- */
function lineChart(container, opts) {
  // opts: { series:[{name,color,points:[[x,y,label],...],width,dash,opacity,hover,
  //         markers:[[x,y,r,color],...]}], bands:[{pts:[[x,lo,hi]],color}],
  //         xDomain:[min,max], yDomain:[min,max], height, fmtVal }
  const W = container.clientWidth || 640, H = opts.height || 240;
  const m = { t: 10, r: 14, b: 26, l: 40 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const [x0, x1] = opts.xDomain, [y0, y1] = opts.yDomain;
  const sx = x => m.l + (x - x0) / (x1 - x0) * iw;
  const sy = y => m.t + (1 - (y - y0) / (y1 - y0)) * ih;

  container.innerHTML = "";
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img" });

  // gridlines + ticks
  const yticks = 4, g = svg("g", { class: "axis" });
  for (let i = 0; i <= yticks; i++) {
    const yv = y0 + (y1 - y0) * i / yticks, yy = sy(yv);
    g.appendChild(svg("line", { class: "gridline", x1: m.l, x2: W - m.r, y1: yy, y2: yy }));
    const tx = svg("text", { x: m.l - 6, y: yy + 3, "text-anchor": "end" });
    tx.textContent = (y1 - y0) <= 0.5 ? yv.toFixed(2) : yv.toFixed(1); g.appendChild(tx);
  }
  (opts.xTicks || MONTHS).forEach(([d, lab]) => {
    if (d < x0 || d > x1) return;
    const xx = sx(d);
    g.appendChild(svg("line", { class: "gridline", x1: xx, x2: xx, y1: m.t, y2: m.t + ih, opacity: .55 }));
    if (!lab) return;
    const tx = svg("text", { x: xx, y: H - 8, "text-anchor": "middle" });
    tx.textContent = lab; g.appendChild(tx);
  });
  s.appendChild(g);

  // baseline bands (behind)
  (opts.bands || []).forEach(b => {
    if (b.pts.length < 2) return;
    let d = "M" + b.pts.map(p => `${sx(p[0])},${sy(p[1])}`).join(" L");
    for (let i = b.pts.length - 1; i >= 0; i--) d += ` L${sx(b.pts[i][0])},${sy(b.pts[i][2])}`;
    s.appendChild(svg("path", { d: d + "Z", fill: b.color, stroke: "none" }));
  });

  // series
  opts.series.forEach(se => {
    if (!se.points.length) return;
    const d = "M" + se.points.map(p => `${sx(p[0])},${sy(p[1])}`).join(" L");
    const path = svg("path", { d, fill: "none", stroke: se.color,
      "stroke-width": se.width || 1.6, "stroke-linejoin": "round", "stroke-linecap": "round" });
    if (se.dash) path.setAttribute("stroke-dasharray", se.dash);
    if (se.opacity) path.setAttribute("opacity", se.opacity);
    s.appendChild(path);
    (se.markers || []).forEach(mk => s.appendChild(svg("circle",
      { cx: sx(mk[0]), cy: sy(mk[1]), r: mk[2] || 3.5, fill: mk[3] || se.color,
        stroke: cssVar("--surface"), "stroke-width": 1.5 })));
  });

  container.appendChild(s);

  // crosshair + tooltip layer
  const cross = svg("line", { class: "crosshair", y1: m.t, y2: m.t + ih, x1: -9, x2: -9 });
  s.appendChild(cross);
  const tip = el("div", "tooltip"); container.appendChild(tip);
  const hoverSeries = opts.series.filter(se => se.hover !== false && se.points.length);
  const xs = [...new Set(hoverSeries.flatMap(se => se.points.map(p => p[0])))].sort((a, b) => a - b);

  s.addEventListener("pointermove", ev => {
    const pt = s.getBoundingClientRect();
    const px = (ev.clientX - pt.left) / pt.width * W;
    const xData = x0 + (px - m.l) / iw * (x1 - x0);
    if (!xs.length) return;
    let nx = xs[0]; for (const c of xs) if (Math.abs(c - xData) < Math.abs(nx - xData)) nx = c;
    cross.setAttribute("x1", sx(nx)); cross.setAttribute("x2", sx(nx));
    tip.innerHTML = ""; let lab = "";
    const xr = el("div", "tt-x");
    hoverSeries.forEach(se => {
      const p = se.points.find(q => q[0] === nx); if (!p) return;
      if (p[2]) lab = p[2];
      const row = el("div", "tt-row");
      const key = el("span", "tt-key"); key.style.background = se.color;
      const nm = el("span", "tt-name"); nm.textContent = se.name;
      const vv = el("span", "tt-val"); vv.textContent = (opts.fmtVal ? opts.fmtVal(p[1]) : p[1].toFixed(3));
      row.append(key, nm, vv); tip.appendChild(row);
    });
    xr.textContent = lab || t("day_label", { n: nx }); tip.insertBefore(xr, tip.firstChild);
    tip.style.opacity = 1;
    let tx = sx(nx) / W * pt.width + 14;
    if (tx + tip.offsetWidth > pt.width) tx = sx(nx) / W * pt.width - tip.offsetWidth - 14;
    tip.style.left = tx + "px"; tip.style.top = (m.t + 4) + "px";
  });
  s.addEventListener("pointerleave", () => { tip.style.opacity = 0; cross.setAttribute("x1", -9); cross.setAttribute("x2", -9); });
}

/* ---- header: status chip + meta line ---- */
function renderHeader() {
  const chip = $("#chip"); chip.textContent = "";
  const sts = DATA.blocks.map(b => (DATA.status[b] || {}).state);
  const nLow = sts.filter(s => s === "active" || s === "flagged").length;
  const judged = sts.filter(s => s && s !== "no-baseline").length;
  let cls, glyph, text;
  if (!judged) { cls = "mute"; glyph = "○"; text = t("building_baselines"); }
  else if (nLow) { cls = "alert"; glyph = "⚠"; text = nLow + " " + t("blocks_flagged", { n: DATA.blocks.length }); }
  else { cls = "ok"; glyph = "✓"; text = t("all_on_track"); }
  chip.className = "chip " + cls;
  const gl = el("span"); gl.textContent = glyph;
  chip.append(gl, document.createTextNode(text));

  const bits = [];
  if (DATA.sites) bits.push(DATA.sites + ", " + t("south_okanagan"));
  bits.push(t("sentinel_label"));
  if (DATA.latest_obs) bits.push(t("data_to", { d: DATA.latest_obs }));
  $("#hdr-meta").textContent = bits.join(" · ");
}

/* ---- block overview cards (also the block switcher) ---- */
function sparkline(container, b) {
  const W = 120, H = 38;
  const bl = (DATA.baseline[b] || {})[LY];
  const obs = bl ? bl.obs.map(o => [o[0], o[1]]) : ((DATA.timeseries[b] || {})[LY] || []).map(o => [o[0], o[1]]);
  if (!obs.length) return;
  const med = bl ? bl.base.map(r => [r[0], r[3]]) : [];
  const flags = bl ? bl.obs.filter(o => o[3]) : [];
  const ys = obs.map(p => p[1]).concat(med.map(p => p[1]));
  const y0 = Math.min(...ys) - 0.04, y1 = Math.max(...ys) + 0.04;
  const sx = x => (x - 91) / (305 - 91) * W;
  const sy = y => H - 3 - (y - y0) / ((y1 - y0) || 1) * (H - 6);
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "spark" });
  s.style.width = W + "px"; s.style.flex = "0 0 auto";
  if (med.length > 1) s.appendChild(svg("path", {
    d: "M" + med.map(p => `${sx(p[0])},${sy(p[1])}`).join(" L"),
    fill: "none", stroke: cssVar("--baseline"), "stroke-width": 1.2 }));
  s.appendChild(svg("path", {
    d: "M" + obs.map(p => `${sx(p[0])},${sy(p[1])}`).join(" L"),
    fill: "none", stroke: cssVar("--accent"), "stroke-width": 1.6,
    "stroke-linejoin": "round", "stroke-linecap": "round" }));
  flags.forEach(o => s.appendChild(svg("circle",
    { cx: sx(o[0]), cy: sy(o[1]), r: 2.1, fill: cssVar("--critical") })));
  container.appendChild(s);
}

function renderCards() {
  const wrap = $("#cards"); wrap.innerHTML = "";
  DATA.blocks.forEach(b => {
    const k = DATA.kpis[b] || {}, st = DATA.status[b] || { state: "no-baseline" };
    const card = el("button", "card");
    card.setAttribute("aria-pressed", b === state.block ? "true" : "false");

    const top = el("div", "toprow");
    const nm = el("span", "name"); nm.textContent = b;
    const sm = statusMeta(st.state);
    const pill = el("span", "pill " + sm.cls); pill.textContent = sm.glyph + " " + sm.label;
    top.append(nm, pill);

    const sub = el("div", "subline");
    sub.textContent = [k.variety, k.site, k.planting_year ? t("planted", { y: k.planting_year }) : null]
      .filter(Boolean).join(" · ");

    const bottom = el("div", "bottomrow");
    const left = el("div");
    const big = el("div", "big");
    big.textContent = k.latest_ndvi === null || k.latest_ndvi === undefined ? "—" : fmt3(k.latest_ndvi);
    const u = el("span", "u"); u.textContent = "NDVI"; big.appendChild(u);
    const dl = el("div", "deltaline");
    if (k.latest_delta !== null && k.latest_delta !== undefined) {
      const d = el("span", k.latest_delta < 0 ? "down" : "up");
      d.textContent = fmtDelta(k.latest_delta);
      dl.append(d, document.createTextNode(t("vs_baseline", { d: fdate(k.latest_date) })));
    } else dl.textContent = fdate(k.latest_date);
    left.append(big, dl);
    bottom.appendChild(left);
    sparkline(bottom, b);

    card.append(top, sub, bottom);
    card.onclick = () => { state.block = b; state.hiddenYears = new Set(); renderAll(); };
    wrap.appendChild(card);
  });
}

/* ---- season triage: reading, active flags, stress log ---- */
function renderTriage() {
  const sec = $("#triage");
  const anyJudged = DATA.blocks.some(b => (DATA.status[b] || {}).state !== "no-baseline");
  if (!anyJudged && !DATA.events.length) { sec.style.display = "none"; return; }
  sec.style.display = "";
  const lowNow = DATA.blocks.filter(b => ["active", "flagged"].includes((DATA.status[b] || {}).state));
  sec.classList.toggle("alert", lowNow.length > 0);

  $("#reading").textContent = DATA.reading || "";

  const fl = $("#flaglines"); fl.innerHTML = "";
  lowNow.forEach(b => {
    const st = DATA.status[b];
    const line = el("div", "flagline");
    const gl = el("span", "glyph"); gl.textContent = "⚠";
    const nm = el("b"); nm.textContent = b;
    const det = el("span", "detail");
    let txt = t("low_readings_txt", { n: st.n_low, a: fdate(st.first_low), b: fdate(st.last_low), v: fmt3(st.min_ndvi) });
    txt += st.state === "active" ? t("still_below", { d: fdate(st.last_obs) })
                                  : t("recovered_by", { d: fdate(st.last_obs) });
    det.textContent = txt;
    line.append(gl, nm, det);
    fl.appendChild(line);
  });

  const tbl = $("#evt-table"); tbl.innerHTML = "";
  if (!DATA.events.length) { $("#evt-wrap").style.display = "none"; return; }
  $("#evt-wrap").style.display = "";
  const cols = [t("col_year"), t("col_block"), t("col_first_low"), t("col_last_low"), t("col_low_readings"), t("col_season_low")];
  const thead = el("thead"), htr = el("tr");
  cols.forEach((c, i) => { const th = el("th" ); if (i > 3) th.className = "num"; th.textContent = c; htr.appendChild(th); });
  thead.appendChild(htr); tbl.appendChild(thead);
  const tb = el("tbody");
  [...DATA.events].sort((a, b) => b.year - a.year || (a.block_id < b.block_id ? -1 : 1)).forEach(e => {
    const tr = el("tr");
    [e.year, e.block_id, e.first_low, e.last_low, e.n_low, fmt3(e.min_ndvi)].forEach((v, i) => {
      const td = el("td"); if (i > 3) td.className = "num"; td.textContent = v; tr.appendChild(td);
    });
    tb.appendChild(tr);
  });
  tbl.appendChild(tb);
}

/* ---- KPI tiles ---- */
function renderKpis() {
  const k = DATA.kpis[state.block] || {}, st = DATA.status[state.block] || {};
  const row = $("#kpis"); row.innerHTML = "";
  const tile = (label, value, cls) => {
    const t = el("div", "kpi" + (cls ? " " + cls : ""));
    const l = el("div", "label"); l.textContent = label;
    const v = el("div", "value");
    v.textContent = (value === null || value === undefined) ? "—" : value;
    const s2 = el("div", "sub2");
    t.append(l, v, s2); row.appendChild(t); return s2;
  };
  const colored = (target, val, text, goodWhenNegative) => {
    const sp = el("span", (goodWhenNegative ? val <= 0 : val >= 0) ? "up" : "down");
    sp.textContent = text; target.appendChild(sp);
  };

  let s2 = tile(t("kpi_latest_ndvi"), k.latest_ndvi === null ? null : fmt3(k.latest_ndvi));
  s2.textContent = fdate(k.latest_date) + (k.latest_delta !== null && k.latest_delta !== undefined ? " · " : "");
  if (k.latest_delta !== null && k.latest_delta !== undefined)
    colored(s2, k.latest_delta, fmtDelta(k.latest_delta) + " " + t("kpi_vs_baseline_short"), false);

  s2 = tile(t("kpi_latest_ndre"), k.latest_ndre === null ? null : fmt3(k.latest_ndre));
  s2.textContent = t("kpi_canopy");

  s2 = tile(t("kpi_peak_so_far", { y: DATA.latest_year }), k.peak_ndvi === null ? null : fmt3(k.peak_ndvi));
  s2.textContent = k.peak_typical !== null && k.peak_typical !== undefined
    ? t("kpi_typical_peak", { v: fmt3(k.peak_typical) }) : t("kpi_no_baseline");

  s2 = tile(t("kpi_greenup"), fdate(k.greenup_date));
  if (k.greenup_delta_days !== null && k.greenup_delta_days !== undefined) {
    const d = k.greenup_delta_days;
    colored(s2, d, d === 0 ? t("kpi_on_schedule")
      : t(d > 0 ? "kpi_days_later" : "kpi_days_earlier", { n: Math.abs(d) }), true);
  } else s2.textContent = t("kpi_first_leaf");

  const sm = statusMeta(st.state || "no-baseline");
  s2 = tile(t("kpi_low_vigor"), k.active_alerts,
    k.active_alerts ? "alert" : (st.state === "ok" ? "ok" : ""));
  s2.textContent = t("kpi_this_season", { s: sm.label });
}

/* ---- season curves: NDVI + NDRE share one year legend ---- */
function yearLabel(y) {
  if (+y === DATA.freeze_year) return t("year_freeze", { y });
  if (y === LY) return t("year_this_season", { y });
  return y;
}

function renderCurves() {
  const seasons = DATA.timeseries[state.block] || {};
  const years = Object.keys(seasons).sort();
  const lg = $("#year-legend"); lg.innerHTML = "";
  years.forEach(y => {
    const b = el("button"); b.setAttribute("aria-pressed", state.hiddenYears.has(y) ? "false" : "true");
    const sw = el("span", "swatch"); sw.style.background = yearColor(y);
    b.append(sw, document.createTextNode(yearLabel(y)));
    b.onclick = () => { state.hiddenYears.has(y) ? state.hiddenYears.delete(y) : state.hiddenYears.add(y); renderCurves(); };
    lg.appendChild(b);
  });
  const mkSeries = (source) => years
    .filter(y => !state.hiddenYears.has(y) && (source[y] || []).length)
    .map(y => ({
      name: y, color: yearColor(y), points: source[y],
      width: (+y === DATA.freeze_year || y === LY) ? 2.3 : (+y < HIST_FLOOR ? 1.1 : 1.4),
      opacity: (+y === DATA.freeze_year || y === LY) ? 1 : (+y < HIST_FLOOR ? 0.7 : 0.85),
    }));
  lineChart($("#overlay-chart"), {
    series: mkSeries(seasons), xDomain: [91, 305], yDomain: [0, 1], height: 300,
    fmtVal: fmt3,
  });
  const ndre = DATA.ndre[state.block] || {};
  const vals = Object.values(ndre).flat().map(p => p[1]);
  const yMax = vals.length ? Math.min(1, Math.ceil((Math.max(...vals) + 0.05) * 10) / 10) : 0.6;
  lineChart($("#ndre-chart"), {
    series: mkSeries(ndre), xDomain: [91, 305], yDomain: [0, yMax], height: 210,
    fmtVal: fmt3,
  });
}

/* ---- current season vs baseline ---- */
function renderBaseline() {
  const wrap = $("#baseline-chart"), title = $("#baseline-title"), lg = $("#baseline-legend");
  const byYear = (DATA.baseline[state.block]) || {};
  const years = Object.keys(byYear).filter(y => byYear[y].base.length).sort();
  if (!years.length) { wrap.innerHTML = ""; lg.innerHTML = ""; title.textContent = t("no_baseline_yet"); return; }
  const yr = years[years.length - 1];
  title.textContent = t("cur_vs_base_sub", { y: yr });
  const a = byYear[yr];
  const bandPts = a.base.map(b => [b[0], b[2], b[4]]);        // p25..p75
  const p10 = a.base.map(b => [b[0], b[1]]);
  const med = a.base.map(b => [b[0], b[3]]);
  const obs = a.obs.map(o => [o[0], o[1], o[2]]);
  const markers = a.obs.filter(o => o[3]).map(o => [o[0], o[1], 4, cssVar("--critical")]);
  if (a.obs.length) {
    const lastO = a.obs[a.obs.length - 1];
    if (!lastO[3]) markers.push([lastO[0], lastO[1], 4]);
  }
  lineChart(wrap, {
    height: 260, xDomain: [91, 305], yDomain: [0, 1], fmtVal: fmt3,
    bands: [{ pts: bandPts, color: cssVar("--band") }],
    series: [
      { name: t("leg_baseline_median"), color: cssVar("--faint"), points: med, width: 1.2, hover: false },
      { name: t("leg_10th_pct"), color: cssVar("--warn"), points: p10, width: 1.2, dash: "5 4", hover: false },
      { name: state.block + " " + yr, color: cssVar("--accent"), points: obs, width: 1.8, markers },
    ],
  });
  // static legend (identity is never hover-gated)
  lg.innerHTML = "";
  const item = (mk, label) => { const it = el("span", "item"); it.append(mk, document.createTextNode(label)); lg.appendChild(it); };
  const band = el("span", "bandswatch"); band.style.background = cssVar("--band");
  item(band, t("leg_prior_iqr"));
  const medSw = el("span", "swatch"); medSw.style.background = cssVar("--faint");
  item(medSw, t("leg_baseline_median"));
  const pSw = el("span", "swatch"); pSw.style.background = cssVar("--warn");
  item(pSw, t("leg_10th_pct"));
  const oSw = el("span", "swatch"); oSw.style.background = cssVar("--accent");
  item(oSw, t("leg_this_season"));
  const fSw = el("span", "dotswatch"); fSw.style.background = cssVar("--critical");
  item(fSw, t("leg_flagged"));
}

/* ---- this season across blocks ---- */
function renderCompare() {
  const sec = $("#cmp-section");
  const withData = DATA.blocks.filter(b => ((DATA.timeseries[b] || {})[LY] || []).length);
  if (withData.length < 2) { sec.style.display = "none"; return; }
  sec.style.display = "";
  const lg = $("#cmp-legend"); lg.innerHTML = "";
  withData.forEach(b => {
    const btn = el("button"); btn.setAttribute("aria-pressed", state.hiddenBlocks.has(b) ? "false" : "true");
    const sw = el("span", "swatch"); sw.style.background = blockColor(b);
    const k = DATA.kpis[b] || {};
    btn.append(sw, document.createTextNode(b + (k.variety ? " · " + k.variety : "")));
    btn.onclick = () => { state.hiddenBlocks.has(b) ? state.hiddenBlocks.delete(b) : state.hiddenBlocks.add(b); renderCompare(); };
    lg.appendChild(btn);
  });
  const series = withData.filter(b => !state.hiddenBlocks.has(b)).map(b => ({
    name: b, color: blockColor(b), points: DATA.timeseries[b][LY], width: 1.8,
  }));
  lineChart($("#cmp-chart"), {
    series, xDomain: [91, 305], yDomain: [0, 1], height: 240, fmtVal: fmt3,
  });
}

/* ---- zone maps (real outline, aspect-true, 10 m raster squares) ---- */
// zone-map legend swatches (shared by both zone sections)
function fillZoneLegend(lg) {
  const ramp = zoneRamp(); lg.innerHTML = "";
  [t("zone_low"), t("zone_medium"), t("zone_high")].forEach((lab, i) => {
    const it = el("span"); const sw = el("i"); sw.style.background = ramp[i];
    it.append(sw, document.createTextNode(lab)); lg.appendChild(it);
  });
}

// One pixel map for one season, drawn into a fresh .zonecell. `bbox` (from
// zoneBBox) is shared across years so the "by season" cells align; the
// current-zone card passes its own single-year bbox. `label` heads the cell;
// omit it to draw no header.
function drawZoneCell(pts, rings, bbox, targetW, label) {
  const ramp = zoneRamp();
  const { x0, x1, y0, y1, cosf } = bbox;
  const pad = 12;
  const spanX = ((x1 - x0) || 1e-6) * 111320 * cosf, spanY = ((y1 - y0) || 1e-6) * 110540;
  const W = targetW;
  const H = Math.max(90, Math.min(Math.round(targetW * 1.1), Math.round((W - 2 * pad) * spanY / spanX) + 2 * pad));
  const sxD = (W - 2 * pad) / ((x1 - x0) || 1e-6), syD = (H - 2 * pad) / ((y1 - y0) || 1e-6);
  const sx = x => pad + (x - x0) * sxD;
  const sy = y => H - pad - (y - y0) * syD;
  const pw = 10 / (111320 * cosf) * sxD * 0.9, ph = 10 / 110540 * syD * 0.9;

  const cell = el("div", "zonecell");
  if (label != null) { const hd = el("div", "yr"); hd.textContent = label; cell.appendChild(hd); }
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}` });
  const tip = el("div", "tooltip");
  rings.forEach(r => {
    const d = "M" + r.map(p => `${sx(p[0])},${sy(p[1])}`).join(" L") + "Z";
    s.appendChild(svg("path", { d, fill: "none", stroke: cssVar("--baseline"), "stroke-width": 1.2 }));
  });
  pts.forEach(p => {
    const r = svg("rect", { x: sx(p[0]) - pw / 2, y: sy(p[1]) - ph / 2, width: pw, height: ph,
      rx: 1, fill: ramp[p[2]] || ramp[0] });
    r.addEventListener("pointerenter", ev => {
      tip.innerHTML = "";
      const zr = el("div", "tt-row"); const zn = el("span", "tt-name");
      zn.textContent = [t("zone_low"), t("zone_medium"), t("zone_high")][p[2]] || ("zone " + p[2]);
      const zv = el("span", "tt-val"); zv.textContent = p[3].toFixed(3);
      zr.append(zn, zv); tip.appendChild(zr);
      tip.style.opacity = 1;
      const rc = cell.getBoundingClientRect();
      tip.style.left = (ev.clientX - rc.left + 10) + "px"; tip.style.top = (ev.clientY - rc.top + 8) + "px";
    });
    r.addEventListener("pointerleave", () => tip.style.opacity = 0);
    s.appendChild(r);
  });
  cell.appendChild(s); cell.appendChild(tip);
  return cell;
}

// Shared geographic bbox for a set of years + the block outline.
function zoneBBox(yearsPts, rings) {
  let xs = [], ys = [];
  yearsPts.forEach(pts => pts.forEach(p => { xs.push(p[0]); ys.push(p[1]); }));
  rings.forEach(r => r.forEach(p => { xs.push(p[0]); ys.push(p[1]); }));
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const y0 = Math.min(...ys), y1 = Math.max(...ys);
  return { x0, x1, y0, y1, cosf: Math.cos(((y0 + y1) / 2) * Math.PI / 180) };
}

/* ---- current vigor zone: just this season's map, shown large ---- */
function renderCurrentZone() {
  const sec = $("#curzone-section");
  const byYear = (DATA.zones[state.block]) || {};
  const years = Object.keys(byYear).sort();
  const wrap = $("#curzone-wrap"); wrap.innerHTML = "";
  const share = $("#curzone-share"); share.textContent = "";
  fillZoneLegend($("#curzone-legend"));
  if (!years.length) { wrap.textContent = t("curzone_none"); $("#curzone-sub").textContent = ""; return; }

  const yr = years[years.length - 1];               // most recent season with a zone map
  const pts = byYear[yr];
  const rings = DATA.outlines[state.block] || [];
  $("#curzone-sub").textContent = t("curzone_sub", { y: yr });

  const bbox = zoneBBox([pts], rings);
  const W = Math.min(420, Math.max(240, wrap.clientWidth || 420));
  wrap.appendChild(drawZoneCell(pts, rings, bbox, W, null));

  // share of pixels in each zone — the grower-facing headline number
  const n = pts.length || 1, c = [0, 0, 0];
  pts.forEach(p => { if (p[2] >= 0 && p[2] <= 2) c[p[2]]++; });
  const pct = i => Math.round(c[i] / n * 100);
  share.textContent = t("curzone_share", { low: pct(0), med: pct(1), high: pct(2) });
}

function renderZones() {
  fillZoneLegend($("#zone-legend"));
  const wrap = $("#zone-wrap"); wrap.innerHTML = "";
  const byYear = (DATA.zones[state.block]) || {};
  const years = Object.keys(byYear).sort();
  if (!years.length) { wrap.textContent = t("zones_none"); return; }
  const rings = DATA.outlines[state.block] || [];
  // shared bbox across years so cells align
  const bbox = zoneBBox(years.map(yr => byYear[yr]), rings);
  years.forEach(yr => wrap.appendChild(drawZoneCell(byYear[yr], rings, bbox, 220, yr)));
}

/* ---- ML season outlook: GP projection band + analog seasons ---- */
const doyDate = d => { const t = new Date(Date.UTC(DATA.latest_year, 0, d)); return MN[t.getUTCMonth()] + " " + t.getUTCDate(); };

function renderOutlook() {
  const sec = $("#outlook-section");
  const o = DATA.outlook[state.block];
  if (!o || !o.band || !o.band.length) { sec.style.display = "none"; return; }
  sec.style.display = "";

  const obs = (DATA.timeseries[state.block] || {})[LY] || [];  // smoothed, like the season curves
  const bandPts = o.band.map(b => [b[0], b[2], b[3]]);
  const muPts = o.band.map(b => [b[0], b[1], doyDate(b[0])]);
  lineChart($("#outlook-chart"), {
    height: 260, xDomain: [91, 305], yDomain: [0, 1], fmtVal: fmt3,
    bands: [{ pts: bandPts, color: cssVar("--band") }],
    series: [
      { name: t("observed_label", { y: LY }), color: cssVar("--accent"), points: obs, width: 1.8 },
      { name: t("projected_label"), color: cssVar("--accent"), points: muPts, width: 1.6, dash: "6 4" },
    ],
  });

  const lg = $("#outlook-legend"); lg.innerHTML = "";
  const item = (mk, label) => { const it = el("span", "item"); it.append(mk, document.createTextNode(label)); lg.appendChild(it); };
  const oSw = el("span", "swatch"); oSw.style.background = cssVar("--accent");
  item(oSw, t("leg_observed"));
  const pSw = el("span", "swatch"); pSw.style.background = cssVar("--accent"); pSw.style.opacity = .55;
  item(pSw, t("leg_projected"));
  const bSw = el("span", "bandswatch"); bSw.style.background = cssVar("--band");
  item(bSw, t("leg_80range"));

  const stats = $("#outlook-stats"); stats.innerHTML = "";
  const s = o.summary;
  if (s) {
    const tile = (label, value, sub) => {
      const tl = el("div", "kpi");
      const l = el("div", "label"); l.textContent = label;
      const v = el("div", "value"); v.textContent = value;
      const s2 = el("div", "sub2"); s2.textContent = sub;
      tl.append(l, v, s2); stats.appendChild(tl);
    };
    tile(t("stat_proj_peak"), fmt3(s.proj_peak),
      t("stat_range80", { a: fmt3(s.proj_peak_lo), b: fmt3(s.proj_peak_hi) }));
    tile(t("stat_proj_integral"), s.proj_integral.toFixed(1),
      t("stat_approx", { a: s.proj_integral_lo.toFixed(1), b: s.proj_integral_hi.toFixed(1) }));
    tile(t("stat_model_history"), s.n_train_seasons + " " + t(s.n_train_seasons === 1 ? "stat_season" : "stat_seasons"),
      s.n_train_seasons < 3 ? t("stat_provisional") : t("stat_prior_seasons"));
  }

  const an = DATA.analogs[state.block] || [];
  const note = $("#analog-note");
  if (an.length) {
    const parts = an.slice(0, 3).map(a =>
      t("analog_item", { y: a.year, b: a.block, pre: a.pre ? t("analog_pre") : "", d: a.diff.toFixed(3) }));
    note.textContent = t("analog_intro") + parts.join(",  ") + t("analog_outro");
  } else note.textContent = "";
}

/* ---- long-term history: Landsat 8/9 annual means ---- */
function renderLandsat() {
  const sec = $("#landsat-section");
  const withData = DATA.blocks.filter(b => (DATA.landsat[b] || []).length);
  if (!withData.length) { sec.style.display = "none"; return; }
  sec.style.display = "";

  let years = [];
  withData.forEach(b => DATA.landsat[b].forEach(r => years.push(r[0])));
  const y0 = Math.min(...years), y1 = Math.max(...years);
  const step = (y1 - y0) > 9 ? 2 : 1;
  const xTicks = [];
  for (let y = y0; y <= y1; y++) if ((y - y0) % step === 0) xTicks.push([y, String(y)]);

  const series = withData.map(b => {
    const pts = DATA.landsat[b].map(r => [r[0], r[1], t("landsat_point_label", { y: r[0], n: r[2] })]);
    return { name: b, color: blockColor(b), points: pts, width: 1.7,
             markers: pts.map(p => [p[0], p[1], 3]) };
  });
  lineChart($("#landsat-chart"), {
    height: 240, xDomain: [y0 - 0.5, y1 + 0.5], yDomain: [0, 1],
    xTicks, fmtVal: fmt3, series,
  });

  const lg = $("#landsat-legend"); lg.innerHTML = "";
  withData.forEach(b => {
    const it = el("span", "item");
    const sw = el("span", "swatch"); sw.style.background = blockColor(b);
    const k = DATA.kpis[b] || {};
    it.append(sw, document.createTextNode(b + (k.variety ? " · " + k.variety : "")));
    lg.appendChild(it);
  });
}

/* ---- features table (sortable) ---- */
let sortState = { key: "year", dir: 1 };
function renderTable() {
  const rows = DATA.features.filter(r => r.block_id === state.block);
  const cols = [["year", t("col_year"), 0], ["peak_ndvi", t("col_peak_ndvi"), 1], ["peak_doy", t("col_peak_doy"), 1],
    ["integral_may_sep", t("col_integral"), 1], ["greenup_date", t("col_greenup"), 0]];
  const tbl = $("#feat-table"); tbl.innerHTML = "";
  const thead = el("thead"), htr = el("tr");
  cols.forEach(([key, label, num]) => {
    const th = el("th", "sortable" + (num ? " num" : "")); th.textContent = label;
    if (sortState.key === key) th.setAttribute("aria-sort", sortState.dir === 1 ? "ascending" : "descending");
    th.onclick = () => { sortState = { key, dir: sortState.key === key ? -sortState.dir : 1 }; renderTable(); };
    htr.appendChild(th);
  });
  thead.appendChild(htr); tbl.appendChild(thead);
  rows.sort((a, b) => {
    const va = a[sortState.key], vb = b[sortState.key];
    if (va === null) return 1; if (vb === null) return -1;
    return (va > vb ? 1 : va < vb ? -1 : 0) * sortState.dir;
  });
  const tb = el("tbody");
  rows.forEach(r => {
    const tr = el("tr");
    [[r.year, 0, 0], [r.peak_ndvi, 1, 3], [r.peak_doy, 1, 0], [r.integral_may_sep, 1, 1], [r.greenup_date, 0, 0]].forEach(([v, num, dp]) => {
      const td = el("td", num ? "num" : null);
      td.textContent = (v === null || v === undefined) ? "—" : (dp && typeof v === "number" ? v.toFixed(dp) : v);
      tr.appendChild(td);
    });
    tb.appendChild(tr);
  });
  tbl.appendChild(tb);
}

/* ---- CSV export ---- */
function toCsv(rows, cols) {
  const esc = v => { v = v === null || v === undefined ? "" : String(v); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
  return cols.join(",") + "\n" + rows.map(r => cols.map(c => esc(r[c])).join(",")).join("\n") + "\n";
}
function download(name, text) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
  const a = el("a"); a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
function wireDownloads() {
  $("#dl-features").onclick = () => download("season_features.csv",
    toCsv(DATA.features, ["block_id", "year", "peak_ndvi", "peak_doy", "integral_may_sep", "greenup_date"]));
  const fb = $("#dl-flags");
  if (!DATA.flags.length) fb.style.display = "none";
  else fb.onclick = () => download("flagged_observations.csv",
    toCsv(DATA.flags, ["block_id", "date", "year", "ndvi", "base_p10", "base_median"]));
}

function renderAll() {
  renderCards(); renderTriage(); renderKpis(); renderCurves();
  renderBaseline(); renderOutlook(); renderCompare(); renderCurrentZone(); renderZones();
  renderLandsat(); renderTable();
}
applyStaticI18n(); wireLangToggle(); renderHeader(); wireDownloads(); renderAll();
window.addEventListener("resize", () => { renderCurves(); renderBaseline(); renderOutlook(); renderCompare(); renderCurrentZone(); renderLandsat(); });
if (mqDark.addEventListener) mqDark.addEventListener("change", () => { renderHeader(); renderAll(); });
"""

_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<title>Vineyard Vigor Dashboard</title>
<style>__CSS__</style>
</head>
<body>
<header>
  <div class="brandbar">
    <a class="wordmark" href="/">
      <span class="wm-name">H.B. Bro&rsquo;s</span>
      <span class="wm-sub">Vineyards</span>
    </a>
    <div style="display:flex; align-items:center; gap:14px;">
      <span class="langtoggle" id="lang-toggle">
        <button type="button" data-lang="en">EN</button><button type="button" data-lang="pa">ਪੰਜਾਬੀ</button>
      </span>
      <a class="backlink" href="/" data-i18n="back_to_site">&larr; Back to the site</a>
    </div>
  </div>
  <div class="masthead">
    <div>
      <div class="eyebrow" data-i18n="eyebrow">Field data &middot; Vineyard Vigor Dashboard</div>
      <h1 data-i18n="title">How the blocks are growing</h1>
      <div class="meta" id="hdr-meta"></div>
    </div>
    <span class="chip" id="chip"></span>
  </div>
</header>
<main>
  <div class="cards" id="cards"></div>

  <section class="banner" id="triage">
    <h2 data-i18n="this_season_h">This season</h2>
    <div class="caption" data-i18n="this_season_cap">A block is flagged when two consecutive readings sit under the
      10th percentile of its own prior seasons at that time of year.</div>
    <p class="reading" id="reading"></p>
    <div id="flaglines"></div>
    <div id="evt-wrap">
      <h3><span data-i18n="stress_log_h">Stress log</span> <span class="sub" data-i18n="stress_log_sub">every below-baseline run on record</span></h3>
      <div class="overflow"><table id="evt-table"></table></div>
    </div>
  </section>

  <section>
    <h2 data-i18n="glance_h">At a glance</h2>
    <div class="caption" data-i18n="glance_cap">Latest reading and this season&rsquo;s headline numbers for the selected block.</div>
    <div class="kpis" id="kpis"></div>
  </section>

  <section>
    <h2 data-i18n="curves_h">Season curves</h2>
    <div class="caption" data-i18n="curves_cap">Every season on a shared April&ndash;October axis, outlier-screened and
      smoothed (Savitzky&ndash;Golay) so residual cloud and smoke spikes don&rsquo;t read as vine
      stress. Toggle years in the legend (it drives both charts); hover for values and dates.
      The freeze year is red; exact scene readings live in the baseline chart and the CSVs.</div>
    <div class="legend" id="year-legend"></div>
    <h3><span data-i18n="ndvi_h">NDVI</span> <span class="sub" data-i18n="ndvi_sub">vine vigor &middot; 10 m</span></h3>
    <div class="chart" id="overlay-chart"></div>
    <h3><span data-i18n="ndre_h">NDRE</span> <span class="sub" data-i18n="ndre_sub">canopy chlorophyll &middot; 20 m &middot; watch for late-season nutrient stress</span></h3>
    <div class="chart" id="ndre-chart"></div>
  </section>

  <section>
    <h2><span data-i18n="cur_vs_base_h">Current season vs baseline</span> <span class="sub" id="baseline-title"></span></h2>
    <div class="caption" data-i18n="cur_vs_base_cap">The latest season against its own prior-season, day-of-year baseline.
      Red dots mark flagged (two-in-a-row below the 10th percentile) readings.</div>
    <div class="legend" id="baseline-legend"></div>
    <div class="chart" id="baseline-chart"></div>
  </section>

  <section id="outlook-section">
    <h2><span data-i18n="outlook_h">Season outlook</span> <span class="sub" data-i18n="outlook_sub">machine-learned projection</span></h2>
    <div class="caption" data-i18n="outlook_cap">A Gaussian-process model trained on this block&rsquo;s prior vine seasons
      (plus the season so far) projects NDVI through October. The shaded band is the model&rsquo;s
      80% range &mdash; it reflects how much past seasons varied, and it cannot see weather ahead.
      With only a season or two of vine history, treat it as provisional.</div>
    <div class="legend" id="outlook-legend"></div>
    <div class="chart" id="outlook-chart"></div>
    <div class="kpis" id="outlook-stats" style="margin-top:14px"></div>
    <p class="note" id="analog-note"></p>
  </section>

  <section id="cmp-section">
    <h2 data-i18n="cmp_h">This season across blocks</h2>
    <div class="caption" data-i18n="cmp_cap">All blocks together, smoothed like the season curves: if every curve dips
      at once the cause is shared (weather, heat, smoke); one curve dipping alone points at that
      block (irrigation, virus, damage).</div>
    <div class="legend" id="cmp-legend"></div>
    <div class="chart" id="cmp-chart"></div>
  </section>

  <section id="curzone-section">
    <h2><span data-i18n="curzone_h">Current vigor zone</span> <span class="sub" id="curzone-sub"></span></h2>
    <div class="caption" data-i18n="curzone_cap">The most recent complete-season vigor map for the selected block,
      one square per 10&nbsp;m pixel. Zoning needs a full April&ndash;October season, so a new map appears
      here once each season ends. Low-vigor zones are where the vine was weakest &mdash;
      check those rows first on the next walk. Hover a pixel for its season-mean NDVI.</div>
    <div class="zonelegend" id="curzone-legend"></div>
    <div class="curzone-wrap" id="curzone-wrap"></div>
    <p class="note" id="curzone-share"></p>
  </section>

  <section>
    <h2 data-i18n="zones_h">Vigor zones by season</h2>
    <div class="caption" data-i18n="zones_cap">Within-block zones on the real block outline, one square per
      10&nbsp;m pixel. Zones that hold their shape across years read as soil or rootstock;
      one-off zones read as management, irrigation, or damage. Hover a pixel for its
      season-mean NDVI.</div>
    <div class="zonelegend" id="zone-legend"></div>
    <div class="zonewrap" id="zone-wrap"></div>
  </section>

  <section id="landsat-section">
    <h2><span data-i18n="landsat_h">Long-term history</span> <span class="sub" data-i18n="landsat_sub">Landsat 8/9 &middot; 30 m &middot; since 2014</span></h2>
    <div class="caption" data-i18n="landsat_cap">Growing-season (May&ndash;September) mean NDVI per year from Landsat &mdash;
      a different satellite at coarser resolution, so compare shapes across years rather than exact
      values against the Sentinel charts above. Years before the 2024 planting show the previous
      ground cover; the 2021 heat dome and the 2024 freeze year sit in this record. Hover a point
      for the number of clear scenes behind it.</div>
    <div class="legend" id="landsat-legend"></div>
    <div class="chart" id="landsat-chart"></div>
  </section>

  <section>
    <h2 data-i18n="features_h">Season features</h2>
    <div class="caption" data-i18n="features_cap">Peak NDVI, its day of year, the May&ndash;September integral (NDVI&middot;days),
      and green-up date. Click a header to sort.</div>
    <div class="overflow"><table id="feat-table"></table></div>
    <div class="toolbar">
      <button class="btn" id="dl-features" data-i18n="dl_features">Download features CSV</button>
      <button class="btn" id="dl-flags" data-i18n="dl_flags">Download flagged readings CSV</button>
    </div>
    <p class="note" data-i18n-html="planted_note">Blocks planted in 2024, so seasons before then reflect the previous ground cover;
      baselines and &ldquo;typical&rdquo; comparisons respect each block&rsquo;s <code>baseline_start</code>.
      Read early-season flags as provisional until more vine history accrues.</p>
  </section>
</main>
<footer id="footer" data-generated="__GENERATED__">Sentinel-2 L2A (harmonized) &middot; Cloud Score+ mask (cs_cdf &ge; 0.60) &middot;
  observations with &ge;80% clear pixels &middot; NDVI 10 m, NDRE 20 m &middot; generated __GENERATED__</footer>
<script>__JS__</script>
</body>
</html>
"""


def render_page(data_json: str) -> str:
    from datetime import datetime
    js = _JS.replace("__DATA__", data_json.replace("</", "<\\/"))
    return (
        _TEMPLATE
        .replace("__CSS__", _CSS)
        .replace("__JS__", js)
        .replace("__GENERATED__", datetime.now().strftime("%Y-%m-%d %H:%M"))
    )
