# PR #38 CI remediation evidence
+
+Base candidate: `c0d96009f11785bac92f6e9e78d7fed8014a8455`.
+Version remains `0.1.0-rc.2` / `0.1.0rc2`; no release/tag is created.
+Owner authorized exactly one CI-remediation commit and push to existing PR #38.
+The commit containing this record is the local verified candidate; its exact
+SHA and subsequent remote CI results are recorded in external delivery evidence.
+
+## Root causes and correction
+
+1. The Windows/Python 3.12-generated dev lock pinned more-itertools 11.2.1,
+   which requires Python >=3.11. Pin 11.1.0, supporting >=3.10, across the
+   declared Python 3.10-3.13 range. Pin OS/Python-conditional dependency closure
+   as well; no matrix version or check is removed.
+2. Standalone CI installs the project's dev lock, not ComfyUI. The loopback
+   adapter and tests import aiohttp, but earlier local tests inherited it from
+   ComfyUI via PYTHONPATH. Declare aiohttp explicitly in the dev extra and lock
+   it and its transitive dependencies. ComfyUI remains the runtime owner of
+   aiohttp; Core runtime dependency declarations are unchanged. Testing docs now
+   require a clean lock-installed environment rather than borrowed host packages.
+3. Linux's typed keyring SecretService class exposes an untyped constructor.
+   Bind LinuxVault to Callable[[], CredentialBackend], then call that factory.
+   This creates the same class once with the same zero arguments. No new ignore,
+   relaxed mypy configuration, backend discovery, storage access or behavior.
+
+Before committing, advisory audits rejected the initially inherited aiohttp
+3.14.3 / multidict 6.7.1 and bundled pip. The final lock uses aiohttp 3.14.4,
+multidict 6.9.1, its required yarl 1.25.1 and pip 26.2.1. These fixes preserve
+Python >=3.10. Initial logs remain in initial-validation/; no vulnerability was
+ignored or audit check disabled.
+
+Primary metadata: <https://pypi.org/project/more-itertools/11.1.0/>,
+<https://pypi.org/project/aiohttp/3.14.4/>,
+<https://github.com/jaraco/keyring/blob/v25.7.0/keyring/backends/SecretService.py>.
+
+## Verification
+
+| Gate | Result |
+|---|---|
+| Clean dedicated environments | Lock installed on CPython 3.10.11, 3.12.10, 3.13.13; no ComfyUI PYTHONPATH |
+| Focused credential/callback regression | 34 passed |
+| Full Python 3.10 suite | 511 passed, 3 optional unmaterialized media skips |
+| Full Python 3.13 suite | 511 passed, 3 optional unmaterialized media skips |
+| Full frontend | 146 passed; frontend bytes unchanged |
+| Strict mypy | Windows and Linux targets PASS, 119 files; Linux platform dependencies installed for the check |
+| Ruff / format | PASS |
+| pip check | PASS in all three environments |
+| Dependency/security audit | PASS for installed combined validation dependencies and the flattened Linux/Python 3.10 lock; no known vulnerabilities |
+| Build / package content, secret-pattern and path audit | PASS for wheel and sdist |
+| Product Contract Guard | PASS; one authorized typing-only source digest; unauthorized delta 0 |
+| Credential mechanism | Full-module AST equals c0d9600 after stripping only factory typing; synthetic test proves one constructor and zero vault reads |
+
+The Linux mypy target on Windows is local static evidence, not a Linux runtime
+claim. Real Linux/Windows CI on the final pushed SHA remains the delivery gate.
+Browser/real-vault gates are not applicable to this nonfunctional delta; no new
+OAuth consent, real credential access or live ComfyUI probe was performed.
+
+CI retains all original job names, Python versions, commands, strict typing and
+security checks. Only its baseline/delta paths change to the exact c0d9600 source
+baseline and this authorized delta. Existing accepted contracts/receipts remain
+unchanged; the local reviewed hash is synchronized only for credential_backend.
+OAuth, UI, Naming, capabilities, attribution, billing and all other product
+source are unchanged. Behavioral semantic delta: 0. Unauthorized delta: 0.
+
+## Rebuilt unpublished artifacts
+
+| Artifact | SHA256 |
+|---|---|
+| openrouter_video-0.1.0rc2-py3-none-any.whl | 073779b25d54a96422a95be6b43f0e52f3fba8cdfc503ce9b84e99eac22f4a97 |
| openrouter_video-0.1.0rc2.tar.gz | 2715251154e2b2439450a292d57dad715487136016d1d5074df7ea8850f2c470 |
+
+Evidence: workspace output/rc-preparation-20261016/pr38-ci-remediation.
+The older c0d9600 artifact hashes remain historical, not hashes of this repair.
+Any Product Owner acceptance of c0d9600 does not accept a changed head.
+
+NEXT_GATE after exact-head remote CI PASS: READY_FOR_PRODUCT_OWNER_REACCEPTANCE.
+Otherwise BLOCKED with the actual failing gate. No automatic merge, tag, release,
+publication or PROD changes. Paid POST count: 0. STOP after the requested CI run.
+