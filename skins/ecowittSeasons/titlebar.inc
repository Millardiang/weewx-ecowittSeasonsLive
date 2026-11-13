## titlebar for weewx skins
## Copyright Tom Keffer, Matthew Wall
## See LICENSE.txt for your rights
#errorCatcher Echo
#encoding UTF-8

#set $show_rss = $to_bool($DisplayOptions.get('show_rss', True))
#set $show_reports = $to_bool($DisplayOptions.get('show_reports', True))
#set $ecw_tb_root = $getVar('ecw_root', '.')

<div id="title_bar">
  <div id="title">
    <h1 class="page_title"><a href="$ecw_tb_root/index.html">$station.location</a></h1>
    <p class="lastupdate">$current.dateTime</p>
  </div>
  <div id="tools">
#if $show_rss
    <a id="rss_link" href="$ecw_tb_root/rss.xml">RSS</a>
#end if
#if str($Extras.get("unit_switch_enabled", "1")) == "1"
    <button type="button" id="unitSwitch" class="tool_button" title="$obs.label.unit_toggle_title" aria-label="$obs.label.unit_toggle_title"><span></span></button>
#end if
#if str($Extras.get("theme_toggle_enabled", "1")) == "1"
    <button type="button" id="themeSwitch" class="tool_button" title="$obs.label.theme_toggle_title" aria-label="$obs.label.theme_toggle_title">
      <svg class="wx-icon-moon" viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>
      <svg class="wx-icon-sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="5"/><path d="M12 1v3M12 20v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M1 12h3M20 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
    </button>
#end if
  </div>
#if $show_reports
  <div id="reports">
    $gettext("Monthly Reports"):
    <select name="reports" onchange="openTabularFile(value)">
      #for $monthYear in $SummaryByMonth
      <option value="$monthYear">$monthYear</option>
      #end for
      <option selected>- $gettext("select month") -</option>
    </select>
    <br/>
    $gettext("Yearly Reports"):
    <select name="reports" onchange="openTabularFile(value)">
      #for $yr in $SummaryByYear
      <option value="$yr">$yr</option>
      #end for
      <option selected>- $gettext("select year") -</option>
    </select>
    <br/>
  </div>
#end if
</div>
