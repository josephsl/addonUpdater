# Add-on Updater
# Copyright 2018-2022 Joseph Lee, released under GPL.

import pickle
import os
import globalVars

updateState = {}


def loadState():
	global updateState
	try:
		# Pickle wants to work with bytes.
		with open(os.path.join(globalVars.appArgs.configPath, "nvda3208.pickle"), "rb") as f:
			updateState = pickle.load(f)
	except (IOError, EOFError, NameError, ValueError, pickle.UnpicklingError):
		updateState["autoUpdate"] = True
		updateState["backgroundUpdate"] = False
		updateState["updateNotification"] = "toast"
		updateState["updateSource"] = "nvdaprojectcompatinfo"
		updateState["lastChecked"] = 0
		updateState["noUpdates"] = []
		updateState["devUpdates"] = []
		updateState["legacyAddonsFound"] = set()
	# Just to make sure...
	if "autoUpdate" not in updateState:
		updateState["autoUpdate"] = True
	if "backgroundUpdate" not in updateState:
		updateState["backgroundUpdate"] = False
	if "updateNotification" not in updateState:
		updateState["updateNotification"] = "toast"
	if "updateSource" not in updateState:
		updateState["updateSource"] = "nvdaprojectcompatinfo"
	if "lastChecked" not in updateState:
		updateState["lastChecked"] = 0
	if "noUpdates" not in updateState:
		updateState["noUpdates"] = []
	if "devUpdates" not in updateState:
		updateState["devUpdates"] = []
	if "legacyAddonsFound" not in updateState:
		updateState["legacyAddonsFound"] = set()


def saveState(keepStateOnline=False):
	global updateState
	try:
		with open(os.path.join(globalVars.appArgs.configPath, "nvda3208.pickle"), "wb") as f:
			pickle.dump(updateState, f, protocol=0)
	except IOError:
		pass
	if not keepStateOnline:
		updateState = None


# Load and save add-on state if asked by the user.
def reload(factoryDefaults=False):
	if not factoryDefaults:
		loadState()
	else:
		updateState.clear()
		updateState["autoUpdate"] = True
		updateState["backgroundUpdate"] = False
		updateState["updateNotification"] = "toast"
		updateState["updateSource"] = "nvdaprojectcompatinfo"
		updateState["lastChecked"] = 0
		updateState["noUpdates"] = []
		updateState["devUpdates"] = []


def save():
	saveState(keepStateOnline=True)
