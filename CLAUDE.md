# prowlMCP

Local MCP server (Prowlarr, qBittorrent, Jellyfin) plus the media-server media server it delivers to. Project memory is versioned in `docs/memory/`. It is the same set of notes as the Claude memory folder, and it works in any checkout or worktree.

## Read the memory notes first

At the start of every session in this repo, use these notes before acting. The first five are imported below. Read the sixth whenever you touch the server, the file layout, subtitles or Jellyfin, or when an MCP tool fails. Then call `list_jobs` and tell the user what happened while they were away.

@docs/memory/when-to-use-what.md
@docs/memory/prowl-mcp-usage.md
@docs/memory/mcp-first-terminal-fallback.md
@docs/memory/transfer-processed-file-only.md
@docs/memory/jellyfin-restart-no-approval.md

- `docs/memory/media-server-end-to-end.md`: SSH and copy commands, folder layout, subtitles, Jellyfin, Samba and Tailscale, and the server state verified 2026-11-06.
- `docs/memory/MEMORY.md`: the index.

## Working rules

- Short, interactive work goes through the prowl-mcp tools. Long or unattended work (waiting for a download, subtitles, transfer) goes through the `prowl` CLI as a background Bash task, or the systemd worker. See `when-to-use-what.md`.
- If a tool fails, lacks a feature, or you are not confident in it, use `ssh`, `scp` and other terminal commands directly. Say which path you used.
- Ask the user before deleting anything, on the media server or on this PC, and before changing system settings. Restarting Jellyfin does not need approval.
- Never store or print key contents, passwords, API keys or `.env` secrets.
- When a memory note changes, update both copies: `docs/memory/` and `~/.claude/projects/<this-project>/memory/`.
