# -*- coding: UTF-8 -*-
#addonHandler.py
#A part of NonVisual Desktop Access (NVDA)
#Copyright (C) 2012-2019 Rui Batista, NV Access Limited, Noelia Ruiz Martínez, Joseph Lee
#This file is covered by the GNU General Public License.
#See the file COPYING for more details.

# Proof of concept implementation of NVDA Core issue 3208.

try:
	from urllib import urlopen
except:
	from urllib.request import urlopen
import threading
import wx
import json
import re
import ssl
import addonHandler
from . import addonUtils

# The URL prefixes are same for add-ons listed below.
names2urls={
	"addonUpdater": "nvda3208",
	"Access8Math": "access8math",
	"addonsHelp": "addonshelp",
	"audioChart": "audiochart",
	"AudioThemes3D": "ath",
	"bgt_lullaby": "bgt",
	"bitChe": "bc",
	"bluetoothaudio": "btaudio",
	"browsernav": "browsernav",
	"calibre": "cae",
	"charInfo": "chari",
	"classicSelection": "clsel",
	"clipContentsDesigner": "ccd",
	"clipspeak": "cs",
	"clock": "cac",
	"columnsReview": "cr",
	"dayOfTheWeek": "dw",
	"dropbox": "dx",
	"easyTableNavigator": "etn",
	"emoticons": "emo",
	"eMule": "em",
	"enhancedAria": "earia",
	"enhancedTouchGestures": "ets",
	"extendedWinamp": "ew",
	"focusHighlight": "fh",
	"goldenCursor": "gc",
	"goldwave": "gwv",
	"ImageDescriber": "imgdesc",
	"IndentNav": "indentnav",
	"inputLock": "inputlock",
	"instantTranslate": "it",
	"lambda": "lambda",
	"mirc": "mirc",
	"mp3DirectCut": "mp3dc",
	"Mozilla": "moz",
	"mushClient": "mush",
	"noBeepsSpeechMode": "nb",
	"objLocTones": "objLoc",
	"objPad": "objPad",
	"outlookExtended": "outlookextended",
	"pcKbBrl": "pckbbrl",
	"placeMarkers": "pm",
	"readFeeds": "rf",
	"remote": "nvdaremote",
	"reportSymbols": "rsy",
	"resourceMonitor":"rm",
	"reviewCursorCopier": "rccp",
	"sayCurrentKeyboardLanguage": "ckbl",
	"screenCurtain": "nvda7857",
	"SentenceNav": "sentencenav",
	"speakPasswords": "spp",
	"stationPlaylist": "spl",
	"switchSynth": "sws",
	"systrayList": "st",
	"teamViewer": "tv",
	"textInformation": "txtinfo",
	"textnav": "textnav",
	"toneMaster": "tmast",
	"toolbarsExplorer": "tbx",
	"unicodeBrailleInput": "ubi",
	"virtualRevision": "VR",
	"VLC": "vlc-18",
	"wintenApps": "w10",
	"wordCount": "wc",
}

def shouldNotUpdate():
	# Returns a list of descriptions for add-ons that should not update.
	return [addon.manifest["summary"] for addon in addonHandler.getAvailableAddons()
		if addon.name in addonUtils.updateState["noUpdates"]]

def preferDevUpdates():
	# Returns a list of descriptions for add-ons that prefers development releases.
	return [addon.manifest["summary"] for addon in addonHandler.getAvailableAddons()
		if addon.name in addonUtils.updateState["devUpdates"]]

# Borrowed ideas from NVDA Core.
# Use threads for opening URL's in parallel, resulting in faster update check response on multicore systems.

def fetchAddonInfo(info, addon, manifestInfo):
	addonVersion = manifestInfo["version"]
	addonKey = names2urls[addon]
	# If "-dev" flag is on, switch to development channel if it exists.
	channel = manifestInfo["channel"]
	if channel is not None:
		addonKey += "-" + channel
	updateURL = "https://addons.nvda-project.org/files/get.php?file=%s"%addonKey
	res = None
	try:
		res = urlopen(updateURL)
	except IOError as e:
		# SSL issue (seen in NVDA Core earlier than 2014.1).
		if isinstance(e.strerror, ssl.SSLError) and e.strerror.reason == "CERTIFICATE_VERIFY_FAILED":
			addonUtils._updateWindowsRootCertificates()
			res = urlopen(updateURL)
		else:
			pass
	finally:
		if res is not None: res.close()
	if res is None or (res and res.code != 200):
		return
	# Build emulated add-on update dictionary if there is indeed a new version.
	version = re.search("(?P<name>)-(?P<version>.*).nvda-addon", res.url).groupdict()["version"]
	# If hosted on places other than add-ons server, an unexpected URL might be returned, so parse this further.
	if addon in version: version = version.split(addon)[1][1:]
	if addonVersion != version:
		info[addon] = {"curVersion": addonVersion, "version": version, "path": res.url}

def checkForAddonUpdate(curAddons):
	# The info dictionary will be passed in as a reference in individual threads below.
	info = {}
	updateThreads = [threading.Thread(target=fetchAddonInfo, args=(info, addon, manifestInfo)) for addon, manifestInfo  in curAddons.items()]
	for thread in updateThreads:	
		thread.start()
	for thread in updateThreads:
		thread.join()
	return info

def checkForAddonUpdates():
	curAddons = {}
	addonSummaries = {}
	for addon in addonHandler.getAvailableAddons():
		if addon.name not in names2urls: continue
		# Sorry Nuance Vocalizer family, no update checks for you.
		if "vocalizer" in addon.name.lower(): continue
		manifest = addon.manifest
		name = addon.name
		if name in addonUtils.updateState["noUpdates"]: continue
		curVersion = manifest["version"]
		# Check different channels if appropriate.
		updateChannel = manifest.get("updateChannel")
		if updateChannel == "None": updateChannel = None
		if updateChannel != "dev" and name in addonUtils.updateState["devUpdates"]:
			updateChannel = "dev"
		elif updateChannel == "dev" and name not in addonUtils.updateState["devUpdates"]:
			updateChannel = None
		curAddons[name] = {"summary": manifest["summary"], "version": curVersion, "channel": updateChannel}
		addonSummaries[name] = manifest["summary"]
	try:
		info = checkForAddonUpdate(curAddons)
	except:
		info = {}
	#data = json.dumps(curAddons)
	# Pseudocode:
	"""try:
		res = urllib.open(someURL, data)
		# Check SSL and what not.
		res = json.loads(res)"""
	#res = json.loads(data)
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
		wx.CallAfter(_showAddonUpdateUICallback, info)
