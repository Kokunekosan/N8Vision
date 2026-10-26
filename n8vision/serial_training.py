"""One FIFO worker for interactive and maintenance YOLO evolution."""
import logging
import queue
import threading

class SerialTrainingQueue:
 def __init__(self):
  self.queue=queue.Queue()
  self.lock=threading.Lock()
  self.worker=None
 def submit(self,run):
  with self.lock:
   self.queue.put(run)
   if self.worker is None:
    self.worker=threading.Thread(target=self._work,name='n8vision-yolo-training',daemon=True)
    self.worker.start()
 def _work(self):
  while True:
   run=self.queue.get()
   try:run()
   except Exception:logging.getLogger(__name__).exception('Queued YOLO job failed')
   finally:self.queue.task_done()

YOLO_TRAINING_QUEUE=SerialTrainingQueue()
