# Add-on update process/procedure internals
# Copyright 2022 Joseph Lee, released under GPL

# Proof of concept implementation of NVDA Core issue 3208.
# Split from extended add-on handler and GUI modules in 2022.
# The purpose of this module is to provide implementation of add-on update processes and procedures.
# Specifically, internals of update check, download, and installation steps.
# Parts will resemble that of extended add-on handler and GUI modules.

# From extended add-on handler module
from urllib.request import urlopen, Request
import threading
import wx
import json
import re
import ssl
import addonHandler
import globalVars
from logHandler import log
from .urls import URLs
from . import addonUtils
# From extended add-on GUI module
import os
import tempfile
import hashlib
import gui
from gui import guiHelper
try:
	import updateCheck
except RuntimeError:
	raise RuntimeError("Update check module cannot be imported")
import core
import extensionPoints
from gui.nvdaControls import AutoWidthColumnCheckListCtrl
from .skipTranslation import translate
addonHandler.initTranslation()

# The URL prefixes are same for add-ons listed below.
names2urls = {
	"addonUpdater": "nvda3208",
	"Access8Math": "access8math",
	"addonsHelp": "addonshelp",
	"audioChart": "audiochart",
	"beepKeyboard": "beepkeyboard",
	"bluetoothaudio": "btaudio",
	"browsernav": "browsernav",
	"calibre": "cae",
	"charInfo": "chari",
	"checkGestures": "cig",
	"classicSelection": "clsel",
	"clipContentsDesigner": "ccd",
	"clipspeak": "cs",
	"clock": "cac",
	"consoleToolkit": "consoletoolkit",
	"controlUsageAssistant": "cua",
	"dayOfTheWeek": "dw",
	"debugHelper": "debughelper",
	"developerToolkit": "devtoolkit",
	"dropbox": "dx",
	"easyTableNavigator": "etn",
	"emoticons": "emo",
	"eMule": "em",
	"enhancedTouchGestures": "ets",
	"extendedWinamp": "ew",
	"focusHighlight": "fh",
	"goldenCursor": "gc",
	"goldwave": "gwv",
	"IndentNav": "indentnav",
	"inputLock": "inputlock",
	"instantTranslate": "it",
	"killNVDA": "killnvda",
	"lambda": "lambda",
	"mp3DirectCut": "mp3dc",
	"Mozilla": "moz",
	"noBeepsSpeechMode": "nb",
	"NotepadPlusPlus": "NotepadPlusPlus",
	"numpadNavMode": "numpadNav",
	"nvSpeechPlayer": "nvsp",
	"objLocTones": "objLoc",
	"objPad": "objPad",
	"ocr": "ocr",
	"outlookExtended": "outlookextended",
	"pcKbBrl": "pckbbrl",
	"phoneticPunctuation": "phoneticpunc",
	"placeMarkers": "pm",
	"proxy": "nvdaproxy",
	"quickDictionary": "quickdictionary",
	"readFeeds": "rf",
	"remote": "nvdaremote",
	"reportPasswords": "rp",
	"reportSymbols": "rsy",
	"resourceMonitor": "rm",
	"reviewCursorCopier": "rccp",
	"sayCurrentKeyboardLanguage": "ckbl",
	"SentenceNav": "sentencenav",
	"speakPasswords": "spp",
	"speechHistory": "sps",
	"stationPlaylist": "spl",
	"switchSynth": "sws",
	"synthRingSettingsSelector": "synthrings",
	"systrayList": "st",
	"textInformation": "txtinfo",
	"textnav": "textnav",
	"timezone": "tz",
	"toneMaster": "tmast",
	"tonysEnhancements": "tony",
	"toolbarsExplorer": "tbx",
	"trainingKeyboardCommands": "trainingkbdcmd",
	"unicodeBrailleInput": "ubi",
	"updateChannel": "updchannelselect",
	"virtualRevision": "VR",
	"VLC": "vlc-18",
	"wintenApps": "w10",
	"winWizard": "winwizard",
	"wordCount": "wc",
	"wordNav": "wordnav",
	"zoomEnhancements": "zoom",
}


# Add-ons with built-in update feature.
addonsWithUpdaters = [
	"BrailleExtender",
	"Weather Plus",
]


# Add-ons with all features integrated into NVDA or declared "legacy" by authors.
# For the latter case, update check functionality will be disabled upon authors' request.

# Translators: legacy add-on, features included in NVDA.
LegacyAddonIncludedInNVDA = _("features included in NVDA")
# Translators: legacy add-on, declared by add-on developers.
LegacyAddonAuthorDeclaration = _("declared legacy by add-on developers")

LegacyAddons = {
	# Bit Che is no longer maintained as of 2021, therefore the add-on is unnecessary, according to the author.
	"bitChe": LegacyAddonAuthorDeclaration,
	"enhancedAria": LegacyAddonIncludedInNVDA,
	# Advanced focus highlight customizations are not implemented in NVDA yet,
	# but legacy add-on in terms of functionality.
	"focusHighlight": LegacyAddonIncludedInNVDA,
	"screenCurtain": LegacyAddonIncludedInNVDA,
	# Team Viewer is no longer used by the add-on author.
	"teamViewer": LegacyAddonAuthorDeclaration,
}


def shouldNotUpdate():
	# Returns a list of descriptions for add-ons that should not update.
	return [
		addon.manifest["summary"] for addon in addonHandler.getAvailableAddons()
		if addon.name in addonUtils.updateState["noUpdates"]
	]


def preferDevUpdates():
	# Returns a list of descriptions for add-ons that prefers development releases.
	return [
		addon.manifest["summary"] for addon in addonHandler.getAvailableAddons()
		if addon.name in addonUtils.updateState["devUpdates"]
	]


def detectLegacyAddons():
	# Returns a dictionary of add-on name and summary for legacy add-ons.
	return {
		addon.name: addon.manifest["summary"] for addon in addonHandler.getAvailableAddons()
		if addon.name in LegacyAddons
	}


# Validate a given add-on metadata, mostly involving type checks.
def validateAddonMetadata(addonMetadata):
	# Make sure that fields are of the right type.
	metadataFieldTypes = {
		"summary": str,
		"author": str,
		"minimumNVDAVersion": list,
		"lastTestedNVDAVersion": list
	}
	metadataValid = [
		isinstance(addonMetadata[field], fieldType)
		for field, fieldType in metadataFieldTypes.items()
	]
	if "addonKey" in addonMetadata:
		metadataValid.append(isinstance(addonMetadata["addonKey"], str))
	return all(metadataValid)


# Check add-on update eligibility with help from community add-ons metadata if present.
def addonCompatibleAccordingToMetadata(addon, addonMetadata):
	# Always return "yes" for development releases.
	# The whole point of development releases is to send feedback to add-on developers across NVDA releases.
	# Although possible, development releases should not be used to dodge around NVDA compatibility checks
	# as add-ons can break without notice.
	if addon in addonUtils.updateState["devUpdates"]:
		return True
	import addonAPIVersion
	minimumNVDAVersion = tuple(addonMetadata["minimumNVDAVersion"])
	lastTestedNVDAVersion = tuple(addonMetadata["lastTestedNVDAVersion"])
	# Is the add-on update compatible with local NVDA version the user is using?
	return (
		minimumNVDAVersion <= addonAPIVersion.CURRENT
		and lastTestedNVDAVersion >= addonAPIVersion.BACK_COMPAT_TO
	)


# Borrowed ideas from NVDA Core.
# Obtain update status for add-ons returned from community add-ons website.
# Use threads for opening URL's in parallel, resulting in faster update check response on multicore systems.
# This is the case when it becomes necessary to open another website.
# Also, check add-on update eligibility based on what community add-ons metadata says if present.
def fetchAddonInfo(info, results, addon, manifestInfo, addonsData):
	addonVersion = manifestInfo["version"]
	# Is this add-on's metadata present?
	try:
		addonMetadata = addonsData["active"][addon]
		addonMetadataPresent = True
	except KeyError:
		addonMetadata = {}
		addonMetadataPresent = False
	# Validate add-on metadata.
	if addonMetadataPresent:
		addonMetadataPresent = validateAddonMetadata(addonMetadata)
	# Add-ons metadata includes addon key in active/addonName/addonKey.
	addonKey = addonMetadata.get("addonKey") if addonMetadataPresent else None
	# If add-on key is None, it can indicate Add-on metadata is unusable or add-on key was unassigned.
	# Therefore use the add-on key map that ships with this add-on, although it may not record new add-ons.
	if addonKey is None:
		try:
			addonKey = names2urls[addon]
		except KeyError:
			return
	# If "-dev" flag is on, switch to development channel if it exists.
	channel = manifestInfo["channel"]
	if channel is not None:
		addonKey += "-" + channel
	# Can the add-on be updated based on community add-ons metadata?
	# What if a different update channel must be used if the stable channel update is not compatible?
	if addonMetadataPresent:
		if not addonCompatibleAccordingToMetadata(addon, addonMetadata):
			return
	try:
		addonUrl = results[addonKey]
	except:
		return
	# Necessary duplication if the URL doesn't end in ".nvda-addon".
	# Some add-ons require traversing another URL.
	if ".nvda-addon" not in addonUrl:
		res = None
		# Some hosting services block Python/urllib in hopes of avoding bots.
		# Therefore spoof the user agent to say this is latest Microsoft Edge.
		# Source: Stack Overflow, Google searches on Apache/mod_security
		req = Request(
			f"{URLs.communityFileGetter}{addonKey}",
			headers={
				"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.64 Safari/537.36 Edg/101.0.1210.47"  # NOQA: E501
			}
		)
		try:
			res = urlopen(req)
		except IOError as e:
			# SSL issue (seen in NVDA Core earlier than 2014.1).
			if isinstance(e.reason, ssl.SSLCertVerificationError) and e.reason.reason == "CERTIFICATE_VERIFY_FAILED":
				addonUtils._updateWindowsRootCertificates()
				res = urlopen(req)
			else:
				pass
		finally:
			if res is not None:
				addonUrl = res.url
				res.close()
		if res is None or (res and res.code != 200):
			return
	# Note that some add-ons are hosted on community add-ons server directly.
	if "/" not in addonUrl:
		addonUrl = f"{URLs.communityHostedFile}{addonUrl}"
	# Announce add-on URL for debugging purposes.
	log.debug(f"nvda3208: add-on URL is {addonUrl}")
	# Build emulated add-on update dictionary if there is indeed a new version.
	# All the info we need for add-on version check is after the last slash.
	# Sometimes, regular expression fails, and if so, treat it as though there is no update for this add-on.
	try:
		version = re.search("(?P<name>)-(?P<version>.*).nvda-addon", addonUrl.split("/")[-1]).groupdict()["version"]
	except:
		log.debug("nvda3208: could not retrieve version info for an add-on from its URL", exc_info=True)
		return
	# If hosted on places other than add-ons server, an unexpected URL might be returned, so parse this further.
	if addon in version:
		version = version.split(addon)[1][1:]
	if addonVersion != version:
		info[addon] = {"curVersion": addonVersion, "version": version, "path": addonUrl}


def checkForAddonUpdate(curAddons):
	# First, fetch current community add-ons via an internal thread.
	def _currentCommunityAddons(results):
		res = None
		try:
			res = urlopen(URLs.communityAddonsList)
		except IOError as e:
			# SSL issue (seen in NVDA Core earlier than 2014.1).
			if isinstance(e.reason, ssl.SSLCertVerificationError) and e.reason.reason == "CERTIFICATE_VERIFY_FAILED":
				addonUtils._updateWindowsRootCertificates()
				res = urlopen(URLs.communityAddonsList)
			else:
				# Inform results dictionary that an error has occurred as this is running inside a thread.
				log.debug("nvda3208: errors occurred while retrieving community add-ons", exc_info=True)
				results["error"] = True
		finally:
			if res is not None:
				results.update(json.load(res))
				res.close()

	# Similar to above except fetch add-on metadata from a JSON file hosted by the NVDA add-ons community.
	def _currentCommunityAddonsMetadata(addonsData):
		res = None
		try:
			res = urlopen(URLs.metadata)
		except IOError as e:
			# SSL issue (seen in NVDA Core earlier than 2014.1).
			if isinstance(e.reason, ssl.SSLCertVerificationError) and e.reason.reason == "CERTIFICATE_VERIFY_FAILED":
				addonUtils._updateWindowsRootCertificates()
				res = urlopen(URLs.metadata)
			else:
				# Clear addon metadata dictionary.
				log.debug("nvda3208: errors occurred while retrieving community add-ons metadata", exc_info=True)
				addonsData.clear()
		finally:
			if res is not None:
				addonsData.update(json.load(res))
				res.close()
	# NVDA community add-ons list is always retrieved for fallback reasons.
	results = {}
	addonsFetcher = threading.Thread(target=_currentCommunityAddons, args=(results,))
	addonsFetcher.start()
	# This internal thread must be joined, otherwise results will be lost.
	addonsFetcher.join()
	# Raise an error if results says so.
	if "error" in results:
		raise RuntimeError("Failed to retrieve community add-ons")
	# Enhanced with add-on metadata such as compatibility info maintained by the community.
	addonsData = {}
	addonsFetcher = threading.Thread(target=_currentCommunityAddonsMetadata, args=(addonsData,))
	addonsFetcher.start()
	# Just like the earlier thread, this thread too must be joined.
	addonsFetcher.join()
	# Fallback to add-ons list if metadata is unusable.
	if len(addonsData) == 0:
		log.debug("nvda3208: add-ons metadata unusable, using add-ons list from community add-ons website")
	else:
		log.debug("nvda3208: add-ons metadata successfully retrieved")
	# The info dictionary will be passed in as a reference in individual threads below.
	# Don't forget to perform additional checks based on add-on metadata if present.
	info = {}
	updateThreads = [
		threading.Thread(target=fetchAddonInfo, args=(info, results, addon, manifestInfo, addonsData))
		for addon, manifestInfo in curAddons.items()
	]
	for thread in updateThreads:
		thread.start()
	for thread in updateThreads:
		thread.join()
	return info


def checkForAddonUpdates():
	# Don't even think about update checks if secure mode flag is set.
	if globalVars.appArgs.secure:
		return
	curAddons = {}
	addonSummaries = {}
	for addon in addonHandler.getAvailableAddons():
		# Skip add-ons that can update themselves.
		# Add-on Updater is included, but is an exception as it updates other add-ons, too.
		if addon.name in addonsWithUpdaters:
			continue
		# Sorry Nuance Vocalizer family, no update checks for you.
		if "vocalizer" in addon.name.lower():
			continue
		manifest = addon.manifest
		name = addon.name
		if name in addonUtils.updateState["noUpdates"]:
			continue
		curVersion = manifest["version"]
		# Check different channels if appropriate.
		updateChannel = manifest.get("updateChannel")
		if updateChannel == "None":
			updateChannel = None
		if updateChannel != "dev" and name in addonUtils.updateState["devUpdates"]:
			updateChannel = "dev"
		elif updateChannel == "dev" and name not in addonUtils.updateState["devUpdates"]:
			updateChannel = None
		curAddons[name] = {"summary": manifest["summary"], "version": curVersion, "channel": updateChannel}
		addonSummaries[name] = manifest["summary"]
	try:
		info = checkForAddonUpdate(curAddons)
	except:
		# Present an error dialog if manual add-on update check is in progress.
		raise RuntimeError("Cannot check for community add-on updates")
	res = info
	for addon in res:
		res[addon]["summary"] = addonSummaries[addon]
		# In reality, it'll be a list of URL's to try.
		res[addon]["urls"] = res[addon]["path"]
	return res if len(res) else None


def autoAddonUpdateCheck():
	t = threading.Thread(target=_showAddonUpdateUI)
	t.daemon = True
	t.start()


# Only stored when update toast appears.
_updateInfo = None


def _showAddonUpdateUI():
	def _showAddonUpdateUICallback(info):
		import gui
		from .addonGuiEx import AddonUpdatesDialog
		gui.mainFrame.prePopup()
		AddonUpdatesDialog(gui.mainFrame, info).Show()
		gui.mainFrame.postPopup()
	try:
		info = checkForAddonUpdates()
	except:
		info = None
		raise
	if info is not None:
		# Show either the update notification toast (Windows 10 and later)
		# or the results dialog (other Windows releases and server systems).
		# On Windows 10 and later (client versions), this behavior is configurable.
		# If toast is shown, checking for add-on updates from tools menu will merely show the results dialog.
		# wxPython 4.1.0 (and consequently, wxWidges 3.1.0) simplifies this by
		# allowing action handlers to be defined for toasts, which will then show the results dialog on the spot.
		# However it doesn't work for desktop apps such as NVDA.
		import winVersion
		winVer = winVersion.getWinVer()
		if (
			winVer >= winVersion.WIN10 and winVer.productType == "workstation"
			and addonUtils.updateState["updateNotification"] == "toast"
		):
			global _updateInfo
			updateMessage = _(
				# Translators: presented as part of add-on update notification message.
				"One or more add-on updates are available. "
				"Go to NVDA menu, Tools, Check for add-on updates to review them."
			)
			# Translators: title of the add-on update notification message.
			wx.adv.NotificationMessage(_("NVDA add-on updates"), updateMessage).Show(timeout=30)
			_updateInfo = info
		else:
			wx.CallAfter(_showAddonUpdateUICallback, info)


# Content from extended add-on GUI module

AddonUpdaterManualUpdateCheck = extensionPoints.Action()

_progressDialog = None


# The following event handler comes from a combination of StationPlaylist and Windows App Essentials.
def onAddonUpdateCheck(evt):
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
			next(updateAddonsGenerator(list(self.addonUpdateInfo.values()), auto=self.auto))
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
			if gui.messageBox(
				translate(
					"Changes were made to add-ons. You must restart NVDA for these changes to take effect. "
					"Would you like to restart now?"
				),
				translate("Restart NVDA"),
				wx.YES | wx.NO | wx.ICON_WARNING
			) == wx.YES:
				core.restart()
		return
	# #3208: Update (download and install) add-ons one after the other,
	# done by retrieving the first item (as far as current add-ons container is concerned).
	addonInfo = addons.pop(0)
	downloader = AddonUpdateDownloader(
		[addonInfo["urls"]], addonInfo["summary"], addonsToBeUpdated=addons, auto=auto
	)
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
		self._guiExecTimer = gui.NonReEntrantTimer(self._guiExecNotify)
		gui.mainFrame.prePopup()
		self._progressDialog = wx.ProgressDialog(
			# Translators: The title of the dialog displayed while downloading add-on update.
			_("Downloading Add-on Update"),
			# Translators: The progress message indicating the name of the add-on being downloaded.
			_("Downloading {name}").format(name=self.addonName),
			# PD_AUTO_HIDE is required because ProgressDialog.Update blocks at 100%
			# and waits for the user to press the Close button.
			style=wx.PD_CAN_ABORT | wx.PD_ELAPSED_TIME | wx.PD_REMAINING_TIME | wx.PD_AUTO_HIDE,
			parent=gui.mainFrame
		)
		self._progressDialog.CentreOnScreen()
		self._progressDialog.Raise()
		t = threading.Thread(target=self._bg)
		t.daemon = True
		t.start()

	def _error(self):
		self._stopped()
		gui.messageBox(
			# Translators: A message indicating that an error occurred while downloading an update to NVDA.
			_("Error downloading update for {name}.").format(name=self.addonName),
			translate("Error"),
			wx.OK | wx.ICON_ERROR)
		self.continueUpdatingAddons()


def downloadAddonUpdate(url, destPath, fileHash):
	# #2352: Some security scanners such as Eset NOD32 HTTP Scanner
	# cause huge read delays while downloading.
	# Therefore, set a higher timeout.
	remote = urlopen(url, timeout=120)
	if remote.code != 200:
		raise RuntimeError("Download failed with code %d" % remote.code)
	size = int(remote.headers["content-length"])
	with open(destPath, "wb") as local:
		if fileHash:
			hasher = hashlib.sha1()
		read = 0
		chunk = 8192
		while True:
			if size - read < chunk:
				chunk = size - read
			block = remote.read(chunk)
			if not block:
				break
			read += len(block)
			local.write(block)
			if fileHash:
				hasher.update(block)
		if read < size:
			raise RuntimeError("Content too short")
		if fileHash and hasher.hexdigest() != fileHash:
			raise RuntimeError("Content has incorrect file hash")

def installAddonUpdate(destPath, addonName):
	self._stopped()
	try:
		try:
			bundle = addonHandler.AddonBundle(destPath)
		except:
			log.error(f"Error opening addon bundle from {destPath}", exc_info=True)
			gui.messageBox(
				# Translators: The message displayed when an error occurs
				# when trying to update an add-on package due to package problems.
				_("Cannot update {name} - missing file or invalid file format").format(name=addonName),
				translate("Error"),
				wx.OK | wx.ICON_ERROR
			)
			self.continueUpdatingAddons()
			return
		# NVDA itself will check add-on compatibility range.
		# As such, the below fragment was borrowed from NVDA Core (credit: NV Access).
		from addonHandler import addonVersionCheck
		from gui import addonGui
		if not addonVersionCheck.hasAddonGotRequiredSupport(bundle):
			addonGui._showAddonRequiresNVDAUpdateDialog(gui.mainFrame, bundle)
			self.continueUpdatingAddons()
			return
		elif not addonVersionCheck.isAddonTested(bundle):
			addonGui._showAddonTooOldDialog(gui.mainFrame, bundle)
			self.continueUpdatingAddons()
			return
		bundleName = bundle.manifest['name']
		# Optimization (future): it is better to remove would-be add-ons all at once
		# instead of doing it each time a bundle is opened.
		for addon in addonHandler.getAvailableAddons():
			if bundleName == addon.manifest['name']:
				if not addon.isPendingRemove:
					addon.requestRemove()
				break
		progressDialog = gui.IndeterminateProgressDialog(
			gui.mainFrame,
			# Translators: The title of the dialog presented while an Addon is being updated.
			_("Updating {name}").format(name=addonName),
			# Translators: The message displayed while an addon is being updated.
			_("Please wait while the add-on is being updated.")
		)
		try:
			gui.ExecAndPump(addonHandler.installAddonBundle, bundle)
		except:
			log.error(f"Error installing  addon bundle from {destPath}", exc_info=True)
			progressDialog.done()
			progressDialog.Hide()
			progressDialog.Destroy()
			gui.messageBox(
				# Translators: The message displayed when an error occurs when installing an add-on package.
				_("Failed to update {name} add-on").format(name=addonName),
				translate("Error"),
				wx.OK | wx.ICON_ERROR
			)
			self.continueUpdatingAddons()
			return
		else:
			progressDialog.done()
			progressDialog.Hide()
			progressDialog.Destroy()
			_updatedAddons.append(bundleName)
	finally:
		try:
			os.remove(destPath)
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
