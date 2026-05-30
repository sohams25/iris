#!/usr/bin/env bash
# iris/setup.sh — bootstrap iris into the target Claude Code project.
#
# Usage:
#   bash ~/Tools/iris/setup.sh                       # interactive
#   bash ~/Tools/iris/setup.sh --target /path/to/project --yes
#
# What it does:
#   1. Symlinks .claude/{commands,hooks,skills} from iris into the target
#   2. Symlinks scripts/ from iris into the target
#   3. Copies CLAUDE.md (template) and docs/plan.md (template) if not present
#   4. Copies .env.example if not present
#   5. Offers to clone optional skill sources (~/Tools/superpowers + stop-slop)
#   6. Runs scripts/doctor.py and prints the verdict

set -euo pipefail

IRIS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${PWD}"
ASSUME_YES=0

while [ $# -gt 0 ]; do
    case "$1" in
        --target) TARGET="$2"; shift 2 ;;
        --yes|-y) ASSUME_YES=1; shift ;;
        --help|-h)
            sed -n '2,15p' "$0"; exit 0 ;;
        *)
            echo "unknown flag: $1" >&2; exit 1 ;;
    esac
done

TARGET="$(cd "$TARGET" && pwd)"
echo "iris source: $IRIS_ROOT"
echo "target:      $TARGET"

if [ "$IRIS_ROOT" = "$TARGET" ]; then
    echo "error: target equals source; cd into your project first" >&2
    exit 1
fi

ask() {
    [ "$ASSUME_YES" = 1 ] && return 0
    local prompt="$1"
    read -rp "$prompt [y/N] " ans
    [[ "$ans" =~ ^[Yy]$ ]]
}

link() {
    local src="$1"
    local dst="$2"
    if [ -e "$dst" ] && [ ! -L "$dst" ]; then
        echo "  skip (exists): $dst"
        return 0
    fi
    if [ -L "$dst" ] && [ "$(readlink -f "$dst")" = "$(readlink -f "$src")" ]; then
        echo "  ok   (linked): $dst"
        return 0
    fi
    ln -sfn "$src" "$dst"
    echo "  link        : $dst -> $src"
}

# ----- 1. .claude/ symlinks -------------------------------------------------
echo
echo "[1/5] .claude/ surface"
mkdir -p "$TARGET/.claude"
link "$IRIS_ROOT/.claude/commands"  "$TARGET/.claude/commands"
link "$IRIS_ROOT/.claude/hooks"     "$TARGET/.claude/hooks"
link "$IRIS_ROOT/.claude/settings.json" "$TARGET/.claude/settings.json"

mkdir -p "$TARGET/.claude/skills"
for skill in handovers swarm commit-style karpathy-guidelines; do
    link "$IRIS_ROOT/.claude/skills/$skill" "$TARGET/.claude/skills/$skill"
done

# ----- 2. scripts/ symlinks -------------------------------------------------
echo
echo "[2/5] scripts/"
mkdir -p "$TARGET/scripts"
for f in "$IRIS_ROOT"/scripts/*.py "$IRIS_ROOT"/scripts/*.sh; do
    link "$f" "$TARGET/scripts/$(basename "$f")"
done

# ----- 3. templates ---------------------------------------------------------
echo
echo "[3/5] templates"
for tpl in CLAUDE.md .env.example; do
    if [ ! -e "$TARGET/$tpl" ]; then
        cp "$IRIS_ROOT/$tpl" "$TARGET/$tpl"
        echo "  copy        : $TARGET/$tpl"
    else
        echo "  skip (exists): $TARGET/$tpl"
    fi
done
mkdir -p "$TARGET/docs"
if [ ! -e "$TARGET/docs/plan.md" ]; then
    cp "$IRIS_ROOT/docs/plan.md" "$TARGET/docs/plan.md"
    echo "  copy        : $TARGET/docs/plan.md"
fi
if [ ! -e "$TARGET/docs/next.md" ]; then
    cp "$IRIS_ROOT/docs/next.md" "$TARGET/docs/next.md"
    echo "  copy        : $TARGET/docs/next.md  (plan-ahead queue)"
fi
if [ ! -e "$TARGET/.env" ]; then
    cp "$IRIS_ROOT/.env.example" "$TARGET/.env"
    echo "  copy        : $TARGET/.env  (edit before first use)"
fi

# scaffold the projects dir so /new-task and doctor's projects-dir check are
# coherent on first run (rename via PROJECTS_DIR in .env; default Projects)
PROJECTS_DIR_NAME="${PROJECTS_DIR:-Projects}"
mkdir -p "$TARGET/$PROJECTS_DIR_NAME"
echo "  mkdir       : $TARGET/$PROJECTS_DIR_NAME/"

# ----- 4. optional dependencies --------------------------------------------
echo
echo "[4/5] optional skill sources"
if [ ! -d "$HOME/Tools/superpowers" ]; then
    if ask "  install superpowers (14 skills) at ~/Tools/superpowers ?"; then
        git clone --depth 1 https://github.com/obra/superpowers.git "$HOME/Tools/superpowers"
    else
        echo "  skip          superpowers"
    fi
else
    echo "  already at ~/Tools/superpowers"
fi
# Wire skill symlinks whether superpowers was just cloned or already present.
if [ -d "$HOME/Tools/superpowers/skills" ]; then
    for s in "$HOME"/Tools/superpowers/skills/*/; do
        [ -d "$s" ] || continue
        ln -sfn "$s" "$TARGET/.claude/skills/$(basename "$s")"
    done
    echo "  link        : superpowers skills -> $TARGET/.claude/skills/"
fi

if [ ! -d "$HOME/Tools/stop-slop" ]; then
    if ask "  install stop-slop at ~/Tools/stop-slop ?"; then
        git clone --depth 1 https://github.com/hardikpandya/stop-slop.git "$HOME/Tools/stop-slop"
    else
        echo "  skip          stop-slop"
    fi
else
    echo "  already at ~/Tools/stop-slop"
fi
# Wire the stop-slop symlink whether just cloned or already present.
if [ -d "$HOME/Tools/stop-slop" ]; then
    ln -sfn "$HOME/Tools/stop-slop" "$TARGET/.claude/skills/stop-slop"
    echo "  link        : stop-slop -> $TARGET/.claude/skills/stop-slop"
fi

# ----- 5. doctor ------------------------------------------------------------
echo
echo "[5/5] doctor"
cd "$TARGET"
python3 scripts/doctor.py || {
    echo
    echo "doctor reported issues. Resolve them, then re-run scripts/doctor.py."
    exit 1
}

cat <<EOF

iris installed into $TARGET

Next:
  1. Edit $TARGET/.env with your config (memory backend, optional Slack creds).
  2. Edit $TARGET/CLAUDE.md to add your project's standing instructions.
  3. Open a Claude Code session at $TARGET and try /status.

EOF
