## What's Changed

- feat: add a welcome flow — first-run setup of language, theme, accent colour (system or custom), region with country flags, routing and servers, plus a "What's new" screen after every update
- feat: add free Cloudflare WARP profiles in one click — AmneziaWG with three masks and MASQUE over HTTP/3 and HTTP/2, with endpoint fallbacks
- feat: add proxy chains — route the selected server through a front proxy and/or out through an exit proxy (Xray, sing-box and hybrid mode), with server search when picking hops
- feat: add Zapret for a specific server — bind a server to "Auto" (the default winws2 strategy for TCP, QUIC or WireGuard), a Zapret preset or any catalog strategy; it applies only to that server's IP and port alongside the preset running for other traffic, and the server address is resolved over trusted DoH before connecting
- feat: redesign the Zapret and Configs pages — preset list with details and a preview, one Start/Stop button, double-click to run, and a code editor with line numbers, JSON formatting, validation with jump-to-line and Ctrl+S
- feat: clean up domain and IP rules as they are typed — URLs, ports, paths, `www.` and IDN are reduced to the bare host, IP or CIDR, and several addresses can be added at once with a preview
- feat: translate the whole interface, notifications, event log and backend messages into English, Persian and Chinese
- fix: make the "Start Zapret with Lumen" switch work
- fix: keep an already running Lumen in the tray when Windows autostart launches a second instance
- fix: open drop-down lists upwards when there is no room below and give them a working scrollbar
- test: cover the welcome flow, WARP profiles, proxy chains, per-server Zapret, rule clean-up and translations

Full Changelog: https://github.com/krambovic/Lumen/compare/v1.9.18...v2.0.0
