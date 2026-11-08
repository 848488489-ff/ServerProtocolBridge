package dev.superdebug;

import io.netty.channel.Channel;
import io.netty.channel.ChannelHandler;
import io.netty.channel.ChannelOption;
import org.bukkit.Bukkit;
import org.bukkit.ChatColor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.player.AsyncPlayerPreLoginEvent;
import org.bukkit.event.player.PlayerJoinEvent;
import org.bukkit.event.player.PlayerKickEvent;
import org.bukkit.event.player.PlayerLoginEvent;
import org.bukkit.event.player.PlayerQuitEvent;
import org.bukkit.scheduler.BukkitTask;
import com.destroystokyo.paper.event.player.PlayerConnectionCloseEvent;

import java.io.IOException;
import java.lang.management.ManagementFactory;
import java.lang.management.RuntimeMXBean;
import java.lang.management.ThreadMXBean;
import java.net.SocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.Deque;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

public final class DebugService implements Listener {

    private static final int MAX_CONNECTION_LOG = 100;
    private static final DateTimeFormatter TIME_FORMAT =
            DateTimeFormatter.ofPattern("HH:mm:ss", Locale.ROOT);
    private static final DateTimeFormatter REPORT_TIME =
            DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss", Locale.ROOT);

    private final SuperDebugPlugin plugin;
    private final Map<UUID, PlayerSession> sessions = new ConcurrentHashMap<>();
    private final Map<UUID, PendingLogin> pendingLogins = new ConcurrentHashMap<>();
    private final Deque<ConnectionRecord> connectionLog = new ArrayDeque<>();
    private final Object connectionLogLock = new Object();

    private BukkitTask sampleTask;
    private BukkitTask watchTask;
    private int sampleIntervalSeconds = 5;
    private int pingHistorySize = 60;
    private int sniffDefaultMax = 50;
    private int sniffMaxFrameBytes = 2 * 1024 * 1024;
    private boolean sniffToFile;
    private int watchSeconds;
    private String watchMode = "all";
    /** GrimAC Post risk threshold in nanoseconds (default 10ms). */
    private long postRiskGapNanos = 10 * 1_000_000L;

    public DebugService(SuperDebugPlugin plugin) {
        this.plugin = plugin;
    }

    SuperDebugPlugin plugin() {
        return plugin;
    }

    int pingHistorySize() {
        return pingHistorySize;
    }

    int sniffMaxFrameBytes() {
        return sniffMaxFrameBytes;
    }

    boolean sniffToFile() {
        return sniffToFile;
    }

    /** GrimAC Post risk threshold in nanoseconds. */
    long postRiskGapNanos() {
        return postRiskGapNanos;
    }

    double postRiskGapMs() {
        return postRiskGapNanos / 1_000_000.0;
    }

    public void start() {
        loadSettings();
        startSampler();
        for (Player player : Bukkit.getOnlinePlayers()) {
            ensureSession(player).attach(player);
        }
    }

    public void stop() {
        if (sampleTask != null) {
            sampleTask.cancel();
            sampleTask = null;
        }
        stopWatch();
        for (PlayerSession session : new ArrayList<>(sessions.values())) {
            session.close("plugin disable");
        }
        sessions.clear();
        pendingLogins.clear();
    }

    private void loadSettings() {
        sampleIntervalSeconds = Math.max(1,
                plugin.getConfig().getInt("sample-interval-seconds", 5));
        pingHistorySize = Math.max(2,
                plugin.getConfig().getInt("ping-history-size", 60));
        sniffDefaultMax = Math.max(1,
                plugin.getConfig().getInt("sniff-default-max-packets", 50));
        sniffMaxFrameBytes = Math.max(1024,
                plugin.getConfig().getInt("sniff-max-frame-bytes", 2 * 1024 * 1024));
        sniffToFile = plugin.getConfig().getBoolean("sniff-log-to-file", false);
        postRiskGapNanos = Math.max(1,
                plugin.getConfig().getInt("post-risk-gap-ms", 10)) * 1_000_000L;
    }

    private void startSampler() {
        if (sampleTask != null) {
            sampleTask.cancel();
        }
        long period = Math.max(1, sampleIntervalSeconds) * 20L;
        sampleTask = Bukkit.getScheduler().runTaskTimer(plugin, this::sampleAll, period, period);
    }

    private void sampleAll() {
        for (Player player : Bukkit.getOnlinePlayers()) {
            PlayerSession session = ensureSession(player);
            session.attachIfNeeded(player);
            session.sample(pingHistorySize);
        }
    }

    private PlayerSession ensureSession(Player player) {
        PlayerSession existing = sessions.get(player.getUniqueId());
        if (existing != null) {
            return existing;
        }

        PendingLogin pending = pendingLogins.remove(player.getUniqueId());
        PlayerSession created = new PlayerSession(this, player, pending);
        PlayerSession raced = sessions.putIfAbsent(player.getUniqueId(), created);
        PlayerSession result = raced == null ? created : raced;
        result.attachIfNeeded(player);
        return result;
    }

    private List<PlayerSession> allSessions() {
        List<PlayerSession> result = new ArrayList<>();
        for (Player player : Bukkit.getOnlinePlayers()) {
            result.add(ensureSession(player));
        }
        result.sort(Comparator.comparing(PlayerSession::name, String.CASE_INSENSITIVE_ORDER));
        return result;
    }

    private PlayerSession findSession(String name) {
        if (name == null) {
            return null;
        }
        Player exact = Bukkit.getPlayerExact(name);
        if (exact == null) {
            for (Player online : Bukkit.getOnlinePlayers()) {
                if (online.getName().equalsIgnoreCase(name)) {
                    exact = online;
                    break;
                }
            }
        }
        return exact == null ? null : ensureSession(exact);
    }

    // ---------------------------------------------------------------------
    // Commands
    // ---------------------------------------------------------------------

    public List<String> help() {
        return Arrays.asList(
                "SuperDebug - console diagnostics for Minecraft TCP/WSS proxy debugging",
                "  debug ping [player]                 latency table for all players / one player",
                "  debug net [player|all]              channel, pipeline, socket, encryption, compression",
                "  debug traffic [player|all]          wire/frame byte and packet counters + rates",
                "  debug traffic reset [player|all]    reset counters",
                "  debug timing [player|all]           frame gap timing + GrimAC Post risk pairs",
                "  debug sniff <player|all> on [max] [hex] [filter]",
                "                                      packet ids/lengths to console (filter: 0x1A,0x08)",
                "  debug sniff <player|all> off        stop packet trace",
                "  debug sniff status                  active packet traces",
                "  debug watch [seconds] [ping|traffic|all]",
                "                                      periodic console report; 'debug watch off' stops",
                "  debug tps                           TPS, MSPT, memory, threads, chunks",
                "  debug log [count]                   recent login / join / quit / kick events",
                "  debug dump [player|all]             combined diagnostic report",
                "  debug report                        write full report to plugins/SuperDebug/reports",
                "  debug reload                        reload config.yml",
                "",
                "All reports go to the server console. Player senders also receive a copy.",
                "No output is produced automatically."
        );
    }

    public List<String> pingReport(String target) {
        sampleAll();

        if (target != null && !target.equalsIgnoreCase("all")) {
            PlayerSession session = findSession(target);
            if (session == null) {
                return Collections.singletonList("Player not online: " + target);
            }
            return pingDetail(session);
        }

        List<PlayerSession> online = allSessions();
        if (online.isEmpty()) {
            return Collections.singletonList("No players online.");
        }

        List<Row> rows = new ArrayList<>();
        for (PlayerSession session : online) {
            rows.add(new Row(session, session.pingSnapshot()));
        }
        rows.sort(Comparator.comparingInt((Row row) -> row.ping.current).reversed()
                .thenComparing(row -> row.session.name(), String.CASE_INSENSITIVE_ORDER));

        List<String> lines = new ArrayList<>();
        lines.add("=== Ping report ===");
        lines.add(String.format(Locale.ROOT,
                "Online: %d/%d   %s   sample every %ds",
                online.size(), Bukkit.getMaxPlayers(), tpsShort(), sampleIntervalSeconds));
        lines.add(String.format(Locale.ROOT,
                "%-16s %6s %5s %6s %5s %6s %4s %8s %-22s",
                "Player", "Ping", "Min", "Avg", "Max", "Jitter", "N", "Up", "Remote"));
        lines.add("-".repeat(94));

        for (Row row : rows) {
            Player player = row.session.player();
            String remote = player == null ? row.session.joinAddress()
                    : PlayerSession.address(player.getAddress());
            lines.add(String.format(Locale.ROOT,
                    "%-16s %5dms %5d %6.1f %5d %6.1f %4d %8s %-22s",
                    truncate(row.session.name(), 16),
                    row.ping.current,
                    row.ping.min,
                    row.ping.average,
                    row.ping.max,
                    row.ping.jitter,
                    row.ping.samples,
                    PlayerSession.duration(row.session.sessionAgeMs()),
                    truncate(remote, 22)));
        }

        int total = 0;
        int worst = 0;
        int best = Integer.MAX_VALUE;
        String worstName = "-";
        String bestName = "-";
        int loopback = 0;
        int haproxy = 0;
        int direct = 0;
        for (Row row : rows) {
            total += row.ping.current;
            if (row.ping.current >= worst) {
                worst = row.ping.current;
                worstName = row.session.name();
            }
            if (row.ping.current < best) {
                best = row.ping.current;
                bestName = row.session.name();
            }
            switch (row.session.route()) {
                case "loopback" -> loopback++;
                case "haproxy" -> haproxy++;
                default -> direct++;
            }
        }
        lines.add("-".repeat(94));
        lines.add(String.format(Locale.ROOT,
                "Summary: avg=%.1fms  worst=%s/%dms  best=%s/%dms  routes: loopback=%d haproxy=%d direct=%d",
                (double) total / rows.size(), worstName, worst, bestName, best,
                loopback, haproxy, direct));
        lines.add("Virtual hosts:");
        for (PlayerSession session : online) {
            Player player = session.player();
            String host = player == null ? session.joinVirtualHost()
                    : PlayerSession.address(player.getVirtualHost());
            lines.add(String.format(Locale.ROOT,
                    "  %-16s %-28s proto=%d brand=%s locale=%s view=%d",
                    truncate(session.name(), 16),
                    truncate(host, 28),
                    session.joinProtocol(),
                    truncate(session.joinBrand(), 12),
                    truncate(session.joinLocale(), 10),
                    session.joinViewDistance()));
        }
        return lines;
    }

    private List<String> pingDetail(PlayerSession session) {
        Player player = session.player();
        if (player == null) {
            return Collections.singletonList("Player not online: " + session.name());
        }
        session.sample(pingHistorySize);
        PlayerSession.PingSnapshot ping = session.pingSnapshot();

        List<String> lines = new ArrayList<>();
        lines.add("=== Ping detail: " + session.name() + " ===");
        lines.add(String.format(Locale.ROOT,
                "Current: %dms   Trend: %+dms   Samples: %d (history=%d)",
                ping.current, ping.trend, ping.samples, ping.history.size()));
        lines.add(String.format(Locale.ROOT,
                "Min: %dms   Avg: %.1fms   Max: %dms   Jitter: %.1fms",
                ping.min, ping.average, ping.max, ping.jitter));
        lines.add(String.format(Locale.ROOT,
                "Last sample: %s ago   Last change: %s ago",
                PlayerSession.duration(ping.sinceLastSampleMs),
                PlayerSession.duration(ping.sinceLastChangeMs)));

        List<Integer> history = ping.history;
        int from = Math.max(0, history.size() - 20);
        StringBuilder historyText = new StringBuilder();
        for (int i = from; i < history.size(); i++) {
            if (historyText.length() > 0) {
                historyText.append(' ');
            }
            historyText.append(history.get(i));
        }
        if (from > 0) {
            historyText.insert(0, "... ");
        }
        if (historyText.length() == 0) {
            historyText.append("none");
        }
        lines.add("History: " + historyText);

        lines.add(String.format(Locale.ROOT,
                "Session: %s   Login delay: %s   Route: %s",
                PlayerSession.duration(session.sessionAgeMs()),
                PlayerSession.duration(session.loginDelayMs()),
                session.route()));
        lines.add(String.format(Locale.ROOT,
                "Remote: %s   Virtual host: %s   HAProxy: %s",
                PlayerSession.address(player.getAddress()),
                PlayerSession.address(player.getVirtualHost()),
                PlayerSession.address(player.getHAProxyAddress())));
        lines.add(String.format(Locale.ROOT,
                "Protocol: %d   Brand: %s   Locale: %s   View distance: %d",
                player.getProtocolVersion(),
                PlayerSession.safe(player.getClientBrandName(), "unknown"),
                PlayerSession.safe(player.getLocale(), "unknown"),
                player.getClientViewDistance()));

        NmsAccess.Info info = NmsAccess.read(player);
        if (info.error != null) {
            lines.add("NMS: unavailable (" + info.error + ")");
        } else {
            lines.add(String.format(Locale.ROOT,
                    "NMS: latency=%s   protocol=%s   vhost=%s   encrypted=%s",
                    info.latency, info.protocolVersion,
                    PlayerSession.address(info.virtualHost), info.encrypted));
        }
        return lines;
    }

    public List<String> netReport(String target) {
        boolean all = target == null || target.equalsIgnoreCase("all");
        if (!all) {
            PlayerSession session = findSession(target);
            if (session == null) {
                return Collections.singletonList("Player not online: " + target);
            }
            return netBlock(session);
        }

        List<PlayerSession> online = allSessions();
        if (online.isEmpty()) {
            return Collections.singletonList("No players online.");
        }
        List<String> lines = new ArrayList<>();
        lines.add("=== Network (" + online.size() + " players) ===");
        for (PlayerSession session : online) {
            if (!lines.isEmpty()) {
                lines.add("");
            }
            lines.addAll(netBlock(session));
        }
        return lines;
    }

    private List<String> netBlock(PlayerSession session) {
        Player player = session.player();
        if (player == null) {
            return Collections.singletonList("Network: " + session.name() + " (offline)");
        }

        List<String> lines = new ArrayList<>();
        lines.add("=== Network: " + session.name() + " ===");
        lines.add(String.format(Locale.ROOT,
                "Session: %s   Login delay: %s   Route: %s",
                PlayerSession.duration(session.sessionAgeMs()),
                PlayerSession.duration(session.loginDelayMs()),
                session.route()));

        NmsAccess.Info info = NmsAccess.read(player);
        Channel channel = info.channel != null ? info.channel : session.channel();

        lines.add(String.format(Locale.ROOT,
                "Address: remote=%s   socket=%s   local=%s",
                PlayerSession.address(player.getAddress()),
                PlayerSession.address(player.getSocketAddress()),
                channel == null ? "?" : PlayerSession.address(channel.localAddress())));
        lines.add(String.format(Locale.ROOT,
                "Virtual host: %s   HAProxy: %s",
                PlayerSession.address(player.getVirtualHost()),
                PlayerSession.address(player.getHAProxyAddress())));
        lines.add(String.format(Locale.ROOT,
                "Client: protocol=%d   brand=%s   locale=%s   view-distance=%d",
                player.getProtocolVersion(),
                PlayerSession.safe(player.getClientBrandName(), "unknown"),
                PlayerSession.safe(player.getLocale(), "unknown"),
                player.getClientViewDistance()));

        if (info.error != null) {
            lines.add("NMS: unavailable (" + info.error + ")");
        } else {
            lines.add(String.format(Locale.ROOT,
                    "NMS: latency=%s   protocol=%s   vhost=%s   encrypted=%s",
                    info.latency, info.protocolVersion,
                    PlayerSession.address(info.virtualHost), info.encrypted));
        }

        if (channel == null) {
            lines.add("Channel: unavailable (Netty channel could not be resolved)");
        } else {
            lines.add(String.format(Locale.ROOT,
                    "Channel: %s#%s active=%s open=%s registered=%s writable=%s",
                    channel.getClass().getSimpleName(),
                    channel.id().asShortText(),
                    channel.isActive(), channel.isOpen(),
                    channel.isRegistered(), channel.isWritable()));
            lines.add(String.format(Locale.ROOT,
                    "Buffers: bytesBeforeWritable=%d   bytesBeforeUnwritable=%d   autoRead=%s",
                    channel.bytesBeforeWritable(), channel.bytesBeforeUnwritable(),
                    channel.config().isAutoRead()));
            lines.add("Event loop: " + channel.eventLoop());
            lines.add("Pipeline: " + pipelineString(channel));

            Integer threshold = NmsAccess.compressionThreshold(channel);
            boolean compression = NmsAccess.hasCompression(channel);
            boolean encryption = NmsAccess.hasEncryption(channel);
            lines.add(String.format(Locale.ROOT,
                    "Security: compression=%s   encryption=%s",
                    compression ? (threshold == null ? "on(threshold=?)" : "on(threshold=" + threshold + ")")
                            : "off",
                    encryption ? "on" : "off"));
            lines.add("Socket options: " + optionsString(channel));
            lines.add(trafficOneLine(session));
            if (session.installError() != null) {
                lines.add("Handler install: " + session.installError());
            }
        }
        return lines;
    }

    private String pipelineString(Channel channel) {
        List<String> names = channel.pipeline().names();
        StringBuilder out = new StringBuilder();
        for (String name : names) {
            ChannelHandler handler = channel.pipeline().get(name);
            if (out.length() > 0) {
                out.append(" -> ");
            }
            out.append(name).append('=')
                    .append(handler == null ? "?" : handler.getClass().getSimpleName());
        }
        return out.toString();
    }

    private String optionsString(Channel channel) {
        List<String> parts = new ArrayList<>();
        for (Map.Entry<ChannelOption<?>, Object> entry
                : channel.config().getOptions().entrySet()) {
            parts.add(entry.getKey().name() + "=" + entry.getValue());
        }
        Collections.sort(parts);
        return String.join(", ", parts);
    }

    public List<String> trafficReport(String target, boolean reset) {
        boolean all = target == null || target.equalsIgnoreCase("all");
        if (reset) {
            if (all) {
                List<PlayerSession> online = allSessions();
                for (PlayerSession session : online) {
                    session.stats().reset();
                }
                return Collections.singletonList("Traffic counters reset for "
                        + online.size() + " player(s).");
            }
            PlayerSession session = findSession(target);
            if (session == null) {
                return Collections.singletonList("Player not online: " + target);
            }
            session.stats().reset();
            return Collections.singletonList("Traffic counters reset for " + session.name() + ".");
        }

        sampleAll();
        if (!all) {
            PlayerSession session = findSession(target);
            if (session == null) {
                return Collections.singletonList("Player not online: " + target);
            }
            return trafficBlock(session);
        }

        List<PlayerSession> online = allSessions();
        if (online.isEmpty()) {
            return Collections.singletonList("No players online.");
        }

        List<String> lines = new ArrayList<>();
        lines.add("=== Traffic (" + online.size() + " players) ===");
        long totalWireIn = 0;
        long totalWireOut = 0;
        long totalFrameIn = 0;
        long totalFrameOut = 0;
        long totalPacketsIn = 0;
        long totalPacketsOut = 0;

        for (PlayerSession session : online) {
            if (lines.size() > 1) {
                lines.add("");
            }
            lines.addAll(trafficBlock(session));
            PlayerSession.TrafficStats stats = session.stats();
            totalWireIn += stats.wireInBytes.sum();
            totalWireOut += stats.wireOutBytes.sum();
            totalFrameIn += stats.frameInBytes.sum();
            totalFrameOut += stats.frameOutBytes.sum();
            totalPacketsIn += stats.frameInPackets.sum();
            totalPacketsOut += stats.frameOutPackets.sum();
        }

        lines.add("");
        lines.add(String.format(Locale.ROOT,
                "Totals: wire IN %s / OUT %s   frames IN %s / OUT %s   packets IN %s / OUT %s",
                bytes(totalWireIn), bytes(totalWireOut),
                bytes(totalFrameIn), bytes(totalFrameOut),
                count(totalPacketsIn), count(totalPacketsOut)));
        return lines;
    }

    private List<String> trafficBlock(PlayerSession session) {
        PlayerSession.TrafficStats stats = session.stats();
        long elapsedNanos = Math.max(1, System.nanoTime() - stats.startedAtNanos);
        long wireIn = stats.wireInBytes.sum();
        long wireOut = stats.wireOutBytes.sum();
        long frameIn = stats.frameInBytes.sum();
        long frameOut = stats.frameOutBytes.sum();
        long packetsIn = stats.frameInPackets.sum();
        long packetsOut = stats.frameOutPackets.sum();

        PlayerSession.PingSnapshot ping = session.pingSnapshot();
        List<String> lines = new ArrayList<>();
        lines.add(String.format(Locale.ROOT,
                "%s (ping=%dms, up=%s, counters=%s)",
                session.name(), ping.current,
                PlayerSession.duration(session.sessionAgeMs()),
                PlayerSession.duration(elapsedNanos / 1_000_000L)));
        lines.add(String.format(Locale.ROOT,
                "  wire   IN %s / %s msgs   OUT %s / %s msgs",
                bytes(wireIn), count(stats.wireInMessages.sum()),
                bytes(wireOut), count(stats.wireOutMessages.sum())));
        lines.add(String.format(Locale.ROOT,
                "  frames IN %s / %s pkts   OUT %s / %s pkts",
                bytes(frameIn), count(packetsIn),
                bytes(frameOut), count(packetsOut)));
        lines.add(String.format(Locale.ROOT,
                "  rates  IN %s   OUT %s   overhead IN %s OUT %s",
                rate(wireIn, elapsedNanos),
                rate(wireOut, elapsedNanos),
                overhead(wireIn, frameIn),
                overhead(wireOut, frameOut)));
        long errors = stats.frameErrors.sum();
        if (errors > 0) {
            lines.add("  frame parser errors: " + count(errors));
        }
        if (session.installError() != null) {
            lines.add("  handler install: " + session.installError());
        }
        return lines;
    }

    public List<String> timingReport(String target) {
        boolean all = target == null || target.equalsIgnoreCase("all");
        if (!all) {
            PlayerSession session = findSession(target);
            if (session == null) {
                return Collections.singletonList("Player not online: " + target);
            }
            return timingBlock(session);
        }

        List<PlayerSession> online = allSessions();
        if (online.isEmpty()) {
            return Collections.singletonList("No players online.");
        }
        List<String> lines = new ArrayList<>();
        lines.add("=== Frame timing (" + online.size() + " players) ===");
        lines.add(String.format(Locale.ROOT,
                "GrimAC Post risk threshold: gap < %.1fms between same-direction client packets",
                postRiskGapMs()));
        for (PlayerSession session : online) {
            if (lines.size() > 1) {
                lines.add("");
            }
            lines.addAll(timingBlock(session));
        }
        return lines;
    }

    private List<String> timingBlock(PlayerSession session) {
        PlayerSession.TrafficStats stats = session.stats();
        List<String> lines = new ArrayList<>();
        lines.add(String.format(Locale.ROOT,
                "%s   frames IN=%d OUT=%d   post-risk < %.1fms",
                session.name(),
                stats.frameInPackets.sum(), stats.frameOutPackets.sum(),
                postRiskGapMs()));
        lines.add(String.format(Locale.ROOT,
                "  IN  gaps=%d  avg=%.2fms  max=%.2fms  POST=%d",
                stats.inGaps.sum(),
                avgMs(stats.inGapNanosSum.sum(), stats.inGaps.sum()),
                ms(stats.inMaxGapNanos.get()),
                stats.inPostCount.sum()));
        lines.add(String.format(Locale.ROOT,
                "  OUT gaps=%d  avg=%.2fms  max=%.2fms  POST=%d",
                stats.outGaps.sum(),
                avgMs(stats.outGapNanosSum.sum(), stats.outGaps.sum()),
                ms(stats.outMaxGapNanos.get()),
                stats.outPostCount.sum()));
        lines.add(String.format(Locale.ROOT,
                "  counters active since %s   reset via 'debug traffic reset'",
                PlayerSession.duration(
                        Math.max(0, System.nanoTime() - stats.startedAtNanos) / 1_000_000L)));
        return lines;
    }

    public List<String> sniffCommand(String[] args) {
        if (args.length == 0) {
            return sniffUsage();
        }

        String target = args[0];
        if (target.equalsIgnoreCase("status")) {
            return sniffStatus();
        }

        if (args.length == 1) {
            return startSniff(target, sniffDefaultMax, false, Collections.emptySet());
        }

        String action = args[1].toLowerCase(Locale.ROOT);
        if (action.equals("off") || action.equals("stop")) {
            return stopSniff(target);
        }
        if (action.equals("status")) {
            return sniffStatus();
        }
        if (!action.equals("on") && !action.equals("start")) {
            return sniffUsage();
        }

        int index = 2;
        int max = sniffDefaultMax;
        if (index < args.length && !args[index].equalsIgnoreCase("hex")) {
            try {
                max = Integer.parseInt(args[index]);
                index++;
            } catch (NumberFormatException e) {
                return Collections.singletonList("Invalid packet limit: " + args[index]);
            }
        }
        max = Math.max(1, Math.min(5000, max));

        boolean hex = false;
        if (index < args.length && args[index].equalsIgnoreCase("hex")) {
            hex = true;
            index++;
        }

        Set<Integer> filter = Collections.emptySet();
        if (index < args.length) {
            Set<Integer> parsed = parseFilter(args[index]);
            if (parsed == null) {
                return Collections.singletonList("Invalid packet filter: " + args[index]
                        + " (use comma-separated decimal or 0x hex ids)");
            }
            filter = parsed;
            index++;
        }
        if (index != args.length) {
            return sniffUsage();
        }

        return startSniff(target, max, hex, filter);
    }

    private List<String> startSniff(String target, int max, boolean hex, Set<Integer> filter) {
        List<PlayerSession> targets = resolveSessions(target);
        if (targets.isEmpty()) {
            return Collections.singletonList(target.equalsIgnoreCase("all")
                    ? "No players online." : "Player not online: " + target);
        }

        List<String> lines = new ArrayList<>();
        for (PlayerSession session : targets) {
            session.startSniff(max, hex, filter);
            lines.add("Sniff started for " + session.name()
                    + ": max=" + max
                    + ", hex=" + hex
                    + ", filter=" + (filter.isEmpty() ? "all" : filter)
                    + ", output=console"
                    + (sniffToFile ? "+file" : ""));
        }
        return lines;
    }

    private List<String> stopSniff(String target) {
        List<PlayerSession> targets = resolveSessions(target);
        if (targets.isEmpty()) {
            return Collections.singletonList(target.equalsIgnoreCase("all")
                    ? "No players online." : "Player not online: " + target);
        }
        List<String> lines = new ArrayList<>();
        for (PlayerSession session : targets) {
            if (session.sniffActive()) {
                session.stopSniff("command");
                lines.add("Sniff stopped for " + session.name() + ".");
            } else {
                lines.add("Sniff is not active for " + session.name() + ".");
            }
        }
        return lines;
    }

    private List<String> sniffStatus() {
        List<String> lines = new ArrayList<>();
        for (PlayerSession session : allSessions()) {
            if (session.sniffActive()) {
                lines.add(session.sniffStatus());
            }
        }
        if (lines.isEmpty()) {
            lines.add("No active sniff sessions.");
        } else {
            lines.add(0, "Active sniff sessions:");
        }
        return lines;
    }

    private List<String> sniffUsage() {
        return Arrays.asList(
                "Usage: debug sniff <player|all> on [max] [hex] [filter]",
                "       debug sniff <player|all> off",
                "       debug sniff status",
                "Filter examples: 0x1A,0x08   or   26,8",
                "The optional 'hex' token adds a short hex preview of each packet."
        );
    }

    private Set<Integer> parseFilter(String raw) {
        Set<Integer> result = new LinkedHashSet<>();
        for (String part : raw.split(",")) {
            String value = part.trim();
            if (value.isEmpty()) {
                continue;
            }
            try {
                if (value.startsWith("0x") || value.startsWith("0X")) {
                    result.add(Integer.parseInt(value.substring(2), 16));
                } else if (value.matches("\\d+")) {
                    result.add(Integer.parseInt(value));
                } else {
                    result.add(Integer.parseInt(value, 16));
                }
            } catch (NumberFormatException e) {
                return null;
            }
        }
        return result.isEmpty() ? null : result;
    }

    private List<PlayerSession> resolveSessions(String target) {
        if (target == null || target.equalsIgnoreCase("all")) {
            return allSessions();
        }
        PlayerSession session = findSession(target);
        return session == null ? Collections.emptyList() : Collections.singletonList(session);
    }

    public List<String> watchCommand(String[] args) {
        if (args.length == 0) {
            return watchStatus();
        }
        if (args[0].equalsIgnoreCase("off") || args[0].equalsIgnoreCase("stop")) {
            stopWatch();
            return Collections.singletonList("Watch disabled.");
        }

        int seconds;
        try {
            seconds = Integer.parseInt(args[0]);
        } catch (NumberFormatException e) {
            return Collections.singletonList("Invalid interval: " + args[0]);
        }
        seconds = Math.max(1, Math.min(3600, seconds));

        String mode = args.length > 1 ? args[1].toLowerCase(Locale.ROOT) : "all";
        if (!mode.equals("ping") && !mode.equals("traffic") && !mode.equals("all")) {
            return Collections.singletonList("Invalid watch mode: " + mode
                    + " (use ping, traffic or all)");
        }

        stopWatch();
        watchSeconds = seconds;
        watchMode = mode;
        watchTask = Bukkit.getScheduler().runTaskTimer(plugin, this::runWatch,
                seconds * 20L, seconds * 20L);
        return Collections.singletonList("Watch enabled: every " + seconds
                + "s, mode=" + mode + ". Reports go to the server console.");
    }

    private List<String> watchStatus() {
        if (watchTask == null || watchTask.isCancelled()) {
            return Collections.singletonList("Watch is disabled. Usage: debug watch <seconds> [ping|traffic|all]");
        }
        return Collections.singletonList("Watch is active: every " + watchSeconds
                + "s, mode=" + watchMode + ".");
    }

    private void runWatch() {
        try {
            List<String> lines = new ArrayList<>();
            lines.add("=== watch @ " + TIME_FORMAT.format(LocalDateTime.now()) + " ===");
            if (watchMode.equals("ping") || watchMode.equals("all")) {
                lines.addAll(pingReport(null));
            }
            if (watchMode.equals("traffic") || watchMode.equals("all")) {
                lines.addAll(trafficReport(null, false));
            }
            logLines(lines);
        } catch (Throwable t) {
            plugin.getLogger().warning("Watch report failed: " + t);
        }
    }

    private void stopWatch() {
        if (watchTask != null) {
            watchTask.cancel();
            watchTask = null;
        }
        watchSeconds = 0;
    }

    public List<String> tpsReport() {
        double[] tps = Bukkit.getTPS();
        long[] tickTimes = Bukkit.getTickTimes();
        long[] sortedTicks = tickTimes.clone();
        Arrays.sort(sortedTicks);

        Runtime runtime = Runtime.getRuntime();
        long used = runtime.totalMemory() - runtime.freeMemory();
        long max = runtime.maxMemory();
        ThreadMXBean threads = ManagementFactory.getThreadMXBean();
        RuntimeMXBean jvm = ManagementFactory.getRuntimeMXBean();
        long nettyThreads = Thread.getAllStackTraces().keySet().stream()
                .filter(thread -> thread.getName().contains("Netty"))
                .count();
        int chunks = 0;
        for (var world : Bukkit.getWorlds()) {
            chunks += world.getLoadedChunks().length;
        }

        List<String> lines = new ArrayList<>();
        lines.add("=== Server performance ===");
        lines.add("Server: " + ChatColor.stripColor(Bukkit.getVersion()));
        lines.add("Minecraft: " + Bukkit.getMinecraftVersion()
                + "   API: " + Bukkit.getBukkitVersion());
        lines.add(String.format(Locale.ROOT,
                "TPS: %.2f / %.2f / %.2f (1m/5m/15m)   MSPT avg=%.2fms",
                tps.length > 0 ? tps[0] : 0,
                tps.length > 1 ? tps[1] : 0,
                tps.length > 2 ? tps[2] : 0,
                Bukkit.getAverageTickTime()));
        lines.add(String.format(Locale.ROOT,
                "Tick times: p50=%.2fms p95=%.2fms p99=%.2fms max=%.2fms (samples=%d)",
                percentile(sortedTicks, 0.50),
                percentile(sortedTicks, 0.95),
                percentile(sortedTicks, 0.99),
                percentile(sortedTicks, 1.00),
                sortedTicks.length));
        lines.add(String.format(Locale.ROOT,
                "Memory: used=%s / max=%s (%.1f%%)   free=%s",
                bytes(used), bytes(max), max == 0 ? 0 : used * 100.0 / max,
                bytes(runtime.freeMemory())));
        lines.add(String.format(Locale.ROOT,
                "Threads: live=%d peak=%d netty=%d",
                threads.getThreadCount(), threads.getPeakThreadCount(), nettyThreads));
        lines.add("JVM: " + jvm.getVmName() + " " + jvm.getVmVersion()
                + "   Uptime: " + PlayerSession.duration(jvm.getUptime()));
        lines.add(String.format(Locale.ROOT,
                "Worlds: %d   loaded chunks: %s   online: %d/%d   tick: %d",
                Bukkit.getWorlds().size(), count(chunks),
                Bukkit.getOnlinePlayers().size(), Bukkit.getMaxPlayers(),
                Bukkit.getCurrentTick()));
        return lines;
    }

    public List<String> logReport(int requested) {
        int count = Math.max(1, Math.min(MAX_CONNECTION_LOG, requested));
        List<ConnectionRecord> snapshot;
        int total;
        synchronized (connectionLogLock) {
            snapshot = new ArrayList<>(connectionLog);
            total = snapshot.size();
        }
        if (snapshot.isEmpty()) {
            return Collections.singletonList("Connection log is empty.");
        }
        int from = Math.max(0, snapshot.size() - count);
        List<String> lines = new ArrayList<>();
        lines.add("=== Connection log (last " + (snapshot.size() - from)
                + " of " + total + ") ===");
        for (int i = from; i < snapshot.size(); i++) {
            lines.add(snapshot.get(i).format());
        }
        return lines;
    }

    public List<String> dumpReport(String target) {
        if (target != null && !target.equalsIgnoreCase("all")) {
            PlayerSession session = findSession(target);
            if (session == null) {
                return Collections.singletonList("Player not online: " + target);
            }
            List<String> lines = new ArrayList<>(pingDetail(session));
            lines.add("");
            lines.addAll(netBlock(session));
            lines.add("");
            lines.addAll(trafficBlock(session));
            lines.add("");
            lines.addAll(timingBlock(session));
            return lines;
        }

        List<String> lines = new ArrayList<>(pingReport(null));
        lines.add("");
        lines.addAll(tpsReport());
        lines.add("");
        lines.addAll(trafficReport(null, false));
        lines.add("");
        lines.addAll(timingReport(null));
        lines.add("");
        lines.addAll(netReport(null));
        lines.add("");
        lines.addAll(logReport(15));
        return lines;
    }

    public List<String> writeReport() {
        List<String> lines = new ArrayList<>();
        lines.add("SuperDebug report");
        lines.add("Generated: " + Instant.now());
        lines.addAll(tpsReport());
        lines.add("");
        lines.addAll(pingReport(null));
        lines.add("");
        lines.addAll(trafficReport(null, false));
        lines.add("");
        lines.addAll(timingReport(null));
        lines.add("");
        lines.addAll(netReport(null));
        lines.add("");
        lines.addAll(logReport(30));

        try {
            Path directory = plugin.getDataFolder().toPath().resolve("reports");
            Files.createDirectories(directory);
            Path file = directory.resolve("debug-"
                    + REPORT_TIME.format(LocalDateTime.now()) + ".txt");
            Files.write(file, lines, StandardCharsets.UTF_8);
            return Collections.singletonList("Report written: " + file
                    + " (" + lines.size() + " lines)");
        } catch (IOException e) {
            return Collections.singletonList("Could not write report: " + e);
        }
    }

    public List<String> reload() {
        stopWatch();
        plugin.reloadConfig();
        loadSettings();
        startSampler();
        return Arrays.asList(
                "Configuration reloaded.",
                "  sample-interval-seconds=" + sampleIntervalSeconds,
                "  ping-history-size=" + pingHistorySize,
                "  sniff-default-max-packets=" + sniffDefaultMax,
                "  sniff-max-frame-bytes=" + sniffMaxFrameBytes,
                "  sniff-log-to-file=" + sniffToFile,
                "  post-risk-gap-ms=" + (postRiskGapNanos / 1_000_000L));
    }

    public void emit(CommandSender sender, List<String> lines) {
        for (String line : lines) {
            if (sender instanceof org.bukkit.command.ConsoleCommandSender) {
                plugin.getLogger().info(line);
            } else {
                plugin.getLogger().info(line);
                sender.sendMessage("[SuperDebug] " + line);
            }
        }
    }

    private void logLines(List<String> lines) {
        for (String line : lines) {
            plugin.getLogger().info(line);
        }
    }

    // ---------------------------------------------------------------------
    // Event tracking
    // ---------------------------------------------------------------------

    @EventHandler(priority = EventPriority.MONITOR)
    public void onPreLogin(AsyncPlayerPreLoginEvent event) {
        String name = event.getName();
        String rawAddress = PlayerSession.address(event.getRawSocketAddress());
        String host = PlayerSession.safe(event.getHostname(), "none");
        String result = event.getLoginResult() == null ? "?" : event.getLoginResult().name();
        String detail = "uuid=" + event.getUniqueId() + " result=" + result
                + (event.getKickMessage() == null || event.getKickMessage().isEmpty()
                ? "" : " kick=" + event.getKickMessage());

        if (event.getLoginResult() == AsyncPlayerPreLoginEvent.Result.ALLOWED) {
            pendingLogins.put(event.getUniqueId(),
                    new PendingLogin(System.currentTimeMillis(), name, rawAddress, host));
        } else {
            pendingLogins.remove(event.getUniqueId());
        }
        record("PRELOGIN", name, rawAddress, host, detail);
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onLogin(PlayerLoginEvent event) {
        String name = event.getPlayer().getName();
        String address = PlayerSession.address(event.getRealSocketAddress());
        String host = PlayerSession.safe(event.getHostname(), "none");
        String result = event.getResult() == null ? "?" : event.getResult().name();
        String detail = "result=" + result
                + " real=" + PlayerSession.address(event.getRealAddress())
                + (event.getKickMessage() == null || event.getKickMessage().isEmpty()
                ? "" : " kick=" + event.getKickMessage());
        record("LOGIN", name, address, host, detail);
        if (event.getResult() != PlayerLoginEvent.Result.ALLOWED) {
            pendingLogins.remove(event.getPlayer().getUniqueId());
        }
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onJoin(PlayerJoinEvent event) {
        Player player = event.getPlayer();
        PlayerSession session = ensureSession(player);
        session.attach(player);
        record("JOIN", player.getName(), session.joinAddress(), session.joinVirtualHost(),
                "proto=" + session.joinProtocol()
                        + " login=" + PlayerSession.duration(session.loginDelayMs())
                        + " brand=" + session.joinBrand());
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onQuit(PlayerQuitEvent event) {
        Player player = event.getPlayer();
        PlayerSession session = sessions.remove(player.getUniqueId());
        String reason = event.getReason() == null ? "?" : event.getReason().name();
        if (session == null) {
            record("QUIT", player.getName(), PlayerSession.address(player.getAddress()),
                    PlayerSession.address(player.getVirtualHost()), "reason=" + reason);
            return;
        }
        record("QUIT", player.getName(), PlayerSession.address(player.getAddress()),
                PlayerSession.address(player.getVirtualHost()),
                "session=" + PlayerSession.duration(session.sessionAgeMs())
                        + " reason=" + reason);
        session.close("quit");
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onKick(PlayerKickEvent event) {
        Player player = event.getPlayer();
        record("KICK", player.getName(), PlayerSession.address(player.getAddress()),
                PlayerSession.address(player.getVirtualHost()),
                "cause=" + (event.getCause() == null ? "?" : event.getCause().name())
                        + " reason=" + PlayerSession.safe(event.getReason(), ""));
    }

    @EventHandler(priority = EventPriority.MONITOR)
    public void onClose(PlayerConnectionCloseEvent event) {
        pendingLogins.remove(event.getPlayerUniqueId());
        String name = PlayerSession.safe(event.getPlayerName(), "?");
        String address = PlayerSession.address(event.getSocketAddress());
        boolean online = Bukkit.getPlayer(event.getPlayerUniqueId()) != null;
        record("CLOSE", name, address, "none",
                "online=" + online + " uuid=" + event.getPlayerUniqueId());
    }

    private void record(String type, String name, String address, String host, String detail) {
        ConnectionRecord entry = new ConnectionRecord(System.currentTimeMillis(), type,
                PlayerSession.safe(name, "?"), PlayerSession.safe(address, "none"),
                PlayerSession.safe(host, "none"), detail);
        synchronized (connectionLogLock) {
            connectionLog.addLast(entry);
            while (connectionLog.size() > MAX_CONNECTION_LOG) {
                connectionLog.removeFirst();
            }
        }
    }

    // ---------------------------------------------------------------------
    // Formatting
    // ---------------------------------------------------------------------

    private String tpsShort() {
        double[] tps = Bukkit.getTPS();
        return String.format(Locale.ROOT, "TPS %.2f/%.2f/%.2f  MSPT %.2fms",
                tps.length > 0 ? tps[0] : 0,
                tps.length > 1 ? tps[1] : 0,
                tps.length > 2 ? tps[2] : 0,
                Bukkit.getAverageTickTime());
    }

    private String trafficOneLine(PlayerSession session) {
        PlayerSession.TrafficStats stats = session.stats();
        long elapsed = Math.max(1, System.nanoTime() - stats.startedAtNanos);
        return String.format(Locale.ROOT,
                "Traffic: wire IN %s (%s msgs) OUT %s (%s msgs)   frames IN %s (%s pkts) OUT %s (%s pkts)   rates IN %s OUT %s",
                bytes(stats.wireInBytes.sum()), count(stats.wireInMessages.sum()),
                bytes(stats.wireOutBytes.sum()), count(stats.wireOutMessages.sum()),
                bytes(stats.frameInBytes.sum()), count(stats.frameInPackets.sum()),
                bytes(stats.frameOutBytes.sum()), count(stats.frameOutPackets.sum()),
                rate(stats.wireInBytes.sum(), elapsed),
                rate(stats.wireOutBytes.sum(), elapsed));
    }

    private static double avgMs(long sumNanos, long count) {
        return count == 0 ? 0.0 : sumNanos / (double) count / 1_000_000.0;
    }

    private static double ms(long nanos) {
        return nanos / 1_000_000.0;
    }

    private static double percentile(long[] sorted, double percentile) {
        if (sorted.length == 0) {
            return 0;
        }
        int index = (int) Math.min(sorted.length - 1,
                Math.round(percentile * (sorted.length - 1)));
        return sorted[index] / 1_000_000.0;
    }

    private static String bytes(long value) {
        if (value < 1024) {
            return value + " B";
        }
        double size = value;
        String[] units = {"KiB", "MiB", "GiB", "TiB", "PiB"};
        int unit = -1;
        do {
            size /= 1024.0;
            unit++;
        } while (size >= 1024.0 && unit < units.length - 1);
        return String.format(Locale.ROOT, "%.1f %s", size, units[unit]);
    }

    private static String rate(long bytes, long elapsedNanos) {
        double perSecond = bytes * 1_000_000_000.0 / Math.max(1, elapsedNanos);
        return bytes((long) perSecond) + "/s";
    }

    private static String overhead(long wire, long frame) {
        if (frame <= 0) {
            return "n/a";
        }
        return String.format(Locale.ROOT, "%.1f%%", wire * 100.0 / frame);
    }

    private static String count(long value) {
        return String.format(Locale.ROOT, "%,d", value);
    }

    private static String truncate(String value, int max) {
        if (value == null) {
            return "-";
        }
        if (value.length() <= max) {
            return value;
        }
        return value.substring(0, Math.max(0, max - 1)) + "~";
    }

    private static String safe(String value, String fallback) {
        return value == null || value.isEmpty() ? fallback : value;
    }

    // ---------------------------------------------------------------------
    // Small data holders
    // ---------------------------------------------------------------------

    static final class PendingLogin {
        final long time;
        final String name;
        final String address;
        final String host;

        PendingLogin(long time, String name, String address, String host) {
            this.time = time;
            this.name = name;
            this.address = address;
            this.host = host;
        }
    }

    static final class ConnectionRecord {
        final long time;
        final String type;
        final String name;
        final String address;
        final String host;
        final String detail;

        ConnectionRecord(long time, String type, String name, String address,
                         String host, String detail) {
            this.time = time;
            this.type = type;
            this.name = name;
            this.address = address;
            this.host = host;
            this.detail = detail;
        }

        String format() {
            String clock = TIME_FORMAT.format(
                    Instant.ofEpochMilli(time).atZone(ZoneId.systemDefault()));
            return String.format(Locale.ROOT,
                    "[%s] %-8s %-16s %-21s host=%-24s %s",
                    clock, type, truncate(name, 16), truncate(address, 21),
                    truncate(host, 24), detail);
        }
    }

    private static final class Row {
        final PlayerSession session;
        final PlayerSession.PingSnapshot ping;

        Row(PlayerSession session, PlayerSession.PingSnapshot ping) {
            this.session = session;
            this.ping = ping;
        }
    }
}
