package dev.superdebug;

import java.util.Locale;

final class VarInts {

    private VarInts() {
    }

    static final class Result {
        final int value;
        final int bytes;
        final boolean ok;

        Result(int value, int bytes, boolean ok) {
            this.value = value;
            this.bytes = bytes;
            this.ok = ok;
        }
    }

    static Result read(byte[] data, int offset, int length) {
        int value = 0;
        int shift = 0;
        for (int i = 0; i < 5; i++) {
            if (i >= length) {
                return new Result(0, i, false);
            }
            int b = data[offset + i] & 0xFF;
            value |= (b & 0x7F) << shift;
            if ((b & 0x80) == 0) {
                return new Result(value, i + 1, true);
            }
            shift += 7;
        }
        return new Result(0, 5, false);
    }

    static Result read(byte[] data) {
        return read(data, 0, data.length);
    }

    static String hex(byte[] data, int offset, int length, int maxBytes) {
        int count = Math.min(length, maxBytes);
        StringBuilder out = new StringBuilder(count * 3);
        for (int i = 0; i < count; i++) {
            if (i > 0) {
                out.append(' ');
            }
            out.append(String.format(Locale.ROOT, "%02X", data[offset + i] & 0xFF));
        }
        if (length > count) {
            out.append(" ..");
        }
        return out.toString();
    }

    static String id(int id) {
        if (id < 0) {
            return "?";
        }
        if (id <= 0xFF) {
            return String.format(Locale.ROOT, "0x%02X(%d)", id, id);
        }
        return String.format(Locale.ROOT, "0x%X(%d)", id, id);
    }
}
