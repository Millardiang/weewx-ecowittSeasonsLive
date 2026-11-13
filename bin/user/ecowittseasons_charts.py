"""
weewx-echarts: interactive weather charts for WeeWX, drawn with Apache ECharts.

This copy is part of the weewx-ecowittSeasonsLive skin. It is weewx-echarts 1.0.0
(https://github.com/Millardiang/weewx-ECharts) under its own module name, so the
two extensions can be installed side by side, with one change: load_chart_dict()
leaves out the lines (and then the charts) whose observation has no data, when
[Extras] hide_empty_charts is on (see user.ecowittseasons.prune_chart_dict).

Charts are set up in charts.conf. A Belchertown skin graphs.conf works too: its option names are translated.
EChartsJsonGenerator writes one JSON file per chart group; the browser draws them.

The chart generator comes from the Belchertown skin by Pat O'Brien
(https://github.com/poblabs/weewx-belchertown) and its contributors, including
Copyright (c) 2026 Manuel Hilgert <hilman2@gmail.com>.

This program is free software: you can redistribute it and/or modify it under the terms of
the GNU General Public License as published by the Free Software Foundation, either version 3
of the License, or (at your option) any later version. See the LICENSE file.
"""
import calendar
import datetime
import json
import locale
import logging
import os
import os.path
import re
import time
from collections import OrderedDict

import configobj
import weedb
import weeutil.weeutil
import weewx
import weewx.reportengine
import weewx.units
import weewx.xtypes
from weeutil.config import accumulateLeaves
from weeutil.weeutil import (
    TimeSpan,
    archiveDaySpan,
    archiveMonthSpan,
    archiveSpanSpan,
    archiveWeekSpan,
    archiveYearSpan,
    isStartOfDay,
    startOfDay,
    to_bool,
    to_float,
    to_int,
)
from weewx.cheetahgenerator import SearchList

if int(weewx.__version__.split(".")[0]) < 5:
    raise weewx.UnsupportedFeature("weewx-echarts requires weewx 5.0 or newer, found weewx %s" % weewx.__version__)

VERSION = "1.0.0"

log = logging.getLogger(__name__)


def logdbg(msg):
    log.debug(msg)


def loginf(msg):
    log.info(msg)


def logerr(msg):
    log.error(msg)


loginf("version %s" % VERSION)

# What the air quality chart shows when there's no station reading
aqi = ""
aqi_category = ""

DATABASE_DOWN = (weedb.CannotConnectError, weedb.DisconnectError) + (
    (weedb.DatabaseLockedError,) if hasattr(weedb, "DatabaseLockedError") else ())

# Day.js formats dates in the browser. These are the locale files cdnjs has for this version;
# English is built in.
DAYJS_VERSION = "1.11.23"
DAYJS_LOCALES = frozenset([
    'af', 'am', 'ar', 'ar-dz', 'ar-iq', 'ar-kw', 'ar-ly', 'ar-ma', 'ar-sa', 'ar-tn', 'az', 'be',
    'bg', 'bi', 'bm', 'bn', 'bn-bd', 'bo', 'br', 'bs', 'ca', 'cs', 'cv', 'cy', 'da', 'de',
    'de-at', 'de-ch', 'dv', 'el', 'en', 'en-au', 'en-ca', 'en-gb', 'en-ie', 'en-il', 'en-in',
    'en-nz', 'en-sg', 'en-tt', 'eo', 'es', 'es-do', 'es-mx', 'es-pr', 'es-us', 'et', 'eu', 'fa',
    'fi', 'fo', 'fr', 'fr-ca', 'fr-ch', 'fy', 'ga', 'gd', 'gl', 'gom-latn', 'gu', 'he', 'hi',
    'hr', 'ht', 'hu', 'hy-am', 'id', 'is', 'it', 'it-ch', 'ja', 'jv', 'ka', 'kk', 'km', 'kn',
    'ko', 'ku', 'ky', 'lb', 'lo', 'lt', 'lv', 'me', 'mi', 'mk', 'ml', 'mn', 'mr', 'ms', 'ms-my',
    'mt', 'my', 'nb', 'ne', 'nl', 'nl-be', 'nn', 'oc-lnc', 'pa-in', 'pl', 'pt', 'pt-br', 'rn',
    'ro', 'ru', 'rw', 'sd', 'se', 'si', 'sk', 'sl', 'sq', 'sr', 'sr-cyrl', 'ss', 'sv', 'sv-fi',
    'sw', 'ta', 'te', 'tet', 'tg', 'th', 'tk', 'tl-ph', 'tlh', 'tr', 'tzl', 'tzm', 'tzm-latn',
    'ug-cn', 'uk', 'ur', 'uz', 'uz-latn', 'vi', 'x-pseudo', 'yo', 'zh', 'zh-cn', 'zh-hk',
    'zh-tw'
])

DEFAULT_ORDINATES = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW",
                     "NNW", "N/A"]


def translate_title(label_dict, title):
    """Return the translation of a title or button text from charts.conf.

    A title is looked up by its own English text, so the titles of a charts.conf that was copied
    from charts.conf.example get translated too, and any other title is shown as written.
    An unquoted title with a comma is a list to ConfigObj.
    """
    if isinstance(title, list):
        title = ", ".join(title)
    translated = label_dict[title]
    # A list label, such as "second", isn't a translation of the title
    return title if isinstance(translated, list) else translated


def report_locale(wanted, lang):
    """The locale name for the browser, such as 'de_DE', from the echarts_locale option ('auto' or a name).

    A locale that isn't installed on the server can't be set. Its name is returned all the same:
    the browser has its own locale data.
    """
    try:
        name, encoding = locale.getlocale()
    except ValueError:
        name, encoding = None, None
    if wanted == "auto":
        # A bare 'de' isn't a locale name; 'lang = en' is what every new station says, so it means nothing
        wanted = ""
        language = (lang or "en").split(".")[0]
        if language != "en" and not ((name or "") + "_").startswith(language + "_"):
            wanted = locale.normalize(language + ".UTF-8")
    if wanted:
        try:
            locale.setlocale(locale.LC_ALL, wanted)
            name, encoding = locale.getlocale()
        except locale.Error as error:
            log.debug("Locale %s is not installed. The browser will still use it: %s", wanted, error)
            name, _, encoding = wanted.partition(".")
    # The browser throws a RangeError on a name it can't parse, such as 'C' or 'de_DE@euro'
    name = (name or "").split("@")[0]
    if name in ("C", "POSIX") or not re.fullmatch(r"[A-Za-z]{2,8}(_[A-Za-z0-9]{2,8})*", name):
        name = "en_US"
    return name, encoding or "UTF-8"


def system_timezone():
    """The server's time zone name, such as America/New_York, or "" when it can't be told."""
    tz = os.environ.get("TZ", "").lstrip(":")
    if "/" in tz:
        return tz
    link = os.path.realpath("/etc/localtime")
    if "zoneinfo/" in link:
        return re.sub(r"^(posix|right)/", "", link.split("zoneinfo/", 1)[1])
    try:
        with open("/etc/timezone") as f:
            return f.read().strip()
    except OSError:
        logdbg("No time zone name found (TZ, /etc/localtime, /etc/timezone); charts use the UTC offset")
        return ""


UNIT_SWITCH_GROUPS = ("group_temperature", "group_speed", "group_speed2", "group_pressure", "group_rain", "group_rainrate",
                      "group_distance", "group_altitude", "group_degree_day", "group_length")


def unit_switch_config(formatter, converter):
    """The station's display units, labels and formats, for the visitor's unit switch in the browser."""
    labels = {}
    for unit, label in formatter.unit_label_dict.items():
        labels[unit] = label[-1] if isinstance(label, (list, tuple)) else label
    return {
        "groups": {g: u for g, u in converter.group_unit_dict.items() if g in UNIT_SWITCH_GROUPS},
        "labels": labels,
        "formats": dict(formatter.unit_format_dict),
        "decimal_point": locale.localeconv()["decimal_point"],
        "obs": {o: g for o, g in weewx.units.obs_group_dict.items() if g in UNIT_SWITCH_GROUPS},
    }


# Chart options from the Belchertown skin and Highcharts, and what this skin calls them. A Belchertown graphs.conf
# works unchanged: its names are read as these.
LEGACY_OPTION_NAMES = {
    "observation_type": "observation",
    "connectNulls": "connect_gaps",
    "gapsize": "gap_size",
    "xAxis_categories": "categories",
    "xAxis_groupby": "group_by",
    "exporting": "download_button",
    "yAxis_label": "axis_label",
    "yAxis_label_unit": "axis_unit",
    "yAxis_min": "axis_min",
    "yAxis_max": "axis_max",
    "yAxis_softMin": "axis_soft_min",
    "yAxis_softMax": "axis_soft_max",
    "yAxis_tickInterval": "axis_step",
    "yAxis_minorTicks": "axis_minor_ticks",
    "mirrored_value": "mirrored",
    "range_type": "range_observation",
    "area_display": "band",
    "zIndex": "layer",
    "lineWidth": "line_width",
    "lineColor": "line_color",
    "dashStyle": "line_style",
    "fillColor": "fill_color",
    "fillOpacity": "fill_opacity",
    "showInLegend": "in_legend",
    "enableMouseTracking": "in_tooltip",
}
LEGACY_NUMBER_FORMAT = {"decimalPoint": "decimal_point", "thousandsSep": "thousands_separator"}
LEGACY_TYPES = {"spline": "smooth", "areaspline": "smooth_area", "scatter": "dots", "bar": "column"}
LEGACY_STEPS = {"left": "start", "center": "middle", "right": "end"}
LEGACY_SYMBOLS = {"triangle-down": "triangle_down"}
# Wind rose speed band colours, slowest first
DEFAULT_SPEED_COLORS = ["#7cb5ec", "#b2df8a", "#f7a35c", "#8c6bb1", "#dd3497", "#e4d354", "#268bd2"]


def modernize_chart_options(section):
    """Rewrite Belchertown/Highcharts option names in a chart config (and its subsections) to this skin's names.

    An option already given under its new name wins over the old one.
    """
    def put(key, value):
        if key not in section:
            section[key] = value

    for old, new in LEGACY_OPTION_NAMES.items():
        if old in section.scalars:
            if new not in section:
                section.rename(old, new)
            else:
                del section[old]
    # yAxis = 1 puts the line on a second scale, on the right
    if "yAxis" in section.scalars:
        value = section.pop("yAxis")
        put("right_axis", "true" if str(value).strip() in ("1", "1.0") else "false")
    # stacking = normal (with an optional stack = name) -> stack = true / name
    if "stacking" in section.scalars:
        stacking = str(section.pop("stacking")).strip().lower()
        if stacking not in ("", "none", "null", "false", "0"):
            put("stack", "true")
        elif "stack" in section.scalars:
            del section["stack"]
    # Belchertown's misspelt Beaufort colours for the wind rose
    beauford = [k for k in section.scalars if re.fullmatch(r"beauford[0-6]", k)]
    if beauford:
        colors = list(DEFAULT_SPEED_COLORS)
        for key in beauford:
            colors[int(key[-1])] = section.pop(key)
        put("speed_colors", colors)
    if "type" in section.scalars and isinstance(section["type"], str):
        section["type"] = LEGACY_TYPES.get(section["type"].strip().lower(), section["type"].strip().lower())
    if "step" in section.scalars and isinstance(section["step"], str):
        section["step"] = LEGACY_STEPS.get(section["step"].strip().lower(), section["step"].strip().lower())
    if "line_style" in section.scalars and isinstance(section["line_style"], str):
        # Highcharts' ShortDashDot -> short_dash_dot
        section["line_style"] = re.sub(r"(?<!^)(?=[A-Z])", "_", section["line_style"].strip()).lower()

    for name in list(section.sections):
        sub = section[name]
        if name == "marker":
            if "enabled" in sub:
                put("markers", sub["enabled"])
            if "radius" in sub:
                try:
                    put("marker_size", "%g" % (2 * float(sub["radius"])))
                except ValueError:
                    pass
            if "symbol" in sub:
                put("marker_shape", LEGACY_SYMBOLS.get(sub["symbol"], sub["symbol"]))
            del section[name]
        elif name == "dataLabels":
            if "enabled" in sub:
                put("value_labels", sub["enabled"])
            del section[name]
        elif name == "states":
            # Highcharts' hover styling; nothing to do with ECharts
            del section[name]
        elif name in ("numberFormat", "number_format"):
            for old, new in LEGACY_NUMBER_FORMAT.items():
                if old in sub.scalars:
                    sub.rename(old, new)
            if name == "numberFormat":
                if "number_format" in section:
                    del section[name]
                else:
                    section.rename(name, "number_format")
        else:
            modernize_chart_options(sub)


def load_chart_dict(config_dict, skin_dict, db_manager=None):
    """The chart config from the skin folder, in this skin's option names.

    charts.conf; else graphs.conf (Belchertown's name for it); else charts.conf.example.
    With a database, lines and charts with no data are left out (weewx-ecowittSeasonsLive).
    """
    skin_dir = os.path.join(config_dict["WEEWX_ROOT"], skin_dict["SKIN_ROOT"], skin_dict.get("skin", ""))
    for name in ("charts.conf", "graphs.conf", "charts.conf.example"):
        path = os.path.join(skin_dir, name)
        if os.path.exists(path):
            break
    chart_dict = configobj.ConfigObj(path, file_error=True, encoding="utf-8")
    modernize_chart_options(chart_dict)
    if db_manager is not None and to_bool(skin_dict.get("Extras", {}).get("hide_empty_charts", True)):
        from user.ecowittseasons import prune_chart_dict
        prune_chart_dict(chart_dict, db_manager, skin_dict)
    return chart_dict


def skin_conf_extras(config_dict, skin_dict):
    """The [Extras] of the skin's own skin.conf, before weewx.conf changes anything."""
    path = os.path.join(config_dict["WEEWX_ROOT"], skin_dict["SKIN_ROOT"], skin_dict.get("skin", ""), "skin.conf")
    try:
        return configobj.ConfigObj(path, encoding="utf-8").get("Extras", {})
    except (IOError, configobj.ConfigObjError):
        return {}


def extra(extras, name, default, *old_names, skin_defaults=None):
    """An [Extras] option, also under an older (Belchertown) name, so copied weewx.conf settings carry over.

    skin.conf always sets the new name, so it counts only when weewx.conf changed it; otherwise an old name
    set in weewx.conf is used.
    """
    skin_defaults = skin_defaults or {}
    if name in extras and (name not in skin_defaults or str(extras[name]) != str(skin_defaults[name])):
        return extras[name]
    for key in old_names:
        if key in extras:
            return extras[key]
    return extras.get(name, default)


class EChartsSearchList(SearchList):
    """What the pages need: the chart groups, and the settings the browser scripts read."""

    def get_extension_list(self, timespan, db_lookup):
        gen = self.generator
        skin_dict = gen.skin_dict
        extras = skin_dict.get("Extras", {})
        defaults = skin_conf_extras(gen.config_dict, skin_dict)
        label_dict = weeutil.weeutil.KeyDict(skin_dict.get("Labels", {}).get("Generic", {}))

        # The station's UTC offset in minutes, for when the browser can't use the time zone name
        now = time.localtime(time.time())
        utc_offset = (calendar.timegm(now) - calendar.timegm(time.gmtime(time.mktime(now)))) / 60
        tz = skin_dict.get("Units", {}).get("TimeZone", {}).get("time_zone", "") or system_timezone()

        locale_name, _ = report_locale(extra(extras, "echarts_locale", "auto", "belchertown_locale", skin_defaults=defaults), skin_dict.get("lang"))
        locale_js = locale_name.replace("_", "-")
        dayjs_locale = "en"
        for candidate in (locale_js.lower(), locale_js.lower().split("-")[0]):
            if candidate in DAYJS_LOCALES:
                dayjs_locale = candidate
                break

        try:
            ordinates = weeutil.weeutil.option_as_list(skin_dict["Units"]["Ordinates"]["directions"])
        except KeyError:
            ordinates = DEFAULT_ORDINATES

        chart_dict = load_chart_dict(gen.config_dict, skin_dict, db_lookup(skin_dict.get("data_binding", "wx_binding")))
        charts = OrderedDict()
        titles = OrderedDict()
        content = OrderedDict()
        buttons = []
        for group in chart_dict.sections:
            charts[group] = list(chart_dict[group].sections)
            titles[group] = translate_title(label_dict, chart_dict[group]["title"]) if "title" in chart_dict[group] else group
            if "page_content" in chart_dict[group]:
                content[group] = chart_dict[group]["page_content"]
            if to_bool(chart_dict[group].get("show_button", False)):
                text = translate_title(label_dict, chart_dict[group].get("button_text", group))
                buttons.append({"group": group, "text": text})

        default_group = extra(extras, "default_group", "", "default_graphgroup", "graph_page_default_graphgroup", skin_defaults=defaults)
        if default_group not in charts:
            default_group = buttons[0]["group"] if buttons else (next(iter(charts)) if charts else "")

        page_config = {
            "debug": to_int(extra(extras, "echarts_debug", 0, "belchertown_debug", skin_defaults=defaults)),
            "locale": locale_js,
            "dayjs_locale": dayjs_locale,
            "time_zone": tz,
            "utc_offset": utc_offset,
            "decimal": extra(extras, "chart_decimal", "auto", "highcharts_decimal", skin_defaults=defaults),
            "thousands": extra(extras, "chart_thousands", "auto", "highcharts_thousands", skin_defaults=defaults),
            "chart_texts": dict(skin_dict.get("Texts", {}).get("Charts", skin_dict.get("Texts", {}).get("Highcharts", {}))),
            "units": unit_switch_config(gen.formatter, gen.converter),
            "ordinate_names": [str(x) for x in ordinates],
            # Compass labels on the wind direction axis, from the same translated ordinates
            "windDir_ordinals": {"0": str(ordinates[0]), "90": str(ordinates[4]), "180": str(ordinates[8]),
                                 "270": str(ordinates[12]), "360": str(ordinates[0])},
            "charts": charts,
            "group_titles": titles,
            "group_content": content,
            "default_group": default_group,
            "theme": extras.get("theme", "auto"),
            "labels": {k: v for k, v in label_dict.items() if isinstance(v, str)},
        }
        return [{
            "echarts_version": VERSION,
            "dayjs_version": DAYJS_VERSION,
            "dayjs_locale": dayjs_locale,
            "page_locale": locale_js,
            "page_config_json": json.dumps(page_config, ensure_ascii=False).replace("</", "<\\/"),
            "group_buttons": buttons,
            "group_titles": titles,
            "default_group": default_group,
        }]


class EChartsJsonGenerator(weewx.reportengine.ReportGenerator):
    """Generates the chart JSON files from charts.conf, one per chart group, for the browser to draw.
    Adapted from the ImageGenerator class.

    Useful attributes (some inherited from ReportGenerator):

        config_dict:      The weewx configuration dictionary
        skin_dict:        The dictionary for this skin
        gen_ts:           The generation time
        first_run:        Is this the first time the generator has been run?
        stn_info:         An instance of weewx.station.StationInfo
        record:           A copy of the "current" record. May be None.
        formatter:        An instance of weewx.units.Formatter
        converter:        An instance of weewx.units.Converter
        search_list_objs: A list holding search list extensions
        db_binder:        An instance of weewx.manager.DBBinder from which the
                          data should be extracted
    """

    def run(self):
        """Main entry point for file generation."""

        self.chart_dict = load_chart_dict(self.config_dict, self.skin_dict,
                                          self.db_binder.get_manager(self.skin_dict.get("data_binding", "wx_binding")))

        self.converter = weewx.units.Converter.fromSkinDict(self.skin_dict)
        self.formatter = weewx.units.Formatter.fromSkinDict(self.skin_dict)

        # Setup title dict for plot titles
        try:
            d = self.skin_dict["Labels"]["Generic"]
        except KeyError:
            d = {}
        label_dict = weeutil.weeutil.KeyDict(d)

        # Final output dict
        output = {}

        # Loop through each [section]. This is the first bracket group of
        # options including global options.
        for chart_group in self.chart_dict.sections:
            output[
                chart_group
            ] = (
                OrderedDict()
            )  # This retains the order in which to load the charts on the page.
            chart_options = accumulateLeaves(self.chart_dict[chart_group])

            output[chart_group]["skin_version"] = VERSION
            output[chart_group]["generated_timestamp"] = time.strftime(
                "%m/%d/%Y %H:%M:%S"
            )

            # Setup the JSON file name for each chart group
            html_dest_dir = os.path.join(
                self.config_dict["WEEWX_ROOT"], self.skin_dict["HTML_ROOT"], "json"
            )
            # Nothing else makes the json folder
            os.makedirs(html_dest_dir, exist_ok=True)
            json_filename = html_dest_dir + "/" + chart_group + ".json"

            # The default line colours
            colors = chart_options.get(
                "colors",
                "#4282b4, #b44242, #42b442, #42b4b4, #b442b4, #72b2c4, #c47272, #72c472, #72c4c4, #c472c4",
            )
            output[chart_group]["colors"] = colors

            # chartgroup_title is used on the graphs page
            chartgroup_title = chart_options.get("title", None)
            if chartgroup_title:
                output[chart_group]["group_title"] = translate_title(label_dict, chartgroup_title)

            # Define the default tooltip datetime format from the global options
            tooltip_date_format = chart_options.get("tooltip_date_format", "LLLL")
            output[chart_group]["tooltip_date_format"] = tooltip_date_format

            # Credits Text
            credits = chart_options.get("credits", "")
            output[chart_group]["credits"] = credits

            # Credits URL
            credits_url = chart_options.get("credits_url", "")
            output[chart_group]["credits_url"] = credits_url

            # Credits position
            credits_position = chart_options.get(
                "credits_position", ""
            )
            output[chart_group]["credits_position"] = credits_position

            # Check if there are any user override on generation periods.
            # Takes the crontab approach. If the words hourly, daily, monthly,
            # yearly are present use them, otherwise use an integer interval if
            # available.  Since weewx could be restarted, we'll lose our
            # end-timestamp to trigger off of for chart staleness.  So we have
            # to use the timestamp of the file to generate this. If the file
            # does not exist, we need to create it first.  Once created we use
            # that to see if we need to generate a fresh data set for the
            # chart.
            generate = chart_options.get("generate", None)
            if generate is not None:
                # Default to not making a new chart
                create_new_chart = False

                # Get our intervals. Minus 60 seconds so that it'll run a
                # little more reliably on the next interval.
                if generate.lower() == "hourly":
                    chart_stale_timer = 3540
                elif generate.lower() == "daily":
                    chart_stale_timer = 86340
                elif generate.lower() == "weekly":
                    chart_stale_timer = 604740
                elif generate.lower() == "monthly":
                    chart_stale_timer = 2629686
                elif generate.lower() == "yearly":
                    chart_stale_timer = 31556892
                else:
                    chart_stale_timer = int(generate)

                if not os.path.isfile(json_filename):
                    # File doesn't exist. Chart is stale no matter what.
                    create_new_chart = True
                else:
                    # The file exists get timestamp to compare against what the
                    # user wants for an interval
                    if (int(time.time()) - int(os.path.getmtime(json_filename))) >= int(
                        chart_stale_timer
                    ):
                        create_new_chart = True

                # Chart isn't stale, so continue to next chart (this current
                # chart_group is skipped and not generated)
                if not create_new_chart:
                    continue

            # Loop through each [[chart_group]] within the section.
            for plotname in self.chart_dict[chart_group].sections:
                output[chart_group][plotname] = {}

                # This retains the observation position in the dictionary to
                # match the order in the conf so the chart is in the right
                # user-defined order
                output[chart_group][plotname]["series"] = OrderedDict()

                output[chart_group][plotname]["options"] = {}
                # output[chart_group][plotname]["options"]["id"] = chart_group + plotname # daychart1, weekchart1, etc.
                # Used for the graphs page and the different chart_groups
                output[chart_group][plotname]["options"][
                    "id"
                ] = plotname  # daychart1, weekchart1, etc. Used for the graphs page and the different chart_groups
                output[chart_group][plotname]["options"]["group"] = chart_group

                plot_options = accumulateLeaves(self.chart_dict[chart_group][plotname])

                # Setup the database binding, default to weewx.conf's binding
                # if none supplied.
                binding = plot_options.get(
                    "data_binding",
                    self.config_dict["StdReport"].get("data_binding", "wx_binding"),
                )
                archive = self.db_binder.get_manager(binding)

                # Generate timespan for the string time windows
                start_ts = archive.firstGoodStamp()
                stop_ts = archive.lastGoodStamp()
                timespan = weeutil.weeutil.TimeSpan(start_ts, stop_ts)

                # Find timestamps for the rolling window
                plotgen_ts = self.gen_ts
                if not plotgen_ts:
                    plotgen_ts = stop_ts
                    if not plotgen_ts:
                        plotgen_ts = time.time()

                chart_title = translate_title(label_dict, plot_options.get("title", ""))
                output[chart_group][plotname]["options"]["title"] = chart_title

                chart_subtitle = plot_options.get("subtitle", "")
                output[chart_group][plotname]["options"]["subtitle"] = chart_subtitle

                # Get the type of plot ("bar', 'line', 'spline', or 'scatter')
                plottype = plot_options.get("type", "line")
                output[chart_group][plotname]["options"]["type"] = plottype

                # gap_size has to be in milliseconds. Take the charts.conf value
                # and multiply by 1000
                gapsize = plot_options.get(
                    "gap_size", 300
                )  # Default to 5 minutes in millis
                if gapsize:
                    output[chart_group][plotname]["options"]["gap_size"] = int(gapsize) * 1000

                connectNulls = plot_options.get("connect_gaps", "false")
                output[chart_group][plotname]["options"]["connect_gaps"] = connectNulls

                xAxis_groupby = plot_options.get("group_by", None)
                xAxis_categories = plot_options.get("categories", "")
                # Check if this is a list. If not then we have 1 item, so force
                # it into a list
                if isinstance(xAxis_categories, list) is False:
                    xAxis_categories = xAxis_categories.split()
                output[chart_group][plotname]["options"][
                    "categories"
                ] = xAxis_categories

                # Grab any per-chart tooltip date format overrides
                plot_tooltip_date_format = plot_options.get("tooltip_date_format", None)
                output[chart_group][plotname]["options"][
                    "tooltip_date_format"
                ] = plot_tooltip_date_format

                # Width and height specific CSS overrides
                output[chart_group][plotname]["options"][
                    "width"
                ] = plot_options.get("width", "")
                output[chart_group][plotname]["options"][
                    "height"
                ] = plot_options.get("height", "")

                # Setup legend option
                legend = plot_options.get("legend", None)
                if legend is None:
                    # Default to true if the option is missing
                    output[chart_group][plotname]["options"]["legend"] = "true"
                else:
                    # JS parses this as JSON, so only these two values can reach it
                    try:
                        output[chart_group][plotname]["options"]["legend"] = "true" if to_bool(legend) else "false"
                    except ValueError:
                        output[chart_group][plotname]["options"]["legend"] = "true"

                # Setup exporting option
                exporting = plot_options.get("download_button", None)
                if exporting is not None and to_bool(exporting):
                    # Only turn on exporting if it's not none and it's true (1 or True)
                    output[chart_group][plotname]["options"]["download_button"] = "true"
                else:
                    output[chart_group][plotname]["options"]["download_button"] = "false"

                # Loop through each [[[observation]]] within the chart_group.
                for line_name in self.chart_dict[chart_group][plotname].sections:
                    output[chart_group][plotname]["series"][line_name] = {}
                    output[chart_group][plotname]["series"][line_name][
                        "section"
                    ] = line_name

                    line_options = accumulateLeaves(
                        self.chart_dict[chart_group][plotname][line_name]
                    )

                    # Look for any keyword timespans first and default to those
                    # start/stop times for the chart
                    time_length = line_options.get("time_length", 86400)
                    time_ago = int(line_options.get("time_ago", 1))
                    day_specific = line_options.get(
                        "day_specific", 1
                    )  # Force a day so we don't error out
                    month_specific = line_options.get(
                        "month_specific", 8
                    )  # Force a month so we don't error out
                    year_specific = line_options.get(
                        "year_specific", 2019
                    )  # Force a year so we don't error out
                    start_at_midnight = to_bool(
                        line_options.get("start_at_midnight", False)
                    )  # Should our timespan start at midnight?
                    start_at_whole_hour = to_bool(
                        line_options.get("start_at_whole_hour", False)
                    )  # Should our timespan start at a whole hour?
                    start_at_beginning_of_month = to_bool(
                        line_options.get("start_at_beginning_of_month", False)
                    )  # Should our timespan start at the beginning of a month?
                    if time_length == "today":
                        minstamp, maxstamp = archiveDaySpan(timespan.stop)
                    elif time_length == "week":
                        week_start = to_int(
                            self.config_dict["Station"].get("week_start", 6)
                        )
                        minstamp, maxstamp = archiveWeekSpan(timespan.stop, week_start)
                    elif time_length == "month":
                        minstamp, maxstamp = archiveMonthSpan(timespan.stop)
                    elif time_length == "year":
                        minstamp, maxstamp = archiveYearSpan(timespan.stop)
                    elif time_length == "days_ago":
                        minstamp, maxstamp = archiveDaySpan(
                            timespan.stop, days_ago=time_ago
                        )
                    elif time_length == "weeks_ago":
                        week_start = to_int(
                            self.config_dict["Station"].get("week_start", 6)
                        )
                        minstamp, maxstamp = archiveWeekSpan(
                            timespan.stop, week_start, weeks_ago=time_ago
                        )
                    elif time_length == "months_ago":
                        minstamp, maxstamp = archiveMonthSpan(
                            timespan.stop, months_ago=time_ago
                        )
                    elif time_length == "years_ago":
                        minstamp, maxstamp = archiveYearSpan(
                            timespan.stop, years_ago=time_ago
                        )
                    elif time_length == "day_specific":
                        # Set an arbitrary hour within the specific day to get
                        # that full day timespan and not the day before.
                        # e.g. 1pm
                        day_dt = datetime.datetime.strptime(
                            str(year_specific)
                            + "-"
                            + str(month_specific)
                            + "-"
                            + str(day_specific)
                            + " 13",
                            "%Y-%m-%d %H",
                        )
                        daystamp = int(time.mktime(day_dt.timetuple()))
                        minstamp, maxstamp = archiveDaySpan(daystamp)
                    elif time_length == "month_specific":
                        # Set an arbitrary day within the specific month to get
                        # that full month timespan and not the day before.
                        # e.g. 5th day
                        month_dt = datetime.datetime.strptime(
                            str(year_specific) + "-" + str(month_specific) + "-5",
                            "%Y-%m-%d",
                        )
                        monthstamp = int(time.mktime(month_dt.timetuple()))
                        minstamp, maxstamp = archiveMonthSpan(monthstamp)
                    elif time_length == "year_specific":
                        # Get a date in the middle of the year to get the full
                        # year epoch so weewx can find the year timespan.
                        year_dt = datetime.datetime.strptime(
                            str(year_specific) + "-8-1", "%Y-%m-%d"
                        )
                        yearstamp = int(time.mktime(year_dt.timetuple()))
                        minstamp, maxstamp = archiveYearSpan(yearstamp)
                    elif time_length == "year_to_now":
                        minstamp, maxstamp = self.timespan_year_to_now(timespan.stop)
                    elif time_length == "hour_ago_to_now":
                        if start_at_midnight:
                            span_start, span_stop = archiveSpanSpan(
                                timespan.stop, hour_delta=time_ago
                            )
                            minstamp, maxstamp = TimeSpan(
                                startOfDay(span_start), span_stop
                            )
                        else:
                            minstamp, maxstamp = archiveSpanSpan(
                                timespan.stop, hour_delta=time_ago
                            )
                    elif time_length == "day_ago_to_now":
                        if start_at_midnight:
                            span_start, span_stop = archiveSpanSpan(
                                timespan.stop, day_delta=time_ago
                            )
                            minstamp, maxstamp = TimeSpan(
                                startOfDay(span_start), span_stop
                            )
                        else:
                            minstamp, maxstamp = archiveSpanSpan(
                                timespan.stop, day_delta=time_ago
                            )
                    elif time_length == "week_ago_to_now":
                        if start_at_midnight:
                            span_start, span_stop = archiveSpanSpan(
                                timespan.stop, week_delta=time_ago
                            )
                            minstamp, maxstamp = TimeSpan(
                                startOfDay(span_start), span_stop
                            )
                        else:
                            minstamp, maxstamp = archiveSpanSpan(
                                timespan.stop, week_delta=time_ago
                            )
                    elif time_length == "month_ago_to_now":
                        if start_at_midnight:
                            span_start, span_stop = archiveSpanSpan(
                                timespan.stop, month_delta=time_ago
                            )
                            minstamp, maxstamp = TimeSpan(
                                startOfDay(span_start), span_stop
                            )
                        else:
                            minstamp, maxstamp = archiveSpanSpan(
                                timespan.stop, month_delta=time_ago
                            )
                    elif time_length == "year_ago_to_now":
                        if start_at_midnight:
                            span_start, span_stop = archiveSpanSpan(
                                timespan.stop, year_delta=time_ago
                            )
                            minstamp, maxstamp = TimeSpan(
                                startOfDay(span_start), span_stop
                            )
                        else:
                            minstamp, maxstamp = archiveSpanSpan(
                                timespan.stop, year_delta=time_ago
                            )
                    elif time_length == "timestamp_ago_to_now":
                        if start_at_midnight:
                            minstamp, maxstamp = TimeSpan(
                                startOfDay(time_ago), timespan.stop
                            )
                        else:
                            minstamp, maxstamp = TimeSpan(time_ago, timespan.stop)
                    elif time_length == "timespan_specific":
                        minstamp = line_options.get("timespan_start", None)
                        maxstamp = line_options.get("timespan_stop", None)
                        if minstamp is None or maxstamp is None:
                            logerr(
                                "EChartsJsonGenerator: %s skipped. timespan_specific needs "
                                "both timespan_start and timespan_stop." % line_name
                            )
                            del output[chart_group][plotname]["series"][line_name]
                            continue
                        # Options from charts.conf are strings
                        try:
                            minstamp = int(float(minstamp))
                            maxstamp = int(float(maxstamp))
                        except (TypeError, ValueError):
                            logerr(
                                "EChartsJsonGenerator: %s skipped. timespan_start and "
                                "timespan_stop have to be timestamps." % line_name
                            )
                            del output[chart_group][plotname]["series"][line_name]
                            continue
                    elif time_length == "all":
                        minstamp = start_ts
                        maxstamp = stop_ts
                    else:
                        # Rolling timespans using seconds

                        # Convert to int() for minstamp math and for
                        # point_timestamp conditional later
                        time_length = int(time_length)

                        # Take the generation time and subtract the time_length
                        # to get our start time
                        if start_at_midnight:
                            span_start = plotgen_ts - time_length
                            minstamp = startOfDay(span_start)
                        else:
                            minstamp = plotgen_ts - time_length
                        maxstamp = plotgen_ts

                    if start_at_whole_hour:
                        minstamp -= minstamp % 3600
                    
                    if start_at_beginning_of_month:
                        minstamp = archiveMonthSpan(minstamp)[0]

                    # Find if this chart is using a new database binding.
                    # Default to the binding set in plot_options
                    binding = line_options.get("data_binding", binding)
                    archive = self.db_binder.get_manager(binding)

                    # Find the observation type if specified (e.g. more than 1
                    # of the same on a chart). (e.g. outTemp, rainFall,
                    # windDir, etc.)
                    observation_type = line_options.get("observation", line_name)
                    output[chart_group][plotname]["series"][line_name]["observation"] = observation_type

                    # If we have a weather range, define what the actual
                    # observation type to lookup in the db is, and to use for
                    # yAxis labels
                    weatherRange_obs_lookup = line_options.get("range_observation", None)

                    # Get any custom names for this observation
                    name = line_options.get("name", None)
                    if not name:
                        # No explicit name. Look up a generic one. NB:
                        # label_dict is a KeyDict which will substitute the key
                        # if the value is not in the dictionary.
                        if weatherRange_obs_lookup is not None:
                            name = label_dict[weatherRange_obs_lookup]
                        else:
                            name = label_dict[observation_type]
                    else:
                        name = translate_title(label_dict, name)

                    # Look for aggregation type:
                    aggregate_type = line_options.get("aggregate_type")
                    if aggregate_type in (None, "", "None", "none"):
                        # No aggregation specified.
                        aggregate_type = aggregate_interval = None
                    else:
                        try:
                            # Aggregation specified. Get the interval.
                            aggregate_interval = weeutil.weeutil.nominal_spans(
                                line_options.get(
                                "aggregate_interval"
                            ))
                        except KeyError:
                            logerr(
                                "EChartsJsonGenerator: aggregate interval required for aggregate type %s"
                                % aggregate_type
                            )
                            logerr(
                                "EChartsJsonGenerator: line type %s skipped"
                                % observation_type
                            )
                            continue
                            
                    # use different target unit
                    special_target_unit = line_options.get("unit",None)

                    # Get the unit label
                    if observation_type == "rainTotal":
                        obs_label = "rain"
                    elif (
                        observation_type == "weatherRange"
                        and weatherRange_obs_lookup is not None
                    ):
                        obs_label = weatherRange_obs_lookup
                    else:
                        obs_label = observation_type
                    unit_label = line_options.get(
                        "axis_unit",
                        self.formatter.get_label_string(
                            special_target_unit if special_target_unit else self.converter.getTargetUnit(obs_label,aggregate_type)[0]
                        ),
                    )

                    # Set the yAxis label. Place into series for custom
                    # JavaScript.
                    yAxisLabel_config = line_options.get("axis_label", None)
                    # Set a default axis label if charts.conf axis_label is
                    # none and there's a unit_label - e.g. Temperature (F)
                    if yAxisLabel_config is None and unit_label:
                        yAxis_label = name + " (" + unit_label.strip() + ")"
                    elif yAxisLabel_config and unit_label:
                        yAxis_label = (
                            yAxisLabel_config + " (" + unit_label.strip() + ")"
                        )
                    elif yAxisLabel_config:
                        yAxis_label = yAxisLabel_config
                    else:
                        # Unknown observation, set the default label to ""
                        yAxis_label = ""
                    output[chart_group][plotname]["options"][
                        "axis_label"
                    ] = yAxis_label
                    output[chart_group][plotname]["series"][line_name][
                        "axis_label"
                    ] = yAxis_label
                    # The unit the data is in, for the visitor's unit switch
                    output[chart_group][plotname]["series"][line_name]["unit"] = (
                        special_target_unit
                        or self.converter.getTargetUnit("windSpeed" if obs_label == "haysChart" else obs_label, aggregate_type)[0]
                    )

                    # Check for average type:
                    average_type = line_options.get("average_type")
                    if average_type in (None, "", "None", "none"):
                        # No average type specified so force to none.
                        average_type = None

                    # Mirrored charts
                    mirrored_value = line_options.get("mirrored", None)

                    # Custom CSS
                    css_class = line_options.get("css_class", None)
                    output[chart_group][plotname]["options"]["css_class"] = css_class

                    # Setup polar charts
                    polar = line_options.get("polar", None)
                    if polar is not None and to_bool(polar):
                        # Only turn on polar if it's not none and it's true (1 or True)
                        output[chart_group][plotname]["series"][line_name][
                            "polar"
                        ] = "true"
                    else:
                        output[chart_group][plotname]["series"][line_name][
                            "polar"
                        ] = "false"

                    # Every option set on the line in charts.conf goes to the browser
                    for option_name, option_value in self.chart_dict[
                        chart_group
                    ][plotname][line_name].items():
                        output[chart_group][plotname]["series"][line_name][
                            option_name
                        ] = option_value

                    # Override any line options with standardized
                    # data, then generate the data output
                    output[chart_group][plotname]["series"][line_name]["name"] = name

                    # Set the yAxis min and max if present. Useful for the
                    # rxCheckPercent plots
                    yAxis_min = line_options.get("axis_min", None)
                    if yAxis_min:
                        output[chart_group][plotname]["series"][line_name][
                            "axis_min"
                        ] = yAxis_min
                    yAxis_max = line_options.get("axis_max", None)
                    if yAxis_max:
                        output[chart_group][plotname]["series"][line_name][
                            "axis_max"
                        ] = yAxis_max

                    # data rounding
                    obs_round = None
                    if (obs_round is None and 
                        self.chart_dict[chart_group][plotname][line_name].get("number_format",dict()).get(
                            "decimals") is not None
                       ):
                        # The user specified decimals. Use them for rounding,
                        # too.
                        try:
                            obs_round = float(self.chart_dict[chart_group][plotname][line_name]["number_format"]["decimals"])
                        except (ValueError,TypeError):
                            logerr("cannot use numberFormat decimals %s for rounding" % self.chart_dict[chart_group][plotname][line_name]["number_format"]["decimals"])
                    if obs_round is None:
                        # Add rounding from weewx.conf/skin.conf for the tooltips
                        if observation_type == "rainTotal":
                            rounding_obs_lookup = "rain"
                        elif observation_type == "weatherRange":
                            rounding_obs_lookup = weatherRange_obs_lookup
                        elif observation_type == "haysChart":
                            rounding_obs_lookup = "windSpeed"
                        else:
                            rounding_obs_lookup = observation_type
                        try:
                            obs_group = weewx.units.obs_group_dict[rounding_obs_lookup]
                            obs_unit = self.converter.group_unit_dict[obs_group]
                            decimals = re.search(
                                r"\.(\d+)f",
                                self.skin_dict["Units"]["StringFormats"].get(obs_unit, "0"),
                            )
                            obs_round = decimals.group(1) if decimals else -1
                        except:
                            # Not a valid weewx schema name - maybe this is
                            # windRose or something?
                            obs_round = -1
                    output[chart_group][plotname]["series"][line_name][
                        "rounding"
                    ] = obs_round

                    # Set default colors, unless the user has specified
                    # otherwise in charts.conf
                    speed_colors = line_options.get("speed_colors", DEFAULT_SPEED_COLORS)
                    if not isinstance(speed_colors, list):
                        speed_colors = [speed_colors]
                    wind_rose_color = {i: (speed_colors[i] if i < len(speed_colors) else DEFAULT_SPEED_COLORS[i]).strip()
                                       for i in range(7)}

                    # The air quality chart shows the station's own reading
                    if observation_type == "aqiChart":
                        self.station_aqi = self.get_station_aqi(archive, line_options, label_dict, plotgen_ts)

                    # Build series data. An exception here would freeze all the chart groups after this one.
                    try:
                        series_data = self.get_observation_data(
                            binding,
                            archive,
                            observation_type,
                            minstamp,
                            maxstamp,
                            aggregate_type,
                            aggregate_interval,
                            average_type,
                            time_length,
                            xAxis_groupby,
                            xAxis_categories,
                            mirrored_value,
                            weatherRange_obs_lookup,
                            wind_rose_color,
                            special_target_unit,
                            obs_round
                        )
                    except Exception as error:
                        # get_observation_data wraps most errors in a Warning, with the original as its context
                        if isinstance(error, DATABASE_DOWN) or isinstance(error.__context__, DATABASE_DOWN):
                            raise
                        logerr(
                            "EChartsJsonGenerator: [%s] [[%s]] [[[%s]]] skipped: %s"
                            % (chart_group, plotname, line_name, error)
                        )
                        del output[chart_group][plotname]["series"][line_name]
                        continue

                    # Build the final series data JSON
                    if isinstance(series_data, dict):
                        # If the returned type is a dict, then it's from the
                        # xAxis groupby section containing labels. Need to
                        # repack data, and update xAxis_categories.

                        # Use SQL Labels?
                        if "use_sql_labels" in series_data:
                            if series_data["use_sql_labels"]:
                                output[chart_group][plotname]["options"][
                                    "categories"
                                ] = series_data["xAxis_groupby_labels"]
                        elif "weatherRange" in series_data:
                            output[chart_group][plotname]["series"][line_name][
                                "range_unit"
                            ] = series_data["range_unit"]
                            output[chart_group][plotname]["series"][line_name][
                                "range_unit_label"
                            ] = series_data["range_unit_label"]

                        # No matter what, reset data back to just the series
                        # data and not a dict of values
                        output[chart_group][plotname]["series"][line_name][
                            "data"
                        ] = list(series_data["obsdata"])
                    else:
                        # No custom series data overrides, so just add
                        # series_data to the chart series data
                        output[chart_group][plotname]["series"][line_name][
                            "data"
                        ] = list(series_data)

                    # Final pass through
                    # self.series_options_to_float() to convert the
                    # remaining options with numeric values to float such that
                    # the browser can use them.
                    output[chart_group][plotname]["series"][
                        line_name
                    ] = self.series_options_to_float(
                        output[chart_group][plotname]["series"][line_name]
                    )

            # Write the output to the JSON file
            with open(json_filename, mode="w") as jf:
                jf.write(json.dumps(output[chart_group], indent=4))

            # Save the chart config, as read, to a json file for debugging
            chart_json_filename = html_dest_dir + "/charts_conf.json"
            with open(chart_json_filename, mode="w") as cjf:
                cjf.write(json.dumps(self.chart_dict, indent=4))

        if to_bool(self.skin_dict["Extras"].get("chart_builder_enabled", True)):
            try:
                self.write_chart_builder_data(label_dict)
            except Exception as e:
                logerr("EChartsJsonGenerator: chart builder data not written: %s" % e)

    # The chart builder page previews charts from this file: each observation with data in the last 30 days,
    # over four spans, in display units. Rain-type observations are summed, the rest averaged.
    CHART_BUILDER_SPANS = (("day", 86400, None), ("week", 7 * 86400, 3600), ("month", 31 * 86400, 6 * 3600),
                           ("year", 365 * 86400, 86400))

    def write_chart_builder_data(self, label_dict):
        dest = os.path.join(self.config_dict["WEEWX_ROOT"], self.skin_dict["HTML_ROOT"], "json", "chart_builder.json")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if os.path.isfile(dest) and time.time() - os.path.getmtime(dest) < 3540:
            return
        binding = self.config_dict["StdReport"].get("data_binding", "wx_binding")
        archive = self.db_binder.get_manager(binding)
        stop = archive.lastGoodStamp()
        if stop is None:
            return
        out = {"generated": stop, "observations": OrderedDict()}
        for obs in archive.sqlkeys:
            if obs in ("dateTime", "usUnits", "interval"):
                continue
            try:
                entry = self.chart_builder_entry(archive, obs, stop, label_dict)
            except Exception as e:
                logdbg("EChartsJsonGenerator: chart builder skips %s: %s" % (obs, e))
                continue
            if entry:
                out["observations"][obs] = entry
        with open(dest, mode="w") as f:
            json.dump(out, f, separators=(",", ":"))

    def chart_builder_entry(self, archive, obs, stop, label_dict):
        count = archive.getSql("SELECT COUNT(`%s`) FROM %s WHERE dateTime > ?" % (obs, archive.table_name), (stop - 30 * 86400,))
        if not count or not count[0]:
            return None
        group = weewx.units.obs_group_dict.get(obs, "")
        summed = group in ("group_rain", "group_energy", "group_count")
        how = "sum" if summed else "avg"
        unit, unit_group = weewx.units.getStandardUnitType(archive.std_unit_system, obs, how)
        entry = {"label": label_dict[obs], "group": group, "aggregate": how, "spans": {}}
        places = 2
        for name, length, interval in self.CHART_BUILDER_SPANS:
            rows = self.chart_builder_rows(archive, obs, stop - length, stop, interval, how)
            points = []
            for t, v in rows:
                if v is not None:
                    v, unit_out, _ = self.converter.convert(weewx.units.ValueTuple(float(v), unit, unit_group))
                    decimals = re.search(r"\.(\d+)f", self.formatter.unit_format_dict.get(unit_out, "%.2f") or "")
                    places = int(decimals.group(1)) if decimals else 0
                    entry["unit"] = unit_out
                    v = round(v, places)
                points.append([int(t) * 1000, v])
            entry["spans"][name] = points
        entry["unit_label"] = self.formatter.get_label_string(entry["unit"]).strip() if entry.get("unit") else ""
        return entry

    @staticmethod
    def chart_builder_rows(archive, obs, start, stop, interval, how):
        """(timestamp, value) rows: every record, or one per interval labeled by its end like weewx does.
        Day-size intervals come from the daily summaries, which follow the local calendar day."""
        col = "`%s`" % obs
        if not interval:
            return archive.genSql("SELECT dateTime, %s FROM %s WHERE dateTime > ? AND dateTime <= ? ORDER BY dateTime"
                                  % (col, archive.table_name), (start, stop))
        if interval >= 86400:
            value = "sum" if how == "sum" else "sum / count"
            return archive.genSql("SELECT dateTime + 86400, %s FROM %s_day_%s WHERE dateTime >= ? AND dateTime < ? AND count > 0 "
                                  "ORDER BY dateTime" % (value, archive.table_name, obs), (start, stop))
        # The MySQL driver formats the statement with %, so the modulo operator has to be doubled there
        mod = "%%" if getattr(archive.connection, "dbtype", "") == "mysql" else "%"
        bucket = "(dateTime - 1) - (dateTime - 1) %s %d + %d" % (mod, interval, interval)
        return archive.genSql("SELECT %s, %s(%s) FROM %s WHERE dateTime > ? AND dateTime <= ? AND %s IS NOT NULL GROUP BY %s ORDER BY %s"
                              % (bucket, how.upper(), col, archive.table_name, col, bucket, bucket), (start, stop))

    def get_observation_data(
        self,
        binding,
        archive,
        observation,
        start_ts,
        end_ts,
        aggregate_type,
        aggregate_interval,
        average_type,
        time_length,
        xAxis_groupby,
        xAxis_categories,
        mirrored_value,
        weatherRange_obs_lookup,
        wind_rose_color,
        special_target_unit,
        obs_round
    ):
        """
        Get the SQL vectors for the observation, the aggregate type and the
        interval of time
        """

        if observation == "windRose":
            # Wind rose: how often the wind blew from each direction, with wind
            # speeds split into the first 7 Beaufort groups.
            # https://en.wikipedia.org/wiki/Beaufort_scale

            # Force no aggregate_type
            if aggregate_type:
                aggregate_type = None

            # Force no aggregate_interval
            if aggregate_interval:
                aggregate_interval = None

            # Get windDir observations.
            obs_lookup = "windDir"
            (time_start_vt, time_stop_vt, windDir_vt) = weewx.xtypes.get_series(
                obs_lookup,
                TimeSpan(start_ts, end_ts),
                archive,
                aggregate_type,
                aggregate_interval,
            )
            # windDir_vt = self.converter.convert(windDir_vt)
            # usage_round = int(self.skin_dict['Units']['StringFormats'].get(windDir_vt[2], "0f")[-2])
            usage_round = 0  # Force round to 0 decimal
            windDir_round_vt = [self.round_none(x, usage_round) for x in windDir_vt[0]]
            # windDir_round_vt = [0.0 if v is None else v for v in windDir_round_vt]

            # Get windSpeed observations.
            obs_lookup = "windSpeed"
            (time_start_vt, time_stop_vt, windSpeed_vt) = weewx.xtypes.get_series(
                obs_lookup,
                TimeSpan(start_ts, end_ts),
                archive,
                aggregate_type,
                aggregate_interval,
            )
            windSpeed_vt = self.converter.convert(windSpeed_vt)
            # Round as the site shows the speed: 3.9 mph is shown as 4, which is in the "4-7" band
            decimals = re.search(r"\.(\d+)f", self.skin_dict["Units"]["StringFormats"].get(windSpeed_vt[1], ""))
            usage_round = int(decimals.group(1)) if decimals else 2
            windSpeed_round_vt = [
                self.round_none(x, usage_round) for x in windSpeed_vt[0]
            ]

            # Exit if the vectors are None
            if windDir_vt[1] is None or windSpeed_vt[1] is None:
                empty_windrose = [{"name": "", "data": []}]
                return empty_windrose

            # Get the unit label from the skin dict for speed.
            windSpeed_unit = windSpeed_vt[1]
            windSpeed_unit_label = self.skin_dict["Units"]["Labels"][windSpeed_unit]

            # Merge the two outputs so we have a consistent data set to filter on
            merged = zip(windDir_round_vt, windSpeed_round_vt)

            # Sort by beaufort wind speeds
            (
                group_0_windDir,
                group_0_windSpeed,
                group_1_windDir,
                group_1_windSpeed,
                group_2_windDir,
                group_2_windSpeed,
                group_3_windDir,
                group_3_windSpeed,
                group_4_windDir,
                group_4_windSpeed,
                group_5_windDir,
                group_5_windSpeed,
                group_6_windDir,
                group_6_windSpeed,
            ) = ([] for i in range(14))
            # Each band starts where the one before it ends, so no speed falls between two bands
            for windData in merged:
                if windData[0] is not None and windData[1] is not None:
                    if windSpeed_unit in ("mile_per_hour", "mile_per_hour2"):
                        if windData[1] < 1:
                            group_0_windDir.append(windData[0])
                            group_0_windSpeed.append(windData[1])
                        elif windData[1] < 4:
                            group_1_windDir.append(windData[0])
                            group_1_windSpeed.append(windData[1])
                        elif windData[1] < 8:
                            group_2_windDir.append(windData[0])
                            group_2_windSpeed.append(windData[1])
                        elif windData[1] < 13:
                            group_3_windDir.append(windData[0])
                            group_3_windSpeed.append(windData[1])
                        elif windData[1] < 19:
                            group_4_windDir.append(windData[0])
                            group_4_windSpeed.append(windData[1])
                        elif windData[1] < 25:
                            group_5_windDir.append(windData[0])
                            group_5_windSpeed.append(windData[1])
                        else:
                            group_6_windDir.append(windData[0])
                            group_6_windSpeed.append(windData[1])
                    elif windSpeed_unit in ("km_per_hour", "km_per_hour2"):
                        if windData[1] < 2:
                            group_0_windDir.append(windData[0])
                            group_0_windSpeed.append(windData[1])
                        elif windData[1] < 6:
                            group_1_windDir.append(windData[0])
                            group_1_windSpeed.append(windData[1])
                        elif windData[1] < 12:
                            group_2_windDir.append(windData[0])
                            group_2_windSpeed.append(windData[1])
                        elif windData[1] < 20:
                            group_3_windDir.append(windData[0])
                            group_3_windSpeed.append(windData[1])
                        elif windData[1] < 29:
                            group_4_windDir.append(windData[0])
                            group_4_windSpeed.append(windData[1])
                        elif windData[1] < 39:
                            group_5_windDir.append(windData[0])
                            group_5_windSpeed.append(windData[1])
                        else:
                            group_6_windDir.append(windData[0])
                            group_6_windSpeed.append(windData[1])
                    elif windSpeed_unit in ("meter_per_second", "meter_per_second2"):
                        if windData[1] < 0.5:
                            group_0_windDir.append(windData[0])
                            group_0_windSpeed.append(windData[1])
                        elif windData[1] < 1.6:
                            group_1_windDir.append(windData[0])
                            group_1_windSpeed.append(windData[1])
                        elif windData[1] < 3.4:
                            group_2_windDir.append(windData[0])
                            group_2_windSpeed.append(windData[1])
                        elif windData[1] < 5.6:
                            group_3_windDir.append(windData[0])
                            group_3_windSpeed.append(windData[1])
                        elif windData[1] < 8:
                            group_4_windDir.append(windData[0])
                            group_4_windSpeed.append(windData[1])
                        elif windData[1] < 10.8:
                            group_5_windDir.append(windData[0])
                            group_5_windSpeed.append(windData[1])
                        else:
                            group_6_windDir.append(windData[0])
                            group_6_windSpeed.append(windData[1])
                    elif windSpeed_unit in ("knot", "knot2"):
                        if windData[1] < 1:
                            group_0_windDir.append(windData[0])
                            group_0_windSpeed.append(windData[1])
                        elif windData[1] < 4:
                            group_1_windDir.append(windData[0])
                            group_1_windSpeed.append(windData[1])
                        elif windData[1] < 7:
                            group_2_windDir.append(windData[0])
                            group_2_windSpeed.append(windData[1])
                        elif windData[1] < 11:
                            group_3_windDir.append(windData[0])
                            group_3_windSpeed.append(windData[1])
                        elif windData[1] < 17:
                            group_4_windDir.append(windData[0])
                            group_4_windSpeed.append(windData[1])
                        elif windData[1] < 22:
                            group_5_windDir.append(windData[0])
                            group_5_windSpeed.append(windData[1])
                        else:
                            group_6_windDir.append(windData[0])
                            group_6_windSpeed.append(windData[1])
                    elif windSpeed_unit == "beaufort":
                        if windData[1] <= 1:
                            group_0_windDir.append(windData[0])
                            group_0_windSpeed.append(windData[1])
                        elif windData[1] == 2:
                            group_1_windDir.append(windData[0])
                            group_1_windSpeed.append(windData[1])
                        elif windData[1] == 3:
                            group_2_windDir.append(windData[0])
                            group_2_windSpeed.append(windData[1])
                        elif windData[1] == 4:
                            group_3_windDir.append(windData[0])
                            group_3_windSpeed.append(windData[1])
                        elif windData[1] == 5:
                            group_4_windDir.append(windData[0])
                            group_4_windSpeed.append(windData[1])
                        elif windData[1] == 6:
                            group_5_windDir.append(windData[0])
                            group_5_windSpeed.append(windData[1])
                        elif windData[1] >= 7:
                            group_6_windDir.append(windData[0])
                            group_6_windSpeed.append(windData[1])

            # Get the windRose data
            group_0_series_data = self.create_windrose_data(
                group_0_windDir, group_0_windSpeed
            )
            group_1_series_data = self.create_windrose_data(
                group_1_windDir, group_1_windSpeed
            )
            group_2_series_data = self.create_windrose_data(
                group_2_windDir, group_2_windSpeed
            )
            group_3_series_data = self.create_windrose_data(
                group_3_windDir, group_3_windSpeed
            )
            group_4_series_data = self.create_windrose_data(
                group_4_windDir, group_4_windSpeed
            )
            group_5_series_data = self.create_windrose_data(
                group_5_windDir, group_5_windSpeed
            )
            group_6_series_data = self.create_windrose_data(
                group_6_windDir, group_6_windSpeed
            )

            # Group all together to get wind frequency percentages
            wind_sum = sum(
                group_0_series_data
                + group_1_series_data
                + group_2_series_data
                + group_3_series_data
                + group_4_series_data
                + group_5_series_data
                + group_6_series_data
            )
            if wind_sum > 0:
                y = 0
                while y < len(group_0_series_data):
                    group_0_series_data[y] = round(
                        group_0_series_data[y] / wind_sum * 100
                    )
                    y += 1
                y = 0
                while y < len(group_1_series_data):
                    group_1_series_data[y] = round(
                        group_1_series_data[y] / wind_sum * 100
                    )
                    y += 1
                y = 0
                while y < len(group_2_series_data):
                    group_2_series_data[y] = round(
                        group_2_series_data[y] / wind_sum * 100
                    )
                    y += 1
                y = 0
                while y < len(group_3_series_data):
                    group_3_series_data[y] = round(
                        group_3_series_data[y] / wind_sum * 100
                    )
                    y += 1
                y = 0
                while y < len(group_4_series_data):
                    group_4_series_data[y] = round(
                        group_4_series_data[y] / wind_sum * 100
                    )
                    y += 1
                y = 0
                while y < len(group_5_series_data):
                    group_5_series_data[y] = round(
                        group_5_series_data[y] / wind_sum * 100
                    )
                    y += 1
                y = 0
                while y < len(group_6_series_data):
                    group_6_series_data[y] = round(
                        group_6_series_data[y] / wind_sum * 100
                    )
                    y += 1

            # Setup the labels based on unit
            if windSpeed_unit in ("mile_per_hour", "mile_per_hour2"):
                group_0_speedRange = "< 1"
                group_1_speedRange = "1-3"
                group_2_speedRange = "4-7"
                group_3_speedRange = "8-12"
                group_4_speedRange = "13-18"
                group_5_speedRange = "19-24"
                group_6_speedRange = "25+"
            elif windSpeed_unit in ("km_per_hour", "km_per_hour2"):
                group_0_speedRange = "< 2"
                group_1_speedRange = "2-5"
                group_2_speedRange = "6-11"
                group_3_speedRange = "12-19"
                group_4_speedRange = "20-28"
                group_5_speedRange = "29-38"
                group_6_speedRange = "39+"
            elif windSpeed_unit in ("meter_per_second", "meter_per_second2"):
                group_0_speedRange = "< 0.5"
                group_1_speedRange = "0.5-1.5"
                group_2_speedRange = "1.6-3.3"
                group_3_speedRange = "3.4-5.5"
                group_4_speedRange = "5.6-7.9"
                group_5_speedRange = "8-10.7"
                group_6_speedRange = "10.8+"
            elif windSpeed_unit in ("knot", "knot2"):
                group_0_speedRange = "< 1"
                group_1_speedRange = "1-3"
                group_2_speedRange = "4-6"
                group_3_speedRange = "7-10"
                group_4_speedRange = "11-16"
                group_5_speedRange = "17-21"
                group_6_speedRange = "22+"
            elif windSpeed_unit == "beaufort":
                group_0_speedRange = "0"
                group_1_speedRange = "1"
                group_2_speedRange = "2"
                group_3_speedRange = "3"
                group_4_speedRange = "4"
                group_5_speedRange = "5"
                group_6_speedRange = "6+"

            group_0_name = "%s %s" % (group_0_speedRange, windSpeed_unit_label)
            group_1_name = "%s %s" % (group_1_speedRange, windSpeed_unit_label)
            group_2_name = "%s %s" % (group_2_speedRange, windSpeed_unit_label)
            group_3_name = "%s %s" % (group_3_speedRange, windSpeed_unit_label)
            group_4_name = "%s %s" % (group_4_speedRange, windSpeed_unit_label)
            group_5_name = "%s %s" % (group_5_speedRange, windSpeed_unit_label)
            group_6_name = "%s %s" % (group_6_speedRange, windSpeed_unit_label)

            group_0 = {
                "name": group_0_name,
                "type": "column",
                "color": wind_rose_color[0],
                "zIndex": 106,
                "stacking": "normal",
                "fillOpacity": 0.75,
                "data": group_0_series_data,
            }
            group_1 = {
                "name": group_1_name,
                "type": "column",
                "color": wind_rose_color[1],
                "zIndex": 105,
                "stacking": "normal",
                "fillOpacity": 0.75,
                "data": group_1_series_data,
            }
            group_2 = {
                "name": group_2_name,
                "type": "column",
                "color": wind_rose_color[2],
                "zIndex": 104,
                "stacking": "normal",
                "fillOpacity": 0.75,
                "data": group_2_series_data,
            }
            group_3 = {
                "name": group_3_name,
                "type": "column",
                "color": wind_rose_color[3],
                "zIndex": 103,
                "stacking": "normal",
                "fillOpacity": 0.75,
                "data": group_3_series_data,
            }
            group_4 = {
                "name": group_4_name,
                "type": "column",
                "color": wind_rose_color[4],
                "zIndex": 102,
                "stacking": "normal",
                "fillOpacity": 0.75,
                "data": group_4_series_data,
            }
            group_5 = {
                "name": group_5_name,
                "type": "column",
                "color": wind_rose_color[5],
                "zIndex": 101,
                "stacking": "normal",
                "fillOpacity": 0.75,
                "data": group_5_series_data,
            }
            group_6 = {
                "name": group_6_name,
                "type": "column",
                "color": wind_rose_color[6],
                "zIndex": 100,
                "stacking": "normal",
                "fillOpacity": 0.75,
                "data": group_6_series_data,
            }

            # Append everything into a list and return right away, do not
            # process rest of function
            series = [group_0, group_1, group_2, group_3, group_4, group_5, group_6]
            return series

        # Weather range: each day's low, high and average
        if observation == "weatherRange":

            # Define what we are looking up
            if weatherRange_obs_lookup is not None:
                obs_lookup = weatherRange_obs_lookup
            else:
                raise Warning(
                    "Error trying to create the weather range graph. "
                    "You are missing the range_type configuration item."
                )

            # Force 1 day if aggregate_interval. These charts are meant to show
            # a column range for high, low and average for a full day.
            if not aggregate_interval:
                aggregate_interval = 86400

            # Get min values
            aggregate_type = "min"
            try:
                (time_start_vt, time_stop_vt, obs_vt) = weewx.xtypes.get_series(
                    obs_lookup,
                    TimeSpan(start_ts, end_ts),
                    archive,
                    aggregate_type,
                    aggregate_interval,
                )
            except Exception as e:
                raise Warning(
                    "Error trying to use database binding %s to graph observation %s. "
                    "Error was: %s." % (binding, obs_lookup, e)
                )

            self.insert_null_value_timestamps_to_end_ts(time_start_vt, time_stop_vt, obs_vt, start_ts, end_ts, aggregate_interval)

            min_obs_vt = self.converter.convert(obs_vt)

            # Get max values
            aggregate_type = "max"
            try:
                (time_start_vt, time_stop_vt, obs_vt) = weewx.xtypes.get_series(
                    obs_lookup,
                    TimeSpan(start_ts, end_ts),
                    archive,
                    aggregate_type,
                    aggregate_interval,
                )
            except Exception as e:
                raise Warning(
                    "Error trying to use database binding %s to graph observation %s. "
                    "Error was: %s." % (binding, obs_lookup, e)
                )

            self.insert_null_value_timestamps_to_end_ts(time_start_vt, time_stop_vt, obs_vt, start_ts, end_ts, aggregate_interval)

            max_obs_vt = self.converter.convert(obs_vt)

            # Get avg values
            aggregate_type = "avg"
            try:
                (time_start_vt, time_stop_vt, obs_vt) = weewx.xtypes.get_series(
                    obs_lookup,
                    TimeSpan(start_ts, end_ts),
                    archive,
                    aggregate_type,
                    aggregate_interval,
                )
            except Exception as e:
                raise Warning(
                    "Error trying to use database binding %s to graph observation %s. "
                    "Error was: %s." % (binding, obs_lookup, e)
                )

            self.insert_null_value_timestamps_to_end_ts(time_start_vt, time_stop_vt, obs_vt, start_ts, end_ts, aggregate_interval)

            avg_obs_vt = self.converter.convert(obs_vt)

            obs_unit = avg_obs_vt[1]
            obs_unit_label = self.skin_dict["Units"]["Labels"].get(obs_unit, "")

            # Convert to millis and zip all together
            time_ms = [float(x) * 1000 for x in time_start_vt[0]]
            output_data = zip(time_ms, min_obs_vt[0], max_obs_vt[0], avg_obs_vt[0])

            data = {
                "weatherRange": True,
                "obsdata": output_data,
                "range_unit": obs_unit,
                "range_unit_label": obs_unit_label,
            }

            return data

        if observation == "aqiChart":
            value, category = getattr(self, "station_aqi", (aqi, aqi_category))
            data = {"aqiChart": True, "obsdata": [{"y": value, "category": category}]}
            return data

        # Hays chart
        if observation == "haysChart":

            start_ts = int(start_ts)
            end_ts = int(end_ts)

            # Set aggregate interval based on timespan and make sure it is
            # between 5 minutes and 1 day
            logging.debug("Start time is %s and end time is %s" % (start_ts, end_ts))
            aggregate_interval = (end_ts - start_ts) / 360
            if aggregate_interval < 300:
                aggregate_interval = 300
            elif aggregate_interval > 86400:
                aggregate_interval = 86400
            logging.debug("Interval is: %s" % aggregate_interval)

            aggregate_type = "max"
            # Get min values
            obs_lookup = "windSpeed"
            try:
                (time_start_vt, time_stop_vt, obs_vt) = weewx.xtypes.get_series(
                    obs_lookup,
                    TimeSpan(start_ts, end_ts),
                    archive,
                    aggregate_type,
                    aggregate_interval,
                )
            except Exception as e:
                raise Warning(
                    "Error trying to use database binding %s to graph observation %s. "
                    "Error was: %s." % (binding, obs_lookup, e)
                )

            self.insert_null_value_timestamps_to_end_ts(time_start_vt, time_stop_vt, obs_vt, start_ts, end_ts, aggregate_interval)
            
            min_obs_vt = self.converter.convert(obs_vt)

            # Get max values
            obs_lookup = "windGust"
            try:
                (time_start_vt, time_stop_vt, obs_vt) = weewx.xtypes.get_series(
                    obs_lookup,
                    TimeSpan(start_ts, end_ts),
                    archive,
                    aggregate_type,
                    aggregate_interval,
                )
            except Exception as e:
                raise Warning(
                    "Error trying to use database binding %s to graph observation %s. "
                    "Error was: %s." % (binding, obs_lookup, e)
                )

            self.insert_null_value_timestamps_to_end_ts(time_start_vt, time_stop_vt, obs_vt, start_ts, end_ts, aggregate_interval)
            
            max_obs_vt = self.converter.convert(obs_vt)

            obs_unit = max_obs_vt[1]
            obs_unit_label = self.skin_dict["Units"]["Labels"].get(obs_unit, "")

            # Convert to millis and zip all together
            time_ms = [float(x) * 1000 for x in time_start_vt[0]]
            output_data = zip(time_ms, min_obs_vt[0], max_obs_vt[0])

            data = {
                "haysChart": True,
                "obsdata": output_data,
                "range_unit": obs_unit,
                "range_unit_label": obs_unit_label,
            }

            return data

        # Rain total: rain added up over the chart
        if observation == "rainTotal":
            obs_lookup = "rain"
            # Force sum on this observation
            if aggregate_interval:
                aggregate_type = "sum"
        elif observation == "rainRate":
            obs_lookup = "rainRate"
            # Force max on this observation
            if aggregate_interval:
                aggregate_type = "max"
        else:
            obs_lookup = observation
            
        #   Special aggregation_subtype measures to enable average rainfall, max and min temperatures to be calculated
        
        if aggregate_type == "avg" and observation == "avgRainfall" and aggregate_interval == 86400:
            obs_lookup = "rain"
            obs_label = "Rainfall"

        if xAxis_groupby or len(xAxis_categories) >= 1:
            # Setup the converter - for some reason self.converter doesn't work
            # for the group_unit_dict in this section Get the target unit
            # nickname (something like 'US' or 'METRIC'):
            target_unit_nickname = self.config_dict["StdConvert"]["target_unit"]
            # Get the target unit: weewx.US, weewx.METRIC, weewx.METRICWX
            target_unit = weewx.units.unit_constants[target_unit_nickname.upper()]
            # Bind to the appropriate standard converter units
            converter = weewx.units.StdUnitConverters[target_unit]

            # Find what kind of database we're working with and specify the
            # correctly tailored SQL Query for each type of database
            data_binding = self.config_dict["StdArchive"]["data_binding"]
            database = self.config_dict["DataBindings"][data_binding]["database"]
            database_type = self.config_dict["Databases"][database]["database_type"]
            driver = self.config_dict["DatabaseTypes"][database_type]["driver"]
            xAxis_labels = []
            obsvalues = []

            # Define the xAxis group by for the sql query. Default to month
            if xAxis_groupby == "hour":
                strformat = "%H"
            elif xAxis_groupby == "day":
                strformat = "%d"
            elif xAxis_groupby == "month":
                strformat = "%m"
            elif xAxis_groupby == "year":
                strformat = "%Y"
            elif xAxis_groupby == "":
                strformat = "%m"
            else:
                strformat = "%m"

            # Default catch all in case the aggregate_type isn't defined, default to sum
            if aggregate_type is None:
                aggregate_type = "sum"

            # A span within one label cycle sorts by time, a longer one by label. MySQL needs MIN() in a GROUP BY.
            label_cycle = {"hour": 86400, "day": 28 * 86400}.get(xAxis_groupby, 366 * 86400)
            if isinstance(time_length, int) or end_ts - start_ts <= label_cycle:
                order_sql = ' ORDER BY MIN(dateTime) ASC'
                subqry_order_sql = ' ORDER BY MIN(first_dateTime) ASC'
            else:
                order_sql = ' ORDER BY %s ASC' % xAxis_groupby
                subqry_order_sql = order_sql

            # Special case for time_length = all, force to use complete days only
            if time_length == "all":
                start_ts = startOfDay(archive.firstGoodStamp()) + 86400
                end_ts = startOfDay(archive.lastGoodStamp())

            # Set up subquery groupby clause
            if xAxis_groupby == "year": subqry_groupby = '"%Y"'
            elif xAxis_groupby == "month": subqry_groupby = '"%Y%m"'
            elif xAxis_groupby == "day": subqry_groupby = '"%Y%m%d"'
            elif xAxis_groupby == "hour": subqry_groupby = '"%Y%m%d%H"'
            else: subqry_groupby = ''
                            
            if driver == "weedb.sqlite":
                # Use daily summaries where possible - MUST BE FOR WHOLE DAYS determined by start and stop times otherwise use archive
                if xAxis_groupby != "hour" and isStartOfDay(start_ts) and isStartOfDay(end_ts) and end_ts - start_ts > 0 :  # 1 or more exact days
                    # Avg is a special case
                    if aggregate_type == "avg":
                        # Avg(sum) requires a subquery with the correct group by clause
                        if average_type is not None and average_type == "sum":
                            sql_lookup = 'SELECT dt1 AS {0}, ' \
                                         'AVG(obs1) AS obs ' \
                                         'FROM (SELECT strftime("{1}", datetime(dateTime, "unixepoch", "localtime")) AS dt1, sum(sum) AS obs1, MIN(dateTime) AS first_dateTime ' \
                                                'FROM archive_day_{2} WHERE dateTime >= {3} AND dateTime < {4} '\
                                                'GROUP BY strftime({5}, datetime(dateTime, "unixepoch", "localtime"))) ' \
                                         'GROUP BY {0}{6};'.format(
                                xAxis_groupby,
                                strformat,
                                obs_lookup,
                                start_ts,
                                end_ts,
                                subqry_groupby,
                                subqry_order_sql
                            )
                        # avg cases with an average_type
                        elif average_type is not None:
                            sql_lookup = 'SELECT strftime("{0}", datetime(dateTime, "unixepoch", "localtime")) AS {1}, ' \
                                         '{2}({3}) AS obs ' \
                                         'FROM archive_day_{4}  WHERE dateTime >= {5} AND dateTime < {6} ' \
                                         'GROUP BY {1}{7};'.format(
                                strformat,
                                xAxis_groupby,
                                aggregate_type,
                                average_type,
                                obs_lookup,
                                start_ts,
                                end_ts,
                                order_sql
                            )
                        # remaining avg cases without an average_type use weighted average
                        else:
                            sql_lookup = 'SELECT strftime("{0}", datetime(dateTime, "unixepoch", "localtime")) AS {1}, ' \
                                         'SUM(wsum)/SUM(sumtime) AS obs ' \
                                         'FROM archive_day_{2}  WHERE dateTime >= {3} AND dateTime < {4} ' \
                                         'GROUP BY {1}{5};'.format(
                                strformat,
                                xAxis_groupby,
                                obs_lookup,
                                start_ts,
                                end_ts,
                                order_sql
                            )
                    # other aggregate_type cases use direct interrogation of daily summary
                    else:
                        sql_lookup = 'SELECT strftime("{0}", datetime(dateTime, "unixepoch", "localtime")) AS {1}, ' \
                                     '{2}({2}) AS obs ' \
                                     'FROM archive_day_{3}  ' \
                                     'WHERE dateTime >= {4} AND dateTime < {5} GROUP BY {1}{6};'.format(
                            strformat,
                            xAxis_groupby,
                            aggregate_type,
                            obs_lookup,
                            start_ts,
                            end_ts,
                            order_sql
                        )
                else:
                    # archive access with no average_type
                    if average_type is None:
                        sql_lookup = 'SELECT strftime("{0}", datetime(dateTime, "unixepoch", "localtime")) as {1}, ' \
                                     '{2}({3}) AS obs FROM archive ' \
                                     'WHERE dateTime >= {4} AND dateTime < {5} GROUP BY {1}{6};'.format(
                            strformat,
                            xAxis_groupby,
                            aggregate_type,
                            obs_lookup,
                            start_ts,
                            end_ts,
                            order_sql
                        )

                    # average_type requiring a subquery
                    else:
                        sql_lookup = 'SELECT dt1 AS {0}, ' \
                                     '{1}(obs1) AS obs ' \
                                     'FROM (SELECT strftime("{2}", datetime(dateTime, "unixepoch", "localtime")) AS dt1, '\
                                            '{3}({4}) AS obs1, MIN(dateTime) AS first_dateTime ' \
                                            'FROM archive WHERE dateTime >= {5} AND dateTime < {6} '\
                                            'GROUP BY strftime({7}, datetime(dateTime, "unixepoch", "localtime"))) ' \
                                     'GROUP BY {0}{8};'.format(
                            xAxis_groupby,
                            aggregate_type,
                            strformat,
                            average_type,
                            obs_lookup,
                            start_ts,
                            end_ts,
                            subqry_groupby,
                            subqry_order_sql
                        )

            elif driver == "weedb.mysql":
                # Use daily summaries where possible - MUST BE FOR WHOLE DAYS determined by start and stop times otherwise use archive
                if xAxis_groupby != "hour" and isStartOfDay(start_ts) and isStartOfDay(end_ts) and end_ts - start_ts > 0 :  # 1 or more exact days
                    # Avg is a special case
                    if aggregate_type == "avg":
                        # Avg(sum) requires a subquery with the correct group by clause
                        if average_type is not None and average_type == "sum":
                            sql_lookup = 'SELECT dt1 AS {0}, ' \
                                         'AVG(obs1) AS obs ' \
                                         'FROM (SELECT FROM_UNIXTIME( dateTime, "%{1}" ) AS dt1, sum(sum) AS obs1, MIN(dateTime) AS first_dateTime ' \
                                                'FROM archive_day_{2} WHERE dateTime >= {3} AND dateTime < {4} '\
                                                'GROUP BY FROM_UNIXTIME( dateTime, {5} ), dt1) AS periods ' \
                                         'GROUP BY {0}{6};'.format(
                                xAxis_groupby,
                                strformat,
                                obs_lookup,
                                start_ts,
                                end_ts,
                                subqry_groupby.replace("%", "%%"),
                                subqry_order_sql
                            )
                        # avg cases with an average_type
                        elif average_type is not None:
                            sql_lookup = 'SELECT FROM_UNIXTIME( dateTime, "%{0}" ) AS {1}, ' \
                                         '{2}({3}) AS obs ' \
                                         'FROM archive_day_{4}  WHERE dateTime >= {5} AND dateTime < {6} ' \
                                         'GROUP BY {1}{7};'.format(
                                strformat,
                                xAxis_groupby,
                                aggregate_type,
                                average_type,
                                obs_lookup,
                                start_ts,
                                end_ts,
                                order_sql
                            )
                        # remaining avg cases without an average_type use weighted average
                        else:
                            sql_lookup = 'SELECT FROM_UNIXTIME( dateTime, "%{0}" ) AS {1}, ' \
                                         'SUM(wsum)/SUM(sumtime) AS obs ' \
                                         'FROM archive_day_{2}  WHERE dateTime >= {3} AND dateTime < {4} ' \
                                         'GROUP BY {1}{5};'.format(
                                strformat,
                                xAxis_groupby,
                                obs_lookup,
                                start_ts,
                                end_ts,
                                order_sql
                            )
                    # other aggregate_type cases use direct interrogation of daily summary
                    else:
                        sql_lookup = 'SELECT FROM_UNIXTIME( dateTime, "%{0}" ) AS {1}, ' \
                                     '{2}({2}) AS obs ' \
                                     'FROM archive_day_{3}  ' \
                                     'WHERE dateTime >= {4} AND dateTime < {5} GROUP BY {1}{6};'.format(
                            strformat,
                            xAxis_groupby,
                            aggregate_type,
                            obs_lookup,
                            start_ts,
                            end_ts,
                            order_sql
                        )
                else:
                    # archive access with no average_type
                    if average_type is None:
                        sql_lookup = 'SELECT FROM_UNIXTIME( dateTime, "%{0}" ) as {1}, ' \
                                     '{2}({3}) AS obs FROM archive ' \
                                     'WHERE dateTime >= {4} AND dateTime < {5} GROUP BY {1}{6};'.format(
                            strformat,
                            xAxis_groupby,
                            aggregate_type,
                            obs_lookup,
                            start_ts,
                            end_ts,
                            order_sql
                        )

                    # average_type requiring a subquery
                    else:
                        sql_lookup = 'SELECT dt1 AS {0}, ' \
                                     '{1}(obs1) AS obs ' \
                                     'FROM (SELECT FROM_UNIXTIME( dateTime, "%{2}" ) AS dt1, '\
                                            '{3}({4}) AS obs1, MIN(dateTime) AS first_dateTime ' \
                                            'FROM archive WHERE dateTime >= {5} AND dateTime < {6} '\
                                            'GROUP BY FROM_UNIXTIME( dateTime, {7} ), dt1) AS periods ' \
                                     'GROUP BY {0}{8};'.format(
                            xAxis_groupby,
                            aggregate_type,
                            strformat,
                            average_type,
                            obs_lookup,
                            start_ts,
                            end_ts,
                            subqry_groupby.replace("%", "%%"),
                            subqry_order_sql
                        )

            # Setup values for the converter
            try:
                obs_group = weewx.units.obs_group_dict[obs_lookup]
                obs_unit_from_target_unit = converter.group_unit_dict[obs_group]
            except:
                # This observation doesn't exist within weewx schema so nothing
                # to convert, so set None type
                obs_group = None
                obs_unit_from_target_unit = None

            for row in archive.genSql(sql_lookup):
                xAxis_labels.append(row[0])
                row_tuple = (row[1], obs_unit_from_target_unit, obs_group)
                if special_target_unit:
                    row_converted = weewx.units.convert(row_tuple, special_target_unit)
                else:
                    row_converted = self.converter.convert(row_tuple)
                obsvalues.append(row_converted[0])

            # Categories match values by position, so a full calendar cycle needs a gap where there's no data
            full_cycle = {"hour": 24, "day": 31}.get(xAxis_groupby, 12)
            if (not isinstance(time_length, int) and xAxis_groupby != "year"
                    and 0 < len(xAxis_labels) < len(xAxis_categories) == full_cycle):
                first_label = 0 if xAxis_groupby == "hour" else 1
                by_position = dict(zip([int(label) - first_label for label in xAxis_labels], obsvalues))
                obsvalues = [by_position.get(i) for i in range(len(xAxis_categories))]

            # If the values are to be mirrored, we need to make them negative
            if mirrored_value and to_bool(mirrored_value):
                obsvalues = [-i if i is not None else None for i in obsvalues]

            # Return a dict which has the value for if we need to add labels
            # from sql or not.
            if len(xAxis_categories) == 0:
                data = {
                    "use_sql_labels": True,
                    "xAxis_groupby_labels": xAxis_labels,
                    "obsdata": obsvalues,
                }
            else:
                data = {
                    "use_sql_labels": False,
                    "xAxis_groupby_labels": "",
                    "obsdata": obsvalues,
                }
            return data

        # A direction can't be averaged as a number. weewx has the vector mean on "wind", which needs windSpeed.
        if obs_lookup == "windDir" and aggregate_type in ("avg", "vecdir"):
            if "windSpeed" in archive.sqlkeys:
                obs_lookup, aggregate_type = "wind", "vecdir"
            else:
                aggregate_type = "avg"

        # Begin standard observation lookups
        try:
            (time_start_vt, time_stop_vt, obs_vt) = weewx.xtypes.get_series(
                obs_lookup,
                TimeSpan(start_ts, end_ts),
                archive,
                aggregate_type,
                aggregate_interval,
            )
        except Exception as e:
            raise Warning(
                "Error trying to use database binding %s to graph observation %s. Error was: %s."
                % (binding, obs_lookup, e)
            )

        self.insert_null_value_timestamps_to_end_ts(time_start_vt, time_stop_vt, obs_vt, start_ts, end_ts, aggregate_interval)
        
        if special_target_unit:
            logdbg("unit_group=%s source_unit=%s special_target_unit=%s" % (obs_vt[2],obs_vt[1],special_target_unit))
            obs_vt = weewx.units.Converter({obs_vt[2]:special_target_unit}).convert(obs_vt)
        else:
            obs_vt = self.converter.convert(obs_vt)

        # Special handling for the rain.
        if observation == "rainTotal":
            # The weewx "rain" observation is really "bucket tips". This
            # special counter increments the bucket tips over timespan to
            # return rain total.
            rain_count = 0
            obs_round_vt = []
            for rain in obs_vt[0]:
                # If the rain value is None or "", add it as 0.0
                if rain is None or rain == "":
                    # rain = 0.0
                    # Do not keep adding None or empty results, so that
                    # full-length charts (like weewx v4 archiveYearSpan) don't
                    # have a line that continues past the last actual plot
                    obs_round_vt.append(rain)
                    continue
                rain_count = rain_count + rain
                obs_round_vt.append(round(rain_count, 2))
        else:
            # Send all other observations through the usual process, except
            # Barometer for finer detail
            if observation == "barometer":
                usage_round = int(
                    self.skin_dict["Units"]["StringFormats"].get(obs_vt[1], "1f")[-2]
                )
                obs_round_vt = [
                    round(x, usage_round) if x is not None else None for x in obs_vt[0]
                ]
            else:
                try:
                   if obs_round is None:
                       usage_round = int(
                           self.skin_dict["Units"]["StringFormats"].get(obs_vt[1], "2f")[-2]
                       )
                   else:
                       usage_round = int(obs_round)+1
                except ValueError:
                   loginf (
                      "Observation %s is using unit %s that returns %s for StringFormat, rather than float point decimal format value - using 0 as rounding"
                      % (observation, obs_vt[1], self.skin_dict["Units"]["StringFormats"].get(obs_vt[1]))
                   )
                   usage_round = 0

                # -1 means weewx has no unit for this observation (e.g. an O3 sensor):
                # keep the raw values instead of rounding them to whole numbers.
                if str(obs_round) in ("-1", "-1.0"):
                    obs_round_vt = obs_vt[0]
                else:
                    obs_round_vt = [self.round_none(x, usage_round) for x in obs_vt[0]]

        # "Today" charts, "timespan_specific" charts and floating timespan
        # charts have the point timestamp on the stop time so we don't see the
        # previous minute in the tooltip. (e.g. 4:59 instead of 5:00)
        # Everything else has it on the start time so we don't see the next day
        # in the tooltip (e.g. Jan 2 instead of Jan 1)
        try:
            if not aggregate_type:
                point_timestamp = time_stop_vt
            elif aggregate_interval and (
                      aggregate_interval == 3600 or aggregate_interval==2629800):
                point_timestamp = time_start_vt
            else:
                point_timestamp = ([(x+y)/2.0 for x,y in zip(time_start_vt[0],time_stop_vt[0])],time_start_vt[1],time_start_vt[2])
        except Exception:
            point_timestamp = time_stop_vt

        # If the values are to be mirrored, we need to make them negative
        if mirrored_value:
            for i in range(len(obs_round_vt)):
                if obs_round_vt[i] is not None:
                    obs_round_vt[i] = -obs_round_vt[i]

        time_ms = [float(x) * 1000 for x in point_timestamp[0]]
        data = zip(time_ms, obs_round_vt)

        return data

    def insert_null_value_timestamps_to_end_ts(self, time_start_vt, time_stop_vt, obs_vt, start_ts, end_ts, interval):
        """
        In weewx 4.5.1 xtypes.py was modified to not return any data points which didn't exist in the archive database.
        This function adds the 'future' data points from the last timestamp in the list up until end_ts with None entries.
        This means that graphs still have the option of showing a full day or month or year on the x axis depending on the time_length specfied.       
        """
        count = 0

        if interval is not None:
            try:
                ts = time_start_vt[0][-1] + interval
            except:
                ts = start_ts

            while ts < end_ts:
                time_start_vt[0].append(ts)
                time_stop_vt[0].append(ts)
                ts = ts + interval
                count = count + 1

        for i in range(count):
           obs_vt[0].append(None)

    # US EPA Air Quality Index for PM2.5 (24-hour, µg/m³), with the breakpoints in force since May 6, 2024
    PM25_AQI_BREAKPOINTS = ((0.0, 9.0, 0, 50), (9.1, 35.4, 51, 100), (35.5, 55.4, 101, 150), (55.5, 125.4, 151, 200),
                            (125.5, 225.4, 201, 300), (225.5, 325.4, 301, 500))
    AQI_CATEGORIES = ((50, "aqi_good"), (100, "aqi_moderate"), (150, "aqi_usg"), (200, "aqi_unhealthy"),
                      (300, "aqi_very_unhealthy"), (float("inf"), "aqi_hazardous"))

    @classmethod
    def pm25_to_aqi(cls, pm25):
        """The US AQI for a PM2.5 concentration in µg/m³: EPA's linear interpolation, concentration cut to 0.1."""
        c = max(0.0, int(float(pm25) * 10) / 10.0)
        for c_lo, c_hi, i_lo, i_hi in cls.PM25_AQI_BREAKPOINTS:
            if c <= c_hi:
                return int(round((i_hi - i_lo) / (c_hi - c_lo) * (max(c, c_lo) - c_lo) + i_lo))
        return 500

    def get_station_aqi(self, archive, line_options, label_dict, stop_ts):
        """(AQI, category text) from the station's database, or (None, "no data" text).

        aqi_observation: a column that already holds the AQI (such as aqi), or a PM2.5 column (pm2_5), which is
        averaged over aqi_average seconds (default 3600, the last hour) and turned into the US AQI.
        Default: aqi if the database has it, else pm2_5.
        """
        columns = archive.sqlkeys
        obs = line_options.get("aqi_observation") or ("aqi" if "aqi" in columns else "pm2_5")
        if obs not in columns:
            logdbg("EChartsJsonGenerator: AQI chart: no %s column in the database" % obs)
            return None, label_dict["aqi_no_data"]
        is_pm = "pm2_5" in obs or "pm25" in obs
        span = to_int(line_options.get("aqi_average", 3600)) if is_pm else 0
        last = archive.getSql("SELECT dateTime FROM %s WHERE `%s` IS NOT NULL AND dateTime <= ? ORDER BY dateTime DESC LIMIT 1"
                              % (archive.table_name, obs), (stop_ts,))
        # A reading more than two hours old is no reading
        if not last or last[0] < stop_ts - 7200:
            return None, label_dict["aqi_no_data"]
        row = archive.getSql("SELECT AVG(`%s`) FROM %s WHERE dateTime > ? AND dateTime <= ?" % (obs, archive.table_name),
                             (last[0] - span, last[0])) if span else \
            archive.getSql("SELECT `%s` FROM %s WHERE dateTime = ?" % (obs, archive.table_name), (last[0],))
        if not row or row[0] is None:
            return None, label_dict["aqi_no_data"]
        value = self.pm25_to_aqi(row[0]) if is_pm else int(round(float(row[0])))
        category = next(key for limit, key in self.AQI_CATEGORIES if value <= limit)
        return value, label_dict[category]

    def round_none(self, value, places):
        """Round value to 'places' places but also permit a value of None"""
        if value is not None:
            try:
                value = round(value, places)
            except:
                value = None
        return value

    def timespan_year_to_now(self, time_ts, grace=1, years_ago=0):
        """
        In weewx 4 the get_series() for archiveYearSpan returns the full 365
        day chart.  if users do not want a full year (with empty data) and
        would rather a Jan 1 to "now", then they can use this custom timespan

        This is taken right from weewx, but adapted to end at the current
        timestamp, and not the following Jan 1.
        """
        if time_ts is None:
            return None
        time_ts -= grace
        _day_date = datetime.date.fromtimestamp(time_ts)
        return TimeSpan(
            int(time.mktime((_day_date.year - years_ago, 1, 1, 0, 0, 0, 0, 0, -1))),
            int(float(time_ts)),
        )

    def create_windrose_data(self, windDir_list, windSpeed_list):
        # List comprehension borrowed from weewx-wd extension
        # Create windrose_list container and initialise to all 0s
        windrose_list = [0.0 for x in range(16)]

        # Step through each windDir and add corresponding windSpeed to windrose_list
        x = 0
        while x < len(windDir_list):
            # Only want to add windSpeed if both windSpeed and windDir have a value
            if windSpeed_list[x] is not None and windDir_list[x] is not None:
                # Add the windSpeed value to the corresponding element of our
                # windrose list
                windrose_list[
                    int((windDir_list[x] + 11.25) / 22.5) % 16
                ] += windSpeed_list[x]
            x += 1

        # Step through our windrose list and round all elements to 1 decimal place
        y = 0
        while y < len(windrose_list):
            windrose_list[y] = round(windrose_list[y], 1)
            y += 1
        # Need to return a string of the list elements comma separated, no
        # spaces and bounded by [ and ]
        # windroseData = '[' + ','.join(str(z) for z in windrose_list) + ']'
        return windrose_list

    def get_cardinal_direction(self, degree):
        if 0 <= degree <= 11.25:
            return "N"
        if 11.26 <= degree <= 33.75:
            return "NNE"
        if 33.76 <= degree <= 56.25:
            return "NE"
        if 56.26 <= degree <= 78.75:
            return "ENE"
        if 78.76 <= degree <= 101.25:
            return "E"
        if 101.26 <= degree <= 123.75:
            return "ESE"
        if 123.76 <= degree <= 146.25:
            return "SE"
        if 146.26 <= degree <= 168.75:
            return "SSE"
        if 168.76 <= degree <= 191.25:
            return "S"
        if 191.26 <= degree <= 213.75:
            return "SSW"
        if 213.76 <= degree <= 236.25:
            return "SW"
        if 236.26 <= degree <= 258.75:
            return "WSW"
        if 258.76 <= degree <= 281.25:
            return "W"
        if 281.26 <= degree <= 303.75:
            return "WNW"
        if 303.76 <= degree <= 326.25:
            return "NW"
        if 326.26 <= degree <= 348.75:
            return "NNW"
        if 348.76 <= degree <= 360:
            return "N"

    def series_options_to_float(self, d):
        """
        Recurse through all the series options and set any strings that
        should be numbers to float.
        https://stackoverflow.com/a/54565277/1177153
        """

        try:
            for k, v in d.items():
                if isinstance(v, dict):
                    # Check nested dicts
                    self.series_options_to_float(v)
                else:
                    try:
                        v = to_float(v)
                        d.update({k: v})
                    except:
                        pass
            return d
        except:
            # This item isn't a dict, so return it back
            return d
