## sensors module for weewx skins
## Copyright Tom Keffer, Matthew Wall
## See LICENSE.txt for your rights
#errorCatcher Echo
#encoding UTF-8

## weewx-ecowittSeasonsLive: the signal and battery of each sensor the gateway reports are drawn in
## the browser from ecwLoop.json (table ecw_sensors_live). The archive's sensor columns below are
## shown instead until then, or if ecwLoop.json has no sensor fields. With neither, the widget
## stays hidden.

## remember the current time - we will use it more than once.
#import time
#set $now = time.time()

## use this span to determine whether there are any data to consider.
#set $recent=$span($day_delta=30, boundary='midnight')

#def get_battery_status($x)
## no value: nothing, so the row is hidden (no N/A)
#if $x is None
#pass
#elif $x == 1
<span class="status_low">$gettext('LOW')</span>
#else
<span class="status_ok">$gettext('OK')</span>
#end if
#end def

## provide an indication of how much time has passed since the last sensor
## reading.
#def get_time_delta($last_ts, $now)
  #if $last_ts
    #set $delta = int($now - $last_ts)
    #if $delta < 60
 
#elif $delta < 3600
      #set $minutes = int($delta / 60)
$minutes $gettext('minutes ago')
    #elif $delta < 86400
      #set $hours = int($delta / 3600)
$hours $gettext('hours ago')
    #else
      #set $days = int($delta / 86400)
$days $gettext('days ago')
    #end if
  #else
$gettext('never')
  #end if
#end def


## Get the list of sensor observations from the configuration file, otherwise
## fallback to a very rudimentary set.
#set $sensor_connections = $to_list($DisplayOptions.get('sensor_connections', ['rxCheckPercent']))
#set $sensor_batteries = $to_list($DisplayOptions.get('sensor_batteries', ['outTempBatteryStatus', 'inTempBatteryStatus', 'rainBatteryStatus', 'windBatteryStatus', 'uvBatteryStatus', 'txBatteryStatus']))
#set $sensor_voltages = $to_list($DisplayOptions.get('sensor_voltages', ['consBatteryVoltage', 'heatingVoltage', 'supplyVoltage', 'referenceVoltage']))

## first see what sensor data are available

#set $have_conn = 0
#for $x in $sensor_connections
  #if $getattr($recent, $x).has_data
    #set $have_conn = 1
  #end if
#end for

#set $have_battery = 0
#for $x in $sensor_batteries
  #if $getattr($recent, $x).has_data
    #set $have_battery = 1
  #end if
#end for

#set $have_voltage = 0
#for $x in $sensor_voltages
  #if $getattr($recent, $x).has_data
    #set $have_voltage = 1
  #end if
#end for


## now display the available data only

#set $have_archive = 1 if ($have_conn or $have_battery or $have_voltage) else 0
<div id='sensors_widget' class="widget"#if not $have_archive then ' style="display:none"' else ''#>
  <div class="widget_title">
    <a href="telemetry.html">$gettext("Sensor Status")</a>
    <a class="widget_control" onclick="toggle_widget('sensors')">&diams;</a>
  </div>
  <div class="widget_contents">
  <table id="ecw_sensors_live" class="ecw_sensors" style="display:none"></table>
  <table id="ecw_sensors_archive" data-has-data="$have_archive">

#if $have_conn
    <tr><th>$gettext("Connectivity")</th><th></th></tr>
#for $x in $sensor_connections
  #if $getattr($recent, $x).has_data
    <tr>
      <td class="label">$obs.label[$x]</td>
      <td class="data">$getVar('current.' + $x)</td>
#set $lasttime = $getattr($recent, $x).lasttime.raw
      <td class="timestamp">$get_time_delta($lasttime, $now)</td>
    </tr>
  #end if
#end for
#end if

#if $have_battery
    <tr><th>$gettext("Battery Status")</th><th></th></tr>
#for $x in $sensor_batteries
  #if $getattr($recent, $x).has_data
    <tr>
      <td class="label">$obs.label[$x]</td>
      <td class="data">$get_battery_status($getVar('current.%s.raw' % $x))</td>
#set $lasttime = $getattr($recent, $x).lasttime.raw
      <td class="timestamp">$get_time_delta($lasttime, $now)</td>
    </tr>
  #end if
#end for
#end if

#if $have_voltage
    <tr><th>$gettext("Voltage")</th><th></th></tr>
#for $x in $sensor_voltages
  #if $getattr($recent, $x).has_data
    <tr>
      <td class="label">$obs.label[$x]</td>
      <td class="data">$getVar('current.' + $x)</td>
#set $lasttime = $getattr($recent, $x).lasttime.raw
      <td class="timestamp">$get_time_delta($lasttime, $now)</td>
    </tr>
  #end if
#end for
#end if

  </table>
  </div>

</div>

