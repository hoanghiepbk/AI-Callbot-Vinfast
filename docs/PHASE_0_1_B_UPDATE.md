# Person B Update: Phase 0-1

This note summarizes what was completed for the Track B work in `PLAN.md`, with the phase, wave, and gate context your teammate asked for.

## Scope Completed

### Phase 0 - Wave 0 - Gate 0

Delivered the B-side foundations that support the frozen contract and the voice stack:

- Added the B-owned architecture write-up in `docs/ARCHITECTURE.md`.
- Implemented the frozen schema-side plate/phone validation support needed by the B normalization flow.
- Filled the audio-side scaffolding with import-safe implementations:
  - `src/callbot/asr/faster_whisper_asr.py`
  - `src/callbot/audio/recorder.py`
  - `src/callbot/audio/vad.py`
  - `src/callbot/audio/playback.py`

What this means for Gate 0:

- The shared contract is in place for the B-side modules.
- The voice-side modules are no longer placeholders.
- The work is still scoped to B-owned files; the full project gate also depends on A-side dialogue work.

### Phase 1 - Wave 1 - Gate 1

Delivered the B-side Phase 1 items from `PLAN.md`:

- `B10` Vietnamese normalization with unit tests
- `B11` ASR wrapper with file-mode support
- `B12` microphone capture + VAD
- `B13` scenario corpus for `G_1` through `G_5` plus exception cases
- `B14` audio fixture support for WER evaluation readiness

Key behaviors now covered:

- Spoken Vietnamese numbers normalize into phone, plate, VIN, and odo formats.
- Short pauses in numeric fields are tolerated so `30F` and `1234` can be treated as one plate input.
- The corpus contains realistic Vietnamese user utterances for all five categories.

## Verification

Validation passed after the implementation:

- `pytest -q -p no:cacheprovider` -> `17 passed`
- JSON fixtures in `scenarios/` parse successfully
- Import check for the new audio/normalization modules succeeded

## Files Worth Reviewing

- [`src/callbot/normalization/vietnamese_numbers.py`](../src/callbot/normalization/vietnamese_numbers.py)
- [`src/callbot/asr/faster_whisper_asr.py`](../src/callbot/asr/faster_whisper_asr.py)
- [`src/callbot/audio/vad.py`](../src/callbot/audio/vad.py)
- [`src/callbot/audio/recorder.py`](../src/callbot/audio/recorder.py)
- [`src/callbot/audio/playback.py`](../src/callbot/audio/playback.py)
- [`src/callbot/models/schemas.py`](../src/callbot/models/schemas.py)
- [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md)
- [`tests/test_normalization.py`](../tests/test_normalization.py)

## Notes For Teammates

- The B-side now has concrete implementations and test coverage for Phase 1.
- Phase 2 work can build on these interfaces without changing the public API.
- The remaining project work is still the dialogue engine, pipeline wiring, TTS, and eval/reporting tasks from the later waves.
