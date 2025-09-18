# dialogue/topic_threader.py
from collections import deque
from dataclasses import dataclass
import time, re

@dataclass
class Thread:
    key: str
    prompt: str
    last_asked: float = 0.0
    priority: int = 1
    open: bool = True

class TopicThreader:
    def __init__(self, maxlen=6, cooldown=180.0):
        self.q = deque(maxlen=maxlen)
        self.cooldown = cooldown

    def _now(self): return time.time()

    def enqueue_from_user(self, text: str):
        txt = (text or "").lower()
        if re.search(r"\b(бот|telegram|телеграм|нейросеть|чат.?бот)\b", txt):
            self._push("project_bot","Как продвигается твой бот? Что уже умеет?")
        if re.search(r"\b(учеб|сесс|курс|универ|лекци)\w*\b", txt):
            self._push("study","Что по учёбе сейчас самое сложное/интересное?")
        if re.search(r"\b(спорт|вел|тренир|бег|зала|пульс)\w*\b", txt):
            self._push("fitness","Как прошла последняя тренировка? Был прогресс?")
        if re.search(r"\b(фильм|сериал|книг|читал|смотрел)\w*\b", txt):
            self._push("media","Что зацепило в последнем фильме/книге?")
        if re.search(r"\b(музык|плейлист|трек|альбом)\w*\b", txt):
            self._push("music","Что сейчас в плейлисте зациклено?")

    def _push(self,key,prompt,priority=1):
        for t in self.q:
            if t.key==key:
                t.open=True; t.priority=max(t.priority,priority)
                return
        self.q.appendleft(Thread(key=key,prompt=prompt,priority=priority))

    def maybe_hook(self):
        now=self._now()
        for t in list(self.q):
            if t.open and (now-t.last_asked)>=self.cooldown:
                t.last_asked=now
                return t.prompt
        return None

TOPICS=TopicThreader()
