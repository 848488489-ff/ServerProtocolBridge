#!/usr/bin/env python3
"""Append English entries to ``web/api/version.json`` changelog_en."""

import json
from pathlib import Path

filepath = Path(__file__).resolve().parent.parent / 'web' / 'api' / 'version.json'

with open(filepath, 'r', encoding='utf-8') as f:
    data = json.load(f)

# New changelog entries (the project is English-only).
new_entries_en = (
    'New resource pack handling: Settings -> Connection now offers Forward prompt, '
    'Accept if present, Reject, or Spoof as accept to bypass servers that force '
    'resource packs and block browser clients.\n'
    'About window and help docs now include a VC++ runtime FAQ: if the EXE won\'t '
    'open, install the VC++ Redistributable.'
)

# Append to the English changelog.
if 'changelog_en' in data and data['changelog_en']:
    data['changelog_en'] = data['changelog_en'].rstrip('\n') + '\n' + new_entries_en

# Write back.
with open(filepath, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print('version.json updated successfully')
print('Changelog_en length:', len(data.get('changelog_en', '')))
