use anyhow::{Context, Result, bail, ensure};
use mangapy::{
    download::DownloadRequest,
    provider::{Options, Proxy, Source},
    selection::Selection,
};
use serde::{Deserialize, Deserializer};
use serde_yaml_ng::{Mapping, Value};
use std::{collections::HashSet, fs, path::PathBuf};

#[derive(Deserialize)]
#[serde(untagged)]
enum ChapterValue {
    Text(String),
    Numeric(f64),
}

impl ChapterValue {
    fn text(self) -> String {
        match self {
            Self::Text(value) => value,
            Self::Numeric(value) => value.to_string(),
        }
    }
}

fn present<'de, D: Deserializer<'de>, T: Deserialize<'de>>(
    value: D,
) -> Result<Option<T>, D::Error> {
    T::deserialize(value).map(Some)
}

#[derive(Default, Deserialize)]
#[serde(default, deny_unknown_fields)]
struct Entry {
    title: String,
    #[serde(deserialize_with = "present")]
    source: Option<Source>,
    #[serde(deserialize_with = "present")]
    output: Option<String>,
    #[serde(deserialize_with = "present")]
    debug: Option<bool>,
    proxy: Option<Proxy>,
    pdf: bool,
    #[serde(deserialize_with = "present")]
    force: Option<bool>,
    #[serde(deserialize_with = "present")]
    no_retry: Option<bool>,
    #[serde(deserialize_with = "present")]
    no_progress: Option<bool>,
    download_all_chapters: bool,
    download_last_chapter: bool,
    download_single_chapter: Option<ChapterValue>,
    download_chapters: Option<ChapterValue>,
    #[serde(deserialize_with = "present")]
    translated_language: Option<StringList>,
    #[serde(deserialize_with = "present")]
    content_rating: Option<StringList>,
    #[serde(deserialize_with = "present")]
    data_saver: Option<bool>,
}

#[derive(Deserialize)]
#[serde(untagged)]
enum StringList {
    One(String),
    Many(Vec<String>),
}

impl StringList {
    fn values(self) -> Result<Vec<String>> {
        let values = match self {
            Self::One(value) => vec![value],
            Self::Many(values) => values,
        };
        ensure!(
            !values.is_empty() && values.iter().all(|s| !s.trim().is_empty()),
            "Expected a non-empty string or list"
        );
        Ok(values.into_iter().map(|s| s.trim().to_owned()).collect())
    }
}

#[derive(Clone, Default, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub(crate) struct Defaults {
    #[serde(deserialize_with = "present")]
    output: Option<String>,
    debug: bool,
    proxy: Option<Proxy>,
    force: bool,
    no_retry: bool,
    no_progress: bool,
}

pub(crate) fn read_yaml(path: PathBuf) -> Result<(Defaults, Vec<Value>)> {
    let mut root: Mapping = serde_yaml_ng::from_str(&fs::read_to_string(path)?)?;
    let downloads = root.remove("downloads");
    let mut legacy = Vec::new();
    let mut groups = HashSet::new();
    let keys: Vec<_> = root.keys().cloned().collect();
    for key in keys {
        let Some(source) = key.as_str().and_then(|key| key.parse::<Source>().ok()) else {
            continue;
        };
        ensure!(
            downloads.is_none(),
            "downloads cannot be combined with legacy provider groups"
        );
        ensure!(
            groups.insert(key.as_str().unwrap().to_ascii_lowercase()),
            "Duplicate provider group"
        );
        for mut item in serde_yaml_ng::from_value::<Vec<Mapping>>(root.remove(&key).unwrap())? {
            item.entry(Value::from("source"))
                .or_insert_with(|| Value::from(source.name()));
            legacy.push(Value::Mapping(item));
        }
    }
    let entries = match downloads {
        Some(value) => serde_yaml_ng::from_value(value)?,
        None => legacy,
    };
    ensure!(!entries.is_empty(), "YAML contains no downloads");
    ensure!(
        entries.iter().all(Value::is_mapping),
        "Every download must be a mapping"
    );
    Ok((serde_yaml_ng::from_value(Value::Mapping(root))?, entries))
}

pub(crate) fn yaml_request(value: Value, defaults: &Defaults) -> Result<DownloadRequest> {
    // An explicit null disables an inherited proxy; an omitted field inherits it.
    let proxy_is_null = value.get("proxy").is_some_and(Value::is_null);
    let entry: Entry = serde_yaml_ng::from_value(value)?;
    let enabled = [
        entry.download_all_chapters,
        entry.download_last_chapter,
        entry.download_single_chapter.is_some(),
        entry.download_chapters.is_some(),
    ];
    ensure!(
        enabled.into_iter().filter(|enabled| *enabled).count() <= 1,
        "Chapter selection fields are mutually exclusive"
    );
    let selection = if entry.download_all_chapters {
        Selection::All
    } else if let Some(value) = entry.download_single_chapter {
        Selection::Single(value.text())
    } else if let Some(value) = entry.download_chapters {
        Selection::range(&value.text())?
    } else {
        Selection::Latest
    };
    let title = entry.title.trim();
    ensure!(!title.is_empty(), "Title must be non-empty");
    let source = entry.source.unwrap_or(Source::Fanfox);
    ensure!(
        source == Source::Mangadex
            || (entry.translated_language.is_none()
                && entry.content_rating.is_none()
                && entry.data_saver.is_none()),
        "translated_language, content_rating and data_saver require MangaDex"
    );
    let output = output_path(entry.output.or_else(|| defaults.output.clone()).as_deref())?;
    let mut options = Options::defaults(source);
    if let Options::MangaDex(options) = &mut options {
        if let Some(languages) = entry.translated_language {
            options.languages = languages.values()?;
        }
        if let Some(ratings) = entry.content_rating {
            options.ratings = ratings.values()?;
        }
        options.data_saver = entry.data_saver.unwrap_or(false);
    }
    Ok(DownloadRequest {
        title: title.to_owned(),
        output,
        selection,
        options,
        proxy: if proxy_is_null {
            None
        } else {
            entry.proxy.or_else(|| defaults.proxy.clone())
        },
        retries: !entry.no_retry.unwrap_or(defaults.no_retry),
        debug: entry.debug.unwrap_or(defaults.debug),
        pdf: entry.pdf,
        force: entry.force.unwrap_or(defaults.force),
        show_progress: !entry.no_progress.unwrap_or(defaults.no_progress),
    })
}

pub(crate) fn output_path(output: Option<&str>) -> Result<PathBuf> {
    let home = || dirs::home_dir().context("Home directory unavailable");
    Ok(match output.map(str::trim) {
        None => home()?.join("Downloads").join("mangapy"),
        Some("") => bail!("Output must be non-empty"),
        Some("~") => home()?,
        Some(s) if s.starts_with("~/") => home()?.join(&s[2..]),
        Some(s) => PathBuf::from(s),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn yaml_legacy_groups_and_invalid_fields() {
        let tmp = tempfile::tempdir().unwrap();
        let yaml = tmp.path().join("settings.yaml");
        fs::write(
            &yaml,
            "FanFox:\n  - title: Example\n    download_single_chapter: 10.5\n",
        )
        .unwrap();
        let (_, entries) = read_yaml(yaml.clone()).unwrap();
        let entry: Entry = serde_yaml_ng::from_value(entries.into_iter().next().unwrap()).unwrap();
        assert_eq!(entry.source, Some(Source::Fanfox));
        assert_eq!(entry.download_single_chapter.unwrap().text(), "10.5");

        fs::write(&yaml, "FanFox: []\ndownloads: []\n").unwrap();
        assert!(read_yaml(yaml.clone()).is_err());
        fs::write(&yaml, "unexpected: true\ndownloads: [{title: Example}]\n").unwrap();
        assert!(read_yaml(yaml).is_err());
        for input in [
            "title: Example\nforce: null",
            "title: Example\nunknown: true",
        ] {
            assert!(serde_yaml_ng::from_str::<Entry>(input).is_err());
        }
    }
    #[test]
    fn resolves_yaml_defaults_and_rejects_conflicting_options() {
        let defaults: Defaults = serde_yaml_ng::from_str(
            "output: ~/manga\nproxy: {http: 'http://localhost:8888', https: 'http://localhost:8888'}"
        ).unwrap();
        let request = |input| yaml_request(serde_yaml_ng::from_str(input).unwrap(), &defaults);
        let job = request("title: Example\nsource: MANGADEX\nproxy: null\ndownload_chapters: 2.5-")
            .unwrap();
        assert_eq!(job.output, dirs::home_dir().unwrap().join("manga"));
        assert!(job.proxy.is_none());
        assert!(matches!(job.options, Options::MangaDex(_)));
        assert!(matches!(job.selection, Selection::Range(2.5, None)));
        assert!(request("title: Example").unwrap().proxy.is_some());
        assert!(request("title: Example\ndata_saver: true").is_err());
        assert!(
            request("title: Example\ndownload_all_chapters: true\ndownload_single_chapter: 2")
                .is_err()
        );
    }

    #[test]
    fn existing_yaml_samples_parse() {
        for sample in fs::read_dir("samples").unwrap() {
            let path = sample.unwrap().path();
            if path.extension().is_some_and(|ext| ext == "yaml") {
                let (_, entries) = read_yaml(path).unwrap();
                for entry in entries {
                    serde_yaml_ng::from_value::<Entry>(entry).unwrap();
                }
            }
        }
    }
}
