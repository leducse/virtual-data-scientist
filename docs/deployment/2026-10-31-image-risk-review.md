# Development image findings and mitigation

The official Python 3.13 slim base is now pinned to the verified index digest
`sha256:2d44738ebf4ce5f63b9d9ea871e9c7cfdc0426f7b0c97cac915fd88ded1d86bb`.
The Docker Hub and public ECR mirrors reported the same base digest; public ECR
rate limiting during inspection prompted use of the official Docker Hub mirror.
Available apt upgrades remain enabled. This does not remove the stable-package
CVE findings recorded by ECR.

Primary Debian tracker checked October 31, 2026:

| Finding | Stable-package status and relevant boundary |
|---|---|
| [CVE-2026-84243](https://security-tracker.debian.org/tracker/CVE-2026-84243) | Stable remains affected. The advisory requires attacker-controlled LANGUAGE plus a non-C locale and a readable malicious catalog. The container now fixes LANG/LC_ALL to C.UTF-8 and LANGUAGE to C. No request accepts environment overrides. |
| [CVE-2026-19499](https://security-tracker.debian.org/tracker/CVE-2026-19499) | Stable remains affected; newer unstable package has a fix. Trigger involves strfmon/strfmon_l formatting. Application code does not call those APIs; transitive library reachability is not proven absent. |
| [CVE-2026-5435](https://security-tracker.debian.org/tracker/CVE-2026-5435) | Stable remains affected; newer unstable package has a fix. Trigger involves deprecated DNS-record print routines. No application call identified; transitive reachability is not cleared. |
| [CVE-2026-85091](https://security-tracker.debian.org/tracker/CVE-2026-85091) | Stable tracker marks affected and links an upstream affected-range discussion. Trigger involves gzprintf/gzvprintf after nonblocking-write stalls. The application uses compression libraries, so no blanket zlib exemption is claimed. |

The runtime remains nonroot. Generated Python executes in separate Code
Interpreter sessions, with no runtime credentials, network tools or environment
mutation capabilities in the approved wrapper. Authentication limits hosted
analysis to administrator-created development users; open signup is disabled.

These are mitigations and an initial reachability review, not proof of complete
non-exploitability or a waiver. Do not suppress scanner findings or call the
image patched/production-ready. Resolve with distribution fixes or a separately
reviewed base/backport change before a public production launch.
