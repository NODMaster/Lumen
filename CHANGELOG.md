## What's Changed

- feat: add a first-run welcome flow (language, theme, palette, region, routing and servers) that also opens after every update with curated "What's new" notes; fresh installs see only the setup
- feat: get free Cloudflare WARP profiles in one click — three AmneziaWG masks and MASQUE over HTTP/3 and HTTP/2, generated like warp-generation.github.io with endpoint fallbacks
- feat: add a proxy chain like v2rayN — route the selected server through a previous (front) proxy and/or out through an exit proxy, for Xray, sing-box and the hybrid sidecar; unsupported or missing hops are skipped with a warning
- feat: run Zapret together with a specific server — the bound preset applies only to connection handshakes to that server's IP and port (started before the connection when the address is known), next to the preset started manually for all other traffic, and does not count as a running Zapret strategy; the "start Zapret with Lumen" switch now works
- feat: bind a server to a "Strategy" — one list per server offers "Auto" (the named default winws2 strategy for its type: TCP, QUIC, WireGuard), Zapret presets and the other catalog strategies, applied to that server only; changing it while connected reconnects through the new strategy, an unresolved server address is looked up before connecting so winws2 is ready before the handshake, and the selected server is offered first when adding a binding
- fix: resolve bound server names over trusted DoH by IP (no ISP DNS, last good address kept for 7 days) and send no SNI to direct DoH-by-IP resolvers
- feat: redesign the Zapret and Configs pages — preset list with details and a preview, a shared code editor with line numbers, JSON formatting, validation with jump-to-line and Ctrl+S
- feat: translate the remaining windows, hints, notifications, event log entries and backend messages into English, Persian and Chinese
- fix: keep an already running Lumen in the tray when Windows autostart launches a second instance
- fix: render the welcome card with clean rounded borders over a strongly blurred backdrop
- fix: smooth the welcome flow at the monitor's full refresh rate, keep its cards the same size in every language and stop the WARP panel from jumping at the end of its animation
- feat: ask for a GitHub star and offer project support at the bottom of the last welcome page; the subscription field now matches the search fields
- feat: show country flags for regional profiles and offer the system accent first plus a custom accent colour in the welcome flow
- feat: search servers when picking proxy chain hops; double-click a Zapret preset to run it
- feat: clean up domain and IP rules as they are typed — pasted URLs, ports, paths, `www.`, trailing dots and IDN are reduced to the bare host, IP or CIDR, several addresses can be added at once and a preview shows what will be added
- fix: open drop-down lists upwards when there is no room below and give them a working scrollbar
- fix: simplify the Zapret page — one Start/Stop button for the selected preset and a shorter "Zapret" title
- test: cover the welcome flow, release notes, WARP profile generation and dynamic translations
- test: cover proxy chain config building and per-server Zapret bindings
- test: cover server-limited Zapret profiles and routing address normalisation

Full Changelog: https://github.com/krambovic/Lumen/compare/v1.9.18...v2.0.0
