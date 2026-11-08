package dev.superdebug;

import io.netty.buffer.ByteBuf;
import io.netty.channel.ChannelDuplexHandler;
import io.netty.channel.ChannelHandlerContext;
import io.netty.channel.ChannelPromise;

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
        session.onFrameTiming(direction, frameLength, gapNanos);

        if (capture != null && capturePosition > 0) {
            session.onSniffFrame(direction, capture, capturePosition, frameLength,
                    frameCompressed, truncated, gapNanos);
        }
        capture = null;
        capturePosition = 0;
        truncated = false;
        remaining = -1;
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
