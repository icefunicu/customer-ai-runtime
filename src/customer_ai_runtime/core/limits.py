from __future__ import annotations

# Conservative defaults to prevent accidental oversized payloads.
# This value is configurable at higher layers if needed, but keeps a safe baseline.
AUDIO_BASE64_MAX_CHARS = 2_000_000
