# Add-on update protocols
# Copyright 2022 Joseph Lee, released under GPL

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
			"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.64 Safari/537.36 Edg/101.0.1210.47"  # NOQA: E501
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

	def getAddonsData(self, results, url=None, differentUserAgent=False, errorText=None):
		"""Accesses and returns add-ons data from a predefined add-on source URL.
		As this function blocks the main thread, it should be run from a separate thread.
		Therefore, the results argument passed in should be a dictionary that can be accessed
		after calling join function on this thread.
		Dictionaries are used to return results in a variety of formats under a dedicated key
		as sources may use different representation such as lists and dictionaries.
		Subclasses can override this method to access sources not using JSON format or for other reasons.
		differentUserAgent: used to report a user agent other than Python as some websites block Python.
		errorText: logs specified text to the NVDA og.
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
				results["error"] = True
		finally:
			if res is not None:
				results["results"] = json.load(res)
				res.close()

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
		"""If the source URL does not end in a '.nvda-addon' extension, obtains the actual download ink
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
			addonUrl = self.getAddonDownloadLink(addonUrl)
			if addonUrl is None:
				return
		# Note that some add-ons are hosted on community add-ons server directly.
		if "/" not in addonUrl:
			addonUrl = f"https://addons.nvda-project.org/files/{addonUrl}"
		# Announce add-on URL for debugging purposes.
		log.debug(f"nvda3208: add-on URL is {addonUrl}")
		# Update add-on update record if there is indeed a new version.
		# This applies to add-on URL's coming from external sources.
		# Fall back to installed version as update record will compare versions.
		version = self.parseAddonVersionFromUrl(addonUrl, addon, fallbackVersion=addon.installedVersion)
		addon.version = version
		addon.url = addonUrl

	def checkForAddonUpdate(self, curAddons, fallbackData=None):
		# First, fetch current community add-ons via an internal thread.
		results = {}
		# Only do this if no fallback data is specified.
		if fallbackData is None:
			addonsFetcher = threading.Thread(
				target=self.getAddonsData,
				args=(results,),
				kwargs={
					"errorText": "nvda3208: errors occurred while retrieving community add-ons"
				}
			)
			addonsFetcher.start()
			# This internal thread must be joined, otherwise results will be lost.
			addonsFetcher.join()
			# Raise an error if results says so.
			if "error" in results:
				raise RuntimeError("Failed to retrieve community add-ons")
		# Perhaps a newer protocol sent a fallback data if the protocol URL fails somehow.
		else:
			results = fallbackData
		# Retrieve results from "results" key found in the dictionary.
		updateThreads = [
			threading.Thread(target=self.fetchAddonInfo, args=(addon, results["results"]))
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
	"""Protocol 2: NVDA community add-ons website with compatibility information supplied by the community.
	This protocol uses a combination of community add-ons get.php JSON
	and compatibility data provided by the community.
	While similar to protocol 1, addons.nvda-project.org JSON is consulted only to retrieve download links.
	Version and compatibility range (minimum and last tested NVDA versions) checks are possible.
	This resembles Add-on Updater 21.07 and later and is the default protocol.
	"""

	protocol = 2
	protocolName = "nvdaprojectcompatinfo"
	protocolDescription = "NVDA Community Add-ons website with compatibility information"
	sourceUrl = URLs.metadata

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
			addonUrl = self.getAddonDownloadLink(addonUrl)
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

	def checkForAddonUpdate(self, curAddons, fallbackData=None):
		# NVDA community add-ons list is always retrieved for fallback reasons.
		# It is also supposed to be the first fallback collection.
		results = {}
		if fallbackData is None:
			addonsFetcher = threading.Thread(
				target=self.getAddonsData,
				args=(results,),
				kwargs={
					"url": URLs.communityAddonsList,
					"errorText": "nvda3208: errors occurred while retrieving community add-ons"
				}
			)
			addonsFetcher.start()
			# This internal thread must be joined, otherwise results will be lost.
			addonsFetcher.join()
			# Raise an error if results says so.
			if "error" in results:
				raise RuntimeError("Failed to retrieve community add-ons")
		else:
			results = fallbackData
		# Enhanced with add-on metadata such as compatibility info maintained by the community.
		addonsData = {}
		addonsFetcher = threading.Thread(
			target=self.getAddonsData,
			args=(addonsData,),
			kwargs={
				"errorText": "nvda3208: errors occurred while retrieving community add-ons metadata"
			}
		)
		addonsFetcher.start()
		# Just like the earlier thread, this thread too must be joined.
		addonsFetcher.join()
		# Fallback to add-ons list if metadata is unusable.
		if "error" in addonsData:
			addonsData.clear()
		# Results are stored in "results" key.
		if len(addonsData["results"]) == 0:
			log.debug("nvda3208: add-ons metadata unusable, using add-ons list from community add-ons website")
			# Resort to using protocol 1.
			return AddonUpdateCheckProtocolNVDAProject().checkForAddonUpdate(curAddons, fallbackData=results)
		else:
			log.debug("nvda3208: add-ons metadata successfully retrieved")
		# Don't forget to perform additional checks based on add-on metadata if present.
		updateThreads = [
			threading.Thread(
				target=self.fetchAddonInfo, args=(addon, results["results"], addonsData["results"])
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
			addonUrl = self.getAddonDownloadLink(addonUrl)
			if addonUrl is None:
				return
		version = addonMetadata["version"]
		addon.version = version
		addon.url = addonUrl

	def checkForAddonUpdate(self, curAddons, fallbackData=None):
		results = {}
		# Only do this if no fallback data is specified.
		if fallbackData is None:
			addonsFetcher = threading.Thread(
				target=self.getAddonsData,
				args=(results,),
				kwargs={
					"differentUserAgent": True,
					"errorText": "nvda3208: errors occurred while retrieving Spanish community add-ons catalog"
				}
			)
			addonsFetcher.start()
			# This internal thread must be joined, otherwise results will be lost.
			addonsFetcher.join()
			# Raise an error if results says so.
			if "error" in results:
				raise RuntimeError("Failed to retrieve community add-ons")
		# Perhaps a newer protocol sent a fallback data if the protocol URL fails somehow.
		else:
			results = fallbackData
		# Transform results dictionary inside results key to proper update dictionary.
		# Spanish community catalog uses add-on ID's (integer) as opposed to name string.
		# Therefore, metadata inside ID's will be stored under add-on name.
		metadataDictionary = {}
		for addon in results["results"]:
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


class AddonUpdateCheckProtocolNVAccessDatastore(AddonUpdateCheckProtocol):
	"""Protocol 4: NV Access add-ons datastore protocol
	NV Access has reimagined the add-ons metadata storage mechanics.
	Due to similarities, this protocol borrows ideas from Spanish community catalog protocol.
	Version, compatibility, and update channel checks are available.
	Just like Spanish community catalog, results data is a list, not a dictionary.
	"""

	protocol = 4
	protocolName = "nvaccessdatastore"
	protocolDescription = "NV Access add-ons datastore"
	sourceUrl = "https://www.nvaccess.org/addonStore"

	def fetchAddonInfo(self, addon, results):
		# NV Access datastore contains version, channel, URL, and compatibility information.
		# This eliminates the need to access additional sources just for obtaining data.
		# Unlike other protocols, NV Access datastore returns add-ons compatible with the currentNVDA version only.
		# Because versions for all update channels can be returned, make sure
		# it records add-on name of the form "name-channel".
		# Is this add-on's metadata present?
		# Without this, update checking is impossible.
		# Stable channel is recorded as "stable".
		channel = addon.updateChannel
		if channel is None:
			channel = "stable"
		metadataTag = f"{addon.name}-{channel}"
		try:
			addonMetadata = results[metadataTag]
		except KeyError:
			return
		addonUrl = addonMetadata["URL"]
		# Announce add-on URL for debugging purposes.
		log.debug(f"nvda3208: add-on URL is {addonUrl}")
		version = addonMetadata["addonVersionName"]
		addon.version = version
		addon.url = addonUrl

	def checkForAddonUpdate(self, curAddons, fallbackData=None):
		results = {}
		# Only do this if no fallback data is specified.
		if fallbackData is None:
			# URL is of the form https://www.nvaccess.org/addonStore/<language>/all/<NVDA API Version>.json,
			# in this case sourceUrl/<language>/all/<NVDA API Version>.json,
			# Use English (en) for language and current nVDA release for version.
			import versionInfo
			nvdaVer = f"{versionInfo.version_year}.{versionInfo.version_major}.{versionInfo.version_minor}"
			url = f"{self.sourceUrl}/en/all/{nvdaVer}.json"
			addonsFetcher = threading.Thread(
				target=self.getAddonsData,
				args=(results,),
				kwargs={
					"url": url,
					"differentUserAgent": True,
					"errorText": "nvda3208: errors occurred while accessing NV Access datastore"
				}
			)
			addonsFetcher.start()
			# This internal thread must be joined, otherwise results will be lost.
			addonsFetcher.join()
			# Raise an error if results says so.
			if "error" in results:
				raise RuntimeError("Failed to retrieve community add-ons")
		# Perhaps a newer protocol sent a fallback data if the protocol URL fails somehow.
		else:
			results = fallbackData
		# Transform results dictionary inside results key to proper update dictionary.
		# NV Access datastore uses addonId string.
		# It may also return two or more metadata records for the same add-on depending on update channel.
		# Therefore, add-on name will be of the form "name-channel".
		# In reality, no need for a separate fetch ad-on info method as version check can be done here
		# as all that's needed is check version-channel while looping through results list.
		# However, call fetch add-on info for backward compatibility and consistency with other protocols.
		metadataDictionary = {}
		for addon in results["results"]:
			addonId = addon["addonId"]
			channel = addon["channel"]
			metadataTag = f"{addonId}-{channel}"
			metadataDictionary[metadataTag] = addon
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
	)
)
