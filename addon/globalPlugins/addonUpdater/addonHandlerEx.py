# -*- coding: UTF-8 -*-
# addonHandler.py
# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2012-2019 Rui Batista, NV Access Limited, Noelia Ruiz Martínez, Joseph Lee
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

# Proof of concept implementation of NVDA Core issue 3208.

from urllib.request import urlopen
import threading
import wx
import json
import re
import ssl
import addonHandler
from logHandler import log
from . import addonUtils

# The URL prefixes are same for add-ons listed below.
names2urls = {
	"addonUpdater": "nvda3208",
	"Access8Math": "access8math",
	"addonsHelp": "addonshelp",
	"audioChart": "audiochart",
	"AudioThemes3D": "ath",
	"beepKeyboard": "beepkeyboard",
	"bgt_lullaby": "bgt",
	"bluetoothaudio": "btaudio",
	"browsernav": "browsernav",
	"calibre": "cae",
	"charInfo": "chari",
	"checkGestures": "cig",
	"classicSelection": "clsel",
	"clipContentsDesigner": "ccd",
	"clipspeak": "cs",
	"clock": "cac",
	"columnsReview": "cr",
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
	"mirc": "mirc",
	"mp3DirectCut": "mp3dc",
	"Mozilla": "moz",
	"mushClient": "mush",
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
	"winMag": "winmag",
	"wintenApps": "w10",
	"winWizard": "winwizard",
	"wordCount": "wc",
	"wordNav": "wordnav",
	"zoomEnhancements": "zoom",
}


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


# Borrowed ideas from NVDA Core.
# Obtain update status for add-ons returned from community add-ons website.
# Use threads for opening URL's in parallel, resulting in faster update check response on multicore systems.
# This is the case when it becomes necessary to open another website.
def fetchAddonInfo(info, results, addon, manifestInfo):
	addonVersion = manifestInfo["version"]
	addonKey = names2urls[addon]
	# If "-dev" flag is on, switch to development channel if it exists.
	channel = manifestInfo["channel"]
	if channel is not None:
		addonKey += "-" + channel
	try:
		addonUrl = results[addonKey]
	except:
		return
	# Necessary duplication if the URL doesn't end in ".nvda-addon".
	# Some add-ons require traversing another URL.
	if ".nvda-addon" not in addonUrl:
		res = None
		try:
			res = urlopen(f"https://addons.nvda-project.org/files/get.php?file={addonKey}")
		except IOError as e:
			# SSL issue (seen in NVDA Core earlier than 2014.1).
			if isinstance(e.strerror, ssl.SSLError) and e.strerror.reason == "CERTIFICATE_VERIFY_FAILED":
				addonUtils._updateWindowsRootCertificates()
				res = urlopen(f"https://addons.nvda-project.org/files/get.php?file={addonKey}")
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
		addonUrl = f"https://addons.nvda-project.org/files/{addonUrl}"
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
			res = urlopen("https://addons.nvda-project.org/files/get.php?addonslist")
		except IOError as e:
			# SSL issue (seen in NVDA Core earlier than 2014.1).
			if isinstance(e.strerror, ssl.SSLError) and e.strerror.reason == "CERTIFICATE_VERIFY_FAILED":
				addonUtils._updateWindowsRootCertificates()
				res = urlopen("https://addons.nvda-project.org/files/get.php?addonslist")
			else:
				# Inform results dictionary that an error has occurred as this is running inside a thread.
				log.debug("nvda3208: errors occurred while retrieving community add-ons", exc_info=True)
				results["error"] = True
		finally:
			if res is not None:
				results.update(json.load(res))
				res.close()
	results = {}
	addonsFetcher = threading.Thread(target=_currentCommunityAddons, args=(results,))
	addonsFetcher.start()
	# This internal thread must be joined, otherwise results will be lost.
	addonsFetcher.join()
	# Raise an error if results says so.
	if "error" in results:
		raise RuntimeError("Failed to retrieve community add-ons")
	# The info dictionary will be passed in as a reference in individual threads below.
	info = {}
	updateThreads = [
		threading.Thread(target=fetchAddonInfo, args=(info, results, addon, manifestInfo))
		for addon, manifestInfo in curAddons.items()
	]
	for thread in updateThreads:
		thread.start()
	for thread in updateThreads:
		thread.join()
	return info


def checkForAddonUpdates():
	curAddons = {}
	addonSummaries = {}
	for addon in addonHandler.getAvailableAddons():
		if addon.name not in names2urls:
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
	# data = json.dumps(curAddons)
	# Pseudocode:
	"""try:
		res = urllib.open(someURL, data)
		# Check SSL and what not.
		res = json.loads(res)"""
	# res = json.loads(data)
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
		# Show either the update notification toast (Windows 10) or the results dialog (other Windows releases).
		# If toast is shown, checking for add-on updates from tools menu will merely show the results dialog.
		# wxPython 4.1.0 (and consequently, wxWidges 3.1.0) simplifies this by
		# allowing action handlers to be defined for toasts, which will then show the results dialog on the spot.
		# However it doesn't work for desktop apps such as NVDA.
		import sys
		if sys.getwindowsversion().major == 10:
			global _updateInfo
			updateMessage = []
			if len(info) == 1:
				updateMessage.append("1 NVDA add-on update is available.")
			else:
				updateMessage.append("%s NVDA add-on updates are available."%len(info))
			updateMessage.append("Go to NVDA menu, Tools, Check for add-on update to review them.")
			wx.adv.NotificationMessage("NVDA add-on updates", " ".join(updateMessage)).Show(timeout=30)
			_updateInfo = info
		else: wx.CallAfter(_showAddonUpdateUICallback, info)
