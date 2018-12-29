# -*- coding: UTF-8 -*-
#addonHandler.py
#A part of NonVisual Desktop Access (NVDA)
#Copyright (C) 2012-2017 Rui Batista, NV Access Limited, Noelia Ruiz Martínez, Joseph Lee
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

names2urls={
	"addonUpdater": "https://addons.nvda-project.org/files/get.php?file=nvda3208",
	"Access8Math": "https://addons.nvda-project.org/files/get.php?file=access8math",
	"audioChart": "https://addons.nvda-project.org/files/get.php?file=audiochart",
	"AudioThemes3D": "https://addons.nvda-project.org/files/get.php?file=ath",
	"bgt_lullaby": "https://addons.nvda-project.org/files/get.php?file=bgt",
	"bitChe": "https://addons.nvda-project.org/files/get.php?file=bc",
	"bluetoothaudio": "https://addons.nvda-project.org/files/get.php?file=btaudio",
	"calibre": "https://addons.nvda-project.org/files/get.php?file=cae",
	"classicSelection": "https://addons.nvda-project.org/files/get.php?file=clsel",
	"clipContentsDesigner": "https://addons.nvda-project.org/files/get.php?file=ccd",
	"clipspeak": "https://addons.nvda-project.org/files/get.php?file=cs",
	"clock": "https://addons.nvda-project.org/files/get.php?file=cac",
	"columnsReview": "https://addons.nvda-project.org/files/get.php?file=cr",
	"dayOfTheWeek": "https://addons.nvda-project.org/files/get.php?file=dw",
	"dropbox": "https://addons.nvda-project.org/files/get.php?file=dx",
	"easyTableNavigator": "https://addons.nvda-project.org/files/get.php?file=etn",
	"emoticons": "https://addons.nvda-project.org/files/get.php?file=emo",
	"eMule": "https://addons.nvda-project.org/files/get.php?file=em",
	"enhancedAria": "https://addons.nvda-project.org/files/get.php?file=earia",
	"enhancedTouchGestures": "https://addons.nvda-project.org/files/get.php?file=ets",
	"extendedWinamp": "https://addons.nvda-project.org/files/get.php?file=ew",
	"focusHighlight": "https://addons.nvda-project.org/files/get.php?file=fh",
	"goldenCursor": "https://addons.nvda-project.org/files/get.php?file=gc",
	"goldwave": "https://addons.nvda-project.org/files/get.php?file=gwv",
	"IndentNav": "https://addons.nvda-project.org/files/get.php?file=indentnav",
	"inputLock": "https://addons.nvda-project.org/files/get.php?file=inputlock",
	"instantTranslate": "https://addons.nvda-project.org/files/get.php?file=it",
	"lambda": "https://addons.nvda-project.org/files/get.php?file=lambda",
	"mirc": "https://addons.nvda-project.org/files/get.php?file=mirc",
	"mp3DirectCut": "https://addons.nvda-project.org/files/get.php?file=mp3dc",
	"Mozilla": "https://addons.nvda-project.org/files/get.php?file=moz",
	"mushClient": "https://addons.nvda-project.org/files/get.php?file=mush",
	"noBeepsSpeechMode": "https://addons.nvda-project.org/files/get.php?file=nb",
	"objLocTones": "https://addons.nvda-project.org/files/get.php?file=objLoc",
	"objPad": "https://addons.nvda-project.org/files/get.php?file=objPad",
	"pcKbBrl": "https://addons.nvda-project.org/files/get.php?file=pckbbrl",
	"placeMarkers": "https://addons.nvda-project.org/files/get.php?file=pm",
	"readFeeds": "https://addons.nvda-project.org/files/get.php?file=rf",
	"remote": "https://addons.nvda-project.org/files/get.php?file=nvdaremote",
	"reportSymbols": "https://addons.nvda-project.org/files/get.php?file=rsy",
	"resourceMonitor":"https://addons.nvda-project.org/files/get.php?file=rm",
	"reviewCursorCopier": "https://addons.nvda-project.org/files/get.php?file=rccp",
	"sayCurrentKeyboardLanguage": "https://addons.nvda-project.org/files/get.php?file=ckbl",
	"screenCurtain": "https://addons.nvda-project.org/files/get.php?file=nvda7857",
	"SentenceNav": "https://addons.nvda-project.org/files/get.php?file=sentencenav",
	"speakPasswords": "https://addons.nvda-project.org/files/get.php?file=spp",
	"stationPlaylist": "https://addons.nvda-project.org/files/get.php?file=spl",
	"switchSynth": "https://addons.nvda-project.org/files/get.php?file=sws",
	"systrayList": "https://addons.nvda-project.org/files/get.php?file=st",
	"teamViewer": "https://addons.nvda-project.org/files/get.php?file=tv",
	"textInformation": "https://addons.nvda-project.org/files/get.php?file=txtinfo",
	"textnav": "https://addons.nvda-project.org/files/get.php?file=textnav",
	"toneMaster": "https://addons.nvda-project.org/files/get.php?file=tmast",
	"toolbarsExplorer": "https://addons.nvda-project.org/files/get.php?file=tbx",
	"unicodeBrailleInput": "https://addons.nvda-project.org/files/get.php?file=ubi",
	"virtualRevision": "https://addons.nvda-project.org/files/get.php?file=VR",
	"VLC": "https://addons.nvda-project.org/files/get.php?file=vlc-18",
	"wintenApps": "https://addons.nvda-project.org/files/get.php?file=w10",
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
	updateURL = names2urls[addon]
	# If "-dev" flag is on, switch to development channel if it exists.
	channel = manifestInfo["channel"]
	if channel is not None:
		updateURL += "-" + channel
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
		res.close()
	if res.code != 200:
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
