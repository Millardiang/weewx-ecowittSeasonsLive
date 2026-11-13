// weewx-echarts: draws the charts of charts.conf with Apache ECharts (Apache License 2.0).
// Adapted from the Belchertown skin's chart code by Pat O'Brien (GPL-3.0).
// weewx-ecowittSeasonsLive: chart colours come from the skin's CSS, and a chart group's data passes through
// wx_filter_chart_group() (ecowitt-seasons.js) so charts with no data are not drawn.

// The chart groups of charts.conf: their charts, titles and page text
var chart_groups = config.charts;
var group_titles = config.group_titles;
var group_content = config.group_content;
// Compass labels on the wind direction axis
var weatherdirection = config.windDir_ordinals;

/* ---------------------------------------------------------------------------
 * Chart rendering with Apache ECharts (Apache License 2.0).
 *
 * echarts.py writes one JSON file per chart group, with each chart's options
 * and lines in this skin's option names (charts.conf); they are turned into
 * ECharts options here.
 * ------------------------------------------------------------------------- */

// Charts on this page, by the id of their div, so they can be redrawn on theme change and resized
var wx_charts = {};

// Chart colours of the Seasons skin's plots: grey labels, light grid lines, dark titles (and a dark version)
function wx_chart_theme() {
    var css = getComputedStyle(document.documentElement);
    var v = function(name, fallback) { return (css.getPropertyValue(name) || "").trim() || fallback; };
    var dark = wx_is_dark();
    return {background: v("--chart-background-color", dark ? "#16211f" : "#ffffff"),
            text: v("--chart-text-color", dark ? "#9fb5b1" : "#5f7471"),
            title: v("--chart-title-color", dark ? "#7fd3c7" : "#007a73"),
            grid: v("--chart-grid-color", dark ? "#2c3f3c" : "#d6e6e4"),
            axis: v("--chart-axis-color", dark ? "#5f7a76" : "#7d9693"),
            tooltip: v("--chart-tooltip-color", dark ? "rgba(22, 33, 31, 0.96)" : "rgba(255, 255, 255, 0.96)"),
            tooltipText: v("--text-color", dark ? "#dcebe8" : "#1d2b29"),
            tooltipBorder: v("--section-border-color", dark ? "#3f5a56" : "#99c2bd"),
            credits: v("--muted-color", "#9aaeab")};
}

function wx_font() {
    return getComputedStyle(document.body).fontFamily || "sans-serif";
}

// Offset (ms) that makes the browser's local time read as the station's local time.
// ECharts places time-axis ticks in browser time, so the x values are shifted before plotting.
var wx_tz_shift_cache = {};
function wx_tz_shift(ms) {
    var hour = Math.floor(ms / 3600000);
    if (wx_tz_shift_cache[hour] === undefined) {
        var station = tzAdjustedMoment(ms / 1000).utcOffset();
        var browser = -new Date(ms).getTimezoneOffset();
        wx_tz_shift_cache[hour] = (station - browser) * 60000;
    }
    return wx_tz_shift_cache[hour];
}

function wx_bool(value) {
    return value === true || value === 1 || value === "1" || String(value).toLowerCase() === "true";
}

function wx_esc(text) {
    return String(text === undefined || text === null ? "" : text).replace(/[&<>"']/g, function(c) {
        return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c];
    });
}

// Strip any HTML a title may carry (the chart builder escapes its titles) and decode entities for the canvas
function wx_plain(text) {
    var div = document.createElement("div");
    div.innerHTML = String(text === undefined || text === null ? "" : text);
    return div.textContent;
}

// Chart types (charts.conf type =)
var WX_TYPES = {line: "line", smooth: "smooth", area: "area", smooth_area: "smooth_area", column: "column", dots: "dots"};
// line_style: solid, dashed, dotted, and the finer dash patterns
var WX_DASH = {
    solid: "solid", dashed: "dashed", dash: "dashed", dotted: "dotted", dot: "dotted",
    short_dash: [6, 2], long_dash: [16, 6], short_dot: [2, 2], dash_dot: [8, 6, 2, 6], short_dash_dot: [6, 2, 2, 2],
    short_dash_dot_dot: [6, 2, 2, 2, 2, 2], long_dash_dot: [16, 6, 2, 6], long_dash_dot_dot: [16, 6, 2, 6, 2, 6]
};
// marker_shape
var WX_SYMBOL = {circle: "circle", square: "rect", diamond: "diamond", triangle: "triangle", triangle_down: "path://M0,0L10,0L5,10Z"};
// Every option a line can have; with echarts_debug = 1 others are listed in the browser console
var WX_KNOWN_OPTIONS = ["section", "observation", "name", "data", "unit", "rounding", "polar", "color", "type", "layer",
    "line_width", "line_color", "line_style", "markers", "marker_size", "marker_shape", "visible", "step", "fill_color",
    "fill_opacity", "opacity", "connect_gaps", "gap_size", "stack", "in_legend", "in_tooltip", "value_labels", "right_axis",
    "axis_label", "axis_unit", "axis_min", "axis_max", "axis_soft_min", "axis_soft_max", "axis_step", "axis_minor_ticks",
    "mirrored", "number_format", "aggregate_type", "aggregate_interval", "average_type", "time_length", "time_ago",
    "range_observation", "range_unit", "range_unit_label", "band", "css_class", "data_binding", "start_at_midnight",
    "start_at_whole_hour", "start_at_beginning_of_month", "day_specific", "month_specific", "year_specific",
    "timespan_start", "timespan_stop", "group_by", "categories", "speed_colors", "colors_enabled", "color1", "color2",
    "color3", "color4", "color5", "color6", "color7", "color1_label", "color2_label", "color3_label", "color4_label",
    "color5_label", "color6_label", "color7_label", "color2_position", "color3_position", "color4_position",
    "color5_position", "color6_position", "color7_position", "aqi_observation", "aqi_average", "axis_index"];

function showChart(json_file, prepend_renderTo = false) {
    if (!charts_shown.some(function(c) { return c[0] === json_file; })) charts_shown.push([json_file, prepend_renderTo]);
    // Relative URL by finding what page we're on currently.
    var font_ready = document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve();
    Promise.all([wx_json(get_relative_url() + '/json/' + json_file + '.json'), font_ready]).then(function(loaded) {
        var data = loaded[0];
        if (units_alt_on()) convert_chart_units(data);
        if (typeof wx_filter_chart_group === "function") wx_filter_chart_group(data, json_file, prepend_renderTo);
        var group = {
            colors: data.colors.split(","),
            credits: data.credits.split(",")[0],
            credits_url: data.credits_url.split(",")[0],
            credits_position: data.credits_position
        };
        Object.keys(data).forEach(function(plotname) {
            var plot = data[plotname];
            if (plot && plot.options) {
                // One bad chart must not take the rest of the chart group with it
                try {
                    render_chart(plot, group, json_file, prepend_renderTo);
                } catch (e) {
                    console.log("ERROR: Cannot draw chart " + plotname + " of " + json_file + ": " + e.message);
                }
            }
        });
    }).catch(function(e) {
        console.log(e);
        // The page can say there's nothing to show yet
        document.dispatchEvent(new CustomEvent("wx-chart-error", {detail: json_file}));
    });
}

// Build one chart from its entry in a chart group's JSON file.
function render_chart(plot, group, json_file, prepend_renderTo) {
    var opt = plot.options;
    var renderTo = prepend_renderTo ? json_file + "_" + opt.id : opt.id;
    var div = document.getElementById(renderTo);
    if (!div) return;

    wx_debug(renderTo + ": building a " + opt.type + " chart");

    if (opt.css_class) {
        div.classList.add.apply(div.classList, opt.css_class.split(/\s+/).filter(Boolean));
        wx_debug(renderTo + ": adding CSS class: " + opt.css_class);
    }

    // Apply any width, height CSS overrides to the parent div of the chart
    var chart_parent = div.parentElement;
    if (opt.height && chart_parent) {
        chart_parent.style.height = opt.height;
        chart_parent.style.padding = '0px 15px';
        chart_parent.style.marginBottom = '20px';
    }
    if (opt.width && chart_parent) {
        // A chart with its own width gets a row of the chart grid to itself
        chart_parent.style.width = opt.width;
        chart_parent.style.gridColumn = "1 / -1";
    }
    // 400 pixels high when the page gives the chart no height
    if (div.clientHeight < 50) div.style.height = "400px";
    div.classList.add("wx-echart");

    var series_list = Object.keys(plot.series).map(function(name) { return plot.series[name]; });
    // Special charts are known by the observation of their (last) line: windRose, aqiChart, ...
    var observation_type = series_list.length ? series_list[series_list.length - 1].observation : undefined;
    var is_gauge = opt.type == "gauge" || series_list.some(function(s) { return s.type == "gauge"; });

    var chart = echarts.getInstanceByDom(div) || echarts.init(div, null, {renderer: "canvas"});
    // Gauges and the wind rose lay themselves out for the chart's size, so a new size draws them again
    var redraw_on_resize = is_gauge || ["windRose", "aqiChart", "haysChart", "weatherRange"].indexOf(observation_type) >= 0;
    wx_charts[renderTo] = {chart: chart, plot: plot, group: group, json_file: json_file, prepend: prepend_renderTo,
                           redraw_on_resize: redraw_on_resize, width: div.clientWidth, height: div.clientHeight};
    if (!div.wx_observed && window.ResizeObserver) {
        div.wx_observed = true;
        new ResizeObserver(function() {
            var c = echarts.getInstanceByDom(div), entry = wx_charts[renderTo];
            if (!c) return;
            c.resize();
            if (entry && entry.redraw_on_resize && (entry.width !== div.clientWidth || entry.height !== div.clientHeight)) {
                render_chart(entry.plot, entry.group, entry.json_file, entry.prepend);
            }
        }).observe(div);
    }

    var size = {width: div.clientWidth, height: div.clientHeight};
    var options;
    if (observation_type == "windRose") options = wx_windrose_options(plot, group, renderTo, size.width, size.height);
    else if (observation_type == "aqiChart") options = wx_aqi_options(plot, group, renderTo, size);
    else if (observation_type == "haysChart") options = wx_hays_options(plot, group, renderTo, size.width);
    else if (observation_type == "weatherRange") options = wx_weather_range_options(plot, group, renderTo, size.width);
    else if (is_gauge) options = wx_gauge_options(plot, group, renderTo, size);
    else options = wx_line_chart_options(plot, group, renderTo, size.width);
    var wx_time = options.wx_time;
    delete options.wx_time;
    chart.setOption(options, true);
    chart.wx_tick_target = wx_time ? wx_time.target : 8;
    wx_enable_zoom(chart, options, wx_time);

    wx_debug(options);
    wx_debug("echarts option for " + renderTo + ": " + JSON.stringify(options, function(k, v) { return typeof v === "function" ? "[function]" : v; }));
}

// Time axis ticks at regular calendar steps (every 2 hours, every 2 days, monthly...) in station time,
// at most about `target` of them. ECharts' own ticks add month and day boundaries between the regular ones.
var WX_TICK_STEPS = [[15, "m"], [30, "m"], [1, "h"], [2, "h"], [3, "h"], [4, "h"], [6, "h"], [12, "h"], [1, "d"], [2, "d"],
                     [3, "d"], [7, "d"], [14, "d"], [1, "M"], [2, "M"], [3, "M"], [6, "M"], [1, "y"], [2, "y"], [5, "y"]];
var WX_UNIT_MS = {m: 60000, h: 3600000, d: 86400000, M: 2629800000, y: 31557600000};
function wx_time_ticks(lo, hi, target) {
    if (!isFinite(lo) || !isFinite(hi) || hi <= lo) return [];
    var step = WX_TICK_STEPS[WX_TICK_STEPS.length - 1];
    for (var i = 0; i < WX_TICK_STEPS.length; i++) {
        if ((hi - lo) / (WX_TICK_STEPS[i][0] * WX_UNIT_MS[WX_TICK_STEPS[i][1]]) <= target) { step = WX_TICK_STEPS[i]; break; }
    }
    var n = step[0], unit = step[1];
    var d = new Date(lo);
    if (unit == "y") d = new Date(Math.floor(d.getFullYear() / n) * n, 0, 1);
    else if (unit == "M") d = new Date(d.getFullYear(), Math.floor(d.getMonth() / n) * n, 1);
    else if (unit == "d") d = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    else d = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    var ticks = [];
    for (var guard = 0; d.getTime() <= hi && guard < 5000; guard++) {
        if (d.getTime() >= lo) ticks.push(d.getTime());
        if (unit == "y") d = new Date(d.getFullYear() + n, 0, 1);
        else if (unit == "M") d = new Date(d.getFullYear(), d.getMonth() + n, 1);
        else if (unit == "d") d = new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
        else d = new Date(d.getTime() + n * WX_UNIT_MS[unit]);
    }
    return ticks;
}

function wx_set_time_ticks(chart, lo, hi) {
    var ticks = wx_time_ticks(lo, hi, chart.wx_tick_target || 8);
    chart.setOption({xAxis: {axisLabel: {customValues: ticks}, axisTick: {customValues: ticks}}});
}

// A time axis label (the axis values are shifted to station time): times in the visitor's locale
// (3:00 PM, 15:00), the date at midnight, the month on the 1st of long spans
function wx_time_axis_label(value, days) {
    var d = new Date(value);
    if (d.getHours() === 0 && d.getMinutes() === 0) {
        if (days > 60 && d.getDate() === 1) return dayjs(d).format("MMM YY");
        return dayjs(d).format("D MMM");
    }
    return d.toLocaleTimeString(dayjs.locale(), {hour: "numeric", minute: "2-digit"});
}

// Title, legend, toolbox and colours every chart shares
function wx_base_options(opt, group, renderTo) {
    var t = wx_chart_theme();
    var has_subtitle = opt.subtitle && opt.subtitle != "";
    var options = {
        backgroundColor: t.background,
        textStyle: {fontFamily: wx_font(), color: t.text},
        color: group.colors.map(function(c) { return c.trim(); }),
        animationDuration: 600,
        title: {
            text: wx_plain(opt.title),
            subtext: has_subtitle ? wx_plain(opt.subtitle) : "",
            link: "#" + renderTo, // Anchor link to chart for direct linking
            target: "self",
            left: "center",
            top: 4,
            textStyle: {color: t.title, fontSize: 14, fontWeight: "bold", fontFamily: wx_font()},
            subtextStyle: {color: t.text, fontSize: 12}
        },
        legend: {
            show: wx_bool(opt.legend),
            bottom: 4,
            icon: "roundRect",
            itemWidth: 14,
            itemHeight: 3,
            textStyle: {color: t.text, fontSize: 12},
            inactiveColor: wx_is_dark() ? "#555" : "#ccc"
        },
        grid: {
            top: has_subtitle ? 70 : 50,
            bottom: wx_bool(opt.legend) ? 40 : 15,
            left: 10,
            right: 10,
            outerBoundsMode: "same",
            outerBoundsContain: "all"
        },
        toolbox: {
            right: 8,
            top: 4,
            itemSize: 14,
            iconStyle: {borderColor: t.text},
            feature: {
                saveAsImage: {show: wx_bool(opt.download_button), name: wx_plain(opt.title) || renderTo, backgroundColor: t.background,
                              title: (config.chart_texts && config.chart_texts.downloadPNG) || "Download PNG image"}
            }
        },
        graphic: []
    };

    // A credit line from the config (credits, credits_url, credits_position)
    if (group.credits) {
        var pos = {};
        try { if (group.credits_position) pos = JSON.parse(group.credits_position); } catch (e) {}
        var align = pos.align || "right";
        var credit = {
            type: "text", bottom: 2 - (parseFloat(pos.y) || 0), z: 100,
            style: {text: group.credits, fill: t.credits, font: "10px " + wx_font()}
        };
        credit[align === "left" ? "left" : align === "center" ? "center" : "right"] = align === "center" ? "center" : 10 + Math.abs(parseFloat(pos.x) || 0);
        if (group.credits_url) {
            credit.cursor = "pointer";
            credit.onclick = function() { window.location.href = group.credits_url; };
        }
        options.graphic.push(credit);
        if (wx_bool(opt.legend)) options.legend.bottom = 16;
        options.grid.bottom += 12;
    }
    return options;
}

// Line, spline, area, column and scatter charts on a time (or category) x axis
function wx_line_chart_options(plot, group, renderTo, width) {
    var opt = plot.options;
    var t = wx_chart_theme();
    var options = wx_base_options(opt, group, renderTo);
    var tooltip_date_format = opt.tooltip_date_format;
    var categories = opt.categories && opt.categories.length >= 1 ? opt.categories : null;
    var series_list = Object.keys(plot.series).map(function(name) { return plot.series[name]; });

    // y axes: the left one, and a right one if any line has right_axis = true
    var axes = [{opposite: false, label: "", extent: [Infinity, -Infinity], hasBar: false}];
    series_list.forEach(function(s) {
        s.axis_index = wx_bool(s.right_axis) ? 1 : 0;
        if (s.axis_index == 1 && axes.length == 1) axes.push({opposite: true, label: "", extent: [Infinity, -Infinity], hasBar: false});
    });

    var gap_size = parseFloat(opt.gap_size) || 0;
    var connect_gaps = wx_bool(opt.connect_gaps);
    var span = [Infinity, -Infinity];

    options.series = series_list.map(function(s, i) {
        var axis = axes[s.axis_index];
        // The axis title comes from the last line on the axis
        axis.label = s.axis_label;
        var type = WX_TYPES[(s.type || opt.type || "line").toLowerCase()] || "line";
        var line_width = s.line_width !== undefined ? parseFloat(s.line_width) : 1.5;
        var markers = s.markers !== undefined ? wx_bool(s.markers) : (type == "dots");
        var es = {
            name: s.name,
            yAxisIndex: s.axis_index,
            z: 2 + (parseFloat(s.layer) || 0),
            connectNulls: s.connect_gaps !== undefined ? wx_bool(s.connect_gaps) : connect_gaps,
            emphasis: {focus: "none", scale: 1.5}
        };
        if (type == "column") {
            es.type = "bar";
            es.barMaxWidth = 30;
            axis.hasBar = true;
        } else if (type == "dots" || line_width === 0) {
            // A line with no line (the wind direction dots) is dots
            es.type = "scatter";
            es.large = true;
        } else {
            es.type = "line";
            es.smooth = (type == "smooth" || type == "smooth_area") ? 0.3 : false;
            es.lineStyle = {width: line_width};
            es.showSymbol = markers;
            es.symbol = "circle";
            if (type == "area" || type == "smooth_area") {
                es.areaStyle = {opacity: s.fill_opacity !== undefined ? parseFloat(s.fill_opacity) : 0.75, origin: "start"};
                if (s.fill_color) es.areaStyle.color = s.fill_color;
            }
            if (s.step) es.step = ["start", "middle", "end"].indexOf(s.step) >= 0 ? s.step : "start";
        }
        if (es.type != "bar") {
            es.symbolSize = s.marker_size !== undefined ? parseFloat(s.marker_size) : 4;
            if (s.marker_shape && WX_SYMBOL[s.marker_shape]) es.symbol = WX_SYMBOL[s.marker_shape];
        }
        if (s.color) {
            es.itemStyle = {color: s.color};
            if (es.lineStyle) es.lineStyle.color = s.color;
        }
        if (s.line_color && es.lineStyle) es.lineStyle.color = s.line_color;
        if (s.line_style && es.lineStyle) es.lineStyle.type = WX_DASH[String(s.line_style).toLowerCase()] || "solid";
        if (s.opacity !== undefined) {
            es.itemStyle = es.itemStyle || {};
            es.itemStyle.opacity = parseFloat(s.opacity);
            if (es.lineStyle) es.lineStyle.opacity = parseFloat(s.opacity);
        }
        // stack = true stacks the lines of one axis; stack = a name stacks the lines with that name
        if (s.stack !== undefined && !/^(false|0|no|none)$/i.test(String(s.stack))) {
            es.stack = /^(true|1|yes)$/i.test(String(s.stack)) ? "stack_y" + s.axis_index : "stack_" + s.stack;
        }
        if (s.in_tooltip !== undefined && !wx_bool(s.in_tooltip)) {
            es.silent = true;
            es.tooltip = {show: false};
        }
        if (wx_bool(s.value_labels)) {
            es.label = {show: true, color: t.text, formatter: function(p) {
                return wx_value_format(Array.isArray(p.value) ? p.value[1] : p.value, s.observation, false, s.rounding, s.mirrored, s.number_format);
            }};
        }

        // The data: shift times to station time, and break the line where readings are missing
        var gap = s.gap_size ? parseFloat(s.gap_size) * 1000 : gap_size;
        var data = [];
        var last_x = null;
        (s.data || []).forEach(function(point) {
            var x, y;
            if (Array.isArray(point)) { x = point[0]; y = point[1]; } else { x = null; y = point; }
            if (y !== null && y !== undefined) {
                y = +y;
                axis.extent[0] = Math.min(axis.extent[0], y);
                axis.extent[1] = Math.max(axis.extent[1], y);
            } else {
                y = null;
            }
            if (categories || x === null) {
                data.push(y);
                return;
            }
            if (!es.connectNulls && gap > 0 && last_x !== null && x - last_x > gap * 1.05) {
                data.push([last_x + 1 + wx_tz_shift(last_x + 1), null, last_x + 1]);
            }
            data.push([x + wx_tz_shift(x), y, x]);
            span[0] = Math.min(span[0], x);
            span[1] = Math.max(span[1], x);
            last_x = x;
        });
        es.data = data;
        if (s.visible !== undefined && !wx_bool(s.visible)) {
            options.legend.selected = options.legend.selected || {};
            options.legend.selected[s.name] = false;
        }
        if (s.in_legend !== undefined && !wx_bool(s.in_legend)) es.wx_hide_legend = true;

        Object.keys(s).forEach(function(key) {
            if (WX_KNOWN_OPTIONS.indexOf(key) < 0) wx_debug(renderTo + ": option " + key + " on " + s.section + " is not one this skin knows, and is ignored");
        });
        return es;
    });

    // Legend entries: a dot for dots, a line for lines, leaving out lines with in_legend = false
    options.legend.data = options.series.filter(function(es) { return !es.wx_hide_legend; }).map(function(es) {
        return {name: es.name, icon: es.type == "scatter" ? "circle" : es.type == "bar" ? "rect" : "roundRect",
                itemWidth: es.type == "scatter" ? 7 : 14, itemHeight: es.type == "scatter" ? 7 : (es.type == "bar" ? 9 : 3)};
    });
    options.series.forEach(function(es) { delete es.wx_hide_legend; });

    // A legend too wide for the chart wraps onto more rows; keep them clear of the axis labels
    if (options.legend.show) {
        var row_width = (width || 600) - 20, rows = 1, used = 0;
        options.legend.data.forEach(function(item) {
            var w = item.itemWidth + 15 + String(item.name).length * 6.5;
            if (used > 0 && used + w > row_width) { rows++; used = 0; }
            used += w;
        });
        options.grid.bottom += (rows - 1) * 22;
    }

    options.yAxis = axes.map(function(axis, index) {
        var y = {
            type: "value",
            position: axis.opposite ? "right" : "left",
            scale: !axis.hasBar,
            name: axis.label || "",
            nameLocation: "middle",
            nameRotate: axis.opposite ? -90 : 90,
            nameGap: 20,
            nameMoveOverlap: true,
            nameTextStyle: {color: t.text, fontSize: 11},
            axisLine: {show: false},
            axisTick: {show: false},
            axisLabel: {color: t.text, fontSize: 11, hideOverlap: true, formatter: function(v) { return wx_number_format(v); }},
            splitLine: {show: index === 0, lineStyle: {color: t.grid}},
            minorTick: {show: false},
            minorSplitLine: {show: false}
        };
        axis.y = y;
        return y;
    });

    // Axis settings from each line (the last line that sets one wins)
    series_list.forEach(function(s) {
        var axis = axes[s.axis_index];
        var y = axis.y;
        var obs = s.observation;
        if (s.axis_min !== undefined) y.min = parseFloat(s.axis_min);
        if (s.axis_max !== undefined) y.max = parseFloat(s.axis_max);
        if (s.axis_soft_min !== undefined && parseFloat(s.axis_soft_min) < axis.extent[0]) y.min = parseFloat(s.axis_soft_min);
        if (s.axis_soft_max !== undefined && parseFloat(s.axis_soft_max) > axis.extent[1]) y.max = parseFloat(s.axis_soft_max);

        // The step between axis labels (used for barometer), unless it would crowd the axis
        if (s.axis_step) {
            var interval = parseFloat(s.axis_step);
            var lo = y.min !== undefined ? y.min : axis.extent[0];
            var hi = y.max !== undefined ? y.max : axis.extent[1];
            if (interval > 0 && isFinite(hi - lo) && (hi - lo) / interval <= 12) y.interval = interval;
        }
        if (wx_bool(s.axis_minor_ticks)) {
            y.minorTick = {show: true};
            y.minorSplitLine = {show: true, lineStyle: {color: t.grid, opacity: 0.4}};
        }

        // Barometer axis labels get the barometer's decimals
        if (obs == "barometer") {
            var decimals = typeof s.rounding !== "undefined" ? s.rounding : 2;
            y.axisLabel.formatter = function(v) { return wx_number_format(v, decimals); };
        }

        // Rain, rainRate and rainTotal start at zero, and a dry spell still gets an axis
        if (obs == "rain" || obs == "rainRate" || obs == "rainTotal") {
            y.min = 0;
            y.scale = false;
            if (!(axis.extent[1] > 0) && y.max === undefined) y.max = 0.01;
        }

        if (obs == "windDir") {
            y.interval = 90;
            y.axisLabel.formatter = function(v) { var value = weatherdirection[v]; return value !== undefined ? value : v; };
        }

        // A mirrored chart (values drawn below the axis) labels its axis without minus signs
        if (wx_bool(s.mirrored)) {
            y.axisLabel.formatter = function(v) { return wx_number_format(Math.abs(v)); };
        }

        // Lastly, number_format overrides the axis label format
        if (s.number_format && Object.keys(s.number_format).length >= 1) {
            var nf = s.number_format;
            y.axisLabel.formatter = function(v) { return wx_number_format(v, nf.decimals, nf.decimal_point, nf.thousands_separator); };
        }
    });

    // x axis
    if (categories) {
        options.xAxis = {
            type: "category",
            data: categories,
            axisLine: {onZero: false, lineStyle: {color: t.axis}},
            axisTick: {alignWithLabel: true, lineStyle: {color: t.axis}},
            axisLabel: {color: t.text, fontSize: 11},
            splitLine: {show: false}
        };
    } else {
        var days = (span[1] - span[0]) / 86400000;
        var lo = span[0] + wx_tz_shift(span[0]), hi = span[1] + wx_tz_shift(span[1]);
        var target = Math.max(4, Math.min(12, Math.round((width || 600) / 110)));
        var ticks = wx_time_ticks(lo, hi, target);
        options.wx_time = {lo: lo, hi: hi, target: target};
        options.xAxis = {
            type: "time",
            min: isFinite(lo) ? lo : undefined,
            max: isFinite(hi) ? hi : undefined,
            axisLine: {onZero: false, lineStyle: {color: t.axis}},
            // About one label per 110 pixels
            axisTick: {lineStyle: {color: t.axis}, customValues: ticks},
            splitLine: {show: false},
            axisLabel: {
                customValues: ticks,
                color: t.text,
                fontSize: 11,
                hideOverlap: true,
                formatter: function(value) { return wx_time_axis_label(value, days); }
            }
        };
    }

    // Tooltip: the date, then each series formatted as the skin formats observations
    options.tooltip = {
        trigger: "axis",
        confine: false,
        appendTo: "body",
        backgroundColor: t.tooltip,
        borderColor: t.tooltipBorder,
        textStyle: {color: t.tooltipText, fontSize: 12},
        axisPointer: {type: "line", lineStyle: {color: t.grid}},
        formatter: function(params) {
            if (!Array.isArray(params)) params = [params];
            if (!params.length) return "";
            var header;
            if (categories) {
                header = params[0].axisValueLabel;
            } else {
                var v = params[0].value;
                header = tzAdjustedMoment((Array.isArray(v) ? v[2] : params[0].axisValue) / 1000).format(tooltip_date_format);
            }
            var lines = params.map(function(p) {
                var s = series_list[p.seriesIndex];
                var y = Array.isArray(p.value) ? p.value[1] : p.value;
                if (y === null || y === undefined || s === undefined) return null;
                return "<span style='color:" + p.color + "'>●</span> " + wx_esc(p.seriesName) + ": <b>" +
                    wx_value_format(y, s.observation, true, s.rounding, wx_bool(s.mirrored), s.number_format) + "</b>";
            }).filter(Boolean);
            return wx_esc(header) + "<br>" + lines.join("<br>");
        }
    };
    return options;
}

/* --- Special charts: wind rose, gauge, air quality, Hays and weather range ------------------------------------ */

// Shared look of a tooltip
function wx_tooltip_base(trigger) {
    var t = wx_chart_theme();
    return {
        trigger: trigger,
        appendTo: "body",
        backgroundColor: t.tooltip,
        borderColor: t.tooltipBorder,
        textStyle: {color: t.tooltipText, fontSize: 12}
    };
}

function wx_dot(color) {
    return "<span style='color:" + color + "'>●</span> ";
}

// Time labels on a polar angle axis, read in the station's time zone
function wx_polar_time_label(value, span_days) {
    var m = tzAdjustedMoment(value / 1000);
    if (span_days > 60) return m.format("MMM");
    if (span_days > 1.5 || (m.hour() === 0 && m.minute() === 0)) return m.format("D MMM");
    return m.toDate().toLocaleTimeString(dayjs.locale(), {hour: "numeric", minute: "2-digit", timeZone: wx_tz || undefined});
}

// Tick positions for a polar time axis: whole hours, days or months in station time
function wx_polar_time_ticks(lo, hi) {
    var shift_lo = lo + wx_tz_shift(lo), shift_hi = hi + wx_tz_shift(hi);
    return wx_time_ticks(shift_lo, shift_hi, 12).map(function(v) { return v - wx_tz_shift(v); })
        .filter(function(v) { return v >= lo && v <= hi; });
}

// Wind rose: how often the wind blew from each direction, in speed bands, as stacked polar columns
function wx_windrose_options(plot, group, renderTo, width, height) {
    var opt = plot.options;
    var t = wx_chart_theme();
    var options = wx_base_options(opt, group, renderTo);
    var s = plot.series[Object.keys(plot.series).pop()];
    var bands = (s.data || []).filter(function(b) { return b && Array.isArray(b.data); });
    var directions = config.ordinate_names.slice(0, 16);
    var narrow = (width || 600) < 520;

    options.legend.orient = narrow ? "horizontal" : "vertical";
    if (!narrow) {
        // Just right of the rose: its centre plus its radius (72% of half the smaller side, under the title)
        var rose_radius = 0.72 * Math.min(width, (height || 400) - 40) / 2;
        delete options.legend.bottom;
        options.legend.left = Math.round(width * 0.42 + rose_radius + 50);
        options.legend.top = "middle";
    }
    options.legend.icon = "rect";
    options.legend.itemWidth = 12;
    options.legend.itemHeight = 12;
    // On a phone the legend goes underneath, so the rose moves up
    options.polar = {center: [narrow ? "50%" : "42%", narrow ? "44%" : "54%"], radius: narrow ? "56%" : "72%"};
    options.angleAxis = {
        type: "category",
        data: directions,
        // North at the top, centred on its column
        startAngle: 90 + 360 / 32,
        boundaryGap: true,
        axisLine: {lineStyle: {color: t.grid}},
        axisTick: {show: false},
        axisLabel: {color: t.text, fontSize: 11},
        splitLine: {show: true, lineStyle: {color: t.grid, opacity: 0.6}}
    };
    options.radiusAxis = {
        type: "value",
        min: 0,
        axisLine: {show: false},
        axisTick: {show: false},
        axisLabel: {show: false},
        splitLine: {lineStyle: {color: t.grid, opacity: 0.6}}
    };
    options.series = bands.map(function(band) {
        return {
            type: "bar",
            coordinateSystem: "polar",
            name: band.name,
            stack: "windrose",
            data: band.data,
            barCategoryGap: "4%",
            itemStyle: {color: band.color},
            emphasis: {focus: "none"}
        };
    });
    options.tooltip = Object.assign(wx_tooltip_base("axis"), {
        axisPointer: {type: "shadow"},
        formatter: function(params) {
            if (!params.length) return "";
            var total = 0;
            var lines = params.map(function(p) {
                total += +p.value || 0;
                return +p.value ? wx_dot(p.color) + wx_esc(p.seriesName) + ": <b>" + p.value + "%</b>" : null;
            }).filter(Boolean);
            return "<b>" + wx_esc(params[0].name) + "</b> (" + total + "%)<br>" + lines.join("<br>");
        }
    });
    return options;
}

// Gauge and air quality: the latest value as a ring
function wx_ring_options(opt, group, renderTo, size, ring) {
    var t = wx_chart_theme();
    var options = wx_base_options(opt, group, renderTo);
    options.legend.show = false;
    options.grid = undefined;
    // The ring reaches its radius above the centre and sin(50°) of it below
    var radius = Math.max(40, Math.min(size.width * 0.45, (size.height - 52) / 1.77));
    var thickness = Math.round(radius * 0.4);
    var value = ring.value;
    var has_value = value !== null && value !== undefined && !isNaN(value);
    var big = Math.max(18, Math.min(50, Math.round(radius * 0.38)));
    options.series = [{
        type: "gauge",
        // From 140° left of the top round to 140° right of it
        startAngle: 230,
        endAngle: -50,
        min: ring.min,
        max: ring.max,
        radius: radius,
        center: ["50%", Math.round(42 + radius + ((size.height - 52) - 1.77 * radius) / 2) + "px"],
        progress: {show: has_value && value > ring.min, width: thickness, roundCap: ring.rounded, itemStyle: {color: ring.color}},
        axisLine: {roundCap: ring.rounded, lineStyle: {width: thickness, color: [[1, wx_is_dark() ? "#3a3a3d" : "#e6e6e6"]]}},
        pointer: {show: false},
        axisTick: {show: false},
        splitLine: {show: false},
        axisLabel: {show: false},
        anchor: {show: false},
        title: {show: false},
        detail: {
            valueAnimation: false,
            offsetCenter: [0, ring.caption ? "-8%" : "0%"],
            formatter: function() {
                return "{value|" + ring.text + "}" + (ring.caption ? "\n{caption|" + ring.caption + "}" : "");
            },
            rich: {
                value: {fontSize: big, fontWeight: "bold", color: ring.color, lineHeight: big * 1.15, fontFamily: wx_font()},
                caption: {fontSize: Math.max(11, Math.round(big * (ring.caption_small ? 0.28 : 0.4))), fontWeight: "bold",
                          color: ring.color, lineHeight: big * 0.6, fontFamily: wx_font()}
            }
        },
        data: [{value: has_value ? Math.min(Math.max(value, ring.min), ring.max) : ring.min}],
        silent: true
    }];
    return options;
}

function wx_gauge_options(plot, group, renderTo, size) {
    var opt = plot.options;
    var s = plot.series[Object.keys(plot.series)[0]];
    var points = (s.data || []).filter(function(p) { return Array.isArray(p) ? p[1] !== null : p !== null; });
    var last = points.length ? points[points.length - 1] : null;
    var value = last === null ? null : +(Array.isArray(last) ? last[1] : last);
    var obs = s.observation;
    var color = s.color || group.colors[0].trim();
    var caption = null, caption_small = false;
    if (value !== null && wx_bool(s.colors_enabled)) {
        var band = gauge_band(value, s);
        if (band.color) color = band.color;
        if (band.label) { caption = band.label; caption_small = true; }
    }
    if (!caption && s.unit && units_config.labels[s.unit] !== undefined) caption = String(units_config.labels[s.unit]).trim() || null;
    var text = value === null ? "–" : wx_value_format(value, obs, false, s.rounding, wx_bool(s.mirrored), s.number_format);
    var min = s.axis_min !== undefined ? parseFloat(s.axis_min) : 0;
    var max = s.axis_max !== undefined ? parseFloat(s.axis_max) : 100;
    return wx_ring_options(opt, group, renderTo, size, {value: value, min: min, max: max, color: color, text: text,
                                                        caption: caption, caption_small: caption_small, rounded: true});
}

function wx_aqi_options(plot, group, renderTo, size) {
    var opt = plot.options;
    var s = plot.series[Object.keys(plot.series).pop()];
    var point = (s.data || [])[0] || {};
    var value = point.y === null || point.y === undefined || point.y === "" ? null : +point.y;
    var color = value === null ? (wx_is_dark() ? "#a0a0a3" : "#777777") : get_aqi_color(value);
    return wx_ring_options(opt, group, renderTo, size, {value: value, min: 0, max: 500, color: color,
        text: value === null ? "–" : String(value), caption: point.category || labels.aqi_no_data, caption_small: true, rounded: true});
}

// A filled band between two lists of points, drawn by a custom series. Gaps (nulls) split the band.
// to_xy(point, side) returns the [x, y] for the coordinate system, side 1 for the low edge and 2 for the high.
function wx_band_series(points, coordinateSystem, fill) {
    var segments = [], current = [];
    points.forEach(function(p) {
        if (p[1] === null || p[2] === null || p[1] === undefined || p[2] === undefined) {
            if (current.length) segments.push(current);
            current = [];
        } else {
            current.push(p);
        }
    });
    if (current.length) segments.push(current);
    return {
        type: "custom",
        coordinateSystem: coordinateSystem,
        silent: true,
        z: 1,
        data: [0],
        encode: coordinateSystem === "polar" ? {radius: [], angle: []} : {x: [], y: []},
        renderItem: function(params, api) {
            var coord = function(x, y) {
                return coordinateSystem === "polar" ? api.coord([y, x]) : api.coord([x, y]);
            };
            return {
                type: "group",
                children: segments.map(function(seg) {
                    var high = seg.map(function(p) { return coord(p[0], p[2]); });
                    var low = seg.slice().reverse().map(function(p) { return coord(p[0], p[1]); });
                    return {type: "polygon", shape: {points: high.concat(low)}, style: {fill: typeof fill === "function" ? fill(api) : fill}};
                })
            };
        }
    };
}

// Hays chart: wind speed and gusts around the clock, the band between them filled
function wx_hays_options(plot, group, renderTo, width) {
    var opt = plot.options;
    var t = wx_chart_theme();
    var options = wx_base_options(opt, group, renderTo);
    var s = plot.series[Object.keys(plot.series).pop()];
    var color = s.color || group.colors[0].trim();
    var data = (s.data || []).filter(function(p) { return Array.isArray(p); });
    var lo = data.length ? data[0][0] : 0, hi = data.length ? data[data.length - 1][0] : 1;
    var top = 0;
    data.forEach(function(p) { if (p[2] !== null && p[2] > top) top = p[2]; });
    if (s.axis_soft_max !== undefined && parseFloat(s.axis_soft_max) > top) top = parseFloat(s.axis_soft_max);
    var span_days = (hi - lo) / 86400000;
    var tooltip_date_format = opt.tooltip_date_format;

    options.legend.show = false;
    options.grid = undefined;
    options.polar = {center: ["50%", "54%"], radius: (width || 600) < 520 ? "62%" : "78%"};
    options.angleAxis = {
        type: "value",
        min: lo,
        max: hi,
        startAngle: 90,
        clockwise: true,
        axisLine: {lineStyle: {color: t.grid}},
        axisTick: {show: false},
        axisLabel: {color: t.text, fontSize: 10, customValues: wx_polar_time_ticks(lo, hi),
                    formatter: function(v) { return wx_polar_time_label(v, span_days); }},
        splitLine: {show: true, lineStyle: {color: t.grid, opacity: 0.6}}
    };
    var ring_step = top > 12 ? Math.ceil(top / 12) * 2 : 2;
    var rings = [];
    for (var r = 0; r <= Math.max(top, ring_step); r += ring_step) rings.push(r);
    if (rings[rings.length - 1] < top) rings.push(rings[rings.length - 1] + ring_step);
    options.radiusAxis = {
        type: "value",
        // A small hole in the middle
        min: -1,
        max: rings[rings.length - 1],
        axisLine: {show: false},
        axisTick: {show: false, customValues: rings},
        axisLabel: {color: t.text, fontSize: 9, customValues: rings},
        splitLine: {lineStyle: {color: t.grid, opacity: 0.6}}
    };
    options.series = [
        wx_band_series(data, "polar", color),
        {type: "line", coordinateSystem: "polar", name: labels.windSpeed, data: data.map(function(p) { return [p[1], p[0]]; }),
         showSymbol: false, lineStyle: {width: 1, color: color}, itemStyle: {color: color}, connectNulls: false},
        {type: "line", coordinateSystem: "polar", name: labels.windGust, data: data.map(function(p) { return [p[2], p[0]]; }),
         showSymbol: false, lineStyle: {width: 1, color: color}, itemStyle: {color: color}, connectNulls: false}
    ];
    options.tooltip = Object.assign(wx_tooltip_base("axis"), {
        axisPointer: {type: "line", lineStyle: {color: t.grid}},
        formatter: function(params) {
            var p = params.filter(function(x) { return x.seriesType === "line"; });
            if (!p.length) return "";
            var time = p[0].value[1];
            return "<b>" + wx_esc(tzAdjustedMoment(time / 1000).format(tooltip_date_format)) + "</b>" + p.map(function(x) {
                return x.value[0] === null ? "" : "<br>" + wx_dot(color) + wx_esc(x.seriesName) + ": <b>" +
                    wx_value_format(x.value[0], "windSpeed", true, s.rounding, false, s.number_format) + "</b>";
            }).join("");
        }
    });
    return options;
}

// Weather range: each day's low to high, coloured by its average temperature, as columns or a shaded band.
// polar = true wraps the days around a circle ("weather radials").
function wx_weather_range_options(plot, group, renderTo, width) {
    var opt = plot.options;
    var t = wx_chart_theme();
    var options = wx_base_options(opt, group, renderTo);
    var s = plot.series[Object.keys(plot.series).pop()];
    var obs = s.range_observation || "outTemp";
    var unit = s.range_unit;
    var polar = wx_bool(s.polar);
    var area = wx_bool(s.band);
    var data = (s.data || []).filter(function(p) { return Array.isArray(p); });
    var tooltip_date_format = opt.tooltip_date_format;
    var fallback = s.color || group.colors[0].trim();
    var color_of = function(avg) { return s.color || get_outTemp_color(unit, avg) || fallback; };

    var lows = data.map(function(p) { return p[1]; }).filter(function(v) { return v !== null; });
    var highs = data.map(function(p) { return p[2]; }).filter(function(v) { return v !== null; });
    var range_min = lows.length ? Math.min.apply(null, lows) : 0;
    var range_max = highs.length ? Math.max.apply(null, highs) : 1;
    // Tick spacing: a fifth of the highest value, rounded up to a multiple of 5
    var interval = Math.max(5, Math.ceil(Math.round(range_max / 5) / 5) * 5);
    var axis_min = Math.floor(range_min / interval) * interval;
    var axis_max = Math.ceil(range_max / interval) * interval;
    if (axis_max <= axis_min) axis_max = axis_min + interval;
    var step = data.length > 1 ? data[1][0] - data[0][0] : 86400000;
    var lo = data.length ? data[0][0] : 0, hi = data.length ? data[data.length - 1][0] + step : 1;
    var span_days = (hi - lo) / 86400000;

    // Temperature colours from the bottom of the axis to the top, for the shaded band
    var stops = function() {
        var scale = OUTTEMP_COLORS[unit];
        if (!scale || s.color) return null;
        var out = [], prev = axis_min;
        scale.forEach(function(z) {
            var from = Math.max(prev, axis_min), to = Math.min(z[0], axis_max);
            if (to > from) {
                out.push({offset: (from - axis_min) / (axis_max - axis_min), color: z[1]});
                out.push({offset: (to - axis_min) / (axis_max - axis_min), color: z[1]});
            }
            prev = z[0];
        });
        return out.length ? out : null;
    };

    options.legend.show = false;
    var tooltip_lines = function(p) {
        var f = function(v) { return v === null ? "–" : wx_value_format(v, obs, true, s.rounding, false, s.number_format); };
        return "<b>" + wx_esc(tzAdjustedMoment(p[0] / 1000).format(tooltip_date_format)) + "</b><br>" +
            wx_dot(color_of(p[2])) + labels.range_high + ": <b>" + f(p[2]) + "</b><br>" +
            wx_dot(color_of(p[1])) + labels.range_low + ": <b>" + f(p[1]) + "</b><br>" +
            wx_dot(color_of(p[3])) + labels.range_average + ": <b>" + f(p[3]) + "</b>";
    };
    var value_axis = {
        type: "value",
        min: axis_min,
        max: axis_max,
        interval: interval,
        axisLine: {show: false},
        axisTick: {show: false},
        axisLabel: {color: t.text, fontSize: polar ? 9 : 11, formatter: function(v) { return wx_number_format(v); }},
        splitLine: {lineStyle: {color: t.grid, opacity: polar ? 0.6 : 1}},
        name: s.axis_label || "",
        nameTextStyle: {color: t.text, fontSize: polar ? 10 : 11}
    };

    if (polar) {
        options.grid = undefined;
        options.polar = {center: ["50%", "54%"], radius: (width || 600) < 520 ? "66%" : "74%"};
        options.angleAxis = {
            type: "value",
            min: lo,
            max: hi,
            startAngle: 90,
            clockwise: true,
            axisLine: {lineStyle: {color: t.grid}},
            axisTick: {show: false},
            axisLabel: {color: t.text, fontSize: 10, customValues: wx_polar_time_ticks(lo, hi),
                        formatter: function(v) { return wx_polar_time_label(v, span_days); }},
            splitLine: {show: true, lineStyle: {color: t.grid, opacity: 0.6}}
        };
        options.radiusAxis = Object.assign(value_axis, {name: ""});
    } else {
        var shift = function(v) { return v + wx_tz_shift(v); };
        var x_lo = shift(lo), x_hi = shift(hi);
        var target = Math.max(4, Math.min(12, Math.round((width || 600) / 110)));
        var ticks = wx_time_ticks(x_lo, x_hi, target);
        options.xAxis = {
            type: "time",
            min: x_lo,
            max: x_hi,
            axisLine: {onZero: false, lineStyle: {color: t.axis}},
            axisTick: {lineStyle: {color: t.axis}, customValues: ticks},
            splitLine: {show: false},
            axisLabel: {customValues: ticks, color: t.text, fontSize: 11, hideOverlap: true,
                        formatter: function(v) { return wx_time_axis_label(v, span_days); }}
        };
        options.yAxis = Object.assign(value_axis, {nameLocation: "middle", nameRotate: 90, nameGap: 20, nameMoveOverlap: true});
        options.wx_time = {lo: x_lo, hi: x_hi, target: target};
        data = data.map(function(p) { return [shift(p[0]), p[1], p[2], p[3], p[0]]; });
    }

    var coord = function(api, x, y) { return polar ? api.coord([y, x]) : api.coord([x, y]); };
    if (area) {
        var band_points = data.map(function(p) { return [p[0] + step / 2, p[1], p[2]]; });
        var band_fill = function(api) {
            var st = stops();
            if (!st) return fallback;
            if (polar) {
                var c = api.coord([axis_min, lo]), r = Math.hypot(api.coord([axis_max, lo])[0] - c[0], api.coord([axis_max, lo])[1] - c[1]);
                var centre = options.polar.center;
                var cx = api.getWidth() * parseFloat(centre[0]) / 100, cy = api.getHeight() * parseFloat(centre[1]) / 100;
                return new echarts.graphic.RadialGradient(cx, cy, r, st, true);
            }
            var y0 = api.coord([data[0][0], axis_min])[1], y1 = api.coord([data[0][0], axis_max])[1];
            return new echarts.graphic.LinearGradient(0, y0, 0, y1, st, true);
        };
        options.series = [wx_band_series(band_points, polar ? "polar" : "cartesian2d", band_fill)];
    } else {
        options.series = [];
    }
    // The days themselves: columns, or invisible markers over the band that carry the tooltip
    options.series.push({
        type: "custom",
        coordinateSystem: polar ? "polar" : "cartesian2d",
        data: data,
        encode: polar ? {angle: 0, radius: [1, 2], tooltip: [1, 2, 3]} : {x: 0, y: [1, 2], tooltip: [1, 2, 3]},
        renderItem: function(params, api) {
            var x = api.value(0) + step / 2, low = api.value(1), high = api.value(2), avg = api.value(3);
            if (isNaN(low) || isNaN(high)) return null;
            var a = coord(api, x, low), b = coord(api, x, high);
            if (area) {
                // A thin line the pointer can find, nearly invisible
                return {type: "line", shape: {x1: a[0], y1: a[1], x2: b[0], y2: b[1]}, style: {stroke: "rgba(0,0,0,0.001)", lineWidth: 6}};
            }
            var colour = color_of(avg);
            if (polar) {
                var widthpx = Math.max(1.5, 2 * Math.PI * Math.hypot(b[0] - coord(api, x, axis_min)[0], b[1] - coord(api, x, axis_min)[1]) / Math.max(1, data.length) * 0.7);
                return {type: "line", shape: {x1: a[0], y1: a[1], x2: b[0], y2: b[1]}, style: {stroke: colour, lineWidth: Math.min(widthpx, 8), lineCap: "round"}};
            }
            var w = Math.max(1, api.size([step, 0])[0] * 0.75);
            return {type: "rect", shape: {x: a[0] - w / 2, y: b[1], width: w, height: Math.max(1, a[1] - b[1]), r: Math.min(2, w / 4)},
                    style: {fill: colour}};
        }
    });
    options.tooltip = Object.assign(wx_tooltip_base(polar ? "item" : "axis"), {
        axisPointer: {type: "shadow"},
        formatter: function(params) {
            var p = Array.isArray(params) ? params.filter(function(x) { return x.seriesIndex === options.series.length - 1; })[0] : params;
            if (!p || !p.value) return "";
            var v = p.value;
            return tooltip_lines([polar ? v[0] : v[4], v[1], v[2], v[3]]);
        }
    });
    return options;
}

// Drag across the chart to zoom in; a reset button appears once zoomed.
// Touch screens keep one-finger scrolling of the page.
function wx_enable_zoom(chart, options, wx_time) {
    if (!options.xAxis || options.xAxis.type !== "time") return;
    var fine_pointer = !window.matchMedia || window.matchMedia("(pointer: fine)").matches;
    if (!fine_pointer) return;
    var t = wx_chart_theme();
    chart.setOption({
        dataZoom: [{id: "wx-zoom", type: "inside", xAxisIndex: 0, filterMode: "none", zoomOnMouseWheel: false,
                    moveOnMouseMove: false, moveOnMouseWheel: false, preventDefaultMouseMove: false}],
        brush: {xAxisIndex: 0, brushType: "lineX", brushMode: "single", transformable: false, throttleType: "debounce",
                brushStyle: {color: wx_is_dark() ? "rgba(255,255,255,0.12)" : "rgba(51,92,173,0.25)", borderWidth: 0},
                outOfBrush: {colorAlpha: 1}}
    });
    chart.dispatchAction({type: "takeGlobalCursor", key: "brush", brushOption: {brushType: "lineX", brushMode: "single"}});

    var label = (config.chart_texts && config.chart_texts.resetZoom) || "Reset zoom";
    var show_reset = function(show) {
        chart.setOption({graphic: [{id: "wx-reset-zoom", type: "group", right: 40, top: 40, ignore: !show, z: 100,
            children: [
                {type: "rect", shape: {width: 82, height: 24, r: 3}, style: {fill: wx_is_dark() ? "#505053" : "#f7f7f7", stroke: t.grid}},
                {type: "text", x: 41, y: 12, style: {text: label, fill: t.tooltipText, font: "12px " + wx_font(), align: "center", verticalAlign: "middle"}}
            ],
            onclick: function() {
                chart.dispatchAction({type: "dataZoom", dataZoomId: "wx-zoom", start: 0, end: 100});
                if (wx_time) wx_set_time_ticks(chart, wx_time.lo, wx_time.hi);
                show_reset(false);
            }
        }]});
    };
    show_reset(false);
    chart.off("brushEnd");
    chart.on("brushEnd", function(e) {
        var area = e.areas && e.areas[0];
        chart.dispatchAction({type: "brush", areas: []});
        if (!area || !area.coordRange) return;
        var range = area.coordRange;
        // A click, or a drag of a few pixels, is not a zoom
        if (Math.abs(area.range[1] - area.range[0]) < 5) return;
        var from = Math.min(range[0], range[1]), to = Math.max(range[0], range[1]);
        chart.dispatchAction({type: "dataZoom", dataZoomId: "wx-zoom", startValue: from, endValue: to});
        wx_set_time_ticks(chart, from, to);
        show_reset(true);
    });
}

// Redraw every chart from its data, e.g. after the light/dark theme changes
function wx_charts_redraw() {
    Object.keys(wx_charts).forEach(function(id) {
        var c = wx_charts[id];
        if (!document.getElementById(id)) { delete wx_charts[id]; return; }
        try { render_chart(c.plot, c.group, c.json_file, c.prepend); } catch (e) { console.log(e); }
    });
}

function wx_charts_resize() {
    Object.keys(wx_charts).forEach(function(id) {
        var c = echarts.getInstanceByDom(document.getElementById(id) || document.createElement("div"));
        if (c) c.resize();
    });
}

function wx_charts_dispose(id) {
    var div = document.getElementById(id);
    var c = div && echarts.getInstanceByDom(div);
    if (c) c.dispose();
    delete wx_charts[id];
}

window.addEventListener("resize", wx_charts_resize);
