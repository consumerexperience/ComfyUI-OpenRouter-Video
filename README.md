# OpenRouter Video for ComfyUI

A BYOK, model-agnostic gateway from ComfyUI to OpenRouter's asynchronous Video API.
Use your own OpenRouter account, API key and balance. Results are native ComfyUI
VIDEO, with JOB_ID, MODEL, ACTUAL_COST_USD when available, and STATUS outputs.

## Release candidate

This is v0.1 RC preparation, not a stable release or Registry publication.
The single version authority is project.version in pyproject.toml. Python tooling
normalizes 0.1.0-rc.1 to PEP 440 version 0.1.0rc1.

## Installation

Stop ComfyUI. From its directory, clone the custom node:

```sh
git clone https://github.com/consumerexperience/ComfyUI-OpenRouter-Video.git custom_nodes/ComfyUI-OpenRouter-Video
python -m pip install ./custom_nodes/ComfyUI-OpenRouter-Video
```

Use the interpreter that runs ComfyUI in place of python, including the bundled
interpreter for a portable installation. Check out your intended reviewed revision
before installing. The default remote branch does not contain an unpublished local RC.
An unpacked source distribution can occupy the same custom-node directory; run the
same pip installation command there. The wheel alone installs the Python Core and
adapter, not the custom-node entrypoint and web directory needed by ComfyUI.

Python 3.10+ and ComfyUI's numbered V3 API comfy_api.v0_0_2 with native media and
dynamic inputs are required. Historical verification anchors are ComfyUI v0.34.3
and v0.37.0. RC installation is checked on the v0.34.3 anchor; other host versions
require compatible APIs and are not automatically certified.

## First run

Configure OPENROUTER_API_KEY in the launch environment, then restart ComfyUI.
The key belongs outside nodes and workflows. Never commit a secret .env or put
credentials into workflow JSON, source files, logs or bug reports.

Add OpenRouter Video. Choose Model and Inference Method, enter Prompt,
connect the required media, and select the offered parameters. Loading a workflow
or selecting a model does not generate a video. Discovery needs the configured
key; missing credentials produce a configuration error without a paid submit.

Native IMAGE uses the direct image bridge. Native VIDEO/AUDIO also need your own
private S3-compatible staging storage. Public HTTPS media reference helper nodes
remain available. See [native media setup and cleanup](docs/native-media-bridge.md).
The project supplies no storage service and does not collect credentials.

## Adaptive controls and media

Only capabilities confirmed for the selected OpenRouter model and method appear.
UNKNOWN and conflicting states fail closed. Provider-native support does not
establish support through OpenRouter. Available methods vary by model:

- T2V: text to video.
- I2V and FLF2V: first frame or first and last frame.
- IR2V and MI2V: one or multiple image references.
- VR2V: video references.
- MMR2V: mixed image/video/audio references.
- Seedance 2.5 V2V_EDIT and V2V_EXTEND: Source Video plus Prompt describing the
  change or continuation, through the existing reference-based request shape.

Load Image, Load Video and Load Audio connect where topology permits. Reference
kinds, combinations and counts are bounded. Generate Audio is independent from
AUDIO references. Edit/Extend omit First/Last Frame inputs. Seedance 2.5 exposes
480p/720p in the reviewed integration; Draft is not exposed. Standalone AR2V is
hidden where unconfirmed or conflicting. Known Exact Size conflicts are constrained.

Classic and Nodes 2.0 share the same adaptive semantics. Compatible values and
links survive save/reload. Incompatible intent is retained for repair. Model
switching can choose a supported fallback; reselect your intended method when
returning to a compatible model.

## Resume, recovery and billing

Each intentional Generate operation attempts at most one paid Video submit.
Ambiguous submission, poll interruption and download failure never trigger an
automatic resubmit. Keep the returned job ID. OpenRouter Video Resume observes
and downloads that known job; it submits no new generation and uploads no media.

SQLite recovery state lives in the ComfyUI user directory. Preserve it during
updates. Staging cleanup follows remote job state and exact object ownership;
the native-media guide covers pending cleanup and storage configuration changes.

The header estimate is not a spending cap or charge guarantee. It is unavailable
when pricing or input-media charges cannot be bounded. Actual cost comes from
OpenRouter when available. No project telemetry or analytics service is included;
static application attribution has no user, device or installation identifier.

## Update

Stop ComfyUI. Inspect local changes and move the custom-node checkout to the
intended reviewed revision. On a clean tracked branch use git pull --ff-only,
then run python -m pip install . from the custom-node directory with the ComfyUI
interpreter and restart. Preserve user data and local credential configuration;
do not force-reset local work or delete job databases.

## Limitations and development

Capabilities and availability vary by OpenRouter integration. Accepted live
evidence is not universal model-quality certification. See [RC notes](CHANGELOG.md),
[security guidance](SECURITY.md) and [contributing checks](CONTRIBUTING.md).
Original project code is MIT licensed; ComfyUI's host implementation is not bundled.
See [LICENSE](LICENSE).
