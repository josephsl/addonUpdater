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
	"""The default update check protocol, also known as protocol 0.
	The purpose of this class is to provide a base implementation for other protocols.
	While this protocol can be instantiated, subclasses (other protocols) should be used.
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
		Subclasses can override this method.
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
				results.update(json.load(res))
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

	def checkForAddonUpdate(self, curAddons):
		"""Coordinates add-on update check facility based on update recorded provided.
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

	def fetchAddonInfo(self, addon, results):
		# Not all released add-ons are recorded in names to URLs dictionary.
		if addon.name not in names2urls:
			return
		# Borrowed ideas from NVDA Core.
		# Obtain update status for add-ons returned from community add-ons website.
		# Use threads for opening URL's in parallel, resulting in faster update check response on multicore systems.
		# This is the case when it becomes necessary to open another website.
		addonKey = names2urls[addon.name]
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
		# Update add-on update record if there is indeed a new version.
		# All the info we need for add-on version check is after the last slash.
		# Sometimes, regular expression fails, and if so, treat it as though there is no update for this add-on.
		try:
			version = re.search(
				"(?P<name>)-(?P<version>.*).nvda-addon", addonUrl.split("/")[-1]
			).groupdict()["version"]
		except:
			log.debug("nvda3208: could not retrieve version info for an add-on from its URL", exc_info=True)
			return
		# If hosted on places other than add-ons server, an unexpected URL might be returned, so parse this further.
		if addon.name in version:
			version = version.split(addon.name)[1][1:]
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
		addonKey = addonMetadata.get("addonKey") if addonMetadataPresent else None
		# If "-dev" flag is on, switch to development channel if it exists.
		channel = addon.updateChannel
		if channel is not None:
			addonKey += "-" + channel
		# Can the add-on be updated based on community add-ons metadata?
		# What if a different update channel must be used if the stable channel update is not compatible?
		if addonMetadataPresent:
			if not self.addonCompatibleAccordingToMetadata(addon.name, addonMetadata):
				return
		try:
			addonUrl = results[addonKey]
		except:
			return
		# Necessary duplication if the URL doesn't end in ".nvda-addon".
		# Some add-ons require traversing another URL.
		if ".nvda-addon" not in addonUrl:
			res = None
			req = getUrlViaMSEdgeUserAgent(f"{URLs.communityFileGetter}{addonKey}")
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
		# All the info we need for add-on version check is after the last slash.
		# Sometimes, regular expression fails, and if so, treat it as though there is no update for this add-on.
		try:
			version = re.search(
				"(?P<name>)-(?P<version>.*).nvda-addon", addonUrl.split("/")[-1]
			).groupdict()["version"]
		except:
			log.debug("nvda3208: could not retrieve version info for an add-on from its URL", exc_info=True)
			return
		# If hosted on places other than add-ons server, an unexpected URL might be returned, so parse this further.
		if addon.name in version:
			version = version.split(addon.name)[1][1:]
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
		if len(addonsData) == 0:
			log.debug("nvda3208: add-ons metadata unusable, using add-ons list from community add-ons website")
			# Resort to using protocol 1.
			return AddonUpdateCheckProtocolNVDAProject().checkForAddonUpdate(curAddons, fallbackData=results)
		else:
			log.debug("nvda3208: add-ons metadata successfully retrieved")
		# Don't forget to perform additional checks based on add-on metadata if present.
		updateThreads = [
			threading.Thread(target=self.fetchAddonInfo, args=(addon, results, addonsData))
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

	def getAddonsData(self, results, url=None, differentUserAgent=False, errorText=None):
		"""Unlike other protocols, json data is a list, not a dictionary.
		Therefore do return a dictionary with results stored inside a key.
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

	def fetchAddonInfo(self, addon, results):
		# Spanish community catalog contains version, channel, URL, and compatibility information.
		# This eliminates the need to access additional sources just for obtaining data.
		# Is this add-on's metadata present?
		# Without this, update checking is impossible.
		addonMetadataPresent = addon.name in results
		if not addonMetadataPresent:
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
			res = None
			req = getUrlViaMSEdgeUserAgent(addonUrl)
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
