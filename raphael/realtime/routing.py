"""Conservative fast path for clearly conversational requests, without another model call."""
import re

LOCAL = re.compile(r'\b(?:hardware|system|ram|gpu|cpu|storage|drives?|files?|folders?|workspace|desktop|documents?|downloads?|windows|chrome|gmail|youtube|github|google|apps?|open|create|write|save|edit|browse|read|notepad|calculator|computer|laptop|devices?|settings?|permissions?|access|screen|mail|memory|notes?)\b|[A-Z]:[\\/]', re.I)
STANDALONE = re.compile(r'^(?:hello\b|hi\b|hey\b|thanks\b|thank you\b|what (?:is|are)\b|explain\b|define\b|why\b|give\b.{0,50}\b(?:tips|ideas|examples)\b)', re.I)
ACTION = re.compile(r'\b(?:launch|start|run|execute|show|check|change|delete|rename|move|copy|install|list|find|explorer|task[ _]manager|my|mine|this|these|that|those)\b', re.I)

def plain_conversation(messages):
    """Ambiguity, local references and follow-up actions retain the full tool protocol.

    Only an explicit standalone question/greeting with no local-tool context takes
    the smaller plain-text prompt. This does not select a smaller reasoning model.
    """
    if not messages: return False
    latest = messages[-1].content.strip()
    return bool(STANDALONE.search(latest)) and not ACTION.search(latest) and not any(LOCAL.search(m.content) for m in messages[-6:])
