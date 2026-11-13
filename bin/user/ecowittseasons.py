"""
weewx-ecowittSeasonsLive: the WeeWX Seasons skin for Ecowitt gateways.

- Current conditions and sensor status are drawn in the browser from ecwLoop.json, the loop data file
  written by weewx-ecowittGateway (https://github.com/Millardiang/weewx-ecowittGateway), and kept up to
  date while the page is open. EcowittSeasonsSearchList gives the page what it needs for that: where
  ecwLoop.json is, how to convert each field to the report's units, and the labels and layout.
- The plots are interactive charts drawn by weewx-echarts (user.ecowittseasons_charts). prune_chart_dict()
  leaves out charts of observations with no data.

Copyright (C) 2026 Ian Millard (weewx-ecowittSeasonsLive)

This program is free software: you can redistribute it and/or modify it under the terms of the
GNU General Public License as published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version. See the LICENSE file.
"""

import json
import logging
import os

import weeutil.config
import weeutil.weeutil
import weewx
import weewx.units
import weewx.xtypes
from weeutil.weeutil import TimeSpan, to_bool, to_int
from weewx.cheetahgenerator import SearchList

VERSION = "1.0.0"

log = logging.getLogger(__name__)

# The unit systems ecwLoop.json can be in (its usUnits)
UNIT_SYSTEMS = {weewx.US: weewx.units.USUnits, weewx.METRIC: weewx.units.MetricUnits,
                weewx.METRICWX: weewx.units.MetricWXUnits}

# Lines on a chart that stand for something other than a database column, and what they need
SPECIAL_LINES = {
    "windRose": ("windSpeed", "windDir"),
    "haysChart": ("windSpeed",),
    "rainTotal": ("rain",),
}

DEFAULT_ORDINATES = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW",
                     "NNW", ""]

# Fields of ecwLoop.json that are not readings
NOT_READINGS = ("dateTime", "usUnits", "interval")

_warned = set()


def _warn_once(key, msg, *args):
    if key not in _warned:
        _warned.add(key)
        log.warning(msg, *args)


# ---------------------------------------------------------------------------------------------------------
#  Charts: leave out what has no data
# ---------------------------------------------------------------------------------------------------------

def obs_has_data(db_manager, obs, days, cache):
    """Whether obs (a column or an xtype) has any data in the last `days` days. Unknown types have none."""
    if obs in cache:
        return cache[obs]
    found = False
    try:
        stop = db_manager.lastGoodStamp()
        if stop:
            span = TimeSpan(stop - days * 86400, stop)
            count = weewx.xtypes.get_aggregate(obs, span, "count", db_manager)
            found = bool(count is not None and count[0])
    except (weewx.UnknownType, weewx.UnknownAggregation, weewx.CannotCalculate):
        found = False
    except Exception as e:  # a database error must not stop the report
        log.debug("has_data(%s): %s", obs, e)
        found = False
    cache[obs] = found
    return found


def line_has_data(line_name, line, db_manager, days, cache):
    obs = line.get("observation", line_name)
    if obs in SPECIAL_LINES:
        return all(obs_has_data(db_manager, o, days, cache) for o in SPECIAL_LINES[obs])
    if obs == "weatherRange":
        return obs_has_data(db_manager, line.get("range_observation", "outTemp"), days, cache)
    if obs == "aqiChart":
        names = [line["aqi_observation"]] if "aqi_observation" in line else ["aqi", "pm2_5"]
        return any(obs_has_data(db_manager, o, days, cache) for o in names)
    return obs_has_data(db_manager, obs, days, cache)


def prune_chart_dict(chart_dict, db_manager, skin_dict):
    """Remove the lines of charts.conf whose observation has had no data for [Extras] hide_empty_days (30) days,
    and then the charts left with no lines. Chart groups stay, even if empty, so links to them still work."""
    days = to_int(skin_dict.get("Extras", {}).get("hide_empty_days", 30))
    cache = {}
    for group in list(chart_dict.sections):
        for chart in list(chart_dict[group].sections):
            for line in list(chart_dict[group][chart].sections):
                options = weeutil.config.accumulateLeaves(chart_dict[group][chart][line])
                if not line_has_data(line, options, db_manager, days, cache):
                    del chart_dict[group][chart][line]
            if not chart_dict[group][chart].sections:
                del chart_dict[group][chart]
    return chart_dict


# ---------------------------------------------------------------------------------------------------------
#  Live data: where ecwLoop.json is, and how to show it
# ---------------------------------------------------------------------------------------------------------

def loop_json_location(config_dict):
    """(absolute path of ecwLoop.json, whether weewx-ecowittGateway writes it)"""
    ec = config_dict.get("EcowittGateway", {}) or {}
    loop = ec.get("loop_json", {}) or {}
    enabled = to_bool(loop.get("enable", False))
    root = config_dict.get("WEEWX_ROOT", "")
    html_root = os.path.abspath(os.path.join(root, config_dict.get("StdReport", {}).get("HTML_ROOT", "public_html")))
    path = os.path.expanduser(str(loop.get("path", "ecwLoop.json")))
    if not os.path.isabs(path):
        path = os.path.join(html_root, path)
    if path.endswith(os.sep) or os.path.isdir(path):
        path = os.path.join(path, "ecwLoop.json")
    return os.path.abspath(path), enabled


def linear_conversion(group, from_unit, to_unit):
    """[factor, offset] that converts from_unit to to_unit, or None if the two can't be converted linearly."""
    if from_unit == to_unit:
        return [1, 0]
    try:
        y = [weewx.units.convert((x, from_unit, group), to_unit)[0] for x in (0.0, 1.0, 100.0)]
    except (KeyError, TypeError, ValueError, weewx.ViolatedPrecondition):
        return None
    if None in y:
        return None
    factor, offset = y[1] - y[0], y[0]
    if abs(offset + factor * 100.0 - y[2]) > 1e-6 * max(1.0, abs(y[2])):
        return None  # not linear (eg Beaufort)
    return [factor, offset]


class EcowittSeasonsSearchList(SearchList):
    """$ecw_live_json: the settings of the live widgets; $ecw_archive_json: the latest archive record, shown until
    (or if never) ecwLoop.json can be read; $ecw_version."""

    def get_extension_list(self, timespan, db_lookup):
        gen = self.generator
        skin_dict = gen.skin_dict
        live = skin_dict.get("LiveConditions", {})
        labels = skin_dict.get("Labels", {}).get("Generic", {})

        # Where ecwLoop.json is, relative to this report's pages
        loop_path, loop_enabled = loop_json_location(gen.config_dict)
        report_root = os.path.abspath(os.path.join(gen.config_dict.get("WEEWX_ROOT", ""), skin_dict["HTML_ROOT"]))
        url = str(live.get("url", "")).strip()
        if not url:
            url = os.path.relpath(loop_path, report_root).replace(os.sep, "/")
        if not loop_enabled and not str(live.get("url", "")).strip():
            _warn_once("loop_json", "ecowittSeasons: [EcowittGateway] [[loop_json]] is not enabled; current conditions "
                       "will show the last archive record instead of live data")

        # Unit conversions: for each unit system ecwLoop.json may be in, each group to the report's unit
        converter, formatter = gen.converter, gen.formatter
        groups = sorted(set(weewx.units.obs_group_dict.values()))
        conversions = {}
        for system, std in UNIT_SYSTEMS.items():
            conv = {}
            for group in groups:
                src = std.get(group)
                dst = converter.group_unit_dict.get(group, src)
                if src is None or dst is None:
                    continue
                c = linear_conversion(group, src, dst)
                if c is None:
                    c, dst = [1, 0], src
                conv[group] = c + [dst]
            conversions[str(system)] = conv
        unit_labels = {}
        for unit, label in formatter.unit_label_dict.items():
            unit_labels[unit] = label[-1] if isinstance(label, (list, tuple)) else label
        unit_formats = dict(formatter.unit_format_dict)

        try:
            ordinates = [str(x) for x in weeutil.weeutil.option_as_list(skin_dict["Units"]["Ordinates"]["directions"])]
        except KeyError:
            ordinates = DEFAULT_ORDINATES

        # The layout of the current conditions: [LiveConditions] [[sections]]
        sections = []
        live_sections = live.get("sections", {})
        for name in getattr(live_sections, "sections", []):
            sec = live_sections[name]
            rows = weeutil.weeutil.option_as_list(sec.get("fields", []))
            sections.append({"name": name, "title": str(sec.get("title", name)), "rows": rows or []})

        sensor_names = dict(skin_dict.get("LiveSensors", {}).get("names", {}))
        battery_types = {k: str(v) for k, v in skin_dict.get("LiveSensors", {}).get("battery", {}).items()}

        live_config = {
            "url": url,
            "enabled": loop_enabled or bool(str(live.get("url", "")).strip()),
            "poll": max(2, to_int(live.get("poll_interval", 10))),
            "stale": max(10, to_int(live.get("stale_after", 120))),
            "show_unlisted": to_bool(live.get("show_unlisted", False)),
            "low_volts": float(skin_dict.get("LiveSensors", {}).get("low_volts", 1.2)),
            "sections": sections,
            "obs_groups": dict(weewx.units.obs_group_dict),
            "conversions": conversions,
            "unit_labels": unit_labels,
            "unit_formats": unit_formats,
            "labels": {k: v for k, v in labels.items() if isinstance(v, str)},
            "ordinates": ordinates,
            "sensor_names": sensor_names,
            "battery_types": battery_types,
            "time_zone": skin_dict.get("Units", {}).get("TimeZone", {}).get("time_zone", ""),
        }

        # The latest archive record, for the first draw and in case ecwLoop.json can't be read
        record = {}
        try:
            manager = db_lookup()
            stop = manager.lastGoodStamp()
            if stop:
                record = manager.getRecord(stop) or {}
        except Exception as e:
            log.debug("ecowittSeasons: no archive record: %s", e)
        record = {k: v for k, v in record.items() if v is not None and (k in NOT_READINGS or isinstance(v, (int, float)))}

        def dump(obj):
            return json.dumps(obj, ensure_ascii=False, default=str).replace("</", "<\\/")

        return [{
            "ecw_version": VERSION,
            "ecw_live_json": dump(live_config),
            "ecw_archive_json": dump(record),
            "ecw_loop_url": url,
            "ecw_live_enabled": live_config["enabled"],
        }]
