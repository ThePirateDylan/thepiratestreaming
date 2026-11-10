<p align="center">
  <img src="repo/skin.pirate/media/branding/thepirate-logo.png" alt="The Pirate Streaming" width="480">
</p>

# The Pirate Streaming

A Kodi add-on and custom skin for movies, TV shows, and scheduled channels. Built on FenLightAM and BINGIE Mod, The Pirate brings browsing, playback, and a cable-style TV Guide into one interface.

**[Install](#installation)** · **[First-time setup](#first-time-setup)** · **[Troubleshooting](#troubleshooting)** · **[Report an issue](https://github.com/ThePirateDylan/thepiratestreaming/issues)** · **[Changelog](repo/plugin.video.pirate/resources/text/changelog.txt)**

## What’s included

- **The Pirate Skin:** a navy-and-blue interface designed for remote and keyboard navigation.
- **Movies and TV:** search, Continue Watching, saved progress, and Trakt integration.
- **TV Guide:** scheduled channels, seasonal programming, and playback that joins a program in progress when seeking is available.
- **Channel tuning:** a “SEARCHING FOR SIGNAL...” transition while a channel connects and moves to its scheduled position.
- **Playback options:** supported debrid services, provider cloud search, and external player support.

TV Guide channels use on-demand sources and content lists. Playback availability depends on your configured providers.

## Installation

You’ll need Kodi with Python 3 add-on support, an internet connection, and a supported source provider for playback. Trakt is optional for account-based lists and watch progress. A remote, controller, or keyboard is recommended; mouse support is limited.

### 1. Add the repository source

In Kodi, open **Settings → File manager → Add source**. Select **None** and enter:

```text
https://ThePirateDylan.github.io/thepiratestreaming/
```

Name the source **The Pirate Streaming** and select **OK**.

### 2. Install The Pirate Repo

1. Open **Settings → System → Add-ons** and enable **Unknown sources**.
2. Go to **Add-ons → Add-on browser → Install from zip file**.
3. Select **The Pirate Streaming**, then **repository.pirate-1.0.8.zip**.
4. Wait for the repository installation notification.

Already have the ZIP on your device? Select it directly under **Install from zip file**. [Download the repository ZIP](repository.pirate-1.0.8.zip).

### 3. Install the skin

1. Choose **Install from repository → The Pirate Repo**.
2. Open **Look and feel → Skin → The Pirate Skin** and select **Install**.
3. Accept the required dependencies and wait for installation to finish.
4. Select **Yes** when Kodi asks to switch to The Pirate Skin.

The skin installs the required Pirate components, including the video add-on. Continue with [first-time setup](#first-time-setup) to connect your playback services.

## First-time setup

1. Open **Settings** from the home-screen sidebar.
2. Authorize your supported debrid or source provider.
3. Select and configure your scraper.
4. Connect Trakt if you want your lists and watch progress available in Kodi.
5. Play a movie or episode to confirm your setup, then open the TV Guide.

Allow the guide’s initial preparation to finish. Its channels use the same source configuration as regular playback.

The skin ships with a configured layout. Keep a backup before changing menus, widgets, or advanced skin settings.

## Updating

Install updates through **The Pirate Repo** in Kodi. When an update includes both the video add-on and skin, update both and fully restart Kodi.

For manual test builds, install each supplied add-on ZIP through **Install from zip file**. The GitHub **Download ZIP** archive contains the source repository and cannot be installed as a Kodi add-on.

## Troubleshooting

Choose the issue that matches what you’re seeing:

- [Repository source won’t open](#repository-source-wont-open)
- [Installation or dependency error](#installation-or-dependency-error)
- [Skin didn’t switch or looks wrong](#skin-didnt-switch-or-looks-wrong)
- [No results or playback won’t start](#no-results-or-playback-wont-start)
- [Trakt lists or Continue Watching are missing](#trakt-lists-or-continue-watching-are-missing)
- [TV Guide is empty, stuck, or crashes](#tv-guide-is-empty-stuck-or-crashes)

### Repository source won’t open

Copy the source URL from [Installation](#installation) and check for typing errors. Confirm your device is online. If browsing the source still fails, download the [repository ZIP](repository.pirate-1.0.8.zip), transfer it to your device, and install it locally.

### Installation or dependency error

Install **The Pirate Repo** first, then install the skin from that repository. Note the exact dependency named in Kodi’s error and check that your Kodi version supports it. Include that message when [reporting the problem](#reporting-a-problem).

### Skin didn’t switch or looks wrong

Wait for all dependencies to finish installing. Open **Settings → Interface → Skin** and select **The Pirate Skin**. If an update appears incomplete, confirm that both Pirate components updated and restart Kodi.

If the problem began after changing a skin setting, restore that setting or your saved configuration.

### No results or playback won’t start

Check that your provider is authorized, its subscription is active where required, and your scraper is configured. Try another title or source to see whether the problem affects one item or all playback. For an external player, also check its installation and configuration.

If regular playback works but a guide channel fails, include the channel, program, and time in your report.

### Trakt lists or Continue Watching are missing

Confirm that the correct Trakt account is connected and that the list or playback progress exists in that account. Allow synchronization to finish. Include an affected title and whether the problem appears in the add-on, a home-screen widget, or both.

### TV Guide is empty, stuck, or crashes

Check whether guide preparation is still running, and test a regular movie or episode to confirm your playback setup. After updating both the add-on and skin, fully restart Kodi and try again.

If Kodi freezes or closes, record the exact sequence—for example, **open guide → play channel → stop → exit guide**—and save the log before further restarts overwrite it. See [Reporting a problem](#reporting-a-problem).

### Reporting a problem

[Open a GitHub issue](https://github.com/ThePirateDylan/thepiratestreaming/issues) with:

- Device and operating system.
- Kodi, The Pirate, and Pirate Skin versions.
- Steps to reproduce the problem and what you expected to happen.
- The error message, a screenshot if useful, and a relevant Kodi log.

Remove credentials, API keys, and private playback links from logs before posting them.

## Credits

- **TikiPeter** — FenLight.
- **AnonyMouse** — FenLightAM.
- **BINGIE Mod team** — the original skin.
- **kittmaster** — Kodi Texture Tool.
- **Team Kodi** — Kodi and Android TV GUI sounds.
- **Goldenfreddy0703** and **drinfernoo** — repository structure and examples.
- **peno64** — repository URL assistance.

The Pirate Streaming is an independent community project. It is not affiliated with Kodi or the upstream projects credited above. Third-party services and assets belong to their respective owners.
