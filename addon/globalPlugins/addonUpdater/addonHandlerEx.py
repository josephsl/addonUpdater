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
	"resourceMonitor":"https://addons.nvda-project.org/files/get.php?file=rm",
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
		return {"curVersion": addonVersion, "newVersion": version, "path": res.url}
	return None

def checkForAddonUpdates():
	curAddons = {}
	addonSummaries = {}
	for addon in addonHandler.getAvailableAddons():
		manifest = addon.manifest
		name = manifest["name"]
		if name not in names2urls: continue
		curVersion = manifest["version"]
		curAddons[manifest["name"]] = {"summary": manifest["summary"], "version": curVersion}
		addonSummaries[manifest["name"]] = {"summary": manifest["summary"], "curVersion": curVersion}
		checkForAddonUpdate(names2urls[name], name, curVersion)
	data = json.dumps(curAddons)
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
	return res

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
