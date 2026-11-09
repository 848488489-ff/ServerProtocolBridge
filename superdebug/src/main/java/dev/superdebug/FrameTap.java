package dev.superdebug;

import io.netty.buffer.ByteBuf;
import io.netty.channel.ChannelDuplexHandler;
import io.netty.channel.ChannelHandlerContext;
import io.netty.channel.ChannelPromise;

import java.util.Arrays;
import java.util.zip.DataFormatException;
import java.util.zip.Inflater;

/**
 * Parses Minecraft's framed byte stream at the splitter/prepender boundary.
 *
 * Inbound placement (before "splitter") sees decrypted frames.
 * Outbound placement (before "prepender") sees frames after compression and
 * before encryption. That gives us real packet ids without touching the
 * server's packet classes.
 */
final class FrameTap extends ChannelDuplexHandler {

    enum Direction {
        IN,
        OUT
    }

    private static final int MAX_FRAME_LENGTH = 8 * 1024 * 1024;

    /**
     * How many bytes of the frame body are kept always (independent of sniffing)
     * so the packet id can be decoded for every frame.  For compressed frames
     * this covers the data-length VarInt plus enough deflate stream to recover
     * the leading packet-id VarInt for all but the most pathological packets.
     */
    private static final int ID_PREFIX_MAX = 192;

    private final PlayerSession session;
    private final Direction direction;

    private final int[] varint = new int[5];
    private int varintLength;
    private long remaining = -1;
    private int frameLength;
    private boolean frameCompressed;
    private byte[] capture;
    private int capturePosition;
    private boolean truncated;

    /** Always-captured frame-body prefix used for packet-id decoding. */
    private byte[] idPrefix = new byte[ID_PREFIX_MAX];
    private int idPrefixPosition;

    /** Nanotime of the previous complete frame in this direction (0 = none). */
    private long lastFrameNanos;

    FrameTap(PlayerSession session, Direction direction) {
        this.session = session;
        this.direction = direction;
    }

    @Override
    public void channelRead(ChannelHandlerContext ctx, Object msg) throws Exception {
        if (direction == Direction.IN && msg instanceof ByteBuf buffer) {
            feed(buffer, ctx);
        }
        ctx.fireChannelRead(msg);
    }

    @Override
    public void write(ChannelHandlerContext ctx, Object msg, ChannelPromise promise) throws Exception {
        if (direction == Direction.OUT && msg instanceof ByteBuf buffer) {
            feed(buffer, ctx);
        }
        ctx.write(msg, promise);
    }

    private void feed(ByteBuf buffer, ChannelHandlerContext ctx) {
        int index = buffer.readerIndex();
        int end = buffer.writerIndex();

        while (index < end) {
            if (remaining < 0) {
                if (varintLength == 0) {
                    frameCompressed = compressionEnabled(ctx);
                    boolean sniffing = session.sniffActive();
                    if (sniffing) {
                        capture = new byte[0];
                    } else {
                        capture = null;
                    }
                    capturePosition = 0;
                    truncated = false;
                }

                int b = buffer.getUnsignedByte(index++);
                varint[varintLength++] = b;

                if ((b & 0x80) == 0) {
                    int length = decodeVarInt(varintLength);
                    int prefixBytes = varintLength;
                    varintLength = 0;

                    if (length < 0 || length > MAX_FRAME_LENGTH) {
                        session.stats().frameErrors.increment();
                        continue;
                    }

                    frameLength = length;
                    remaining = length;
                    idPrefixPosition = 0;
                    if (direction == Direction.IN) {
                        session.stats().frameInBytes.add(length + prefixBytes);
                        session.stats().frameInPackets.increment();
                    } else {
                        session.stats().frameOutBytes.add(length + prefixBytes);
                        session.stats().frameOutPackets.increment();
                    }

                    if (capture != null) {
                        int cap = Math.min(length, session.maxSniffCaptureBytes());
                        if (cap > 0) {
                            capture = new byte[cap];
                            truncated = length > cap;
                        } else {
                            capture = null;
                        }
                    }

                    if (remaining == 0) {
                        finishFrame();
                    }
                } else if (varintLength >= 5) {
                    session.stats().frameErrors.increment();
                    varintLength = 0;
                }
            } else {
                int available = (int) Math.min(remaining, end - index);
                if (capture != null && capturePosition < capture.length) {
                    int copy = Math.min(available, capture.length - capturePosition);
                    buffer.getBytes(index, capture, capturePosition, copy);
                    capturePosition += copy;
                }
                if (idPrefixPosition < idPrefix.length) {
                    int copy = Math.min(available, idPrefix.length - idPrefixPosition);
                    buffer.getBytes(index, idPrefix, idPrefixPosition, copy);
                    idPrefixPosition += copy;
                }
                index += available;
                remaining -= available;
                if (remaining == 0) {
                    finishFrame();
                }
            }
        }
    }

    private void finishFrame() {
        // 时序始终采集（不依赖是否在嗅探）：同方向相邻两帧的间隔，用于排查
        // 网页客户端卡顿后动作包与移动包挤在一起触发 GrimAC Post 检查的问题。
        long now = System.nanoTime();
        long gapNanos = lastFrameNanos == 0 ? -1 : now - lastFrameNanos;
        lastFrameNanos = now;

        // 帧前缀里解码包 ID（尽力而为，不依赖嗅探是否开启）。
        int packetId = decodePacketId(idPrefix, idPrefixPosition, frameCompressed);

        session.onFrameTap(direction, frameLength, gapNanos, packetId,
                capture, capturePosition, frameCompressed, truncated);

        capture = null;
        capturePosition = 0;
        truncated = false;
        remaining = -1;
    }

    /**
     * Best-effort decode of the leading packet-id VarInt from the captured frame
     * prefix.  Handles compression (data-length VarInt followed by a deflate
     * stream).  Returns -1 when the prefix is too short or cannot be decoded.
     */
    private int decodePacketId(byte[] prefix, int length, boolean compressed) {
        if (length <= 0) {
            return -1;
        }
        try {
            int offset = 0;
            if (compressed) {
                VarInts.Result dataLength = VarInts.read(prefix, 0, length);
                if (!dataLength.ok) {
                    return -1;
                }
                if (dataLength.value < 0) {
                    return -1;
                }
                offset = dataLength.bytes;
                if (dataLength.value > 0) {
                    byte[] out = inflatePrefix(prefix, offset, length - offset, 32);
                    if (out == null || out.length == 0) {
                        return -1;
                    }
                    VarInts.Result id = VarInts.read(out, 0, out.length);
                    return id.ok ? id.value : -1;
                }
            }
            VarInts.Result id = VarInts.read(prefix, offset, length - offset);
            return id.ok ? id.value : -1;
        } catch (Throwable t) {
            return -1;
        }
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

    private boolean compressionEnabled(ChannelHandlerContext ctx) {
        return ctx.pipeline().get("compress") != null
                || ctx.pipeline().get("decompress") != null;
    }

    private int decodeVarInt(int length) {
        int value = 0;
        int shift = 0;
        for (int i = 0; i < length; i++) {
            int b = varint[i];
            value |= (b & 0x7F) << shift;
            if ((b & 0x80) == 0) {
                return value;
            }
            shift += 7;
        }
        return -1;
    }
}
