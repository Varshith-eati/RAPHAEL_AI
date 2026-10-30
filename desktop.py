"""Native companion launcher. All privacy-sensitive settings default to off."""
from pathlib import Path
import argparse
import logging
import json
import os
import subprocess
import sys
import threading
import time

def main():
    parser = argparse.ArgumentParser(description='Raphael Windows companion')
    parser.add_argument('--config', type=Path, default=Path(__file__).with_name('config.toml'))
    parser.add_argument('--background', action='store_true')
    parser.add_argument('--open', action='store_true', help='Open the main interface even when launch-minimized is saved')
    parser.add_argument('--startup', action='store_true')
    parser.add_argument('--exit', action='store_true')
    parser.add_argument('--managed', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--forward-only', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--launch-id', default='', help=argparse.SUPPRESS)
    args = parser.parse_args()
    from raphael.config import load_config
    from raphael.realtime.settings import SettingsStore
    from raphael.desktop.windows import Instance, startup_matches
    config = load_config(args.config)
    options = SettingsStore(config.data_dir / 'interaction-settings.json').get()
    stop_requested = False
    if os.name == 'nt' and not args.managed:
        from raphael.desktop.recovery import supervise, request_stop
        if args.exit: stop_requested = request_stop(config.server.port)
        else: return supervise(Path(__file__).resolve(), args.config.resolve(), config, args)
    from PySide6.QtCore import QTimer, QIODevice
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    from PySide6.QtWidgets import QApplication, QMessageBox
    qt = QApplication(sys.argv); qt.setQuitOnLastWindowClosed(False)
    from raphael.desktop.theme import initialize_fonts
    initialize_fonts(qt)
    instance = Instance(config.server.port)
    if not instance.owner or args.exit or args.forward_only:
        delivered = False
        for attempt in range(20):
            client = QLocalSocket(); client.connectToServer(instance.name)
            if client.waitForConnected(200):
                client.write(b'exit\n' if args.exit else (b'open\n' if args.open else b'ping\n' if args.startup or args.background else b'open\n'))
                client.waitForBytesWritten(500); client.disconnectFromServer(); delivered = True; break
            time.sleep(.1)
        instance.close()
        return 0 if delivered or stop_requested else (3 if args.exit else 2)
    ipc = QLocalServer()
    ipc.setSocketOptions(QLocalServer.UserAccessOption)
    if not ipc.listen(instance.name):
        instance.close()
        if not args.startup and not args.background: QMessageBox.warning(None, 'Raphael', 'Could not create the private desktop connection.')
        return 2
    if args.managed and args.launch_id:
        config.data_dir.mkdir(parents=True,exist_ok=True)
        record=config.data_dir/'desktop-instance.json'
        temporary=record.with_suffix('.tmp')
        temporary.write_text(json.dumps({'pid':os.getpid(),'launch_id':args.launch_id}),encoding='utf-8')
        os.replace(temporary,record)
    controller = None
    pending_open = False
    connections = set()
    def connected():
        while ipc.hasPendingConnections():
            socket = ipc.nextPendingConnection(); connections.add(socket)
            def read(socket=socket):
                nonlocal pending_open
                if socket.bytesAvailable() > 64: socket.abort(); return
                if not socket.canReadLine(): return
                message = bytes(socket.readLine(65)).strip()
                if message == b'open':
                    if controller: controller.request_action('open')
                    else: pending_open = True
                elif message == b'exit':
                    if controller: controller.exit()
                    else: qt.quit()
                socket.disconnectFromServer()
            socket.readyRead.connect(read)
            socket.disconnected.connect(lambda socket=socket: (connections.discard(socket), socket.deleteLater()))
            QTimer.singleShot(3000, socket.disconnectFromServer)
            read()
    ipc.newConnection.connect(connected)
    app = server = http_thread = None
    failure = False
    def boot():
        nonlocal app, server, controller, http_thread, failure
        try:
            from raphael.application import Application
            from raphael.http_api import LocalServer
            from raphael.logging_setup import configure_logging
            from raphael.desktop.controller import Controller
            configure_logging(config.data_dir)
            app = Application(config)
            if config.laptop.enabled: config.resolve(config.laptop.workspace).mkdir(parents=True, exist_ok=True)
            # Respect the actual per-user registration, including changes made in Windows.
            registered = startup_matches(Path(__file__), args.config)
            if app.settings.get()['startup_enabled'] != registered: app.settings.update({'startup_enabled': registered})
            server = LocalServer(app, require_bootstrap=True)
            app.start(lazy=True)
            http_thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval':.2}, daemon=True)
            http_thread.start()
            controller = Controller(app, server, Path(__file__), config_path=args.config.resolve(), open_ui=args.open or pending_open or not (args.background or args.startup or options['launch_minimized']))
        except Exception as error:
            failure = True
            logging.getLogger('raphael.desktop').error('startup_failed exception=%s', type(error).__name__)
            if not args.startup and not args.background:
                QMessageBox.warning(None, 'Raphael could not start', 'The port may be in use by the previous version, or a dependency is missing. Close the previous Raphael and check runtime/raphael.log. Your files and settings are preserved.')
            qt.quit()
    QTimer.singleShot(options['startup_delay'] * 1000 if args.startup else 0, boot)
    qt.commitDataRequest.connect(lambda manager: controller.exit() if controller else qt.quit())
    try: qt.exec()
    finally:
        if controller: controller.exit()
        if server:
            server.shutdown(); server.server_close()
        if app: app.close()
        if http_thread: http_thread.join(timeout=3)
        ipc.close(); instance.close(); logging.shutdown()
    if controller and controller.restart_requested:
        if args.managed:
            from raphael.desktop.recovery import RESTART
            return RESTART
        subprocess.Popen([sys.executable, '-E', '-s', '-B', str(Path(__file__).resolve()), '--config', str(args.config.resolve()), '--background'],
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return 2 if failure else 0

if __name__ == '__main__': raise SystemExit(main())
