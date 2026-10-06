# Creating the launcher icons

![Launcher icon](../launchers/icon_256.png)

**The icon art** — `launchers/make_icon.py` (a short Pillow script)
generates a purple squircle with a white data-table glyph and an amber
check (*data cleaned* over *table*) in three forms:
`normalize-tabular-data.ico` (Windows), `normalize-tabular-data.icns`
(macOS), and an `icon_256.png` preview. Regenerating it is:

```bash
uv run --with pillow python launchers/make_icon.py
```

Edit the shapes/colors in the script to restyle, then re-run
`--add-shortcut` on either platform to refresh the desktop icon. The
current art is a placeholder built from scratch; if you have a real SEIU
logo file, it can drop in anywhere a source PNG/`Image` goes.

**macOS** — `--add-shortcut` no longer drops a bare `.command` file
(which can't carry a custom icon without resource-fork surgery); it now
builds a proper `Normalize Tabular Data.app` bundle on the Desktop:

- `Contents/Info.plist` declares the name, bundle id
  `org.seiutech.normalize-tabular-data.launcher`, and
  `CFBundleIconFile = AppIcon`, so Finder shows the `.icns`.
- `Contents/MacOS/launch` is a four-line stub that resolves its own path
  absolutely and `open -a Terminal`s the launcher copy in `Resources/` —
  the TUI still gets a terminal, the app process exits after handing off.
- The launcher copy in `Resources/` is what Terminal actually runs, so
  uv-install logic is unchanged.

If the `.icns` is not found beside the launcher, the bundle is still
built and simply shows macOS's default application icon.

**Windows** — the `.lnk` now gets `IconLocation` pointing at
`normalize-tabular-data.ico` beside the `.cmd`. The icon assignment
happens in a second PowerShell pass after the shortcut exists, and skips
silently if the `.ico` isn't there — a standalone `.cmd` without the
icon file still makes a working, default-iconed shortcut. (This is the
one wrinkle worth knowing: a `.cmd` can't embed icon data itself, only
`.exe`/`.lnk` carry icons, so the shortcut references an external file.)

**Refreshing an installed icon** — on macOS, swapping the art and
re-running `--add-shortcut` rebuilds the whole bundle, so Finder
refreshes the icon automatically — no need to log out or toggle caches;
on Windows, the shortcut is overwritten in place, same story.
