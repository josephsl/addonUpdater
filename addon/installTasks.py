# addonUpdater/installTasks.py
# Copyright 2023 Joseph Lee, released under GPL.

# Provides needed routines during add-on installation and removal.
# Mostly checks compatibility.
# Partly based on other add-ons, particularly Place Markers by Noelia Martinez (thanks add-on authors).

import addonHandler
addonHandler.initTranslation()


def onInstall():
	# Display add-on store notification after restarting NVDA.
	try:
		import globalPlugins
		globalPlugins.addonUpdater.addonUtils.updateState["addonStoreNotificationShown"] = False
	except Exception:
		pass
