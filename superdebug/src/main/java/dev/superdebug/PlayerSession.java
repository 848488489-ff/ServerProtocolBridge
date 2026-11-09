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
import java.util.Comparator;
import java.util.Deque;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
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
    static final String PACKET_IN_HANDLER = "superdebug_packet_in";
    static final String PACKET_OUT_HANDLER = "superdebug_packet_out";

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
    private final PacketStats packetStats = new PacketStats();
    private final Object pingLock = new Object();
    private final Deque<Integer> pingHistory = new ArrayDeque<>();
    private final Object packetLock = new Object();
    private final Deque<RecentFrame> recentFrames = new ArrayDeque<>();

    private volatile Channel channel;
    private volatile FrameTap frameIn;
    private volatile FrameTap frameOut;
    private volatile PacketTap packetIn;
    private volatile PacketTap packetOut;
    private volatile SniffSession sniff;
    private volatile String installError;
    private volatile boolean closed;

    private int lastPing = Integer.MIN_VALUE;
    private long lastSampleAt;
    private long lastChangeAt;

    /** Precise Post detection: last inbound ACTION packet nanotime (event loop). */
    private long lastActionNanos;
    /** Last inbound packet nanotime (event loop), for inter-packet gaps. */
    private long lastInPacketNanos;

    /** Sniff pairing slots, touched only from the channel event loop. */
    private PendingFrame pendingInFrame;
    private String pendingOutName;
    private boolean pendingOutNameValid;

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

    PacketStats packetStats() {
        return packetStats;
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
            removeIfPresent(found, PACKET_IN_HANDLER);
            removeIfPresent(found, PACKET_OUT_HANDLER);

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

            // Packet-object taps: read names/categories from the live server.
            // Inbound goes just before the packet listener (after the decoder);
            // outbound goes just before the encoder.
            String packetHandler = pipelineHandlerName(found, "packet_handler");
            if (packetHandler != null) {
                packetIn = new PacketTap(this, PacketTap.Direction.IN);
                found.pipeline().addBefore(packetHandler, PACKET_IN_HANDLER, packetIn);
            } else {
                packetIn = null;
                installError = "pipeline has no 'packet_handler' (packet names unavailable)";
            }
            if (found.pipeline().get("encoder") != null) {
                packetOut = new PacketTap(this, PacketTap.Direction.OUT);
                found.pipeline().addBefore("encoder", PACKET_OUT_HANDLER, packetOut);
            } else {
                packetOut = null;
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

    /**
     * Finds the pipeline name for the packet listener.  It is normally
     * {@code packet_handler}, but some servers add it under a generated name,
     * so fall back to scanning for a handler whose class name ends with the
     * packet-listener marker.
     */
    private static String pipelineHandlerName(Channel channel, String preferred) {
        if (channel.pipeline().get(preferred) != null) {
            return preferred;
        }
        for (Map.Entry<String, io.netty.channel.ChannelHandler> entry
                : channel.pipeline()) {
            String handlerName = entry.getKey();
            String handlerClass = entry.getValue().getClass().getName();
            if (handlerClass.contains("ServerGamePacketListener")
                    || handlerClass.contains("ServerConfigurationPacketListener")
                    || handlerClass.contains("ServerLoginPacketListener")) {
                return handlerName;
            }
        }
        return null;
    }

    void detach() {
        Channel current = channel;
        channel = null;
        frameIn = null;
        frameOut = null;
        packetIn = null;
        packetOut = null;
        if (current == null) {
            return;
        }
        removeIfPresent(current, FRAME_IN_HANDLER);
        removeIfPresent(current, FRAME_OUT_HANDLER);
        removeIfPresent(current, PACKET_IN_HANDLER);
        removeIfPresent(current, PACKET_OUT_HANDLER);
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
     * Frame-level hook, called by the frame taps for every complete frame in
     * both directions, regardless of whether a sniffer is active.
     * {@code gapNanos} is the interval since the previous complete frame in the
     * same direction, or -1 for the first frame.
     *
     * <p>The byte-level {@code capture} (non-null only while sniffing) is paired
     * with the packet name that the corresponding packet tap records.
     */
    void onFrameTap(FrameTap.Direction direction, int frameLength, long gapNanos,
                    int packetId, byte[] capture, int capturePosition,
                    boolean compressed, boolean truncated) {
        boolean inbound = direction == FrameTap.Direction.IN;
        stats.recordGap(inbound, gapNanos, service.postRiskGapNanos());

        if (!inbound) {
            // OUTBOUND: the packet name was already recorded by the outbound tap.
            String name = pendingOutNameValid ? pendingOutName : null;
            pendingOutNameValid = false;
            emitSniff(FrameTap.Direction.OUT, name,
                    new PendingFrame(frameLength, gapNanos, packetId,
                            capture, capturePosition, compressed, truncated));
            return;
        }

        // INBOUND: stash the frame info; the inbound packet tap pairs it with
        // the decoded packet name just after this frame.
        pendingInFrame = new PendingFrame(frameLength, gapNanos, packetId,
                capture, capturePosition, compressed, truncated);
    }

    /**
     * Packet-level hook, called by the packet taps for every decoded packet in
     * both directions.  This is where packet names/categories come from the
     * live server (no hard-coded id table) and where the precise action-to-
     * movement Post detection and the recent-frame ring buffer are updated.
     */
    void onDecodedPacket(PacketTap.Direction direction, Object packet) {
        boolean inbound = direction == PacketTap.Direction.IN;
        String official = PacketNames.officialName(packet);
        PacketNames.Category category = PacketNames.category(official);
        long now = System.nanoTime();

        packetStats.record(inbound, official, category);

        if (!inbound) {
            // Remember the name for the matching outbound frame.
            pendingOutName = official;
            pendingOutNameValid = true;
            return;
        }

        // Precise GrimAC Post detection: an ACTION packet immediately followed
        // by a MOVE packet (gap under the threshold) is the signature of a web
        // client that stalled and then flushed a burst.
        if (category == PacketNames.Category.MOVE && lastActionNanos > 0
                && now - lastActionNanos < service.postRiskGapNanos()) {
            packetStats.postActionMove.increment();
        }
        if (category == PacketNames.Category.ACTION) {
            lastActionNanos = now;
        }

        long gap = lastInPacketNanos == 0 ? -1 : now - lastInPacketNanos;
        lastInPacketNanos = now;

        synchronized (packetLock) {
            recentFrames.addLast(new RecentFrame(now, official, category, gap));
            while (recentFrames.size() > service.packetHistorySize()) {
                recentFrames.removeFirst();
            }
        }

        // Pair with the frame info stashed by the inbound frame tap.
        PendingFrame frame = pendingInFrame;
        pendingInFrame = null;
        emitSniff(FrameTap.Direction.IN, official, frame);
    }

    private void emitSniff(FrameTap.Direction direction, String officialName,
                           PendingFrame frame) {
        SniffSession current = sniff;
        if (current == null || frame == null) {
            return;
        }
        current.onDecodedPacket(direction == FrameTap.Direction.IN
                        ? SniffSession.Direction.IN
                        : SniffSession.Direction.OUT,
                officialName, frame.packetId, frame.frameLength, frame.gapNanos,
                frame.capture, frame.capturePosition, frame.compressed,
                frame.truncated);
    }

    /** Snapshot of the recent inbound packets (newest last). */
    List<RecentFrame> recentPacketSnapshot(int limit) {
        synchronized (packetLock) {
            List<RecentFrame> snapshot = new ArrayList<>(recentFrames);
            if (limit > 0 && snapshot.size() > limit) {
                snapshot = snapshot.subList(snapshot.size() - limit, snapshot.size());
            }
            return snapshot;
        }
    }

    /** Top inbound packet names by count (highest first). */
    List<Map.Entry<String, Long>> topInboundPackets(int limit) {
        return topByName(packetStats.inByName, limit);
    }

    /** Top outbound packet names by count (highest first). */
    List<Map.Entry<String, Long>> topOutboundPackets(int limit) {
        return topByName(packetStats.outByName, limit);
    }

    private static List<Map.Entry<String, Long>> topByName(
            Map<String, LongAdder> source, int limit) {
        List<Map.Entry<String, Long>> result = new ArrayList<>();
        for (Map.Entry<String, LongAdder> entry : source.entrySet()) {
            result.add(Map.entry(entry.getKey(), entry.getValue().sum()));
        }
        result.sort(Comparator.comparingLong((Map.Entry<String, Long> e) -> e.getValue())
                .reversed().thenComparing(Map.Entry::getKey));
        if (limit > 0 && result.size() > limit) {
            result = result.subList(0, limit);
        }
        return result;
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

    /**
     * Per-packet diagnostics, keyed by the official registry name read from the
     * live server (no hard-coded id table).  Counters are split by direction and
     * by coarse category; the per-name maps drive the top-N breakdown.
     */
    static final class PacketStats {
        final LongAdder inPackets = new LongAdder();
        final LongAdder outPackets = new LongAdder();
        final LongAdder inMove = new LongAdder();
        final LongAdder inAction = new LongAdder();
        final LongAdder inMisc = new LongAdder();
        final LongAdder outMove = new LongAdder();
        final LongAdder outAction = new LongAdder();
        final LongAdder outMisc = new LongAdder();
        final LongAdder inUnknown = new LongAdder();
        /** Precise Post count: an ACTION packet followed by a MOVE packet under
         *  the configured gap threshold. */
        final LongAdder postActionMove = new LongAdder();
        final ConcurrentHashMap<String, LongAdder> inByName = new ConcurrentHashMap<>();
        final ConcurrentHashMap<String, LongAdder> outByName = new ConcurrentHashMap<>();

        void record(boolean inbound, String officialName, PacketNames.Category category) {
            if (inbound) {
                inPackets.increment();
                switch (category) {
                    case MOVE -> inMove.increment();
                    case ACTION -> inAction.increment();
                    default -> inMisc.increment();
                }
                if (officialName == null) {
                    inUnknown.increment();
                } else {
                    inByName.computeIfAbsent(officialName, k -> new LongAdder()).increment();
                }
            } else {
                outPackets.increment();
                switch (category) {
                    case MOVE -> outMove.increment();
                    case ACTION -> outAction.increment();
                    default -> outMisc.increment();
                }
                if (officialName != null) {
                    outByName.computeIfAbsent(officialName, k -> new LongAdder()).increment();
                }
            }
        }

        void reset() {
            inPackets.reset();
            outPackets.reset();
            inMove.reset();
            inAction.reset();
            inMisc.reset();
            outMove.reset();
            outAction.reset();
            outMisc.reset();
            inUnknown.reset();
            postActionMove.reset();
            inByName.clear();
            outByName.clear();
        }
    }

    /** One recent inbound packet, for the ring-buffer display. */
    static final class RecentFrame {
        final long nanos;
        final String officialName;
        final PacketNames.Category category;
        final long gapNanos;

        RecentFrame(long nanos, String officialName, PacketNames.Category category, long gapNanos) {
            this.nanos = nanos;
            this.officialName = officialName;
            this.category = category;
            this.gapNanos = gapNanos;
        }
    }

    /** Frame-level info stashed for pairing with a decoded packet name. */
    private static final class PendingFrame {
        final int frameLength;
        final long gapNanos;
        final int packetId;
        final byte[] capture;
        final int capturePosition;
        final boolean compressed;
        final boolean truncated;

        PendingFrame(int frameLength, long gapNanos, int packetId,
                     byte[] capture, int capturePosition,
                     boolean compressed, boolean truncated) {
            this.frameLength = frameLength;
            this.gapNanos = gapNanos;
            this.packetId = packetId;
            this.capture = capture;
            this.capturePosition = capturePosition;
            this.compressed = compressed;
            this.truncated = truncated;
        }
    }
}
