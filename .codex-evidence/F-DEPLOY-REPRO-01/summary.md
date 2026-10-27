# F-DEPLOY-REPRO-01

- Added committed npm lockfile and Node/npm engine contract.
- Replaced runtime-only Dockerfile with Node 24.15.0 multi-stage build and nginx healthcheck.
- Added `.dockerignore` and deployment contract tests.
- TDD: RED 2/2 failed; GREEN 2/2 passed.
- 1.9 built `datara-newweb:deploy-repro-01` from source without `dist`; image sha256 `415f06a…`.
- Isolated container on 18102 healthy/HTTP 200.
- Switched 18091 to reproducible image; live health HTTP 200; Playwright PASS, three workflows visible, console errors 0.
- Previous live image retained as stopped rollback container `datara-newweb-web-rollback-deploy-repro-01`.
