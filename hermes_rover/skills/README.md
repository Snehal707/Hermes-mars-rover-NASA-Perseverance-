# Hermes Mars Rover Skills

Skills are auto-discovered from:

- `hermes_rover/skills`
- `~/.hermes/skills/`

## SKILL.md format

Use the [agentskills.io](https://agentskills.io) SKILL.md format:

- YAML frontmatter: `name`, `description`, `version`, `metadata.hermes.tags`
- Markdown body with instructions

Example:

```yaml
---
name: Obstacle Avoidance
description: Detect and avoid obstacles using LiDAR and IMU
version: 1.0.0
metadata:
  hermes:
    tags: [mars, rover, hazard, navigation]
---
# Obstacle Avoidance

When LiDAR detects close range or IMU shows tilt...
```

## Symlink to Hermes

Point your Hermes skills directory at this folder:

```bash
ln -s ~/hermes-mars-rover/hermes_rover/skills ~/.hermes/skills/mars-rover
```

## How Hermes uses skills

- Hermes loads skills when it encounters similar tasks (e.g., hazard handling, terrain assessment).
- Hermes can create new SKILL.md files when it solves novel problems.
- Skills improve over sessions as Hermes refines them based on success and feedback.
