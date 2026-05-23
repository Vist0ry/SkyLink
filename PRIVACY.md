# SkyLink Privacy & Data Policy

SkyLink is a Windows agent for Elite Dangerous. It synchronizes selected game journal data with external services **only when you run the application and accept the in-app policy**.

## Data transmission

### 1. EDDN (Elite Dangerous Data Network)

- **Sent:** star coordinates, planet scan data, signals, FSD jumps.
- **Purpose:** updating public databases (Inara, Spansh, EDSM).
- **Privacy:** commander name is anonymized/hashed by the network protocol. Personal data is not sent by SkyLink to EDDN.

### 2. SkyBioML Portal (squadron server)

- **Sent:** ship status, loadouts, cargo, location, credits, and related telemetry configured in `events.json`.
- **Purpose:** squadron HQ tools on [skybioml.space](https://skybioml.space) (commander sync, Road 2 Riches, etc.).
- **Privacy:** data is accessible only to authorized members of your squadron portal. You control access via the API key generated in **HQ → SKYLINK API**.

## Local storage

- API keys and settings are stored **only on your PC** under `%APPDATA%\SkyLink\`.
- SkyLink does not upload API keys to third parties except when sending authenticated requests to your configured portal endpoints.

## Network behavior

This program does not transfer information to networked systems unless specifically requested by the user (by adding an account / API key) or required for the features above (EDDN public network, portal heartbeat/telemetry, GitHub update check).

## Contact

Project repository: [github.com/Vist0ry/SkyLink](https://github.com/Vist0ry/SkyLink)
