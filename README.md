# The Pirate Streaming

A fork of FenLightAM that brings external player support, restores API key functionality, adds quality-of-life improvements, and includes a customized BINGIE Mod skin designed specifically for this project.

The Pirate Streaming was created because maintaining the original setup had become a constant cycle of fixes. Since my mom relies on me to keep her TV working, I wanted to build a setup that I could maintain in one place instead of repeatedly fixing the same things.

This project brings the add-on, skin, and related configuration together in one place to make installation easier.

---

## Table of Contents

- [About the Project](#about-the-project)
- [Features](#features)
- [Development Status](#development-status)
- [Important Skin Warning](#important-skin-warning)
- [Simulated Live TV](#simulated-live-tv)
- [Supported Platforms](#supported-platforms)
- [Mouse Support](#mouse-support)
- [Requirements](#requirements)
- [Installation Guide](#installation-guide)
- [Initial Setup](#initial-setup)
- [Troubleshooting](#troubleshooting)
- [Credits](#credits)
- [Disclaimer](#disclaimer)

---

## About the Project

The Pirate Streaming builds on the work of FenLight and FenLightAM while adding its own features and customizations.

The project includes a customized version of the BINGIE Mod skin, bundled directly with the repository. You do not need to locate or install a separate skin repository.

The goal is to provide a unified Kodi experience with personalized home-screen layouts, automated ratings, external player support, and a simulated Live TV experience.

## Features

- **Restored API Key Functionality** — Restores API key functionality from the underlying add-on project where supported.
-  **Prioritize Cloud-Search** - Searches your provider's cloud to auto-select a previously played media instead of scraping again.
- **Automatic TV Ratings** — TV ratings are enabled by default and color-coded to better match the media presentation.
- **Automatic Review Ratings** — Review ratings and their providers are enabled by default.
- **Customized BINGIE Mod Skin** — A bundled skin tailored to The Pirate Streaming.
- **Simulated Live TV** — Genre-based channels, Trakt-powered schedules, Kodi Favorites, and seasonal channels.
- **Unified Installation** — The skin ZIP is intended to install the components required for the complete setup.
- **Ongoing Maintenance** — Continued fixes and improvements as time permits.

## Development Status

The Pirate Streaming is an ongoing project. Features, layouts, and compatibility may change as fixes and improvements are made.
Some areas, especially the simulated Live TV experience and offline TV Guide, remain works in progress.

The percentages below are estimates until verified. They do not guarantee that a feature is complete, stable, or fully tested.

### Core Add-on — 80%

`[████████░░] 80%`

Main add-on functionality and integration.

### External Players — 60%

`[██████░░░░] 60%`

External player configuration and playback.

### API Keys — 70%

`[███████░░░] 70%`

Restored keys and related service functionality.

### Bundled Skin — 80%

`[████████░░] 80%`

BINGIE Mod customization and integration.

### Genre Channels — 60%

`[██████░░░░] 60%`

Channel generation and playback.

### Trakt Schedule — 60%

`[██████░░░░] 60%`

Generating a schedule from Trakt lists.

### Favorites Channel — 70%

`[███████░░░] 70%`

Populating the channel from Kodi Favorites.

### Holiday Channel — 70%

`[███████░░░] 70%`

Seasonal visibility and holiday programming.

### Offline TV Guide — 40%

`[████░░░░░░] 40%`

Guide interface and schedule navigation.

### Testing — 55%

`[█████▌░░░░] 55%`

Compatibility testing across devices and setups.

## Important Skin Warning

**Please do not change the skin settings unless you know exactly what you are doing.**

The included skin has been customized specifically for The Pirate Streaming. Its layouts and features are designed to work with the project's existing configuration.

Changing skin settings, experimenting with unsupported options, or altering its configuration may cause parts of the interface to break or behave unexpectedly.

If you encounter a problem, please check the troubleshooting section before changing skin settings.

## Simulated Live TV

The Pirate Streaming includes a work-in-progress, channel-based experience designed to make browsing your library feel more like watching television.

This is **not conventional broadcast television**. Channels are populated using your configured sources and content lists.

Current features include:

- **Genre Channels** — Browse content through genre-based channels.
- **Trakt-Powered Schedules** — Trakt lists can populate schedules containing a mixture of movies and TV shows.
- **Kodi Favorites Channel** — Content from your Kodi Favorites can populate its own channel.
- **Seasonal Holiday Channels** — A seasonal channel can appear automatically during Halloween and Christmas periods, featuring relevant content.
- **Offline TV Guide** — An offline guide is available in a usable but unfinished state.

### TV Guide Development

The TV Guide remains a major work in progress and needs substantial additional development. Some features and behaviors may change as development continues.

## Supported Platforms

The project has been developed and tested with the following platforms:

- PC
- Xbox
- Android TV
- Amazon Fire TV Stick

Compatibility can vary depending on your device, Kodi version, installed dependencies, and available hardware resources. Not every feature is guaranteed to work identically across every platform.

## Mouse Support

Mouse support is **not officially supported**.

I have made code adjustments to make mouse navigation more bearable, but there are limitations that cannot be fully addressed without changes to Kodi itself.

For the intended experience, a compatible remote, controller, or other supported navigation method is recommended.

## Requirements

Before installing, make sure you have:

- A working installation of Kodi compatible with the project's dependencies.
- An internet connection for installation and initial configuration.
- A Trakt account if you want to use Trakt-powered features.
- A compatible Debrid service or torrent provider, configured according to your preferences and the add-on's supported options, if required for your chosen sources.

Availability and compatibility depend on your device, Kodi version, and provider configuration.

## Installation Guide

Install The Pirate Streaming directly through Kodi using the project's website as a source in Kodi's File Manager.

**Repository URL:**

`https://ThePirateDylan.github.io/thepiratestreaming/`

### Step 1 — Add the Source in Kodi

1. Open Kodi.
2. Navigate to **Settings**.
3. Select **File Manager**.
4. Choose **Add source**.
5. Select the field displaying `<None>`.
6. Enter the following URL exactly:

   `https://ThePirateDylan.github.io/thepiratestreaming/`

7. Select **OK**.
8. Enter `The Pirate Streaming` as the source name.
9. Select **OK** to save the source.

### Step 2 — Enable Unknown Sources

1. Return to Kodi's **Settings**.
2. Select **System**.
3. Open **Add-ons**.
4. Enable **Unknown sources**.
5. Confirm the warning by selecting **Yes**.

This allows Kodi to install ZIP packages from sources outside its official repository system. Only install packages you trust.

### Step 3 — Install the Skin ZIP

1. Return to Kodi's home screen.
2. Open **Add-ons**.
3. Select the **Add-on Browser**.
4. Choose **Install from ZIP file**.
5. Select the `The Pirate Streaming` source you added in Step 1.
6. Locate and select the **The Pirate Repo**.
7. Wait for the installation to complete.
8. Choose **Install from Repositroy**.
9. Select **The Pirate Repo**.
10. Select **Look and Feel**.
11. Select **The Pirate Skin** and install. Select `Yes` to install dependencies.

If Kodi asks whether you want to switch to the included skin, select **Yes**.

### Step 4 — Allow Setup to Finish

Allow Kodi to finish installing and configuring the included components. Depending on your device and internet connection, this may take some time.

Do not interrupt the installation process.

Once the customized home screen loads, continue to [Initial Setup](#initial-setup).

## Initial Setup

After installation:

1. Open the left sidebar from the home screen.
2. Select **Settings**.
3. Sign in to or authenticate your **Trakt** account if you want to use Trakt features.
4. Configure your preferred supported **Debrid** or **Torrent** provider, as applicable. You may configure multiple.
5. Configure your choice of **Scraper**.
6. Return to the home screen and explore the available sections and channels.

Provider availability, authentication steps, and source behavior depend on the services you choose.

**Remember:** Avoid changing the included skin's settings. It has been configured specifically for this project.

## Troubleshooting

### The source cannot be opened

- Check that you entered the repository URL correctly.
- Verify that your device has an internet connection.
- Confirm that the website is accessible.
- If Kodi cannot browse the source, the website may need a Kodi-compatible directory listing or repository structure.

### The skin did not activate

- Check whether Kodi displayed a prompt to switch skins.
- Allow the installation process to finish.
- Restart Kodi and check whether the included skin is available.
- Consult the project website for the current installation package and instructions.

### Add-ons or dependencies are missing

- Confirm that you selected the intended **The Pirate Streaming Skin ZIP**.
- Make sure your Kodi version is compatible with the package.
- Check Kodi's notifications and logs for installation errors.
- Verify that your device has an internet connection.

### Trakt lists or channels are empty

- Confirm that you authenticated Trakt successfully.
- Check that your selected Trakt lists contain content.
- Allow time for content and schedules to populate.
- Check whether the relevant feature is still under development.

### Playback is not working

- Check your provider configuration and authentication.
- Verify that your selected source is supported by your device and Kodi version.
- If using an external player, check its installation and configuration.

### The skin looks broken after changing settings

Restore the intended configuration if you know which settings were changed. If you are unsure how to restore it, avoid making further changes and consult the project's documentation or report the problem.

For unresolved problems, include your device, Kodi version, the steps that caused the issue, and relevant Kodi log errors when reporting a bug.

## Credits

The Pirate Streaming builds on the work and resources of other developers and projects.

- **peno64** — Help with repository URL casing.
- **Goldenfreddy0703** — Inspiration for repository structure and layout.
- **drinfernoo** — Example repository.
- **TikiPeter** — Creator of FenLight.
- **AnonyMouse** — Continued development of FenLightAM.
- **BINGIE Mod team** — Original skin foundation.
- **kittmaster** — Kodi Texture Tool.
- **Team Kodi** — Android TV GUI sounds.

Thank you to the developers and contributors whose work helped make this project possible.

## Disclaimer

The Pirate Streaming is an independent community project and is not affiliated with, endorsed by, or officially connected to Kodi, Team Kodi, the developers of FenLight or FenLightAM, or the BINGIE Mod team.

All trademarks, software, and third-party assets remain the property of their respective owners. Credit is provided to acknowledge the original work.

Users are responsible for how they configure and use Kodi, third-party add-ons, playback providers, and external services. Ensure that your use complies with applicable laws and the terms of the services you choose.
