package dev.superdebug;

import java.io.BufferedWriter;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * One packet-trace session for one player. Both frame taps call into this
 * object; all output is synchronized so interleaved C2S/S2C packets stay
 * readable.
 */
final class SniffSession {

    enum Direction {
        IN("IN "),
        OUT("OUT");

        final String label;

        Direction(String label) {
            this.label = label;
        }
    }

    private static final DateTimeFormatter FILE_TIME =
            DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss", Locale.ROOT);

    private final SuperDebugPlugin plugin;
    private final String playerName;
    private final int maxPackets;
    private final boolean hex;
    private final Set<Integer> filter;
    private final int maxCaptureBytes;

    private final AtomicInteger seen = new AtomicInteger();
    private final AtomicInteger emitted = new AtomicInteger();
    private final AtomicInteger filtered = new AtomicInteger();
    private final AtomicInteger errors = new AtomicInteger();
    private final AtomicBoolean finished = new AtomicBoolean(false);

    private volatile boolean active = true;
    private PrintWriter file;
    private Path filePath;

    SniffSession(SuperDebugPlugin plugin, String playerName, int maxPackets,
                 boolean hex, Set<Integer> filter, int maxCaptureBytes, boolean writeFile) {
        this.plugin = plugin;
        this.playerName = playerName;
        this.maxPackets = maxPackets;
        this.hex = hex;
        this.filter = filter;
        this.maxCaptureBytes = maxCaptureBytes;

        if (writeFile) {
            openFile();
        }
    }

    boolean isActive() {
        return active && !finished.get();
    }

    Path filePath() {
        return filePath;
    }

    int maxPackets() {
        return maxPackets;
    }

    int emittedCount() {
        return emitted.get();
    }

    synchronized void onDecodedPacket(Direction direction, String officialName,
                                      int packetId, int frameLength, long gapNanos,
                                      byte[] body, int bodyLength,
                                      boolean compressed, boolean truncated) {
        if (!isActive()) {
            return;
        }
        seen.incrementAndGet();

        if (!filter.isEmpty() && !filter.contains(packetId)) {
            filtered.incrementAndGet();
            return;
        }

        int number = emitted.incrementAndGet();
        if (number > maxPackets) {
            emitted.decrementAndGet();
            finish("packet limit reached");
            return;
        }

        String line = formatLine(direction, number, officialName, packetId,
                frameLength, gapNanos, body, bodyLength, compressed, truncated);
        plugin.getLogger().info(line);
        if (file != null) {
            file.println(line);
        }

        if (number >= maxPackets) {
            finish("packet limit reached");
        }
    }

    void stop(String reason) {
        finish(reason);
    }

    private synchronized void finish(String reason) {
        if (!finished.compareAndSet(false, true)) {
            return;
        }
        active = false;

        if (file != null) {
            try {
                file.flush();
                file.close();
            } catch (Throwable ignored) {
                // The summary is still useful even if the file close fails.
            }
            file = null;
        }

        plugin.getLogger().info("[sniff] " + playerName + " stopped (" + reason
                + "): captured=" + emitted.get()
                + " seen=" + seen.get()
                + " filtered=" + filtered.get()
                + " errors=" + errors.get()
                + (filePath == null ? "" : " file=" + filePath));
    }

    private String formatLine(Direction direction, int number, String officialName,
                              int packetId, int frameLength, long gapNanos,
                              byte[] body, int bodyLength,
                              boolean compressed, boolean truncated) {
        String name = officialName == null ? "unknown" : officialName;
        String idPart = packetId < 0 ? "" : " id=" + VarInts.id(packetId);
        String preview = hex ? hexPreview(body, bodyLength, compressed) : "";
        return String.format(Locale.ROOT,
                "[sniff] %-16s %s #%d name=%-30s%s frame=%dB%s%s%s%s",
                playerName,
                direction.label,
                number,
                name,
                idPart,
                frameLength,
                compressed ? " comp=yes" : "",
                truncated ? " trunc" : "",
                formatGap(direction, gapNanos),
                preview);
    }

    /** Hex preview of the packet body, skipping the compression header. */
    private String hexPreview(byte[] body, int bodyLength, boolean compressed) {
        if (body == null || bodyLength <= 0) {
            return "";
        }
        int offset = 0;
        if (compressed) {
            VarInts.Result dataLength = VarInts.read(body, 0, bodyLength);
            if (dataLength.ok && dataLength.value > 0) {
                offset = dataLength.bytes;
            }
        }
        if (offset >= bodyLength) {
            return " hex=" + VarInts.hex(body, 0, bodyLength, 40);
        }
        return " hex=" + VarInts.hex(body, offset, bodyLength - offset, 40);
    }

    /**
     * Formats the gap since the previous frame in this direction.  For inbound
     * (client-to-server) frames a gap below the configured threshold is marked
     * {@code POST}: GrimAC's PostCheck treats a packet arriving less than 10ms
     * after the previous movement packet as a Post violation, so a pair of
     * client packets with such a tight gap is exactly the signature to look for.
     */
    private String formatGap(Direction direction, long gapNanos) {
        if (gapNanos < 0) {
            return " gap=first";
        }
        double millis = gapNanos / 1_000_000.0;
        boolean post = direction == Direction.IN
                && gapNanos < plugin.getService().postRiskGapNanos();
        return String.format(Locale.ROOT, " gap=%.2fms%s", millis, post ? " POST" : "");
    }

    private void openFile() {
        try {
            Path directory = plugin.getDataFolder().toPath().resolve("sniff");
            Files.createDirectories(directory);
            String safeName = playerName.replaceAll("[^A-Za-z0-9_.-]", "_");
            filePath = directory.resolve("sniff-" + safeName + "-"
                    + FILE_TIME.format(LocalDateTime.now()) + ".log");
            BufferedWriter writer = Files.newBufferedWriter(filePath, StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING);
            file = new PrintWriter(writer, true);
            file.println("# SuperDebug packet trace");
            file.println("# player=" + playerName
                    + " max=" + maxPackets
                    + " hex=" + hex
                    + " filter=" + (filter.isEmpty() ? "all" : filter));
        } catch (Throwable t) {
            plugin.getLogger().warning("Could not open sniff file for " + playerName + ": " + t);
            file = null;
            filePath = null;
        }
    }
}
