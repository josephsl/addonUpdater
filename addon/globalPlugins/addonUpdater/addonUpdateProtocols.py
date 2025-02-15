# Add-on update protocols
# Copyright 2022-2024 Joseph Lee, released under GPL version 2

# Proof of concept implementation of NVDA Core issue 3208.
# Split from update check processes/procedure module.
# The purpose of this module is to define various update check protocol classes.
# An update protocol is a class that retrieves add-on updates from a specific source and format.
# For instance, an update protocol may work with an internal JSON dictionary
# or access multiple URL's to accomplish its task.
# Specifically, update check routines found in update proc module are now class methods.


from urllib.request import urlopen, Request
import json
import re
from collections import namedtuple
from typing import Optional, Any, Dict, List
import concurrent.futures
import addonHandler
import globalVars
from logHandler import log
from . import addonUtils
from .addonUpdateLegacyProtocols import AddonUpdateCheckProtocolNVDAAddonsGitHub

# To provide type information
from .addonUpdateProc import AddonUpdateRecord

addonHandler.initTranslation()


def getUrlViaMSEdgeUserAgent(url: str) -> Request:
	# Some hosting services block Python/urllib in hopes of avoding bots.
	# Therefore spoof the user agent to say this is latest Microsoft Edge.
	# Source: Stack Overflow, Google searches on Apache/mod_security
	return Request(
		url,
		headers={
			"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 Edg/132.0.2957.55"  # NOQA: E501
		},
	)


# Type alias for type information purposes and to shorten long lines involving ad-on update records
AddonUpdateRecords = List[AddonUpdateRecord]


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

	def getAddonsData(
		self, url: Any = None, differentUserAgent: bool = False, errorText: Optional[str] = None
	) -> Any:
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
		except Exception:
			# Inform results dictionary that an error has occurred as this is running inside a thread.
			log.debug(errorText, exc_info=True)
			raise
		finally:
			# Contents will be gone when the connection is closed, so save it in JSON format.
			if res is not None:
				results = json.load(res)
				res.close()
		return results

	def addonCompatibleAccordingToMetadata(self, addon: str, addonMetadata: Dict[str, Any]) -> bool:
		"""Checks if a given add-on update is compatible with the running version of NVDA."""
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

	def getAddonDownloadLink(self, url: str) -> Optional[str]:
		"""If the source URL does not end in a '.nvda-addon' extension, obtains the actual download link
		by accessing the URL specified in the 'url' parameter.
		This is similar to get add-ons data method except it is optimized to obtain a URL, not results data.
		"""
		res = None
		addonUrl = None
		req = getUrlViaMSEdgeUserAgent(url)
		try:
			res = urlopen(req)
		except Exception:
			pass
		finally:
			if res is not None and res.code == 200:
				addonUrl = res.url
				res.close()
		return addonUrl

	def parseAddonVersionFromUrl(self, url: str, addon: AddonUpdateRecord, fallbackVersion: str = "") -> str:
		"""Parses add-on version from the given URL.
		It can return a fallback version if told to do so, which is instaled add-on version by default.
		A copy of the add-on update record is used to access its attributes such as name.
		"""
		if not fallbackVersion:
			fallbackVersion = addon.installedVersion
		# All the info we need for add-on version check is after the last slash.
		# Sometimes, regular expression fails, and if so, treat it as though there is no update for this add-on.
		try:
			versionMatched = re.search("(?P<name>)-(?P<version>.*).nvda-addon", url.split("/")[-1])
		except Exception:
			log.debug("nvda3208: could not retrieve version info for an add-on from its URL", exc_info=True)
			return fallbackVersion
		if versionMatched is None:
			log.debug("nvda3208: could not retrieve version info for an add-on from its URL")
			return fallbackVersion
		version = versionMatched.groupdict()["version"]
		# If hosted on places other than add-ons repos, an unexpected URL might be returned, so parse this further.
		if addon.name in version:
			version = version.split(addon.name)[1][1:]
		return version

	def checkForAddonUpdate(self, curAddons: AddonUpdateRecords) -> AddonUpdateRecords:
		"""Coordinates add-on update check facility based on update records provided.
		After retrieving add-on update metadata from sources, fetch update info is called on each record
		to see if updates are available, returning a list of updatable add-on records.
		Subclasses must implement this method.
		"""
		raise NotImplementedError

	def checkForAddonUpdates(
		self, installedAddons: Optional[AddonUpdateRecords] = None
	) -> Optional[AddonUpdateRecords]:
		"""Checks and returns add-on update metadata (update records) if any.
		Update record includes name, summary, update URL, compatibility information and other attributes.
		In some cases, a list of preliminary update records based on instaled add-ons will be used.
		Note that in this case, all installed add-ons will be subject to update checks.
		Subclasses can override this method.
		"""
		# Don't even think about update checks if secure mode flag is set.
		if globalVars.appArgs.secure:
			return None
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
				if name in addonUtils.updateState["devUpdates"]:
					# For prerelease builds, dev channel is set as default.
					updateChannel = addonUtils.updateState["devUpdateChannels"].get(name, "dev")
				else:
					updateChannel = None
				# Note that version (update) and installed version will be the same for now.
				curAddons.append(
					AddonUpdateRecord(
						name=name,
						summary=manifest["summary"],
						version=curVersion,
						installedVersion=curVersion,
						updateChannel=updateChannel,
					)
				)
		try:
			info = self.checkForAddonUpdate(curAddons)
		except Exception:
			# Present an error dialog if manual add-on update check is in progress.
			raise RuntimeError("Cannot check for community add-on updates")
		return info


# Protocols 1 and 2 are legacy (see legacy protocols module).


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

	def fetchAddonInfo(self, addon: AddonUpdateRecord, results: Dict[str, Any]) -> None:
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

	def checkForAddonUpdate(
		self, curAddons: AddonUpdateRecords, fallbackData: Any = None
	) -> AddonUpdateRecords:
		results = None
		# Only do this if no fallback data is specified.
		if fallbackData is None:
			with concurrent.futures.ThreadPoolExecutor(max_workers=1) as addonsFetcher:
				try:
					results = addonsFetcher.submit(
						self.getAddonsData,
						differentUserAgent=True,
						errorText="nvda3208: errors occurred while retrieving Spanish community add-ons catalog",
					).result()
				except Exception:
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
		for addon in curAddons:
			self.fetchAddonInfo(addon, metadataDictionary)
		# Build an update info list based on update availability.
		return [addon for addon in curAddons if addon.updateAvailable()]


class AddonUpdateCheckProtocolNVAccessDatastore(AddonUpdateCheckProtocol):
	"""Protocol 4: NV Access add-ons datastore protocol
	NV Access has reimagined the add-ons metadata storage mechanics.
	Due to similarities, this protocol borrows ideas from Spanish community catalog protocol.
	Version, compatibility, hash, and update channel checks are available
	and is the default protocol in Add-on Updater 23.06.
	Just like Spanish community catalog, results data is a list, not a dictionary.
	Note: use NVDA's own add-on store user interface when updating add-ons.
	"""

	protocol = 4
	protocolName = "nvaccessdatastore"
	protocolDescription = "NV Access add-ons datastore"
	sourceUrl = "https://addonStore.nvaccess.org"

	def fetchAddonInfo(self, addon: AddonUpdateRecord, results: Dict[str, Any]) -> None:
		# NV Access datastore contains version, channel, URL, hash, and compatibility information.
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
		# Can the add-on be updated based on add-on store metadata?
		# Add-on store separates major.minor.patch to separate keys.
		# Data is already formatted as integers.
		addonMetadata["minimumNVDAVersion"] = tuple(addonMetadata["minNVDAVersion"].values())
		addonMetadata["lastTestedNVDAVersion"] = tuple(addonMetadata["lastTestedVersion"].values())
		if not self.addonCompatibleAccordingToMetadata(addon.name, addonMetadata):
			return
		addonUrl = addonMetadata["URL"]
		# Announce add-on URL for debugging purposes.
		log.debug(f"nvda3208: add-on URL is {addonUrl}")
		version = addonMetadata["addonVersionName"]
		# Temporarily set up version number attribute alongside version name.
		# Version name will be restored after update availability check.
		versionNumber = addonMetadata["addonVersionNumber"]
		addon.version = [version, (versionNumber["major"], versionNumber["minor"], versionNumber["patch"])]
		addon.url = addonUrl
		addon.hash = addonMetadata["sha256"]

	def checkForAddonUpdate(
		self, curAddons: AddonUpdateRecords, fallbackData: Any = None
	) -> AddonUpdateRecords:
		results = None
		# Only do this if no fallback data is specified.
		if fallbackData is None:
			# URL is of the form https://www.nvaccess.org/addonStore/<language>/all/<NVDA API Version>.json,
			# in this case sourceUrl/<language>/all/<NVDA API Version>.json,
			# Use English (en) for language, and in the future, current NVDA release for version.
			import versionInfo

			currentVersion = (
				f"{versionInfo.version_year}.{versionInfo.version_major}.{versionInfo.version_minor}"
			)
			url = f"{self.sourceUrl}/en/all/{currentVersion}.json"
			with concurrent.futures.ThreadPoolExecutor(max_workers=2) as addonsFetcher:
				try:
					results = addonsFetcher.submit(
						self.getAddonsData,
						url=url,
						differentUserAgent=True,
						errorText="nvda3208: errors occurred while accessing NV Access datastore",
					).result()
				except Exception:
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
		for addon in results:
			addonId = addon["addonId"]
			channel = addon["channel"]
			metadataTag = f"{addonId}-{channel}"
			metadataDictionary[metadataTag] = addon
		# Build an update info list based on update availability.
		# NV Access add-on datastore records version number (major.minor.patch) as a dictionary.
		addonUpdates = []
		for addon in curAddons:
			self.fetchAddonInfo(addon, metadataDictionary)
			# NV Access add-on datastore records version number (major.minor.patch) as a dictionary.
			try:
				version, versionNumber = addon.version
				# Restore version name string.
				addon.version = version
			except ValueError:
				# Add-on version remains a string if there is no entry for this add-on in the datastore.
				continue
			if addon.updateAvailable():
				addonUpdates.append(addon)
		return addonUpdates


class AddonUpdateCheckProtocolNVDACn(AddonUpdateCheckProtocolNVDAAddonsGitHub):
	"""Protocol 5: China community add-ons catalog protocol
	Protocol 5 is same as protocol 2, except for the update source URL.
	So this class inherits from AddonUpdateCheckProtocolNVDAAddonsGitHub class
	and modified its sourceUrl/sourceList attribute.
	"""

	protocol = 5
	protocolName = "nvdacn"
	protocolDescription = "NVDA China Community Add-ons"
	sourceUrl = "https://www.nvdacn.com/usr/uploads/addonsData.json"
	sourceList = "https://www.nvdacn.com/usr/uploads/addonsUrl.json"


class AddonUpdateCheckProtocolNVDATw(AddonUpdateCheckProtocolNVDAAddonsGitHub):
	"""Protocol 6: Taiwan community add-ons catalog protocol
	Protocol 6 is same as protocol 2, except for the update source URL.
	So this class inherits from AddonUpdateCheckProtocolNVDAAddonsGitHub class
	and modified its sourceUrl/sourceList attribute.
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
		"addondatastore",
		"AddonUpdateCheckProtocolNVAccessDatastore",
		# Translators: one of the add-on update source choices.
		_("NV Access add-on store"),
	),
	UpdateProtocol(
		"nvdaes",
		"AddonUpdateCheckProtocolNVDAEs",
		# Translators: one of the add-on update source choices.
		_("Spanish community add-ons catalog"),
	),
	UpdateProtocol(
		"nvdacn",
		"AddonUpdateCheckProtocolNVDACn",
		# Translators: one of the add-on update source choices.
		_("China community add-ons catalog"),
	),
	UpdateProtocol(
		"nvdatw",
		"AddonUpdateCheckProtocolNVDATw",
		# Translators: one of the add-on update source choices.
		_("Taiwan community add-ons catalog"),
	),
)
