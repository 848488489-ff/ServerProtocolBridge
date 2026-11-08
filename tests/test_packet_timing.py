"""数据包发送时序控制的单元测试。

覆盖两件事：配置项默认开启（老配置文件也默认开启），以及节奏器只在
突发时产生等待、正常节奏下不增加任何延迟。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from proxy.config import Config  # noqa: E402
from proxy.packet_timing import DEFAULT_MIN_GAP, PacketPacer  # noqa: E402


class PacketPacerTests(unittest.TestCase):
    def test_normal_tick_rate_never_waits(self):
        """每秒 20 个包（原版移动节奏）不应产生任何等待。"""
        pacer = PacketPacer()
        for index in range(40):
            self.assertEqual(pacer.reserve(100.0 + index * 0.05), 0.0)
        self.assertEqual(pacer.waits, 0)

    def test_burst_is_spread_by_min_gap(self):
        """同一瞬间到达的包按最小间隔依次排开。"""
        pacer = PacketPacer(0.012)
        delays = [pacer.reserve(100.0) for _ in range(5)]
        self.assertEqual(delays[0], 0.0)
        for index, delay in enumerate(delays[1:], start=1):
            self.assertAlmostEqual(delay, 0.012 * index, places=6)
        self.assertEqual(pacer.waits, 4)

    def test_gap_is_configurable_and_reset(self):
        pacer = PacketPacer(0.02)
        self.assertAlmostEqual(pacer.reserve(50.0), 0.0)
        self.assertAlmostEqual(pacer.reserve(50.0), 0.02, places=6)
        pacer.reset()
        self.assertAlmostEqual(pacer.reserve(50.0), 0.0)
        self.assertEqual(pacer.waits, 0)

    def test_default_gap_covers_grim_threshold(self):
        """默认间隔必须大于 Grim Post 检查的 10 毫秒门槛。"""
        self.assertGreater(DEFAULT_MIN_GAP, 0.010)


class PacketTimingConfigTests(unittest.TestCase):
    def test_enabled_by_default(self):
        self.assertTrue(Config().packet_timing)

    def test_old_config_file_still_enables_it(self):
        """老配置文件没有这个键时，应当取默认值 True。"""
        config = Config.from_dict({'config_version': 1, 'target': 'example.org'})
        self.assertTrue(config.packet_timing)

    def test_can_be_disabled_explicitly(self):
        config = Config.from_dict({'packet_timing': False})
        self.assertFalse(config.packet_timing)


if __name__ == '__main__':
    unittest.main()
