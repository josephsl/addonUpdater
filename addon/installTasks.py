# addonUpdater/installTasks.py
# Copyright 2023 Joseph Lee, released under GPL.

# Provides needed routines during add-on installation and removal.
# Mostly checks compatibility.
# Partly based on other add-ons, particularly Place Markers by Noelia Martinez (thanks add-on authors).

import addonHandler
addonHandler.initTranslation()


def onInstall():
	import gui
	import wx
	import winVersion
	import globalVars
	# Do not present dialogs if minimal mode is set.
	currentWinVer = winVersion.getWinVer()
	# Add-on Updater requires Windows 10 22H2 or later.
	# Translators: title of the error dialog shown when trying to install the add-on in unsupported systems.
	# Unsupported systems include Windows versions earlier than 10 and unsupported feature updates.
	unsupportedWindowsReleaseTitle = _("Unsupported Windows release")
	minimumWinVer = winVersion.WIN10_22H2
	if currentWinVer < minimumWinVer:
		if not globalVars.appArgs.minimal:
			gui.messageBox(
				_(
					# Translators: Dialog text shown when trying to install the add-on on
					# releases earlier than minimum supported release.
					"You are using {releaseName} ({build}), a Windows release not supported by this add-on.\n"
					"This add-on requires {supportedReleaseName} ({supportedBuild}) or later."
				).format(
					releaseName=currentWinVer.releaseName,
					build=currentWinVer.build,
					supportedReleaseName=minimumWinVer.releaseName,
					supportedBuild=minimumWinVer.build
				), unsupportedWindowsReleaseTitle, wx.OK | wx.ICON_ERROR
			)
		raise RuntimeError("Attempting to install Add-on Updater add-on on Windows releases earlier than 10")
	# Present add-on store messages while installing this add-on.
	addonStoreMessage = _(
		# Translators: message presented when add-on store is available in NVDA.
		"You are using NVDA 2023.1 or earlier. NVDA 2023.2 introduces an add-on store "
		"to browse, install, manage, and update add-ons. After updating to NVDA 2023.2 or later, "
		"Visit NVDA add-on store (NVDA menu, Tools, add-on store) to check for add-on updates. "
		"Add-on Updater can still be used to check for add-on updates in the meantime."
	)
	if hasattr(gui.mainFrame, "onAddonStoreCommand"):
		addonStoreMessage = _(
			# Translators: message presented when add-on store is available in NVDA.
			"You are using an NVDA release with add-on store included. "
			"Visit NVDA add-on store (NVDA menu, Tools, add-on store) to check for add-on updates. "
			"Add-on Updater can still be used to check for add-on updates in the meantime."
		)
	gui.messageBox(addonStoreMessage, _("Add-on Updater"), wx.OK | wx.ICON_INFORMATION)
