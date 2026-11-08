"""客户端到服务器的数据包发送节奏控制。

网页版客户端（EaglercraftX 等）运行在浏览器里，卡顿、后台标签页节流或网络
抖动之后，往往会把多个游戏刻的数据包挤在同一瞬间发出。服务器端的反作弊
（例如 Grim 的 Post / PacketOrderE 检查）按游戏刻预测数据包的到达顺序：
动作包（换手、使用物品等）距离上一个移动包不足 10 毫秒时，会被记入
“包序异常”的缓冲，连续出现就会告警。

这里不解析任何数据包，也不知道游戏版本，只保证客户端到服务器方向上任意
两个包之间至少间隔 ``min_gap`` 秒。正常节奏（每秒约 20 个移动包）本来就
大于这个间隔，不会增加任何延迟；只有卡顿之后的突发才会被摊开。
"""

from __future__ import annotations

import time

# 默认最小间隔。Grim 的 Post 检查用 10 毫秒作为“动作包紧跟在移动包之后”
# 的门槛；这里留 2 毫秒余量，避免网络抖动把间隔压回门槛以内。
DEFAULT_MIN_GAP = 0.012


class PacketPacer:
    """按最小间隔为每个待发数据包预留一个发送时刻。

    ``reserve()`` 是纯同步的：它返回调用方还需要等待的秒数，真正的等待由
    异步发送循环完成。这样既不会在事件循环里忙等，也方便单元测试注入时间。
    """

    def __init__(self, min_gap: float = DEFAULT_MIN_GAP):
        self.min_gap = max(0.0, float(min_gap))
        self._next_at = 0.0
        self.waits = 0          # 发生过等待的包数（诊断用）
        self.waited = 0.0       # 累计等待秒数（诊断用）

    def reserve(self, now: float | None = None) -> float:
        """为一个数据包预留发送时刻，返回还需要等待的秒数。"""
        if now is None:
            now = time.monotonic()
        delay = 0.0
        if self._next_at > now:
            delay = self._next_at - now
        send_at = now + delay
        self._next_at = send_at + self.min_gap
        if delay > 0.0:
            self.waits += 1
            self.waited += delay
        return delay

    def reset(self) -> None:
        """连接重启或阶段切换时清空节奏，避免把旧连接的等待带到新连接。"""
        self._next_at = 0.0
        self.waits = 0
        self.waited = 0.0
