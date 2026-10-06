#!/bin/sh
# Launcher: installs uv (the toolkit's runner) if missing, then runs
# normalize-tabular-data in an ephemeral uvx environment.
# Works on Linux and macOS; chmod +x this file (or run `sh <file>`).
# EXTRA: "--add-shortcut" (macOS) copies this launcher onto the Desktop
# as a double-clickable "Normalize Tabular Data.command" file.

set -eu

if [ "${1:-}" = "--add-shortcut" ]; then
    if [ "$(uname -s)" = "Darwin" ]; then
        # Finder runs .command files with Terminal; a bare .sh only opens
        # in an editor, so the desktop copy carries the .command suffix
        dest="$HOME/Desktop/Normalize Tabular Data.command"
        if cp "$0" "$dest" && chmod +x "$dest"; then
            echo "Created desktop launcher: $dest"
            echo "Double-click it to run the application (its first run"
            echo "installs uv if it is not present yet)."
        else
            echo "Could not write $dest" >&2
            exit 1
        fi
    else
        echo "--add-shortcut only applies to macOS; on Windows instead run" >&2
        echo "normalize-tabular-data.cmd --add-shortcut" >&2
        exit 1
    fi
    exit 0
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
