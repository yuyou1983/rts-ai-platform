---
adapter:
  language: gdscript
  display_name: "GDScript (Godot Engine)"
  version: "1.0"

  detection:
    files: [project.godot, .godot/]
    content_patterns:
      - file: "project.godot"
        pattern: 'config/features.*=.*PackedStringArray.*4\.'
    confidence: 0.95

  commands:
    build: null  # Godot exports, not traditional builds
    test: "godot --headless --script-runner tests/test_runner.gd"
    lint: null  # Use gdformat / gdlint if available
    lint_arch: "python3 scripts/lint_deps.py src/"
    format: "gdformat ."
    start: "godot --path ."
    dev: "godot --path . --editor"

  package_manager:
    detection: []  # Godot uses its own asset library
    default: null
    install_command: null

  route_detection:
    server_indicators: []  # Godot is a game engine, not a web server
    cli_indicators: []
    frontend_indicators:
      - pattern: 'extends (Control|Node2D|Node3D|CanvasItem|SceneTree)'
        description: "Godot scene node (UI/game object)"
        frameworks: ["godot"]
      - pattern: 'class_name|@export|@onready|@tool'
        description: "Godot class/metadata annotations"
        frameworks: ["godot"]
    patterns:
      - type: game_scene
        pattern: 'extends Node2D|extends Node3D|extends CharacterBody'
        description: "Game scene root node"
      - type: ui_control
        pattern: 'extends Control|extends Panel|extends Button'
        description: "UI control node"
      - type: autoload
        pattern: 'extends Node\nclass_name.*AutoLoad|extends Node\n# AutoLoad'
        description: "Global autoload singleton"

  import_analysis:
    list_packages: null  # No standard package listing
    import_pattern: 'preload\\(["\x27]([^"\x27]+)["\x27]\\)|load\\(["\x27]([^"\x27]+)["\x27]\\)|const \\w+ = preload'
    source_extensions: [.gd, .tscn, .tres]
    module_root_file: "project.godot"

  layer_conventions:
    patterns:
      - layer: 0
        paths: ["proto", "shared", "common", "types"]
        description: "Protocol/types layer — protobuf definitions, shared constants"
      - layer: 1
        paths: ["simcore", "core", "engine", "logic"]
        description: "SimCore/engine layer — game simulation logic, state management"
      - layer: 2
        paths: ["agents", "ai", "tactical"]
        description: "Agent/AI layer — agent decision-making, tactical reasoning"
      - layer: 3
        paths: ["scenes", "ui", "rendering", "frontend"]
        description: "Frontend/rendering layer — Godot scenes, visual presentation"
      - layer: 4
        paths: ["main", "entry", "project.godot"]
        description: "Entry points — project root, main scene, exports"

  dependency_detection:
    manifest_file: "project.godot"
    databases: []
    services: []
    env_var_patterns: []

  linter:
    template_section: "gdscript"
    script_extension: ".py"  # Python-based lint scripts for cross-project consistency
    run_command: "python3 scripts/lint_deps.py src/"

  naming:
    file_pattern: "snake_case"
    test_pattern: "test_*.gd | *_test.gd"
    directory_style: "snake_case"

  ci:
    github_actions:
      image: "ubuntu-latest"
      setup_steps:
        - name: "Install Godot"
          run: "wget -q https://github.com/godotengine/godot/releases/download/4.4.1-stable/Godot_v4.4.1-stable_linux.x86_64.zip -O godot.zip && unzip -q godot.zip && sudo mv Godot_v* /usr/local/bin/godot"
      cache_paths: [".godot/"]
---

# GDScript Adapter (Godot Engine 4.x)

Language adapter for GDScript projects, specifically targeting Godot 4.4.1+ game
engine projects.

## Multi-Language Project Support

RTS-AI-Platform is a **multi-language project**:
- **Python** — SimCore headless engine, agents, training, ML pipeline
- **GDScript** — Godot frontend scenes and UI logic
- **C#** — Godot performance-critical GDExtension modules (optional)
- **Protobuf** — Cross-layer protocol definitions

The Python adapter covers the SimCore and backend. This adapter covers the
Godot/GDScript frontend. Protobuf definitions are language-agnostic and managed
by the Python adapter's build commands.

## Architecture Constraints (RTS-Specific)

| Layer | Path | May Import | Forbidden Imports |
|-------|------|-----------|-------------------|
| L0 Protocol | `proto/`, `shared/` | stdlib only | simcore, agents, scenes |
| L1 SimCore | `simcore/` | L0 | agents, scenes |
| L2 Agent | `agents/`, `ai/` | L0, L1 | scenes |
| L3 Frontend | `scenes/`, `ui/` | L0, L1, L2 | — |
| L4 Entry | root | all | — |

## Godot-Specific Lint Rules

1. **No business logic in scene scripts** — Scene scripts (.gd attached to .tscn)
   should only wire signals and update UI. Game logic belongs in SimCore or
   dedicated autoloads.
2. **Autoload singletons must not reference scene tree paths** — They should
   use signals or callables, not `get_node("/root/SomeScene")`.
3. **Resource paths must be typed** — Use `@export var texture: Texture2D` not
   `@export var texture`.