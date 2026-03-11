# Contributing to Claude Trading Skills

We welcome contributions! Whether you're adding new skills, improving existing ones, or fixing bugs, your work helps the community trade smarter.

## Ways to Contribute

### Add New Skills
- Create skills for new exchanges, chains, or data providers
- Add traditional quant finance skills (equities, futures, FX)

### Improve Existing Skills
- Add more code examples and scripts
- Expand reference documentation
- Add unit tests for calculation functions
- Improve error handling in example code

### Report Issues
- Submit bug reports with reproduction steps
- Suggest improvements or new skill ideas

## How to Contribute

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-skill`)
3. **Follow** the directory structure and SKILL.md format
4. **Test** all code examples
5. **Commit** (`git commit -m 'Add amazing skill'`)
6. **Push** (`git push origin feature/amazing-skill`)
7. **Submit** a pull request

## Skill Structure

Every skill must follow this structure:

```
skill-name/
├── SKILL.md          # Required: YAML frontmatter + instructions
├── references/       # Optional: detailed docs, formulas, guides
├── scripts/          # Optional: executable Python/Bash scripts
└── assets/           # Optional: templates, data files
```

### SKILL.md Requirements

1. **YAML Frontmatter** (required):
   ```yaml
   ---
   name: skill-name          # Must match directory name, lowercase + hyphens
   description: >-            # Clear description of what and when to use
     Concise description...
   license: MIT               # Or appropriate license
   metadata:
     author: your-name
     version: "1.0.0"
     category: trading
   ---
   ```

2. **Markdown Body** (required):
   - Overview of what the skill does
   - Prerequisites (packages, API keys)
   - Quick Start with working code example
   - Use Cases
   - References to additional docs

3. **Size**: Keep SKILL.md under 500 lines. Move details to `references/`.

### Agent Skills Specification

All skills must adhere to the [Agent Skills Specification](https://agentskills.io/specification). Key rules:
- Directory name must match the `name` field in frontmatter
- Use lowercase alphanumeric characters and hyphens only
- `name` and `description` fields are required
- Keep references one level deep from SKILL.md

## Code Standards

- **Python**: 3.9+, type hints, docstrings
- **Package management**: Use `uv pip install` in examples
- **No API keys in code**: Use environment variables or placeholder strings
- **Financial math**: Double-check all formulas, include unit tests
- **Disclaimers**: Any analysis skill must note it's not financial advice

## Safety Requirements

Skills that interact with real money (execution, swaps) MUST:
- Default to simulation/dry-run mode
- Require explicit user confirmation before any transaction
- Display all transaction details before execution
- Include safety warnings in the SKILL.md

## Testing

- All code examples should be runnable
- Include sample data or mock API responses for testing
- Test edge cases (zero values, negative prices, empty data)
- Verify financial calculations against known correct values

## License

By contributing, you agree that your contributions will be licensed under the MIT License unless you specify otherwise in the skill's frontmatter.
