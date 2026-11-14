"""Complaint categories used across the application."""

CATEGORIES = {
    "pothole": "Pothole / road damage",
    "garbage": "Garbage / litter",
    "waterlogging": "Waterlogging",
    "streetlight": "Streetlight issue",
    "other": "Other civic issue",
}

# Categories for which an *installed and evaluated* image model could provide
# suggestions. Waterlogging, streetlight and other are always manual: a daytime
# photograph cannot establish whether a streetlight works.
IMAGE_MODEL_ELIGIBLE = {"pothole", "garbage"}


def label(key: str | None) -> str:
    if not key:
        return "Not set"
    return CATEGORIES.get(key, key)
