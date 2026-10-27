"""Fair, bounded AI concurrency shared by all application jobs."""
import contextlib
import threading
import time

BLOCKED={'daily_ai_limit','ai_not_connected','model_not_selected','subscription_not_authorized','sign_in_again','reasoning_not_supported','web_search_unavailable'}


def transient(error):
    code=getattr(error,'code','')
    return code in ('network_error','ai_stream_interrupted','ai_request_failed') or (
        code=='upstream_http_error' and any('HTTP '+str(n) in error.detail for n in (408,429,500,502,503,504)))


class AILimiter:
    def __init__(self,limit):
        self.limit=limit;self.condition=threading.Condition();self.waiting=[];self.active={};self.cooldown=0

    @contextlib.contextmanager
    def slot(self,job,check):
        ticket=object()
        with self.condition:
            self.waiting.append(ticket)
            try:
                while True:
                    check()
                    if self.waiting[0] is ticket and sum(self.active.values())<self.limit() and time.monotonic()>=self.cooldown:break
                    self.condition.wait(.2)
                self.waiting.remove(ticket);self.active[job]=self.active.get(job,0)+1
                self.condition.notify_all()
            except BaseException:
                self.waiting.remove(ticket);self.condition.notify_all();raise
        try:yield
        finally:
            with self.condition:
                self.active[job]-=1
                if not self.active[job]:del self.active[job]
                self.condition.notify_all()

    def cool_down(self,seconds):
        with self.condition:self.cooldown=max(self.cooldown,time.monotonic()+seconds)

    def state(self):
        with self.condition:return {'active':sum(self.active.values()),'waiting':len(self.waiting),'by_job':dict(self.active),'limit':self.limit()}
