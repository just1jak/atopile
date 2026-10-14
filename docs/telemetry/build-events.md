# Build events in 0.15.9

`cli:build_start` and `cli:build_end` count **invocations**, not individual
build targets or compiler stages. One CLI `ato build` command (including `--all`)
or one extension build request emits one pair. All requested targets share a
`build_invocation_id`; each retains its existing, distinct `ATO_BUILD_ID`.
Validation and launch failures also produce a terminal event.

The parent owns event delivery. Workers receive the invocation ID and the
initiating process's `ATO_VSCE_PID` explicitly, overriding stale forkserver state.
They expose these as `ATO_BUILD_INVOCATION_ID` and `ATO_VSCE_PID`. Workers do not
emit lifecycle pairs. `via_vsce` is snapshotted from the initiating process;
`install_method` describes installation and never determines build origin.

Both events include `build_invocation_id`, `counting_unit=invocation`, `via_vsce`,
`outcome`, `duration` (elapsed seconds at capture time), and the dispatcher's usual
`atopile_version` and identity properties. `target_count` is zero at invocation
start, before target resolution, and the resolved target count at the end.
The start outcome is `started`. The end outcome is `success`, `failed`, or
`cancelled`. A failed target takes precedence over cancellation; otherwise any
cancelled target makes the invocation cancelled. Success requires all targets
to succeed (warnings remain successful). The end event waits for all targets
and for the invoking function to return, except when that function raises.

Cancellation of running or queued work and orderly queue shutdown produce a
cancelled terminal event. CLI interrupts stop the queue before unwinding.
As with other best-effort telemetry, parent-process SIGKILL, power loss, opt-out,
or delivery failure can leave missing events. No telemetry delivery failure
may change the build result. Opt-out is handled by the existing dispatcher.

## Analytics compatibility

The event names and invocation counting unit are unchanged. Previously,
`cli:build_end` was emitted only on a successful CLI return. Consumers measuring
successful builds must now filter `outcome = 'success'`, treating absent/empty
outcomes on older events as successful. The dashboard's build-volume queries
and `builds-today` command retain that filter. Active-user queries may still
include all outcomes. Deduplicate pairs by `build_invocation_id`, not `run_id`
(which is a process identifier), when analyzing the new schema.

Extension build events were missing in 0.15.8. A zero count of extension-attributed
build events for that version does **not** establish zero extension builders.
Historical extension builder counts cannot be reconstructed from those events,
and `install_method=vsce-managed` does not prove an extension-triggered build.
