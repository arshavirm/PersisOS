// PersisOS default desktop layout

var wallpaper =
    'file:///usr/share/wallpapers/PersisOS-1/contents/images/2560x1600.png'
var allDesktops = desktopsForActivity(currentActivity())
for (var i = 0; i < allDesktops.length; i++) {
  var desktop = allDesktops[i]
  desktop.wallpaperPlugin = 'org.kde.image'
  desktop.currentConfigGroup = ['Wallpaper', 'org.kde.image', 'General']
  desktop.writeConfig('Image', wallpaper)
  desktop.writeConfig('FillMode', 2)
}

var existingPanels = panels()
for (var p = existingPanels.length - 1; p >= 0; p--) {
  existingPanels[p].remove()
}

var panel = new Panel
panel.location = 'top'
panel.height = 2 * Math.floor(gridUnit * 2.5 / 2)

var appmenu = panel.addWidget('org.kde.plasma.kickoff')
appmenu.currentConfigGroup = ['General']
appmenu.writeConfig('icon', 'persisos-launcher')

var icontasks = panel.addWidget('org.kde.plasma.icontasks')
icontasks.currentConfigGroup = ['General']
icontasks.writeConfig('launchers', [])
panel.addWidget('org.kde.plasma.panelspacer')
panel.addWidget('org.kde.plasma.systemtray')
panel.addWidget('org.kde.plasma.digitalclock')
panel.addWidget('org.kde.plasma.showdesktop')
