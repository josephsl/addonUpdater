# Add-on Updater
# Copyright 2018 Joseph Lee, released under GPL.

# Note: proof of concept implementation of NVDA Core issue 3208
# URL: https://github.com/nvaccess/nvda/issues/3208

import globalPluginHandler
# Python 3 calls for using urllib.request instead, which is functionally equivalent to urllib2.
try:
	from urllib.request import urlopen
except ImportError:
	from urllib import urlopen
import time
import gui
import wx
# What if this is run from NVDA source?
try:
	import updateCheck
	canUpdate = True
except RuntimeError:
	canUpdate = False
from logHandler import log
import globalVars
import config
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
		addonUtils.updateState["lastChecked"] = currentTime
		if addonUtils.updateState["autoUpdate"]: startAutoUpdateCheck(addonUpdateCheckInterval)
		addonHandlerEx.autoAddonUpdateCheck()
	else: startAutoUpdateCheck(whenToCheck - currentTime)

# Start or restart auto update checker.
def startAutoUpdateCheck(interval):
	global updateChecker
	if updateChecker is not None:
		wx.CallAfter(updateChecker.Stop)
	updateChecker = wx.PyTimer(autoUpdateCheck)
	wx.CallAfter(updateChecker.Start, interval * 1000, True)

def endAutoUpdateCheck():
	global updateChecker
	addonUtils.updateState["lastChecked"] = time.time()
	if updateChecker is not None:
		wx.CallAfter(updateChecker.Stop)
		wx.CallAfter(autoUpdateCheck)

addonGuiEx.AddonUpdaterManualUpdateCheck.register(endAutoUpdateCheck)

class GlobalPlugin(globalPluginHandler.GlobalPlugin):

	def __init__(self):
		super(GlobalPlugin, self).__init__()
		if globalVars.appArgs.secure: return
		if config.isAppX: return
		addonUtils.loadState()
		self.toolsMenu = gui.mainFrame.sysTrayIcon.toolsMenu
		self.addonUpdater = self.toolsMenu.Append(wx.ID_ANY, _("Check for &add-on updates..."), _("Check for nVDA add-on updates"))
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, addonGuiEx.onAddonUpdateCheck, self.addonUpdater)
		gui.settingsDialogs.NVDASettingsDialog.categoryClasses.append(AddonUpdaterPanel)
		if addonUtils.updateState["autoUpdate"]:
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

class AddonUpdaterPanel(gui.SettingsPanel):
	# Translators: This is the label for the Add-on Updater settings panel.
	title = _("Add-on Updater")

	def makeSettings(self, settingsSizer):
		sHelper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		# Never, EVER allow touch support to be disabled completely if using normal configuration (only manual passthrough will be allowed).
		# Translators: This is the label for a checkbox in the
		# Enhanced Touch Gestures settings panel.
		self.autoUpdateCheckBox=sHelper.addItem(wx.CheckBox(self, label=_("Automatically check for add-on &updates")))
		self.autoUpdateCheckBox.SetValue(addonUtils.updateState["autoUpdate"])

		# Checkable list comes from NVDA Core issue 7491 (credit: Derek Riemer and Babbage B.V.).
		from . import nvdaControlsEx
		self.noAddonUpdates = sHelper.addLabeledControl(_("Do &not update add-ons:"), nvdaControlsEx.CustomCheckListBox, choices=[addon.manifest["summary"] for addon in addonHandler.getAvailableAddons()])
		self.noAddonUpdates.SetCheckedStrings(addonHandlerEx.shouldNotUpdate())
		self.noAddonUpdates.SetSelection(0)

	def onSave(self):
		noAddonUpdateSummaries = self.noAddonUpdates.GetCheckedStrings()
		addonUtils.updateState["noUpdates"] = [addon.name for addon in addonHandler.getAvailableAddons()
			if addon.manifest["summary"] in noAddonUpdateSummaries]
		addonUtils.updateState["autoUpdate"] = self.autoUpdateCheckBox.IsChecked()
		global updateChecker
		if updateChecker and updateChecker.IsRunning():
			updateChecker.Stop()
		updateChecker = None
		if addonUtils.updateState["autoUpdate"]:
			addonUtils.updateState["lastChecked"] = time.time()
			wx.CallAfter(autoUpdateCheck)
