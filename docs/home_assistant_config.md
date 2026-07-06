# Home Assistant Config

## Package Mode

If your Home Assistant setup already uses `packages:`, the quickest install
path is to place:

- `homeassistant/packages/load_optimizer_1_package.yaml`

into your packages folder.

Example:

```yaml
homeassistant:
  packages: !include_dir_named packages
```

## Pyscript Layout

Place these files into your Home Assistant `pyscript` folder structure:

- `homeassistant/pyscript/core/load_optimizer_1.py`
- `homeassistant/pyscript/adapters/dishwasher_1.py`
- `homeassistant/migrations/legacy_to_load_optimizer_1/migrate_legacy_dishwasher.py`

Suggested layout:

```text
pyscript/
├── adapters/
│   └── dishwasher_1.py
├── core/
│   └── load_optimizer_1.py
└── migrate_legacy_dishwasher.py
```

## Reload Order

After the files are in place:

1. reload YAML configuration if needed
2. reload template entities
3. reload Pyscript
4. confirm the new entities exist
5. run the migration service

