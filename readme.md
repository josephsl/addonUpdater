# Add-on Updater

* Author: Joseph Lee
* Download [prototype version][1]

This add-on brings NVDA Core issue 3208 to life: ability to check for, download, and apply add-on updates.

To check for updates after installing this add-on, go to NVDA menu/Tools/Check for add-on updates. If updates are available, a list of add-on updates will be shown, with each entry consisting of description, current version, and the new version. Select Update, and NVDA will download and apply updates in sequence, with a prompt to restart your NVDA shown afterwards.

The following add-ons provide built-in update feature and thus updates will not be checked via this add-on:

* Braille Extender
* StationPlaylist Studio
* WeatherPlus
* Windows 10 App Essentials

IMPORTANT: this is a proof of concept add-on. Once the [relevant feature is included in NVDA][2], this add-on will be discontinued.

## Version 18.08.5

* Fixed an issue where Add-on Updater settings panel failed to show if one or more add-ons had badly formatted manifest data.
* Added Nuance Vocalizer family of add-ons to add-ons that'll not be checked for updates.

## Version 18.08.4

* Fixed a regression introducedin 18.08.3 where NVDA continuously played progress beep when trying to check for add-on updates.

## Version 18.08.3

* Added ability to exclude add-ons from being updated via a new checkable list box found in Add-on Updater settings panel. Checked items will not be updated.

## Version 18.08.1

* It is now possible to let NVDA check for add-on updates automatically (every 24 hours). This is configured through a new Add-on Updater settings panel found in NVDA settings.

## Version 18.08

* Initial version.

[1]: https://addons.nvda-project.org/files/get.php?file=nvda3208

[2]: https://github.com/nvaccess/nvda/issues/3208
