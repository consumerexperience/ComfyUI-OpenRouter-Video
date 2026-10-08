# Golden Multimodal Asset Pack v1

Local, zero-cost MMR2V reference pack. The target generated output remains **5 seconds**. This pack contains two original Higgsfield IMAGE references, one official Higgsfield commercial sample as a playblast/blocking reference, and one real car/urban-ambience production recording. No generation request was submitted.

## Contents and order

`manifest.json` is the machine-readable inventory, provenance record, metadata record, semantic-role mapping, and checksum authority. The canonical MMR2V occurrences are explicitly ordered:

1. IMAGE — `car_sheet.png`
2. IMAGE — `loc_street_main.png`
3. VIDEO — `Car_Chasing.mp4`
4. AUDIO — `Passing_car_urban_ambience.wav`

The first five seconds of the 5.366667-second MP4 are a tightly usable timing cue. The original MP4 is retained unchanged; no derived clip was made. The 14-second audio is also unchanged, with its opening five seconds available as a cue. Local semantic role names live only in the manifest; they are not sent upstream. Transport role and wire type are recorded separately.

The car-chase sample controls blocking, camera movement, action timing, and urban motion, not the IMAGE hero-car identity. The audio is a Mixkit production SFX titled “Passing car and urban ambience”, downloaded as WAV under the Mixkit License. The official Higgsfield tutorial itself describes sound effects but does not publish an audio binary.

## Local assets

Binary files are materialized under `assets/` and gitignored, following the existing image-pack policy because source redistribution rights are not asserted. The source materialization paths and upstream links are retained in `manifest.json`. Tests require every asset to exist locally and verify exact SHA-256 and byte count; absent binaries fail the tests.

## Verification

Run from the repository root:

```powershell
python -m pytest tests/contract/test_higgsfield_multimodal_pack.py
```

These checks are offline and record `paid_generation.post_count = 0`. They do not authorize a paid smoke or establish that a selected OpenRouter model accepts IMAGE + VIDEO + AUDIO. No local semantic role is serialized to the provider.
