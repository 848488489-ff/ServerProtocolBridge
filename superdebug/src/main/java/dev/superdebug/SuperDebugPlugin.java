package dev.superdebug;

import org.bukkit.command.PluginCommand;
import org.bukkit.plugin.java.JavaPlugin;

public final class SuperDebugPlugin extends JavaPlugin {

    private DebugService service;

    @Override
    public void onEnable() {
        saveDefaultConfig();

        this.service = new DebugService(this);
        this.service.start();

        PluginCommand command = getCommand("debug");
        if (command == null) {
            getLogger().severe("Command 'debug' is missing from plugin.yml; commands are unavailable.");
        } else {
            DebugCommand executor = new DebugCommand(service);
            command.setExecutor(executor);
            command.setTabCompleter(executor);
        }

        getServer().getPluginManager().registerEvents(service, this);

        getLogger().info("SuperDebug " + getPluginMeta().getVersion() + " enabled.");
        getLogger().info("Console usage: debug ping | debug net | debug traffic | debug timing | debug packets | debug sniff | debug tps | debug help");
        try {
            Class.forName("io.netty.channel.Channel");
            getLogger().info("Netty channel API is available to plugins.");
        } catch (Throwable t) {
            getLogger().warning("Netty channel API is NOT visible to the plugin: " + t);
        }
    }

    @Override
    public void onDisable() {
        if (service != null) {
            service.stop();
        }
        getLogger().info("SuperDebug disabled.");
    }

    public DebugService getService() {
        return service;
    }
}
