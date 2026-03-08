# Lock Migration Persistence

## Scope

This document describes what can and cannot be preserved when migrating the OVMS vehicle lock control from a Home Assistant `switch` entity to a native `lock` entity.

The current implementation exposes `v.e.locked` as:

- a `binary_sensor` for state
- a `switch` for control

The target implementation should expose `v.e.locked` as:

- a `binary_sensor` for raw/diagnostic state visibility
- a `lock` for control in the proper Home Assistant domain

## Key Constraint

Home Assistant can migrate entity registry data and unique IDs cleanly within a platform domain, but it does not provide a clean in-place migration from one entity domain to another for custom integrations.

For this change, the old `switch` entity and the new `lock` entity are different entities from Home Assistant's perspective.

That means:

- `switch.some_entity` cannot become `lock.some_entity` without creating a new entity
- existing automations, dashboards, and scripts referencing the old `switch` entity will break
- long-term statistics and history tied to the old entity ID will not follow automatically

## What Can Be Preserved

If we migrate deliberately through the entity registry before the new `lock` platform is loaded, we can preserve some metadata from the old lock `switch` entity.

### Preservable metadata

- device association
- area assignment
- hidden/disabled state
- user-defined name override
- user-defined icon override

### How to preserve it cleanly

1. Find the existing OVMS `switch` entity registry entry for the lock control.
2. Create a new OVMS `lock` registry entry with the new lock unique ID.
3. Copy supported registry metadata from the old `switch` entry to the new `lock` entry.
4. Remove the old `switch` registry entry.
5. Let the new lock platform claim the pre-created `lock` registry entry during setup.

This avoids keeping any legacy runtime code while still preserving the parts that Home Assistant stores in the registry.

## What Cannot Be Preserved

The following should be treated as breaking changes:

- entity domain
- entity ID
- service calls using `switch.turn_on` and `switch.turn_off`
- automations, scripts, template references, and dashboards targeting the old `switch` entity ID
- historical continuity for the old `switch` entity ID

These are structural consequences of changing the Home Assistant domain, not OVMS-specific limitations.

## Clean Migration Recommendation

Use a one-time migration in the config entry setup path.

### Recommended behavior

1. Bump `CONFIG_VERSION`.
2. During config entry migration, inspect the entity registry for old lock `switch` entries belonging to the OVMS config entry.
3. Pre-create matching `lock` registry entries and copy supported metadata.
4. Remove the old `switch` entries.
5. Stop creating lock controls through `SWITCH_TYPES`.
6. Create a native `lock` entity for `v.e.locked`.

### Why this is clean

- no compatibility shim
- no dual `switch` and `lock` controls for the same feature
- no indefinite legacy paths
- migration logic stays isolated to setup/migration, not the normal runtime path

## Unique ID Recommendation

The new lock entity should use a lock-specific unique ID suffix such as `_lock`.

Example direction:

- old: `ovms_<vehicle>_v_e_locked_<hash>_switch`
- new: `ovms_<vehicle>_v_e_locked_<hash>_lock`

This is cleaner than reusing `_switch` for a `lock` entity and keeps the registry shape understandable.

## Entity ID Recommendation

The new lock entity should also use a clean object ID without the old `_switch` suffix.

Recommended direction:

- old: `switch.ovms_<vehicle>_v_e_locked_switch`
- new: `lock.ovms_<vehicle>_v_e_locked`

This produces a cleaner public entity model even though it is a breaking change.

## State Handling Recommendation

The new `lock` entity should not reuse the current switch state parser as-is.

The existing code already shows that `locked` and `unlocked` are first-class lock states, and `v.e.locked` also carries `invert_state` metadata. The new lock entity should use a single lock-aware parser that:

- accepts `locked` and `unlocked`
- accepts boolean-like values such as `true`, `false`, `1`, `0`
- applies `invert_state` when present

This should be implemented once and reused, instead of keeping separate, slightly inconsistent parsing logic across platforms.

## Release Impact

This change should be called out as a breaking change in the release notes.

Minimum user-facing message:

- vehicle locking moved from `switch` to native `lock`
- entity IDs changed from `switch.*` to `lock.*`
- automations and dashboards must be updated accordingly
- `switch.turn_on` and `switch.turn_off` calls must be replaced with `lock.lock` and `lock.unlock`

## Implementation Summary

Based on the current codebase, the target implementation should make the following structural changes:

- remove `v.e.locked` from `SWITCH_TYPES`
- add a dedicated lock control mapping
- add `Platform.LOCK` to the integration platform list
- create a new `lock.py` platform for OVMS
- update topic discovery to emit a `lock` related entity instead of a `switch`
- update entity factory dispatch to pass lock-specific config
- add one-time entity registry migration for old lock switches

## Bottom Line

A fully non-breaking migration is not possible because the Home Assistant entity domain is changing.

A clean migration is possible if we:

- preserve registry metadata where Home Assistant allows it
- accept the domain and entity ID break explicitly
- keep all compatibility behavior out of the steady-state runtime code