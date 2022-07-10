# Add-on update process/procedure internals
# Copyright 2022 Joseph Lee, released under GPL

# Proof of concept implementation of NVDA Core issue 3208.
# Split from extended add-on handler and GUI modules in 2022.
# The purpose of this module is to provide implementation of add-on update processes and procedures.
# Specifically, internals of update check, download, and installation steps.
# For update check, this module is responsible for asking different protocols to return update records.
# Note that add-on update record class is striclty part of update procedures/processes.
# Parts will resemble that of extended add-on handler and GUI modules.

from urllib.request import urlopen, Request
import threading
import json
import re
import ssl
import enum
import addonHandler
import globalVars
from logHandler import log
from .urls import URLs
from . import addonUtils
import hashlib
import gui
import extensionPoints
addonHandler.initTranslation()


# Record add-on update information, resembling NVDA add-on manifest.
class AddonUpdateRecord(object):
	"""Resembles add-on manifests but optimized for updates.
	In addition to add-on name, summary, and version, this class records download URL and other data.
	"""

	def __init__(
			self,
			name="",
			summary="",
			version="",
			installedVersion="",
			url="",
			hash=None,
			minimumNVDAVersion=[0, 0, 0],
			lastTestedNVDAVersion=[0, 0, 0],
			updateChannel=""
	):
		self.name = name
		self.summary = summary
		self.version = version
		self.installedVersion = installedVersion
		self.url = url
		self.hash = hash
		self.minimumNVDAVersion = minimumNVDAVersion
		self.lastTestedNVDAVersion = lastTestedNVDAVersion
		self.updateChannel = updateChannel

	def updateDict(self):
		return {
			"name": self.name,
			"summary": self.summary,
			"version": self.version,
			"installedVersion": self.installedVersion,
			"url": self.url,
			"hash": self.hash,
			"minimumNVDAVersion": self.minimumNVDAVersion,
			"lastTestedNVDAVersion": self.lastTestedNVDAVersion,
			"updateChannel": self.updateChannel
		}

	@property
	def updateAvailable(self):
		return self.version != self.installedVersion


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


def checkForAddonUpdates():
	# Don't even think about update checks if secure mode flag is set.
	if globalVars.appArgs.secure:
		return
	from . import addonUpdateProtocols
	updateProtocols = {
		"nvdaprojectcompatinfo": "AddonUpdateCheckProtocolNVDAAddonsGitHub",
		"nvdaes": "AddonUpdateCheckProtocolNVDAEs"
	}
	updateChecker = getattr(addonUpdateProtocols, updateProtocols[addonUtils.updateState["updateSource"]])
	return updateChecker().checkForAddonUpdates()
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
	# Build a list of add-on update records if present.
	if not len(info):
		return None
	res = []
	for addon, updateInfo in info.items():
		res.append(AddonUpdateRecord(
			name=addon,
			summary=addonSummaries[addon],
			version=updateInfo["version"],
			installedVersion=updateInfo["curVersion"],
			url=updateInfo["path"],
			updateChannel=curAddons[addon]["channel"]
		))
	return res


AddonDownloadNotifier = extensionPoints.Action()


def downloadAddonUpdate(url, destPath, fileHash):
	if not destPath:
		import tempfile
		destPath = tempfile.mktemp(prefix="nvda_addonUpdate-", suffix=".nvda-addon")
	log.debug(f"nvda3208: dest path is {destPath}")
	# #2352: Some security scanners such as Eset NOD32 HTTP Scanner
	# cause huge read delays while downloading.
	# Therefore, set a higher timeout.
	try:
		remote = urlopen(url, timeout=120)
	except:
		log.debug("Could not access download URL")
		raise RuntimeError("Could not access download URL")
	if remote.code != 200:
		remote.close()
		raise RuntimeError("Download failed with code %d" % remote.code)
	size = int(remote.headers["content-length"])
	log.debug(f"nvda3208: remote size is {size} bytes")
	with open(destPath, "wb") as local:
		if fileHash:
			hasher = hashlib.sha1()
		read = 0
		AddonDownloadNotifier.notify(read=read, size=size)
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
			AddonDownloadNotifier.notify(read=read, size=size)
		remote.close()
		if read < size:
			raise RuntimeError("Content too short")
		if fileHash and hasher.hexdigest() != fileHash:
			raise RuntimeError("Content has incorrect file hash")
	log.debug("nvda3208: download complete")
	AddonDownloadNotifier.notify(read=read, size=size)


# Record install status.
class AddonInstallStatus(enum.IntEnum):
	AddonInstallSuccess = 0
	AddonInstallGenericError = 1
	AddonReadBundleFailed = 2
	AddonMinVersionNotMet = 3
	AddonNotTested = 4


def installAddonUpdate(destPath, addonName):
	try:
		bundle = addonHandler.AddonBundle(destPath)
	except:
		log.error(f"Error opening addon bundle from {destPath}", exc_info=True)
		return AddonInstallStatus.AddonReadBundleFailed
	# NVDA itself will check add-on compatibility range.
	# As such, the below fragment was borrowed from NVDA Core (credit: NV Access).
	from addonHandler import addonVersionCheck
	if not addonVersionCheck.hasAddonGotRequiredSupport(bundle):
		return AddonInstallStatus.AddonMinVersionNotMet
	elif not addonVersionCheck.isAddonTested(bundle):
		return AddonInstallStatus.AddonNotTested
	bundleName = bundle.manifest['name']
	# Optimization (future): it is better to remove would-be add-ons all at once
	# instead of doing it each time a bundle is opened.
	for addon in addonHandler.getAvailableAddons():
		if bundleName == addon.manifest['name']:
			if not addon.isPendingRemove:
				addon.requestRemove()
			break
	try:
		gui.ExecAndPump(addonHandler.installAddonBundle, bundle)
	except:
		log.error(f"Error installing  addon bundle from {destPath}", exc_info=True)
		return AddonInstallStatus.AddonInstallGenericError
	return AddonInstallStatus.AddonInstallSuccess
