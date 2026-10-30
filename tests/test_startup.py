"""Recovery policy and real Windows shortcut roundtrip in a temporary folder."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from raphael.desktop import windows
from raphael.desktop.recovery import retry_delay, RESTART

class RecoveryTests(unittest.TestCase):
    def test_clean_exit_never_restarts(self):
        self.assertEqual(retry_delay(0,2,1),(None,2))
    def test_crashes_back_off_and_stop(self):
        failures=0
        for expected in (5,15,45):
            delay,failures=retry_delay(1,failures,1)
            self.assertEqual(delay,expected)
        self.assertEqual(retry_delay(1,failures,1),(None,3))
    def test_disabled_recovery_and_explicit_restart(self):
        self.assertEqual(retry_delay(1,0,1,False),(None,0))
        self.assertEqual(retry_delay(RESTART,3,1,False),(0,3))
    def test_stable_session_resets_budget(self):
        self.assertEqual(retry_delay(1,3,601),(5,1))

@unittest.skipUnless(os.name=='nt','Windows shortcut integration')
class StartupTests(unittest.TestCase):
    def test_shortcut_enable_ownership_and_disable(self):
        with tempfile.TemporaryDirectory(prefix='Raphael startup ') as folder:
            root=Path(folder);link=root/'Raphael Companion.lnk'
            entry=root/'application with spaces'/'desktop.py'
            config=root/'preferences with spaces.toml'
            with patch.object(windows,'startup_path',return_value=link),patch.object(windows,'legacy_startup_value',return_value=''):
                self.assertEqual(windows.startup_value(),'')
                windows.set_startup(True,entry,config)
                value=windows.startup_value()
                self.assertEqual(json.loads(value),windows.startup_spec(entry,config))
                self.assertTrue(windows.startup_matches(entry,config))
                saved=windows.startup_snapshot()
                windows.set_startup(False,root/'other.py',config)
                self.assertEqual(windows.startup_value(),value,'Another installation cannot disable this one')
                windows.set_startup(False,entry,config)
                self.assertFalse(link.exists())
                windows.restore_startup(saved)
                self.assertEqual(windows.startup_value(),value)
                windows.set_startup(False,entry,config)

if __name__=='__main__':unittest.main()
