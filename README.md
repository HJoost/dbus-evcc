# dbus-open-evcc (Fork by HJoost)
Integrate EVCC charger into Victron Venus OS

> **This is a fork of [SamuelBrucksch/dbus-evcc](https://github.com/SamuelBrucksch/dbus-evcc).**
> See [What's different in this fork](#whats-different-in-this-fork) below.

## What's different in this fork

The original script only supports a **single EVCC loadpoint**. This fork adds full **multi-loadpoint support**:

- Each loadpoint is registered as a **separate EV charger on the Victron D-Bus**, with its own DeviceInstance and custom name.
- The number of loadpoints is either **auto-detected from the EVCC API** or configured explicitly via `[LOADPOINT0]`, `[LOADPOINT1]`, … sections in `config.ini`.
- Only a **single HTTP request per update cycle** is made to EVCC, regardless of the number of loadpoints.
- New D-Bus paths: `/Session/Energy` and `/Session/Time`.
- `SetCurrent` now uses `offeredCurrent` (instead of `chargeCurrent`) to reflect what EVCC actually offers.
- `chargeDuration` is now read in seconds (EVCC API v0.13+; older API used nanoseconds).
- Uses `dbus.SystemBus(private=True)` for proper D-Bus isolation when registering multiple services.

## Purpose
This script supports reading EV charger values from EVCC. Writing values is not supported right now.

## Install & Configuration
### Get the code
Grab a copy of **this fork** and copy it to a folder under `/data/` e.g. `/data/dbus-evcc`.
After that call the install.sh script.

The following script should do everything for you:
```
wget https://github.com/HJoost/dbus-evcc/archive/refs/heads/main.zip
unzip main.zip "dbus-evcc-main/*" -d /data
mv /data/dbus-evcc-main /data/dbus-evcc
chmod a+x /data/dbus-evcc/install.sh
/data/dbus-evcc/install.sh
rm main.zip
```
⚠️ Check configuration after that - because the service is already installed and running, and wrong connection data (host) will spam the log-file.

### Change config.ini
Within the project there is a file `/data/dbus-evcc/config.ini`. The minimal required settings are the EVCC host and at least one loadpoint section.

**Example for two loadpoints:**
```ini
[DEFAULT]
AccessType = OnPremise
SignOfLifeLog = 1

[ONPREMISE]
Host = 192.168.1.99:7070

[LOADPOINT0]
Deviceinstance = 43
Name = Wallbox 1

[LOADPOINT1]
Deviceinstance = 44
Name = Wallbox 2
```

If no `[LOADPOINT*]` sections are defined, the number of loadpoints is **auto-detected from the EVCC API** and `Deviceinstance` values are assigned sequentially starting from the `DEFAULT` value.

| Section | Config value | Explanation |
| --- | --- | --- |
| DEFAULT | AccessType | Fixed value `OnPremise` |
| DEFAULT | SignOfLifeLog | Time in minutes how often a status is added to `current.log` with log-level INFO |
| DEFAULT | Deviceinstance | Base DeviceInstance (used when no `[LOADPOINT*]` sections are defined) |
| ONPREMISE | Host | IP or hostname (and port) of EVCC, e.g. `192.168.1.99:7070` |
| LOADPOINT0..N | Deviceinstance | Unique ID identifying this charger in Venus OS |
| LOADPOINT0..N | Name | Custom name shown in Venus OS / Victron Remote Console |

## Useful links
Many thanks to @vikt0rm, @fabian-lauer, @trixing, @JuWorkshop and @SamuelBrucksch:
- https://github.com/SamuelBrucksch/dbus-evcc (upstream fork this is based on)
- https://github.com/trixing/venus.dbus-twc3
- https://github.com/fabian-lauer/dbus-shelly-3em-smartmeter
- https://github.com/vikt0rm/dbus-goecharger
- https://github.com/JuWorkshop/dbus-evsecharger
