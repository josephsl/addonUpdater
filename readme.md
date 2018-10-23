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

## Version 18.10

* Initial stable release (still marked as proof of concept).

[1]: https://addons.nvda-project.org/files/get.php?file=nvda3208

[2]: https://github.com/nvaccess/nvda/issues/3208
