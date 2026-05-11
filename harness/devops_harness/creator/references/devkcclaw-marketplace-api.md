# DevKCClaw Marketplace API — Direct Download Workaround

## Problem

The official DevKCClaw CLI (`npx @nacos-group/cli skill-get`) attempts to connect
to Nacos via HTTP on port 8848. The public marketplace at `market.devkcclaw.io`
only exposes HTTPS on port 443, so the CLI fails with a connection error:

```
Error: connect ECONNREFUSED 0.0.0.0:8848
```

## Workaround: Nacos v3 Client API over HTTPS

The marketplace hosts a Nacos v3-compatible client API that returns skill ZIP
files directly, with **no authentication required**:

```bash
# Download a skill by name
curl -sL 'https://market.devkcclaw.io/nacos/v3/client/ai/skills?name=<skill-name>&namespaceId=public' \
  -o /tmp/<skill-name>.zip

# Extract
mkdir -p /tmp/<skill-name>
cd /tmp/<skill-name> && unzip -q /tmp/<skill-name>.zip
# The skill is at /tmp/<skill-name>/<skill-name>/SKILL.md
```

## Verified Skill Names

| Skill | nacosId | Downloads | ZIP Size |
|-------|---------|-----------|----------|
| `harness-creator` | `nacos-69d107e3e4b0d8b42828bfb7` | 377 | ~98KB |
| `harness-executor` | same (paired skills) | 30 | ~149KB |

Paired skills share the same `nacosId` — harness-creator generates the
infrastructure, harness-executor runs tasks against it.

## Skill Structure (DevKCClaw Format)

```
<skill-name>/
├── SKILL.md               # Frontmatter + instructions (YAML header)
├── agents/                # Subagent prompt definitions (.md)
├── references/            # Knowledge files loaded on demand
├── scripts/               # Executable helper scripts (.py)
├── evals/                 # Evaluation configs (evals.json)
├── templates/             # File templates for scaffolding
└── mixins/                # Reusable agent behavior fragments
```

This structure is directly compatible with Hermes skill format — copy the
entire directory to `~/.hermes/skills/<category>/<skill-name>/`.

## Installation Workflow

```bash
# 1. Download
curl -sL 'https://market.devkcclaw.io/nacos/v3/client/ai/skills?name=harness-creator&namespaceId=public' -o /tmp/harness-creator.zip
curl -sL 'https://market.devkcclaw.io/nacos/v3/client/ai/skills?name=harness-executor&namespaceId=public' -o /tmp/harness-executor.zip

# 2. Extract
mkdir -p /tmp/harness-creator && cd /tmp/harness-creator && unzip -q /tmp/harness-creator.zip
mkdir -p /tmp/harness-executor && cd /tmp/harness-executor && unzip -q /tmp/harness-executor.zip

# 3. Install to Hermes
mkdir -p ~/.hermes/skills/devops/harness-creator
mkdir -p ~/.hermes/skills/devops/harness-executor
cp -R /tmp/harness-creator/harness-creator/* ~/.hermes/skills/devops/harness-creator/
cp -R /tmp/harness-executor/harness-executor/* ~/.hermes/skills/devops/harness-executor/

# 4. Verify
# Use skills_list() or `hermes skills list` to confirm availability
```

## Notes

- The API returns raw ZIP bytes — there is no JSON wrapper or metadata envelope.
- No API key or Nacos token is needed for the public namespace.
- The skill name in the URL must match exactly (lowercase, hyphens).
- Some skills may have a `.DS_Store` in the archive — remove after extraction.