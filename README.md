# Migros Shopping List for Home Assistant

Custom Home Assistant integration for reading a Migros shopping list via Migros web API.

## Features

- Config Flow setup via the Home Assistant UI
- Polling-based updates through a coordinator
- Sensors for item count, in-store total, and online total
- Manual refresh button
- Clean separation of API, models, coordinator, and entities

## Repository Layout

```text
custom_components/
  migros_list/
```

## Installation with HACS

1. Add this repository as a custom repository in HACS.
2. Select the category `Integration`.
3. Install `Migros Shopping List`.
4. Restart Home Assistant.
5. Add the integration from the Home Assistant UI.

## Configuration

The integration requires:

- Migros shopping list ID
- Migros bearer token

The token is currently entered through the Config Flow. If the token expires, reauthentication is supported.

## Development Notes

- Domain: `migros_list`
- Main code: `custom_components/migros_list`
- Tested with Python syntax compilation

## Current Scope

This repository currently focuses on reading and exposing Migros shopping list data inside Home Assistant.
Mealie synchronization can be added as a follow-up feature.