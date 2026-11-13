## Shared <head> contents for the weewx-ecowittSeasonsLive skin
## Before including it a page may set:
##   $ecw_root    path to the top of the site: "." (default) or ".." for a page in a folder
##   $ecw_charts  True on pages with charts (loads Apache ECharts)
## Copyright (C) 2026 Ian Millard
## Distributed under terms of GPLv3.  See LICENSE for your rights.
#errorCatcher Echo
#encoding UTF-8
#set $ecw_root = $getVar('ecw_root', '.')
#set $ecw_charts = $getVar('ecw_charts', False)
#set $ecw_tag = $current.dateTime.raw
#set $ecw_theme = $Extras.get('theme', 'auto')
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <link rel="icon" type="image/png" href="$ecw_root/favicon.ico" />
    <script>
      var ecw_site_root = "$ecw_root";
      /* light or dark before the page draws: the visitor's choice, else [Extras] theme (auto follows the system) */
      (function() {
        var theme = "$ecw_theme";
        try { theme = localStorage.getItem("echarts_theme") || theme; } catch (e) {}
        if (theme !== "dark" && theme !== "light") {
          theme = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
        }
        document.documentElement.classList.add(theme);
      })();
    </script>
    <link rel="stylesheet" type="text/css" href="$ecw_root/ecowitt-seasons.css?$ecw_tag"/>
    #set $dayjs = "https://cdnjs.cloudflare.com/ajax/libs/dayjs/" + $dayjs_version
    <script src="$dayjs/dayjs.min.js"></script>
    #for $plugin in ["utc", "timezone", "localizedFormat", "advancedFormat", "localeData"]
    <script src="$dayjs/plugin/${plugin}.min.js"></script>
    #end for
    #if $dayjs_locale != "en"
    <script src="$dayjs/locale/${dayjs_locale}.min.js"></script>
    #end if
    #if $ecw_charts
    ## Apache ECharts draws the charts (Apache License 2.0, https://echarts.apache.org)
    <script src="https://cdn.jsdelivr.net/npm/echarts@6.1.0/dist/echarts.min.js"></script>
    #end if
    <script src="$ecw_root/js/echarts-config.js?$ecw_tag"></script>
    <script src="$ecw_root/js/echarts-common.js?$ecw_tag"></script>
    #if $ecw_charts
    <script src="$ecw_root/js/echarts-charts.js?$ecw_tag"></script>
    #end if
    <script src="$ecw_root/js/ecowitt-config.js?$ecw_tag"></script>
    <script src="$ecw_root/seasons.js?$ecw_tag"></script>
    <script src="$ecw_root/js/ecowitt-seasons.js?$ecw_tag"></script>
