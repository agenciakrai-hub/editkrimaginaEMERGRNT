/** Serial polling: publish fresh photos before announcing batch completion. */
export function watchBatch({ readJob, readPhotos, onJob, onPhotos, onComplete, onError,
  schedule = (fn) => setTimeout(fn, 2500), cancel = clearTimeout }) {
  let stopped = false, timer, progress = -1;
  const tick = async () => {
    try {
      const job = await readJob();
      if (stopped) return;
      onJob(job);
      if (job.processed !== progress || ["done", "failed", "interrupted"].includes(job.status)) {
        const photos = await readPhotos();
        if (stopped) return;
        onPhotos(photos);
        progress = job.processed;
      }
      if (["done", "failed", "interrupted"].includes(job.status)) {
        stopped = true;
        onComplete(job);
        return;
      }
    } catch (err) {
      if (stopped) return;
      if ([401, 403, 404].includes(err?.response?.status)) {
        stopped = true;
        onError(err);
        return;
      }
      // Keep the job alive after transient network/server errors, including final photo refresh.
    }
    if (!stopped) timer = schedule(tick);
  };
  tick();
  return () => { stopped = true; cancel(timer); };
}
