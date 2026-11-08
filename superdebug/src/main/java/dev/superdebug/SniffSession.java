package dev.superdebug;

import java.io.BufferedWriter;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Arrays;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.zip.DataFormatException;
import java.util.zip.Inflater;

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

    synchronized void onFrame(Direction direction, byte[] body, int bodyLength,
                              int frameLength, boolean compressed, boolean truncated,
                              long gapNanos) {
        if (!isActive()) {
            return;
        }
        seen.incrementAndGet();

        Decoded decoded = decode(body, bodyLength, compressed);
        if (decoded == null) {
            errors.incrementAndGet();
            return;
        }

        if (!filter.isEmpty() && !filter.contains(decoded.packetId)) {
            filtered.incrementAndGet();
            return;
        }

        int number = emitted.incrementAndGet();
        if (number > maxPackets) {
            emitted.decrementAndGet();
            finish("packet limit reached");
            return;
        }

        String line = formatLine(direction, number, decoded, frameLength,
                compressed, truncated, gapNanos);
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

    private String formatLine(Direction direction, int number, Decoded decoded,
                              int frameLength, boolean compressed, boolean truncated,
                              long gapNanos) {
        String preview = hex
                ? " hex=" + VarInts.hex(decoded.preview, 0, decoded.preview.length, 40)
                : "";
        return String.format(Locale.ROOT,
                "[sniff] %-16s %s #%d id=%s frame=%dB pkt=%dB comp=%s%s%s%s",
                playerName,
                direction.label,
                number,
                VarInts.id(decoded.packetId),
                frameLength,
                decoded.packetLength,
                compressed ? "yes" : "no",
                truncated ? " trunc" : "",
                formatGap(direction, gapNanos),
                preview);
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

    private Decoded decode(byte[] body, int bodyLength, boolean compressed) {
        if (bodyLength <= 0) {
            return null;
        }

        int offset = 0;
        int dataLength = -1;

        if (compressed) {
            VarInts.Result dataLengthResult = VarInts.read(body, 0, bodyLength);
            if (!dataLengthResult.ok) {
                return null;
            }
            dataLength = dataLengthResult.value;
            offset = dataLengthResult.bytes;
            if (dataLength < 0) {
                return null;
            }
        }

        if (compressed && dataLength > 0) {
            byte[] inflated = inflatePrefix(body, offset, bodyLength - offset,
                    Math.min(64, Math.max(1, dataLength)));
            if (inflated == null || inflated.length == 0) {
                return null;
            }
            VarInts.Result id = VarInts.read(inflated, 0, inflated.length);
            if (!id.ok) {
                return null;
            }
            return new Decoded(id.value, dataLength, inflated);
        }

        VarInts.Result id = VarInts.read(body, offset, bodyLength - offset);
        if (!id.ok) {
            return null;
        }
        int previewLength = Math.min(48, bodyLength - offset);
        byte[] preview = Arrays.copyOfRange(body, offset, offset + previewLength);
        return new Decoded(id.value, bodyLength - offset, preview);
    }

    private byte[] inflatePrefix(byte[] data, int offset, int length, int wanted) {
        if (length <= 0 || wanted <= 0) {
            return null;
        }
        Inflater inflater = new Inflater();
        try {
            inflater.setInput(data, offset, length);
            byte[] out = new byte[wanted];
            int read = inflater.inflate(out);
            if (read <= 0) {
                return null;
            }
            return read == out.length ? out : Arrays.copyOf(out, read);
        } catch (DataFormatException e) {
            return null;
        } finally {
            inflater.end();
        }
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

    private static final class Decoded {
        final int packetId;
        final int packetLength;
        final byte[] preview;

        Decoded(int packetId, int packetLength, byte[] preview) {
            this.packetId = packetId;
            this.packetLength = packetLength;
            this.preview = preview;
        }
    }
}
