# Copyright notices

weewx-ecowittSeasonsLive
Copyright (C) 2026 Ian Millard

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General
Public License as published by the Free Software Foundation, either version 3 of the License, or (at your
option) any later version. The full text is in `LICENSE`. The Seasons files say "See LICENSE.txt": that is
the same GNU GPL v3, shipped here as `LICENSE`.

It is built from the following works. Their own notices are kept, unchanged, at the top of each file
taken from them.

## WeeWX Seasons skin (GPL-3.0)

Copyright (c) 2009-2021 Tom Keffer <tkeffer@gmail.com> and Matthew Wall.
From WeeWX 5.5.2, <https://github.com/weewx/weewx>, `src/weewx_data/skins/Seasons`.

Templates, includes, `seasons.js`, the layout of `ecowitt-seasons.css`, `skin.conf`, the NOAA templates and
the `lang/*.conf` translations. The translations also carry the notices of their translators, including:
Copyright (c) 2021 Johanna Karen Roedenbeck, and the Finnish translation by iiseppi
(<https://github.com/iiseppi>).

## weewx-echarts (GPL-3.0)

<https://github.com/Millardiang/weewx-ECharts>, version 1.0.0, in `bin/user/ecowittseasons_charts.py`,
`js/echarts-*.js`, `js/echarts-config.js.tmpl`, `chart-builder/`, `CHARTS.md`, and the chart texts added to
the Catalan, German, French and Italian `lang` files.

weewx-echarts began as the charting part of the Belchertown skin by Pat O'Brien and its contributors
(<https://github.com/poblabs/weewx-belchertown>), including Copyright (c) 2026 Manuel Hilgert
<hilman2@gmail.com>.

## weewx-ecowittGateway (GPL-3.0)

<https://github.com/Millardiang/weewx-ecowittGateway>
Copyright (C) 2024-25 Gary Roderick (ecowitt_http.py), Copyright (C) 2026 Ian Millard
(weewx-ecowittGateway 2.0.0 and later); its multi-gateway merge follows weewx-ecowitt-multi,
Copyright (C) 2026 mKainzbauer.

weewx-ecowittGateway is a separate extension and none of its code is included here. This skin reads the
`ecwLoop.json` file it writes and the `[EcowittGateway]` settings, uses its field names, and follows its
battery-state rules (`batt_state_desc()`) in `js/ecowitt-seasons.js`.

## Fonts and libraries

- Open Sans: SIL Open Font License 1.1 (`font/OpenSans-LICENSE.txt`, `font/license.txt`).
- Apache ECharts: Apache License 2.0, <https://echarts.apache.org>. Loaded by the browser from jsDelivr;
  not included.
- Day.js: MIT License, <https://day.js.org>. Loaded by the browser from cdnjs; not included.
