// PersisOS default desktop layout

var plasma = getApiVersion(1)

var allDesktops = desktops()
for (var i = 0; i < allDesktops.length; i++) {
  var d = allDesktops[i]
  d.wallpaperPlugin = 'org.kde.slideshow'
  d.currentConfigGroup = ['Wallpaper', 'org.kde.slideshow', 'General']
  d.writeConfig(
      'SlidePaths', '/usr/share/wallpapers/PersisOS-Slideshow/contents/images/')
  d.writeConfig('SlideInterval', 600)
  d.writeConfig('SlideshowMode', 'Sequential')
  d.writeConfig('SlideshowBackend', 'Directory')
  d.writeConfig('FillMode', 2)
}

var existingPanels = panels()
for (var p = 0; p < existingPanels.length; p++) {
  existingPanels[p].remove()
}

var panel = new plasma.Panel()
panel.location = 'top'
panel.height = gridUnit * 2.2
panel.floating = false
panel.alignment = 'left'
panel.lengthMode = 'fill'

var appmenu = panel.addWidget('org.kde.plasma.kickoff')
appmenu.currentConfigGroup = ['Shortcuts']
appmenu.writeConfig('global', 'Meta')

panel.addWidget('org.kde.plasma.icontasks')

var spacer1 = panel.addWidget('org.kde.plasma.panelspacer')

panel.addWidget('org.kde.plasma.systemtray')
panel.addWidget('org.kde.plasma.digitalclock')

var showdesktop = panel.addWidget('org.kde.plasma.showdesktop')

panel.currentConfigGroup = ['General']
panel.writeConfig('floating', false)
