# Changelog

## 0.1.4 - 2026-06-15

- Added a first-run setup guide for new users.
- Documented Python dependency installation, local config creation, MuMu ADB setup, screenshot diagnosis, dry-run checks, and startup scripts.

## 0.1.3 - 2026-06-15

- Added detection for the in-game energy-saving idle screen.
- Added an automatic center-screen tap to return from energy-saving mode.

## 0.1.2 - 2026-06-15

- Added a template-based blacklist for friends who disallow spectating.
- Added `全剧终` to the default blacklist templates.
- Changed the no-target behavior on the friend list to wait for the main interval instead of swiping immediately.

## 0.1.1 - 2026-06-15

- Restricted friend watch target detection to the exact `正在进行[闪耀大赛]` status.
- Added a dedicated green-pixel template for the `闪耀大赛` status text.
- Disabled generic green-status fallback by default to avoid teleporting to non-PVP friends.

## 0.1.0 - 2026-06-15

- Added ADB device discovery and MuMu third-instance defaults.
- Added automated spectator workflow for friend PVP watching.
- Added template-based scene recognition with assets under `assets/templates`.
- Added green-status scanning for watchable friend rows.
- Added fixed-coordinate `juneng` clicker for the energy button.
- Added Windows startup scripts for auto-watch and juneng clicker.
