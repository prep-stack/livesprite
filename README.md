# LiveSprite

Animated GIF sprites that walk around your desktop, with Twitch **and**
YouTube live-stream notifications. This is a from-scratch rewrite of the
old program keeping only the basics.

## Run

```
python main.py
```

Requires Python 3 with PyQt5 and requests (see requirements.txt).

## Look and feel

Since v2.1.0 the whole UI uses a modern dark theme (deep navy background,
purple accents) defined in `theme.py`. It is a single Qt Style Sheet
applied in `main.py` - purely cosmetic, so removing the
`theme.apply(app)` line restores the classic system look.

## Versions and updates

The program version lives in `version.py`. The "Check for updates"
button in the top bar asks GitHub for the newest release of
`prep-stack/livesprite`; when a newer release exists the button turns
into "Update now" and installs it in place. Updates never touch
`config/` (session, positions, settings) or sprites the user added.

### Releasing a new version (for the developer)

1. Edit `version.py` and bump `VERSION`, e.g. to `"2.1.0"`
2. Run `release.bat 2.1.0` - it builds the exe, zips it, commits, tags
   `v2.1.0` and pushes to GitHub, then opens the release page
3. On the release page: attach `dist\LiveSprite-v2.1.0.zip`, write some
   release notes and press "Publish release"

That's it - every installed copy of the program will offer the update.

## Build a .exe

Double-click `build_exe.bat` (or run `pyinstaller LiveSprite.spec`).
The finished program ends up in `dist\LiveSprite\LiveSprite.exe`.

The `assets\` and `config\` folders are copied next to the exe as normal
folders, so you can add new sprite folders and change settings without
rebuilding. The whole `dist\LiveSprite` folder is portable - copy it
anywhere and run the exe.

## How it works

- **System tray**: the program lives in the notification area (hidden
  icons). Closing the manager window hides it to the tray; click the
  tray icon to reopen it. Right-click the tray icon for quick actions:
  show all / hide all active gifs, restrict all active gifs to screens,
  and Quit (the only way to really exit).
- **Manager window**: two panels with animated GIF previews. Left panel
  shows every folder in `assets/` (double-click to add), right panel
  shows the active gifs on the desktop (double-click to remove) with
  their stream channel and live status. `Settings...` opens the selected
  sprite's configuration. Global buttons (Show all / Hide all /
  Restrict all...) mirror the tray menu. The active sprites and their
  positions are remembered in `config/session.json`.
- **Sprites**: transparent, always-on-top windows. The on-top flag is
  re-asserted every 5 seconds (and after drags and live notifications)
  with a NOTOPMOST->TOPMOST flip, so sprites recover quickly even when
  other always-on-top windows (Discord, fullscreen browser video) push
  above them. Right-click a sprite to toggle "Keep on top" off for that
  sprite (saved per sprite). Each GIF in the asset
  folder is an animation with a chance (%), a walk direction, a movement
  speed (pixels per step) and a playback speed (% - 100 is normal, 200 is
  twice as fast). At the end of each GIF loop there is a 20% chance to
  switch to another animation.
- **Auto-refresh**: the asset list updates automatically when you add or
  remove folders in `assets/` - no need to press Refresh.
- **Screens**: sprites move across all monitors. Checking "Restrict
  screen N" in the settings makes the sprite skip over that screen —
  it jumps to the next allowed screen in its direction of travel.
  Edge behavior can be `wrap` (default, pass through one edge and appear
  on the other side), `bounce` or `stop`.
- **Start with Windows**: on by default. Uses the per-user registry Run
  key, no admin rights needed. The checkbox in the manager window only
  appears when autostart is actually off (checked against the registry) -
  tick it and it registers and disappears again. Turning autostart off
  is done from the tray menu ("Start with Windows" toggle).
- **Remembered positions**: when you drag a sprite somewhere, that spot
  is remembered permanently (in `config/session.json` under
  `positions`). The sprite spawns there on every program start, and even
  when you remove it and add it back later. Brand-new sprites spawn in
  the middle of the screen until you move them once.
- **Live notification**: set a Twitch channel (e.g. `sodapoppin`), a
  YouTube channel (e.g. `@handle`) and/or a Kick channel (e.g. `xqc`),
  pick the preferred platform and a "live animation". The channel is
  checked about every 60 seconds (with a random +/- 15 s jitter) in the
  background (Twitch via decapi.me, Kick via its public channel API - no
  API keys needed anywhere). For YouTube there are two selectable check
  methods in the settings: **Web scrape** (default), which loads
  `youtube.com/<handle>/live` directly and looks for the live marker -
  the most reliable way - or **DecAPI**. When the streamer goes
  live the sprite switches to the live animation and stays in it until
  you double-click the sprite, which opens the stream page in your
  browser (a single click does nothing, so you can't open it by
  accident while grabbing the sprite). Per sprite you can also enable
  "Hide sprite while offline" and, on top of that, "Hide again after
  the live notification was clicked" - then the sprite only ever
  appears to tell you a stream started, and disappears again once
  you've clicked it, until the next stream.
  When the stream ends everything resets so you get notified again next
  time. Right-click a sprite to see the live status or close it.

## Sprite packs (community content)

The **Browse packs...** button opens the community sprite-pack browser.
Packs live in the public repo
[prep-stack/livesprite_gifs](https://github.com/prep-stack/livesprite_gifs)
(one folder per pack with a `pack.json` manifest); the browser shows an
animated preview, name, creator and version for each pack and installs
them into `assets/` with one click. Anyone can contribute a pack via
Pull Request - see that repo's README.

Installed packs carry a hidden `.pack.json` marker with their version.
Shortly after startup the program quietly checks for pack updates (one
GitHub API call); updatable sprites get a purple **"⬆ update
available"** badge right in the Assets panel and a status-bar hint.
Updating a pack overwrites its GIFs but **never** your settings
(channels, chances, directions). Folders you created by hand have no
marker and are never touched. Sprites that are on the desktop are
briefly deactivated during their update and respawn at the same spot.

Sprites don't hold their GIF files open (they play from memory), so
packs can be updated - and asset folders deleted - while sprites are
active. **Delete files...** (button or right-click on an asset) removes
a sprite folder from disk after a confirmation.

## Adding a new sprite

Create a folder in `assets/` and drop GIF files into it. Filenames
containing `run`/`walk` plus `left`/`right`/`up`/`down` automatically get
a matching walk direction; everything can be changed in `Settings...`.
A PNG in the folder is used as the icon in the manager list.

## Files

| File | Purpose |
| --- | --- |
| `main.py` | entry point |
| `config.py` | constants and JSON helpers |
| `sprite_model.py` | asset folder loading + per-sprite settings.json |
| `sprite_window.py` | the walking sprite window (movement, edges, drag, click) |
| `stream_service.py` | Twitch/YouTube live polling in a background thread |
| `main_window.py` | the manager window (preview panels, global actions) + session restore |
| `tray.py` | system tray icon with quick actions |
| `settings_dialog.py` | per-sprite settings UI |
| `theme.py` | modern dark theme (colors + Qt stylesheet, pure cosmetics) |
| `pack_service.py` | community sprite packs: fetch/cache/install/update |
| `pack_browser.py` | the "Browse packs..." dialog |
| `soda.png` / `soda.ico` | application icon (window, tray and exe) |
| `_migrate_old_settings.py` | one-off import of old AppData settings (safe to delete) |
