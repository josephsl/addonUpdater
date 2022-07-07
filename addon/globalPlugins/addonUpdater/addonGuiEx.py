# gui/addonGui.py
# A part of NonVisual Desktop Access (NVDA)
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.
# Copyright (C) 2012-2022 NV Access Limited, Beqa Gozalishvili, Joseph Lee, Babbage B.V., Ethan Holliger

# Proof of concept user interface for add-on update dialog (NVDA Core issue 3208)

from urllib.request import urlopen
import os
import threading
import tempfile
import hashlib
import wx
import gui
from gui import guiHelper
from logHandler import log
import addonHandler
try:
	import updateCheck
except RuntimeError:
	raise RuntimeError("Update check module cannot be imported")
import core
import extensionPoints
from gui.nvdaControls import AutoWidthColumnCheckListCtrl
from .skipTranslation import translate
# Temporary
addonHandler.initTranslation()

AddonUpdaterManualUpdateCheck = extensionPoints.Action()

_progressDialog = None


# The following event handler comes from a combination of StationPlaylist and Windows App Essentials.
def onAddonUpdateCheck(evt):
	from . import addonHandlerEx
	addonHandlerEx.updateSuccess.notify()
	# If toast was shown, this will launch the results dialog directly as there is already update info.
	# Update info is valid only once, and this check will nullify it.
	from . import addonHandlerEx
	if addonHandlerEx._updateInfo is not None:
		wx.CallAfter(AddonUpdatesDialog, gui.mainFrame, dict(addonHandlerEx._updateInfo), auto=False)
		addonHandlerEx._updateInfo = None
		return
	AddonUpdaterManualUpdateCheck.notify()
	global _progressDialog
	_progressDialog = gui.IndeterminateProgressDialog(
		gui.mainFrame,
		# Translators: The title of the dialog presented while checking for add-on updates.
		_("Add-on update check"),
		# Translators: The message displayed while checking for add-on updates.
		_("Checking for add-on updates...")
	)
	t = threading.Thread(target=addonUpdateCheck)
	t.daemon = True
	t.start()


def addonUpdateCheck():
	from . import addonUpdateProc
	global _progressDialog
	try:
		info = addonUpdateProc.checkForAddonUpdates()
	except:
		info = None
		wx.CallAfter(_progressDialog.done)
		_progressDialog = None
		wx.CallAfter(gui.messageBox, _("Error checking for add-on updates."), translate("Error"), wx.ICON_ERROR)
		raise
	wx.CallAfter(_progressDialog.done)
	_progressDialog = None
	# Transform add-on update records to update dictionary entries for compatibility.
	meteorInfo = {}
	for addon in info:
		meteorInfo[addon.name] = addon.updateDict()
		meteorInfo[addon.name]["curVersion"] = addon.installedVersion
		meteorInfo[addon.name]["path"] = addon.url
		meteorInfo[addon.name]["urls"] = addon.url
	wx.CallAfter(AddonUpdatesDialog, gui.mainFrame, meteorInfo, auto=False)


class AddonUpdatesDialog(wx.Dialog):

	def __init__(self, parent, addonUpdateInfo, auto=True):
		# Translators: The title of the add-on updates dialog.
		super(AddonUpdatesDialog, self).__init__(parent, title=_("NVDA Add-on Updates"))
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		addonsSizerHelper = guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)
		self.addonUpdateInfo = addonUpdateInfo
		self.auto = auto

		if addonUpdateInfo:
			addonUpdateCount = len(addonUpdateInfo)
			# Translators: Message displayed when add-on updates are available.
			updateText = _("Add-on updates available: {updateCount}").format(updateCount=addonUpdateCount)
			addonsSizerHelper.addItem(wx.StaticText(self, label=updateText))
			entriesSizer = wx.BoxSizer(wx.VERTICAL)
			self.addonsList = AutoWidthColumnCheckListCtrl(
				self, -1, style=wx.LC_REPORT | wx.LC_SINGLE_SEL, size=(550, 350)
			)
			self.addonsList.Bind(wx.EVT_CHECKLISTBOX, self.onAddonsChecked)
			self.addonsList.InsertColumn(0, translate("Package"), width=150)
			# Translators: The label for a column in add-ons updates list
			# used to identify current add-on version (example: version is 0.3).
			self.addonsList.InsertColumn(1, _("Current version"), width=50)
			# Translators: The label for a column in add-ons updates list
			# used to identify new add-on version (example: version is 0.4).
			self.addonsList.InsertColumn(2, _("New version"), width=50)
			entriesSizer.Add(self.addonsList, proportion=8)
			for entry in sorted(addonUpdateInfo.keys()):
				addon = addonUpdateInfo[entry]
				self.addonsList.Append((addon['summary'], addon['curVersion'], addon['version']))
				self.addonsList.CheckItem(self.addonsList.GetItemCount() - 1)
			self.addonsList.Select(0)
			self.addonsList.SetItemState(0, wx.LIST_STATE_FOCUSED, wx.LIST_STATE_FOCUSED)
			addonsSizerHelper.addItem(entriesSizer)
		else:
			# Translators: Message displayed when no add-on updates are available.
			addonsSizerHelper.addItem(wx.StaticText(self, label=_("No add-on update available.")))

		bHelper = addonsSizerHelper.addDialogDismissButtons(guiHelper.ButtonHelper(wx.HORIZONTAL))
		if addonUpdateInfo:
			# Translators: The label of a button to update add-ons.
			label = _("&Update add-ons")
			self.updateButton = bHelper.addButton(self, label=label)
			self.updateButton.Bind(wx.EVT_BUTTON, self.onUpdate)

		closeButton = bHelper.addButton(self, wx.ID_CLOSE, label=translate("&Close"))
		closeButton.Bind(wx.EVT_BUTTON, self.onClose)
		self.Bind(wx.EVT_CLOSE, lambda evt: self.onClose)
		self.EscapeId = wx.ID_CLOSE

		mainSizer.Add(addonsSizerHelper.sizer, border=guiHelper.BORDER_FOR_DIALOGS, flag=wx.ALL)
		self.Sizer = mainSizer
		mainSizer.Fit(self)
		self.CenterOnScreen()
		wx.CallAfter(self.Show)

	def onAddonsChecked(self, evt):
		if any([self.addonsList.IsChecked(addon) for addon in range(self.addonsList.GetItemCount())]):
			self.updateButton.Enable()
		else:
			self.updateButton.Disable()

	def onUpdate(self, evt):
		self.Destroy()
		# #3208: do not display add-ons manager while updates are in progress.
		# Also, Skip the below step if this is an automatic update check.
		if not self.auto:
			self.Parent.Hide()
		availableAddons = sorted(self.addonUpdateInfo.keys())
		try:
			for addon in range(self.addonsList.GetItemCount()):
				if not self.addonsList.IsChecked(addon):
					del self.addonUpdateInfo[availableAddons[addon]]
			updateAddons(list(self.addonUpdateInfo.values()), auto=self.auto)
		except NameError:
			for addon in range(self.addonsList.GetItemCount()):
				if not self.addonsList.IsChecked(addon):
					del self.addonUpdateInfo[availableAddons[addon]]
			updateAddons(list(self.addonUpdateInfo.values()), auto=self.auto)

	def onClose(self, evt):
		self.Destroy()


_downloadProgressDialog = None

def downloadAndInstallAddonUpdates(addons):
	from . import addonUpdateProc
	global _downloadProgressDialog
	downloadedAddons = []
	currentPos = 0
	totalCount = len(addons)
	for addon in addons:
		destPath = tempfile.mktemp(prefix="nvda_addonUpdate-", suffix=".nvda-addon")
		downloadPercent = int((currentPos/totalCount) * 100)
		wx.CallAfter(_downloadProgressDialog.Update, downloadPercent, _("Downloading {addonName}").format(addonName=addon.summary))
		wx.CallAfter(_downloadProgressDialog.Fit)
		try:
			addonUpdateProc.downloadAddonUpdate(addon.url, destPath, addon.hash)
		except RuntimeError:
			gui.messageBox(
				# Translators: A message indicating that an error occurred while downloading an update to NVDA.
				_("Error downloading update for {name}.").format(name=addon.summary),
				translate("Error"),
				wx.OK | wx.ICON_ERROR)
		else:
			downloadedAddons.append((destPath, addon.summary))
		currentPos += 1
	_downloadProgressDialog.Update(100, "Downloading add-on updates")
	_downloadProgressDialog.Hide()
	_downloadProgressDialog.Destroy()
	_downloadProgressDialog = None
	gui.mainFrame.postPopup()
	if len(downloadedAddons):
		wx.CallAfter(installAddons, downloadedAddons)


def installAddons(addons):
	from . import addonUpdateProc
	progressDialog = gui.IndeterminateProgressDialog(
		gui.mainFrame,
		# Translators: The title of the dialog presented while an Addon is being updated.
		_("Updating add-ons"),
		# Translators: The message displayed while an addon is being updated.
		_("Please wait while add-ons are being updated.")
	)
	successfullyInstalledCount = 0
	for addon in addons:
		# Handle errors first.
		installStatus = addonUpdateProc.installAddonUpdate(addon[0], addon[1])
		if installStatus == addonUpdateProc.AddonInstallStatus.AddonReadBundleFailed:
			log.error(f"Error opening addon bundle from {addon[0]}", exc_info=True)
			gui.messageBox(
				# Translators: The message displayed when an error occurs
				# when trying to update an add-on package due to package problems.
				_("Cannot update {name} - missing file or invalid file format").format(name=addon[1]),
				translate("Error"),
				wx.OK | wx.ICON_ERROR
			)
		elif installStatus in (addonUpdateProc.AddonInstallStatus.AddonMinVersionNotMet, addonUpdateProc.AddonInstallStatus.AddonNotTested):
			# NVDA itself will check add-on compatibility range.
			# As such, the below fragment was borrowed from NVDA Core (credit: NV Access).
			from addonHandler import addonVersionCheck
			from gui import addonGui
			# Assuming that tempfile is readable, open the bundle again
			# so NVDA can actually show compatibility dialog.
			bundle = addonHandler.AddonBundle(addon[0])
			if installStatus == addonUpdateProc.AddonInstallStatus.AddonMinVersionNotMet:
				addonGui._showAddonRequiresNVDAUpdateDialog(gui.mainFrame, bundle)
			elif installStatus == addonUpdateProc.AddonInstallStatus.AddonNotTested:
				addonGui._showAddonTooOldDialog(gui.mainFrame, bundle)
		elif installStatus == addonUpdateProc.AddonInstallStatus.AddonInstallGenericError:
			gui.messageBox(
				# Translators: The message displayed when an error occurs when installing an add-on package.
				_("Failed to update {name} add-on").format(name=addon[1]),
				translate("Error"),
				wx.OK | wx.ICON_ERROR
			)
		else:
			successfullyInstalledCount += 1
		try:
			os.remove(addon[0])
		except OSError:
			pass
	progressDialog.done()
	progressDialog.Hide()
	progressDialog.Destroy()
	# Only present messages if add-ons were actually updated.
	if successfullyInstalledCount:
		if gui.messageBox(
			translate(
				"Changes were made to add-ons. You must restart NVDA for these changes to take effect. "
				"Would you like to restart now?"
			),
			translate("Restart NVDA"),
			wx.YES | wx.NO | wx.ICON_WARNING
		) == wx.YES:
			core.restart()


def updateAddons(addons, auto=True):
	from . import addonUpdateProc
	if not len(addons):
		return
	global _downloadProgressDialog
	meteorInfo = []
	for addon in addons:
		meteorInfo.append(addonUpdateProc.AddonUpdateRecord(
			name=addon["name"] if "name" in addon else "",
			summary=addon["summary"],
			version=addon["version"],
			installedVersion=addon["curVersion"],
			url=addon["path"],
			updateChannel= addon["updateChannel"] if "updateChannel" in addon else ""
		))
	gui.mainFrame.prePopup()
	_downloadProgressDialog = wx.ProgressDialog(
		# Translators: The title of the dialog displayed while downloading add-on update.
		_("Downloading Add-on Update"),
		# Translators: The progress message indicating the name of the add-on being downloaded.
		_("Downloading add-on updates"),
		# PD_AUTO_HIDE is required because ProgressDialog.Update blocks at 100%
		# and waits for the user to press the Close button.
		style=wx.PD_CAN_ABORT | wx.PD_ELAPSED_TIME | wx.PD_REMAINING_TIME | wx.PD_AUTO_HIDE,
		parent=gui.mainFrame
	)
	_downloadProgressDialog.CentreOnScreen()
	_downloadProgressDialog.Raise()
	threading.Thread(target=downloadAndInstallAddonUpdates, args=[meteorInfo]).start()
