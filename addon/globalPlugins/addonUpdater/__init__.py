# Add-on Updater
# Copyright 2018 Joseph Lee, released under GPL.

# Note: proof of concept implementation of NVDA Core issue 3208
# URL: https://github.com/nvaccess/nvda/issues/3208

import globalPluginHandler
import json
import os
import threading
# Python 3 calls for using urllib.request instead, which is functionally equivalent to urllib2.
try:
	from urllib.request import urlopen
except ImportError:
	from urllib import urlopen
import tempfile
import ssl
import time
import config
import gui
import wx
import queueHandler
# What if this is run from NVDA source?
try:
	import updateCheck
	canUpdate = True
except RuntimeError:
	canUpdate = False
from logHandler import log
import globalVars
from . import addonHandlerEx
from . import addonGuiEx
from . import addonUtils
import addonHandler
addonHandler.initTranslation()

# Overall update check routine comes from StationPlaylist Studio add-on (Joseph Lee).)

addonUpdateCheckInterval = 86400
updateChecker = None

# To avoid freezes, a background thread will run after the global plugin constructor calls wx.CallAfter.
def autoUpdateCheck():
	currentTime = time.time()
	whenToCheck = addonUtils.updateState["lastChecked"] + addonUpdateCheckInterval
	if currentTime >= whenToCheck:
		addonHandlerEx.autoAddonUpdateCheck()
	else: startAutoUpdateCheck

# Start or restart auto update checker.
def startAutoUpdateCheck():
	global updateChecker
	if updateChecker is not None:
		wx.CallAfter(updateChecker.Stop)
	updateChecker = wx.PyTimer(autoUpdateCheck)
	wx.CallAfter(updateChecker.Start, addonUpdateCheckInterval * 1000, True)

class GlobalPlugin(globalPluginHandler.GlobalPlugin):

	def __init__(self):
		super(GlobalPlugin, self).__init__()
		# #20: don't even think about proceeding in secure screens (especially add-on updates).
		if globalVars.appArgs.secure: return
		# #40: skip over the rest if appx is in effect.
		if config.isAppX: return
		addonUtils.loadState()
		self.toolsMenu = gui.mainFrame.sysTrayIcon.toolsMenu
		self.addonUpdater = self.toolsMenu.Append(wx.ID_ANY, _("Check for &add-on updates..."), _("Check for nVDA add-on updates"))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, addonGuiEx.onAddonUpdateCheck, self.addonUpdater)
		if addonUtils.updateState["auto"]:
			# But not when NVDA itself is updating.
			if not (globalVars.appArgs.install and globalVars.appArgs.minimal):
				wx.CallAfter(autoUpdateCheck)

	def terminate(self):
		super(GlobalPlugin, self).terminate()
		try:
			if wx.version().startswith("4"):
				self.toolsMenu.Remove(self.addonUpdater)
			else:
				self.toolsMenu.RemoveItem(self.addonUpdater)
		except: #(RuntimeError, AttributeError, wx.PyDeadObjectError):
			pass
		global updateChecker
		if updateChecker and updateChecker.IsRunning():
			updateChecker.Stop()
		updateChecker = None
		addonUtils.saveState()
