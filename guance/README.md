# Guance Headless Shell

This fork packages Linux x64 Chromium Headless Shell for browser monitoring.
The current baseline is Chromium **156.0.8078.47**. Build only the Shell target;
retain JavaScript JIT, WebAssembly, V8 context snapshots, normal web graphics,
the Chromium sandbox, site isolation and CDP screenshots.

The lean build removes printing/PDF, standalone Shell command handlers, desktop
device discovery and native desktop integrations. Use CDP `Page.captureScreenshot`
for screenshots. The standalone `--screenshot` command is not included.
Physical device/audio integration and PDF workflows need a regular Shell build.

`headless_shell` uses the normal runtime defaults. The optional adjacent
`headless_shell_low_memory` launcher disables spare renderers and the larger
PartitionAlloc thread cache, and uses one raster thread. It merges the caller's
last `--disable-features=value` argument. It does not disable the sandbox or site
isolation, impose a JavaScript heap cap, or block image/font/network requests.
Configure resource loading in the task controller as required by the page.

In a short local four-context fixture, the lean build plus launcher used about
248 MiB summed process PSS, compared with about 266 MiB for the release baseline.
These figures are workload-specific, exclude the controller, and are not a
production capacity guarantee. A `dev` build disables PGO/ThinLTO and its dependent
CFI hardening for iteration. Use `release` for deployment and for measuring memory
and throughput.

The browser itself does not enforce tenant or private-network policy. Keep a
separate browser/OS boundary across tenants; only share within a trusted tenant.
Private-network restrictions need a controlled proxy plus an enforced egress
boundary, or another validated network enforcement mechanism.

See [CI.md](CI.md) for build and runner options. For a prepared source tree:

```sh
bash guance/prepare.sh /absolute/build-root
bash guance/build.sh /absolute/build-root/src dev 4
bash guance/package.sh /absolute/build-root/src dev /absolute/dist
```

The fixed official archive supplies Chromium dependencies; tracked fork source
changes are overlaid before compilation, including deletions and file modes.
Changing `DEPS`, submodules or the Chromium version requires updating source
preparation. Preserve `src/out/Guance-*` on a trusted dedicated runner for
incremental compilation. A warm build is faster; a cold build still compiles
Chromium and has substantial CPU, memory and disk requirements.

Artifacts include build arguments, revision and checksum metadata, generated
third-party notices, and a local-only CDP form/storage/PNG smoke report. Smoke
tests run as a non-root user with the Chromium sandbox enabled. Linux hosts must
allow Chromium's sandbox and supply runtime libraries such as NSS, GBM, fontconfig
and fonts. Use a representative task corpus before a production rollout.
