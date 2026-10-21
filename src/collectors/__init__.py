# Collectors are imported directly — no eager imports here.
# Importing from src.collectors (e.g. NewsCollector) requires feedparser and other
# optional heavy deps; downstream code must import each collector explicitly.
