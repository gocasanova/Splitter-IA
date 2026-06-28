# Optional AI-powered lyrics/chords analysis.
import os

from src.utils.logger import setup_logger
from src.utils.config import BASE_DIR

logger = setup_logger(__name__)


class LyricsAnalyzer:
    """Analyze lyrics and chords with the OpenAI Responses API when configured."""

    def __init__(self, model: str | None = None):
        try:
            from dotenv import load_dotenv
            load_dotenv(BASE_DIR / ".env")
        except ImportError:
            pass

        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-5.2")

    def analyze(self, title: str, lyrics: str, chords: str = "") -> str:
        """Return a musician-focused interpretation of the song material."""
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is not configured.")

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("The openai package is not installed. Run: pip install openai") from exc

        client = OpenAI()
        prompt = (
            f"Song title: {title or 'Unknown'}\n\n"
            f"Lyrics:\n{lyrics.strip() or '(No lyrics provided)'}\n\n"
            f"Chords / performance notes:\n{chords.strip() or '(No chords provided)'}"
        )

        logger.info("Requesting lyrics analysis with model: %s", self.model)
        response = client.responses.create(
            model=self.model,
            instructions=(
                "You are a helpful music coach for band practice. Analyze only the text "
                "the user provided. Do not reproduce long copyrighted lyric passages. "
                "Write in Spanish. Include: resumen, emocion, secciones importantes, "
                "ideas para cantar/tocar, and chord/performance observations if chords are present."
            ),
            input=prompt,
        )
        return response.output_text.strip()
