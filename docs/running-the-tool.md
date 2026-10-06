# Running the tool

If you just want a desktop icon that starts the tool, the novice edition
below is all you need; the rest of this document covers other ways to run 
it (`uv tool install`, `uvx`, a git checkout).

## Novice edition

Apologies that the next few steps are slightly hackerish. Simply following the
instructions should suffice not to have to touch the terminal again thereafter.

You'll want to download the launcher plus its icon image. The icon file 
is optional: with only the launcher, `--add-shortcut` still installs a 
working desktop icon—it just shows the platform's default icon.

Both files live in the `launchers/` directory of this repository: 
<https://github.com/SEIU-Tech/normalize-tabular-data/tree/main/launchers>.

For each platform below, download both files into one folder (e.g. your usual
`Downloads/` folder) and leave them side by side — the icon must sit next to 
the launcher when you run the install command.

### macOS

Download `normalize-tabular-data.sh` and `normalize-tabular-data.icns`

1. Open the `launchers` folder page in your browser.
2. Click `normalize-tabular-data.sh`, then click the "Download raw file" 
   button on the file page's toolbar. Save into `Downloads/`.
3. Go back one page, click `normalize-tabular-data.icns`, and download it the
   same way.
4. Open the Terminal app: press ⌘+&lt;space&gt;, type `Terminal`, press Enter.
5. Type these four lines, pressing Enter after each (you can drag the
   downloaded files' icons into the Terminal window instead of typing
   their names, which also spares you spelling mistakes):

   ```bash
   cd ~/Downloads
   xattr -c normalize-tabular-data.sh normalize-tabular-data.icns
   chmod +x normalize-tabular-data.sh
   ./normalize-tabular-data.sh --add-shortcut
   ```

   Line 2 clears the "downloaded from the internet" tag macOS puts on files
   fetched in a browser; without it, the first double-click will ask for a 
   security confirmation on each of the icon pieces.
6. A `Normalize Tabular Data.app` appears on the Desktop. Double-click it; 
   its first run downloads `uv`.
7. [Optional] the NTD application has windows, mouse control, buttons, etc.,
   but still runs in a terminal. To resize the font, use ⌘+&lt;plus&gt; and 
   ⌘+&lt;minus&gt; (same as in a web browser and other applications).

### Windows

Download `normalize-tabular-data.cmd` and `normalize-tabular-data.ico`

1. From `launchers/` directory, click `normalize-tabular-data.cmd` → 
   "Download raw file" → save into `Downloads`; then download 
   `normalize-tabular-data.ico` in the same manner. If the browser pops a 
   warning like "this file type can harm your computer", choose "Keep".
2. Open Command Prompt: click the **Start** button (or press ⊞ Win),
   type `cmd`, press Enter.
3. In the terminal window, type these two lines, pressing Enter after each:

   ```bat
   cd %USERPROFILE%\Downloads
   normalize-tabular-data.cmd --add-shortcut
   ```

4. A shortcut named "Normalize Tabular Data" appears on the Desktop.
   Double-click it to run (the `.ico` must stay next to the `.cmd` in
   `Downloads`, and the `.cmd` must not be renamed or moved—the shortcut 
   remembers where they both live).

## Programmer edition

### Persistent install

```bash
uv tool install normalize-tabular-data
# upgrade later with:
uv tool upgrade normalize-tabular-data
```

### Ephemeral run (no install)

`uvx` fetches into a throwaway environment each time:

```bash
uvx normalize-tabular-data
# pin a specific version:
uvx normalize-tabular-data==0.1.1
```

### From a git checkout

Within the directory of the cloned repository:

```bash
uv run normalize-tabular-data
```
