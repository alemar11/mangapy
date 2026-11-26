use anyhow::{Context, Result, ensure};
use clap::Parser;
use mangapy::{
    archive::{ArchiveStatus, Archiver, chapter_name, write_pdf},
    provider::{self, Http, MangaDexOptions, Options, Source},
    selection::{Selection, sort_chapters},
};
use serde_json::{Value, json};
use std::{
    fs,
    path::{Path, PathBuf},
    time::Instant,
};

#[derive(Parser)]
struct Args {
    #[arg(short, long, default_value = "fanfox")]
    source: Source,
    #[arg(short, long, default_value = "Boku dake ga Inai Machi")]
    title: String,
    #[arg(short, long)]
    chapter: Option<String>,
    #[arg(short, long)]
    out: Option<PathBuf>,
    #[arg(short, long, default_value = "1", value_parser = clap::value_parser!(u32).range(1..))]
    rounds: u32,
    #[arg(long)]
    pages: bool,
    #[arg(long)]
    images: bool,
    #[arg(long)]
    pdf: bool,
    #[arg(long)]
    pdf_only: bool,
    #[arg(long)]
    no_retry: bool,
    #[arg(long)]
    no_progress: bool,
    #[arg(long, value_delimiter = ',', default_value = "en")]
    translated_language: Vec<String>,
    #[arg(long, value_delimiter = ',', default_value = "safe,suggestive,erotica")]
    content_rating: Vec<String>,
    #[arg(long)]
    data_saver: bool,
}

fn measure(name: &str, rounds: u32, mut run: impl FnMut(u32) -> Result<()>) -> Result<Value> {
    let mut times = Vec::new();
    for index in 1..=rounds {
        let start = Instant::now();
        run(index).with_context(|| format!("{name}, round {index}"))?;
        times.push(start.elapsed().as_secs_f64() * 1_000.0);
    }
    Ok(json!({
        "name": name,
        "avg": times.iter().sum::<f64>() / f64::from(rounds),
        "min": times.iter().copied().reduce(f64::min),
        "max": times.iter().copied().reduce(f64::max),
        "runs": times,
    }))
}

fn main() -> Result<()> {
    let args = Args::parse();
    let default_phases = !(args.pages || args.images || args.pdf || args.pdf_only);
    let http = Http::connect(args.source, !args.no_retry, None)?;
    let options = match args.source {
        Source::Fanfox => Options::FanFox,
        Source::Mangadex => Options::MangaDex(MangaDexOptions {
            languages: args.translated_language,
            ratings: args.content_rating,
            data_saver: args.data_saver,
        }),
    };
    let provider = provider::open(http.clone(), options);
    let selection = args
        .chapter
        .clone()
        .map_or(Ok(Selection::Latest), Selection::from_cli)?;
    let output = args
        .out
        .or_else(|| dirs::home_dir().map(|home| home.join("Downloads/mangapy")))
        .context("Output directory unavailable")?
        .join("bench-rust");
    let title = &args.title;
    let select = || {
        let mut manga = provider.search(title)?;
        sort_chapters(&mut manga.chapters);
        selection
            .select(&manga.chapters)
            .first()
            .map(|chapter| (*chapter).clone())
            .context("No matching chapter")
    };
    let download = |pdf: bool| -> Result<(PathBuf, String)> {
        let chapter = select()?;
        let name = chapter_name(&chapter, args.source);
        let root = tempfile::tempdir_in(&output)?.keep();
        let archiver = Archiver {
            root: &root,
            http: &http,
            page_workers: args.source.limits().pages,
            pdf,
            force: false,
        };
        ensure!(
            archiver.archive(provider.as_ref(), &chapter, &name)? == ArchiveStatus::Downloaded,
            "Chapter unavailable"
        );
        Ok((root, name))
    };

    let mut results = serde_json::Map::new();
    if args.pages || default_phases {
        results.insert(
            "pages".into(),
            measure("search_pages", args.rounds, |_| {
                let chapter = select()?;
                ensure!(
                    !provider.pages(&chapter)?.is_empty(),
                    "Chapter has no pages"
                );
                Ok(())
            })?,
        );
    }
    for (key, enabled, pdf) in [("images", args.images, false), ("pdf", args.pdf, true)] {
        if enabled || default_phases {
            fs::create_dir_all(&output)?;
            results.insert(
                key.into(),
                measure(&format!("download_{key}"), args.rounds, |round| {
                    if !args.no_progress {
                        eprintln!("{key}: round {round}");
                    }
                    download(pdf).map(|_| ())
                })?,
            );
        }
    }
    if args.pdf_only {
        fs::create_dir_all(&output)?;
        let (root, name) = download(false)?;
        let mut images = fs::read_dir(root.join("images").join(&name))?
            .map(|entry| entry.map(|entry| entry.path()))
            .collect::<Result<Vec<_>, _>>()?;
        images.sort_by_key(|path| page_index(path));
        results.insert(
            "pdf_only".into(),
            measure("pdf_only", args.rounds, |round| {
                write_pdf(&images, &root.join(format!("{name}-{round}.pdf")))
            })?,
        );
    }
    println!(
        "{}",
        serde_json::to_string_pretty(&json!({
            "source": args.source.name(), "title": title,
            "chapter": args.chapter, "rounds": args.rounds, "results": results,
        }))?
    );
    Ok(())
}

fn page_index(path: &Path) -> usize {
    path.file_stem()
        .and_then(|stem| stem.to_str())
        .and_then(|stem| stem.parse().ok())
        .unwrap_or(usize::MAX)
}
