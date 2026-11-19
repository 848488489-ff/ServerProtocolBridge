#!/usr/bin/env python3
"""Update version.json changelog with new feature entries."""

import json
import os

filepath = r'D:\桌面\版本更新检查\api\version.json'

with open(filepath, 'r', encoding='utf-8') as f:
    data = json.load(f)

# New changelog entries
new_entries_zh = (
    '新增资源包处理方式：设置→连接可选择"转发提示"、"有则允许"、"拒绝"或"伪装为允许"，'
    '解决部分服务器强制资源包导致浏览器客户端无法进入的问题。\n'
    '关于窗口和帮助文档新增 VC++ 运行时问答：EXE 打不开时安装 VC++ 运行时即可解决。'
)

new_entries_en = (
    'New resource pack handling: Settings -> Connection now offers Forward prompt, '
    'Accept if present, Reject, or Spoof as accept to bypass servers that force '
    'resource packs and block browser clients.\n'
    'About window and help docs now include a VC++ runtime FAQ: if the EXE won\'t '
    'open, install the VC++ Redistributable.'
)

# Append to changelog
if 'changelog' in data and data['changelog']:
    data['changelog'] = data['changelog'].rstrip('\n') + '\n' + new_entries_zh

if 'changelog_en' in data and data['changelog_en']:
    data['changelog_en'] = data['changelog_en'].rstrip('\n') + '\n' + new_entries_en

# Write back
with open(filepath, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print('version.json updated successfully')
print('Changelog length:', len(data['changelog']))
print('Changelog_en length:', len(data['changelog_en']))
