use anyhow::{Context, Result, bail, ensure};
use reqwest::{Url, blocking::Client, header::HeaderMap};
use serde_json::Value;
use std::{
    collections::HashSet,
    sync::Mutex,
    thread,
    time::{Duration, Instant},
};

pub(crate) mod fanfox;
use fanfox::FanFox;

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Source {
    Fanfox,
    Mangadex,
}

pub struct Limits {
    pub chapters: usize,
    pub pages: usize,
}

impl Source {
    pub fn name(self) -> &'static str {
        match self {
            Self::Fanfox => "fanfox",
            Self::Mangadex => "mangadex",
        }
    }

    pub fn limits(self) -> Limits {
        match self {
            Self::Fanfox => Limits {
                chapters: 1,
                pages: 1,
            },
            Self::Mangadex => Limits {
                chapters: 2,
                pages: 4,
            },
        }
    }

    pub fn chapter_output_label(self, chapter: &Chapter) -> std::borrow::Cow<'_, str> {
        use std::borrow::Cow;
        match (self, chapter.number) {
            (Self::Fanfox, Some(number)) => Cow::Owned(number.to_string()),
            _ => Cow::Borrowed(&chapter.id),
        }
    }

    pub fn coalesces_chapter_aliases(self) -> bool {
        matches!(self, Self::Fanfox)
    }

    fn user_agent(self) -> &'static str {
        match self {
            Self::Fanfox => fanfox::USER_AGENT,
            Self::Mangadex => "mangapy",
        }
    }
}

impl std::str::FromStr for Source {
    type Err = anyhow::Error;

    fn from_str(value: &str) -> Result<Self> {
        match value.trim().to_ascii_lowercase().as_str() {
            "fanfox" => Ok(Self::Fanfox),
            "mangadex" => Ok(Self::Mangadex),
            _ => bail!("Unknown source: {value}"),
        }
    }
}

impl<'de> serde::Deserialize<'de> for Source {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        let value = String::deserialize(deserializer)?;
        value.parse().map_err(serde::de::Error::custom)
    }
}

#[derive(Clone)]
pub struct Chapter {
    pub id: String,
    pub label: String,
    pub number: Option<f64>,
    pub volume: Option<f64>,
    pub url: Url,
    pub count: Option<usize>,
    pub external: bool,
}

impl Chapter {
    pub fn is_downloadable(&self) -> bool {
        !self.external && self.count != Some(0)
    }
}

pub struct Manga {
    pub title: String,
    pub chapters: Vec<Chapter>,
}

pub trait Provider: Sync {
    fn search(&self, title: &str) -> Result<Manga>;
    fn pages(&self, chapter: &Chapter) -> Result<Vec<Url>>;
    fn page_headers(&self, _url: &Url) -> HeaderMap {
        HeaderMap::new()
    }
}

#[derive(Clone, serde::Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Proxy {
    pub http: String,
    pub https: String,
}

#[derive(Clone)]
pub struct Http {
    client: Client,
    retries: bool,
}

impl Http {
    pub fn new(client: Client, retries: bool) -> Self {
        Self { client, retries }
    }

    pub fn connect(source: Source, retries: bool, proxy: Option<&Proxy>) -> Result<Self> {
        let mut client = Client::builder()
            .connect_timeout(Duration::from_secs(10))
            .timeout(Duration::from_secs(30))
            .user_agent(source.user_agent());
        if let Some(proxy) = proxy {
            let parse = |value: &str| -> Result<Url> {
                let (scheme, authority) = value.split_once("://").context("Invalid proxy URL")?;
                ensure!(
                    matches!(scheme, "http" | "https") && !authority.starts_with('/'),
                    "Invalid proxy URL"
                );
                let url = Url::parse(value).context("Invalid proxy URL")?;
                ensure!(url.has_host(), "Invalid proxy URL");
                Ok(url)
            };
            client = client
                .proxy(reqwest::Proxy::http(parse(&proxy.http)?)?)
                .proxy(reqwest::Proxy::https(parse(&proxy.https)?)?);
        }
        Ok(Self::new(client.build()?, retries))
    }

    pub fn get(&self, url: &Url, headers: HeaderMap) -> Result<reqwest::blocking::Response> {
        self.request(url, headers, || {})
    }

    fn request(
        &self,
        url: &Url,
        headers: HeaderMap,
        mut before_attempt: impl FnMut(),
    ) -> Result<reqwest::blocking::Response> {
        let max_retries = if self.retries { 2 } else { 0 };
        let mut attempt = 0;
        loop {
            before_attempt();
            let result = self.client.get(url.clone()).headers(headers.clone()).send();
            let retry = match &result {
                Ok(response) => {
                    response.status() == reqwest::StatusCode::TOO_MANY_REQUESTS
                        || response.status().is_server_error()
                }
                Err(_) => true,
            };
            if !retry || attempt == max_retries {
                return Ok(result?.error_for_status()?);
            }
            let retry_after = result
                .as_ref()
                .ok()
                .and_then(|r| r.headers().get(reqwest::header::RETRY_AFTER));
            let delay = retry_delay(retry_after, attempt);
            drop(result);
            thread::sleep(delay);
            attempt += 1;
        }
    }
}

fn retry_delay(retry_after: Option<&reqwest::header::HeaderValue>, attempt: u32) -> Duration {
    let delay = retry_after
        .and_then(|value| value.to_str().ok()?.parse::<f64>().ok())
        .filter(|n| n.is_finite() && *n >= 0.0)
        .unwrap_or((1_u32 << attempt) as f64)
        .min(30.0);
    Duration::from_secs_f64(delay)
}

pub enum Options {
    FanFox,
    MangaDex(MangaDexOptions),
}

impl Options {
    pub fn defaults(source: Source) -> Self {
        match source {
            Source::Fanfox => Self::FanFox,
            Source::Mangadex => Self::MangaDex(MangaDexOptions::default()),
        }
    }

    pub fn source(&self) -> Source {
        match self {
            Self::FanFox => Source::Fanfox,
            Self::MangaDex(_) => Source::Mangadex,
        }
    }
}

pub struct MangaDexOptions {
    pub languages: Vec<String>,
    pub ratings: Vec<String>,
    pub data_saver: bool,
}

impl Default for MangaDexOptions {
    fn default() -> Self {
        Self {
            languages: vec!["en".into()],
            ratings: ["safe", "suggestive", "erotica"]
                .map(str::to_owned)
                .to_vec(),
            data_saver: false,
        }
    }
}

pub fn open(http: Http, options: Options) -> Box<dyn Provider> {
    match options {
        Options::FanFox => Box::new(FanFox::new(http)),
        Options::MangaDex(options) => Box::new(MangaDex {
            http,
            base: Url::parse(API).expect("valid MangaDex base URL"),
            options,
            last_api_request: Mutex::new(None),
        }),
    }
}

pub fn number(value: &str) -> Option<f64> {
    value.trim().parse::<f64>().ok().filter(|n| n.is_finite())
}

pub(crate) fn legacy_slug(title: &str) -> String {
    static SEPARATORS: std::sync::LazyLock<regex::Regex> =
        std::sync::LazyLock::new(|| regex::Regex::new("[^a-zA-Z0-9]+").unwrap());
    SEPARATORS
        .replace_all(
            title.trim_matches(|c: char| !c.is_ascii_alphanumeric()),
            "_",
        )
        .to_ascii_lowercase()
}

fn normalized(title: &str) -> String {
    title
        .to_lowercase()
        .chars()
        .filter(|c| c.is_alphanumeric())
        .collect()
}

fn display_title(attributes: &Value) -> Option<&str> {
    let titles = attributes["title"].as_object()?;
    titles
        .get("en")
        .and_then(Value::as_str)
        .or_else(|| titles.values().find_map(Value::as_str))
}

struct MangaDex {
    base: Url,
    http: Http,
    options: MangaDexOptions,
    last_api_request: Mutex<Option<Instant>>,
}

const API: &str = "https://api.mangadex.org";

impl MangaDex {
    fn json(&self, url: &Url) -> Result<Value> {
        Ok(self
            .http
            .request(url, HeaderMap::new(), || {
                let mut last = self.last_api_request.lock().expect("request throttle lock");
                if let Some(start) = *last {
                    thread::sleep(Duration::from_millis(500).saturating_sub(start.elapsed()));
                }
                *last = Some(Instant::now());
            })?
            .json()?)
    }
}

impl Provider for MangaDex {
    fn search(&self, title: &str) -> Result<Manga> {
        let mut url = self.base.join("/manga")?;
        url.query_pairs_mut()
            .append_pair("limit", "10")
            .append_pair("title", title);
        let payload = self.json(&url)?;
        let results = payload["data"]
            .as_array()
            .context("Invalid MangaDex search response")?;
        let query = normalized(title);
        let mut best = None;
        for item in results {
            let attributes = &item["attributes"];
            let titles = std::iter::once(&attributes["title"])
                .chain(attributes["altTitles"].as_array().into_iter().flatten());
            let mut exact = false;
            let mut partial = false;
            for candidate in titles
                .filter_map(Value::as_object)
                .flat_map(|map| map.values())
                .filter_map(Value::as_str)
            {
                let candidate = normalized(candidate);
                exact |= candidate == query;
                partial |= !query.is_empty() && candidate.contains(&query);
            }
            if exact {
                best = Some(item);
                break;
            }
            if partial && best.is_none() {
                best = Some(item);
            }
        }
        let suggestions = || {
            results
                .iter()
                .take(5)
                .filter_map(|item| display_title(&item["attributes"]))
                .collect::<Vec<_>>()
                .join(", ")
        };
        let item = best.with_context(|| {
            let suggestions = suggestions();
            if suggestions.is_empty() {
                format!("Manga not found: {title}")
            } else {
                format!("Manga not found: {title}. Suggestions: {suggestions}")
            }
        })?;
        let id = item["id"].as_str().context("Missing manga ID")?;
        let title = display_title(&item["attributes"])
            .unwrap_or(title)
            .to_owned();
        let mut chapters = Vec::new();
        let mut seen = HashSet::new();
        let mut total = 0;
        loop {
            let mut url = self.base.join("/chapter")?;
            {
                let mut pairs = url.query_pairs_mut();
                pairs
                    .append_pair("manga", id)
                    .append_pair("limit", "100")
                    .append_pair("offset", &chapters.len().to_string())
                    .append_pair("order[chapter]", "asc");
                for language in &self.options.languages {
                    pairs.append_pair("translatedLanguage[]", language);
                }
                for rating in &self.options.ratings {
                    pairs.append_pair("contentRating[]", rating);
                }
            }
            let payload = self.json(&url)?;
            let entries = payload["data"]
                .as_array()
                .context("Invalid MangaDex chapter list")?;
            total = total
                .max(
                    payload["total"]
                        .as_u64()
                        .context("Missing MangaDex chapter total")? as usize,
                )
                .max(chapters.len() + entries.len());
            for item in entries {
                let id = item["id"]
                    .as_str()
                    .filter(|id| !id.is_empty())
                    .context("Missing chapter ID")?;
                ensure!(
                    seen.insert(id.to_lowercase()),
                    "Duplicate MangaDex chapter ID {id}"
                );
                let attrs = &item["attributes"];
                chapters.push(Chapter {
                    id: id.to_owned(),
                    label: attrs["chapter"]
                        .as_str()
                        .filter(|s| !s.is_empty())
                        .unwrap_or(id)
                        .to_owned(),
                    number: attrs["chapter"].as_str().and_then(number),
                    volume: attrs["volume"].as_str().and_then(number),
                    url: self.base.join("/at-home/server/")?.join(id)?,
                    count: attrs["pages"].as_u64().map(|n| n as usize),
                    external: attrs["externalUrl"].as_str().is_some_and(|s| !s.is_empty()),
                });
            }
            if chapters.len() >= total {
                break;
            }
            ensure!(
                !entries.is_empty(),
                "MangaDex feed ended before its declared total"
            );
        }
        ensure!(
            !chapters.is_empty(),
            "{title} found, but no chapters matched languages ({}) and content ratings ({})",
            self.options.languages.join(", "),
            self.options.ratings.join(", ")
        );
        Ok(Manga { title, chapters })
    }

    fn pages(&self, chapter: &Chapter) -> Result<Vec<Url>> {
        let data = self.json(&chapter.url)?;
        ensure!(
            data["result"] == "ok",
            "MangaDex rejected chapter page request"
        );
        let mut base = Url::parse(data["baseUrl"].as_str().context("Missing image server")?)?;
        let (folder, key) = if self.options.data_saver {
            ("data-saver", "dataSaver")
        } else {
            ("data", "data")
        };
        let hash = data["chapter"]["hash"]
            .as_str()
            .context("Missing image hash")?;
        let files = data["chapter"][key]
            .as_array()
            .context("Missing image list")?;
        if !matches!(base.scheme(), "http" | "https") {
            bail!("Invalid image server scheme");
        }
        base.path_segments_mut()
            .map_err(|_| anyhow::anyhow!("Invalid image server"))?
            .pop_if_empty()
            .push(folder)
            .push(hash);
        files
            .iter()
            .map(|file| {
                let mut url = base.clone();
                url.path_segments_mut()
                    .expect("validated URL")
                    .push(file.as_str().context("Invalid image name")?);
                Ok(url)
            })
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn provider(source: Source) -> Box<dyn Provider> {
        open(
            Http::connect(source, false, None).unwrap(),
            Options::defaults(source),
        )
    }

    #[test]
    fn retry_after_honors_the_server_and_caps_the_delay() {
        use reqwest::header::HeaderValue;
        assert_eq!(retry_delay(None, 0), Duration::from_secs(1));
        assert_eq!(retry_delay(None, 1), Duration::from_secs(2));
        assert_eq!(
            retry_delay(Some(&HeaderValue::from_static("0.5")), 0),
            Duration::from_millis(500)
        );
        assert_eq!(
            retry_delay(Some(&HeaderValue::from_static("60")), 0),
            Duration::from_secs(30)
        );
        assert_eq!(
            retry_delay(Some(&HeaderValue::from_static("inf")), 0),
            Duration::from_secs(1)
        );
    }

    #[test]
    fn mangadex_follows_pagination_and_preserves_chapter_identity() {
        use crate::test_http::Server;
        use serde_json::json;
        let server = Server::start(|path| {
            let url = Url::parse(&format!("http://localhost{path}")).unwrap();
            let params: std::collections::HashMap<_, _> = url.query_pairs().into_owned().collect();
            let entry = |id, chapter, pages| {
                json!({
                    "id": id, "attributes": { "chapter": chapter, "volume": "2", "pages": pages }
                })
            };
            let payload = match url.path() {
                "/manga" => {
                    assert_eq!(params["title"], "Alternate");
                    json!({ "data": [
                        { "id": "partial", "attributes": { "title": { "en": "Alternate Story" } } },
                        { "id": "exact", "attributes": { "title": { "en": "Primary" }, "altTitles": [{ "en": "Alternate" }] } }
                    ] })
                }
                "/chapter" => {
                    assert_eq!(params["manga"], "exact");
                    assert_eq!(params["translatedLanguage[]"], "it");
                    assert_eq!(params["contentRating[]"], "safe");
                    match params["offset"].as_str() {
                        "0" => json!({ "total": 2, "data": [entry("first", "10.5", 2)] }),
                        "1" => json!({ "total": 2, "data": [entry("extra", "Special", 0)] }),
                        _ => panic!("Unexpected offset"),
                    }
                }
                "/at-home/server/first" => {
                    json!({ "result": "ok", "baseUrl": "https://images.example",
                        "chapter": { "hash": "hash", "data": [], "dataSaver": ["page b.jpg", "page a.jpg"] }
                    })
                }
                _ => return (404, Vec::new()),
            };
            (200, payload.to_string().into_bytes())
        });
        let provider = MangaDex {
            base: Url::parse(&server.url).unwrap(),
            http: Http::new(Client::new(), false),
            options: MangaDexOptions {
                languages: vec!["it".into()],
                ratings: vec!["safe".into()],
                data_saver: true,
            },
            last_api_request: Mutex::new(None),
        };
        let manga = provider.search("Alternate").unwrap();
        assert_eq!(manga.title, "Primary");
        assert_eq!(manga.chapters.len(), 2);
        assert_eq!(manga.chapters[0].id, "first");
        assert_eq!(manga.chapters[0].number, Some(10.5));
        assert_eq!(manga.chapters[1].label, "Special");
        let pages = provider.pages(&manga.chapters[0]).unwrap();
        assert_eq!(
            pages[0].as_str(),
            "https://images.example/data-saver/hash/page%20b.jpg"
        );
        assert_eq!(
            pages[1].as_str(),
            "https://images.example/data-saver/hash/page%20a.jpg"
        );
    }

    mod fanfox_live {
        use super::*;

        #[test]
        #[ignore = "requires live FanFox"]
        fn test_fetch_manga() {
            let manga = provider(Source::Fanfox)
                .search("Boku dake ga Inai Machi")
                .unwrap();
            assert!(!manga.chapters.is_empty());
        }

        #[test]
        #[ignore = "requires live FanFox"]
        fn test_fetch_manga_chapter_pages() {
            let provider = provider(Source::Fanfox);
            let manga = provider.search("Boku dake ga Inai Machi").unwrap();
            let chapter = manga
                .chapters
                .iter()
                .find(|ch| ch.number == Some(1.0))
                .unwrap();
            assert!(!provider.pages(chapter).unwrap().is_empty());
        }
    }

    mod mangadex_live {
        use super::*;

        #[test]
        #[ignore = "requires live MangaDex"]
        fn test_fetch_manga() {
            let manga = provider(Source::Mangadex)
                .search("Backstage Lovers")
                .unwrap();
            assert!(!manga.chapters.is_empty());
        }

        #[test]
        #[ignore = "requires live MangaDex"]
        fn test_fetch_manga_chapter_pages() {
            let provider = provider(Source::Mangadex);
            let manga = provider.search("Backstage Lovers").unwrap();
            let chapter = manga
                .chapters
                .iter()
                .find(|ch| !ch.external && ch.count.unwrap_or(0) > 0)
                .unwrap();
            assert_eq!(
                provider.pages(chapter).unwrap().len(),
                chapter.count.unwrap()
            );
        }
    }
}
