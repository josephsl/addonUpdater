# addonUpdater/installTasks.py
# Copyright 2023 Joseph Lee, released under GPL version 2
# Copyright 2024, Luke Davis

# Provides needed routines during add-on installation and removal.
# Mostly checks compatibility.
# Partly based on other add-ons, particularly Place Markers by Noelia Martinez (thanks add-on authors).

import addonHandler
import gui
import winVersion

addonHandler.initTranslation()


def onInstall():
	# Do not present dialogs if minimal mode is set.
	currentWinVer = winVersion.getWinVer()
	# Add-on Updater requires Windows 10 22H2 or later.
	# Translators: title of the error dialog shown when trying to install the add-on in unsupported systems.
	# Unsupported systems include Windows versions earlier than 10 and unsupported feature updates.
	unsupportedWindowsReleaseTitle = _("Unsupported Windows release")
	minimumWinVer = winVersion.WIN10_22H2
	if currentWinVer < minimumWinVer:
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
				supportedBuild=minimumWinVer.build,
			),
			unsupportedWindowsReleaseTitle,
		)
		raise RuntimeError("Attempting to install Add-on Updater add-on on Windows releases earlier than 10")
