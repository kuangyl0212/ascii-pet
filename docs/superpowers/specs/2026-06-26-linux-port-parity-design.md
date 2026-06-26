# Linux 版适配 Windows 新功能 — 设计文档

> 日期: 2026-06-26
> 主题: 将 Windows 版新增功能适配到 Linux 版 `bin/ascii-pet`

## 背景与目标

`bin/ascii-pet-win.py`（Windows 版，1489 行）自 `3b3fec0` 提交以来新增了大量功能；`bin/ascii-pet`（Linux 版，527 行）停留在 `3b3fec0`，缺失社区广场、战斗日志、交易、访客叠加、主题、i18n、备份还原、LAN 消息循环等功能。

**目标**：补齐 Linux 版渲染层和主循环钩子，使其与 Windows 版功能对等（除平台特有 GUI 交互外）。

**约束**：
- 不修改 `src/ascii_pet/` 核心包（状态机已跨平台）
- 遵循"无外部运行时依赖"原则
- 遵循 TDD：先写测试再实现
- 遵循现有 ANSI 字符串返回风格（vs. Windows 的 `(text, (R,G,B))` 元组）

## 范围

### 包含
1. 社区广场 UI（`lan` 模式 + 7 个子模式）
2. LAN 用户名编辑 UI（`lan_name_edit` 模式）
3. 战斗日志叠加、交易确认对话框叠加
4. 访客宠物叠加、拜访操作提示叠加（compact/expanded）
5. 主题系统（green/orange）
6. 国际化 `_()` 包裹
7. 备份/还原 UI
8. LAN 消息循环（`process_lan_queues()`）+ 退出清理（`disable_lan()`）
9. 方向键宠物切换（左/右箭头 = `b`/`n`）
10. Linux 自启动（`~/.config/autostart/ascii-pet.desktop`）
11. 现有 Bug 修复

### 不包含（理由）
- **系统托盘图标**：终端无原生支持；`yad`/`dunst` 需额外依赖
- **鼠标悬停摸宠**：终端鼠标跟踪不可靠
- **右键上下文菜单**：终端无右键事件，改用键盘快捷键替代

## 架构

### 总体思路
采用**增量修改**方案（Approach B）：保留 `bin/ascii-pet` 现有结构，新增函数 + 修改主循环，不大重写。核心状态机已跨平台，Linux 版只需补齐渲染层。

### 数据流
```
main loop (500ms tick)
  ├─ game.tick()                    → 推进游戏状态、生成消息
  ├─ game.process_lan_queues()      → 处理 LAN 消息（新增）
  ├─ get_key()                      → 读取按键
  ├─ 平台层 Shift 键拦截            → B/V/;/'/A 快捷键（新增）
  ├─ game.handle_key(key)           → 状态机分发
  └─ redraw
      ├─ build_<mode>(game)         → 基础面板
      ├─ 叠加访客宠物（compact/expanded）
      ├─ 叠加拜访提示（compact/expanded）
      ├─ 叠加战斗日志（expanded/lan）
      ├─ 叠加交易确认（所有模式）
      ├─ 叠加消息/动画
      └─ ANSI 输出到终端
```

## 详细设计

### 1. 新增键盘快捷键（平台层拦截）

在 `game.handle_key()` 之前处理，不进入状态机：

| 键 | 功能 | 实现 |
|---|---|---|
| `B` (Shift+b) | 创建备份 | `create_backup(game.uid, game.data_dir, 'manual')`，设置 `game.message = _('Backup successful')` |
| `V` (Shift+v) | 进入还原模式 | 设置平台层标志 `_restore_mode = True`（类似现有 `move_mode`，不进入状态机） |
| `;` | 切换主题 | `green → orange → green`，`save_theme()` + `_refresh_theme()` |
| `'` | 切换语言 | `en → zh → en`，`set_language()` + `save_settings()` |
| `A` (Shift+a) | 切换自启动 | 创建/删除 `~/.config/autostart/ascii-pet.desktop` |

**注意**：`B`/`V`/`A` 需检查大写形式（Shift+b 实际是 `B`）。`get_key()` 在 raw 模式下返回 `'B'` 而非 `'b'`。

**还原模式集成**：`_restore_mode` 是平台层布尔标志，类似现有 `move_mode`。当为 `True` 时：
- 重绘分发优先渲染 `build_restore(game)`，忽略 `game.mode`
- 按键处理优先：`1-9` 选择备份还原，`c`/ESC 退出还原模式
- 不修改 `game.mode`，退出后回到原模式

**Shift 键拦截点**：在主循环中，`get_key()` 返回后、`game.handle_key()` 调用前检查。顺序：
1. 检查 `move_mode`（现有）
2. 检查 `_restore_mode`（新增）
3. 检查 Shift 键 `B`/`V`/`;`/`'`/`A`（新增）
4. 检查方向键转义序列（新增）
5. 调用 `game.handle_key(key)`

### 2. 新增渲染函数（返回 ANSI 字符串）

| 函数 | 对应 Windows 函数 | 说明 |
|---|---|---|
| `build_lan_panel(game)` | `render_lan_lines` | 社区广场主面板 |
| `build_lan_name_edit(game)` | `render_lan_name_edit_lines` | 用户名编辑面板 |
| `build_battle_log(battle_result)` | `render_battle_log_lines` | 战斗日志叠加 |
| `build_trade_confirm(trade_req)` | `render_trade_confirm_lines` | 交易确认对话框叠加 |
| `build_restore(game)` | 类似 `render_release_lines` | 备份还原选择面板 |

#### `build_lan_panel(game)` 渲染顺序
1. 标题 `═ Community Plaza ═`
2. 已连接：`Username: {}  |  Players online: {}` + 宠物信息行 `{} | {} | Lv.{} | HP:{}/100`
3. 未连接：`Status: Disconnected`（+ `Error: {}`）
4. 拜访状态：`★ Visiting ({}m{}s)` 和/或 `★ {} is visiting you ({}m{}s)`
5. 游戏消息（< 10s 内）
6. 玩家列表（分页）：`─ Online Players (Page {}/{}) ─` + `[{}] {} - {}({})` 每行
7. 访客列表：`─ Visitors ─` + `  {}({})` 每行
8. 操作区（子模式相关）：
   - `visit`/`challenge`/`gift`/`trade`：`Select <X> target:` + 玩家列表 + `[ESC]Cancel`
   - `gift_item`：`Select item to gift:` + 物品列表 + `[ESC]Cancel`
   - `trade_pet`：`Select pet to trade:` + 自己宠物列表 + `[ESC]Cancel`
   - `active_visit`/`being_visited`：`[e]End Visit [f]Remote Feed [p]Remote Play`
   - 空闲：`[u]Edit Username`
   - 空闲且无活跃操作：`[v]Visit [c]Challenge [g]Gift [t]Trade [h]Heal`
9. 交易确认（`pending_trade_req`）：`{} wants to trade {}! [y]Accept [n]Reject`
10. 分页：`Prev Page: [  Next Page: ]`（总页数 ≥ 2 时）
11. 底部：`[l]Back [o]Disable LAN`（或 `[o]Enable LAN`）

#### `build_battle_log(battle_result)` 渲染
- `═ Battle Log ═`
- 每条日志
- `Winner: {} | Loser: {}`
- `Winner HP: -{} | Loser HP: -{}`
- `XP +{}`（若 > 0）
- `Level Up!`（若 `leveled_up`）
- `Evolved into {species}!`（若 `evolved`）

#### `build_trade_confirm(trade_req)` 渲染
- `═ Trade Request ═`
- `Player {username} wants to trade their {pet}({species})`
- `[y]Accept [n]Reject`

### 3. 新增 layout 函数

| 函数 | 列×行 |
|---|---|
| `layout_lan()` | 50×20 |
| `layout_lan_name_edit()` | 50×12 |
| `layout_rename()` | 50×12 |
| `layout_restore()` | 50×14 |

扩展 `do_layout()` 处理 `'lan'` / `'lan_name_edit'` 模式。

**`restore` 模式的 layout**：由于 `_restore_mode` 是平台层标志，不通过 `do_layout(game)` 分发。在主循环中检查 `_restore_mode`，若为 `True` 则直接调用 `layout_restore()` 并跳过 `do_layout(game)`。

### 4. 叠加层逻辑

在主重绘循环中，**所有模式**追加：
- **交易确认**：`game.pending_trade_req` 存在时追加 `build_trade_confirm`

**compact/expanded 模式**追加（按 Windows 顺序）：
1. **访客宠物**：`game.visitor_pets` 非空时，渲染每个访客精灵（`render_sprite(v_bones, frame_idx)`）+ `[Visitor] NAME (from OWNER)` 标签
2. **拜访提示**：`active_visit` 或 `being_visited` 时追加 `[e]End Visit [f]Feed [p]Play`

**expanded/lan 模式**追加：
3. **战斗日志**：`game.battle_result` 存在时追加 `build_battle_log`

### 5. 主题系统

- 从 `ascii_pet.i18n` 导入 `get_theme, set_theme, save_theme, init_theme`
- 从 `ascii_pet.core` 导入 `THEMES, DEFAULT_THEME`
- 新增 `_refresh_theme()`：从 `THEMES[get_theme()]` 读取 `ansi_dim`/`ansi_white`/`ansi_bar_fill` 设置模块级颜色变量：
  - `COLOR_DIM`、`COLOR_MSG`、`COLOR_WHITE`、`COLOR_BAR_FILL`、`COLOR_BAR_EMPTY`
- 替换 `RARITY_COLORS`、`MOOD_COLORS`、`stat_bar()` 中的硬编码颜色
- `main()` 中调用 `init_theme(game.data_dir)` + `_refresh_theme()`
- 主题切换后调用 `_refresh_theme()`

### 6. i18n

- 从 `ascii_pet.i18n` 导入 `_`
- 所有用户可见字符串包裹 `_()`，对齐 Windows 版用例
- 注意：动态数据（如物品数量）不包裹 `_()`，避免截断（参考 project_memory 教训）

### 7. 主循环修改

```python
# tick 循环（每 500ms）
if now - last_tick >= 0.5:
    game.tick()
    game.process_lan_queues()  # 新增
    last_tick = now
    need_redraw = True

# 退出清理
try:
    ...
finally:
    game.disable_lan()  # 新增
    show_cursor()
    clear_screen()
```

### 8. 方向键宠物切换

在 `get_key()` 返回的键值中识别方向键转义序列：
- `\x1b[D`（左箭头）→ 调用 `game.handle_key('b')`
- `\x1b[C`（右箭头）→ 调用 `game.handle_key('n')`

### 9. 自启动（Linux 等价物）

- **文件路径**：`~/.config/autostart/ascii-pet.desktop`
- **内容**（路径运行时计算）：
  ```ini
  [Desktop Entry]
  Type=Application
  Name=ASCII Pet
  Exec={launcher_path}
  Icon={icon_path}
  Terminal=false
  X-GNOME-Autostart-enabled=true
  ```
  - `launcher_path`：优先使用 `~/.local/bin/ascii-pet-launcher`（`reinstall.sh` 安装位置）；回退到 `__file__` 同目录的 `ascii-pet-launcher`
  - `icon_path`：优先使用 `~/.local/share/ascii-pet/icon.png`；回退到 `__file__` 同级的 `../icon.png`
- **`is_autostart_enabled()`**：检查 `.desktop` 文件是否存在
- **`set_autostart(enable)`**：创建或删除文件
- **`A` 键切换**：`set_autostart(not is_autostart_enabled())`，设置 `game.message` 提示当前状态

### 10. Bug 修复

1. `from weather import format_weather_line` → `from ascii_pet.weather import format_weather_line`
2. 动画光标定位 ANSI 转义序列：
   - 错误：`f'\033[H{n}\033[K'`
   - 正确：`f'\033[{n};1H\033[K'`

## 测试方案（TDD）

### 新建 `test/test_linux_render.py`

使用 `importlib` 导入 `bin/ascii-pet`（文件名含连字符，参考 `test_tray_menu.py` 模式）。

#### 测试用例

**渲染函数测试：**
- `test_build_lan_panel_disconnected`：未连接时显示 "Status: Disconnected"
- `test_build_lan_panel_connected`：已连接时显示 "Username:" 和 "Players online:"
- `test_build_lan_panel_pet_info_line`：显示宠物信息行 `{} | {} | Lv.{} | HP:{}/100`
- `test_build_lan_panel_visit_status`：`active_visit` 时显示 "Visiting"
- `test_build_lan_panel_submode_visit`：`lan_submode='visit'` 时显示 "Select visit target"
- `test_build_lan_panel_submode_challenge`：`lan_submode='challenge'` 时显示 "Select challenge target"
- `test_build_lan_panel_submode_gift`：`lan_submode='gift'` 时显示 "Select gift target"
- `test_build_lan_panel_submode_gift_item`：`lan_submode='gift_item'` 时显示 "Select item to gift"
- `test_build_lan_panel_submode_trade`：`lan_submode='trade'` 时显示 "Select trade target"
- `test_build_lan_panel_submode_trade_pet`：`lan_submode='trade_pet'` 时显示 "Select pet to trade"
- `test_build_lan_name_edit`：显示当前用户名和输入框
- `test_build_battle_log`：显示 Winner/Loser/XP/Level Up
- `test_build_trade_confirm`：显示交易请求和 `[y]Accept [n]Reject`
- `test_build_restore`：显示备份列表

**叠加层测试：**
- `test_overlay_visitor_pets`：`game.visitor_pets` 非空时 compact/expanded 显示访客精灵
- `test_overlay_visit_hint`：`active_visit` 时 compact/expanded 显示 `[e]End Visit`
- `test_overlay_battle_log`：`game.battle_result` 存在时 expanded 显示战斗日志
- `test_overlay_trade_confirm`：`game.pending_trade_req` 存在时所有模式显示交易确认

**键盘快捷键测试：**
- `test_key_backup_creates_backup`：`B` 键创建备份
- `test_key_restore_enters_mode`：`V` 键切换到 restore 模式
- `test_key_theme_toggle`：`;` 键切换主题
- `test_key_language_toggle`：`'` 键切换语言
- `test_key_autostart_toggle`：`A` 键切换自启动

**主循环测试：**
- `test_process_lan_queues_called`：tick 循环调用 `process_lan_queues`
- `test_disable_lan_on_exit`：退出时调用 `disable_lan`

**Bug 修复测试：**
- `test_weather_import`：验证 `format_weather_line` 可正常导入
- `test_animation_cursor_positioning`：验证 ANSI 转义序列格式正确

## 文件改动清单

| 文件 | 改动类型 | 说明 |
|---|---|---|
| `bin/ascii-pet` | 修改 | 主要工作量：新增渲染函数、layout、主循环钩子、主题、i18n、Bug 修复 |
| `test/test_linux_render.py` | 新建 | TDD 测试，使用 `importlib` 导入 `bin/ascii-pet`（参考 `test_tray_menu.py` 模式） |

**不修改**：
- `src/ascii_pet/` 核心包（状态机已跨平台）
- `bin/ascii-pet-launcher`（launcher 的 alacritty 配置路径问题是既有问题，不在本次范围）
- `locales/` 翻译文件（Linux 版使用的 `_()` key 与 Windows 版一致，`.po` 已有）

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| `get_key()` 在 raw 模式下返回 Shift 键的方式不确定 | 测试中验证实际返回值，必要时调整 |
| 方向键转义序列在不同终端有差异 | 使用最常见的 `\x1b[D`/`\x1b[C`，参考现有 Linux 终端实现 |
| 主题 ANSI 代码在某些终端不支持 | 使用最基础的 ANSI 代码（`\033[2m` 等），兼容性已验证 |
| 备份还原模式不在状态机中 | 作为平台层模式处理，类似现有 `move_mode` |

## 验证标准

1. `pytest test/test_linux_render.py` 全部通过
2. `pytest` 全套测试无回归
3. Linux 版启动后，按 `l` 进入社区广场，可见玩家列表和操作提示
4. 拜访/挑战/礼物/交易流程在两台 Linux 机器间可正常进行
5. 主题切换（`;`）和语言切换（`'`）即时生效
6. 备份（`B`）和还原（`V`）功能正常
7. 自启动（`A`）创建/删除 `.desktop` 文件正确
