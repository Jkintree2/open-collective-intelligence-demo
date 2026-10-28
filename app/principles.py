"""John's statement of purpose and the two documents it names, read once at start.

The block opens every instruction that carries the principles (reading statements today);
each task keeps its own rules beside its call. John can edit the three files on GitHub."""

from __future__ import annotations

from pathlib import Path

GUIDING = Path(__file__).resolve().parent / "guiding"
BRIDGE = "Now, here are more detailed instructions for you to use to fulfill the purpose of this platform."


def _read(name: str) -> str:
    # An editor may add a trailing newline or Windows line ends; neither reaches the prompt.
    return (GUIDING / name).read_text(encoding="utf-8").replace("\r\n", "\n").strip()


PURPOSE = _read("purpose.txt")
UDHR = _read("udhr.txt")
EARTH_CHARTER = _read("earth_charter.txt")


# The three documents as the About page shows them (its anchor, its title) and Ask cites them (D1 to D3).
DOCUMENTS = (("purpose", "Statement of purpose", PURPOSE),
             ("udhr", "Universal Declaration of Human Rights", UDHR),
             ("earth-charter", "The Earth Charter", EARTH_CHARTER))


def guiding_block() -> str:
    """The purpose, the Universal Declaration of Human Rights and the Earth Charter in full,
    then the line that hands over to the task's own instructions."""
    return "\n\n".join((PURPOSE, UDHR, EARTH_CHARTER, BRIDGE))
