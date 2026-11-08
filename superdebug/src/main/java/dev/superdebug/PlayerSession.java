package dev.superdebug;

import io.netty.buffer.ByteBuf;
import io.netty.channel.Channel;
import io.netty.channel.ChannelDuplexHandler;
import io.netty.channel.ChannelHandlerContext;
import io.netty.channel.ChannelPromise;
import org.bukkit.Bukkit;
import org.bukkit.entity.Player;

import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketAddress;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.LongAdder;

/**
 * Per-player state: ping history, connection metadata, Netty counters and the
 * currently active packet sniffer.
 */
final class PlayerSession {

    static final String WIRE_HANDLER = "superdebug_wire";
    static final String FRAME_IN_HANDLER = "superdebug_frame_in";
    static final String FRAME_OUT_HANDLER = "superdebug_frame_out";

    private final DebugService service;
    private final UUID uuid;
    private final String name;
    private final long joinedAt;
    private final long preLoginAt;
    private final long loginDelayMs;
    private final String joinAddress;
    private final String joinVirtualHost;
    private final String joinHaProxy;
    private final int joinProtocol;
    private final String joinBrand;
    private final String joinLocale;
    private final int joinViewDistance;

    private final TrafficStats stats = new TrafficStats();
    private final Object pingLock = new Object();
    private final Deque<Integer> pingHistory = new ArrayDeque<>();

    private volatile Channel channel;
    private volatile FrameTap frameIn;
    private volatile FrameTap frameOut;
    private volatile SniffSession sniff;
    private volatile String installError;
    private volatile boolean closed;

    private int lastPing = Integer.MIN_VALUE;
    private long lastSampleAt;
    private long lastChangeAt;

    PlayerSession(DebugService service, Player player, DebugService.PendingLogin pending) {
        this.service = service;
        this.uuid = player.getUniqueId();
        this.name = player.getName();
        this.joinedAt = System.currentTimeMillis();
        this.preLoginAt = pending == null ? joinedAt : pending.time;
        this.loginDelayMs = Math.max(0, joinedAt - preLoginAt);
        this.joinAddress = address(player.getAddress());
        this.joinVirtualHost = address(player.getVirtualHost());
        this.joinHaProxy = address(player.getHAProxyAddress());
        this.joinProtocol = player.getProtocolVersion();
        this.joinBrand = safe(player.getClientBrandName(), "unknown");
        this.joinLocale = safe(player.getLocale(), "unknown");
        this.joinViewDistance = player.getClientViewDistance();
        this.lastChangeAt = joinedAt;
    }

    UUID uuid() {
        return uuid;
    }

    String name() {
        return name;
    }

    Player player() {
        return Bukkit.getPlayer(uuid);
    }

    String joinAddress() {
        return joinAddress;
    }

    String joinVirtualHost() {
        return joinVirtualHost;
    }

    String joinHaProxy() {
        return joinHaProxy;
    }

    int joinProtocol() {
        return joinProtocol;
    }

    String joinBrand() {
        return joinBrand;
    }

    String joinLocale() {
        return joinLocale;
    }

    int joinViewDistance() {
        return joinViewDistance;
    }

    long joinedAt() {
        return joinedAt;
    }

    long loginDelayMs() {
        return loginDelayMs;
    }

    long sessionAgeMs() {
        return Math.max(0, System.currentTimeMillis() - joinedAt);
    }

    Channel channel() {
        return channel;
    }

    String installError() {
        return installError;
    }

    TrafficStats stats() {
        return stats;
    }

    void attachIfNeeded(Player player) {
        if (closed || channel != null) {
            return;
        }
        attach(player);
    }

    void attach(Player player) {
        if (closed) {
            return;
        }

        NmsAccess.Info info = NmsAccess.read(player);
        Channel found = info.channel;
        if (found == null) {
            installError = "channel unavailable"
                    + (info.error == null ? "" : " (" + info.error + ")");
            return;
        }

        Channel previous = channel;
        if (previous == found
                && previous.pipeline().get(WIRE_HANDLER) != null
                && previous.pipeline().get(FRAME_IN_HANDLER) != null
                && previous.pipeline().get(FRAME_OUT_HANDLER) != null) {
            return;
        }

        try {
            removeIfPresent(found, WIRE_HANDLER);
            removeIfPresent(found, FRAME_IN_HANDLER);
            removeIfPresent(found, FRAME_OUT_HANDLER);

            found.pipeline().addFirst(WIRE_HANDLER, new WireStatsHandler(stats));

            if (found.pipeline().get("splitter") == null) {
                installError = "pipeline has no 'splitter' handler";
            } else {
                frameIn = new FrameTap(this, FrameTap.Direction.IN);
                found.pipeline().addBefore("splitter", FRAME_IN_HANDLER, frameIn);
            }

            if (found.pipeline().get("prepender") == null) {
                installError = "pipeline has no 'prepender' handler";
            } else {
                frameOut = new FrameTap(this, FrameTap.Direction.OUT);
                found.pipeline().addBefore("prepender", FRAME_OUT_HANDLER, frameOut);
            }

            channel = found;
            stats.startedAtNanos = System.nanoTime();
            if (installError == null) {
                installError = null;
            }
        } catch (Throwable t) {
            installError = t.getClass().getSimpleName()
                    + (t.getMessage() == null ? "" : ": " + t.getMessage());
            service.plugin().getLogger().warning("Could not install Netty taps for "
                    + name + ": " + installError);
        }
    }

    void detach() {
        Channel current = channel;
        channel = null;
        frameIn = null;
        frameOut = null;
        if (current == null) {
            return;
        }
        removeIfPresent(current, FRAME_IN_HANDLER);
        removeIfPresent(current, FRAME_OUT_HANDLER);
        removeIfPresent(current, WIRE_HANDLER);
    }

    void close(String reason) {
        if (closed) {
            return;
        }
        closed = true;
        stopSniff(reason);
        detach();
    }

    void sample(int historySize) {
        Player player = player();
        if (player == null) {
            return;
        }
        long now = System.currentTimeMillis();
        int ping = Math.max(0, player.getPing());
        synchronized (pingLock) {
            pingHistory.addLast(ping);
            while (pingHistory.size() > Math.max(2, historySize)) {
                pingHistory.removeFirst();
            }
            if (lastPing == Integer.MIN_VALUE || ping != lastPing) {
                lastPing = ping;
                lastChangeAt = now;
            }
            lastSampleAt = now;
        }
    }

    PingSnapshot pingSnapshot() {
        long now = System.currentTimeMillis();
        synchronized (pingLock) {
            if (pingHistory.isEmpty()) {
                sample(service.pingHistorySize());
            }

            int current = pingHistory.isEmpty() ? 0 : pingHistory.peekLast();
            int min = Integer.MAX_VALUE;
            int max = Integer.MIN_VALUE;
            long sum = 0;
            long deltaSum = 0;
            int deltaCount = 0;
            int previous = Integer.MIN_VALUE;

            for (int value : pingHistory) {
                min = Math.min(min, value);
                max = Math.max(max, value);
                sum += value;
                if (previous != Integer.MIN_VALUE) {
                    deltaSum += Math.abs(value - previous);
                    deltaCount++;
                }
                previous = value;
            }

            if (pingHistory.isEmpty()) {
                min = 0;
                max = 0;
            }

            int count = pingHistory.size();
            double average = count == 0 ? 0.0 : (double) sum / count;
            double jitter = deltaCount == 0 ? 0.0 : (double) deltaSum / deltaCount;
            int trend = 0;
            if (count >= 2) {
                int index = 0;
                int previousValue = 0;
                for (int value : pingHistory) {
                    if (index == count - 2) {
                        previousValue = value;
                    }
                    index++;
                }
                trend = current - previousValue;
            }

            List<Integer> history = new ArrayList<>(pingHistory);
            return new PingSnapshot(current, min, max, average, jitter, count,
                    trend, history, now - lastSampleAt, now - lastChangeAt);
        }
    }

    String route() {
        Player player = player();
        if (player == null) {
            return "offline";
        }
        if (player.getHAProxyAddress() != null) {
            return "haproxy";
        }
        InetSocketAddress remote = player.getAddress();
        if (remote != null && remote.getAddress() != null
                && remote.getAddress().isLoopbackAddress()) {
            return "loopback";
        }
        return "direct";
    }

    void startSniff(int maxPackets, boolean hex, Set<Integer> filter) {
        stopSniff("restarted");
        sniff = new SniffSession(service.plugin(), name, maxPackets, hex, filter,
                service.sniffMaxFrameBytes(), service.sniffToFile());
    }

    void stopSniff(String reason) {
        SniffSession current = sniff;
        sniff = null;
        if (current != null) {
            current.stop(reason);
        }
    }

    boolean sniffActive() {
        SniffSession current = sniff;
        return current != null && current.isActive();
    }

    String sniffStatus() {
        SniffSession current = sniff;
        if (current == null) {
            return name + ": inactive";
        }
        return name + ": " + (current.isActive() ? "active" : "stopping")
                + ", captured=" + current.emittedCount() + "/" + current.maxPackets()
                + (current.filePath() == null ? "" : ", file=" + current.filePath());
    }

    int maxSniffCaptureBytes() {
        return service.sniffMaxFrameBytes();
    }

    /**
     * Frame timing hook, called for every complete frame in both directions
     * regardless of whether a sniffer is active.  {@code gapNanos} is the
     * interval since the previous complete frame in the same direction, or -1
     * for the first frame.
     */
    void onFrameTiming(FrameTap.Direction direction, int frameLength, long gapNanos) {
        stats.recordGap(direction == FrameTap.Direction.IN, gapNanos,
                service.postRiskGapNanos());
    }

    void onSniffFrame(FrameTap.Direction direction, byte[] body, int bodyLength,
                      int frameLength, boolean compressed, boolean truncated, long gapNanos) {
        SniffSession current = sniff;
        if (current != null) {
            current.onFrame(direction == FrameTap.Direction.IN
                            ? SniffSession.Direction.IN
                            : SniffSession.Direction.OUT,
                    body, bodyLength, frameLength, compressed, truncated, gapNanos);
        }
    }

    private static void removeIfPresent(Channel channel, String name) {
        try {
            if (channel.pipeline().get(name) != null) {
                channel.pipeline().remove(name);
            }
        } catch (Throwable ignored) {
            // The channel may be closing.
        }
    }

    static String address(SocketAddress address) {
        if (address == null) {
            return "none";
        }
        String value = address.toString();
        if (value.startsWith("/")) {
            value = value.substring(1);
        }
        return value;
    }

    static String address(InetAddress address) {
        return address == null ? "none" : address.getHostAddress();
    }

    static String safe(String value, String fallback) {
        return value == null || value.isEmpty() ? fallback : value;
    }

    static String duration(long millis) {
        if (millis < 1000) {
            return millis + "ms";
        }
        long seconds = millis / 1000;
        if (seconds < 60) {
            return String.format(Locale.ROOT, "%.1fs", millis / 1000.0);
        }
        long minutes = seconds / 60;
        long restSeconds = seconds % 60;
        if (minutes < 60) {
            return String.format(Locale.ROOT, "%dm%02ds", minutes, restSeconds);
        }
        long hours = minutes / 60;
        long restMinutes = minutes % 60;
        return String.format(Locale.ROOT, "%dh%02dm", hours, restMinutes);
    }

    static final class PingSnapshot {
        final int current;
        final int min;
        final int max;
        final double average;
        final double jitter;
        final int samples;
        final int trend;
        final List<Integer> history;
        final long sinceLastSampleMs;
        final long sinceLastChangeMs;

        PingSnapshot(int current, int min, int max, double average, double jitter,
                     int samples, int trend, List<Integer> history,
                     long sinceLastSampleMs, long sinceLastChangeMs) {
            this.current = current;
            this.min = min;
            this.max = max;
            this.average = average;
            this.jitter = jitter;
            this.samples = samples;
            this.trend = trend;
            this.history = history;
            this.sinceLastSampleMs = Math.max(0, sinceLastSampleMs);
            this.sinceLastChangeMs = Math.max(0, sinceLastChangeMs);
        }
    }

    static final class TrafficStats {
        final LongAdder wireInBytes = new LongAdder();
        final LongAdder wireOutBytes = new LongAdder();
        final LongAdder wireInMessages = new LongAdder();
        final LongAdder wireOutMessages = new LongAdder();
        final LongAdder frameInBytes = new LongAdder();
        final LongAdder frameOutBytes = new LongAdder();
        final LongAdder frameInPackets = new LongAdder();
        final LongAdder frameOutPackets = new LongAdder();
        final LongAdder frameErrors = new LongAdder();
        volatile long startedAtNanos = System.nanoTime();

        // 包时序诊断：同方向相邻帧间隔统计。inPostCount/outPostCount 记录
        // 间隔低于阈值（默认 10ms）的“包对”数——网页客户端卡顿后动作包与
        // 移动包挤在一起正是触发 GrimAC Post 检查的特征。
        final LongAdder inGaps = new LongAdder();
        final LongAdder outGaps = new LongAdder();
        final LongAdder inGapNanosSum = new LongAdder();
        final LongAdder outGapNanosSum = new LongAdder();
        final LongAdder inPostCount = new LongAdder();
        final LongAdder outPostCount = new LongAdder();
        final AtomicLong inMaxGapNanos = new AtomicLong();
        final AtomicLong outMaxGapNanos = new AtomicLong();

        void reset() {
            wireInBytes.reset();
            wireOutBytes.reset();
            wireInMessages.reset();
            wireOutMessages.reset();
            frameInBytes.reset();
            frameOutBytes.reset();
            frameInPackets.reset();
            frameOutPackets.reset();
            frameErrors.reset();
            inGaps.reset();
            outGaps.reset();
            inGapNanosSum.reset();
            outGapNanosSum.reset();
            inPostCount.reset();
            outPostCount.reset();
            inMaxGapNanos.set(0);
            outMaxGapNanos.set(0);
            startedAtNanos = System.nanoTime();
        }

        /**
         * Records one frame gap.  {@code gapNanos < 0} means the first frame in
         * this direction and is ignored.
         */
        void recordGap(boolean inbound, long gapNanos, long thresholdNanos) {
            if (gapNanos < 0) {
                return;
            }
            if (inbound) {
                inGaps.increment();
                inGapNanosSum.add(gapNanos);
                updateMax(inMaxGapNanos, gapNanos);
                if (gapNanos < thresholdNanos) {
                    inPostCount.increment();
                }
            } else {
                outGaps.increment();
                outGapNanosSum.add(gapNanos);
                updateMax(outMaxGapNanos, gapNanos);
                if (gapNanos < thresholdNanos) {
                    outPostCount.increment();
                }
            }
        }

        private static void updateMax(AtomicLong target, long value) {
            long current = target.get();
            while (value > current && !target.compareAndSet(current, value)) {
                current = target.get();
            }
        }
    }

    static final class WireStatsHandler extends ChannelDuplexHandler {
        private final TrafficStats stats;

        WireStatsHandler(TrafficStats stats) {
            this.stats = stats;
        }

        @Override
        public void channelRead(ChannelHandlerContext ctx, Object msg) throws Exception {
            if (msg instanceof ByteBuf buffer) {
                stats.wireInBytes.add(buffer.readableBytes());
                stats.wireInMessages.increment();
            }
            ctx.fireChannelRead(msg);
        }

        @Override
        public void write(ChannelHandlerContext ctx, Object msg, ChannelPromise promise) throws Exception {
            if (msg instanceof ByteBuf buffer) {
                stats.wireOutBytes.add(buffer.readableBytes());
                stats.wireOutMessages.increment();
            }
            ctx.write(msg, promise);
        }
    }
}
