"""Incremental JSON reply extraction and sentence-aware speech buffering."""
import json
import re

def partial_reply(source):
    """Read only a reply string preceded by a validated action=reply field.

    JSON tool arguments are never interpreted as text or executed by this parser.
    Full schema validation remains the provider's responsibility at stream end.
    """
    decoder = json.JSONDecoder()
    index = 0
    seen = set()
    action = None
    def space(at):
        while at < len(source) and source[at].isspace(): at += 1
        return at
    index = space(index)
    if index >= len(source) or source[index] != '{': return ''
    index += 1
    try:
        while True:
            index = space(index)
            key, index = decoder.raw_decode(source, index)
            if key not in ('action', 'arguments', 'reply') or key in seen: return ''
            seen.add(key)
            index = space(index)
            if source[index] != ':': return ''
            index = space(index + 1)
            if key == 'reply':
                if action != 'reply' or source[index] != '"': return ''
                begin = index
                index += 1
                safe_end = index
                while index < len(source):
                    char = source[index]
                    if char == '"':
                        value = json.loads(source[begin:index + 1])
                        return value if isinstance(value, str) else ''
                    if ord(char) < 32: return ''
                    if char == '\\':
                        if index + 1 >= len(source): break
                        escape = source[index + 1]
                        if escape == 'u':
                            if index + 6 > len(source): break
                            code = int(source[index + 2:index + 6], 16)
                            if 0xD800 <= code <= 0xDBFF:
                                if index + 12 > len(source): break
                                if source[index + 6:index + 8] != '\\u': return ''
                                low = int(source[index + 8:index + 12], 16)
                                if not 0xDC00 <= low <= 0xDFFF: return ''
                                index += 12
                            elif 0xDC00 <= code <= 0xDFFF: return ''
                            else: index += 6
                        elif escape in '"\\/bfnrt': index += 2
                        else: return ''
                    else: index += 1
                    safe_end = index
                return json.loads(source[begin:safe_end] + '"')
            value, index = decoder.raw_decode(source, index)
            if key == 'action':
                if value != 'reply': return ''
                action = value
            elif not isinstance(value, dict): return ''
            index = space(index)
            if source[index] != ',': return ''
            index += 1
    except (ValueError, IndexError, TypeError):
        return ''

class SpeechBuffer:
    """Consume cumulative model text once; bound pending text and phrase length."""
    def __init__(self, first_limit=72, later_limit=220, maximum=2400):
        self.offset = 0
        self.pending = ''
        self.emitted = 0
        self.capped = False
        self.first_limit, self.later_limit, self.maximum = first_limit, later_limit, maximum

    def feed(self, text, final=False):
        if len(text) < self.offset: raise ValueError('The text stream moved backwards.')
        addition = text[self.offset:]
        self.offset = len(text)
        remaining = max(0, self.maximum - self.emitted - len(self.pending))
        if not self.capped:
            self.pending += addition[:remaining]
            if len(addition) > remaining:
                self.capped = True
                last = self.pending.rfind(' ')
                self.pending = self.pending[:last] if last >= 0 else ''
        chunks = []
        while self.pending:
            limit = self.first_limit if self.emitted == 0 else self.later_limit
            boundary = None
            for match in re.finditer(r'[.!?](?:["\u201d\u2019]*)\s+|\n+', self.pending):
                before = self.pending[:match.end()].strip()
                if re.search(r'\b(?:Dr|Mr|Mrs|Ms|Prof|St|vs|e\.g|i\.e)\.$', before, re.I): continue
                if len(before) >= 12 or final:
                    boundary = match.end()
                    break
            if (boundary is None or boundary > limit) and len(self.pending) > limit:
                boundary = self.pending.rfind(' ', 0, limit + 1)
                if boundary <= 0:
                    # Wait for a complete long word, never speak half of one.
                    boundary = self.pending.find(' ', limit)
                    if boundary < 0: boundary = None
            if boundary is None and final: boundary = len(self.pending)
            if boundary is None: break
            piece, self.pending = self.pending[:boundary], self.pending[boundary:]
            self.emitted += len(piece)
            if piece.strip(): chunks.append(piece.strip())
        return chunks
