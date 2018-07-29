# -*- coding: UTF-8 -*-
#addonHandler.py
#A part of NonVisual Desktop Access (NVDA)
#Copyright (C) 2012-2017 Rui Batista, NV Access Limited, Noelia Ruiz Martínez, Joseph Lee
#This file is covered by the GNU General Public License.
#See the file COPYING for more details.

# Proof of concept implementation of NVDA Core issue 3208.

import urllib
import threading
import wx
import json
import re
import addonHandler

names2urls={
	"addonUpdater": "https://addons.nvda-project.org/files/get.php?file=nvda3208",
	"Access8Math": "https://addons.nvda-project.org/files/get.php?file=access8math",
	"AudioThemes3D": "https://addons.nvda-project.org/files/get.php?file=ath",
	"bgt_lullaby": "https://addons.nvda-project.org/files/get.php?file=bgt",
	"bitChe": "https://addons.nvda-project.org/files/get.php?file=bc",
	"classicSelection": "https://addons.nvda-project.org/files/get.php?file=clsel",
	"clipContentsDesigner": "https://addons.nvda-project.org/files/get.php?file=ccd",
	"clipspeak": "https://addons.nvda-project.org/files/get.php?file=cs",
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
	"reportSymbols": "https://addons.nvda-project.org/files/get.php?file=rsy",
	"resourceMonitor":"https://addons.nvda-project.org/files/get.php?file=rm",
	"reviewCursorCopier": "https://addons.nvda-project.org/files/get.php?file=rccp",
	"sayCurrentKeyboardLanguage": "https://addons.nvda-project.org/files/get.php?file=ckbl",
	"SentenceNav": "https://addons.nvda-project.org/files/get.php?file=sentencenav",
	"speakPasswords": "https://addons.nvda-project.org/files/get.php?file=spp",
	"speechHistory": "https://addons.nvda-project.org/files/get.php?file=sps",
	"switchSynth": "https://addons.nvda-project.org/files/get.php?file=sws",
	"systrayList": "https://addons.nvda-project.org/files/get.php?file=st",
	"teamViewer": "https://addons.nvda-project.org/files/get.php?file=tv",
	"textInformation": "https://addons.nvda-project.org/files/get.php?file=txtinfo",
	"toneMaster": "https://addons.nvda-project.org/files/get.php?file=tmast",
	"unicodeBrailleInput": "https://addons.nvda-project.org/files/get.php?file=ubi",
	"virtualRevision": "https://addons.nvda-project.org/files/get.php?file=VR",
	"VLC": "https://addons.nvda-project.org/files/get.php?file=vlc-18",
	"word": "https://addons.nvda-project.org/files/get.php?file=wrd",
}

# Borrowed ideas from NVDA Core.
def checkForAddonUpdate(updateURL, name, addonVersion):
	try:
		res = urllib.urlopen(updateURL)
		res.close()
	except IOError as e:
		# SSL issue (seen in NVDA Core earlier than 2014.1).
		if isinstance(e.strerror, ssl.SSLError) and e.strerror.reason == "CERTIFICATE_VERIFY_FAILED":
			addonUtils._updateWindowsRootCertificates()
			res = urllib.urlopen(updateURL)
		else:
			raise
	if res.code != 200:
		raise RuntimeError("Checking for update failed with code %d" % res.code)
	# Build emulated add-on update dictionary if there is indeed a new version.
	version = re.search("(?P<name>)-(?P<version>.*).nvda-addon", res.url).groupdict()["version"]
	# If hosted on places other than add-ons server, an unexpected URL might be returned, so parse this further.
	version = version.split(name)[1][1:]
	if addonVersion != version:
		return {"curVersion": addonVersion, "version": version, "path": res.url}
	return None

def checkForAddonUpdates():
	curAddons = {}
	addonSummaries = {}
	for addon in addonHandler.getAvailableAddons():
		manifest = addon.manifest
		name = manifest["name"]
		if name not in names2urls: continue
		curVersion = manifest["version"]
		curAddons[name] = {"summary": manifest["summary"], "version": curVersion}
		info = checkForAddonUpdate(names2urls[name], name, curVersion)
		if info:
			addonSummaries[name] = {"summary": manifest["summary"], "curVersion": curVersion}
			addonSummaries[name].update(info)
	# Necessary duplication.
	#data = json.dumps(curAddons)
	data = json.dumps(addonSummaries)
	# Pseudocode:
	"""try:
		res = urllib.open(someURL, data)
		# Check SSL and what not.
		res = json.loads(res)"""
	res = json.loads(data)
	for addon in res:
		res[addon].update(addonSummaries[addon])
		# In reality, it'll be a list of URL's to try.
		res[addon]["urls"] = names2urls[addon]
	return res if len(res) else None

def autoAddonUpdateCheck():
	t = threading.Thread(target=_showAddonUpdateUI)
	t.daemon = True
	t.start()

def _showAddonUpdateUI():
	info = checkForAddonUpdates()
	if info is not None:
		import gui
		from .addonGuiEx import AddonUpdatesDialog
		wx.CallAfter(AddonUpdatesDialog, gui.mainFrame, info)
