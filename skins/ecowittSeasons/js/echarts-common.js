// weewx-echarts: settings and helpers shared by the charts page and the chart builder.
// Settings come from js/echarts-config.js (echarts-config.js.tmpl), loaded just before this file.
// Parts adapted from the Belchertown skin by Pat O'Brien (GPL-3.0).

var config = echarts_config;

// Like $obs.label in a template: an unknown label returns its own name.
var labels = new Proxy(config.labels, {
    get: function(target, key) {
        return (typeof key === "string" && !(key in target)) ? key : target[key];
    }
});

// A time zone name the browser doesn't know would break every date, so it is checked once; the UTC offset is the fallback
var wx_tz = (function() {
    try {
        if (config.time_zone) new Intl.DateTimeFormat("en", {timeZone: config.time_zone});
        return config.time_zone || "";
    } catch (e) {
        return "";
    }
})();

// "auto" separators come from the browser, which knows every locale
(function() {
    var parts = [];
    try { parts = new Intl.NumberFormat(config.locale).formatToParts(1234567.8); } catch (e) {}
    function separator(type, fallback) {
        var part = parts.find(function(p) { return p.type === type; });
        return part ? part.value : fallback;
    }
    if (config.decimal === "auto") config.decimal = separator("decimal", ".");
    if (config.thousands === "auto") config.thousands = separator("group", ",");
})();

["utc", "timezone", "localizedFormat", "advancedFormat", "localeData"].forEach(function(plugin) {
    if (window["dayjs_plugin_" + plugin]) dayjs.extend(window["dayjs_plugin_" + plugin]);
});
dayjs.locale(config.dayjs_locale);

function wx_debug(message) {
    if (config.debug > 0) console.log(message);
}

function wx_ready(fn) {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", fn);
    else fn();
}

function wx_all(selector) {
    return document.querySelectorAll(selector);
}

function wx_html(selector, html) {
    if (html === undefined) return;
    wx_all(selector).forEach(function(el) { el.innerHTML = html; });
}

// JSON that is never served from the browser cache (weewx rewrites these files every archive period)
async function wx_json(url) {
    var resp = await fetch(url + (url.indexOf("?") < 0 ? "?" : "&") + "_=" + Date.now());
    if (!resp.ok) throw new Error("HTTP " + resp.status + " loading " + url);
    return resp.json();
}

// The site's root, relative to this page ("." or "..")
function get_relative_url() {
    var script = document.querySelector("script[src*='js/echarts-common.js']");
    var src = script ? script.getAttribute("src") : "./js/";
    return src.split("js/echarts-common.js")[0].replace(/\/$/, "") || ".";
}

function getURLvar(k) {
    var p = {};
    location.search.replace(/[?&]+([^=&]+)=([^&]*)/gi, function(s, key, v) { p[key] = decodeURIComponent(v); });
    return k ? p[k] : p;
}

// A unix time as a Day.js date in the station's time zone
function tzAdjustedMoment(input) {
    if (!wx_tz) return dayjs.unix(Number(input)).utcOffset(config.utc_offset);
    return dayjs.unix(Number(input)).tz(wx_tz);
}

// A number with a given number of decimals (-1: its own) and separators; the thousands separator is used
// from 10000 up, so a pressure of 1013 stays as it is.
function wx_number_format(number, decimals, decimalPoint, thousandsSep) {
    number = +number || 0;
    if (decimals === undefined || decimals === null || decimals === "") decimals = -1;
    decimals = parseInt(decimals, 10);
    if (decimalPoint === undefined) decimalPoint = config.decimal;
    if (thousandsSep === undefined) thousandsSep = config.thousands;
    var str;
    if (decimals === -1) {
        str = String(+number.toFixed(10));
        if (/e/.test(str)) str = number.toFixed(10).replace(/\.?0+$/, "");
    } else {
        str = number.toFixed(decimals);
    }
    var negative = str.charAt(0) === "-";
    if (negative) str = str.slice(1);
    var parts = str.split(".");
    var whole = parts[0];
    if (Math.abs(number) >= 10000) whole = whole.replace(/\B(?=(\d{3})+(?!\d))/g, thousandsSep);
    var out = whole + (parts.length > 1 ? decimalPoint + parts[1] : "");
    return (negative && +str !== 0 ? "-" : "") + out;
}

// Compass name of a direction in degrees: N, NNE, ... (16 points)
function wx_compass(degrees) {
    var names = config.ordinate_names;
    return names[Math.round(((+degrees % 360) + 360) % 360 / 22.5) % 16];
}

// A value as the tooltips show it: wind direction as "NNW (337°)", numbers with the station's rounding
function wx_value_format(value, observation, withDegrees, rounding, mirrored, number_format) {
    if (mirrored) value = Math.abs(value);
    if (observation == "windDir") {
        var name = wx_compass(value);
        return withDegrees ? name + " (" + Math.round(value) + "\xBA)" : name;
    }
    var nf = number_format || {};
    var decimals = nf.decimals;
    if (decimals === undefined && rounding !== undefined && rounding != "-1") decimals = rounding;
    try {
        return wx_number_format(value, decimals, nf.decimal_point, nf.thousands_separator);
    } catch (e) {
        return String(value);
    }
}

/* --- Light and dark theme ------------------------------------------------- */

function wx_is_dark() {
    return document.documentElement.classList.contains("dark");
}

function wx_set_theme(theme, remember) {
    var root = document.documentElement;
    root.classList.toggle("dark", theme === "dark");
    root.classList.toggle("light", theme !== "dark");
    if (remember) {
        try { localStorage.setItem("echarts_theme", theme); } catch (e) {}
    }
    if (typeof wx_charts_redraw === "function") wx_charts_redraw();
}

// With theme = auto and no choice of the visitor's own, follow the system setting as it changes
if (window.matchMedia) {
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function(e) {
        var saved = null;
        try { saved = localStorage.getItem("echarts_theme"); } catch (err) {}
        if (config.theme === "auto" && !saved) wx_set_theme(e.matches ? "dark" : "light", false);
    });
}

/* --- Visitor's unit switch: charts in the other unit system (°F <-> °C, mph <-> km/h, ...) --- */

var units_config = config.units;

var UNIT_ALT = {
    degree_F: "degree_C", degree_C: "degree_F",
    mile_per_hour: "km_per_hour", km_per_hour: "mile_per_hour", meter_per_second: "km_per_hour",
    mile_per_hour2: "km_per_hour2", km_per_hour2: "mile_per_hour2", meter_per_second2: "km_per_hour2",
    inHg: "hPa", hPa: "inHg", mbar: "inHg", kPa: "inHg", mmHg: "hPa",
    inch: "mm", mm: "inch", cm: "inch",
    inch_per_hour: "mm_per_hour", mm_per_hour: "inch_per_hour", cm_per_hour: "inch_per_hour",
    mile: "km", km: "mile",
    foot: "meter", meter: "foot",
    degree_F_day: "degree_C_day", degree_C_day: "degree_F_day"
};

// Factor to a common base per dimension (m/s, hPa, mm, mm/h, km, m); temperatures are special-cased
var UNIT_FACTOR = {
    mile_per_hour: 0.44704, km_per_hour: 1 / 3.6, meter_per_second: 1, knot: 0.514444,
    mile_per_hour2: 0.44704, km_per_hour2: 1 / 3.6, meter_per_second2: 1,
    inHg: 33.8638866667, hPa: 1, mbar: 1, kPa: 10, mmHg: 1.33322368,
    inch: 25.4, mm: 1, cm: 10,
    inch_per_hour: 25.4, mm_per_hour: 1, cm_per_hour: 10,
    mile: 1.609344, km: 1,
    foot: 0.3048, meter: 1,
    degree_F_day: 5 / 9, degree_C_day: 1
};

function units_alt_on() {
    try { return localStorage.getItem("echarts_units") === "alt"; } catch (e) { return false; }
}

function alt_unit(unit) {
    var alt = UNIT_ALT[unit];
    return alt && units_config.labels[alt] !== undefined ? alt : null;
}

// delta: a temperature difference, which converts without the 32° offset
function convert_unit(value, from, to, delta) {
    if (value === null || value === undefined || isNaN(value) || from === to) return value;
    if (from === "degree_F" && to === "degree_C") return delta ? value * 5 / 9 : (value - 32) * 5 / 9;
    if (from === "degree_C" && to === "degree_F") return delta ? value * 9 / 5 : value * 9 / 5 + 32;
    return value * UNIT_FACTOR[from] / UNIT_FACTOR[to];
}

function unit_decimals(unit) {
    var m = /%\.(\d+)f/.exec(units_config.formats[unit] || "");
    return m ? parseInt(m[1]) : 0;
}

// The unit a group is shown in right now
function display_unit(group) {
    var unit = units_config.groups[group];
    return (units_alt_on() && alt_unit(unit)) || unit;
}

// Chart group JSON: each series says which unit its data is in
function convert_chart_units(data) {
    Object.keys(data).forEach(function(plotname) {
        var plot = data[plotname];
        if (!plot || !plot.series) return;
        Object.keys(plot.series).forEach(function(name) {
            var s = plot.series[name], from = s.range_unit || s.unit || series_station_unit(s), to = from && alt_unit(from);
            if (s.observation === "windRose") {
                (s.data || []).forEach(function(band) { if (band && band.name) band.name = convert_unit_range_text(band.name); });
                return;
            }
            if (!to) return;
            var from_label = (units_config.labels[from] || "").trim(), to_label = units_config.labels[to].trim();
            s.data = (s.data || []).map(function(point) {
                if (Array.isArray(point)) {
                    return point.map(function(v, i) { return i === 0 || v === null ? v : convert_unit(v, from, to); });
                }
                return typeof point === "number" ? convert_unit(point, from, to) : point;
            });
            if (s.axis_label) s.axis_label = swap_axis_unit(s.axis_label, from_label, to_label);
            if (plot.options && plot.options.axis_label) plot.options.axis_label = swap_axis_unit(plot.options.axis_label, from_label, to_label);
            if (s.rounding !== undefined && s.rounding >= 0) s.rounding = unit_decimals(to);
            if (s.range_unit) {
                s.range_unit = to;
                s.range_unit_label = units_config.labels[to];
            }
            if (s.unit) s.unit = to;
            ["axis_min", "axis_max", "axis_soft_min", "axis_soft_max"].forEach(function(key) {
                if (s[key] !== undefined && s[key] !== null && s[key] !== "") s[key] = convert_unit(parseFloat(s[key]), from, to);
            });
            if (s.axis_step) s.axis_step = convert_unit(parseFloat(s.axis_step), from, to, true);
            // A gauge picks its colour by comparing its value with these
            [1, 2, 3, 4, 5, 6, 7].forEach(function(n) {
                var key = "color" + n + "_position";
                if (s[key] !== undefined) s[key] = convert_unit(parseFloat(s[key]), from, to);
            });
        });
    });
    return data;
}

// A line without its unit in the chart file: go by the observation
function series_station_unit(s) {
    var obs = s.observation;
    if (obs === "rainTotal") obs = "rain";
    if (obs === "haysChart") obs = "windSpeed";
    var group = units_config.obs[obs];
    return group ? units_config.groups[group] : null;
}

// "Rain Total (in)" -> "Rain Total (mm)": only the unit in parentheses
function swap_axis_unit(text, from_label, to_label) {
    if (!from_label) return text;
    return text.split("(" + from_label + ")").join("(" + to_label + ")");
}

// "1-3 mph" (wind rose speed bands) -> "2-5 km/h"
function convert_unit_range_text(text) {
    var by_label = {};
    Object.keys(units_config.labels).forEach(function(unit) {
        var label = String(units_config.labels[unit]).trim();
        if (label && alt_unit(unit) && !(label in by_label)) by_label[label] = unit;
    });
    var swap = function(match, a, b, label, pre, plus) {
        var from = by_label[label], to = from && alt_unit(from);
        if (!to) return match;
        var to_label = units_config.labels[to].trim();
        if (b === null) return pre + Math.round(convert_unit(parseFloat(a), from, to)) + plus + " " + to_label;
        return Math.round(convert_unit(parseFloat(a), from, to)) + "-" + Math.round(convert_unit(parseFloat(b), from, to)) + " " + to_label;
    };
    return String(text).replace(/(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*(\S+)\s*$/, function(m, a, b, label) {
        return swap(m, a, b, label, "", "");
    }).replace(/^([<>]?\s*)(\d+(?:\.\d+)?)(\+?)\s*(\S+)\s*$/, function(m, pre, a, plus, label) {
        return swap(m, a, null, label, pre, plus);
    });
}

/* --- Colour scales --------------------------------------------------------- */

var OUTTEMP_COLORS = {
    degree_F: [[0, "#1278c8"], [25, "#30bfef"], [32, "#1fafdd"], [40, "rgba(0,172,223,1)"], [50, "#71bc3c"],
               [55, "rgba(90,179,41,0.8)"], [65, "rgba(131,173,45,1)"], [70, "rgba(206,184,98,1)"],
               [75, "rgba(255,174,0,0.9)"], [80, "rgba(255,153,0,0.9)"], [85, "rgba(255,127,0,1)"],
               [90, "rgba(255,79,0,0.9)"], [95, "rgba(255,69,69,1)"], [110, "rgba(255,104,104,1)"],
               [Infinity, "rgba(218,113,113,1)"]],
    degree_C: [[-17.7, "#1278c8"], [-3.8, "#30bfef"], [0, "#1fafdd"], [4.4, "rgba(0,172,223,1)"], [10, "#71bc3c"],
               [12.7, "rgba(90,179,41,0.8)"], [18.3, "rgba(131,173,45,1)"], [21.1, "rgba(206,184,98,1)"],
               [23.8, "rgba(255,174,0,0.9)"], [26.6, "rgba(255,153,0,0.9)"], [29.4, "rgba(255,127,0,1)"],
               [32.2, "rgba(255,79,0,0.9)"], [35, "rgba(255,69,69,1)"], [43.3, "rgba(255,104,104,1)"],
               [Infinity, "rgba(218,113,113,1)"]]
};

// The colour of a temperature, or undefined for anything that isn't one
function get_outTemp_color(unit, temp) {
    var scale = OUTTEMP_COLORS[unit];
    if (!scale || temp === null || temp === undefined || isNaN(temp)) return undefined;
    var t = Math.round(parseFloat(String(temp).replace("\u2212", "-")));
    for (var i = 0; i < scale.length; i++) if (t <= scale[i][0]) return scale[i][1];
}

// US EPA air quality category colours, softened to suit the pages
function get_aqi_color(aqi) {
    if (aqi >= 301) return "#cc241d";
    if (aqi >= 201) return "#b16286";
    if (aqi >= 151) return "rgba(255,69,69,1)";
    if (aqi >= 101) return "rgba(255,127,0,1)";
    if (aqi >= 51) return "rgba(255,174,0,0.9)";
    return "#71bc3c";
}

// Gauge colour bands from charts.conf: color1 ... color7, each from its colorN_position up, with an optional colorN_label
function gauge_band(value, s) {
    var band = {color: s.color1, label: s.color1_label};
    for (var n = 2; n <= 7; n++) {
        if (s["color" + n] && value >= parseFloat(s["color" + n + "_position"])) {
            band = {color: s["color" + n], label: s["color" + n + "_label"]};
        }
    }
    return band;
}

// The temperature unit on screen now, shown on the switch
function unit_switch_text() {
    return (units_config.labels[display_unit("group_temperature")] || "").trim();
}

// Chart groups drawn on this page, so a switch can draw them again
var charts_shown = [];

function set_units(alt) {
    try { localStorage.setItem("echarts_units", alt ? "alt" : "station"); } catch (e) {}
    wx_all("#unitSwitch span").forEach(function(s) { s.textContent = unit_switch_text(); });
    charts_shown.forEach(function(args) { showChart(args[0], args[1]); });
    document.dispatchEvent(new Event("wx-units"));
}

wx_ready(function() {
    var unit_button = document.getElementById("unitSwitch");
    if (unit_button) {
        unit_button.querySelector("span").textContent = unit_switch_text();
        unit_button.addEventListener("click", function() { set_units(!units_alt_on()); });
    }
    var theme_button = document.getElementById("themeSwitch");
    if (theme_button) {
        theme_button.addEventListener("click", function() { wx_set_theme(wx_is_dark() ? "light" : "dark", true); });
    }
});
