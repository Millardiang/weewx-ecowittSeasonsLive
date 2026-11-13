/* weewx-ecowittSeasonsLive: live current conditions and sensor status from ecwLoop.json, the interactive
 * history charts, and hiding anything that has no value.
 *
 * Needs js/echarts-config.js and js/echarts-common.js (weewx-echarts) and, on pages with charts,
 * js/echarts-charts.js. The page sets ecw_live (settings from EcowittSeasonsSearchList) and
 * ecw_archive (the latest archive record) before loading this file.
 *
 * Copyright (C) 2026 Ian Millard
 * Battery states follow batt_state_desc() of weewx-ecowittGateway / ecowitt_http.py,
 * Copyright (C) 2024-25 Gary Roderick, Copyright (C) 2026 Ian Millard (GPL-3.0).
 *
 * This program is free software: you can redistribute it and/or modify it under the terms of the
 * GNU General Public License as published by the Free Software Foundation, either version 3 of the
 * License, or (at your option) any later version.
 */

var ecw = window.ecw_live || {};
var ecw_labels = ecw.labels || {};

function ecw_label(key, fallback) {
    if (Object.prototype.hasOwnProperty.call(ecw_labels, key) && ecw_labels[key] !== "") return ecw_labels[key];
    return fallback !== undefined ? fallback : key;
}

function ecw_esc(text) {
    return String(text).replace(/[&<>"']/g, function(c) {
        return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c];
    });
}

// Is v a reading worth showing? No null, no NaN, no empty string.
function ecw_present(v) {
    if (v === null || v === undefined || v === "") return false;
    if (typeof v === "number") return isFinite(v);
    if (typeof v === "string") {
        var t = v.trim().toUpperCase();
        return t !== "" && t !== "N/A" && t !== "NONE" && t !== "NAN";
    }
    return true;
}

/* --- Values: unit conversion and formatting ----------------------------------------------------------- */

// [value in the report's units (or the visitor's, after the unit switch), unit] for a field of a packet
function ecw_convert(field, value, us_units) {
    var group = (ecw.obs_groups || {})[field];
    if (!group) return [value, null, null];
    var conv = ((ecw.conversions || {})[String(us_units)] || {})[group];
    if (!conv) return [value, null, group];
    var v = value * conv[0] + conv[1], unit = conv[2];
    // The visitor's unit switch (echarts-common.js), for the groups it covers
    if (typeof display_unit === "function" && typeof units_config !== "undefined" && units_config.groups[group]) {
        var shown = display_unit(group);
        var temps = /^degree_[CF]$/;
        var convertible = (temps.test(shown) && temps.test(unit)) ||
            (UNIT_FACTOR[shown] !== undefined && UNIT_FACTOR[unit] !== undefined);
        if (shown && shown !== unit && convertible) {
            v = convert_unit(v, unit, shown, false);
            unit = shown;
        }
    }
    return [v, unit, group];
}

function ecw_decimals(unit) {
    var m = /%\.(\d+)f/.exec((ecw.unit_formats || {})[unit] || "");
    return m ? parseInt(m[1], 10) : null;
}

function ecw_unit_label(unit) {
    var l = (ecw.unit_labels || {})[unit];
    return l === undefined || l === null ? "" : l;
}

function ecw_number(v, decimals) {
    if (typeof wx_number_format === "function") return wx_number_format(v, decimals === null ? -1 : decimals);
    return decimals === null ? String(v) : Number(v).toFixed(decimals);
}

function ecw_compass(deg) {
    var o = ecw.ordinates || [];
    if (o.length >= 16) return o[Math.round(((+deg % 360) + 360) % 360 / 22.5) % 16];
    return typeof wx_compass === "function" ? wx_compass(deg) : "";
}

function ecw_time(ts) {
    if (typeof tzAdjustedMoment === "function") return tzAdjustedMoment(ts).format("L LT");
    return new Date(ts * 1000).toLocaleString();
}

// A field's value as text, or null if it has none
function ecw_format(field, packet) {
    var raw = packet[field];
    if (!ecw_present(raw)) return null;
    if (typeof raw !== "number") {
        var n = Number(raw);
        if (!isFinite(n)) return ecw_esc(raw);
        raw = n;
    }
    var c = ecw_convert(field, raw, packet.usUnits), v = c[0], unit = c[1], group = c[2];
    if (group === "group_direction") return ecw_esc(ecw_compass(v)) + " (" + Math.round(v) + "&deg;)";
    if (group === "group_time") return ecw_esc(ecw_time(v));
    if (group === "group_boolean") return ecw_esc(v ? ecw_label("live_yes", "Yes") : ecw_label("live_no", "No"));
    if (/^leak\d+$/.test(field)) return ecw_esc(v ? ecw_label("live_leak", "LEAK") : ecw_label("live_dry", "Dry"));
    var decimals = unit ? ecw_decimals(unit) : null;
    if (group === "group_count" && decimals === null) decimals = 0;
    return ecw_esc(ecw_number(v, decimals) + (unit ? ecw_unit_label(unit) : ""));
}

/* --- Current conditions --------------------------------------------------------------------------------- */

var ECW_SENSOR_FIELD = /^(w[hns]\d+[a-z]?)(?:_ch(\d+))?_(batt|sig|volt)$/;
var ECW_NOT_READINGS = ["dateTime", "usUnits", "interval", "gateway_online"];

// The label of a row; a tipping (t_) or piezo (p_) rain field says which when both gauges report
function ecw_row_label(field, packet) {
    var label = ecw_label(field, field);
    var m = /^([tp])_(.*)$/.exec(field);
    if (m) {
        var other = (m[1] === "t" ? "p_" : "t_") + m[2];
        if (ecw_present(packet[other])) {
            label += " " + ecw_label(m[1] === "t" ? "live_tipping" : "live_piezo", m[1] === "t" ? "(tipping)" : "(piezo)");
        }
    }
    return ecw_esc(label);
}

// "outTemp" or "extraTemp1+extraHumid1": one row, the label of the first field present
function ecw_row(spec, packet, used) {
    var fields = spec.split("+").map(function(f) { return f.trim(); }).filter(Boolean);
    var parts = [], first = null;
    fields.forEach(function(f) {
        used[f] = true;
        var text = ecw_format(f, packet);
        if (text === null) return;
        if (first === null) first = f;
        var dir = (ecw.obs_groups || {})[f] === "group_direction";
        parts.push((parts.length ? (dir ? " " : " &middot; ") : "") + text);
    });
    if (first === null) return "";
    return '<tr><td class="label">' + ecw_row_label(first, packet) + '</td><td class="data">' + parts.join("") + "</td></tr>";
}

function ecw_render_current(packet) {
    var table = document.getElementById("ecw_current_table");
    if (!table || !packet) return;
    var used = {}, html = "", shown = 0;
    (ecw.sections || []).forEach(function(sec) {
        var rows = sec.rows.map(function(r) { return ecw_row(r, packet, used); }).join("");
        if (rows) {
            shown++;
            html += '<tr class="ecw_section"><th colspan="2">' + ecw_esc(ecw_label(sec.title, sec.title)) + "</th></tr>" + rows;
        }
    });
    if (ecw.show_unlisted) {
        var rows = Object.keys(packet).sort().filter(function(f) {
            return !used[f] && ECW_NOT_READINGS.indexOf(f) < 0 && !ECW_SENSOR_FIELD.test(f) && typeof packet[f] === "number";
        }).map(function(f) { return ecw_row(f, packet, used); }).join("");
        if (rows) html += '<tr class="ecw_section"><th colspan="2">' + ecw_esc(ecw_label("live_other", "Other")) + "</th></tr>" + rows;
    }
    // One section: no heading needed
    if (shown === 1 && !ecw.show_unlisted) html = html.replace(/<tr class="ecw_section">.*?<\/tr>/, "");
    table.innerHTML = html || '<tr><td class="ecw_none">' + ecw_esc(ecw_label("live_waiting", "Waiting for data")) + "</td></tr>";
}

/* --- Sensor status --------------------------------------------------------------------------------------- */

function ecw_battery(model, value, volts) {
    var type = (ecw.battery_types || {})[model] || "level";
    if (type === "volts" || (volts !== undefined && volts !== null)) {
        var v = (volts !== undefined && volts !== null) ? volts : value;
        var low = v <= (ecw.low_volts || 1.2);
        return ['<span class="' + (low ? "status_low" : "status_ok") + '">' +
                ecw_esc(low ? ecw_label("live_low", "LOW") : ecw_label("live_ok", "OK")) + "</span>",
                ecw_number(v, 2) + " V"];
    }
    if (type === "binary") {
        if (value === 0) return ['<span class="status_ok">' + ecw_esc(ecw_label("live_ok", "OK")) + "</span>", ""];
        if (value === 1) return ['<span class="status_low">' + ecw_esc(ecw_label("live_low", "LOW")) + "</span>", ""];
        return null;
    }
    // level: 0-5, 0 or 1 low, 6 on DC power
    if (value === 6) return ['<span class="status_ok">' + ecw_esc(ecw_label("live_dc", "DC")) + "</span>", ""];
    if (value >= 0 && value <= 5) {
        return ['<span class="' + (value <= 1 ? "status_low" : "status_ok") + '">' +
                ecw_esc(value <= 1 ? ecw_label("live_low", "LOW") : ecw_label("live_ok", "OK")) + "</span>",
                ecw_esc(value + "/5")];
    }
    return null;
}

function ecw_signal(sig) {
    var bars = Math.max(0, Math.min(4, Math.round(sig)));
    var html = '<span class="ecw_signal" title="' + bars + '/4">';
    for (var i = 1; i <= 4; i++) html += '<span class="ecw_bar ecw_bar' + i + (i <= bars ? " on" : "") + '"></span>';
    return html + "</span>";
}

function ecw_sensor_name(key, model, ch) {
    var names = ecw.sensor_names || {};
    if (names[key]) return names[key];
    var base = names[model] || model.toUpperCase();
    return ch ? base + " " + ecw_label("live_channel", "ch") + " " + ch : base;
}

function ecw_render_sensors(packet) {
    var table = document.getElementById("ecw_sensors_live");
    if (!table || !packet) return false;
    var sensors = {}, order = [];
    Object.keys(packet).forEach(function(f) {
        var m = ECW_SENSOR_FIELD.exec(f);
        if (!m || !ecw_present(packet[f])) return;
        var key = m[1] + (m[2] ? "_ch" + m[2] : "");
        if (!sensors[key]) { sensors[key] = {model: m[1], ch: m[2] ? +m[2] : 0}; order.push(key); }
        sensors[key][m[3]] = Number(packet[f]);
    });
    order.sort(function(a, b) {
        var x = sensors[a], y = sensors[b];
        return x.model === y.model ? x.ch - y.ch : (x.model < y.model ? -1 : 1);
    });
    var rows = order.map(function(key) {
        var s = sensors[key];
        var batt = s.batt !== undefined ? ecw_battery(s.model, s.batt, s.volt) : null;
        var lost = s.sig === 0;
        return '<tr' + (lost ? ' class="ecw_lost"' : "") + '><td class="label">' + ecw_esc(ecw_sensor_name(key, s.model, s.ch)) + "</td>" +
            '<td class="data">' + (s.sig !== undefined ? ecw_signal(s.sig) : "") + "</td>" +
            '<td class="data">' + (batt ? batt[0] : "") + "</td>" +
            '<td class="timestamp">' + (batt ? batt[1] : "") + (lost ? " " + ecw_esc(ecw_label("live_no_signal", "no signal")) : "") + "</td></tr>";
    }).join("");
    var gw = "";
    if (ecw_present(packet.gateway_online)) {
        gw = '<tr><td class="label">' + ecw_esc(ecw_label("gateway_online", "Gateway")) + '</td><td class="data" colspan="3">' +
            (packet.gateway_online ? '<span class="status_ok">' + ecw_esc(ecw_label("live_online", "online")) + "</span>"
                                   : '<span class="status_low">' + ecw_esc(ecw_label("live_offline", "offline")) + "</span>") + "</td></tr>";
    }
    if (!rows && !gw) return false;
    table.innerHTML = '<tr><th>' + ecw_esc(ecw_label("live_sensor", "Sensor")) + "</th><th>" +
        ecw_esc(ecw_label("live_signal", "Signal")) + "</th><th>" + ecw_esc(ecw_label("live_battery", "Battery")) +
        "</th><th></th></tr>" + gw + rows;
    return true;
}

/* --- Polling ecwLoop.json -------------------------------------------------------------------------------- */

var ecw_packet = null, ecw_is_live = false, ecw_timer = null, ecw_failures = 0;

function ecw_status() {
    var el = document.getElementById("ecw_live_status");
    if (!el || !ecw_packet) return;
    var age = Math.max(0, Math.round(Date.now() / 1000 - (ecw_packet.dateTime || 0)));
    var text, cls;
    if (!ecw_is_live) {
        text = ecw_label("live_archive", "Last archive record") + ", " + ecw_time(ecw_packet.dateTime);
        cls = "ecw_archive";
    } else if (age > ecw.stale) {
        text = ecw_label("live_stale", "No live data since") + " " + ecw_time(ecw_packet.dateTime);
        cls = "ecw_stale";
    } else {
        text = ecw_esc(ecw_label("live_live", "Live")) + " &middot; " + (age < 60 ? age + " s" : Math.round(age / 60) + " min");
        cls = "ecw_fresh";
    }
    el.className = "ecw_status " + cls;
    el.innerHTML = '<span class="ecw_dot"></span>' + (cls === "ecw_fresh" ? text : ecw_esc(text));
}

function ecw_show(packet, live) {
    ecw_packet = packet;
    ecw_is_live = live;
    ecw_render_current(packet);
    var has_live_sensors = live && ecw_render_sensors(packet);
    var live_box = document.getElementById("ecw_sensors_live");
    var archive_box = document.getElementById("ecw_sensors_archive");
    if (live_box) live_box.style.display = has_live_sensors ? "" : "none";
    if (archive_box) archive_box.style.display = has_live_sensors ? "none" : "";
    var widget = document.getElementById("sensors_widget");
    if (widget) widget.style.display = (has_live_sensors || (archive_box && archive_box.dataset.hasData === "1")) ? "" : "none";
    ecw_status();
}

// The places ecwLoop.json may be (the first is where the report found it); the one that answers is kept
var ecw_urls = (ecw.urls && ecw.urls.length ? ecw.urls : [ecw.url]).filter(Boolean);
var ecw_url_index = 0;

function ecw_poll() {
    clearTimeout(ecw_timer);
    if (!ecw.enabled || !ecw_urls.length) return;
    var next = function() {
        // Slow down while ecwLoop.json can't be read
        var wait = ecw.poll * 1000 * Math.min(6, 1 + Math.floor(ecw_failures / ecw_urls.length));
        ecw_timer = setTimeout(function() { if (!document.hidden) ecw_poll(); }, wait);
    };
    var url = ecw_urls[ecw_url_index];
    wx_json(url).then(function(packet) {
        if (!packet || typeof packet !== "object" || !packet.dateTime) throw new Error("not a loop packet");
        ecw_failures = 0;
        ecw.url = url;
        // ecwLoop.json older than the archive record shown: keep the record
        if (!ecw_is_live && ecw_packet && packet.dateTime < ecw_packet.dateTime) {
            ecw_status();
        } else {
            ecw_show(packet, true);
        }
        next();
    }).catch(function(e) {
        ecw_failures++;
        if (ecw_failures <= ecw_urls.length) console.log("ecowittSeasons: cannot read " + url + ": " + e.message);
        // Try the next place at once, until each has been tried
        ecw_url_index = (ecw_url_index + 1) % ecw_urls.length;
        ecw_status();
        if (ecw_failures < ecw_urls.length) ecw_poll();
        else next();
    });
}

/* --- Charts ---------------------------------------------------------------------------------------------- */

// Does a line have a value anywhere in its data? Points are [time, value...] or plain numbers (wind rose)
function ecw_series_has_data(s) {
    var data = s.data;
    if (data === undefined || data === null) return true;  // a kind of chart this doesn't know: draw it
    if (!Array.isArray(data)) return ecw_present(data);
    var timed = data.length && Array.isArray(data[0]) && typeof data[0][0] === "number" && data[0][0] > 1e11;
    return data.some(function(p) {
        if (timed) return p.slice(1).some(function(x) { return ecw_present(x); });
        if (Array.isArray(p)) return p.some(function(x) { return typeof x === "number" ? x !== 0 : ecw_present(x); });
        if (p && typeof p === "object") return ecw_present(p.value !== undefined ? p.value : p.y);
        return typeof p === "number" ? (s.observation === "windRose" ? p !== 0 : isFinite(p)) : ecw_present(p);
    });
}

// Called by showChart (echarts-charts.js) with a chart group's data: drop the lines with no data,
// then the charts with none left, and hide their places on the page.
function wx_filter_chart_group(data, json_file, prepend) {
    Object.keys(data).forEach(function(plotname) {
        var plot = data[plotname];
        if (!plot || !plot.options || !plot.series) return;
        Object.keys(plot.series).forEach(function(name) {
            if (!ecw_series_has_data(plot.series[name])) delete plot.series[name];
        });
        var id = prepend ? json_file + "_" + plot.options.id : plot.options.id;
        var div = document.getElementById(id);
        if (!Object.keys(plot.series).length) {
            delete data[plotname];
            if (div && div.parentElement) div.parentElement.style.display = "none";
        } else if (div && div.parentElement) {
            div.parentElement.style.display = "";
        }
    });
    ecw_empty_note(json_file);
}

function ecw_empty_note(group) {
    var grid = document.querySelector('.wx-chart-grid[data-group="' + group + '"]');
    if (!grid) return;
    var visible = Array.prototype.some.call(grid.children, function(c) { return c.style.display !== "none"; });
    var note = grid.parentElement.querySelector(".wx-empty");
    if (note) note.style.display = visible ? "none" : "";
}

// The history widget (index and telemetry pages): a period's charts are drawn the first time it is shown
var ecw_drawn = {};
function ecw_show_period(period) {
    var container = document.getElementById("history_" + period);
    if (!container || typeof showChart !== "function") return;
    var group = (container.dataset.chartPrefix || "") + period;
    if (ecw_drawn[group]) {
        if (typeof wx_charts_resize === "function") setTimeout(wx_charts_resize, 0);
        return;
    }
    ecw_drawn[group] = true;
    var charts = (typeof chart_groups !== "undefined" && chart_groups[group]) || [];
    var empty = '<p class="wx-empty"' + (charts.length ? ' style="display:none"' : "") + ">" +
        ecw_esc(ecw_label("charts_no_data", "No chart data yet. Charts appear after the next report.")) + "</p>";
    container.innerHTML = empty + '<div class="wx-chart-grid" data-group="' + ecw_esc(group) + '">' + charts.map(function(id) {
        return '<div class="wx-chart"><div id="' + ecw_esc(group + "_" + id) + '" style="width:100%;height:100%;"></div></div>';
    }).join("") + "</div>";
    if (charts.length) showChart(group, true);
}

/* --- No N/A: rows whose every value is empty are hidden --------------------------------------------------- */

function ecw_hide_empty_rows(root) {
    (root || document).querySelectorAll(".widget table tr").forEach(function(tr) {
        if (tr.closest("#ecw_current_table, #ecw_sensors_live")) return;
        var cells = tr.querySelectorAll("td.data");
        if (!cells.length) return;
        var empty = Array.prototype.every.call(cells, function(td) { return !ecw_present(td.textContent.replace(/\s+/g, " ")); });
        if (empty) tr.style.display = "none";
    });
}

/* --- Start ----------------------------------------------------------------------------------------------- */

function ecw_setup() {
    ecw_hide_empty_rows();
    if (document.getElementById("ecw_current_table") || document.getElementById("ecw_sensors_live")) {
        var archive = window.ecw_archive || {};
        if (archive.dateTime) ecw_show(archive, false);
        else ecw_render_current({});
        ecw_poll();
        setInterval(ecw_status, 1000);
        document.addEventListener("visibilitychange", function() { if (!document.hidden) ecw_poll(); });
        document.addEventListener("wx-units", function() { if (ecw_packet) ecw_show(ecw_packet, ecw_is_live); });
    }
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", ecw_setup);
else ecw_setup();
