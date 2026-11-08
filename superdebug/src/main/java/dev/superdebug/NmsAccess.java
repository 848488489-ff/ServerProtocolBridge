package dev.superdebug;

import io.netty.channel.Channel;
import org.bukkit.entity.Player;

import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.net.InetSocketAddress;

/**
 * Small reflection bridge to the server's Netty channel. Paper does not expose
 * the player channel through the Bukkit API, so this walks the vanilla object
 * chain: CraftPlayer -> ServerPlayer.connection -> ServerGamePacketListenerImpl.connection
 * -> net.minecraft.network.Connection.channel.
 *
 * Everything is optional: if a future server version renames a field the plugin
 * still works, it only loses the channel-specific sections.
 */
final class NmsAccess {

    private NmsAccess() {
    }

    static final class Info {
        final Channel channel;
        final Integer latency;
        final Integer protocolVersion;
        final InetSocketAddress virtualHost;
        final Boolean encrypted;
        final String error;

        Info(Channel channel, Integer latency, Integer protocolVersion,
             InetSocketAddress virtualHost, Boolean encrypted, String error) {
            this.channel = channel;
            this.latency = latency;
            this.protocolVersion = protocolVersion;
            this.virtualHost = virtualHost;
            this.encrypted = encrypted;
            this.error = error;
        }
    }

    static Info read(Player player) {
        Channel channel = null;
        Integer latency = null;
        Integer protocolVersion = null;
        InetSocketAddress virtualHost = null;
        Boolean encrypted = null;
        String error = null;

        try {
            Object handle = invokeNoArgs(player, "getHandle");
            if (handle == null) {
                throw new IllegalStateException("CraftPlayer#getHandle() not found");
            }

            Object packetListener = field(handle, "connection");
            if (packetListener == null) {
                throw new IllegalStateException("ServerPlayer.connection not found");
            }

            Object connection = field(packetListener, "connection");
            if (connection == null) {
                throw new IllegalStateException("packet listener .connection not found");
            }

            Object channelObject = field(connection, "channel");
            if (channelObject instanceof Channel found) {
                channel = found;
            } else {
                channel = searchChannel(handle, 4, 0);
            }

            latency = intMethod(packetListener, "latency");
            protocolVersion = intField(connection, "protocolVersion");

            Object host = field(connection, "virtualHost");
            if (host instanceof InetSocketAddress address) {
                virtualHost = address;
            }

            encrypted = booleanField(connection, "encrypted");

            if (channel == null) {
                error = "channel field unavailable";
            }
        } catch (Throwable t) {
            error = t.getClass().getSimpleName()
                    + (t.getMessage() == null ? "" : ": " + t.getMessage());
        }

        return new Info(channel, latency, protocolVersion, virtualHost, encrypted, error);
    }

    static Integer compressionThreshold(Channel channel) {
        if (channel == null) {
            return null;
        }
        Object handler = channel.pipeline().get("compress");
        if (handler == null) {
            handler = channel.pipeline().get("decompress");
        }
        if (handler == null) {
            return null;
        }

        try {
            Method method = handler.getClass().getMethod("getThreshold");
            Object value = method.invoke(handler);
            if (value instanceof Number number) {
                return number.intValue();
            }
        } catch (Throwable ignored) {
            // CompressionDecoder has no public getter; fall through to the field.
        }

        Object value = field(handler, "threshold");
        if (value instanceof Number number) {
            return number.intValue();
        }
        return null;
    }

    static boolean hasEncryption(Channel channel) {
        return channel != null
                && (channel.pipeline().get("encrypt") != null
                || channel.pipeline().get("decrypt") != null);
    }

    static boolean hasCompression(Channel channel) {
        return channel != null
                && (channel.pipeline().get("compress") != null
                || channel.pipeline().get("decompress") != null);
    }

    private static Channel searchChannel(Object root, int depth, int level) {
        if (root == null || level > depth) {
            return null;
        }
        if (root instanceof Channel channel) {
            return channel;
        }

        Class<?> type = root.getClass();
        while (type != null && type != Object.class) {
            for (Field candidate : type.getDeclaredFields()) {
                if (java.lang.reflect.Modifier.isStatic(candidate.getModifiers())) {
                    continue;
                }
                Class<?> fieldType = candidate.getType();
                if (!Channel.class.isAssignableFrom(fieldType)
                        && !fieldType.getName().startsWith("net.minecraft.")) {
                    continue;
                }
                try {
                    candidate.setAccessible(true);
                    Object value = candidate.get(root);
                    if (value instanceof Channel channel) {
                        return channel;
                    }
                    if (level < depth && value != null && value != root) {
                        Channel nested = searchChannel(value, depth, level + 1);
                        if (nested != null) {
                            return nested;
                        }
                    }
                } catch (Throwable ignored) {
                    // Try the next field.
                }
            }
            type = type.getSuperclass();
        }
        return null;
    }

    private static Object invokeNoArgs(Object target, String name) {
        if (target == null) {
            return null;
        }
        Class<?> type = target.getClass();
        while (type != null) {
            try {
                Method method = type.getDeclaredMethod(name);
                method.setAccessible(true);
                return method.invoke(target);
            } catch (NoSuchMethodException e) {
                type = type.getSuperclass();
            } catch (Throwable ignored) {
                return null;
            }
        }
        return null;
    }

    private static Integer intMethod(Object target, String name) {
        Object value = invokeNoArgs(target, name);
        return value instanceof Number number ? number.intValue() : null;
    }

    private static Object field(Object target, String name) {
        if (target == null) {
            return null;
        }
        Class<?> type = target.getClass();
        while (type != null) {
            try {
                Field found = type.getDeclaredField(name);
                found.setAccessible(true);
                return found.get(target);
            } catch (NoSuchFieldException e) {
                type = type.getSuperclass();
            } catch (Throwable ignored) {
                return null;
            }
        }
        return null;
    }

    private static Integer intField(Object target, String name) {
        Object value = field(target, name);
        return value instanceof Number number ? number.intValue() : null;
    }

    private static Boolean booleanField(Object target, String name) {
        Object value = field(target, name);
        return value instanceof Boolean bool ? bool : null;
    }
}
