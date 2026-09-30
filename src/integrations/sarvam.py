"""Re-export facade for the Sarvam speech adapter moved in Phase 3.

Canonical home: ``src.dss.infrastructure.speech.sarvam``. This module forwards the public names so existing imports keep working; it is deleted in Phase 6 (spec 2.1, 2.3 contract step). The result types re-export from the speech port, which is their single canonical home since Phase 2.
"""

from src.dss.application.ports.speech import (
    STTResult as STTResult,
)
from src.dss.application.ports.speech import (
    TTSResult as TTSResult,
)
from src.dss.infrastructure.speech.sarvam import (
    SarvamClient as SarvamClient,
)
from src.dss.infrastructure.speech.sarvam import (
    configure_sarvam_client as configure_sarvam_client,
)
from src.dss.infrastructure.speech.sarvam import (
    get_sarvam_client as get_sarvam_client,
)
