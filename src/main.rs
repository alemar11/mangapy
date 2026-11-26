mod config;

use anyhow::{Result, ensure};
use clap::{Parser, Subcommand};
use config::{output_path, read_yaml, yaml_request};
use mangapy::{
    download::DownloadRequest,
    provider::{Options, Proxy, Source},
    selection::Selection,
};
use std::{path::PathBuf, process::ExitCode};

#[derive(Parser)]
#[command(version, about, disable_version_flag = true)]
struct Cli {
    #[arg(short, long, action = clap::ArgAction::Version)]
    version: Option<bool>,
    #[command(subcommand)]
    mode: Mode,
}

#[derive(Subcommand)]
enum Mode {
    /// Download a manga by title.
    Title {
        /// Manga title to look up.
        manga_title: String,
        /// Manga provider.
        #[arg(short, long, default_value = "fanfox")]
        source: Source,
        /// Output directory (defaults to ~/Downloads/mangapy).
        #[arg(short, long)]
        out: Option<String>,
        /// Show detailed chapter errors.
        #[arg(short, long)]
        debug: bool,
        /// Create one PDF per chapter.
        #[arg(long)]
        pdf: bool,
        /// Redownload and replace existing chapter files.
        #[arg(long)]
        force: bool,
        /// Disable network retries.
        #[arg(long)]
        no_retry: bool,
        /// Hide per-chapter progress messages.
        #[arg(long)]
        no_progress: bool,
        /// JSON object with http and https proxy URLs.
        #[arg(short, long)]
        proxy: Option<String>,
        /// Download every chapter.
        #[arg(short, long, conflicts_with = "chapter")]
        all: bool,
        /// Single chapter or range (e.g. 10, 10-13, or 10-). Defaults to the latest.
        #[arg(short, long)]
        chapter: Option<String>,
    },
    /// Download the entries in a YAML configuration file.
    Yaml { yaml_file: PathBuf },
}

fn run(mode: Mode) -> Result<()> {
    match mode {
        Mode::Title {
            manga_title,
            source,
            out,
            debug,
            pdf,
            force,
            no_retry,
            no_progress,
            proxy,
            all,
            chapter,
        } => {
            let selection = match chapter {
                Some(value) => Selection::from_cli(value)?,
                None if all => Selection::All,
                None => Selection::Latest,
            };
            let title = manga_title.trim();
            ensure!(!title.is_empty(), "Title must be non-empty");
            DownloadRequest {
                title: title.to_owned(),
                output: output_path(out.as_deref())?,
                selection,
                options: Options::defaults(source),
                proxy: proxy
                    .map(|value| serde_json::from_str::<Proxy>(&value))
                    .transpose()?,
                retries: !no_retry,
                debug,
                pdf,
                force,
                show_progress: !no_progress,
            }
            .run()
        }
        Mode::Yaml { yaml_file } => {
            let (defaults, entries) = read_yaml(yaml_file)?;
            let mut failures = 0;
            for (index, entry) in entries.into_iter().enumerate() {
                if let Err(err) = yaml_request(entry, &defaults).and_then(DownloadRequest::run) {
                    eprintln!("Download entry {}: {err:#}", index + 1);
                    failures += 1;
                }
            }
            ensure!(failures == 0, "{failures} download(s) incomplete");
            Ok(())
        }
    }
}

fn main() -> ExitCode {
    match run(Cli::parse().mode) {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("{error:#}");
            ExitCode::FAILURE
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use mangapy::provider::Chapter;

    #[test]
    fn cli_flags_and_selection() {
        assert_eq!(
            Cli::try_parse_from(["mangapy", "-v"]).err().unwrap().kind(),
            clap::error::ErrorKind::DisplayVersion
        );
        assert!(
            Cli::try_parse_from(["mangapy", "title", "manga", "--all", "--chapter", "1"]).is_err()
        );
        assert!(matches!(
            Selection::range("10.5-").unwrap(),
            Selection::Range(10.5, None)
        ));
    }

    #[test]
    fn latest_and_ranges_skip_unavailable_or_unnumbered_chapters_as_applicable() {
        let chapter = |label: &str, number, count| Chapter {
            id: format!("id-{label}"),
            label: label.to_owned(),
            number,
            volume: None,
            url: reqwest::Url::parse("https://example.org").unwrap(),
            count,
            external: false,
        };
        let chapters = [
            chapter("0", Some(0.0), Some(1)),
            chapter("2.5", Some(2.5), Some(1)),
            chapter("3", Some(3.0), Some(0)),
            chapter("Special", None, Some(1)),
        ];
        assert_eq!(Selection::Latest.select(&chapters)[0].number, Some(2.5));
        assert_eq!(
            Selection::Single("Special".into()).select(&chapters)[0].id,
            "id-Special"
        );
        assert_eq!(
            Selection::range("0-2.5").unwrap().select(&chapters).len(),
            2
        );
        assert!(Selection::range("NaN-3").is_err());
        assert!(Selection::range("5-3").is_err());
    }
}
