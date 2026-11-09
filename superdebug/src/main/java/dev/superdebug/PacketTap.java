package dev.superdebug;

import io.netty.channel.ChannelDuplexHandler;
import io.netty.channel.ChannelHandlerContext;
import io.netty.channel.ChannelPromise;

/**
 * Intercepts decoded {@code net.minecraft.network.protocol.Packet} objects so
 * packet names and categories can be read from the live server (no hard-coded
 * id table).  It is placed just before the packet listener on the inbound path
 * (after the packet decoder) and just before the packet encoder on the outbound
 * path, so it always sees fully decoded packets.
 *
 * <p>The inbound tap runs after the {@link FrameTap} and the frame splitter,
 * so when it sees a packet the matching frame's byte-level info is already
 * available for pairing (sniff display).  The outbound tap runs before the
 * encoder, so its packet name is ready by the time the outbound frame is
 * observed by the frame tap.
 */
final class PacketTap extends ChannelDuplexHandler {

    enum Direction {
        IN,
        OUT
    }

    private final PlayerSession session;
    private final Direction direction;

    PacketTap(PlayerSession session, Direction direction) {
        this.session = session;
        this.direction = direction;
    }

    @Override
    public void channelRead(ChannelHandlerContext ctx, Object msg) throws Exception {
        if (direction == Direction.IN && PacketNames.isPacket(msg)) {
            session.onDecodedPacket(direction, msg);
        }
        ctx.fireChannelRead(msg);
    }

    @Override
    public void write(ChannelHandlerContext ctx, Object msg, ChannelPromise promise) throws Exception {
        if (direction == Direction.OUT && PacketNames.isPacket(msg)) {
            session.onDecodedPacket(direction, msg);
        }
        ctx.write(msg, promise);
    }
}
