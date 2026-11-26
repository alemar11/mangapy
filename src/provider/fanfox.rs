use super::{Chapter, Http, Manga, Provider, legacy_slug, normalized, number};
use anyhow::{Context, Result, ensure};
use regex::Regex;
use reqwest::{
    Url,
    header::{COOKIE, HeaderMap, HeaderValue, REFERER},
};
use scraper::{Html, Selector};
use std::{collections::HashSet, sync::LazyLock};

pub const BASE: &str = "https://fanfox.net";
pub const USER_AGENT: &str =
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36";
pub struct FanFox {
    http: Http,
    base: Url,
}

fn selector(value: &str) -> Selector {
    Selector::parse(value).expect("valid static selector")
}

static IMAGE_BASE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r#"pix="(.+?)""#).unwrap());
static CHAPTER_ID: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"chapterid\s*=\s*(\d+)").unwrap());
static CHAPTER_KEY: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"var guidkey=(.*?)';").unwrap());
static IMAGE_COUNT: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"imagecount\s*=\s*(\d+)").unwrap());
static INLINE_IMAGES: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"newImgs\s*=\s*\[([^\]]+)\]").unwrap());

fn capture<'a>(pattern: &Regex, text: &'a str) -> Option<&'a str> {
    Some(pattern.captures(text)?.get(1)?.as_str())
}

impl FanFox {
    pub fn new(http: Http) -> Self {
        Self {
            http,
            base: Url::parse(BASE).expect("valid FanFox base URL"),
        }
    }

    fn html(&self, url: Url) -> Result<String> {
        Ok(self.http.get(&url, self.page_headers(&url))?.text()?)
    }

    fn manga(&self, url: Url, title: &str) -> Result<Manga> {
        parse_manga(&self.base, &self.html(url)?, title)?.context("No FanFox chapters found")
    }

    fn batches(&self, base: &Url, cid: &str, count: usize, key: &str) -> Result<Vec<Url>> {
        let mut links = Vec::new();
        for page in (1..=count).step_by(2) {
            let mut url = base.join("chapterfun.ashx")?;
            url.query_pairs_mut()
                .append_pair("cid", cid)
                .append_pair("page", &page.to_string())
                .append_pair("key", key);
            let script = unpack(&self.html(url)?)?;
            let prefix = capture(&IMAGE_BASE, &script).context("Missing FanFox image base")?;
            static PATH: LazyLock<Regex> = LazyLock::new(|| Regex::new(r#""(/\w.+?)""#).unwrap());
            for value in PATH.captures_iter(&script) {
                links.push(base.join(&format!("{prefix}{}", &value[1]))?);
            }
        }
        ensure!(
            links.len() == count,
            "FanFox advertised {count} pages but returned {}",
            links.len()
        );
        Ok(links)
    }
}

fn parse_manga(base: &Url, html: &str, title: &str) -> Result<Option<Manga>> {
    let doc = Html::parse_document(html);
    let mut chapters = Vec::new();
    let mut seen = HashSet::new();
    for list in ["#list-1", "#list-2"] {
        let links = selector(&format!("{list} ul.detail-main-list a[href]"));
        for link in doc.select(&links) {
            let url = base.join(link.attr("href").unwrap())?;
            let Some(id) = url
                .path_segments()
                .into_iter()
                .flatten()
                .filter(|part| !part.is_empty())
                .rev()
                .find_map(|part| {
                    part.strip_prefix('c')
                        .filter(|id| id.as_bytes().first().is_some_and(u8::is_ascii_digit))
                })
            else {
                continue;
            };
            if !seen.insert(id.to_owned()) {
                continue;
            }
            chapters.push(Chapter {
                id: id.to_owned(),
                label: id.to_owned(),
                number: number(id),
                volume: None,
                url,
                count: None,
                external: false,
            });
        }
    }
    Ok((!chapters.is_empty()).then(|| Manga {
        title: title.to_owned(),
        chapters,
    }))
}

impl Provider for FanFox {
    fn search(&self, title: &str) -> Result<Manga> {
        let url = self.base.join(&format!("/manga/{}/", legacy_slug(title)))?;
        match self.html(url) {
            Ok(html) => {
                if let Some(manga) = parse_manga(&self.base, &html, title)? {
                    return Ok(manga);
                }
            }
            Err(err)
                if err
                    .downcast_ref::<reqwest::Error>()
                    .and_then(reqwest::Error::status)
                    == Some(reqwest::StatusCode::NOT_FOUND) => {}
            Err(err) => return Err(err.context("FanFox direct lookup failed")),
        }
        let mut url = self.base.join("/search")?;
        url.query_pairs_mut().append_pair("title", title);
        let doc = Html::parse_document(&self.html(url)?);
        let query = normalized(title);
        let mut selected = None;
        let mut suggestions = Vec::new();
        for link in doc.select(&selector(
            "ul.manga-list-4-list p.manga-list-4-item-title a[href]",
        )) {
            let name = link.text().collect::<String>().trim().to_owned();
            if !name.is_empty() && suggestions.len() < 5 {
                suggestions.push(name.clone());
            }
            let candidate = normalized(&name);
            if candidate == query
                || (selected.is_none() && !query.is_empty() && candidate.contains(&query))
            {
                selected = Some((name, link.attr("href").unwrap()));
                if candidate == query {
                    break;
                }
            }
        }
        let (title, href) = selected.with_context(|| {
            if suggestions.is_empty() {
                format!("Manga not found: {title}")
            } else {
                format!(
                    "Manga not found: {title}. Suggestions: {}",
                    suggestions.join(", ")
                )
            }
        })?;
        self.manga(self.base.join(href)?, &title)
    }

    fn page_headers(&self, url: &Url) -> HeaderMap {
        let mut headers = HeaderMap::new();
        headers.insert(
            REFERER,
            HeaderValue::from_str(self.base.as_str().trim_end_matches('/'))
                .expect("valid FanFox referer"),
        );
        if self.base.origin() == url.origin() {
            headers.insert(COOKIE, HeaderValue::from_static("isAdult=1"));
        }
        headers
    }

    fn pages(&self, chapter: &Chapter) -> Result<Vec<Url>> {
        let page = self.html(chapter.url.clone())?;
        let doc = Html::parse_document(&page);
        let last_page = doc
            .select(&selector("a[data-page]"))
            .filter_map(|node| node.attr("data-page")?.parse().ok())
            .max();
        let cid = capture(&CHAPTER_ID, &page);
        let key = || {
            unpack(&page)
                .ok()
                .and_then(|script| {
                    capture(&CHAPTER_KEY, &script).map(|s| s.replace(['\'', '\\', '+'], ""))
                })
                .unwrap_or_default()
        };
        let mut batch_error = None;
        let mut attempted_count = None;
        if let Some((cid, count)) =
            cid.zip(capture(&IMAGE_COUNT, &page).and_then(|s| s.parse::<usize>().ok()))
            && count > 0
        {
            attempted_count = Some(count);
            match self.batches(&chapter.url, cid, count, "") {
                Ok(pages) => return Ok(pages),
                Err(err) => batch_error = Some(err),
            }
            let key = key();
            if !key.is_empty() {
                match self.batches(&chapter.url, cid, count, &key) {
                    Ok(pages) => return Ok(pages),
                    Err(err) => batch_error = Some(err),
                }
            }
        }
        if let Some(count) = last_page.filter(|count| Some(*count) != attempted_count) {
            match self.batches(
                &chapter.url,
                cid.context("Missing FanFox chapter ID")?,
                count,
                &key(),
            ) {
                Ok(pages) => return Ok(pages),
                Err(err) => batch_error = Some(err),
            }
        }
        for script in doc.select(&selector("script")) {
            if let Ok(script) = unpack(&script.inner_html())
                && let Some(links) = capture(&INLINE_IMAGES, &script)
            {
                return links
                    .split(',')
                    .map(|s| Ok(chapter.url.join(&unescape(s.trim())?)?))
                    .collect();
            }
        }
        Err(batch_error.unwrap_or_else(|| anyhow::anyhow!("No FanFox images found")))
    }
}

fn unescape(quoted: &str) -> Result<String> {
    ensure!(
        quoted.len() >= 2
            && matches!(quoted.as_bytes()[0], b'\'' | b'"')
            && quoted.as_bytes()[0] == quoted.as_bytes()[quoted.len() - 1],
        "Invalid JavaScript string"
    );
    let mut chars = quoted[1..quoted.len() - 1].chars();
    let mut decoded = String::new();
    while let Some(c) = chars.next() {
        if c != '\\' {
            decoded.push(c);
            continue;
        }
        let escape = chars.next().context("Incomplete JavaScript escape")?;
        match escape {
            'n' => decoded.push('\n'),
            'r' => decoded.push('\r'),
            't' => decoded.push('\t'),
            'b' => decoded.push('\x08'),
            'f' => decoded.push('\x0c'),
            'v' => decoded.push('\x0b'),
            '0' => decoded.push('\0'),
            '\n' => {}
            'x' | 'u' => {
                let width = if escape == 'x' { 2 } else { 4 };
                let hex: String = chars.by_ref().take(width).collect();
                ensure!(hex.len() == width, "Incomplete JavaScript Unicode escape");
                decoded.push(
                    char::from_u32(u32::from_str_radix(&hex, 16)?)
                        .context("Invalid Unicode escape")?,
                );
            }
            other => decoded.push(other),
        }
    }
    Ok(decoded)
}

fn unpack(content: &str) -> Result<String> {
    static ARGS: LazyLock<Regex> = LazyLock::new(|| {
        Regex::new(
        r#"\}\(\s*('(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*('(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")\.split\(\s*['"]\|['"]\s*\)"#
    ).unwrap()
    });
    const ALPHABET: &[u8] = b"0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";
    let args = ARGS
        .captures(content)
        .context("Missing packed FanFox script")?;
    let mut script = unescape(&args[1])?;
    let radix: usize = args[2].parse()?;
    let count: usize = args[3].parse()?;
    let dictionary = unescape(&args[4])?;
    let words: Vec<_> = dictionary.split('|').collect();
    ensure!(
        (2..=ALPHABET.len()).contains(&radix) && count <= words.len(),
        "Invalid FanFox packer dictionary"
    );
    for (index, word) in words[..count]
        .iter()
        .enumerate()
        .rev()
        .filter(|(_, word)| !word.is_empty())
    {
        let mut digits = Vec::new();
        let mut value = index;
        loop {
            digits.push(ALPHABET[value % radix] as char);
            value /= radix;
            if value == 0 {
                break;
            }
        }
        let token: String = digits.into_iter().rev().collect();
        script = Regex::new(&format!(r"\b{token}\b"))?
            .replace_all(&script, regex::NoExpand(word))
            .into_owned();
        ensure!(
            script.len() <= 8 * 1024 * 1024,
            "FanFox script exceeded unpack size limit"
        );
    }
    Ok(script)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fanfox_direct_lookup_falls_back_on_404_only() {
        let server = crate::test_http::Server::start(|path| {
            match path {
            "/manga/lookup/" => (404, vec![]),
            "/manga/unavailable/" => (503, vec![]),
            "/search?title=Lookup" => (200, br#"<ul class="manga-list-4-list"><li><p class="manga-list-4-item-title"><a href="/manga/translated/">Lookup</a></p></li></ul>"#.to_vec()),
            "/manga/translated/" => (200, br#"<div id="list-1"><ul class="detail-main-list"><li><a href="/manga/translated/c001/1.html">1</a></li></ul></div>"#.to_vec()),
            _ => (404, vec![]),
        }
        });
        let repo = FanFox {
            http: Http::new(reqwest::blocking::Client::new(), false),
            base: Url::parse(&server.url).unwrap(),
        };
        let manga = repo.search("Lookup").unwrap();
        assert_eq!(manga.chapters[0].number, Some(1.0));
        assert_eq!(
            repo.page_headers(&manga.chapters[0].url)[COOKIE],
            "isAdult=1"
        );
        assert!(
            !repo
                .page_headers(&Url::parse("https://cdn.example").unwrap())
                .contains_key(COOKIE)
        );
        let err = repo.search("Unavailable").err().unwrap();
        assert_eq!(
            err.downcast_ref::<reqwest::Error>().unwrap().status(),
            Some(reqwest::StatusCode::SERVICE_UNAVAILABLE)
        );
    }

    #[test]
    fn fanfox_discovers_ordered_pages_with_the_packed_key() {
        use crate::test_http::Server;
        let server = Server::start(|path| {
            let content = match path {
                "/manga/example/c001/1.html" => {
                    r#"<script>
                    chapterid = 123; imagecount = 3;
                    eval(function(p,a,c,k,e,d){}("var guidkey='secret';",62,0,''.split('|')))
                </script>"#
                }
                "/manga/example/c001/chapterfun.ashx?cid=123&page=1&key=secret" => {
                    r#"eval(function(p,a,c,k,e,d){}('pix="https://images.example"; images=["/01.jpg","/02.jpg"];',62,0,''.split('|')))"#
                }
                "/manga/example/c001/chapterfun.ashx?cid=123&page=3&key=secret" => {
                    r#"eval(function(p,a,c,k,e,d){}('pix="https://images.example"; images=["/03.jpg"];',62,0,''.split('|')))"#
                }
                _ => return (403, vec![]),
            };
            (200, content.as_bytes().to_vec())
        });
        let repo = FanFox {
            http: Http::new(reqwest::blocking::Client::new(), false),
            base: Url::parse(&server.url).unwrap(),
        };
        let chapter = Chapter {
            id: "001".into(),
            label: "001".into(),
            number: Some(1.0),
            volume: None,
            url: Url::parse(&format!("{}/manga/example/c001/1.html", server.url)).unwrap(),
            count: None,
            external: false,
        };
        let pages = repo.pages(&chapter).unwrap();
        assert_eq!(
            pages.iter().map(Url::as_str).collect::<Vec<_>>(),
            [
                "https://images.example/01.jpg",
                "https://images.example/02.jpg",
                "https://images.example/03.jpg",
            ]
        );
    }

    #[test]
    fn fanfox_merges_chapter_lists() {
        let html = r#"
            <div id="list-1"><ul class="detail-main-list">
                <li><a href="/manga/example/v02/c010.5/1.html">10.5</a></li>
            </ul></div>
            <div id="list-2"><ul class="detail-main-list">
                <li><a href="/manga/example/v02/c010.5/1.html">10.5</a></li>
                <li><a href="/manga/example/v01/c001/1.html">1</a></li>
            </ul></div>"#;
        let manga = parse_manga(&Url::parse(BASE).unwrap(), html, "Example")
            .unwrap()
            .unwrap();
        assert_eq!(
            manga.chapters.iter().map(|c| c.number).collect::<Vec<_>>(),
            [Some(10.5), Some(1.0)]
        );
    }

    #[test]
    fn fanfox_unpacks_without_evaluating_script() {
        let packed =
            r#"eval(function(p,a,c,k,e,d){}('0="1";',62,2,'pix|https://example.org'.split('|')))"#;
        assert_eq!(unpack(packed).unwrap(), r#"pix="https://example.org";"#);
        assert!(unpack(&packed.replace(",62,", ",1,")).is_err());
    }
}
