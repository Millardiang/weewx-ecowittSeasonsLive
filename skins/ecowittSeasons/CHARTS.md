# Setting up charts

Charts are set up in `charts.conf`, in the skin's folder (`skins/ECharts`). To start, copy `charts.conf.example` to `charts.conf` and edit the copy. Charts update at the next report; there's no need to restart WeeWX.

The easiest way to make a new chart is the **Chart Builder** page. Pick observations and options, check the preview, and copy the text it writes into `charts.conf`.

## Layout

```
# Options here apply to every chart
time_length = 90000

[day]                         # A chart group: one page of charts, with a button on the charts page
    title = "Today"
    show_button = true
    button_text = "Day"
    time_length = today       # Applies to every chart in the group

    [[temperature]]           # A chart; the name is yours, and charts are drawn in this order
        title = Temperature
        [[[outTemp]]]         # A line: any observation in your database
        [[[dewpoint]]]
            color = purple    # Applies to this line only
```

An option applies to everything below where it's set, unless something further down sets its own value. A chart group's name (`[day]`) appears in the page address: `?group=day`.

To show the same observation twice on one chart (for example the daily high and low), give the second line a name of its own and say which observation it is:

```
        [[[outTemp]]]
            aggregate_type = max
            name = High
        [[[outTemp_low]]]
            observation = outTemp
            aggregate_type = min
            name = Low
```

## Chart groups

| Option | What it does |
|---|---|
| `title` | Heading of the group's page |
| `show_button` | `true` to give the group a button on the charts page |
| `button_text` | Text on the button |
| `page_content` | Text or HTML shown under the heading |
| `generate` | Rebuild the group's data only `hourly`, `daily`, `weekly`, `monthly`, `yearly`, or every so many seconds, instead of at every report. Useful for slow, long-span groups. |

## Time span and data

| Option | What it does |
|---|---|
| `time_length` | How far back the chart goes: a number of seconds (`86400` is 24 hours), or `today`, `week`, `month`, `year`, `year_to_now` or `all`. Also `days_ago`, `weeks_ago`, `months_ago` and `years_ago` with `time_ago = n`; `hour_ago_to_now`, `day_ago_to_now`, `week_ago_to_now`, `month_ago_to_now` and `year_ago_to_now` with `time_ago = n`; `day_specific`, `month_specific` and `year_specific` with `day_specific`, `month_specific` and `year_specific` set to the date; and `timespan_specific` with `timespan_start` and `timespan_stop` as Unix times. |
| `start_at_midnight`, `start_at_whole_hour`, `start_at_beginning_of_month` | `true` to start the span at a whole day, hour or month |
| `aggregate_type` | Combine readings: `avg`, `max`, `min`, `sum`, `vecdir` (average wind direction), or any WeeWX aggregate |
| `aggregate_interval` | The length of each combined period, in seconds or as `hour`, `day`, `week`, `month` |
| `data_binding` | Another WeeWX database binding |
| `unit` | Show the line in another unit, such as `degree_F` or `km_per_hour` |
| `gap_size` | Seconds without a reading after which the line breaks. Set it to your archive interval. |
| `connect_gaps` | `true` to join the line across missing readings |
| `group_by` | Combine readings by `hour` (of the day), `day` (of the month), `month` (default) or `year`, with those as labels along the bottom instead of times. For example, average temperature for each month of the year. |
| `categories` | The labels along the bottom for `group_by`, such as `"Jan Feb Mar ..."` |
| `average_type` | With `group_by` and `aggregate_type = avg`: what to average. `max` gives the average daily high, `min` the average daily low, `sum` the average daily total. |

## Charts

| Option | What it does |
|---|---|
| `title`, `subtitle` | Text above the chart |
| `type` | `line`, `smooth`, `area`, `smooth_area`, `column`, `dots` or `gauge`. It can also be set on a single line. |
| `legend` | `false` to hide the legend |
| `download_button` | `true` for a button that saves the chart as a PNG |
| `colors` | Line colours, in order: `"#7cb5ec, #b2df8a, ..."` |
| `tooltip_date_format` | Date format in the tooltip, in [Day.js format](https://day.js.org/docs/en/display/format), such as `LLL` or `dddd LL` |
| `width`, `height` | CSS width and height, such as `100%` or `300px`. A chart with its own width gets a row to itself. |
| `css_class` | An extra CSS class on the chart |
| `credits`, `credits_url`, `credits_position` | A small credit line, its link, and its position as JSON: `'{"align": "left", "x": 10, "y": -5}'` |

## Lines

| Option | What it does |
|---|---|
| `name` | Name in the legend and tooltip |
| `color` | Colour, such as `red` or `"#f7a35c"` |
| `observation` | The observation to show, when the section's own name isn't it |
| `layer` | Lines with a higher layer are drawn on top |
| `line_width` | Thickness in pixels. `0` shows dots only. |
| `line_style` | `solid`, `dashed` or `dotted` (also `short_dash`, `long_dash`, `dash_dot`, ...) |
| `markers` | `true` to mark each reading with a dot |
| `marker_size` | Dot size in pixels (default 4) |
| `marker_shape` | `circle`, `square`, `diamond`, `triangle` or `triangle_down` |
| `fill_color`, `fill_opacity` | For `area` charts: the fill colour, and how solid it is (0 to 1) |
| `opacity` | How solid the whole line is (0 to 1) |
| `visible` | `false` to start hidden (click the legend to show it) |
| `in_legend` | `false` to leave the line out of the legend |
| `in_tooltip` | `false` to leave the line out of the tooltip |
| `value_labels` | `true` to write each value next to it |
| `stack` | `true` to stack the line on the others on its scale, or a name to stack it only with lines of that name |
| `step` | Draw steps instead of slopes: `start`, `middle` or `end` |
| `mirrored` | `true` to label the scale without minus signs (for values drawn below the axis) |
| `number_format` | A subsection with `decimals`, `decimal_point` and `thousands_separator` for the tooltip and scale |

## Scales

| Option | What it does |
|---|---|
| `right_axis` | `true` to put the line on a second scale, on the right |
| `axis_label` | The scale's title. The default is the line's name and unit. |
| `axis_unit` | The unit shown in the default title |
| `axis_min`, `axis_max` | Fixed ends of the scale |
| `axis_soft_min`, `axis_soft_max` | The scale reaches at least this far, further if the data does |
| `axis_step` | Distance between scale labels (ignored if it would crowd the scale) |
| `axis_minor_ticks` | `true` for faint lines between the labels |

## Special charts

A chart is special when its line is one of these names.

**Wind rose:** `[[[windRose]]]` shows how often the wind blew from each direction, in seven Beaufort speed bands. `speed_colors` sets the band colours, slowest first.

**Gauge:** `type = gauge` on a chart with one line shows the line's latest reading as a ring.
- `axis_min` and `axis_max` set the ends (default 0–100).
- With `colors_enabled = true`, the ring takes `color1` up to `color2_position`, then `color2` up to `color3_position`, and so on up to `color7`.
- `color1_label` … `color7_label` show a word under the value.

**Air quality:** `[[[aqiChart]]]` shows the US Air Quality Index (0–500) as a ring.
- It reads an `aqi` column from your database if there is one.
- Otherwise it converts `pm2_5` (averaged over the last `aqi_average` seconds, default 3600) using the EPA breakpoints in force since May 2024.
- `aqi_observation` names a different column.

**Hays chart:** `[[[haysChart]]]` shows wind speed and gusts around a clock face. Usually `time_length = today`.

**Weather range:** `[[[weatherRange]]]` with `range_observation = outTemp` shows each day's low to high as a column, coloured by the day's average temperature.
- `band = true` draws a shaded band instead.
- `polar = true` wraps the days around a circle; a year of them makes a "weather radial".
- `color` gives every day one colour.

## Coming from Belchertown

A Belchertown `graphs.conf` works as it is. Copy it into the skin folder as `charts.conf`, or leave it named `graphs.conf`. Its option names are read as these:

| Belchertown / Highcharts | weewx-echarts |
|---|---|
| `zIndex`, `lineWidth`, `lineColor`, `dashStyle` | `layer`, `line_width`, `line_color`, `line_style` |
| `[[[[marker]]]]` `enabled`, `radius`, `symbol` | `markers`, `marker_size` (twice the radius), `marker_shape` |
| `yAxis = 1` | `right_axis = true` |
| `yAxis_min`, `yAxis_max`, `yAxis_softMin`, `yAxis_softMax` | `axis_min`, `axis_max`, `axis_soft_min`, `axis_soft_max` |
| `yAxis_tickInterval`, `yAxis_minorTicks`, `yAxis_label`, `yAxis_label_unit` | `axis_step`, `axis_minor_ticks`, `axis_label`, `axis_unit` |
| `fillColor`, `fillOpacity`, `showInLegend`, `enableMouseTracking` | `fill_color`, `fill_opacity`, `in_legend`, `in_tooltip` |
| `stacking = normal`, `stack` | `stack = true`, or `stack = name` |
| `[[[[dataLabels]]]]` `enabled` | `value_labels` |
| `[[[[numberFormat]]]]` `decimals`, `decimalPoint`, `thousandsSep` | `[[[[number_format]]]]` `decimals`, `decimal_point`, `thousands_separator` |
| `connectNulls`, `gapsize`, `exporting` | `connect_gaps`, `gap_size`, `download_button` |
| `xAxis_categories`, `xAxis_groupby` | `categories`, `group_by` |
| `observation_type`, `mirrored_value` | `observation`, `mirrored` |
| `range_type`, `area_display` | `range_observation`, `band` |
| `beauford0` … `beauford6` | `speed_colors` |
| `type = spline`, `areaspline`, `scatter` | `type = smooth`, `smooth_area`, `dots` |
| `step = left`, `center`, `right` | `step = start`, `middle`, `end` |
| `[[[[states]]]]` | not needed |

These Belchertown settings in `weewx.conf` `[Extras]` also still work: `belchertown_debug`, `belchertown_locale`, `highcharts_decimal`, `highcharts_thousands` and `graph_page_default_graphgroup`. Links to the charts page with `?graph=week` keep working too.
