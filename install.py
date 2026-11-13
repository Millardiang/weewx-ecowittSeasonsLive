# Installer for the weewx-ecowittSeasonsLive skin. Install with:
#     weectl extension install weewx-ecowittSeasonsLive-1.0.0.zip
#
# Copyright (C) 2026 Ian Millard
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version. See the LICENSE file.

from weecfg.extension import ExtensionInstaller

VERSION = "1.0.0"
EXPORT_SERVICE = "user.weewx-ecowittGateway.EcowittGatewayExport"


def loader():
    return EcowittSeasonsInstaller()


class EcowittSeasonsInstaller(ExtensionInstaller):
    def __init__(self):
        skin = "skins/ecowittSeasons/"
        super(EcowittSeasonsInstaller, self).__init__(
            version=VERSION,
            name="ecowittSeasons",
            description="The Seasons skin for Ecowitt gateways: live current conditions from ecwLoop.json "
                        "and interactive ECharts charts",
            author="weewx-ecowittSeasonsLive contributors",
            author_email="",
            config={
                "StdReport": {
                    "ecowittSeasons": {
                        "skin": "ecowittSeasons",
                        "HTML_ROOT": "ecowittSeasons",
                        "enable": "true",
                    }
                }
            },
            files=[
                ("bin/user", ["bin/user/ecowittseasons.py", "bin/user/ecowittseasons_charts.py"]),
                ("skins/ecowittSeasons", [skin + f for f in [
                    "skin.conf", "charts.conf.example", "CHARTS.md",
                    "index.html.tmpl", "statistics.html.tmpl", "telemetry.html.tmpl", "tabular.html.tmpl",
                    "celestial.html.tmpl", "rss.xml.tmpl",
                    "head.inc", "titlebar.inc", "current.inc", "sensors.inc", "hilo.inc", "sunmoon.inc",
                    "about.inc", "radar.inc", "satellite.inc", "map.inc", "analytics.inc", "identifier.inc",
                    "statistics.inc", "celestial.inc",
                    "ecowitt-seasons.css", "seasons.js", "favicon.ico",
                ]]),
                ("skins/ecowittSeasons/js", [skin + "js/" + f for f in [
                    "ecowitt-seasons.js", "ecowitt-config.js.tmpl", "echarts-config.js.tmpl",
                    "echarts-common.js", "echarts-charts.js", "echarts-chart-builder.js",
                ]]),
                ("skins/ecowittSeasons/chart-builder", [skin + "chart-builder/index.html.tmpl"]),
                ("skins/ecowittSeasons/font", [skin + "font/" + f for f in [
                    "OpenSans.woff", "OpenSans.woff2", "OpenSans-LICENSE.txt", "license.txt",
                ]]),
                ("skins/ecowittSeasons/NOAA", [skin + "NOAA/NOAA-%Y-%m.txt.tmpl", skin + "NOAA/NOAA-%Y.txt.tmpl"]),
                ("skins/ecowittSeasons/lang", [skin + "lang/" + f for f in [
                    "ca.conf", "cz.conf", "de.conf", "en.conf", "en_AU.conf", "en_CA.conf", "en_GB.conf",
                    "en_NZ.conf", "es.conf", "fi.conf", "fr.conf", "gr.conf", "it.conf", "nl.conf", "no.conf",
                    "th.conf", "zh.conf", "zh_CN.conf",
                ]]),
            ],
        )

    def configure(self, engine):
        """Turn on ecwLoop.json in weewx-ecowittGateway, unless it was turned off on purpose."""
        config = engine.config_dict

        def say(msg):
            engine.printer.out(msg, level=0)

        changed = False
        gateway = config.get("EcowittGateway")
        if gateway is None:
            say("ecowittSeasons: weewx-ecowittGateway is not configured. Current conditions will "
                               "show the last archive record until it is installed with ecwLoop.json enabled.")
            return False
        loop = gateway.get("loop_json")
        if loop is None:
            gateway["loop_json"] = {"enable": "True"}
            changed = True
            say("ecowittSeasons: turned on ecwLoop.json ([EcowittGateway] [[loop_json]] enable = True)")
        elif str(loop.get("enable", "False")).lower() not in ("true", "1", "yes", "on"):
            say("ecowittSeasons: [EcowittGateway] [[loop_json]] is turned off, so current conditions "
                               "will not be live. Set enable = True there to turn it on.")
        services = config.get("Engine", {}).get("Services", {}).get("restful_services", [])
        if isinstance(services, str):
            services = [s.strip() for s in services.split(",")]
        if EXPORT_SERVICE not in services:
            say("ecowittSeasons: %s is not in [Engine] [[Services]] restful_services; it is the "
                               "service that writes ecwLoop.json." % EXPORT_SERVICE)
        return changed
