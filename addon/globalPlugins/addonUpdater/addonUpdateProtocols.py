# Add-on update protocols
# Copyright 2022-2023 Joseph Lee, released under GPL

# Proof of concept implementation of NVDA Core issue 3208.
# Split from update check processes/procedure module.
# The purpose of this module is to define various update check protocol classes.
# An update protocol is a class that retrieves add-on updates from a specific source and format.
# For instance, an update protocol may work with an internal JSON dictionary
# or access multiple URL's to accomplish its task.
# Specifically, update check routines found in update proc module are now class methods.


from urllib.request import urlopen, Request
import threading
import json
import re
import ssl
from collections import namedtuple
import os
# NVDA 2023.1 includes concurrent.futures.
# A copy of the package minus process pool executor is included to suport older NVDA releases.
try:
	import concurrent.futures
except ModuleNotFoundError:
	import sys
	sys.path.append(os.path.dirname(__file__))
	import concurrent.futures
	sys.path.remove(os.path.dirname(__file__))
import addonHandler
import globalVars
from logHandler import log
from .urls import URLs
from . import addonUtils
addonHandler.initTranslation()


def getUrlViaMSEdgeUserAgent(url):
	# Some hosting services block Python/urllib in hopes of avoding bots.
	# Therefore spoof the user agent to say this is latest Microsoft Edge.
	# Source: Stack Overflow, Google searches on Apache/mod_security
	return Request(
		url,
		headers={
			"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36 Edg/105.0.1343.42"  # NOQA: E501
		}
	)


# Define various add-on update check protocols, beginning with protocol 0 (do nothing/abstract protocol).
class AddonUpdateCheckProtocol(object):
	"""Protocol 0: the default update check protocol.
	The purpose of this class is to provide base services and implementation for other protocols.
	While this protocol can be instantiated, subclasses (other protocols) should be used
	as this protocol does nothing when checking for add-on updates.
	"""

	protocol = 0
	protocolName = "base"
	protocolDescription = "No add-on updates"
	sourceUrl = ""

	def getAddonsData(self, url=None, differentUserAgent=False, errorText=None):
		"""Accesses and returns add-ons data from a predefined add-on source URL.
		As this function blocks the main thread, it should be run from a separate thread.
		The ideal way is for this thread to be concurrent with the calling thread.
		With concurrent.futures, this method becomes a "promise" i.e. returns whatever value requested by
		a "future" object without blocking threads.
		Subclasses can override this method to access sources not using JSON format or for other reasons.
		differentUserAgent: used to report a user agent other than Python as some websites block Python.
		errorText: logs specified text to the NVDA log.
		"""
		if url is None:
			url = self.sourceUrl
		if differentUserAgent:
			url = getUrlViaMSEdgeUserAgent(url)
		if errorText is None:
			errorText = "nvda3208: errors occurred while retrieving add-ons data"
		res = None
		try:
			res = urlopen(url)
		except IOError as e:
			# SSL issue (seen in NVDA Core earlier than 2014.1).
			if isinstance(e.strerror, ssl.SSLError) and e.strerror.reason == "CERTIFICATE_VERIFY_FAILED":
				addonUtils._updateWindowsRootCertificates()
				res = urlopen(url)
			else:
				# Inform results dictionary that an error has occurred as this is running inside a thread.
				log.debug(errorText, exc_info=True)
				raise
		finally:
			# Contents will be gone when the connection is closed, so save it in JSON format.
			if res is not None:
				results = json.load(res)
				res.close()
		return results

	def addonCompatibleAccordingToMetadata(self, addon, addonMetadata):
		"""Checks if a given add-on update is compatible with the running version of NVDA.
		"""
		# Check add-on update eligibility with help from community add-ons metadata if present.
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

	def getAddonDownloadLink(self, url):
		"""If the source URL does not end in a '.nvda-addon' extension, obtains the actual download link
		by accessing the URL specified in the 'url' parameter.
		This is similar to get add-ons data method except it is optimized to obtain a URL, not results data.
		"""
		res = None
		addonUrl = None
		req = getUrlViaMSEdgeUserAgent(url)
		try:
			res = urlopen(req)
		except IOError as e:
			# SSL issue (seen in NVDA Core earlier than 2014.1).
			if isinstance(e.strerror, ssl.SSLError) and e.strerror.reason == "CERTIFICATE_VERIFY_FAILED":
				addonUtils._updateWindowsRootCertificates()
				res = urlopen(req)
			else:
				pass
		finally:
			if res is not None and res.code == 200:
				addonUrl = res.url
				res.close()
		return addonUrl

	def checkForAddonUpdate(self, curAddons):
		"""Coordinates add-on update check facility based on update records provided.
		After retrieving add-on update metadata from sources, fetch update info is called on each record
		to see if updates are available, returning a list of updatable add-on records.
		Subclasses must implement this method.
		"""
		raise NotImplementedError

	def checkForAddonUpdates(self, installedAddons=None):
		"""Checks and returns add-on update metadata (update records) if any.
		Update record includes name, summary, update URL, compatibility information and other attributes.
		In some cases, a list of preliminary update records based on instaled add-ons will be used.
		Note that in this case, all installed add-ons will be subject to update checks.
		Subclasses can override this method.
		"""
		# Don't even think about update checks if secure mode flag is set.
		if globalVars.appArgs.secure:
			return
		# Update record class is defined in update proc module, so import it here to avoid circular import.
		from .addonUpdateProc import AddonUpdateRecord
		# Build a list of preliminary update records based on installed add-ons.
		if installedAddons is not None:
			curAddons = installedAddons
		else:
			curAddons = []
			for addon in addonHandler.getAvailableAddons():
				manifest = addon.manifest
				name = addon.name
				curVersion = manifest["version"]
				# Check different channels if appropriate.
				updateChannel = manifest.get("updateChannel")
				if updateChannel == "None":
					updateChannel = None
				if updateChannel != "dev" and name in addonUtils.updateState["devUpdates"]:
					updateChannel = "dev"
				elif updateChannel == "dev" and name not in addonUtils.updateState["devUpdates"]:
					updateChannel = None
				# Note that version (update) and installed version will be the same for now.
				curAddons.append(AddonUpdateRecord(
					name=name,
					summary=manifest["summary"],
					version=curVersion,
					installedVersion=curVersion,
					updateChannel=updateChannel
				))
		try:
			info = self.checkForAddonUpdate(curAddons)
		except:
			# Present an error dialog if manual add-on update check is in progress.
			raise RuntimeError("Cannot check for community add-on updates")
		return info


# For use in update check protocol 1.
# Record add-on names to URL keys hosted on community add-ons website.
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


class AddonUpdateCheckProtocolNVDAProject(AddonUpdateCheckProtocol):
	"""Protocol 1: NV Access community add-ons website protocol.
	This protocol uses community add-ons get.php JSON to construct update metadata.
	No compatibility range check is possible with this protocol.
	This resembles Add-on Updater 21.05 and earlier.
	"""

	protocol = 1
	protocolName = "nvdaproject"
	protocolDescription = "NVDA Community Add-ons website"
	sourceUrl = URLs.communityAddonsList

	def parseAddonVersionFromUrl(self, url, addon, fallbackVersion=None):
		"""Parses add-on version from the given URL.
		It can return a fallback version if told to do so.
		A copy of the add-on update record is used to access its attributes such as name.
		"""
		# All the info we need for add-on version check is after the last slash.
		# Sometimes, regular expression fails, and if so, treat it as though there is no update for this add-on.
		try:
			version = re.search(
				"(?P<name>)-(?P<version>.*).nvda-addon", url.split("/")[-1]
			).groupdict()["version"]
		except:
			log.debug("nvda3208: could not retrieve version info for an add-on from its URL", exc_info=True)
			return fallbackVersion
		# If hosted on places other than add-ons server, an unexpected URL might be returned, so parse this further.
		if addon.name in version:
			version = version.split(addon.name)[1][1:]
		return version

	def fetchAddonInfo(self, addon, results):
		# Borrowed ideas from NVDA Core.
		# Obtain update status for add-ons returned from community add-ons website.
		# Use threads for opening URL's in parallel, resulting in faster update check response on multicore systems.
		# This is the case when it becomes necessary to open another website.
		# Not all released add-ons are recorded in names to URLs dictionary.
		try:
			addonKey = names2urls[addon.name]
		except KeyError:
			return
		# If "-dev" flag is on, switch to development channel if it exists.
		channel = addon.updateChannel
		if channel is not None:
			addonKey += "-" + channel
		try:
			addonUrl = results[addonKey]
		except:
			return
		# Necessary duplication if the URL doesn't end in ".nvda-addon".
		# Some add-ons require traversing another URL.
		if ".nvda-addon" not in addonUrl:
			with concurrent.futures.ThreadPoolExecutor(max_workers=2) as urlGetter:
				addonUrl = urlGetter.submit(self.getAddonDownloadLink, addonUrl).result()
			if addonUrl is None:
				return
		# Note that some add-ons are hosted on community add-ons server directly.
		if "/" not in addonUrl:
			addonUrl = f"{URLs.communityHostedFile}{addonUrl}"
		# Announce add-on URL for debugging purposes.
		log.debug(f"nvda3208: add-on URL is {addonUrl}")
		# Update add-on update record if there is indeed a new version.
		# This applies to add-on URL's coming from external sources.
		# Fall back to installed version as update record will compare versions.
		version = self.parseAddonVersionFromUrl(addonUrl, addon, fallbackVersion=addon.installedVersion)
		addon.version = version
		addon.url = addonUrl

	def checkForAddonUpdate(self, curAddons, fallbackData=None):
		# First, fetch current community add-ons.
		results = None
		# Only do this if no fallback data is specified.
		if fallbackData is None:
			with concurrent.futures.ThreadPoolExecutor(max_workers=2) as addonsFetcher:
				try:
					results = addonsFetcher.submit(
						self.getAddonsData,
						errorText="nvda3208: errors occurred while retrieving community add-ons"
					).result()
				except:
					raise RuntimeError("Failed to retrieve community add-ons")
		# Perhaps a newer protocol sent a fallback data if the protocol URL fails somehow.
		else:
			results = fallbackData
		# Retrieve add-on update data results.
		updateThreads = [
			threading.Thread(target=self.fetchAddonInfo, args=(addon, results))
			for addon in curAddons
		]
		for thread in updateThreads:
			thread.start()
		for thread in updateThreads:
			thread.join()
		# Build an update info list based on update availability.
		return [
			addon for addon in curAddons
			if addon.updateAvailable
		]


class AddonUpdateCheckProtocolNVDAAddonsGitHub(AddonUpdateCheckProtocolNVDAProject):
	"""Protocol 2.x: NVDA community add-ons website with compatibility information supplied by the community.
	This protocol uses a combination of community add-ons get.php JSON
	and compatibility data provided by the community.
	While similar to protocol 1, addons.nvda-project.org JSON is consulted only to retrieve download links.
	Version and compatibility range (minimum and last tested NVDA versions) checks are possible.
	Later iterations add hash value checks.
	This resembles Add-on Updater 21.07 and later and is the default protocol.
	Protocol 2.0 (original implementation) uses an older version of the compatibility JSON that
	relies on NV Access get.php JSON representation for obtaining links,
	whereas protocol 2.1 (2022) uses additional fields such as URL and hash provided by the JSON
	and is the default protocol in Add-on Updater 22.09 and later.
	Protocol 2.2 enables minimum Windows version checks and rewrites add-ons metadata fetcher to use concurrent.futures instead of separate threads,
	and is the default protocol in Add-on Updater 23.01.
	"""

	protocol = 2
	protocolName = "nvdaprojectcompatinfo"
	protocolDescription = "NVDA Community Add-ons website with compatibility information"
	sourceUrl = URLs.metadata
	sourceList = URLs.communityAddonsList

	def fetchAddonInfo(self, addon, results, addonsData):
		# Borrowed ideas from NVDA Core.
		# Obtain update status for add-ons returned from community add-ons website.
		# Use threads for opening URL's in parallel, resulting in faster update check response on multicore systems.
		# This is the case when it becomes necessary to open another website.
		# Also, check add-on update eligibility based on what community add-ons metadata says if present.
		# Is this add-on's metadata present? If not, update check cannot proceed.
		try:
			addonMetadata = addonsData["active"][addon.name]
		except KeyError:
			return
		# Add-ons metadata includes addon key in active/addonName/addonKey.
		addonKey = addonMetadata.get("addonKey")
		# Can the add-on be updated based on community add-ons metadata?
		if not self.addonCompatibleAccordingToMetadata(addon.name, addonMetadata):
			return
		# Compare minimum versus current Windows releases if defined.
		minWinVersion = addonMetadata.get("minimumWindowsVersion")
		if minWinVersion is not None:
			import winVersion
			curWinVersion = winVersion.getWinVer()
			curWinVersion = tuple((curWinVersion.major, curWinVersion.minor, curWinVersion.build))
			minWinVersion = addonMetadata["minimumWindowsVersion"].split(".")
			minWinVersion = tuple(int(part) for part in minWinVersion)
			if curWinVersion < minWinVersion:
				return
		# If "-dev" flag is on, switch to development channel if it exists.
		channel = addon.updateChannel
		if channel is not None:
			addonKey += "-" + channel
		# Update info (channels) data was added in 2022 to house downlo link, hashes and others.
		# Fall back to checking results data if update channels key does not exist.
		updateChannels = addonMetadata.get("updateChannels")
		if updateChannels is None:
			try:
				addonUrl = results[addonKey]
			except:
				return
		else:
			try:
				addonUrl = updateChannels[addonKey]["url"]
			except:
				try:
					addonUrl = results[addonKey]
				except:
					return
		# Necessary duplication if the URL doesn't end in ".nvda-addon".
		# Some add-ons require traversing another URL.
		if ".nvda-addon" not in addonUrl:
			with concurrent.futures.ThreadPoolExecutor(max_workers=1) as urlGetter:
				addonUrl = urlGetter.submit(self.getAddonDownloadLink, addonUrl).result()
			if addonUrl is None:
				return
		# Note that some add-ons are hosted on community add-ons server directly.
		if "/" not in addonUrl:
			addonUrl = f"{URLs.communityHostedFile}{addonUrl}"
		# Announce add-on URL for debugging purposes.
		log.debug(f"nvda3208: add-on URL is {addonUrl}")
		# This applies to add-on URL's coming from external sources.
		# Fall back to installed version as update record will compare versions.
		version = self.parseAddonVersionFromUrl(addonUrl, addon, fallbackVersion=addon.installedVersion)
		addon.version = version
		addon.url = addonUrl
		# Add SHA256 hash value for add-on package if it exists.
		if updateChannels is not None:
			addon.hash = updateChannels[addonKey].get("sha256")

	def checkForAddonUpdate(self, curAddons, fallbackData=None):
		# NVDA community add-ons list is always retrieved for fallback reasons.
		# It is also supposed to be the first fallback collection.
		results = None
		# Enhanced with add-on metadata such as compatibility info maintained by the community.
		addonsData = None
		# Obtain both at once through concurrency.
		with concurrent.futures.ThreadPoolExecutor(max_workers=2) as addonsFetcher:
			protocol1 = addonsFetcher.submit(
				self.getAddonsData, url=self.sourceList,
				errorText="nvda3208: errors occurred while retrieving community add-ons"
			)
			protocol2 = addonsFetcher.submit(
				self.getAddonsData,
				errorText="nvda3208: errors occurred while retrieving community add-ons metadata"
			)
			# Obtain community add-ons metadata (protocol 2) first.
			try:
				addonsData = protocol2.result()
			except:
				# Prepare to fall back to add-ons list if metadata is unusable.
				pass
			try:
				results = protocol1.result()
			except:
				# Cannot retrieve add-on updates at this time.
				if fallbackData is None:
					raise RuntimeError("Failed to retrieve community add-ons")
				else:
					results = fallbackData
		# Fallback to add-ons list if metadata is unusable.
		if addonsData is None:
			log.debug("nvda3208: add-ons metadata unusable, using add-ons list from community add-ons website")
			# Resort to using protocol 1.
			return AddonUpdateCheckProtocolNVDAProject().checkForAddonUpdate(curAddons, fallbackData=results)
		else:
			log.debug("nvda3208: add-ons metadata successfully retrieved")
		# Don't forget to perform additional checks based on add-on metadata if present.
		updateThreads = [
			threading.Thread(
				target=self.fetchAddonInfo, args=(addon, results, addonsData)
			)
			for addon in curAddons
		]
		for thread in updateThreads:
			thread.start()
		for thread in updateThreads:
			thread.join()
		# Build an update info list based on update availability.
		return [
			addon for addon in curAddons
			if addon.updateAvailable
		]


class AddonUpdateCheckProtocolNVDAEs(AddonUpdateCheckProtocol):
	"""Protocol 3: Spanish community add-ons catalog protocol
	In addition to community add-ons website, NVDA Spanish community hosts add-ons data.
	Version, compatibility, and update channel checks are available.
	Unlike other protocols, results data is a list, not a dictionary.
	"""

	protocol = 3
	protocolName = "nvdaes"
	protocolDescription = "NVDA Spanish Community Add-ons website"
	sourceUrl = "https://nvda.es/files/get.php?addonslist"

	def fetchAddonInfo(self, addon, results):
		# Spanish community catalog contains version, channel, URL, and compatibility information.
		# This eliminates the need to access additional sources just for obtaining data.
		# Is this add-on's metadata present?
		# Without this, update checking is impossible.
		if addon.name not in results:
			return
		# Compatibility, version, and URL are recorded as entries inside links list grouped by channel.
		# Stable channel is recorded as "stable".
		channel = addon.updateChannel
		if channel is None:
			channel = "stable"
		channelEntries = results[addon.name]["links"]
		# Assume at least one update channel exists.
		addonMetadata = channelEntries[0]
		for entry in channelEntries:
			if entry["channel"] == channel:
				addonMetadata = entry
				break
		# Can the add-on be updated based on community add-ons metadata?
		# What if a different update channel must be used if the stable channel update is not compatible?
		# Compatibility information must be converted from strings to integer tuple.
		addonMetadata["minimumNVDAVersion"] = tuple(
			int(component) for component in addonMetadata["minimum"].split(".")
		)
		addonMetadata["lastTestedNVDAVersion"] = tuple(
			int(component) for component in addonMetadata["lasttested"].split(".")
		)
		if not self.addonCompatibleAccordingToMetadata(addon.name, addonMetadata):
			return
		addonUrl = addonMetadata["link"]
		# Announce add-on URL for debugging purposes.
		log.debug(f"nvda3208: add-on URL is {addonUrl}")
		# Necessary duplication if the URL doesn't end in ".nvda-addon".
		# Some add-ons require traversing another URL.
		if ".nvda-addon" not in addonUrl:
			with concurrent.futures.ThreadPoolExecutor(max_workers=1) as urlGetter:
				addonUrl = urlGetter.submit(self.getAddonDownloadLink, addonUrl).result()
			if addonUrl is None:
				return
		version = addonMetadata["version"]
		addon.version = version
		addon.url = addonUrl

	def checkForAddonUpdate(self, curAddons, fallbackData=None):
		results = None
		# Only do this if no fallback data is specified.
		if fallbackData is None:
			with concurrent.futures.ThreadPoolExecutor(max_workers=1) as addonsFetcher:
				try:
					results = addonsFetcher.submit(
						self.getAddonsData, differentUserAgent=True,
						errorText="nvda3208: errors occurred while retrieving Spanish community add-ons catalog"
					).result()
				except:
					# Raise an error if results says so.
					raise RuntimeError("Failed to retrieve community add-ons")
		# Perhaps a newer protocol sent a fallback data if the protocol URL fails somehow.
		else:
			results = fallbackData
		# Transform results dictionary inside results key to proper update dictionary.
		# Spanish community catalog uses add-on ID's (integer) as opposed to name string.
		# Therefore, metadata inside ID's will be stored under add-on name.
		metadataDictionary = {}
		for addon in results:
			metadataDictionary[addon["name"]] = addon
		updateThreads = [
			threading.Thread(target=self.fetchAddonInfo, args=(addon, metadataDictionary))
			for addon in curAddons
		]
		for thread in updateThreads:
			thread.start()
		for thread in updateThreads:
			thread.join()
		# Build an update info list based on update availability.
		return [
			addon for addon in curAddons
			if addon.updateAvailable
		]


class AddonUpdateCheckProtocolNVDACn(AddonUpdateCheckProtocolNVDAAddonsGitHub):
	"""Protocol 5: China community add-ons catalog protocol
	Protocol 5 is same as protocol 2, except for the update source URL.
	So this class inherit from AddonUpdateCheckProtocolNVDAAddonsGitHub class and modified its sourceUrl/sourceList attribute.
	"""

	protocol = 5
	protocolName = "nvdacn"
	protocolDescription = "NVDA China Community Add-ons"
	sourceUrl = "https://www.nvdacn.com/usr/uploads/addonsData.json"
	sourceList = "https://www.nvdacn.com/usr/uploads/addonsUrl.json"


class AddonUpdateCheckProtocolNVDATw(AddonUpdateCheckProtocolNVDAAddonsGitHub):
	"""Protocol 6: Taiwan community add-ons catalog protocol
	Protocol 6 is same as protocol 2, except for the update source URL.
	So this class inherit from AddonUpdateCheckProtocolNVDAAddonsGitHub class and modified its sourceUrl/sourceList attribute.
	"""

	protocol = 6
	protocolName = "nvdatw"
	protocolDescription = "NVDA Taiwan Community Add-ons"
	sourceUrl = "https://accessibility.twvip.org/addonsData.json"
	sourceList = "https://accessibility.twvip.org/addonsUrl.json"


# Define available update protocols as a named tuple.
# Named tuples allow tuple fields (columns) to be index by attribute lookup syntax.
UpdateProtocol = namedtuple("UpdateProtocol", "key, protocol, description")
AvailableUpdateProtocols = (
	UpdateProtocol(
		# Translators: one of the add-on update source choices.
		"nvdaprojectcompatinfo", "AddonUpdateCheckProtocolNVDAAddonsGitHub", _("NVDA community add-ons website")
	),
	UpdateProtocol(
		# Translators: one of the add-on update source choices.
		"nvdaes", "AddonUpdateCheckProtocolNVDAEs", _("Spanish community add-ons catalog")
	),
	UpdateProtocol(
		# Translators: one of the add-on update source choices.
		"nvdacn", "AddonUpdateCheckProtocolNVDACn", _("China community add-ons catalog")
	),
	UpdateProtocol(
		# Translators: one of the add-on update source choices.
		"nvdatw", "AddonUpdateCheckProtocolNVDATw", _("Taiwan community add-ons catalog")
	)
)
