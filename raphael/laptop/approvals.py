"""Single-use, expiring approval proposals; the model cannot approve actions."""
import copy
import threading
import time
import uuid

from ..errors import AppError


class Approvals:
    def __init__(self, commit, ttl=600):
        self.commit, self.ttl = commit, ttl
        self._records = {}
        self._lock = threading.RLock()

    def _expire(self):
        for record in self._records.values():
            if record['state'] == 'pending' and time.time() > record['expires_at']:
                record['state'] = 'expired'

    @staticmethod
    def public(record):
        proposal = record['proposal']
        return {key: copy.deepcopy(record[key]) for key in ('id', 'state', 'expires_at', 'result')} | {
            key: copy.deepcopy(proposal.get(key)) for key in ('title', 'tool', 'target', 'preview', 'content', 'backup_on_update', 'access_only')}

    def create(self, proposal):
        with self._lock:
            self._expire()
            if len(self._records) >= 24:
                old = next((key for key, item in self._records.items() if item['state'] not in ('pending', 'executing')), None)
                if old is None:
                    raise AppError('Review your pending laptop actions before creating more.', 429, 'approvals_full')
                del self._records[old]
            record = {'id': uuid.uuid4().hex, 'proposal': copy.deepcopy(proposal), 'state': 'pending',
                      'expires_at': time.time()+self.ttl, 'result': None}
            self._records[record['id']] = record
            return self.public(record)

    def list(self):
        with self._lock:
            self._expire()
            return [self.public(record) for record in self._records.values()]

    def cancel(self, ids):
        with self._lock:
            for key in ids:
                if key in self._records and self._records[key]['state'] == 'pending':
                    self._records[key]['state'] = 'cancelled'

    def decide(self, key, decision):
        if decision not in ('approve', 'reject'):
            raise AppError('Choose Approve or Reject.')
        with self._lock:
            self._expire()
            record = self._records.get(key)
            if record is None:
                raise AppError('That proposal is unavailable. Ask Raphael to prepare it again.', 404, 'approval_missing')
            if record['state'] != 'pending':
                raise AppError('That proposal has already been handled or expired.', 409, 'approval_closed')
            if decision == 'reject':
                record['state'] = 'rejected'; record['result'] = {'message':
                    'Rejected. No folder listing or file contents were read.' if record['proposal'].get('access_only') else
                    'Rejected. No file changes were made.'}
                return self.public(record)
            record['state'] = 'executing'
        try:
            result = self.commit(copy.deepcopy(record['proposal']))
        except Exception as error:
            message = str(error) if isinstance(error, AppError) else 'The action could not finish. Review the workspace and try again.'
            with self._lock:
                record['state'] = 'failed'; record['result'] = {'message': message}
        else:
            with self._lock:
                record['state'] = 'completed'; record['result'] = result
        return self.public(record)

    def close(self):
        with self._lock:
            self.cancel(list(self._records))
