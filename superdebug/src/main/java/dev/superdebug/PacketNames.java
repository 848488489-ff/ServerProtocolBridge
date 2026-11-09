package dev.superdebug;

import java.lang.reflect.Method;

/**
 * Runtime packet-name and category resolution.
 *
 * <p>Names and categories are read from the live server, never from a
 * hard-coded id table.  Every decoded {@code net.minecraft.network.protocol.Packet}
 * carries a {@code type() -> PacketType -> id() -> Identifier}, whose path is the
 * official registry name (for example {@code move_player_pos_rot}).  That name,
 * plus the packet's Java class, is all we need for readable output and for
 * grouping packets into movement / action / misc categories.  The plugin never
 * contains Mojang's decompiled sources and never hard-codes packet ids.
 *
 * <p>All access is reflective and optional: if a future server version renames
 * the {@code type}/{@code id}/{@code getPath} chain the plugin still works, it
 * just reports {@code unknown}.
 */
final class PacketNames {

    /** Coarse packet category used for grouping and Post detection. */
    enum Category {
        MOVE("move"),
        ACTION("action"),
        MISC("misc");

        final String label;

        Category(String label) {
            this.label = label;
        }
    }

    private static final String PACKET_INTERFACE = "net.minecraft.network.protocol.Packet";
    private static final String TYPE_METHOD = "type";
    private static final String ID_METHOD = "id";
    private static final String GET_PATH_METHOD = "getPath";

    private static volatile Class<?> packetClass;

    private PacketNames() {
    }

    /**
     * True if {@code msg} is a {@code net.minecraft.network.protocol.Packet}.
     * The class is resolved once; the check is an {@code isAssignableFrom} test.
     */
    static boolean isPacket(Object msg) {
        Class<?> iface = packetInterface();
        return iface != null && msg != null && iface.isAssignableFrom(msg.getClass());
    }

    /**
     * Official snake_case packet name from {@code packet.type().id().getPath()},
     * for example {@code move_player_pos_rot}, or {@code null} if it cannot be
     * resolved on this server version.
     */
    static String officialName(Object packet) {
        try {
            Object type = invokeNoArgs(packet, TYPE_METHOD);
            if (type == null) {
                return null;
            }
            Object id = invokeNoArgs(type, ID_METHOD);
            if (id == null) {
                return null;
            }
            String path = invokeString(id, GET_PATH_METHOD);
            if (path != null && !path.isEmpty()) {
                return path;
            }
            String fallback = id.toString();
            int colon = fallback.indexOf(':');
            if (colon >= 0 && colon + 1 < fallback.length()) {
                return fallback.substring(colon + 1);
            }
            return null;
        } catch (Throwable t) {
            return null;
        }
    }

    /** Coarse category of an official packet name. */
    static Category category(String officialName) {
        if (officialName == null) {
            return Category.MISC;
        }
        if (isMovement(officialName)) {
            return Category.MOVE;
        }
        if (isAction(officialName)) {
            return Category.ACTION;
        }
        return Category.MISC;
    }

    /** Movement packets: the ones a Post-flush would follow. */
    static boolean isMovement(String official) {
        return official.contains("move_player") || official.contains("move_vehicle")
                || official.contains("player_input");
    }

    /**
     * Action packets: player interactions that, when immediately followed by a
     * movement packet, are the signature of a client flushing a burst (GrimAC
     * Post).  This drives the precise Post detection.  Classification is by the
     * official registry name, so it stays correct across versions and needs no
     * hard-coded numeric ids.
     */
    static boolean isAction(String official) {
        if (isMovement(official)) {
            return false;
        }
        return official.contains("use_item") || official.contains("player_action")
                || official.contains("attack") || official.contains("interact")
                || official.contains("punch") || official.contains("player_command")
                || official.contains("container_click") || official.contains("container_button_click")
                || official.contains("action") || official.contains("use_")
                || official.contains("pick_item") || official.contains("paddle_boat")
                || official.contains("select_trade") || official.contains("place_recipe")
                || official.contains("rename_item") || official.contains("edit_book")
                || official.contains("sign_update") || official.contains("set_carried_item")
                || official.contains("set_command") || official.contains("set_structure")
                || official.contains("set_jigsaw") || official.contains("set_beacon")
                || official.contains("set_game_rule") || official.contains("set_test")
                || official.contains("change_game_mode") || official.contains("change_difficulty")
                || official.contains("seen_advancements") || official.contains("recipe_book")
                || official.contains("spectator") || official.contains("teleport_to_entity")
                || official.contains("player_abilities") || official.contains("client_command")
                || official.contains("lock_difficulty") || official.contains("jigsaw_generate")
                || official.contains("debug_subscription");
    }

    /**
     * Friendly display name from an official snake_case name, for example
     * {@code move_player_pos_rot} becomes {@code Move Player Pos Rot}.
     */
    static String displayName(String official) {
        if (official == null || official.isEmpty()) {
            return "unknown";
        }
        String[] parts = official.split("_");
        StringBuilder out = new StringBuilder();
        for (String part : parts) {
            if (part.isEmpty()) {
                continue;
            }
            if (out.length() > 0) {
                out.append(' ');
            }
            out.append(Character.toUpperCase(part.charAt(0)));
            if (part.length() > 1) {
                out.append(part.substring(1));
            }
        }
        return out.toString();
    }

    private static Class<?> packetInterface() {
        if (packetClass == null) {
            try {
                packetClass = Class.forName(PACKET_INTERFACE);
            } catch (Throwable t) {
                return null;
            }
        }
        return packetClass;
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
            } catch (Throwable t) {
                return null;
            }
        }
        return null;
    }

    private static String invokeString(Object target, String name) {
        Object value = invokeNoArgs(target, name);
        return value == null ? null : value.toString();
    }
}
