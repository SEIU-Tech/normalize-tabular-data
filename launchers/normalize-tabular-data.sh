#!/bin/sh
# Launcher: installs uv (the toolkit's runner) if missing, then runs
# normalize-tabular-data in an ephemeral uvx environment.
# Works on Linux and macOS; chmod +x this file (or run `sh <file>`).
# EXTRA: "--add-shortcut" (macOS) builds a "Normalize Tabular Data.app"
# bundle on the Desktop, iconed from normalize-tabular-data.icns beside
# this file (default icon when it is missing), that double-clicks into
# Terminal.

set -eu

if [ "${1:-}" = "--add-shortcut" ] && [ "$(uname -s)" = "Darwin" ]; then
    # a bare .command opens Terminal but cannot carry a custom icon; a
    # minimal .app bundle can. The bundle's only job is to hand the
    # command script (the launcher itself) to Terminal, then exit.
    app="$HOME/Desktop/Normalize Tabular Data.app"
    res="$app/Contents/Resources"
    rm -rf "$app" "$HOME/Desktop/Normalize Tabular Data.command"
    mkdir -p "$app/Contents/MacOS" "$res"
    cat > "$app/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>Normalize Tabular Data</string>
    <key>CFBundleDisplayName</key><string>Normalize Tabular Data</string>
    <key>CFBundleIdentifier</key><string>org.seiutech.normalize-tabular-data.launcher</string>
    <key>CFBundleExecutable</key><string>launch</string>
    <key>CFBundleIconFile</key><string>AppIcon</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleShortVersionString</key><string>1</string>
    <key>CFBundleVersion</key><string>1</string>
</dict>
</plist>
PLIST
    cp "$0" "$res/Normalize Tabular Data.command"
    if [ -f "$(dirname "$0")/normalize-tabular-data.icns" ]; then
        cp "$(dirname "$0")/normalize-tabular-data.icns" "$res/AppIcon.icns"
    fi
    {
        echo '#!/bin/sh'
        echo '# bundle stub: hand the real command script to Terminal, then exit'
        echo 'self="$0"'
        echo 'case $self in /*) ;; *) self="$PWD/$self" ;; esac'
        echo 'exec /usr/bin/open -a Terminal "${self%/*}/../Resources/Normalize Tabular Data.command"'
    } > "$app/Contents/MacOS/launch"
    chmod +x "$res/Normalize Tabular Data.command" "$app/Contents/MacOS/launch"
    echo "Created desktop app bundle: $app"
    echo "Double-click it to run the application (its first run installs"
    echo "uv if it is not present yet). A stray '.command' copy from"
    echo "earlier launcher versions was removed in favor of the bundle."
    exit 0
fi

if [ "${1:-}" = "--add-shortcut" ]; then
    echo "--add-shortcut only applies to macOS; on Windows instead run" >&2
    echo "normalize-tabular-data.cmd --add-shortcut" >&2
    exit 1
fi

if ! command -v uvx >/dev/null 2>&1; then
    echo "uv is not installed yet; retrieving the installer..." >&2
    case "$(uname -s)" in
        Linux|Darwin)
            # the official one-line installer puts uvx in ~/.local/bin
            if command -v curl >/dev/null 2>&1; then
                curl -LsSf https://astral.sh/uv/install.sh | sh
            elif command -v wget >/dev/null 2>&1; then
                wget -qO- https://astral.sh/uv/install.sh | sh
            else
                echo "This launcher needs curl or wget to fetch uv." >&2
                echo "Install uv first: https://docs.astral.sh/uv/getting-started/installation/" >&2
                exit 1
            fi
            ;;
        *)
            echo "Unsupported system: $(uname -s). Install uv from" >&2
            echo "https://docs.astral.sh/uv/getting-started/installation/" >&2
            exit 1
            ;;
    esac
    # the installer does not update the PATH of a running shell
    PATH="$HOME/.local/bin:$PATH"
    export PATH
    if ! command -v uvx >/dev/null 2>&1; then
        echo "uv was installed but uvx is still not on the PATH; open a" >&2
        echo "new terminal and rerun this launcher." >&2
        exit 1
    fi
fi

# uvx resolves, caches and runs the tool (first run also downloads it)
exec uvx normalize-tabular-data
