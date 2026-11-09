package dev.superdebug;

import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.command.TabCompleter;
import org.bukkit.entity.Player;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;

public final class DebugCommand implements CommandExecutor, TabCompleter {

    private static final List<String> SUBCOMMANDS = Arrays.asList(
            "help", "ping", "net", "traffic", "timing", "packets", "sniff", "watch",
            "tps", "log", "dump", "report", "reload");

    private final DebugService service;

    public DebugCommand(DebugService service) {
        this.service = service;
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command,
                             String label, String[] args) {
        if (!sender.hasPermission("superdebug.use")) {
            sender.sendMessage("You do not have permission to use SuperDebug.");
            return true;
        }

        if (args.length == 0 || args[0].equalsIgnoreCase("help")) {
            service.emit(sender, service.help());
            return true;
        }

        String sub = args[0].toLowerCase(Locale.ROOT);
        try {
            switch (sub) {
                case "ping" -> {
                    String target = args.length > 1 ? args[1] : null;
                    service.emit(sender, service.pingReport(target));
                }
                case "net", "channel", "conn" -> {
                    String target = args.length > 1 ? args[1] : null;
                    service.emit(sender, service.netReport(target));
                }
                case "traffic" -> {
                    if (args.length > 1 && args[1].equalsIgnoreCase("reset")) {
                        String target = args.length > 2 ? args[2] : null;
                        service.emit(sender, service.trafficReport(target, true));
                    } else {
                        String target = args.length > 1 ? args[1] : null;
                        service.emit(sender, service.trafficReport(target, false));
                    }
                }
                case "timing" -> {
                    String target = args.length > 1 ? args[1] : null;
                    service.emit(sender, service.timingReport(target));
                }
                case "packets", "pkt", "packet" -> {
                    String target = args.length > 1 ? args[1] : null;
                    service.emit(sender, service.packetsReport(target));
                }
                case "sniff" -> service.emit(sender,
                        service.sniffCommand(Arrays.copyOfRange(args, 1, args.length)));
                case "watch" -> service.emit(sender,
                        service.watchCommand(Arrays.copyOfRange(args, 1, args.length)));
                case "tps", "perf" -> service.emit(sender, service.tpsReport());
                case "log", "connections" -> {
                    int count = 20;
                    if (args.length > 1) {
                        try {
                            count = Integer.parseInt(args[1]);
                        } catch (NumberFormatException e) {
                            service.emit(sender, List.of("Invalid count: " + args[1]));
                            return true;
                        }
                    }
                    service.emit(sender, service.logReport(count));
                }
                case "dump" -> {
                    String target = args.length > 1 ? args[1] : null;
                    service.emit(sender, service.dumpReport(target));
                }
                case "report" -> service.emit(sender, service.writeReport());
                case "reload" -> service.emit(sender, service.reload());
                default -> {
                    service.emit(sender, List.of("Unknown subcommand: " + args[0]));
                    service.emit(sender, service.help());
                }
            }
        } catch (Throwable t) {
            service.plugin().getLogger().warning("Command failed: " + t);
            service.emit(sender, List.of("Command failed: " + t.getClass().getSimpleName()
                    + (t.getMessage() == null ? "" : ": " + t.getMessage())));
        }
        return true;
    }

    @Override
    public List<String> onTabComplete(CommandSender sender, Command command,
                                      String alias, String[] args) {
        if (args.length == 1) {
            return filter(SUBCOMMANDS, args[0]);
        }

        String sub = args[0].toLowerCase(Locale.ROOT);
        if (args.length == 2) {
            if (sub.equals("ping") || sub.equals("net") || sub.equals("channel")
                    || sub.equals("traffic") || sub.equals("timing")
                    || sub.equals("packets") || sub.equals("packet")
                    || sub.equals("pkt") || sub.equals("dump")) {
                List<String> values = new ArrayList<>(onlineNames());
                values.add("all");
                if (sub.equals("traffic")) {
                    values.add("reset");
                }
                return filter(values, args[1]);
            }
            if (sub.equals("sniff")) {
                List<String> values = new ArrayList<>(onlineNames());
                values.addAll(List.of("all", "status"));
                return filter(values, args[1]);
            }
            if (sub.equals("watch")) {
                return filter(List.of("off", "1", "5", "10", "30"), args[1]);
            }
            if (sub.equals("log")) {
                return filter(List.of("10", "20", "50", "100"), args[1]);
            }
        }

        if (sub.equals("sniff") && args.length >= 2) {
            if (args.length == 2) {
                return filter(List.of("on", "off", "status"), args[1]);
            }
            if (args.length == 3) {
                return filter(List.of("on", "off", "start", "stop", "status"), args[2]);
            }
            if (args.length == 4) {
                return filter(List.of("10", "25", "50", "100", "hex"), args[3]);
            }
            if (args.length == 5) {
                return filter(List.of("hex"), args[4]);
            }
        }

        if (sub.equals("watch") && args.length == 3) {
            return filter(List.of("ping", "traffic", "all"), args[2]);
        }

        return List.of();
    }

    private static List<String> onlineNames() {
        return org.bukkit.Bukkit.getOnlinePlayers().stream()
                .map(Player::getName)
                .sorted(String.CASE_INSENSITIVE_ORDER)
                .collect(Collectors.toList());
    }

    private static List<String> filter(List<String> values, String prefix) {
        String lower = prefix == null ? "" : prefix.toLowerCase(Locale.ROOT);
        return values.stream()
                .filter(value -> value.toLowerCase(Locale.ROOT).startsWith(lower))
                .sorted(String.CASE_INSENSITIVE_ORDER)
                .collect(Collectors.toList());
    }
}
