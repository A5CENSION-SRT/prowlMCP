# prowlMCP

Local MCP server (Prowlarr, qBittorrent, Jellyfin) plus the delivery pipeline to a Jellyfin media server. See `README.md` for the architecture, the tools, the `prowl` command line and the setup.

## Working rules

- Short, interactive work goes through the prowl-mcp tools. Long or unattended work (waiting for a download, subtitles, transfer) goes through the `prowl` CLI as a background task, or the systemd worker. README section 4 explains when to use which.
- If a tool fails, lacks a feature, or you are not confident in it, use `ssh`, `scp` and other terminal commands directly. Say which path you used.
- Ask the user before deleting anything, on the media server or on this machine, and before changing system settings. Restarting Jellyfin does not need approval.
- Push only the final, subtitle-processed file to the media server, never the raw download. Refresh the Jellyfin library after every upload.
- Never store or print key contents, passwords, API keys or `.env` secrets. Never write real addresses, user names, key paths or real show or movie titles into tracked files or code comments; use placeholders such as `<server>` and `Example Show (2020)`.
- Keep the README, the diagrams (`docs/diagrams/`) and the code in step. Regenerate the diagrams with `scripts/render_diagrams.sh`.

Personal notes for a developer's own setup (real addresses, device notes) are kept outside the repository, loaded through a git-ignored `CLAUDE.local.md`.
