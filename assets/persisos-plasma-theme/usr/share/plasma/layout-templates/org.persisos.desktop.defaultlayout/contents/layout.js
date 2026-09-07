// PersisOS default desktop layout

var allDesktops = desktops()
for (var i = 0; i < allDesktops.length; i++) {
  var d = allDesktops[i]
  d.wallpaperPlugin = 'org.kde.image'
  d.currentConfigGroup = ['Wallpaper', 'org.kde.image', 'General']
  d.writeConfig('Image', 'file:///usr/share/wallpapers/PersisOS-1/contents/images/2560x1600.png')
  d.writeConfig('FillMode', 2)
}

var existingPanels = panels()
for (var p = 0; p < existingPanels.length; p++) {
  existingPanels[p].remove()
}

var panel = new Panel
panel.location = 'top'
panel.height = gridUnit * 2.2
panel.floating = false
panel.alignment = 'left'
panel.lengthMode = 'fill'

var appmenu = panel.addWidget('org.kde.plasma.kickoff')
appmenu.currentConfigGroup = ['General']
appmenu.writeConfig('icon', '/usr/share/icons/hicolor/scalable/apps/persisos-launcher.svg')
appmenu.currentConfigGroup = ['Shortcuts']
appmenu.writeConfig('global', 'Meta')

panel.addWidget('org.kde.plasma.icontasks')
panel.addWidget('org.kde.plasma.panelspacer')
panel.addWidget('org.kde.plasma.systemtray')
panel.addWidget('org.kde.plasma.digitalclock')
panel.addWidget('org.kde.plasma.showdesktop')

panel.currentConfigGroup = ['General']
panel.writeConfig('floating', false)
