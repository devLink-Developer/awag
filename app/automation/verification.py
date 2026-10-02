from collections import Counter
from dataclasses import dataclass
from xml.etree import ElementTree as ET

from app.models.entities import MessageType


@dataclass(frozen=True)
class Bubble:
    kind: MessageType
    text: str
    filename: str
    confirmed: bool

    @property
    def signature(self):
        return self.kind.value, self.text, self.filename


def outgoing_bubbles(xml, selectors):
    root = ET.fromstring(xml)
    parents = {child: parent for parent in root.iter() for child in parent}
    rows = []
    seen = set()
    for node in root.iter():
        if not selectors.matches_id(node, "status"):
            continue
        candidate = node
        while candidate in parents:
            candidate = parents[candidate]
            if candidate.tag == "hierarchy":
                break
            if not selectors.matches_id(candidate, "bubble"):
                continue
            nodes = list(candidate.iter())
            texts = [n.get("text", "") for n in nodes if selectors.matches_id(n, "text")]
            documents = [n.get("text", "") for n in nodes if selectors.matches_id(n, "document")]
            audio = any(selectors.matches_id(n, "audio") for n in nodes)
            video = any(selectors.matches_id(n, "video") for n in nodes)
            image = any(selectors.matches_id(n, "image") for n in nodes)
            if not (texts or documents or audio or video or image):
                continue
            # Avoid treating the entire conversation as one bubble on unknown layouts.
            if sum(selectors.matches_id(n, "status") for n in nodes) != 1:
                break
            if id(candidate) in seen:
                break
            seen.add(id(candidate))
            description = node.get("content-desc", "").strip().casefold()
            confirmed = description in {v.casefold() for v in selectors.labels["sent"]}
            pending = any(selectors.matches_id(n, "pending") or n.get("content-desc", "").casefold() in {
                v.casefold() for v in selectors.labels["pending"]
            } for n in nodes)
            kind = (MessageType.document if documents else MessageType.audio if audio else
                    MessageType.video if video else MessageType.image if image else MessageType.text)
            rows.append(Bubble(kind, "\n".join(texts), documents[0] if documents else "", confirmed and not pending))
            break
    return rows


def confirms_new_bubble(before, after, kind, text=None, filename=None):
    baseline = Counter(b.signature for b in before)
    current = Counter(b.signature for b in after)
    for bubble in reversed(after):
        if bubble.kind != kind or not bubble.confirmed:
            continue
        if kind == MessageType.text and bubble.text != text:
            continue
        if text and kind in {MessageType.image, MessageType.video, MessageType.document} and bubble.text != text:
            continue
        if kind == MessageType.document and bubble.filename != filename:
            continue
        if current[bubble.signature] > baseline[bubble.signature]:
            return True
    return False
