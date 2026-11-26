use crate::{
    archive, parallel,
    provider::{self, Chapter, Options, Proxy, Source},
    selection::{Selection, sort_chapters},
};
use anyhow::{Result, bail, ensure};
use std::{collections::HashSet, io::IsTerminal, path::PathBuf, time::Duration};

pub struct DownloadRequest {
    pub title: String,
    pub output: PathBuf,
    pub selection: Selection,
    pub options: Options,
    pub proxy: Option<Proxy>,
    pub retries: bool,
    pub debug: bool,
    pub pdf: bool,
    pub force: bool,
    pub show_progress: bool,
}

impl DownloadRequest {
    pub fn run(self) -> Result<()> {
        let Self {
            title,
            output,
            selection,
            options,
            proxy,
            retries,
            debug,
            pdf,
            force,
            show_progress,
        } = self;
        let source = options.source();
        let http = provider::Http::connect(source, retries, proxy.as_ref())?;
        let provider = provider::open(http.clone(), options);
        let title = &title;
        let interactive = show_progress && std::io::stderr().is_terminal();
        let spinner = if interactive {
            let spinner = indicatif::ProgressBar::new_spinner();
            spinner.set_message(format!("Searching for {title}"));
            spinner.enable_steady_tick(Duration::from_millis(100));
            spinner
        } else {
            if show_progress {
                eprintln!("Searching for {title}");
            }
            indicatif::ProgressBar::hidden()
        };
        let manga = provider.search(title);
        spinner.finish_and_clear();
        let mut manga = manga?;
        sort_chapters(&mut manga.chapters);
        let chapters = selection.select(&manga.chapters);
        ensure!(
            !chapters.is_empty(),
            "No matching chapters found for {}",
            manga.title
        );
        let jobs = plan(chapters, source)?;
        let root = archive::manga_directory(&output, source, &manga.title)?;
        let _lock = archive::lock(&root)?;
        let archiver = archive::Archiver {
            root: &root,
            http: &http,
            page_workers: source.limits().pages,
            pdf,
            force,
        };

        let progress = if interactive {
            let bar = indicatif::ProgressBar::new(jobs.len() as u64);
            bar.set_message(manga.title.clone());
            bar.set_style(
                indicatif::ProgressStyle::with_template(
                    "{msg} [{bar:30.cyan/blue}] {pos}/{len} chapters",
                )
                .expect("valid progress bar template"),
            );
            bar
        } else {
            indicatif::ProgressBar::hidden()
        };
        let mut downloaded = 0;
        let mut existing = 0;
        let mut failed = 0;
        let workers = source.limits().chapters;
        for batch in jobs.chunks(workers) {
            if show_progress && !interactive {
                for (chapter, _) in batch {
                    eprintln!("{} · chapter {}", manga.title, chapter.label);
                }
            }
            let results = parallel::map(batch, |(chapter, name)| {
                archiver.archive(provider.as_ref(), chapter, name)
            });
            for ((_, name), result) in batch.iter().zip(results) {
                use archive::ArchiveStatus;
                progress.inc(1);
                match result {
                    Ok(ArchiveStatus::Downloaded) => downloaded += 1,
                    Ok(ArchiveStatus::Existing) => existing += 1,
                    Ok(ArchiveStatus::Unavailable) => {
                        progress.suspend(|| eprintln!("Chapter {name} unavailable"));
                        failed += 1;
                    }
                    Err(err) => {
                        if debug {
                            progress.suspend(|| eprintln!("Chapter {name}: {err:?}"));
                        } else {
                            progress.suspend(|| eprintln!("Chapter {name}: {err:#}"));
                        }
                        failed += 1;
                    }
                }
            }
        }
        progress.finish_and_clear();
        println!(
            "{} · {downloaded} downloaded, {existing} already present, {failed} incomplete",
            manga.title
        );
        ensure!(failed == 0, "{failed} chapter(s) incomplete");
        Ok(())
    }
}

fn plan(chapters: Vec<&Chapter>, source: Source) -> Result<Vec<(&Chapter, String)>> {
    let mut names = HashSet::new();
    let mut jobs = Vec::new();
    for chapter in chapters {
        let name = archive::chapter_name(chapter, source);
        if !names.insert(name.to_lowercase()) {
            if source.coalesces_chapter_aliases() {
                continue;
            }
            bail!("Chapter output names collide: {name}");
        }
        jobs.push((chapter, name));
    }
    Ok(jobs)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::test_http::chapter;

    #[test]
    fn output_collisions_respect_the_source_policy() {
        let first = chapter("001", Some(1.0));
        let second = chapter("1", Some(1.0));
        let fanfox = plan(vec![&first, &second], Source::Fanfox).unwrap();
        assert_eq!(fanfox.len(), 1);
        assert_eq!(fanfox[0].1, "1");

        let alias = chapter("001", Some(1.5));
        assert!(plan(vec![&first, &alias], Source::Mangadex).is_err());
    }
}
