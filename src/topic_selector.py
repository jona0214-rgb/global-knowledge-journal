import json
import random
from pathlib import Path


TOPICS_PATH = Path("data/topics.json")


def select_topic() -> dict:
    data = json.loads(TOPICS_PATH.read_text(encoding="utf-8"))

    unused_topics = [
        topic for topic in data["topics"]
        if topic["status"] == "unused"
    ]

    if not unused_topics:
        raise RuntimeError("사용 가능한 주제가 없습니다.")

    return random.choice(unused_topics)