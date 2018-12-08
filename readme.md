# Add-on Updater

* Author: Joseph Lee
* Download [stable version][1]

This add-on brings NVDA Core issue 3208 to life: ability to check for, download, and apply add-on updates.

To check for updates after installing this add-on, go to NVDA menu/Tools/Check for add-on updates. If updates are available, a list of add-on updates will be shown, with each entry consisting of description, current version, and the new version. Select Update, and NVDA will download and apply updates in sequence, with a prompt to restart your NVDA shown afterwards.

The following add-ons provide built-in update feature and thus updates will not be checked via this add-on:

* Braille Extender
* WeatherPlus

The following add-ons do have their own update check feature which will be disabled once Add-on Updater is installed:

* StationPlaylist Studio
* Windows 10 App Essentials

IMPORTANT: this is a proof of concept add-on. Once the [relevant feature is included in NVDA][2], this add-on will be discontinued.

## Version 18.12.1

* Fixed compatibility with recent NVDA alpha snapshots where add-on updates would not download.

## Version 18.12

* Updates for disabled add-ons can be checked. They will stay disabled after updating them.
* During updates, if an add-on requires specific NVDA version and/or Windows release, these will be checked, and if one of these does not match, an error message will be shown and update will be aborted, resulting in no changes to already installed add-on version.
* When automatic update check is enabled and when updates are ready, NVDA will present the updates list instead of asking if you wish to review updates.

## Version 18.10

* Initial stable release (still marked as proof of concept).

[1]: https://addons.nvda-project.org/files/get.php?file=nvda3208

[2]: https://github.com/nvaccess/nvda/issues/3208
