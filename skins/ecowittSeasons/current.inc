## current module for the weewx-ecowittSeasonsLive skin
## Copyright Tom Keffer, Matthew Wall (Seasons)
## The rows are drawn in the browser from ecwLoop.json (weewx-ecowittGateway), in the layout of
## [LiveConditions] in skin.conf, and kept up to date. Only fields with a value are shown.
## Until ecwLoop.json has been read (or if it can't be), the latest archive record is shown.
## Copyright (C) 2026 Ian Millard (live current conditions)
## See LICENSE for your rights
#errorCatcher Echo
#encoding UTF-8

<div id='current_widget' class="widget">
  <div class="widget_title">
    $gettext("Current Conditions")
    <a class="widget_control"
      onclick="toggle_widget('current')">&diams;</a>
  </div>

  <div class="widget_contents">
  <p id="ecw_live_status" class="ecw_status"></p>
  <table>
    <tbody id="ecw_current_table">
    </tbody>
  </table>

  ## Without JavaScript: the archive record, as Seasons shows it, values with data only
  <noscript>
  <table>
    <tbody>
#set $observations = $to_list($DisplayOptions.get('observations_current', ['outTemp', 'barometer']))
#for $x in $observations
  #if $getVar('current.%s.raw' % $x) is not None
    #if $x == 'windSpeed'
      <tr>
        <td class="label">$obs.label.wind</td>
        <td class="data">$current.windSpeed $current.windDir.ordinal_compass</td>
      </tr>
    #else
      <tr>
        <td class="label">$obs.label[$x]</td>
        <td class="data">$getVar('current.' + $x)</td>
      </tr>
    #end if
  #end if
#end for
    </tbody>
  </table>
  </noscript>
  </div>

</div>
