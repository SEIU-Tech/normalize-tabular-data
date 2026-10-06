# Running the tool

If you just want a desktop icon that starts the tool, the novice edition
below is all you need; the rest of this document covers the other ways
to run it (`uv tool install`, `uvx`, a git checkout) and the mechanics
behind the launchers.

## Downloading the two files (novice edition)

Both files live in `launchers/` of the GitHub repository
(<https://github.com/SEIU-Tech/normalize-tabular-data>). If that folder
is not visible on the `main` branch yet, use the branch picker and
choose `desktop-launchers`, or browse
<https://github.com/SEIU-Tech/normalize-tabular-data/tree/desktop-launchers/launchers>.

For each platform below, download **two files into one folder** (e.g.
your usual `Downloads` folder) and leave them side by side — the icon
must sit next to the launcher when you run the install command.

**macOS: download `normalize-tabular-data.sh` and
`normalize-tabular-data.icns`**

1. Open the `launchers` folder page in your browser.
2. Click `normalize-tabular-data.sh`, then click the
   **Download raw file** button on the file page's toolbar (an arrow
   pointing down into a tray — not right-click/save). Save into
   `Downloads`.
3. Go back one page, click `normalize-tabular-data.icns`, and download
   it the same way.
4. Open the Terminal app: press ⌘ + space, type `Terminal`, press Enter.
5. Type these four lines, pressing Enter after each (you can drag the
   downloaded files' icons into the Terminal window instead of typing
   their names, which also spares you spelling mistakes):

   ```bash
   cd ~/Downloads
   xattr -c normalize-tabular-data.sh normalize-tabular-data.icns
   chmod +x normalize-tabular-data.sh
   ./normalize-tabular-data.sh --add-shortcut
   ```

   Line 2 clears the "downloaded from the internet" tag macOS puts on
   files fetched in a browser; without it, the first double-click will
   ask for a security confirmation on each of the icon pieces.
6. A `Normalize Tabular Data.app` appears on the Desktop. Double-click
   it; its first run downloads uv and nothing else.

**Windows: download `normalize-tabular-data.cmd` and
`normalize-tabular-data.ico`**

1. Same page, click `normalize-tabular-data.cmd` → **Download raw
   file** → save into `Downloads`; then do
   `normalize-tabular-data.ico`. If the browser pops a warning like
   "this file type can harm your computer", choose **Keep** — a `.cmd`
   is just a text script, and this one is a plain, readable file.
2. Open Command Prompt: click the **Start** button (or press ⊞ Win),
   type `cmd`, press Enter.
3. In the black window, type these two lines, pressing Enter after each:

   ```bat
   cd %USERPROFILE%\Downloads
   normalize-tabular-data.cmd --add-shortcut
   ```

4. A shortcut named **Normalize Tabular Data** appears on the Desktop.
   Double-click it to run (the `.ico` must stay next to the `.cmd` in
   `Downloads`, and the `.cmd` must not be renamed or moved — the
   shortcut remembers where they both live).

## Persistent install

```bash
uv tool install normalize-tabular-data
# upgrade later with:
uv tool upgrade normalize-tabular-data
```

## Ephemeral run (no install)

`uvx` fetches into a throwaway environment each time:

```bash
uvx normalize-tabular-data
# pin a specific version:
uvx normalize-tabular-data==0.1.1
```

## From a git checkout

Within the directory of the cloned repository:

```bash
uv run normalize-tabular-data
```

## Single-file launchers

`launchers/` holds two standalone files that both install `uv` (if it is
not already present) and then run the app through `uvx` — nothing else
has to be installed first:

- **Linux & macOS** — `normalize-tabular-data.sh`, a POSIX shell script.
  Make it executable and run it (`chmod +x normalize-tabular-data.sh &&
  ./normalize-tabular-data.sh`); it needs `curl` or `wget` on the first
  run to fetch the uv installer.
- **Windows** — `normalize-tabular-data.cmd`, a batch file. Double-click
  it or run it from a terminal (`normalize-tabular-data.cmd`); it uses
  PowerShell (present on all supported Windows systems) to fetch the uv
  installer, and passes any command-line arguments through to the app.

Both run `uvx normalize-tabular-data`, caching uv and the package after
the first launch, so the first run needs network access and later runs
do not.

## Desktop icon

Each launcher can also install itself as a desktop icon that starts the
application on double-click:

```bash
# macOS: a "Normalize Tabular Data.app" on your Desktop
./normalize-tabular-data.sh --add-shortcut
```

```bat
rem Windows: a "Normalize Tabular Data" shortcut on your Desktop
normalize-tabular-data.cmd --add-shortcut
```

The macOS icon is a minimal application bundle on the Desktop (built
from `normalize-tabular-data.icns` beside the launcher) whose stub
executes the launcher in Terminal and exits; on Windows it is a `.lnk`
shortcut pointing at the `.cmd` file, iconed from
`normalize-tabular-data.ico` beside it, so moving or deleting those
files moves or breaks the icon. Re-running `--add-shortcut` refreshes
the icon. The first double-click still installs uv and the package
itself if they are missing; later launches are cached and offline.

### How many files?

The smallest set that installs a desktop icon **with the custom
artwork** is **two files per platform** — the launcher plus its icon
image:

- **macOS** — `normalize-tabular-data.sh` +
  `normalize-tabular-data.icns`. The bundle is generated: the `.plist`,
  the `launch` stub and the `Resources/` command copy come out of the
  `.sh` itself, and the one embedded asset (the `.icns`) is copied in.
- **Windows** — `normalize-tabular-data.cmd` +
  `normalize-tabular-data.ico`. The `.lnk` is generated, but since a
  `.cmd` cannot carry icon data itself, the icon lives in the second
  file and the shortcut references it by path.

Either icon file is optional: with only the launcher, `--add-shortcut`
still installs a working desktop icon — it just shows the platform's
default icon (and the Windows side skips the icon pass silently). So
the true one-file minimum gets you a functional icon; the second file buys
the custom art. See [creating-icons.md](creating-icons.md) for where
the art comes from.

### The icon art

The purple table-and-check artwork is generated by a short Pillow script
— how the art is drawn and where each platform picks it up is described
in [creating-icons.md](creating-icons.md).
