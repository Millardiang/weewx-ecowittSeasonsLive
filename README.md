# weewx-ecowittSeasonsLive

**Version:** 1.0.0 · The WeeWX Seasons skin, made for Ecowitt gateways

The skin is called `ecowittSeasons` (report `[[ecowittSeasons]]`, folder `skins/ecowittSeasons`).

weewx-ecowittSeasonsLive keeps the layout of the Seasons skin that comes with WeeWX 5 and changes four things:

1. **Live current conditions.** The *Current Conditions* and *Sensor Status* widgets are drawn in the browser
   from `ecwLoop.json`, the loop data file written by
   [weewx-ecowittGateway](https://github.com/Millardiang/weewx-ecowittGateway), and refreshed every 10 seconds
   while the page is open. Every reading the gateway reports can be shown: piezo and tipping rain gauges side by
   side, WN31 / WN34 channels, soil moisture, leaf wetness, leak sensors, PM2.5 / PM10 / CO₂, lightning, laser
   distance, and each sensor's signal and battery.
2. **Interactive charts.** The PNG plots are replaced by charts from
   [weewx-ECharts](https://github.com/Millardiang/weewx-ECharts) (Apache ECharts): tooltips, zoom, wind rose, air
   quality gauge, and a chart builder page. The Day / Week / Month / Year buttons work as in Seasons.
3. **No N/A.** Only values that are present are shown. A current-conditions row appears only while its field has a
   value, sensors without data are left out, charts and chart lines with no data are left out, and "N/A" is
   never printed (statistics rows with no values are hidden, a calm wind has no direction).
4. **Green.** The colours are the teal greens of the [WeeWX documentation](https://weewx.com/docs/5.5/usersguide/monitoring/):
   the teal header bar, teal headings, and the `#aacccc` / `#ddefef` panels. There is a dark version too.

## Requirements

- WeeWX 5.0 or later
- [weewx-ecowittGateway](https://github.com/Millardiang/weewx-ecowittGateway) 2.0 or later, with `ecwLoop.json`
  turned on (the installer does this for you). Without it the skin still works, showing the last archive record.
- Visitors' browsers load Apache ECharts and Day.js from jsDelivr and cdnjs.

## Install

```
weectl extension install weewx-ecowittSeasonsLive-1.0.0.zip
sudo systemctl restart weewx
```

The installer:

- adds an `[[ecowittSeasons]]` report to `[StdReport]`, written to the `ecowittSeasons` folder of your web pages
  (eg `/var/www/html/weewx/ecowittSeasons/` or `~/weewx-data/public_html/ecowittSeasons/`);
- turns on `ecwLoop.json` in weewx-ecowittGateway if it isn't set yet:

  ```
  [EcowittGateway]
      [[loop_json]]
          enable = True
  ```

  If you turned it off on purpose it stays off, and the installer says so. It also tells you if the
  `EcowittGatewayExport` service (which writes the file) is missing from `restful_services`.

The pages appear after the next report, or run `weectl report run ecowittSeasons`.

**Make it your main page:** set `HTML_ROOT` of `[[ecowittSeasons]]` to the folder of `[StdReport]` (eg
`HTML_ROOT = /var/www/html/weewx`) and set `enable = false` for `[[SeasonsReport]]`.

To remove it: `weectl extension uninstall ecowittSeasons`.

## How the live data reaches the page

weewx-ecowittGateway writes each loop packet to `ecwLoop.json` (by default in the top of your web pages folder).
The skin works out where that is from `[EcowittGateway] [[loop_json]] path` and the report's `HTML_ROOT`, so the
page fetches it with a relative URL (`../ecwLoop.json` for the default install). The file is in the unit system
`[[loop_json]] units` says; the page converts each field to the report's units.

The status line under *Current Conditions* says what is shown: **Live** with the age of the data, **No live data
since …** when `ecwLoop.json` stops changing, or **Last archive record** when it can't be read (and before the
first read).

If your web server publishes the pages somewhere else (FTP, rsync), copy `ecwLoop.json` along with them, or set
`url` under `[LiveConditions]` to where the browser can fetch it.

## Settings

Put these in `weewx.conf` under `[StdReport] [[ecowittSeasons]]`, where they survive upgrades. The defaults are
in `skins/ecowittSeasons/skin.conf`.

```
[StdReport]
    [[ecowittSeasons]]
        skin = ecowittSeasons
        HTML_ROOT = ecowittSeasons
        [[[Extras]]]
            theme = auto                # light, dark or auto
        [[[LiveConditions]]]
            poll_interval = 10          # seconds between reads of ecwLoop.json
            stale_after = 120           # older data is marked as not live
            show_unlisted = False       # True: an "Other" section with every reading not listed
        [[[Labels]]]
            [[[[Generic]]]]
                extraTemp1 = Greenhouse # names for your channels
```

| Section | Option | Default | What it does |
|---|---|---|---|
| `[LiveConditions]` | `url` | *(found)* | Where `ecwLoop.json` is, relative to the pages |
| | `poll_interval` | `10` | Seconds between reads |
| | `stale_after` | `120` | Seconds before data is no longer called live |
| | `show_unlisted` | `False` | Show readings not in any section |
| | `[[sections]]` | | The sections and rows of *Current Conditions* (see below) |
| `[LiveSensors]` | `low_volts` | `1.2` | Battery voltage at or below which a battery is low |
| | `[[battery]]` | | How each sensor model reports its battery: `binary`, `level` or `volts` |
| | `[[names]]` | | Sensor names, by model (`wh26`) or model and channel (`wn31_ch1`) |
| `[Extras]` | `theme` | `auto` | `light`, `dark`, or follow the visitor's system |
| | `theme_toggle_enabled` | `1` | The light/dark button |
| | `unit_switch_enabled` | `1` | The metric/US button (charts and current conditions) |
| | `hide_empty_charts` | `1` | Leave out chart lines with no data… |
| | `hide_empty_days` | `30` | …in this many days |
| | `chart_builder_enabled` | `1` | The chart builder page |
| `[DisplayOptions]` | `observations_stats` | | Rows of the statistics (rows with no data are hidden) |

### Current conditions layout

Each section of `[LiveConditions] [[sections]]` has a `title` (a label) and a list of `fields`. A field is a name
from `ecwLoop.json`; two joined with `+` share a row, eg `extraTemp1+extraHumid1` shows *12.3 °C · 61 %*. A row
is shown only while one of its fields has a value, and a section only while it has a row:

```
[LiveConditions]
    [[sections]]
        [[[greenhouse]]]
            title = Greenhouse
            fields = extraTemp3+extraHumid3, soilMoist2
```

Rain fields of the tipping (`t_`) and piezo (`p_`) gauges are marked *(tipping)* / *(piezo)* when both report.
The field names are those of the weewx-ecowittGateway field map (`weectl device --default-map`).

## Charts

The charts are set in `skins/ecowittSeasons/charts.conf`: copy `charts.conf.example` to `charts.conf` and edit
it. The `[day]`, `[week]`, `[month]` and `[year]` groups are the history buttons of the front page, and the
`[telemetry_day]` … `[telemetry_year]` groups those of the telemetry page. `CHARTS.md` in the same folder lists
every option. The chart builder page (`chart-builder/`, linked from the history widget) writes `charts.conf`
sections for you.

The example lists every sensor an Ecowitt gateway may have; lines with no data in the last 30 days are left out,
and then charts with no lines, so you only see what you have. To chart a gateway field (eg `p_rain`), it has to
be a column of your database.

The chart code is weewx-echarts 1.0.0, included as `user.ecowittseasons_charts` so this skin can be installed
next to the ECharts skin.

## Languages

The Seasons translations are included. Catalan, German, French and Italian also have the chart texts of
weewx-echarts. New labels of this skin are in English in `skin.conf`; add translations under `[Labels]
[[Generic]]` in the `lang/*.conf` files.

## Credits and licence

- The Seasons skin by Tom Keffer and Matthew Wall (GPL-3.0)
- weewx-echarts, from the Belchertown skin by Pat O'Brien and contributors (GPL-3.0)
- weewx-ecowittGateway, from Gary Roderick's Ecowitt local HTTP API driver (GPL-3.0)
- [Apache ECharts](https://echarts.apache.org) (Apache License 2.0), [Day.js](https://day.js.org) (MIT),
  Open Sans (SIL Open Font License)

weewx-ecowittSeasonsLive is Copyright (C) 2026 Ian Millard, under the GNU General Public License v3.0 (see `LICENSE`). `NOTICE.md` lists every copyright notice of the works it is built from.
