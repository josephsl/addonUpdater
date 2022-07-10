# -*- coding: UTF-8 -*-
# addonHandler.py
# A part of NonVisual Desktop Access (NVDA)
# Copyright (C) 2012-2022 Rui Batista, NV Access Limited, Noelia Ruiz Martínez, Joseph Lee
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

# Proof of concept implementation of NVDA Core issue 3208.

import threading
import wx
import addonHandler
import extensionPoints
from . import addonUtils
addonHandler.initTranslation()


# Add-ons with all features integrated into NVDA or declared "legacy" by authors.
# For the latter case, update check functionality will be disabled upon authors' request.

# Translators: legacy add-on, features included in NVDA.
LegacyAddonIncludedInNVDA = _("features included in NVDA")
# Translators: legacy add-on, declared by add-on developers.
LegacyAddonAuthorDeclaration = _("declared legacy by add-on developers")

LegacyAddons = {
	# Bit Che is no longer maintained as of 2021, therefore the add-on is unnecessary, according to the author.
	"bitChe": LegacyAddonAuthorDeclaration,
	"enhancedAria": LegacyAddonIncludedInNVDA,
	# Advanced focus highlight customizations are not implemented in NVDA yet,
	# but legacy add-on in terms of functionality.
	"focusHighlight": LegacyAddonIncludedInNVDA,
	"screenCurtain": LegacyAddonIncludedInNVDA,
	# Team Viewer is no longer used by the add-on author.
	"teamViewer": LegacyAddonAuthorDeclaration,
}


def shouldNotUpdate():
	# Returns a list of descriptions for add-ons that should not update.
	return [
		addon.manifest["summary"] for addon in addonHandler.getAvailableAddons()
		if addon.name in addonUtils.updateState["noUpdates"]
	]


def preferDevUpdates():
	# Returns a list of descriptions for add-ons that prefers development releases.
	return [
		addon.manifest["summary"] for addon in addonHandler.getAvailableAddons()
		if addon.name in addonUtils.updateState["devUpdates"]
	]


def detectLegacyAddons():
	# Returns a dictionary of add-on name and summary for legacy add-ons.
	return {
		addon.name: addon.manifest["summary"] for addon in addonHandler.getAvailableAddons()
		if addon.name in LegacyAddons
	}


def autoAddonUpdateCheck():
	t = threading.Thread(target=_showAddonUpdateUI)
	t.daemon = True
	t.start()


# Only stored when update toast appears.
_updateInfo = None
updateSuccess = extensionPoints.Action()


def _showAddonUpdateUI():
	def _showAddonUpdateUICallback(info):
		import gui
		from .addonGuiEx import AddonUpdatesDialog
		gui.mainFrame.prePopup()
		AddonUpdatesDialog(gui.mainFrame, info).Show()
		gui.mainFrame.postPopup()
	from . import addonUpdateProc
	try:
		info = addonUpdateProc.checkForAddonUpdates()
	except:
		info = None
		raise
	if info is not None:
		# Show either the update notification toast (Windows 10 and later)
		# or the results dialog (other Windows releases and server systems).
		# On Windows 10 and later (client versions), this behavior is configurable.
		# If toast is shown, checking for add-on updates from tools menu will merely show the results dialog.
		# wxPython 4.1.0 (and consequently, wxWidges 3.1.0) simplifies this by
		# allowing action handlers to be defined for toasts, which will then show the results dialog on the spot.
		# However it doesn't work for desktop apps such as NVDA.
		import winVersion
		winVer = winVersion.getWinVer()
		if (
			winVer >= winVersion.WIN10 and winVer.productType == "workstation"
			and addonUtils.updateState["updateNotification"] == "toast"
		):
			global _updateInfo
			# Translators: menu item label for reviewing add-on updates.
			updateSuccess.notify(label=_("Review &add-on updates ({updateCount})...").format(updateCount=len(info)))
			updateSources = {
				"nvdaprojectcompatinfo": _("NVDA community add-ons website"),
				"nvdaes": _("Spanish community add-ons catalog"),
			}
			updateMessage = _(
				# Translators: presented as part of add-on update notification message.
				"One or more add-on updates are available from {updateSource}. "
				"Go to NVDA menu, Tools, Review add-on updates to review them."
			).format(updateSource=updateSources[addonUtils.updateState["updateSource"]])
			# Translators: title of the add-on update notification message.
			wx.adv.NotificationMessage(_("NVDA add-on updates"), updateMessage).Show(timeout=30)
			_updateInfo = info
		else:
			wx.CallAfter(_showAddonUpdateUICallback, info)
