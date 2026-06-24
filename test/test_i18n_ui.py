"""Tests for i18n UI text translation in ascii-pet-win.py.

TDD RED phase: tests define expected translations for all UI strings
that will be wrapped with _() in ascii-pet-win.py.

Tests the _() function directly with English msgid keys, verifying
Chinese translations match the .po file.
"""
from ascii_pet import i18n


class TestTrayMenuI18n:
    """Tray menu items translated via _() with English keys."""

    def test_show_window_zh(self):
        i18n.set_language('zh')
        assert i18n._('Show Window') == '显示窗口'

    def test_hide_window_zh(self):
        i18n.set_language('zh')
        assert i18n._('Hide Window') == '隐藏窗口'

    def test_autostart_on_boot_zh(self):
        i18n.set_language('zh')
        assert i18n._('Auto-start on Boot') == '开机自启动'

    def test_quit_zh(self):
        i18n.set_language('zh')
        assert i18n._('Quit') == '退出'

    def test_tray_menu_en(self):
        i18n.set_language('en')
        assert i18n._('Show Window') == 'Show Window'
        assert i18n._('Hide Window') == 'Hide Window'
        assert i18n._('Auto-start on Boot') == 'Auto-start on Boot'
        assert i18n._('Quit') == 'Quit'


class TestContextMenuI18n:
    """Context menu items translated via _() with English keys."""

    def test_feed_zh(self):
        i18n.set_language('zh')
        assert i18n._('Feed (F)') == '喂食 (F)'

    def test_play_zh(self):
        i18n.set_language('zh')
        assert i18n._('Play (P)') == '玩耍 (P)'

    def test_sleep_zh(self):
        i18n.set_language('zh')
        assert i18n._('Sleep (S)') == '睡觉 (S)'

    def test_adopt_zh(self):
        i18n.set_language('zh')
        assert i18n._('Adopt New Pet (W)') == '领养新宠物 (W)'

    def test_export_zh(self):
        i18n.set_language('zh')
        assert i18n._('Export to Clipboard (E)') == '导出到剪贴板 (E)'

    def test_prev_pet_zh(self):
        i18n.set_language('zh')
        assert i18n._('Previous Pet (B)') == '上一个宠物 (B)'

    def test_next_pet_zh(self):
        i18n.set_language('zh')
        assert i18n._('Next Pet (N)') == '下一个宠物 (N)'

    def test_compact_mode_zh(self):
        i18n.set_language('zh')
        assert i18n._('Compact Mode') == '紧凑模式'

    def test_expanded_mode_zh(self):
        i18n.set_language('zh')
        assert i18n._('Expanded Mode') == '展开模式'

    def test_stats_panel_zh(self):
        i18n.set_language('zh')
        assert i18n._('Stats Panel (T)') == '属性面板 (T)'

    def test_achievements_zh(self):
        i18n.set_language('zh')
        assert i18n._('Achievements (A)') == '成就面板 (A)'

    def test_items_zh(self):
        i18n.set_language('zh')
        assert i18n._('Items (U)') == '物品栏 (U)'

    def test_lan_zh(self):
        i18n.set_language('zh')
        assert i18n._('Community Plaza (L)') == '社区广场 (L)'

    def test_quit_q_zh(self):
        i18n.set_language('zh')
        assert i18n._('Quit (Q)') == '退出 (Q)'

    def test_context_menu_en(self):
        i18n.set_language('en')
        assert i18n._('Feed (F)') == 'Feed (F)'
        assert i18n._('Compact Mode') == 'Compact Mode'
        assert i18n._('Quit (Q)') == 'Quit (Q)'


class TestExpandedPanelI18n:
    """Expanded panel labels and help line."""

    def test_evolved_zh(self):
        i18n.set_language('zh')
        assert i18n._('★ Evolved') == '★ 已进化'

    def test_help_line_zh(self):
        i18n.set_language('zh')
        assert i18n._('[f]feed [p]play [s]sleep [w]adopt [b]prev [n]next [t]stats [a]achieve [u]items [e]export [Enter]compact [q]quit') == '[f]喂食 [p]玩耍 [s]睡觉 [w]领养 [b]上一只 [n]下一只 [t]属性 [a]成就 [u]物品 [e]导出 [Enter]紧凑 [q]退出'

    def test_help_line_en(self):
        i18n.set_language('en')
        assert i18n._('[f]feed [p]play [s]sleep [w]adopt [b]prev [n]next [t]stats [a]achieve [u]items [e]export [Enter]compact [q]quit') == '[f]feed [p]play [s]sleep [w]adopt [b]prev [n]next [t]stats [a]achieve [u]items [e]export [Enter]compact [q]quit'


class TestStatsPanelI18n:
    """Stats panel labels."""

    def test_stats_for_zh(self):
        i18n.set_language('zh')
        assert i18n._('Stats for {}').format('TestPet') == 'TestPet 的属性'

    def test_species_zh(self):
        i18n.set_language('zh')
        assert i18n._('Species:') == '物种：'

    def test_face_zh(self):
        i18n.set_language('zh')
        assert i18n._('Face:') == '面部：'

    def test_eye_zh(self):
        i18n.set_language('zh')
        assert i18n._('Eye:') == '眼睛：'

    def test_hat_zh(self):
        i18n.set_language('zh')
        assert i18n._('Hat:') == '帽子：'

    def test_pet_zh(self):
        i18n.set_language('zh')
        assert i18n._('Pet:') == '宠物：'

    def test_activity_header_zh(self):
        i18n.set_language('zh')
        assert i18n._('--- Activity ---') == '--- 活动 ---'

    def test_days_adopted_zh(self):
        i18n.set_language('zh')
        assert i18n._('  Days adopted:  {}').format(5) == '  领养天数：5'

    def test_hours_online_zh(self):
        i18n.set_language('zh')
        assert i18n._('  Hours online: {}').format('12.5') == '  在线时长：12.5'

    def test_feed_count_zh(self):
        i18n.set_language('zh')
        assert i18n._('  Feed count:   {}').format(10) == '  喂食次数：10'

    def test_play_count_zh(self):
        i18n.set_language('zh')
        assert i18n._('  Play count:   {}').format(8) == '  玩耍次数：8'

    def test_sleep_count_zh(self):
        i18n.set_language('zh')
        assert i18n._('  Sleep count:  {}').format(3) == '  睡觉次数：3'

    def test_total_acts_zh(self):
        i18n.set_language('zh')
        assert i18n._('  Total acts:   {}').format(21) == '  总互动：21'

    def test_growth_header_zh(self):
        i18n.set_language('zh')
        assert i18n._('--- Growth ---') == '--- 成长 ---'

    def test_level_zh(self):
        i18n.set_language('zh')
        assert i18n._('  Level: {}  XP: {}/{}').format(5, 50, 500) == '  等级：5  XP: 50/500'

    def test_rarity_shiny_zh(self):
        i18n.set_language('zh')
        assert i18n._('  Rarity: {}  Shiny: {}').format('rare', i18n._('Yes')) == '  稀有度：rare  闪光：是'

    def test_yes_no_zh(self):
        i18n.set_language('zh')
        assert i18n._('Yes') == '是'
        assert i18n._('No') == '否'

    def test_stats_labels_en(self):
        i18n.set_language('en')
        assert i18n._('Species:') == 'Species:'
        assert i18n._('Face:') == 'Face:'
        assert i18n._('Eye:') == 'Eye:'
        assert i18n._('Hat:') == 'Hat:'
        assert i18n._('Yes') == 'Yes'
        assert i18n._('No') == 'No'


class TestAchievementsPanelI18n:
    """Achievements panel labels."""

    def test_achievements_for_zh(self):
        i18n.set_language('zh')
        assert i18n._('Achievements for {}').format('TestPet') == 'TestPet 的成就'

    def test_unlocked_zh(self):
        i18n.set_language('zh')
        assert i18n._('unlocked') == '已解锁'

    def test_locked_zh(self):
        i18n.set_language('zh')
        assert i18n._('  ??? Locked') == '  ??? 未解锁'

    def test_achievement_names_zh(self):
        """Achievement names should be translatable via _()."""
        i18n.set_language('zh')
        assert i18n._('First Meal') == '第一餐'
        assert i18n._('Gourmet') == '美食家'
        assert i18n._('Shiny Hunter') == '闪光猎人'


class TestItemsPanelI18n:
    """Items panel labels."""

    def test_inventory_zh(self):
        i18n.set_language('zh')
        assert i18n._('Inventory ({}/{})').format(3, 20) == '物品栏 (3/20)'

    def test_select_item_zh(self):
        i18n.set_language('zh')
        assert i18n._('Select item [1-7] or [c]cancel') == '选择物品 [1-7] 或 [c]取消'

    def test_empty_items_zh(self):
        i18n.set_language('zh')
        assert i18n._('  Empty — items drop from random events') == '  空 — 物品从随机事件中掉落'


class TestReleasePanelI18n:
    """Release panel labels."""

    def test_select_release_zh(self):
        i18n.set_language('zh')
        assert i18n._('Select a pet to release:') == '选择要释放的宠物：'

    def test_max_pets_zh(self):
        i18n.set_language('zh')
        assert i18n._('Max {} pets. Choose 1-3, or [c]cancel').format(3) == '最多3只宠物。选择1-3，或 [c]取消'

    def test_select_cancel_zh(self):
        i18n.set_language('zh')
        assert i18n._('[1-3]select [c]cancel') == '[1-3]选择 [c]取消'


class TestDeathPanelI18n:
    """Death panel labels."""

    def test_died_zh(self):
        i18n.set_language('zh')
        assert i18n._('Your pet has died...') == '你的宠物死了...'

    def test_revive_zh(self):
        i18n.set_language('zh')
        assert i18n._('[r]revive (Potion x{count})') == '[r]复活 (药水 x{count})'
        assert i18n._('[d]release') == '[d]遗弃'
        assert i18n._('[u]backpack') == '[u]背包'


class TestLANPanelI18n:
    """LAN panel labels."""

    def test_lan_title_zh(self):
        i18n.set_language('zh')
        assert i18n._('═ Community Plaza ═') == '═ 社区广场 ═'

    def test_master_slave_zh(self):
        i18n.set_language('zh')
        assert i18n._('Master') == '主节点'
        assert i18n._('Slave') == '从节点'

    def test_disconnected_zh(self):
        i18n.set_language('zh')
        assert i18n._('Status: Disconnected') == '状态: 未连接'

    def test_error_zh(self):
        i18n.set_language('zh')
        assert i18n._('Error: {}').format('timeout') == '错误: timeout'

    def test_online_players_zh(self):
        i18n.set_language('zh')
        assert i18n._('─ Online Players (Page {}/{}) ─').format(1, 2) == '─ 在线玩家 (第1/2页) ─'

    def test_no_other_players_zh(self):
        i18n.set_language('zh')
        assert i18n._('(No other players)') == '（暂无其他玩家）'

    def test_current_visitors_zh(self):
        i18n.set_language('zh')
        assert i18n._('─ Current Visitors ─') == '─ 当前访客 ─'

    def test_actions_zh(self):
        i18n.set_language('zh')
        assert i18n._('─ Actions ─') == '─ 操作 ─'

    def test_disable_lan_zh(self):
        i18n.set_language('zh')
        assert i18n._('[o]Disable LAN') == '[o]断开连接'

    def test_enable_lan_zh(self):
        i18n.set_language('zh')
        assert i18n._('[o]Enable LAN') == '[o]连接社区'

    def test_back_compact_zh(self):
        i18n.set_language('zh')
        assert i18n._('[l]Back [c]Compact Mode') == '[l]返回 [c]紧凑模式'

    def test_edit_username_zh(self):
        i18n.set_language('zh')
        assert i18n._('═ Edit Name ═') == '═ 修改名称 ═'

    def test_not_set_zh(self):
        i18n.set_language('zh')
        assert i18n._('(not set)') == '(未设置)'

    def test_current_username_zh(self):
        i18n.set_language('zh')
        assert i18n._('Current name: {}').format('test') == '当前名称: test'

    def test_new_username_zh(self):
        i18n.set_language('zh')
        assert i18n._('New name: {}_').format('abc') == '新名称: abc_'

    def test_confirm_cancel_zh(self):
        i18n.set_language('zh')
        assert i18n._('[Enter]Confirm [ESC]Cancel') == '[Enter]确认 [ESC]取消'

    def test_connected_status_zh(self):
        i18n.set_language('zh')
        assert i18n._('Username: {}  |  Players online: {}').format('user', 3) == '用户名: user  |  在线玩家: 3'

    def test_visiting_zh(self):
        i18n.set_language('zh')
        assert i18n._('★ Visiting ({}m{}s)').format(5, 30) == '★ 正在拜访中 (5分30秒)'

    def test_being_visited_zh(self):
        i18n.set_language('zh')
        assert i18n._('★ {} is visiting you ({}m{}s)').format('Fluffy', 3, 15) == '★ Fluffy 正在拜访你 (3分15秒)'

    def test_visit_actions_zh(self):
        i18n.set_language('zh')
        assert i18n._('[e]End Visit [f]Remote Feed [p]Remote Play') == '[e]结束拜访 [f]远程喂食 [p]远程玩耍'

    def test_peer_actions_zh(self):
        i18n.set_language('zh')
        assert i18n._('[1-9]Visit Player [u]Edit Username') == '[1-9]拜访玩家 [u]修改名称'

    def test_edit_username_hint_zh(self):
        i18n.set_language('zh')
        assert i18n._('[u]Edit Username') == '[u]修改名称'

    def test_edit_username_hint_en(self):
        i18n.set_language('en')
        assert i18n._('[u]Edit Username') == '[u]Edit Username'

    def test_pagination_hint_zh(self):
        i18n.set_language('zh')
        assert i18n._('Page: [ = Previous  ] = Next') == '翻页: [ = 上一页  ] = 下一页'

    def test_pagination_hint_en(self):
        i18n.set_language('en')
        assert i18n._('Page: [ = Previous  ] = Next') == 'Page: [ = Previous  ] = Next'

    def test_visitor_label_zh(self):
        i18n.set_language('zh')
        assert i18n._('  [Visitor] {} (from {})').format('Fluffy', 'user1') == '  [访客] Fluffy (来自 user1)'

    def test_lan_panel_en(self):
        i18n.set_language('en')
        assert i18n._('═ Community Plaza ═') == '═ Community Plaza ═'
        assert i18n._('Master') == 'Master'
        assert i18n._('Slave') == 'Slave'


class TestMiscMessagesI18n:
    """Clipboard, autostart, and other messages."""

    def test_copied_zh(self):
        i18n.set_language('zh')
        assert i18n._('Copied to clipboard!') == '已复制到剪贴板！'

    def test_failed_copy_zh(self):
        i18n.set_language('zh')
        assert i18n._('Failed to copy') == '复制失败'

    def test_autostart_updated_zh(self):
        i18n.set_language('zh')
        assert i18n._('Auto-start setting updated') == '已更新开机自启动设置'

    def test_setting_failed_zh(self):
        i18n.set_language('zh')
        assert i18n._('Setting failed: {}').format('access denied') == '设置失败: access denied'

    def test_ascii_pet_tray_tip_en(self):
        i18n.set_language('en')
        assert i18n._('ASCII Pet') == 'ASCII Pet'
