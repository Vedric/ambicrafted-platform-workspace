# Qdrant residual Rust LOW review — 2026-10-21

## Scope and decision proposed

The candidate keeps the official Qdrant 1.19.2 server executable and its complete
published Rust SPDX inventory. This is a source/usage review, not a suppression,
not a proof of absence of undefined behavior, and not a corrected Rust binary.
The two advisories represent three package/version occurrences. Recommend a
bounded follow-up with the next qualified upstream patch, rather than owning a
new server fork solely to remove low-risk inventory matches.

Context7 was attempted for the library/API check but returned monthly quota
exceeded. Primary maintainer advisories and checksum-verified published source
were used instead.

## rand: GHSA-cq8v-f236-94qc / RUSTSEC-2026-0097

No CVE assigned. Installed transitive versions 0.8.5 and 0.9.2; compatible fixes
0.8.6 and 0.9.3. Main workspace rand is already on the patched 0.10 line.
The advisory requires the `log` feature and a custom logging path that calls
thread-local RNG during reseeding, causing reentrant mutable access. The official
Cargo.lock entries for both old rand versions have no dependency on `log`.
In checksum-verified rand source all reseeding log macros are guarded by that
feature. Qdrant src/tracing/{mod,default,on_disk}.rs uses tracing fmt layers and
LogTracer, with no RNG calls in those logger implementations. No matching
trigger was found in this source/configuration review. The inventory does not
expose complete compiler feature provenance, so this is not an absolute binary
reachability guarantee.

References: https://github.com/advisories/GHSA-cq8v-f236-94qc and
https://rustsec.org/advisories/RUSTSEC-2026-0097.html .

## xxhash-rust: GHSA-6g2r-675j-hx59

No CVE assigned. Installed 0.8.15; compatible fix 0.8.16. The issue concerns the
custom-secret xxh3 API receiving a secret shorter than its required minimum in
release builds. Qdrant does not directly import xxhash_rust. Cargo.lock has one
parent: seedable_hash 0.1.7, through the ph perfect-hash dependency. The downloaded
seedable_hash crate matches its Cargo.lock SHA-256; its xxh3 adapter calls
Xxh3::with_seed(u64), not a custom-secret API. No request-controlled custom secret
or use of the vulnerable entrypoint was found. This is a checked usage result,
not a patched-version claim.

Reference: https://github.com/advisories/GHSA-6g2r-675j-hx59 .

## Alternatives and real qualification cost

The latest official stable release and checked master revision are still
016542aa5deb6c66380bb137badf73d54f742bde (1.19.2), with these old transitive
versions; no ready-made corrected release was found. Targeted Cargo.lock updates
to 0.8.6, 0.9.3 and 0.8.16 are compatible in principle but have not been resolved
or built here. Merely changing the SPDX inventory would be false and is rejected.

A genuine corrected build needs a pinned Rust 1.98.1 compiler/builder, exact
native clang/lld/cmake/protobuf/libunwind/jemalloc dependencies, stacktrace feature
parity and an honestly regenerated cargo-sbom inventory. The upstream workspace
contains 33 Cargo manifests and 912 locked packages. Upstream validation builds
workspace tests then runs nextest; additional API, storage, distributed/consensus,
restart/recovery and snapshot compatibility checks are necessary. The upstream
consensus workflow alone allocates 60-minute job timeouts; this is a configured
budget, not a measured rebuild duration. No claim about a completed Rust rebuild
or its performance is made. ARM/GPU variants would require separate qualification.

Revisit these patches at the next upstream release or sooner if logger feature
provenance changes, new custom-secret use appears, or advisory severity/exposure
changes. Keep all three findings visible meanwhile. The reasonable OS fix was
applied now: real liblzma5 deb13u2 binaries/package records replace deb13u1, with
migration/search/snapshot/browser checks and a fresh full image scan.
