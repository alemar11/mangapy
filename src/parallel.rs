use anyhow::{Result, anyhow};

/// Runs an ordered batch on scoped threads. A single item needs no worker.
pub(crate) fn map<T: Sync, R: Send>(
    items: &[T],
    operation: impl Fn(&T) -> Result<R> + Sync,
) -> Vec<Result<R>> {
    if items.len() == 1 {
        return vec![operation(&items[0])];
    }
    std::thread::scope(|scope| {
        let jobs: Vec<_> = items
            .iter()
            .map(|item| {
                let operation = &operation;
                scope.spawn(move || operation(item))
            })
            .collect();
        jobs.into_iter()
            .map(|job| {
                job.join()
                    .map_err(|_| anyhow!("Download worker panicked"))
                    .and_then(|result| result)
            })
            .collect()
    })
}
