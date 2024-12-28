# Add-on Updater
# Copyright 2018-2024 Joseph Lee, released under GPL version 2.

import pickle
import os
import globalVars
import winVersion


# Not all features are supported on older Windows releases or on specific configurations.
# Set state flags to specific values based on condition check functions.
def isClientOS() -> bool:
	return winVersion.getWinVer().productType == "workstation"


def isAddonStorePresent() -> bool:
	# NVDA 2023.2 comes with add-on store GUI command with add-ons manager command as an alias for it.
	import gui

	return hasattr(gui.mainFrame, "onAddonStoreCommand")


updateState = {}


def loadState() -> None:
	# Some flags will have different default values based on current Windows version and edition.
	global updateState
	try:
		# Pickle wants to work with bytes.
		with open(os.path.join(globalVars.appArgs.configPath, "nvda3208.pickle"), "rb") as f:
			updateState = pickle.load(f)
	except (IOError, EOFError, NameError, ValueError, pickle.UnpicklingError):
		updateState["autoUpdate"] = isClientOS()
		updateState["backgroundUpdate"] = False
		updateState["addonStoreNotificationShown"] = False
		updateState["updateNotification"] = "toast"
		updateState["updateSource"] = "addondatastore"
		updateState["NVAccessAddonStoreViewsHash"] = ""
		updateState["lastChecked"] = 0
		updateState["noUpdates"] = []
		updateState["devUpdates"] = []
		updateState["devUpdateChannels"] = {}
		updateState["legacyAddonsFound"] = set()
	# Just to make sure...
	if "autoUpdate" not in updateState:
		updateState["autoUpdate"] = isClientOS()
	if "backgroundUpdate" not in updateState:
		updateState["backgroundUpdate"] = False
	if "addonStoreNotificationShown" not in updateState:
		updateState["addonStoreNotificationShown"] = False
	if "updateNotification" not in updateState:
		updateState["updateNotification"] = "toast"
	if "updateSource" not in updateState:
		updateState["updateSource"] = "addondatastore"
	if "NVAccessAddonStoreViewsHash" not in updateState:
		updateState["NVAccessAddonStoreViewsHash"] = ""
	if "lastChecked" not in updateState:
		updateState["lastChecked"] = 0
	if "noUpdates" not in updateState:
		updateState["noUpdates"] = []
	if "devUpdates" not in updateState:
		updateState["devUpdates"] = []
	if "devUpdateChannels" not in updateState:
		updateState["devUpdateChannels"] = {}
	if "legacyAddonsFound" not in updateState:
		updateState["legacyAddonsFound"] = set()
	# Moving from one-dimensional dev updates list to a dictionary of channels (dev channel by default).
	for entry in updateState["devUpdates"]:
		if entry not in updateState["devUpdateChannels"]:
			updateState["devUpdateChannels"][entry] = "dev"
	# Move update source from community add-ons website to add-on store.
	if updateState["updateSource"] == "nvdaprojectcompatinfo":
		updateState["updateSource"] = "addondatastore"


def saveState(keepStateOnline: bool = False) -> None:
	global updateState
	try:
		with open(os.path.join(globalVars.appArgs.configPath, "nvda3208.pickle"), "wb") as f:
			pickle.dump(updateState, f, protocol=0)
	except IOError:
		pass
	if not keepStateOnline:
		updateState.clear()


# Load and save add-on state if asked by the user.
def reload(factoryDefaults: bool = False) -> None:
	if not factoryDefaults:
		loadState()
	else:
		updateState.clear()
		updateState["autoUpdate"] = isClientOS()
		updateState["backgroundUpdate"] = False
		updateState["addonStoreNotificationShown"] = False
		updateState["updateNotification"] = "toast"
		updateState["updateSource"] = "addondatastore"
		updateState["NVAccessAddonStoreViewsHash"] = ""
		updateState["lastChecked"] = 0
		updateState["noUpdates"] = []
		updateState["devUpdates"] = []
		updateState["devUpdateChannels"] = {}


def save() -> None:
	saveState(keepStateOnline=True)
