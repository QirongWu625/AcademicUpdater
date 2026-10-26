"""Run the personal AcademicUpdater application on loopback only."""
import argparse
import json
import os
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path
from academic_updater.server import Application,make_server


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--data-dir',default=str(Path(__file__).resolve().parent/'data'))
    parser.add_argument('--open',action='store_true')
    parser.add_argument('--no-scheduler',action='store_true')
    args=parser.parse_args()
    directory=Path(args.data_dir);directory.mkdir(parents=True,exist_ok=True)
    lock=open(directory/'instance.lock','a+b')
    try:
        if os.name=='nt':
            import msvcrt
            lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:
        try:
            old=json.loads((directory/'server.json').read_text());url=f"http://127.0.0.1:{old['port']}"
            with urllib.request.urlopen(url+'/api/health',timeout=3) as r:healthy=json.load(r).get('app')=='AcademicUpdater'
            if healthy:
                if args.open:webbrowser.open(url)
                print(url,flush=True);return
        except Exception:pass
        raise SystemExit('AcademicUpdater is already running with this data folder.')
    app=Application(directory)
    server=make_server(app,args.port)
    (directory/'server.json').write_text(json.dumps({'pid':os.getpid(),'port':app.port}),encoding='utf-8')
    if not args.no_scheduler:
        app.service.recover_interrupted()
        threading.Thread(target=app.service.scheduler,daemon=True).start()
    url=f'http://127.0.0.1:{app.port}'
    print(url,flush=True)
    if args.open:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:app.service.stop.set();server.server_close();lock.close()


if __name__=='__main__':main()
