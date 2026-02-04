#!/bin/bash
#
# Triad Init Script
# Initializes Triad workflow in a project directory
#
# Usage:
#   /projects/triad/scripts/init.sh [target_dir]
#
# If no target_dir specified, uses current directory.
# Detects if project is new (empty) or existing (has files).
#

set -e

TRIAD_ROOT="/projects/triad"
TEMPLATES_DIR="$TRIAD_ROOT/scripts/templates"
TARGET_DIR="${1:-.}"

# Resolve to absolute path
TARGET_DIR="$(cd "$TARGET_DIR" && pwd)"
PROJECT_NAME="$(basename "$TARGET_DIR")"

echo "=== Triad Init ==="
echo "Project: $PROJECT_NAME"
echo "Path: $TARGET_DIR"
echo ""

# Check if triad/ already exists
if [ -d "$TARGET_DIR/triad" ]; then
    echo "Error: triad/ directory already exists in $TARGET_DIR"
    echo "If you want to reinitialize, remove the triad/ directory first."
    exit 1
fi

# Count files (excluding hidden files and directories)
FILE_COUNT=$(find "$TARGET_DIR" -maxdepth 1 -type f ! -name ".*" 2>/dev/null | wc -l)
DIR_COUNT=$(find "$TARGET_DIR" -maxdepth 1 -type d ! -name ".*" ! -path "$TARGET_DIR" 2>/dev/null | wc -l)

TOTAL_COUNT=$((FILE_COUNT + DIR_COUNT))

echo "Detected $TOTAL_COUNT items in project root."
echo ""

# Create triad directory
mkdir -p "$TARGET_DIR/triad"

if [ "$TOTAL_COUNT" -eq 0 ]; then
    # NEW PROJECT MODE
    echo "Mode: NEW PROJECT"
    echo ""
    echo "This is an empty directory. Triad will help you define the project."
    echo ""
    echo "Scaffolding created. Next steps:"
    echo "  1. cd $TARGET_DIR"
    echo "  2. Open Claude: claude"
    echo "  3. Tell Claude: 'This is a new project. Run the Triad new project Q&A.'"
    echo ""
    echo "Claude will guide you through defining the project, then create your PLAN.md."

    # Copy new project template
    cp "$TEMPLATES_DIR/NEW_PROJECT.md" "$TARGET_DIR/triad/NEW_PROJECT.md"
    cp "$TEMPLATES_DIR/AGENTS_STATE.md" "$TARGET_DIR/triad/AGENTS_STATE.md"

    # Update AGENTS_STATE with new project status
    sed -i "s/{{PROJECT_NAME}}/$PROJECT_NAME/g" "$TARGET_DIR/triad/AGENTS_STATE.md"
    sed -i "s/{{STATUS}}/New project - awaiting definition/g" "$TARGET_DIR/triad/AGENTS_STATE.md"

else
    # EXISTING PROJECT MODE
    echo "Mode: EXISTING PROJECT"
    echo ""
    echo "Detected existing codebase. Creating Triad scaffolding."

    # Copy all templates
    cp "$TEMPLATES_DIR/PLAN.md" "$TARGET_DIR/triad/PLAN.md"
    cp "$TEMPLATES_DIR/DECISIONS.md" "$TARGET_DIR/triad/DECISIONS.md"
    cp "$TEMPLATES_DIR/AGENTS_STATE.md" "$TARGET_DIR/triad/AGENTS_STATE.md"
    cp "$TEMPLATES_DIR/GEMINI.md" "$TARGET_DIR/triad/GEMINI.md"

    # Update placeholders
    sed -i "s/{{PROJECT_NAME}}/$PROJECT_NAME/g" "$TARGET_DIR/triad/"*.md
    sed -i "s/{{STATUS}}/Existing project - awaiting analysis/g" "$TARGET_DIR/triad/AGENTS_STATE.md"

    echo ""
    echo "Scaffolding created. Next steps:"
    echo "  1. cd $TARGET_DIR"
    echo "  2. Open Claude: claude"
    echo "  3. Tell Claude: 'Analyze this project and prepare triad/PLAN.md'"
    echo ""
    echo "Claude will review the codebase and create an actionable plan."
fi

# Copy scripts to project
echo "Copying Triad scripts..."
mkdir -p "$TARGET_DIR/scripts"
cp "$TRIAD_ROOT/scripts/slack_post.sh" "$TARGET_DIR/scripts/"
cp "$TRIAD_ROOT/scripts/slack_new_project.sh" "$TARGET_DIR/scripts/"
chmod +x "$TARGET_DIR/scripts/slack_post.sh"
chmod +x "$TARGET_DIR/scripts/slack_new_project.sh"

# Copy .gitignore if it doesn't exist
if [ ! -f "$TARGET_DIR/.gitignore" ]; then
    echo "Creating .gitignore..."
    cp "$TRIAD_ROOT/.gitignore" "$TARGET_DIR/.gitignore"
else
    # Ensure .env is in .gitignore
    if ! grep -q "^\.env$" "$TARGET_DIR/.gitignore"; then
        echo ".env" >> "$TARGET_DIR/.gitignore"
        echo "Added .env to existing .gitignore"
    fi
fi

# Copy .env.example if it doesn't exist
if [ ! -f "$TARGET_DIR/.env.example" ]; then
    echo "Creating .env.example..."
    cp "$TEMPLATES_DIR/.env.example" "$TARGET_DIR/.env.example"
    # Update channel name placeholder with project name
    sed -i "s/triad-yourproject/triad-$PROJECT_NAME/g" "$TARGET_DIR/.env.example"
fi

echo ""
echo "Files created in $TARGET_DIR/triad/:"
ls -la "$TARGET_DIR/triad/"
echo ""
echo "Scripts copied to $TARGET_DIR/scripts/:"
ls -la "$TARGET_DIR/scripts/"
echo ""
echo "Environment setup:"
echo "  1. Copy .env.example to .env: cp .env.example .env"
echo "  2. Add your SLACK_BOT_TOKEN to .env"
echo "  3. Run: ./scripts/slack_new_project.sh $PROJECT_NAME"
echo ""
echo "=== Triad Init Complete ==="
