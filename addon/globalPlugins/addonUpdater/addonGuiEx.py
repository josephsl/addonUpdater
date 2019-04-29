#gui/addonGui.py
#A part of NonVisual Desktop Access (NVDA)
#This file is covered by the GNU General Public License.
#See the file COPYING for more details.
#Copyright (C) 2012-2019 NV Access Limited, Beqa Gozalishvili, Joseph Lee, Babbage B.V., Ethan Holliger

# Proof of concept user interface for add-on update dilaog (NVDA Core issue 3208)

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
import updateCheck
import core
import extensionPoints
from gui.nvdaControls import AutoWidthColumnCheckListCtrl
from .skipTranslation import translate
# Temporary
addonHandler.initTranslation()

AddonUpdaterManualUpdateCheck = extensionPoints.Action()

_progressDialog = None

# The following event handler comes from a combination of StationPlaylist Studio and Windows 10 App Essentials.

def onAddonUpdateCheck(evt):
	AddonUpdaterManualUpdateCheck.notify()
	global _progressDialog
	_progressDialog = gui.IndeterminateProgressDialog(gui.mainFrame,
	# Translators: The title of the dialog presented while checking for add-on updates.
	_("Add-on update check"),
	# Translators: The message displayed while checking for add-on updates.
	_("Checking for add-on updates..."))
	t = threading.Thread(target=addonUpdateCheck)
	t.daemon = True
	t.start()

def addonUpdateCheck():
	from . import addonHandlerEx
	global _progressDialog
	try:
		info = addonHandlerEx.checkForAddonUpdates()
	except:
		info = None
		wx.CallAfter(_progressDialog.done)
		_progressDialog = None
		wx.CallAfter(gui.messageBox, _("Error checking for add-on updates."), translate("Error"), wx.ICON_ERROR)
		raise
	wx.CallAfter(_progressDialog.done)
	_progressDialog = None
	wx.CallAfter(AddonUpdatesDialog, gui.mainFrame, info, auto=False)

class AddonUpdatesDialog(wx.Dialog):

	def __init__(self,parent, addonUpdateInfo, auto=True):
		# Translators: The title of the add-on updates dialog.
		super(AddonUpdatesDialog,self).__init__(parent,title=_("NVDA Add-on Updates"))
		mainSizer=wx.BoxSizer(wx.VERTICAL)
		addonsSizerHelper = guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)
		self.addonUpdateInfo = addonUpdateInfo
		self.auto = auto

		if addonUpdateInfo:
			entriesSizer=wx.BoxSizer(wx.VERTICAL)
			self.addonsList=AutoWidthColumnCheckListCtrl(self,-1,style=wx.LC_REPORT|wx.LC_SINGLE_SEL,size=(550,350))
			self.addonsList.Bind(wx.EVT_CHECKLISTBOX, self.onAddonsChecked)
			self.addonsList.InsertColumn(0,translate("Package"),width=150)
			# Translators: The label for a column in add-ons list used to identify add-on's running status (example: status is running).
			self.addonsList.InsertColumn(1,_("Current version"),width=50)
			# Translators: The label for a column in add-ons list used to identify add-on's version (example: version is 0.3).
			self.addonsList.InsertColumn(2,_("New version"),width=50)
			entriesSizer.Add(self.addonsList,proportion=8)
			for entry in sorted(addonUpdateInfo.keys()):
				addon = addonUpdateInfo[entry]
				self.addonsList.Append((addon['summary'], addon['curVersion'], addon['version']))
				self.addonsList.CheckItem(self.addonsList.GetItemCount()-1)
			self.addonsList.Select(0)
			self.addonsList.SetItemState(0,wx.LIST_STATE_FOCUSED,wx.LIST_STATE_FOCUSED)
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
		self.Center(wx.BOTH | wx.CENTER_ON_SCREEN)
		wx.CallAfter(self.Show)

	def onAddonsChecked(self, evt):
		try:
			self.updateButton.Enable() if any([self.addonsList.IsChecked(addon) for addon in range(self.addonsList.GetItemCount())]) else self.updateButton.Disable()
		except NameError:
			self.updateButton.Enable() if any([self.addonsList.IsChecked(addon) for addon in range(self.addonsList.GetItemCount())]) else self.updateButton.Disable()

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
			updateAddonsGenerator(self.addonUpdateInfo.values(), auto=self.auto).next()
		except NameError:
			for addon in range(self.addonsList.GetItemCount()):
				if not self.addonsList.IsChecked(addon):
					del self.addonUpdateInfo[availableAddons[addon]]
			next(updateAddonsGenerator(list(self.addonUpdateInfo.values()), auto=self.auto))

	def onClose(self, evt):
		self.Destroy()

# Keep an eye on successful add-on updates.
_updatedAddons = []

def updateAddonsGenerator(addons, auto=True):
	"""Updates one add-on after the other.
	The auto parameter is used to show add-ons manager after all add-ons were updated.
	"""
	if not len(addons):
		# Only present messages if add-osn were actually updated.
		if len(_updatedAddons):
			# This is possible because all add-ons were updated.
			if gui.messageBox(translate("Changes were made to add-ons. You must restart NVDA for these changes to take effect. Would you like to restart now?"),
			translate("Restart NVDA"),
			wx.YES|wx.NO|wx.ICON_WARNING)==wx.YES:
				core.restart()
		return
	# #3208: Update (download and install) add-ons one after the other, done by retrieving the first item (as far as current add-ons container is concerned).
	addonInfo = addons.pop(0)
	downloader = AddonUpdateDownloader([addonInfo["urls"]], addonInfo["summary"], addonsToBeUpdated=addons, auto=auto)
	downloader.start()
	yield


class AddonUpdateDownloader(updateCheck.UpdateDownloader):
	"""Same as downloader class for NVDA screen reader updates.
	No hash checking for now, and URL's and temp file paths are different.
	"""

	def __init__(self, urls, addonName, fileHash=None, addonsToBeUpdated=None, auto=True):
		"""Constructor.
		@param urls: URLs to try for the update file.
		@type urls: list of str
		@param addonName: Name of the add-on being downloaded.
		@type addonName: str
		@param fileHash: The SHA-1 hash of the file as a hex string.
		@type fileHash: basestring
		@param addonsToBeUpdated: a list of add-ons that needs updating.
		@type addonsToBeUpdated: list of str
		@param auto: Automatic add-on updates or not.
		@type auto: bool
		"""
		self.urls = urls
		self.addonName = addonName
		self.destPath = tempfile.mktemp(prefix="nvda_addonUpdate-", suffix=".nvda-addon")
		self.fileHash = fileHash
		self.addonsToBeUpdated = addonsToBeUpdated
		self.auto = auto

	def start(self):
		"""Start the download.
		"""
		self._shouldCancel = False
		# Use a timer because timers aren't re-entrant.
		self._guiExecTimer = wx.PyTimer(self._guiExecNotify)
		gui.mainFrame.prePopup()
		# Translators: The title of the dialog displayed while downloading add-on update.
		self._progressDialog = wx.ProgressDialog(_("Downloading Add-on Update"),
			# Translators: The progress message indicating the name of the add-on being downloaded.
			_("Downloading {name}").format(name = self.addonName),
			# PD_AUTO_HIDE is required because ProgressDialog.Update blocks at 100%
			# and waits for the user to press the Close button.
			style=wx.PD_CAN_ABORT | wx.PD_ELAPSED_TIME | wx.PD_REMAINING_TIME | wx.PD_AUTO_HIDE,
			parent=gui.mainFrame)
		self._progressDialog.Raise()
		t = threading.Thread(target=self._bg)
		t.daemon = True
		t.start()

	def _error(self):
		self._stopped()
		gui.messageBox(
			# Translators: A message indicating that an error occurred while downloading an update to NVDA.
			_("Error downloading update for {name}.").format(name = self.addonName),
			translate("Error"),
			wx.OK | wx.ICON_ERROR)
		self.continueUpdatingAddons()

	def _download(self, url):
		import sys
		if sys.version_info.major == 3:
			remote = urlopen(url, timeout=120)
		else:
			remote = urlopen(url)
		if remote.code != 200:
			raise RuntimeError("Download failed with code %d" % remote.code)
		# #2352: Some security scanners such as Eset NOD32 HTTP Scanner
		# cause huge read delays while downloading.
		# Therefore, set a higher timeout.
		if sys.version_info.major == 2: remote.fp._sock.settimeout(120)
		size = int(remote.headers["content-length"])
		with open(self.destPath, "wb") as local:
			if self.fileHash:
				hasher = hashlib.sha1()
			self._guiExec(self._downloadReport, 0, size)
			read = 0
			chunk=8192
			while True:
				if self._shouldCancel:
					return
				if size -read <chunk:
					chunk =size -read
				block = remote.read(chunk)
				if not block:
					break
				read += len(block)
				if self._shouldCancel:
					return
				local.write(block)
				if self.fileHash:
					hasher.update(block)
				self._guiExec(self._downloadReport, read, size)
			if read < size:
				raise RuntimeError("Content too short")
			if self.fileHash and hasher.hexdigest() != self.fileHash:
				raise RuntimeError("Content has incorrect file hash")
		self._guiExec(self._downloadReport, read, size)

	def _downloadSuccess(self):
		self._stopped()
		try:
			try:
				bundle=addonHandler.AddonBundle(self.destPath.decode("mbcs"))
			except AttributeError:
				bundle=addonHandler.AddonBundle(self.destPath)
			except:
				log.error("Error opening addon bundle from %s"%self.destPath,exc_info=True)
				# Translators: The message displayed when an error occurs when trying to update an add-on package due to package problems.
				gui.messageBox(_("Cannot update {name} - missing file or invalid file format").format(name = self.addonName),
					translate("Error"),
					wx.OK | wx.ICON_ERROR)
				self.continueUpdatingAddons()
				return
			# Check compatibility with NVDA and/or Windows release.
			import versionInfo
			minimumNVDAVersion = bundle.manifest.get("minimumNVDAVersion", None)
			if minimumNVDAVersion is None:
				minimumNVDAVersion = [versionInfo.version_year, versionInfo.version_major]
			lastTestedNVDAVersion = bundle.manifest.get("lastTestedNVDAVersion", None)
			if lastTestedNVDAVersion is None:
				lastTestedNVDAVersion = [versionInfo.version_year, versionInfo.version_major]
			# For NVDA version, only version_year.version_major will be checked.
			minimumYear, minimumMajor = minimumNVDAVersion[:2]
			lastTestedYear, lastTestedMajor = lastTestedNVDAVersion[:2]
			if not ((minimumYear, minimumMajor) <= (versionInfo.version_year, versionInfo.version_major) <= (lastTestedYear, lastTestedMajor)):
				# Translators: The message displayed when trying to update an add-on that is not going to be compatible with the current version of NVDA.
				gui.messageBox(_("{name} add-on is not compatible with this version of NVDA. Minimum NVDA version: {minYear}.{minMajor}, last tested: {testedYear}.{testedMajor}.").format(name = self.addonName, minYear = minimumYear, minMajor = minimumMajor, testedYear=lastTestedYear, testedMajor=lastTestedMajor),
					translate("Error"),
					wx.OK | wx.ICON_ERROR)
				self.continueUpdatingAddons()
				return
			# Some add-ons require a specific Windows release or later.
			import winVersion
			minimumWindowsVersion = bundle.manifest.get("minimumWindowsVersion", None)
			if minimumWindowsVersion is None:
				minimumWindowsVersion = winVersion.winVersion[:3]
			else:
				minimumWindowsVersion = [int(data) for data in minimumWindowsVersion.split(".")]
			minimumWinMajor, minimumWinMinor, minimumWinBuild = minimumWindowsVersion
			winMajor, winMinor, winBuild = winVersion.winVersion[:3]
			if (winMajor, winMinor, winBuild) < (minimumWinMajor, minimumWinMinor, minimumWinBuild):
				# Translators: The message displayed when the add-on requires a newer version of Windows.
				gui.messageBox(_("{name} add-on is not compatible with this version of Windows.").format(name = self.addonName),
					translate("Error"),
					wx.OK | wx.ICON_ERROR)
				self.continueUpdatingAddons()
				return
			bundleName=bundle.manifest['name']
			isDisabled = False
			# Optimization (future): it is better to remove would-be add-ons all at once instead of doing it each time a bundle is opened.
			for addon in addonHandler.getAvailableAddons():
				# Check for disabled state first.
				if bundleName==addon.manifest['name']:
					if addon.isDisabled:
						isDisabled = True
					if not addon.isPendingRemove:
						addon.requestRemove()
					break
			progressDialog = gui.IndeterminateProgressDialog(gui.mainFrame,
			# Translators: The title of the dialog presented while an Addon is being updated.
			_("Updating {name}").format(name = self.addonName),
			# Translators: The message displayed while an addon is being updated.
			_("Please wait while the add-on is being updated."))
			try:
				gui.ExecAndPump(addonHandler.installAddonBundle,bundle)
			except:
				log.error("Error installing  addon bundle from %s"%self.destPath,exc_info=True)
				progressDialog.done()
				progressDialog.Hide()
				progressDialog.Destroy()
				# Translators: The message displayed when an error occurs when installing an add-on package.
				gui.messageBox(_("Failed to update {name} add-on").format(name = self.addonName),
					translate("Error"),
					wx.OK | wx.ICON_ERROR)
				self.continueUpdatingAddons()
				return
			else:
				progressDialog.done()
				progressDialog.Hide()
				progressDialog.Destroy()
				_updatedAddons.append(bundleName)
				if isDisabled:
					for addon in addonHandler.getAvailableAddons():
						if bundleName==addon.manifest['name'] and addon.isPendingInstall:
							addon.enable(False)
							break
		finally:
			try:
				os.remove(self.destPath)
			except OSError:
				pass
		self.continueUpdatingAddons()

	def continueUpdatingAddons(self):
		# Do not leave add-on update installers in the temp directory.
		try:
			os.remove(self.destPath)
		except OSError:
			pass
		try:
			next(updateAddonsGenerator(self.addonsToBeUpdated, auto=self.auto))
		except StopIteration:
			pass
