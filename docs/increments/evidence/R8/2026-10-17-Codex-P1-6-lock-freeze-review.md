# Codex P1-6 lock and pip-freeze comparison

Date: 2026-10-17 (Asia/Shanghai). The only available interpreter is the user-global Python; no project-specific backend venv was found.

## Comparison result

- Interpreter: Python 3.12.1 / `python -m pip freeze`.
- Lock entries parsed: 101; exact version matches: 30; mismatches: 55; missing: 16.
- This global interpreter is not the project container and cannot prove the locked runtime is installed. Docker CLI is unavailable on this host (`docker` is not recognized), so the image build and container `pip check` could not be run.
- Static source checks: the 7 direct pins in `requirements-ai-copilot.in`, the `ai-copilot` optional dependency group in `pyproject.toml`, and lock direct pins agree. Dockerfile declares Python 3.11-slim and uses `pip install --require-hashes` followed by `pip check`; this is configuration inspection, not execution evidence.
- The vendored `vanna-2.0.2-py3-none-any.whl` SHA-256 is `d54f039572b0bcc520859ba99b7a587bdf96eebafc0c77c28fe44c0962550553`; the digest is present in the lock file Vanna hash set.
- Lock header says `pip-compile` was run under Python 3.12 while `.in` documents Python 3.11 as the image target. Container installation and compatibility remain unverified.

## Direct pin snapshot

| Package | Lock | Current global freeze | Result |
|---|---:|---:|---|
| `vanna` | `2.0.2` | `not installed` | MISSING |
| `chromadb` | `1.5.9` | `not installed` | MISSING |
| `openai` | `2.54.0` | `2.54.0` | MATCH |
| `python-dotenv` | `1.2.4` | `1.2.2` | MISMATCH |
| `bcrypt` | `4.0.1` | `4.2.1` | MISMATCH |
| `numpy` | `2.2.6` | `2.4.6` | MISMATCH |
| `onnxruntime` | `1.23.2` | `1.28.0` | MISMATCH |

## Sanitized pip-freeze snapshot for packages in the lock

Only simple `name==version` entries are retained; editable/local-reference lines and unrelated packages are excluded to avoid leaking machine paths or private index URLs.

```text
# python=3.12.1 lock_packages=101
PyYAML==6.0.3
Pygments==2.20.0
SQLAlchemy==2.0.41
aiohappyeyeballs==2.6.1
aiohttp==3.13.5
aiosignal==1.4.0
annotated-doc==0.0.4
annotated-types==0.7.0
anyio==4.13.0
attrs==26.1.0
bcrypt==4.2.1
build==1.6.1
certifi==2026.7.22
charset-normalizer==3.4.7
click==8.4.1
colorama==0.4.6
coloredlogs==15.0.1
distro==1.9.0
filelock==3.29.0
flatbuffers==25.12.19
frozenlist==1.8.0
fsspec==2026.4.0
googleapis-common-protos==1.75.1
grpcio==1.81.0
h11==0.16.0
hf-xet==1.5.0
httpcore2==2.12.0
httpcore==1.0.9
httptools==0.7.1
httpx2==2.12.0
httpx==0.28.1
huggingface_hub==1.17.0
humanfriendly==10.0
idna==3.19
jiter==0.16.0
jsonschema-specifications==2025.9.1
jsonschema==4.26.0
markdown-it-py==4.2.0
mdurl==0.1.2
mmh3==5.2.1
mpmath==1.3.0
multidict==6.7.1
narwhals==2.25.0
numpy==2.4.6
onnxruntime==1.28.0
openai==2.54.0
opentelemetry-api==1.44.0
opentelemetry-exporter-otlp-proto-common==1.44.0
opentelemetry-proto==1.44.0
opentelemetry-sdk==1.44.0
opentelemetry-semantic-conventions==0.65b0
orjson==3.11.9
packaging==25.0
pandas==3.0.3
propcache==0.5.2
protobuf==7.35.1
pydantic-settings==2.14.1
pydantic==2.13.4
pydantic_core==2.46.4
pyproject_hooks==1.3.3
pyreadline3==3.5.6
python-dateutil==2.9.0.post0
python-dotenv==1.2.2
referencing==0.37.0
requests==2.33.1
rich==15.0.0
rpds-py==0.30.0
shellingham==1.5.4
six==1.17.0
sniffio==1.3.1
sympy==1.14.0
tabulate==0.10.0
tenacity==9.1.4
tokenizers==0.22.2
tqdm==4.67.3
truststore==0.10.4
typer==0.25.1
typing-inspection==0.4.2
typing_extensions==4.15.0
tzdata==2023.3
urllib3==2.7.0
uvicorn==0.34.0
watchfiles==1.1.1
websockets==16.0
yarl==1.23.0
# NOT INSTALLED: aiohttp-retry==2.9.1
# NOT INSTALLED: chromadb==1.5.9
# NOT INSTALLED: durationpy==0.11
# NOT INSTALLED: importlib-resources==7.1.0
# NOT INSTALLED: kubernetes==37.0.1
# NOT INSTALLED: oauthlib==4.0.0
# NOT INSTALLED: opentelemetry-exporter-otlp-common==0.66b1
# NOT INSTALLED: opentelemetry-exporter-otlp-proto-grpc==1.45.1
# NOT INSTALLED: overrides==7.7.0
# NOT INSTALLED: plotly==7.1.0
# NOT INSTALLED: pybase64==1.5.1
# NOT INSTALLED: pypika==0.51.1
# NOT INSTALLED: requests-oauthlib==2.0.0
# NOT INSTALLED: sqlparse==0.6.0
# NOT INSTALLED: vanna==2.0.2
# NOT INSTALLED: websocket-client==1.9.2
```

## Outcome

**PARTIAL:** source pin consistency and Vanna wheel hash pass. Lock-vs-available-environment check fails (30/101 exact; 55 mismatched; 16 missing), but that environment is not the project runtime. Final reproducibility proof requires running the locked installation and `pip check` inside the Python 3.11 target container; until then do not claim P1-6 lock proof complete or GREEN.
