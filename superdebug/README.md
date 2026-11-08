# SuperDebug

Paper plugin for debugging Minecraft connections that pass through a TCP-to-WSS
proxy. Everything is console-first and on demand. Nothing is printed
automatically.

## Build

```powershell
powershell -ExecutionPolicy Bypass -File superdebug\build.ps1
```

The script compiles against the Paper API and Netty jars in
`D:\桌面\测试服务器\libraries`, then copies `SuperDebug-1.1.0.jar` to
`D:\桌面\测试服务器\plugins`.

## Commands

Run these in the server console (they also work in game with `superdebug.use`,
default op):

```
debug ping [player]                  latency table, min/avg/max/jitter, route, remote
debug net [player|all]               channel, pipeline, socket options, compression/encryption
debug traffic [player|all]           wire bytes / frame bytes / packet counts and rates
debug traffic reset [player|all]     reset counters
debug timing [player|all]            frame gap timing + GrimAC Post risk pairs
debug sniff <player|all> on [max] [hex] [filter]
debug sniff <player|all> off
debug sniff status
debug watch [seconds] [ping|traffic|all]
debug watch off
debug tps                            TPS, tick times, memory, threads, chunks
debug log [count]                    recent prelogin/login/join/quit/kick/close events
debug dump [player|all]              combined report
debug report                         write a full report to plugins/SuperDebug/reports
debug reload                         reload config.yml
```

Examples:

```
debug ping
debug ping nopp
debug net nopp
debug timing nopp
debug sniff nopp on 100 hex
debug sniff nopp on 200 0x1A,0x08
debug watch 5 all
```

`debug sniff` decodes Minecraft frame lengths and packet ids at the
splitter/prepender boundary, so it works with compression and encryption
enabled. Packet ids are numeric; use them with the protocol version shown by
`debug net`.

## Config

`plugins/SuperDebug/config.yml`:

- `sample-interval-seconds` – ping history sample period
- `ping-history-size` – number of samples kept per player
- `sniff-default-max-packets` – default packet limit for sniff
- `sniff-max-frame-bytes` – capture limit per frame
- `sniff-log-to-file` – also write traces under `plugins/SuperDebug/sniff/`
- `post-risk-gap-ms` – gap below this many ms (same-direction client packets) is
  flagged as a GrimAC Post risk pair; sniff lines show `POST` and `debug timing`
  counts them

## Frame timing

Every frame in both directions gets a timestamp and the gap since the previous
frame in the same direction. `debug timing [player|all]` prints per-direction
gap count, average, maximum and how many pairs fell below `post-risk-gap-ms`.
`debug sniff` lines include `gap=XX.XXms` and, for client-to-server frames under
the threshold, a `POST` marker — the signature of a web client that stalled and
then flushed a burst, which is what GrimAC's PostCheck flags.
