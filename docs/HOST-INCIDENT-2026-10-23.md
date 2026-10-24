# Reference workstation incident — 23 October 2026

Status: Resolved at the 24 October 2026 checkpoint. After the operator's Windows
update/reboot, Linux GPU access and actual GPU-backed generation pass. See the
[recovery evidence](QUALIFICATION-2026-10-24.md#gpu-recovery-and-real-conversation).
The observations below remain the historical incident record; the exact original
Windows/WSL fault is not attributed to a particular component without evidence.

## Observed boundary

The read-only check at 13:01 UTC found that Linux `nvidia-smi` exited with
code 255 and reported that NVML GPU access was blocked by the operating system.
The Windows-side command exited successfully, detected the device and returned
GPU telemetry. This establishes Windows visibility, not successful execution
of a Windows inference workload or a complete hardware-health diagnosis.

A read-only follow-up at 14:01 UTC returned the same Linux exit code and
GPU-access-blocked message. The console and Grafana login page both returned
HTTP200 and the console service remained active. Those HTTP responses do not
establish working model generation. No inference request or service mutation
was made in that follow-up.

A bounded kernel-log query also found 178 occurrences of
`dxgvmb_send_create_process failed -75` between 11:34:53 and 13:04:16 UTC.
This is the retrieved window, not an established incident start time. It
corroborates a failure at the WSL GPU interface without identifying its cause.

Ollama remained an active service. A direct embedding request completed, while
direct chat generation exceeded the diagnostic deadline. The isolated gateway
exercise also timed out on its generation path. The direct request bypasses the
gateway, so the observed availability failure is not limited to the newly
backported OpenTelemetry parser. Its underlying cause remains unresolved.

The parser correction itself passes its bounded regression and provenance
checks. A separate gateway diagnostic passes authentication, aliases,
embeddings, persistence/rollback and real trace delivery. It explicitly reports
`generation_requested=false`, `profile_passed=true` and `passed=false`.
Those results cannot be presented as a healthy end-to-end conversation or as
the complete gateway qualification. See the
[dated qualification](QUALIFICATION-2026-10-23.md).

## Controlled application recovery

At 16:33–16:35 UTC, with the application's inference/queue counters idle,
the operator-owned model was unloaded and the Ollama service was restarted
once. The console was briefly stopped and restarted around each operation;
model files, configuration and user data were retained. The previous parent
and runner exited. WSL NVML still failed with exit 255, and CUDA initialization
returned 100. The restart restored application state but did not repair GPU
access. No Windows/WSL shutdown, driver replacement or device reset was made.

Ollama selected CPU inference automatically. A first 45-second generation probe
expired during loading and was cancelled. A separate bounded cold-start probe
then completed in 115.700 seconds, including 109.049 seconds of loading, returning
the requested synthetic response. It used the existing model and configuration,
not a replacement model or cloud fallback.

A real saved AURA conversation subsequently completed in both languages. The
English turn delivered its first token at 47.751 seconds and completed at 69.407;
the French follow-up recalled the synthetic environment from the prior turn,
with first token at 47.292 seconds and completion at 70.104. A replay retained the
same history. Closing a third stream after its first token released the
inference lease and did not persist a partial turn. Only the newly created
synthetic conversation was deleted; its subsequent lookup returned 404.
These measurements establish degraded functionality, **not responsive voice
interaction or recovered GPU performance**.

The full gateway exercise also exposed a verifier race: auth/pre-call spans
were visible before their SERVER parent. The same trace contained the correct
parent 200 ms later. The corrected verifier waits for that parent within its
existing 60-poll budget, distinguishes spans from OTLP links, and still rejects
incorrect identifiers/state. All seven full gateway checks then passed on the
exact corrected image in 120.878 seconds, including real structured generation,
streaming, OTLP delivery, migration, restart, independent logical rollback and
resource cleanup. The earlier failed reports remain retained. See the
[qualification report](QUALIFICATION-2026-10-23.md) for scope and provenance.

## Preserved evidence and operating state

The checks record exit codes, bounded diagnostics and hashes in private
evidence. Public documentation excludes host identities, device serials,
process IDs, raw event logs, paths and user content. Earlier successful tests,
the failed full gateway attempt and the narrower passing diagnostic remain
separate records; none is replaced with an inferred success.

The initial read-only GPU diagnostic did not reboot Windows/WSL, restart services,
change host policy or send another model request. The separately recorded
synthetic inference probes were performed before that read-only inspection.
User data and existing services were preserved. A live platform host must not
be rebooted or used as a disposable CI runner to bypass this incident.

## Recovery acceptance

Host administration must first restore GPU access within WSL and verify the
Windows/WSL runtime boundary. The read-only evidence does not establish a
specific corrective driver or reboot procedure; choose that action only after
reviewing the actual host state and preserving active work.
No successful non-disruptive GPU repair was demonstrated during this session.

These read-only checks can be run from Windows PowerShell before and after the
operator's maintenance intervention:

```powershell
nvidia-smi.exe --query-gpu=name,driver_version,memory.total,memory.used --format=csv
wsl.exe --version
wsl.exe --list --verbose
```

Then use the Linux shell of the distribution that actually hosts the platform;
the default WSL distribution may be different. Check GPU access there and
inspect only the recent relevant kernel messages:

```sh
/usr/lib/wsl/lib/nvidia-smi
journalctl -k --since '5 minutes ago' --no-pager --output=cat --grep 'dxgvmb_send_create_process'
./plateforme preparation
```

Run the platform command from its checkout. Keep diagnostic output private.
Successful Windows telemetry must be accompanied by working WSL GPU access;
repeated creation failures remain a blocker. An empty log interval and a green
readiness check alone do not prove inference. NVIDIA's
[WSL guidance](https://docs.nvidia.com/cuda/wsl-user-guide/index.html) and
Microsoft's [GPU compute documentation](https://learn.microsoft.com/en-us/windows/wsl/tutorials/gpu-compute)
describe the Windows-driver/WSL boundary. Do not install a Linux NVIDIA display
driver inside WSL as a speculative repair. No reboot or driver change is
represented here as an observed fix.
Microsoft also documents [listing and selecting WSL distributions](https://learn.microsoft.com/en-us/windows/wsl/basic-commands).

After the host is repaired:

1. Recheck GPU access from WSL and verify that the intended local inference
   runtime can execute a bounded synthetic generation request.
2. Re-run the complete isolated gateway qualification after recovery on the exact corrected
   image, including structured generation and streaming. Its full `passed`
   result must be true; the embeddings-only profile is insufficient.
3. Recheck the platform's actual readiness, local routing and conversation path.
   A live process, an HTTP health response or an embedding result alone does
   not demonstrate successful chat generation.
4. Complete the preserved-data promotion and post-installation verification
   before publishing the personal prerelease. Keep the hosted draft unpublished
   if these checks remain blocked.

Successful CI qualifies its own source and disposable environment. It cannot
repair this workstation or substitute for these operating checks. The earlier
physical-audio, off-host recovery, external-alert and reboot/second-machine
acceptance boundaries also remain applicable.
