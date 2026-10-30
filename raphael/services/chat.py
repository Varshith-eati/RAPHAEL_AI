from dataclasses import asdict
import json
import time

from ..providers.base import ChatProvider
from ..contracts import Result
from ..errors import AppError
from ..laptop.service import SCHEMAS
from ..laptop.presentation import hardware_report
from ..realtime.routing import plain_conversation


class ChatService:
    def __init__(self, provider: ChatProvider, laptop=None, settings=None, performance=None):
        self.provider = provider
        self.laptop = laptop
        self.settings, self.performance = settings, performance

    def start(self):
        self.provider.start()

    def execute(self, request, cancel, on_delta):
        direct = (getattr(self.provider, 'supports_plain_conversation', False) and
                  (self.settings is None or self.settings.get()['fast_conversation']) and plain_conversation(request.messages))
        if direct or not self.laptop or not self.laptop.enabled or not hasattr(self.provider, 'tool_turn'):
            if self.settings and not self.settings.get()['response_streaming']:
                parts = []
                result = self.provider.generate(request, cancel, parts.append)
                if self.performance: self.performance.record('prompt', result.details.get('prompt_seconds', 0))
                cancel.check(); on_delta(''.join(parts))
                return result
            result = self.provider.generate(request, cancel, on_delta)
            if self.performance: self.performance.record('prompt', result.details.get('prompt_seconds', 0))
            return result
        messages = [asdict(message) for message in request.messages]
        pending, used, cache = [], [], {}
        def cancel_previews():
            self.laptop.approvals.cancel(pending)
        cancel.register(cancel_previews)
        try:
            for _ in range(4):
                cancel.check()
                streaming = (hasattr(self.provider, 'tool_turn_stream') and
                             (self.settings is None or self.settings.get()['response_streaming']))
                streamed = []
                def publish(text):
                    cancel.check()
                    streamed.append(text)
                    on_delta(text)
                prompt_started = time.perf_counter()
                context = self.laptop.context()
                context_seconds = time.perf_counter() - prompt_started
                if streaming:
                    message, details = self.provider.tool_turn_stream(request, messages, cancel, SCHEMAS, context, publish)
                else:
                    message, details = self.provider.tool_turn(request, messages, cancel, SCHEMAS, context)
                if self.performance:
                    self.performance.record('prompt', context_seconds + details.get('prompt_seconds', 0))
                calls = message.get('tool_calls') or []
                if not calls:
                    text = message.get('content', '').strip()
                    if text.startswith(('{', '```')) and any('"'+item['function']['name']+'"' in text for item in SCHEMAS):
                        # Retry formatting, never parse/execute action JSON printed in prose.
                        messages.extend([{'role': 'assistant', 'content': text},
                                         {'role': 'user', 'content': 'Use the provided structured action format to carry out the requested step. Do not print a tool invocation in the reply field. File changes must still wait for the approval button.'}])
                        continue
                    if not text:
                        raise AppError('The model returned no answer. Try again.', 502, 'empty_reply')
                    if not streamed: on_delta(text)
                    return Result({**details, 'tools_used': used})
                if not isinstance(calls, list) or len(used)+len(calls) > 8:
                    raise AppError('This request needs too many steps. Try one action at a time.')
                messages.append(message)
                for call in calls:
                    cancel.check()
                    function = call.get('function', {}) if isinstance(call, dict) else {}
                    name, arguments = function.get('name'), function.get('arguments', {})
                    if not isinstance(name, str):
                        raise AppError('The model returned an invalid laptop action.')
                    if hasattr(on_delta, 'progress') and name in {item['function']['name'] for item in SCHEMAS}:
                        on_delta.progress('Checking laptop access: ' + name.replace('_', ' '))
                    key = json.dumps([name, arguments], sort_keys=True)
                    try:
                        result = cache.get(key)
                        if result is None:
                            tool_started = time.perf_counter()
                            result = self.laptop.execute(name, arguments, cancel)
                            if self.performance:
                                self.performance.record('tool', time.perf_counter() - tool_started)
                            cache[key] = result
                    except AppError as error:
                        result = {'error': str(error)}
                    used.append(name)
                    if not result.get('error') and name in ('system_info', 'open_app', 'open_text'):
                        cancel.check()
                        # Facts and action receipts come directly from the tool, so a small
                        # model cannot replace real hardware with a fabricated denial of access.
                        on_delta(hardware_report(result) if name=='system_info' else result['message'])
                        return Result({**details, 'tools_used': used})
                    if result.get('approval_required'):
                        approval = result['approval']
                        pending.append(approval['id'])
                        cancel.check()
                        # Never ask the model to approve or describe a write as completed.
                        on_delta(('Please approve this access: ' if approval.get('access_only') else 'I prepared a change: ')+
                                 approval['title']+'. Review it, then choose Approve or Reject. '+
                                 ('No folder listing or file contents have been read yet.' if approval.get('access_only') else 'Nothing has been changed yet.'))
                        return Result({**details, 'tools_used': used, 'approvals': [approval]})
                    cancel.check()
                    messages.append({'role': 'tool', 'tool_name': name,
                                     'content': json.dumps(result, ensure_ascii=False)})
            raise AppError('Raphael reached the action limit. Please ask for one step at a time.')
        except BaseException:
            cancel_previews()
            raise
        finally:
            # Retain the hook while a completed job can still be cancelled by its caller.
            if not pending:
                cancel.unregister(cancel_previews)

    def close(self):
        self.provider.close()
